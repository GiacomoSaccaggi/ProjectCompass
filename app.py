# +----------------------------------------------+
# | PROJECT COMPASS APPLICATION                  |
# +----------------------------------------------+
"""
ProjectCompass — Analysis catalog and execution platform.
"""
import fcntl
import os
from typing import IO

from flask import Flask
from flask_apscheduler import APScheduler
from flask_cors import CORS

from basefun import ProjectCompass
from config import Config
from logging_config import setup_logging
from utils.app_settings import PublicAppSettings, SettingsLoader
from utils.feature_gate import FeatureGate


def acquire_scheduler_lock(lock_file_path: str) -> IO[str] | None:
    """Attempt to acquire a non-blocking exclusive OS file lock for APScheduler leader election."""
    os.makedirs(os.path.dirname(os.path.abspath(lock_file_path)), exist_ok=True)
    lock_handle = open(lock_file_path, "w", encoding="utf-8")
    try:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        lock_handle.write(str(os.getpid()))
        lock_handle.flush()
        return lock_handle
    except OSError:
        lock_handle.close()
        return None


def create_app(config_class: type = Config) -> Flask:
    default_root = os.path.dirname(os.path.abspath(__file__))
    path = default_root + '/'

    template_path = os.path.join(path, 'templates')
    app = Flask(__name__, template_folder=template_path, static_folder=os.path.join(path, 'static'))
    app.url_map.strict_slashes = False
    app.config.from_object(config_class)

    env_data_dir = os.environ.get('DATA_DIR')
    cfg_data_dir = app.config.get('DATA_DIR')
    if cfg_data_dir and os.path.abspath(str(cfg_data_dir)) != os.path.abspath(default_root):
        resolved_data_dir = os.path.abspath(str(cfg_data_dir))
    elif env_data_dir:
        resolved_data_dir = os.path.abspath(env_data_dir)
    else:
        resolved_data_dir = os.path.abspath(str(cfg_data_dir or default_root))

    app.config['DATA_DIR'] = resolved_data_dir
    data_path = resolved_data_dir.rstrip('/') + '/'
    os.makedirs(resolved_data_dir, exist_ok=True)
    os.makedirs(os.path.join(resolved_data_dir, 'tmp'), exist_ok=True)
    os.makedirs(os.path.join(resolved_data_dir, 'rag_data'), exist_ok=True)

    default_db_uri = 'sqlite:///' + os.path.join(default_root, 'projectcompass.db')
    if (
        resolved_data_dir != os.path.abspath(default_root)
        and app.config.get('SQLALCHEMY_DATABASE_URI') == default_db_uri
        and not os.environ.get('DATABASE_URL')
    ):
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(resolved_data_dir, 'projectcompass.db')

    default_lock = os.path.join(default_root, 'tmp', 'scheduler.lock')
    if (
        resolved_data_dir != os.path.abspath(default_root)
        and app.config.get('SCHEDULER_LOCK_FILE') == default_lock
        and not os.environ.get('SCHEDULER_LOCK_FILE')
    ):
        app.config['SCHEDULER_LOCK_FILE'] = os.path.join(resolved_data_dir, 'tmp', 'scheduler.lock')

    # Initialize database
    from models import init_db, init_fts
    init_db(app)
    init_fts(app)

    settings = SettingsLoader.from_environment(
        app.config.get('PC_CONFIG_FILE'), resolved_data_dir,
    ).load()
    template_settings = settings.for_templates()
    app.config['PC_SETTINGS'] = settings
    for connection_error in settings.connection_errors:
        app.logger.warning('Skipping configured database connection: %s', connection_error)

    @app.context_processor
    def inject_pc_settings() -> dict[str, PublicAppSettings]:
        active = app.config.get('PC_SETTINGS')
        return {'pc': active.for_templates() if hasattr(active, 'for_templates') else template_settings}

    FeatureGate(settings.features).install(app)

    # Security: restrict CORS
    CORS(app, resources={r"/api/*": {"origins": os.environ.get('ALLOWED_ORIGINS', '*').split(',')}})

    # Setup logging
    setup_logging(app)

    # Initialize core webapp
    webapp = ProjectCompass(dir_path=path, data_dir=data_path)
    webapp.apply_settings(template_settings)
    app.config['WEBAPP'] = webapp

    if (
        app.config.get('USE_GIT_SYNC')
        or app.config.get('USE_GITLAB_REPO')
        or webapp._is_git_sync_enabled()
    ):
        repo_url = str(app.config.get('GIT_REPO_URL') or os.environ.get('GIT_REPO_URL', '')).strip()
        if repo_url:
            webapp.git_init_or_clone(
                repo_url=repo_url,
                branch=str(app.config.get('GIT_BRANCH') or os.environ.get('GIT_BRANCH', 'main')),
                target_dir=webapp.save_folder_path,
                token=str(app.config.get('GIT_TOKEN') or os.environ.get('GIT_TOKEN', '')),
            )

    # Register blueprints
    from blueprints.agent import agent_bp
    from blueprints.api import api_bp
    from blueprints.auth import auth_bp
    from blueprints.catalog import catalog_bp
    from blueprints.connections import connections_bp
    from blueprints.data import data_bp
    from blueprints.k8s import k8s_bp
    from blueprints.rag import rag_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(catalog_bp)
    app.register_blueprint(data_bp)
    app.register_blueprint(connections_bp)
    app.register_blueprint(agent_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(rag_bp)
    app.register_blueprint(k8s_bp)

    # Scheduler with file-lock leader election across Gunicorn workers
    if 'SCHEDULER_JOBSTORES' not in app.config:
        if app.config.get('TESTING'):
            app.config['SCHEDULER_JOBSTORES'] = {'default': {'type': 'memory'}}
        else:
            scheduler_db_path = os.path.join(resolved_data_dir, 'scheduler_jobs.db')
            app.config['SCHEDULER_JOBSTORES'] = {
                'default': {'type': 'sqlalchemy', 'url': f'sqlite:///{scheduler_db_path}'}
            }
    app.config['SCHEDULER_JOB_DEFAULTS'] = {
        'coalesce': True,
        'max_instances': 1,
        'misfire_grace_time': 60,
    }
    app.config['SCHEDULER_API_ENABLED'] = False

    lock_path = app.config.get('SCHEDULER_LOCK_FILE', os.path.join(resolved_data_dir, 'tmp', 'scheduler.lock'))
    lock_handle = acquire_scheduler_lock(lock_path)

    scheduler = APScheduler()
    scheduler.init_app(app)
    if lock_handle is not None:
        scheduler.start()
        app.config['SCHEDULER_IS_LEADER'] = True
        app.config['_SCHEDULER_LOCK_HANDLE'] = lock_handle
    else:
        scheduler._scheduler.start(paused=True)
        app.config['SCHEDULER_IS_LEADER'] = False
        app.config['_SCHEDULER_LOCK_HANDLE'] = None
    app.config['SCHEDULER'] = scheduler

    if app.config['SCHEDULER_IS_LEADER']:
        from utils.db_connection_service import DbConnectionService
        from utils.managed_connections import ManagedConnectionSync

        with app.app_context():
            sync_report = ManagedConnectionSync(DbConnectionService()).sync(
                settings.connections,
                preserve_unlisted=bool(settings.connection_errors),
            )
        app.logger.info(
            'Managed database connections synchronized: %d created, %d updated, %d removed, %d skipped.',
            len(sync_report.created),
            len(sync_report.updated),
            len(sync_report.removed),
            len(sync_report.skipped),
        )

    # Health endpoint
    @app.route('/health')
    def health():
        from flask import jsonify
        return jsonify({'status': 'ok', 'version': '0.1.0'})

    return app


# Application instance for gunicorn
app = create_app()


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    host = '0.0.0.0' if os.environ.get('FLASK_ENV') == 'production' else '127.0.0.1'
    app.run(host=host, port=port, debug=debug)

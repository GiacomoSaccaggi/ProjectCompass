# +----------------------------------------------+
# | APPLICATION DATABASE MODELS                  |
# +----------------------------------------------+
from datetime import datetime, timezone

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='editor')  # admin, editor, viewer
    email = db.Column(db.String(120))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)


class DbConnection(db.Model):
    __tablename__ = 'db_connections'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    db_type = db.Column(db.String(50), nullable=False)
    host = db.Column(db.String(255))
    port = db.Column(db.Integer)
    database = db.Column(db.String(255))
    username = db.Column(db.String(255))
    password_encrypted = db.Column(db.Text)
    file_path = db.Column(db.Text)
    extra_params_json = db.Column(db.Text)
    custom_uri_encrypted = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), nullable=False,
    )
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        nullable=False,
    )
    last_tested_at = db.Column(db.DateTime)
    last_test_ok = db.Column(db.Boolean)
    last_test_message = db.Column(db.Text)
    managed = db.Column(db.Boolean, nullable=False, default=False)


class Execution(db.Model):
    __tablename__ = 'executions'
    id = db.Column(db.Integer, primary_key=True)
    analysis_name = db.Column(db.String(200), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    finished_at = db.Column(db.DateTime)
    status = db.Column(db.String(20), default='running')  # running, success, failed, aborted
    output_path = db.Column(db.String(500))
    log_text = db.Column(db.Text)
    inputs_json = db.Column(db.Text)  # JSON list/dict of inputs
    outputs_json = db.Column(db.Text)  # JSON list of output files
    job_name = db.Column(db.String(200))
    namespace = db.Column(db.String(100), default='default')
    node_name = db.Column(db.String(200))
    exit_code = db.Column(db.Integer)
    error_message = db.Column(db.Text)
    trigger_type = db.Column(db.String(20), default='manual')  # manual, scheduled


class K8sWorkerNode(db.Model):
    __tablename__ = 'k8s_worker_nodes'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), unique=True, nullable=False)
    uid = db.Column(db.String(100))
    status = db.Column(db.String(30), nullable=False)  # Ready, NotReady, Unknown, Removed
    roles = db.Column(db.String(100), default='worker')
    internal_ip = db.Column(db.String(100))
    cpu_capacity = db.Column(db.String(50))
    memory_capacity = db.Column(db.String(50))
    cpu_allocatable = db.Column(db.String(50))
    memory_allocatable = db.Column(db.String(50))
    cpu_usage = db.Column(db.String(50))
    memory_usage = db.Column(db.String(50))
    kubelet_version = db.Column(db.String(50))
    first_seen_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_seen_at = db.Column(db.DateTime, default=datetime.utcnow)
    removed_at = db.Column(db.DateTime, nullable=True)

    @property
    def address(self) -> str | None:
        return self.internal_ip

    @address.setter
    def address(self, value: str | None) -> None:
        self.internal_ip = value


class PipelineVersion(db.Model):
    __tablename__ = 'pipeline_versions'
    id = db.Column(db.Integer, primary_key=True)
    analysis_name = db.Column(db.String(200), nullable=False)
    version_num = db.Column(db.Integer, nullable=False)
    graph_json = db.Column(db.Text)
    script_text = db.Column(db.Text)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    message = db.Column(db.String(500))


class FlowVersion(db.Model):
    __tablename__ = 'flow_versions'
    id = db.Column(db.Integer, primary_key=True)
    flow_name = db.Column(db.String(200), nullable=False, index=True)
    version_num = db.Column(db.Integer, nullable=False)
    code = db.Column(db.Text, nullable=False)
    config_json = db.Column(db.Text, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    message = db.Column(db.String(500), default='')


class FlowChain(db.Model):
    __tablename__ = 'flow_chains'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), unique=True, nullable=False)
    description = db.Column(db.Text, default='')
    flow_names_json = db.Column(db.Text, nullable=False)  # JSON list of ordered flow names
    owner = db.Column(db.String(100), default='flow-author')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class ChainExecution(db.Model):
    __tablename__ = 'chain_executions'
    id = db.Column(db.Integer, primary_key=True)
    chain_id = db.Column(db.Integer, db.ForeignKey('flow_chains.id'), nullable=False)
    chain_name = db.Column(db.String(200), nullable=False)
    status = db.Column(db.String(20), default='running')  # running, success, failed, aborted
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    finished_at = db.Column(db.DateTime, nullable=True)
    current_step = db.Column(db.Integer, default=0)
    execution_ids_json = db.Column(db.Text, default='[]')  # JSON list of Execution IDs
    trigger_type = db.Column(db.String(20), default='manual')  # manual, scheduled
    error_message = db.Column(db.Text, nullable=True)


class AuditLog(db.Model):
    __tablename__ = 'audit_log'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    action = db.Column(db.String(50), nullable=False)
    target_type = db.Column(db.String(50))
    target_name = db.Column(db.String(200))
    details_json = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Comment(db.Model):
    __tablename__ = 'comments'
    id = db.Column(db.Integer, primary_key=True)
    analysis_name = db.Column(db.String(200), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    text = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Webhook(db.Model):
    __tablename__ = 'webhooks'
    id = db.Column(db.Integer, primary_key=True)
    analysis_name = db.Column(db.String(200), nullable=False)
    url = db.Column(db.String(500), nullable=False)
    secret = db.Column(db.String(100))
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class ApiToken(db.Model):
    __tablename__ = 'api_tokens'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    token_hash = db.Column(db.String(256), nullable=False)
    name = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime)
    revoked = db.Column(db.Boolean, default=False)


def _ensure_execution_columns():
    """Ensure existing SQLite executions table has all Kubernetes Job tracking columns."""
    from sqlalchemy import text
    try:
        rows = db.session.execute(text("PRAGMA table_info(executions)")).fetchall()
        existing_cols = {row[1] for row in rows}
        migrations = [
            ("job_name", "VARCHAR(200)"),
            ("namespace", "VARCHAR(100) DEFAULT 'default'"),
            ("node_name", "VARCHAR(200)"),
            ("exit_code", "INTEGER"),
            ("error_message", "TEXT"),
            ("trigger_type", "VARCHAR(20) DEFAULT 'manual'"),
        ]
        for col_name, col_type in migrations:
            if col_name not in existing_cols:
                db.session.execute(text(f"ALTER TABLE executions ADD COLUMN {col_name} {col_type}"))
        db.session.commit()
    except Exception:
        db.session.rollback()


def _ensure_db_connection_columns() -> None:
    """Add management metadata to existing saved-connection tables."""
    from sqlalchemy import inspect, text
    from sqlalchemy.exc import SQLAlchemyError

    table_name = DbConnection.__tablename__
    try:
        existing_columns = {column['name'] for column in inspect(db.engine).get_columns(table_name)}
        if 'managed' in existing_columns:
            return
        db.session.execute(text(
            'ALTER TABLE db_connections ADD COLUMN managed BOOLEAN NOT NULL DEFAULT FALSE'
        ))
        db.session.commit()
    except SQLAlchemyError as exc:
        db.session.rollback()
        try:
            updated_columns = {column['name'] for column in inspect(db.engine).get_columns(table_name)}
        except SQLAlchemyError:
            db.session.rollback()
            raise RuntimeError('Unable to inspect the saved database connection schema.') from exc
        if 'managed' not in updated_columns:
            raise RuntimeError('Unable to add managed metadata to saved database connections.') from exc


def _sqlite_db_path_from_uri(uri: str) -> str | None:
    """Resolve the filesystem path of a SQLite database URI, or None for in-memory/non-SQLite."""
    import os

    if not uri.startswith('sqlite:///') or ':memory:' in uri:
        return None
    raw_path = uri[len('sqlite:///'):].split('?', 1)[0]
    if not raw_path:
        return None
    return raw_path if raw_path.startswith('/') else os.path.abspath(raw_path)


def _salvage_and_reset_corrupt_sqlite(db_path: str) -> dict[str, tuple[list[str], list[tuple]]] | None:
    """Run PRAGMA quick_check and table probes; if malformed, salvage intact rows and remove corrupt file."""
    import os
    import sqlite3

    if not db_path or not os.path.exists(db_path):
        return None

    regular_tables = (
        'users',
        'db_connections',
        'executions',
        'k8s_worker_nodes',
        'pipeline_versions',
        'flow_versions',
        'flow_chains',
        'chain_executions',
        'audit_log',
        'comments',
        'webhooks',
        'api_tokens',
    )
    corrupted = False
    conn = None
    try:
        conn = sqlite3.connect(db_path, timeout=10.0)
        chk = conn.execute('PRAGMA quick_check').fetchall()
        if not chk or any(row[0] != 'ok' for row in chk):
            corrupted = True
        else:
            existing = [
                r[0]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                ).fetchall()
            ]
            for tbl in existing:
                conn.execute(f'SELECT count(*) FROM "{tbl}"').fetchone()
    except sqlite3.DatabaseError:
        corrupted = True
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

    if not corrupted:
        return None

    salvaged: dict[str, tuple[list[str], list[tuple]]] = {}
    try:
        conn = sqlite3.connect(db_path, timeout=10.0)
        for tbl in regular_tables:
            try:
                cur = conn.execute(f'SELECT * FROM "{tbl}"')
                cols = [d[0] for d in (cur.description or [])]
                rows = cur.fetchall()
                if cols and rows:
                    salvaged[tbl] = (cols, rows)
            except Exception:
                continue
    except Exception:
        pass
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

    for suffix in ('', '-wal', '-shm', '-journal'):
        target = f'{db_path}{suffix}'
        if os.path.exists(target):
            try:
                os.remove(target)
            except OSError:
                pass

    return salvaged


def _restore_salvaged_rows(salvaged: dict[str, tuple[list[str], list[tuple]]] | None) -> None:
    """Re-insert salvaged rows into a freshly rebuilt SQLite database."""
    if not salvaged:
        return
    from sqlalchemy import inspect, text

    try:
        inspector = inspect(db.engine)
        for tbl, (cols, rows) in salvaged.items():
            try:
                valid_cols = {c['name'] for c in inspector.get_columns(tbl)}
                keep_idx = [i for i, col in enumerate(cols) if col in valid_cols]
                if not keep_idx:
                    continue
                keep_cols = [cols[i] for i in keep_idx]
                col_list = ', '.join(f'"{c}"' for c in keep_cols)
                param_list = ', '.join(f':p{i}' for i in range(len(keep_cols)))
                stmt = text(f'INSERT OR IGNORE INTO "{tbl}" ({col_list}) VALUES ({param_list})')
                for row in rows:
                    params = {f'p{n}': row[idx] for n, idx in enumerate(keep_idx)}
                    db.session.execute(stmt, params)
                db.session.commit()
            except Exception:
                db.session.rollback()
    except Exception:
        db.session.rollback()


def _configure_sqlite_pragmas(app):
    """Configure SQLite busy_timeout and journal_mode for PVC and multi-worker safety."""
    import os

    from sqlalchemy import text

    uri = str(app.config.get('SQLALCHEMY_DATABASE_URI', ''))
    if not uri.startswith('sqlite'):
        return
    journal_mode = os.environ.get('SQLITE_JOURNAL_MODE', 'DELETE').strip().upper()
    try:
        db.session.execute(text("PRAGMA busy_timeout = 5000"))
        if ':memory:' not in uri and journal_mode in ('WAL', 'DELETE', 'TRUNCATE', 'PERSIST', 'MEMORY'):
            db.session.execute(text(f"PRAGMA journal_mode = {journal_mode}"))
        db.session.commit()
    except Exception:
        db.session.rollback()


def _acquire_db_init_lock(app, db_path: str | None):
    """Acquire an exclusive file lock to serialize schema initialization across Gunicorn workers."""
    import fcntl
    import os

    data_dir = app.config.get('DATA_DIR') or os.environ.get('DATA_DIR', '')
    if data_dir:
        lock_dir = os.path.join(data_dir, 'tmp')
    elif db_path:
        lock_dir = os.path.dirname(db_path) or '/tmp'
    else:
        lock_dir = '/tmp'
    try:
        os.makedirs(lock_dir, exist_ok=True)
        lock_file = open(os.path.join(lock_dir, 'db_init.lock'), 'w')
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        return lock_file
    except Exception:
        return None


def _release_db_init_lock(lock_file) -> None:
    """Release the file lock acquired by _acquire_db_init_lock."""
    import fcntl

    if lock_file is None:
        return
    try:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
    except Exception:
        pass
    try:
        lock_file.close()
    except Exception:
        pass


def init_db(app):
    uri = str(app.config.get('SQLALCHEMY_DATABASE_URI', ''))
    db_path = _sqlite_db_path_from_uri(uri)
    lock_file = _acquire_db_init_lock(app, db_path)
    try:
        salvaged = _salvage_and_reset_corrupt_sqlite(db_path) if db_path else None
        if 'sqlalchemy' not in app.extensions:
            db.init_app(app)
        with app.app_context():
            if salvaged is not None:
                db.session.remove()
                db.engine.dispose()
            _configure_sqlite_pragmas(app)
            db.create_all()
            _ensure_db_connection_columns()
            _ensure_execution_columns()
            _restore_salvaged_rows(salvaged)
    finally:
        _release_db_init_lock(lock_file)


def init_fts(app):
    """Initialize FTS5 virtual table for full-text search, repairing if malformed."""
    uri = str(app.config.get('SQLALCHEMY_DATABASE_URI', ''))
    db_path = _sqlite_db_path_from_uri(uri)
    lock_file = _acquire_db_init_lock(app, db_path)
    try:
        with app.app_context():
            from sqlalchemy import text
            try:
                db.session.execute(text(
                    'CREATE VIRTUAL TABLE IF NOT EXISTS analyses_fts USING fts5'
                    '(name, title, description, readme_text, script_text)'
                ))
                db.session.execute(text('SELECT count(*) FROM analyses_fts')).fetchall()
                db.session.commit()
            except Exception:
                db.session.rollback()
                try:
                    db.session.execute(text('DROP TABLE IF EXISTS analyses_fts'))
                    db.session.execute(text(
                        'CREATE VIRTUAL TABLE IF NOT EXISTS analyses_fts USING fts5'
                        '(name, title, description, readme_text, script_text)'
                    ))
                    db.session.commit()
                except Exception:
                    db.session.rollback()
    finally:
        _release_db_init_lock(lock_file)


def index_analysis_fts(name, title='', description='', readme_text='', script_text=''):
    """Index or update an analysis in the FTS table."""
    from sqlalchemy import text
    try:
        db.session.execute(text("DELETE FROM analyses_fts WHERE name = :name"), {'name': name})
        db.session.execute(text(
            "INSERT INTO analyses_fts(name, title, description, readme_text, script_text) "
            "VALUES(:name, :title, :desc, :readme, :script)"
        ), {'name': name, 'title': title, 'desc': description, 'readme': readme_text, 'script': script_text})
        db.session.commit()
    except Exception:
        db.session.rollback()


def log_action(action, target_type, target_name, details=None, user_id=None):
    """Log an action to the audit trail."""
    import json

    from flask import session
    entry = AuditLog(
        user_id=user_id or session.get('user_id'),
        action=action,
        target_type=target_type,
        target_name=target_name,
        details_json=json.dumps(details) if details else None,
    )
    db.session.add(entry)
    db.session.commit()


def fire_webhooks(analysis_name, payload):
    """Fire webhooks for an analysis after execution."""
    import hashlib
    import hmac
    import json

    import requests
    webhooks = Webhook.query.filter_by(analysis_name=analysis_name, active=True).all()
    for wh in webhooks:
        try:
            headers = {'Content-Type': 'application/json'}
            if wh.secret:
                sig = hmac.new(wh.secret.encode(), json.dumps(payload).encode(), hashlib.sha256).hexdigest()
                headers['X-Webhook-Signature'] = sig
            requests.post(wh.url, json=payload, headers=headers, timeout=5)
        except Exception:
            pass  # Don't fail execution on webhook errors

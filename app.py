"""
ProjectCompass — Analysis catalog and execution platform.
"""
import os

from flask import Flask
from flask_cors import CORS

from basefun import ProjectCompass
from config import Config
from logging_config import setup_logging


def create_app(config_class=Config):
    path = os.path.dirname(os.path.abspath(__file__)) + '/'

    template_path = os.path.join(path, 'templates')
    app = Flask(__name__, template_folder=template_path, static_folder=os.path.join(path, 'static'))
    app.config.from_object(config_class)

    # Security: restrict CORS
    CORS(app, resources={r"/api/*": {"origins": os.environ.get('ALLOWED_ORIGINS', '*').split(',')}})

    # Setup logging
    setup_logging(app)

    # Initialize core webapp
    webapp = ProjectCompass(dir_path=path)
    app.config['WEBAPP'] = webapp

    # Register blueprints
    from blueprints.agent import agent_bp
    from blueprints.api import api_bp
    from blueprints.auth import auth_bp
    from blueprints.catalog import catalog_bp
    from blueprints.data import data_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(catalog_bp)
    app.register_blueprint(data_bp)
    app.register_blueprint(agent_bp)
    app.register_blueprint(api_bp)

    # Health endpoint
    @app.route('/health')
    def health():
        from flask import jsonify
        return jsonify({'status': 'ok', 'version': '0.1.0'})

    # Ensure directories exist
    os.makedirs(os.path.join(path, 'tmp'), exist_ok=True)

    return app


# Application instance for gunicorn
app = create_app()


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    host = '0.0.0.0' if os.environ.get('FLASK_ENV') == 'production' else '127.0.0.1'
    app.run(host=host, port=port, debug=debug)

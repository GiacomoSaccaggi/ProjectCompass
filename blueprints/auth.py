from flask import Blueprint, current_app, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from logging_config import logger

auth_bp = Blueprint('auth', __name__)


@auth_bp.before_app_request
def require_login():
    path = request.path
    allowed = ('/login', '/static', '/health', '/api/')
    if any(path.startswith(p) for p in allowed):
        return
    if path.endswith(('.css', '.js', '.png', '.jpg', '.svg', '.ico', '.woff', '.woff2')):
        return
    if not session.get('authenticated'):
        return render_template('login_page.html')


@auth_bp.route('/login/', methods=['POST'])
def login():
    uname = request.form.get('uname', '')
    psw = request.form.get('psw', '')
    expected_user = current_app.config['ADMIN_USERNAME']
    expected_hash = current_app.config['ADMIN_PASSWORD_HASH']

    authenticated = False
    if expected_hash:
        authenticated = (uname == expected_user and check_password_hash(expected_hash, psw))
    else:
        # Fallback for first run — check against legacy constants
        webapp = current_app.config['WEBAPP']
        authenticated = (uname == webapp.constants.get('uname', '') and
                         psw == str(webapp.constants.get('psw', '')))

    if authenticated:
        session['authenticated'] = True
        logger.info(f"User '{uname}' logged in")
    else:
        logger.warning(f"Failed login attempt for '{uname}'")

    return redirect(url_for('catalog.index'))


@auth_bp.route('/logout/')
def logout():
    session.clear()
    return redirect(url_for('catalog.index'))


@auth_bp.route('/reset/')
def reset():
    session.clear()
    return redirect(url_for('catalog.index'))


def hash_password(password: str) -> str:
    """Utility to generate a password hash for .env configuration."""
    return generate_password_hash(password)

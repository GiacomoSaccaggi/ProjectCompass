from datetime import datetime
from functools import wraps

from flask import Blueprint, current_app, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from logging_config import logger
from models import User, db, log_action

auth_bp = Blueprint('auth', __name__)


def require_role(*roles):
    """Decorator to restrict access to users with specific roles."""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if session.get('role') not in roles:
                return redirect(url_for('catalog.index'))
            return f(*args, **kwargs)
        return decorated
    return decorator


@auth_bp.before_app_request
def require_login():
    path = request.path
    allowed = ('/login', '/static', '/health', '/api/', '/landing', '/setup')
    if any(path.startswith(p) for p in allowed):
        return
    if path.endswith(('.css', '.js', '.png', '.jpg', '.svg', '.ico', '.woff', '.woff2')):
        return

    # Check for Bearer token authentication
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        import hashlib

        from flask import jsonify

        from models import ApiToken
        token = auth_header[7:]
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        api_token = ApiToken.query.filter_by(token_hash=token_hash, revoked=False).first()
        if api_token:
            user = User.query.get(api_token.user_id)
            if user:
                session['authenticated'] = True
                session['user_id'] = user.id
                session['username'] = user.username
                session['role'] = user.role
                return  # allow request
        return jsonify({'error': 'Invalid token'}), 401

    if not session.get('authenticated'):
        # First-time setup: if no users exist at all, show setup wizard
        if User.query.count() == 0:
            return render_template('setup_wizard.html', step='1')
        return render_template('landing.html')


@auth_bp.route('/login/', methods=['POST'])
def login():
    uname = request.form.get('uname', '')
    psw = request.form.get('psw', '')

    authenticated = False
    user = None

    # First, check if any users exist in the database
    user_count = User.query.count()

    if user_count > 0:
        # Multi-user mode: check against database
        user = User.query.filter_by(username=uname).first()
        if user and check_password_hash(user.password_hash, psw):
            authenticated = True
    else:
        # Backward compat: no users in DB, fall back to env var
        expected_user = current_app.config['ADMIN_USERNAME']
        expected_hash = current_app.config['ADMIN_PASSWORD_HASH']

        if expected_hash:
            authenticated = (uname == expected_user and check_password_hash(expected_hash, psw))
        else:
            # Fallback for first run — check against legacy constants
            webapp = current_app.config['WEBAPP']
            authenticated = (uname == webapp.constants.get('uname', '') and
                             psw == str(webapp.constants.get('psw', '')))

        # In legacy mode, treat as admin
        if authenticated:
            session['user_id'] = None
            session['username'] = uname
            session['role'] = 'admin'

    if authenticated:
        session['authenticated'] = True
        if user:
            session['user_id'] = user.id
            session['username'] = user.username
            session['role'] = user.role
            user.last_login = datetime.utcnow()
            db.session.commit()
        log_action('login', 'user', uname)
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


# --- Setup Wizard Routes ---

@auth_bp.route('/setup')
def setup_page():
    """Setup wizard page - shows different steps based on query param."""
    step = request.args.get('step', '1')
    # If users exist and not authenticated, redirect to landing
    if User.query.count() > 0 and not session.get('authenticated'):
        return render_template('landing.html')
    return render_template('setup_wizard.html', step=step)


@auth_bp.route('/setup/create-admin', methods=['POST'])
def setup_create_admin():
    """Create the first admin user during setup."""
    if User.query.count() > 0:
        return redirect('/')
    username = request.form.get('username', 'admin').strip()
    email = request.form.get('email', '').strip() or None
    password = request.form.get('password', '')
    if not username or not password:
        return render_template('setup_wizard.html', step='1', error='Username and password required')
    user = User(
        username=username,
        email=email,
        password_hash=generate_password_hash(password),
        role='admin'
    )
    db.session.add(user)
    db.session.commit()
    session['authenticated'] = True
    session['user_id'] = user.id
    session['username'] = user.username
    session['role'] = 'admin'
    log_action('setup', 'user', username)
    logger.info(f"Setup wizard: created admin user '{username}'")
    return redirect('/setup?step=2')


@auth_bp.route('/setup/upload-data', methods=['POST'])
def setup_upload_data():
    """Upload first dataset during setup (optional step)."""
    import os
    webapp = current_app.config['WEBAPP']
    f = request.files.get('file')
    if f and f.filename:
        filepath = os.path.join(webapp.save_data_path, f.filename)
        f.save(filepath)
        log_action('upload', 'data', f.filename)
        logger.info(f"Setup wizard: uploaded file '{f.filename}'")
    return redirect('/setup?step=3')


@auth_bp.route('/admin/users', methods=['GET'])
@require_role('admin')
def admin_users():
    webapp = current_app.config['WEBAPP']
    html_part = webapp.substitute_html(port=webapp.constants.get("port", 5000),
                                        project_folder=webapp.project_folder)
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template('admin_users.html',
                           head=html_part['head'],
                           top_container=html_part['top_container'],
                           sidebar_menu=html_part['sidebar_menu'],
                           users=users)


@auth_bp.route('/admin/users/create', methods=['POST'])
@require_role('admin')
def admin_create_user():
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '')
    role = request.form.get('role', 'editor')
    email = request.form.get('email', '').strip() or None

    if not username or not password:
        return redirect(url_for('auth.admin_users'))

    if role not in ('admin', 'editor', 'viewer'):
        role = 'editor'

    # Check if username already exists
    if User.query.filter_by(username=username).first():
        logger.warning(f"Attempt to create duplicate user '{username}'")
        return redirect(url_for('auth.admin_users'))

    user = User(
        username=username,
        password_hash=generate_password_hash(password),
        role=role,
        email=email
    )
    db.session.add(user)
    db.session.commit()
    logger.info(f"User '{username}' created by '{session.get('username')}'")

    return redirect(url_for('auth.admin_users'))


@auth_bp.route('/admin/users/<int:user_id>/delete', methods=['POST'])
@require_role('admin')
def admin_delete_user(user_id):
    user = User.query.get(user_id)
    if user:
        # Prevent self-deletion
        if user.id == session.get('user_id'):
            logger.warning(f"User '{session.get('username')}' attempted self-deletion")
            return redirect(url_for('auth.admin_users'))

        username = user.username
        db.session.delete(user)
        db.session.commit()
        logger.info(f"User '{username}' deleted by '{session.get('username')}'")

    return redirect(url_for('auth.admin_users'))


def hash_password(password: str) -> str:
    """Utility to generate a password hash for .env configuration."""
    return generate_password_hash(password)


# --- API Token Management ---

@auth_bp.route('/api/tokens', methods=['POST'])
def create_token():
    import hashlib
    import secrets

    from flask import jsonify

    from models import ApiToken
    if not session.get('authenticated'):
        return jsonify({'error': 'Unauthorized'}), 401
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    name = request.json.get('name', 'API Token') if request.is_json else 'API Token'
    api_token = ApiToken(user_id=session['user_id'], token_hash=token_hash, name=name)
    db.session.add(api_token)
    db.session.commit()
    log_action('create', 'api_token', name)
    return jsonify({'token': token, 'id': api_token.id, 'name': name})


@auth_bp.route('/api/tokens/<int:token_id>', methods=['DELETE'])
def revoke_token(token_id):
    from flask import jsonify

    from models import ApiToken
    if not session.get('authenticated'):
        return jsonify({'error': 'Unauthorized'}), 401
    token = ApiToken.query.get_or_404(token_id)
    if token.user_id != session.get('user_id'):
        return jsonify({'error': 'Forbidden'}), 403
    token.revoked = True
    db.session.commit()
    log_action('delete', 'api_token', token.name or f'Token {token_id}')
    return jsonify({'success': True})


@auth_bp.route('/settings')
def settings_page():
    from models import ApiToken
    if not session.get('authenticated'):
        return redirect(url_for('catalog.index'))
    webapp = current_app.config['WEBAPP']
    html_part = webapp.substitute_html(port=webapp.constants.get("port", 5000),
                                        project_folder=webapp.project_folder)
    tokens = ApiToken.query.filter_by(user_id=session.get('user_id'), revoked=False).order_by(
        ApiToken.created_at.desc()).all()
    return render_template('settings.html',
                           head=html_part['head'],
                           top_container=html_part['top_container'],
                           sidebar_menu=html_part['sidebar_menu'],
                           port=webapp.constants.get("port", 5000),
                           project_folder=webapp.project_folder,
                           username=session.get('username'),
                           role=session.get('role'),
                           tokens=tokens)


@auth_bp.route('/admin/metrics')
@require_role('admin')
def admin_metrics():
    webapp = current_app.config['WEBAPP']
    html_part = webapp.substitute_html(port=webapp.constants.get("port", 5000),
                                        project_folder=webapp.project_folder)
    return render_template('admin_metrics.html',
                           head=html_part['head'],
                           top_container=html_part['top_container'],
                           sidebar_menu=html_part['sidebar_menu'])


@auth_bp.route('/api/metrics')
def api_metrics():
    from datetime import timedelta

    from flask import jsonify
    from sqlalchemy import func

    from models import AuditLog, Execution
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)

    # Executions per day (last 30 days)
    daily = db.session.query(
        func.date(Execution.started_at).label('day'),
        func.count().label('count')
    ).filter(Execution.started_at >= thirty_days_ago).group_by('day').all()

    # Status breakdown
    statuses = db.session.query(Execution.status, func.count()).group_by(Execution.status).all()

    # Top analyses
    top = db.session.query(
        Execution.analysis_name, func.count().label('c')
    ).group_by(Execution.analysis_name).order_by(func.count().desc()).limit(5).all()

    # Total counts
    total_execs = Execution.query.count()
    total_actions = AuditLog.query.count()
    total_users = User.query.count()

    # Success rate
    success_count = sum(s[1] for s in statuses if s[0] == 'success')
    success_rate = round((success_count / total_execs * 100) if total_execs > 0 else 0, 1)

    # Count analyses
    webapp = current_app.config['WEBAPP']
    analyses = webapp.read_multiple_analysis()
    total_analyses = len(analyses)

    return jsonify({
        'daily': [{'day': str(d[0]), 'count': d[1]} for d in daily],
        'statuses': {s[0] or 'unknown': s[1] for s in statuses},
        'top_analyses': [{'name': t[0], 'count': t[1]} for t in top],
        'total_executions': total_execs,
        'total_actions': total_actions,
        'total_users': total_users,
        'total_analyses': total_analyses,
        'success_rate': success_rate,
    })

from datetime import datetime

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


class Execution(db.Model):
    __tablename__ = 'executions'
    id = db.Column(db.Integer, primary_key=True)
    analysis_name = db.Column(db.String(200), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    finished_at = db.Column(db.DateTime)
    status = db.Column(db.String(20), default='running')  # running, success, failed
    output_path = db.Column(db.String(500))
    log_text = db.Column(db.Text)
    inputs_json = db.Column(db.Text)  # JSON list of input datasets
    outputs_json = db.Column(db.Text)  # JSON list of output files


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


def init_db(app):
    db.init_app(app)
    with app.app_context():
        db.create_all()


def init_fts(app):
    """Initialize FTS5 virtual table for full-text search."""
    with app.app_context():
        from sqlalchemy import text
        db.session.execute(text(
            'CREATE VIRTUAL TABLE IF NOT EXISTS analyses_fts USING fts5'
            '(name, title, description, readme_text, script_text)'
        ))
        db.session.commit()


def index_analysis_fts(name, title='', description='', readme_text='', script_text=''):
    """Index or update an analysis in the FTS table."""
    from sqlalchemy import text
    db.session.execute(text("DELETE FROM analyses_fts WHERE name = :name"), {'name': name})
    db.session.execute(text(
        "INSERT INTO analyses_fts(name, title, description, readme_text, script_text) "
        "VALUES(:name, :title, :desc, :readme, :script)"
    ), {'name': name, 'title': title, 'desc': description, 'readme': readme_text, 'script': script_text})
    db.session.commit()


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

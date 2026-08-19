"""Tests for models.py — database models, log_action, init_fts, index_analysis_fts."""
# ruff: noqa: S106  # Hardcoded passwords are expected in tests
import json
import uuid

from models import (
    ApiToken,
    AuditLog,
    Comment,
    Execution,
    PipelineVersion,
    User,
    Webhook,
    db,
    index_analysis_fts,
    init_fts,
    log_action,
)


def _unique_username():
    """Generate a unique username to avoid constraint violations."""
    return f'user_{uuid.uuid4().hex[:8]}'


def test_user_creation(app):
    """Test creating a User and verifying fields."""
    with app.app_context():
        username = _unique_username()
        user = User(
            username=username,
            password_hash='hashed_pw_123',
            role='editor',
            email='test@example.com'
        )
        db.session.add(user)
        db.session.commit()

        assert user.id is not None
        assert user.username == username
        assert user.password_hash == 'hashed_pw_123'
        assert user.role == 'editor'
        assert user.email == 'test@example.com'
        assert user.created_at is not None


def test_execution_creation(app):
    """Test creating an Execution record."""
    with app.app_context():
        user = User(username=_unique_username(), password_hash='pw', role='admin')
        db.session.add(user)
        db.session.commit()

        execution = Execution(
            analysis_name='My Analysis',
            user_id=user.id,
            status='running',
            output_path='/outputs/test',
            inputs_json='["dataset1.csv"]',
            outputs_json='["result.csv"]'
        )
        db.session.add(execution)
        db.session.commit()

        assert execution.id is not None
        assert execution.analysis_name == 'My Analysis'
        assert execution.status == 'running'
        assert execution.started_at is not None


def test_pipeline_version_creation(app):
    """Test creating a PipelineVersion record."""
    with app.app_context():
        user = User(username=_unique_username(), password_hash='pw', role='editor')
        db.session.add(user)
        db.session.commit()

        version = PipelineVersion(
            analysis_name='Pipeline Test',
            version_num=1,
            graph_json='{"nodes": []}',
            script_text='print("hello")',
            user_id=user.id,
            message='Initial version'
        )
        db.session.add(version)
        db.session.commit()

        assert version.id is not None
        assert version.version_num == 1
        assert version.message == 'Initial version'
        assert version.created_at is not None


def test_log_action(app):
    """Test log_action() creates an AuditLog entry with explicit user_id."""
    with app.app_context():
        # Create a user first
        user = User(username=_unique_username(), password_hash='pw', role='admin')
        db.session.add(user)
        db.session.commit()

        target_name = f'TestAnalysis_{uuid.uuid4().hex[:8]}'
        log_action(
            action='create',
            target_type='analysis',
            target_name=target_name,
            details={'foo': 'bar'},
            user_id=user.id
        )

        entry = AuditLog.query.filter_by(target_name=target_name).first()
        assert entry is not None
        assert entry.action == 'create'
        assert entry.target_type == 'analysis'
        assert entry.user_id == user.id
        assert json.loads(entry.details_json) == {'foo': 'bar'}


def test_log_action_no_session(app):
    """Test log_action() with explicit user_id (no session)."""
    with app.app_context():
        user = User(username=_unique_username(), password_hash='pw', role='viewer')
        db.session.add(user)
        db.session.commit()

        target_name = f'old_data_{uuid.uuid4().hex[:8]}.csv'
        log_action(
            action='delete',
            target_type='dataset',
            target_name=target_name,
            details=None,
            user_id=user.id
        )

        entry = AuditLog.query.filter_by(target_name=target_name).first()
        assert entry is not None
        assert entry.user_id == user.id
        assert entry.action == 'delete'
        assert entry.details_json is None


def test_comment_creation(app):
    """Test creating a Comment."""
    with app.app_context():
        user = User(username=_unique_username(), password_hash='pw', role='editor')
        db.session.add(user)
        db.session.commit()

        comment = Comment(
            analysis_name='My Analysis',
            user_id=user.id,
            text='This is a great analysis!'
        )
        db.session.add(comment)
        db.session.commit()

        assert comment.id is not None
        assert comment.text == 'This is a great analysis!'
        assert comment.created_at is not None


def test_webhook_creation(app):
    """Test creating a Webhook."""
    with app.app_context():
        webhook = Webhook(
            analysis_name='Webhook Analysis',
            url='https://example.com/hook',
            secret='mysecret123',
            active=True
        )
        db.session.add(webhook)
        db.session.commit()

        assert webhook.id is not None
        assert webhook.url == 'https://example.com/hook'
        assert webhook.secret == 'mysecret123'
        assert webhook.active is True


def test_api_token_creation(app):
    """Test creating an ApiToken."""
    with app.app_context():
        user = User(username=_unique_username(), password_hash='pw', role='admin')
        db.session.add(user)
        db.session.commit()

        token = ApiToken(
            user_id=user.id,
            token_hash='hashed_token_value',
            name='My API Token',
            revoked=False
        )
        db.session.add(token)
        db.session.commit()

        assert token.id is not None
        assert token.token_hash == 'hashed_token_value'
        assert token.name == 'My API Token'
        assert token.revoked is False


def test_init_fts(app):
    """Test init_fts() creates the FTS5 virtual table."""
    with app.app_context():
        init_fts(app)

        # Query the FTS table to verify it exists
        from sqlalchemy import text
        result = db.session.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='analyses_fts'")
        ).fetchone()
        assert result is not None
        assert result[0] == 'analyses_fts'


def test_index_analysis_fts(app):
    """Test index_analysis_fts() indexes an analysis and allows search."""
    with app.app_context():
        init_fts(app)

        name = f'sales_report_{uuid.uuid4().hex[:8]}'
        # Index an analysis
        index_analysis_fts(
            name=name,
            title='Monthly Sales Report',
            description='Analysis of monthly sales data',
            readme_text='This report covers Q1 sales',
            script_text='import pandas as pd'
        )

        # Search for it
        from sqlalchemy import text
        results = db.session.execute(
            text("SELECT name, title FROM analyses_fts WHERE analyses_fts MATCH 'sales'")
        ).fetchall()

        # Find our specific entry
        our_result = [r for r in results if r[0] == name]
        assert len(our_result) == 1
        assert our_result[0][1] == 'Monthly Sales Report'


def test_index_analysis_fts_update(app):
    """Test that re-indexing replaces the old entry."""
    with app.app_context():
        init_fts(app)

        name = f'test_analysis_{uuid.uuid4().hex[:8]}'
        # Index once
        index_analysis_fts(name=name, title='Old Title')
        # Update
        index_analysis_fts(name=name, title='New Title')

        from sqlalchemy import text
        results = db.session.execute(
            text("SELECT title FROM analyses_fts WHERE name = :name"),
            {'name': name}
        ).fetchall()

        # Should only have one entry with the new title
        assert len(results) == 1
        assert results[0][0] == 'New Title'

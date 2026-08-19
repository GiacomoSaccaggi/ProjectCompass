import os
import sys

import pytest

# Ensure project root is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def app():
    from app import create_app
    from config import Config
    from models import db

    class TestConfig(Config):
        TESTING = True
        SECRET_KEY = 'test-secret'
        WTF_CSRF_ENABLED = False
        SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'

    app = create_app(TestConfig)

    with app.app_context():
        db.create_all()
        # Initialize FTS table
        from sqlalchemy import text
        db.session.execute(text(
            'CREATE VIRTUAL TABLE IF NOT EXISTS analyses_fts USING fts5'
            '(name, title, description, readme_text, script_text)'
        ))
        db.session.commit()
        yield app
        db.drop_all()


@pytest.fixture
def client(app):
    with app.test_client() as client:
        with app.app_context():
            # Auto-authenticate for tests
            with client.session_transaction() as sess:
                sess['authenticated'] = True
        yield client


@pytest.fixture
def unauth_client(app):
    """Client without authentication."""
    with app.test_client() as client:
        yield client

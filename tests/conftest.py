# +----------------------------------------------+
# | SHARED TEST FIXTURES                         |
# +----------------------------------------------+
import os
import sys
from unittest.mock import patch

import pytest

os.environ['PC_CONFIG_FILE'] = os.devnull

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class _MockEmbedder:
    """Deterministic embedder for tests — no model download."""
    def embed(self, texts):
        return [[0.1, 0.2, 0.3] * 128 for _ in texts]
    def embed_query(self, text):
        return [0.1, 0.2, 0.3] * 128


@pytest.fixture(autouse=True)
def _mock_local_embedder():
    """Globally prevent scomp-link from downloading embedding models in tests.
    Must patch at the USAGE site (pipeline.py), not the definition site (embedder.py).
    """
    with patch('scomp_link.llm.rag.pipeline.get_local_embedder', return_value=_MockEmbedder()):
        yield


@pytest.fixture
def app(tmp_path, monkeypatch):
    from app import create_app
    from config import Config
    from models import db

    class TestConfig(Config):
        TESTING = True
        SECRET_KEY = 'test-secret'
        WTF_CSRF_ENABLED = False
        SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
        PC_CONFIG_FILE = os.devnull

    monkeypatch.setenv('PC_WORKERS__AUTO_PROVISION', 'false')
    monkeypatch.setenv('PC_FEATURES__AI_CHAT', 'true')
    monkeypatch.setenv('PC_FEATURES__RAG', 'true')
    monkeypatch.setenv('PC_FEATURES__PIPELINE_BUILDER', 'true')
    monkeypatch.setenv('PC_FEATURES__RAWGRAPHS', 'true')
    monkeypatch.setenv('PC_FEATURES__QUERY_RUNNER', 'true')
    monkeypatch.setenv('PC_FEATURES__DB_CONNECTIONS', 'true')
    monkeypatch.setenv('PC_FEATURES__TODO', 'true')
    monkeypatch.setenv('PC_DEMO__ENABLED', 'true')
    monkeypatch.setenv('PC_BRANDING__DEMO_NOTICE__ENABLED', 'true')
    app = create_app(TestConfig)

    with app.app_context():
        db.create_all()
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
            with client.session_transaction() as sess:
                sess['authenticated'] = True
        yield client


@pytest.fixture
def unauth_client(app):
    """Client without authentication."""
    with app.test_client() as client:
        yield client

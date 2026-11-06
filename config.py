import os
from datetime import timedelta

from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', os.urandom(32).hex())
    DEBUG = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    PORT = int(os.environ.get('PORT', 5000))
    USE_GITLAB_REPO = os.environ.get('USE_GITLAB_REPO', 'False').lower() == 'true'
    ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'admin')
    ADMIN_PASSWORD_HASH = os.environ.get('ADMIN_PASSWORD_HASH', '')
    PERMANENT_SESSION_LIFETIME = timedelta(hours=24)
    MITHRIL_HOST = os.environ.get('MITHRIL_HOST', 'http://localhost:16180')
    MITHRIL_EMBED_MODEL = os.environ.get('MITHRIL_EMBED_MODEL', 'gemini-embedding-exp-03-07')
    MITHRIL_RERANK_MODEL = os.environ.get('MITHRIL_RERANK_MODEL', 'gemini-2.5-flash')
    RAG_EMBED_BACKEND = os.environ.get('RAG_EMBED_BACKEND', 'local')  # 'local' (E5) or 'mithril' (cloud)
    WTF_CSRF_ENABLED = True
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'DATABASE_URL',
        'sqlite:///' + os.path.join(os.path.dirname(os.path.abspath(__file__)), 'projectcompass.db')
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

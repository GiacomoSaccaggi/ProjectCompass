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
    OLLAMA_HOST = os.environ.get('OLLAMA_HOST', 'http://localhost:11434')
    WTF_CSRF_ENABLED = True

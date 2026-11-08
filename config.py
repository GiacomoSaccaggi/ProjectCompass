# +----------------------------------------------+
# | PROJECT COMPASS CONFIGURATION                |
# +----------------------------------------------+
import os
from datetime import timedelta

from dotenv import load_dotenv

load_dotenv()


class Config:
    DATA_DIR = os.environ.get('DATA_DIR', os.path.dirname(os.path.abspath(__file__)))
    PC_CONFIG_FILE = os.environ.get('PC_CONFIG_FILE')
    DB_CONNECTIONS_KEY = os.environ.get('DB_CONNECTIONS_KEY') or None
    DB_CONNECTIONS_MAX_ROWS = int(os.environ.get('DB_CONNECTIONS_MAX_ROWS', '100000'))
    SECRET_KEY = os.environ.get('SECRET_KEY', os.urandom(32).hex())
    DEBUG = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    PORT = int(os.environ.get('PORT', 5000))
    USE_GITLAB_REPO = os.environ.get('USE_GITLAB_REPO', 'False').lower() == 'true'
    ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'admin')
    ADMIN_PASSWORD_HASH = os.environ.get('ADMIN_PASSWORD_HASH', '')
    API_AUTH_TOKEN = os.environ.get('API_AUTH_TOKEN', '')
    PERMANENT_SESSION_LIFETIME = timedelta(hours=24)
    MITHRIL_HOST = os.environ.get('MITHRIL_HOST', 'http://localhost:16180')
    MITHRIL_EMBED_MODEL = os.environ.get('MITHRIL_EMBED_MODEL', 'gemini-embedding-exp-03-07')
    MITHRIL_RERANK_MODEL = os.environ.get('MITHRIL_RERANK_MODEL', 'gemini-2.5-flash')
    RAG_EMBED_BACKEND = os.environ.get('RAG_EMBED_BACKEND', 'local')  # 'local' (E5) or 'mithril' (cloud)
    WTF_CSRF_ENABLED = True
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'DATABASE_URL',
        'sqlite:///' + os.path.join(DATA_DIR, 'projectcompass.db')
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Kubernetes / k0s configuration
    K8S_NAMESPACE = os.environ.get('K8S_NAMESPACE', 'default')
    K8S_KUBECONFIG = os.environ.get('K8S_KUBECONFIG', os.environ.get('KUBECONFIG', ''))
    K8S_IN_CLUSTER = os.environ.get('K8S_IN_CLUSTER', 'auto')
    K8S_API_URL = os.environ.get('K8S_API_URL', '')
    K8S_BEARER_TOKEN = os.environ.get('K8S_BEARER_TOKEN', '')
    K8S_VERIFY_SSL = os.environ.get('K8S_VERIFY_SSL', 'true')
    K8S_DEFAULT_IMAGE = os.environ.get('K8S_DEFAULT_IMAGE', 'python:3.11-slim')
    K8S_JOB_TTL_SECONDS = int(os.environ.get('K8S_JOB_TTL_SECONDS', 300))
    K8S_DEFAULT_CPU_REQUEST = os.environ.get('K8S_DEFAULT_CPU_REQUEST', '500m')
    K8S_DEFAULT_CPU_LIMIT = os.environ.get('K8S_DEFAULT_CPU_LIMIT', '1')
    K8S_DEFAULT_MEMORY_REQUEST = os.environ.get('K8S_DEFAULT_MEMORY_REQUEST', '512Mi')
    K8S_DEFAULT_MEMORY_LIMIT = os.environ.get('K8S_DEFAULT_MEMORY_LIMIT', '1Gi')
    K8S_SECRET_REFS = os.environ.get('K8S_SECRET_REFS', '')
    SCHEDULER_LOCK_FILE = os.environ.get(
        'SCHEDULER_LOCK_FILE',
        os.path.join(DATA_DIR, 'tmp', 'scheduler.lock')
    )

    # Optional Git synchronization for Analyses/
    USE_GIT_SYNC = os.environ.get('USE_GIT_SYNC', os.environ.get('USE_GITLAB_REPO', 'False')).lower() == 'true'
    GIT_REPO_URL = os.environ.get('GIT_REPO_URL', '')
    GIT_BRANCH = os.environ.get('GIT_BRANCH', 'main')
    GIT_TOKEN = os.environ.get('GIT_TOKEN', '')
    GIT_SYNC_ON_SAVE = os.environ.get('GIT_SYNC_ON_SAVE', 'True').lower() == 'true'

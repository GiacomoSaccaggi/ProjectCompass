"""
ProjectCompass Configuration

Configuration settings for the ProjectCompass application.
"""

import os
from datetime import timedelta

class Config:
    """Base configuration class."""
    
    # Flask settings
    SECRET_KEY = os.environ.get('SECRET_KEY') or b'_5#y2L"F4Q8z\n\xec]/'
    DEBUG = os.environ.get('FLASK_DEBUG', 'True').lower() == 'true'
    
    # Application settings
    PORT = int(os.environ.get('PORT', 5000))
    USE_GITLAB_REPO = os.environ.get('USE_GITLAB_REPO', 'False').lower() == 'true'
    USERNAME = os.environ.get('USERNAME', 'tester')
    
    # Session settings
    PERMANENT_SESSION_LIFETIME = timedelta(hours=24)
    SESSION_TYPE = 'filesystem'
    SESSION_PERMANENT = False
    
    # CORS settings
    ALLOWED_ORIGINS = os.environ.get('ALLOWED_ORIGINS', 'https://site_to_embedded_in.com').split(',')
    
    # Paths
    PROJECT_FOLDER = os.environ.get('PROJECT_FOLDER', 'ProjectCompass/')
    ANALYSES_FOLDER = os.environ.get('ANALYSES_FOLDER', 'Analyses/')

class DevelopmentConfig(Config):
    """Development configuration."""
    DEBUG = True

class ProductionConfig(Config):
    """Production configuration."""
    DEBUG = False
    
# Configuration dictionary
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
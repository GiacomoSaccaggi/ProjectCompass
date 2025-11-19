#!/usr/bin/env python3
"""
ProjectCompass Application Runner

Simple script to start the ProjectCompass Flask application.
"""

import os
import sys

if __name__ == "__main__":
    # Add current directory to Python path
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    
    # Import and run the Flask app
    from app import app
    
    # Run the application
    app.run(
        host='127.0.0.1',
        port=5000,
        debug=True
    )
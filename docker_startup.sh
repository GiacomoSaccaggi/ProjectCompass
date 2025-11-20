#!/bin/bash

echo "Starting ProjectCompass Flask application..."
echo "Environment: ${FLASK_ENV}"
echo "Debug: ${FLASK_DEBUG}"

cd /app

echo "Starting Gunicorn server on 0.0.0.0:8080..."
gunicorn --bind 0.0.0.0:8080 --workers 4 --timeout 120 app:app
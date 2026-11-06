#!/bin/bash

echo "Starting ProjectCompass Flask application..."
echo "Environment: ${FLASK_ENV}"
echo "Debug: ${FLASK_DEBUG}"

cd /app

# Check Mithril availability in background
if [ -n "$MITHRIL_HOST" ]; then
    echo "Mithril configured at $MITHRIL_HOST"
    (sleep 5 && curl -sf "$MITHRIL_HOST/health" > /dev/null 2>&1 && echo "Mithril is ready" || echo "Mithril not yet available — AI chat will retry on demand") &
fi

echo "Starting Gunicorn server on 0.0.0.0:8080..."
gunicorn --bind 0.0.0.0:8080 --workers 4 --timeout 120 app:app

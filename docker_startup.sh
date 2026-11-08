#!/bin/bash

echo "Starting ProjectCompass Flask application..."
echo "Environment: ${FLASK_ENV}"
echo "Debug: ${FLASK_DEBUG}"

cd /app

DATA_PATH="${DATA_DIR:-/app/data}"
mkdir -p "${DATA_PATH}/Analyses" "${DATA_PATH}/Saved_data" "${DATA_PATH}/Saved_queries" "${DATA_PATH}/tmp" "${DATA_PATH}/rag_data" "${DATA_PATH}/logs"
export DATA_DIR="${DATA_PATH}"
python -m utils.content_seeder
python -c "from app import app; print('Database schema & FTS5 integrity verified.')"

# Check Mithril availability in background
if [ -n "$MITHRIL_HOST" ]; then
    echo "Mithril configured at $MITHRIL_HOST"
    (sleep 5 && curl -sf "$MITHRIL_HOST/health" > /dev/null 2>&1 && echo "Mithril is ready" || echo "Mithril not yet available — AI chat will retry on demand") &
fi

echo "Starting Gunicorn server on 0.0.0.0:8080..."
gunicorn --bind 0.0.0.0:8080 --workers "${GUNICORN_WORKERS:-4}" --timeout "${GUNICORN_TIMEOUT:-120}" app:app

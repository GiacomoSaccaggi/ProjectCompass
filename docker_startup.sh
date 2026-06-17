#!/bin/bash

echo "Starting ProjectCompass Flask application..."
echo "Environment: ${FLASK_ENV}"
echo "Debug: ${FLASK_DEBUG}"

cd /app

# Pull default LLM model in background if Ollama is configured
if [ -n "$OLLAMA_HOST" ]; then
    echo "Ollama configured at $OLLAMA_HOST — pulling qwen3:0.6b in background..."
    (sleep 10 && curl -s -X POST "http://${OLLAMA_HOST}/api/pull" -d '{"name":"qwen3:0.6b"}' > /dev/null 2>&1 && echo "Model qwen3:0.6b ready") &
fi

echo "Starting Gunicorn server on 0.0.0.0:8080..."
gunicorn --bind 0.0.0.0:8080 --workers 4 --timeout 120 app:app
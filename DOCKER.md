# Docker Documentation

## Overview

ProjectCompass runs as two services:
- **ProjectCompass**: Flask app with Gunicorn (port 8080)
- **Ollama**: Local LLM for AI chat (port 11434, optional)

## Quick Start

```bash
# Start all services
docker-compose up -d

# Check health
curl http://localhost:8080/health

# Stop
docker-compose down
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | random | Flask session key |
| `ADMIN_USERNAME` | `admin` | Login username |
| `ADMIN_PASSWORD_HASH` | *(empty)* | Werkzeug password hash |
| `PORT` | `8080` | Internal port |
| `FLASK_DEBUG` | `False` | Debug mode |
| `OLLAMA_HOST` | `ollama:11434` | Ollama endpoint |
| `ALLOWED_ORIGINS` | `*` | CORS origins |

## Volumes

| Host Path | Container Path | Purpose |
|-----------|---------------|---------|
| `./Analyses` | `/app/Analyses` | Analysis storage |
| `./Saved_data` | `/app/Saved_data` | Uploaded datasets |
| `./Saved_queries` | `/app/Saved_queries` | Saved SQL queries |
| `./logs` | `/app/log` | Application logs |
| `ollama_data` | `/root/.ollama` | LLM model storage |

## Build

```bash
# Build image
docker-compose build

# Build without cache
docker-compose build --no-cache
```

## Health Check

The container has a built-in healthcheck:
```
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3
    CMD curl -f http://localhost:8080/health || exit 1
```

Check status:
```bash
docker inspect --format='{{.State.Health.Status}}' projectcompass_app
```

## Ollama Setup

```bash
# Pull required models
docker exec ollama ollama pull llama3
docker exec ollama ollama pull nomic-embed-text

# List models
docker exec ollama ollama list
```

The AI chat (`/chat`) works without Ollama — it shows a "service unavailable" message gracefully.

## Production

```bash
# Generate password hash
docker exec projectcompass_app python -c \
  "from werkzeug.security import generate_password_hash; print(generate_password_hash('your-pass'))"
```

Then set `ADMIN_PASSWORD_HASH` in your environment or `.env` file.

### Recommended production settings:
```yaml
environment:
  - SECRET_KEY=<random-64-char-string>
  - ADMIN_PASSWORD_HASH=<werkzeug-hash>
  - ALLOWED_ORIGINS=https://yourdomain.com
  - FLASK_DEBUG=False
```

## Backup

```bash
# Backup data
tar -czf backup_$(date +%Y%m%d).tar.gz Analyses/ Saved_data/ Saved_queries/

# Backup Ollama models
docker run --rm -v ollama_data:/data -v $(pwd):/backup \
  alpine tar czf /backup/ollama_models.tar.gz -C /data .
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Port conflict | Change port in `docker-compose.yml` |
| Out of memory | Increase Docker memory to 8GB+ |
| Model download fails | `docker exec ollama ollama pull llama3` manually |
| Permission denied | `sudo chown -R $USER Analyses/ Saved_data/ Saved_queries/` |
| App won't start | Check `docker-compose logs projectcompass` |

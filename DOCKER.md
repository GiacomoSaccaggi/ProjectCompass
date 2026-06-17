# Docker Documentation

## Overview

ProjectCompass is published as a Docker image on GitHub Container Registry:

```
ghcr.io/giacomosaccaggi/projectcompass:latest
```

Two services run together:
- **ProjectCompass**: Flask app with Gunicorn (port 8080)
- **Ollama**: Local LLM for AI chat (port 11434, optional)

---

## For Users: Quick Install

No cloning needed. Download and run:

```bash
curl -O https://raw.githubusercontent.com/GiacomoSaccaggi/ProjectCompass/main/docker-compose.public.yml
docker compose -f docker-compose.public.yml up -d
open http://localhost:8080
```

Update to latest:
```bash
docker compose -f docker-compose.public.yml pull
docker compose -f docker-compose.public.yml up -d
```

---

## For Developers: Build from Source

```bash
git clone https://github.com/GiacomoSaccaggi/ProjectCompass.git
cd ProjectCompass
docker compose up -d
```

This uses `docker-compose.yml` which builds the image locally.

Build without cache:
```bash
docker compose build --no-cache
```

---

## Compose Files

| File | Purpose |
|------|---------|
| `docker-compose.public.yml` | End users — pulls pre-built image from ghcr.io |
| `docker-compose.yml` | Developers — builds from local source |

---

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

---

## Volumes

| Host Path | Container Path | Purpose |
|-----------|---------------|---------|
| `./data/Analyses` | `/app/Analyses` | Analysis storage |
| `./data/Saved_data` | `/app/Saved_data` | Uploaded datasets |
| `./data/Saved_queries` | `/app/Saved_queries` | Saved SQL queries |
| `ollama_data` | `/root/.ollama` | LLM model storage |

---

## Health Check

Built-in healthcheck in the image:
```
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3
    CMD curl -f http://localhost:8080/health || exit 1
```

Check status:
```bash
docker inspect --format='{{.State.Health.Status}}' projectcompass_app
```

---

## Ollama Setup

```bash
# Pull required models (optional — app works without them)
docker exec ollama ollama pull llama3
docker exec ollama ollama pull nomic-embed-text

# List installed models
docker exec ollama ollama list
```

---

## Production Settings

Generate a password hash:
```bash
docker exec projectcompass_app python -c \
  "from werkzeug.security import generate_password_hash; print(generate_password_hash('your-pass'))"
```

Recommended environment:
```yaml
environment:
  - SECRET_KEY=<random-64-char-string>
  - ADMIN_PASSWORD_HASH=<werkzeug-hash>
  - ALLOWED_ORIGINS=https://yourdomain.com
  - FLASK_DEBUG=False
```

---

## Backup

```bash
# Backup data
tar -czf backup_$(date +%Y%m%d).tar.gz data/

# Backup Ollama models
docker run --rm -v ollama_data:/data -v $(pwd):/backup \
  alpine tar czf /backup/ollama_models.tar.gz -C /data .
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Port conflict | Change port mapping in compose file |
| Out of memory | Increase Docker memory to 8GB+ |
| Model download fails | `docker exec ollama ollama pull llama3` manually |
| Permission denied | `sudo chown -R $USER data/` |
| App won't start | Check `docker compose logs projectcompass` |

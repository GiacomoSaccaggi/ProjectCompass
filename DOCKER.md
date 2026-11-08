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

## Customization

Copy `projectcompass.example.yaml` to `projectcompass.yaml`, edit the values you need, and mount it read-only in the container. The loader defaults to `${DATA_DIR}/projectcompass.yaml`; set `PC_CONFIG_FILE` to use another path. The Compose files contain commented mount and environment examples:

```yaml
environment:
  - PC_CONFIG_FILE=/app/data/projectcompass.yaml
  - PC_DEMO__ENABLED=false
  - PC_THEME__PRIMARY_COLOR=#1f2937
volumes:
  - ./projectcompass.yaml:/app/data/projectcompass.yaml:ro
```

Precedence is built-in defaults, then YAML values, then `PC_<SECTION>__<KEY>` environment overrides. YAML strings support `${VARIABLE}` and `${VARIABLE:-fallback}` interpolation. Invalid colors, unsafe image URLs, unknown feature names, and malformed YAML stop startup with a setting-specific message.

`branding` configures the app name, logos, favicon, page title, footer and background images. `theme` configures colors, font and the initial dark-mode state. Set `demo.enabled: false` to start without bundled analyses or datasets; `demo.analyses_dir` and `demo.data_dir` can point to alternate seed folders.

Module flags under `features` hide disabled modules and return 404 for their routes. For example, `features.ai_chat: false` disables AI chat, and `features.db_connections: false` keeps local DuckDB queries available while disabling saved remote connections.

Preset connections can be declared under `connections` in YAML only. They are reconciled by name at startup and marked read-only in the Connections page. Passwords and custom URIs can reference environment variables; pass each referenced variable into the container (for example, `WAREHOUSE_PASSWORD`) and do not put clear-text credentials in Compose files. Preset credentials are encrypted with the same stable `DB_CONNECTIONS_KEY` used by UI-created connections.

`GUNICORN_WORKERS` and `GUNICORN_TIMEOUT` configure the server process; their defaults remain `4` and `120` seconds.

### Kubernetes ConfigMap

`k8s/configmap.yaml` contains a `compass-settings` ConfigMap with a `projectcompass.yaml` key. The deployment mounts that key read-only at `/app/config/projectcompass.yaml` and sets `PC_CONFIG_FILE` accordingly. Store connection passwords in Kubernetes Secrets and expose them as container environment variables before referencing them from the YAML file.

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | random | Flask session key |
| `ADMIN_USERNAME` | `admin` | Initial admin username |
| `ADMIN_PASSWORD_HASH` | *(empty)* | Werkzeug password hash for initial admin |
| `DATABASE_URL` | `sqlite:///projectcompass.db` | Database connection string |
| `PORT` | `8080` | Internal port |
| `FLASK_DEBUG` | `False` | Debug mode |
| `DB_CONNECTIONS_KEY` | generated key file | Fernet key for saved database credentials; keep it stable across deployments |
| `DB_CONNECTIONS_MAX_ROWS` | `100000` | Maximum rows returned by a remote query |
| `PC_CONFIG_FILE` | `${DATA_DIR}/projectcompass.yaml` | Optional external application settings YAML path |
| `PC_<SECTION>__<KEY>` | built-in value | Override an individual scalar setting, for example `PC_DEMO__ENABLED=false` |
| `GUNICORN_WORKERS` | `4` | Gunicorn worker count |
| `GUNICORN_TIMEOUT` | `120` | Gunicorn request timeout in seconds |
| `MITHRIL_HOST` | `mithril:16180` | Ollama endpoint |
| `ALLOWED_ORIGINS` | `*` | CORS origins |

If `DB_CONNECTIONS_KEY` is not set, the app creates `DATA_DIR/tmp/.db_connections.key` with owner-only permissions. Keep the `DATA_DIR` volume persistent across container recreation, or set and securely preserve `DB_CONNECTIONS_KEY`; losing or changing the key makes saved passwords unreadable.

---

## Volumes

| Host Path | Container Path | Purpose |
|-----------|---------------|---------|
| `./data/Analyses` | `/app/Analyses` | Analysis storage |
| `./data/Saved_data` | `/app/Saved_data` | Uploaded datasets |
| `./data/Saved_queries` | `/app/Saved_queries` | Saved SQL queries |
| `./data/tmp` | `/app/tmp` | Persistent Fernet key for saved database connections |
| `./data/projectcompass.db` | `/app/projectcompass.db` | SQLite database (users, audit log, etc.) |
| `.mithril | /root/.mithril | Fellowship config and credentials |

---

## Multi-User Setup

ProjectCompass supports multiple users with role-based access control (RBAC).

**First startup:**
- The app creates an initial admin user from `ADMIN_USERNAME` and `ADMIN_PASSWORD_HASH` environment variables
- If no password hash is set, the admin account has no password (development only)

**Adding more users:**
- Log in as admin and navigate to `/admin/users`
- Create users with roles: `admin`, `editor`, or `viewer`

**Roles:**
| Role | Permissions |
|------|-------------|
| `admin` | Full access, user management, system settings |
| `editor` | Create/edit/execute analyses, upload data, manage database connections |
| `viewer` | Read-only access to analyses and data; may use saved connections in the Query Runner |

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

## Mithril Setup

```bash
# Pull required models (optional — app works without them)
# Configure API keys in .env:
# MITHRIL_KEY_GEMINI=AIza...
# MITHRIL_KEY_OPENAI=sk-...
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
  - DB_CONNECTIONS_KEY=<stable-fernet-key>
  - DB_CONNECTIONS_MAX_ROWS=100000
  - DATABASE_URL=sqlite:////app/data/projectcompass.db
  - ALLOWED_ORIGINS=https://yourdomain.com
  - FLASK_DEBUG=False
```

---

## Backup

```bash
# Backup data (includes database)
tar -czf backup_$(date +%Y%m%d).tar.gz data/

# Backup Ollama models
docker run --rm -v ollama_data:/data -v $(pwd):/backup \
  alpine tar czf /backup/ollama_models.tar.gz -C /data .
```

**Important:** The SQLite database (`projectcompass.db`) contains users, audit logs, execution history, and comments. Always include it in backups.

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Port conflict | Change port mapping in compose file |
| Out of memory | Increase Docker memory to 8GB+ |
| Model download fails | `# Configure API keys in .env:
# MITHRIL_KEY_GEMINI=AIza...
# MITHRIL_KEY_OPENAI=sk-...` manually |
| Permission denied | `sudo chown -R $USER data/` |
| App won't start | Check `docker compose logs projectcompass` |
| Database locked | Stop other processes accessing `projectcompass.db` |
| Lost admin password | Delete `projectcompass.db` and restart to recreate admin |

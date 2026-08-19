# Contributing to ProjectCompass

## Getting Started

```bash
git clone https://github.com/GiacomoSaccaggi/ProjectCompass.git
cd ProjectCompass
uv sync
cp .env.example .env
```

## Development Workflow

1. Create a feature branch: `git checkout -b feature/your-feature-name`
2. Make your changes
3. Run linter: `uv run ruff check .`
4. Run tests: `uv run pytest -v`
5. Commit with descriptive messages
6. Push and submit a pull request

## Project Structure

```
blueprints/              → Flask routes (auth, catalog, data, agent, api)
utils/                   → Business logic (analysis, data, HTML, agent)
templates/               → Jinja2 HTML templates
tests/                   → pytest test suite (194 tests, 83% coverage)
static/
├── css/
│   └── dark.css         → Dark mode stylesheet
├── js/                  → JavaScript modules
├── pipeline_templates/  → Pre-built pipeline templates (JSON)
├── img/                 → Images and icons
└── fonts/               → Font files
models.py                → SQLAlchemy database models (User, AuditLog, etc.)
```

## Database

ProjectCompass uses SQLite with Flask-SQLAlchemy. The database file (`projectcompass.db`) is created automatically on first run.

**Key points:**
- Models are defined in `models.py`
- No migration system — tables are created via `db.create_all()` in `app.py`
- To reset the database, delete `projectcompass.db` and restart the app

**Models overview:**
- `User` — multi-user auth with roles (admin/editor/viewer)
- `AuditLog` — tracks all user actions
- `Execution` — execution history with status and logs
- `Comment` — comments on analyses
- `Webhook` — webhook configurations with HMAC secrets
- `APIToken` — bearer tokens for API authentication

## HTMX Patterns

We use HTMX 2.0 for interactive UI without writing JavaScript. Common patterns:

```html
<!-- Load content into an element -->
<button hx-get="/api/data" hx-target="#results" hx-swap="innerHTML">
    Load Data
</button>

<!-- Submit form and swap response -->
<form hx-post="/analysis/save" hx-target="#status" hx-swap="outerHTML">
    ...
</form>

<!-- Trigger on custom events -->
<div hx-get="/notifications" hx-trigger="sse:message">
    ...
</div>

<!-- Out-of-band swaps for toast notifications -->
<div id="toast" hx-swap-oob="true">Success!</div>
```

**Conventions:**
- Use `hx-target` to specify where the response goes
- Use `hx-swap="innerHTML"` for partial updates, `"outerHTML"` for full replacement
- Use `hx-indicator` to show loading spinners
- SSE endpoints use `hx-trigger="sse:message"` for real-time updates

## Audit System

All significant user actions are logged via the `log_action()` helper:

```python
from utils.audit_utils import log_action

# In a route handler
log_action(
    user_id=current_user.id,
    action="analysis.execute",
    resource_type="analysis",
    resource_id=analysis_name,
    details={"parameters": params}
)
```

**Action naming convention:** `resource.verb` (e.g., `analysis.create`, `user.login`, `webhook.trigger`)

The audit log is viewable at `/admin/audit` and powers the activity feed on the dashboard.

## Pipeline Builder

The Pipeline Builder uses a DSL powered by scomp-link v2.2.0. To add a new block type:

1. **Define the node** in `NODE_DEFS` (in `utils/pipeline_utils.py`):
```python
NODE_DEFS["my_transform"] = {
    "label": "My Transform",
    "category": "transform",
    "inputs": ["data"],
    "outputs": ["transformed"],
    "params": {
        "column": {"type": "string", "required": True},
        "method": {"type": "select", "options": ["mean", "median"]}
    }
}
```

2. **Add code generation** in `_generate_pipeline_script()`:
```python
if node["type"] == "my_transform":
    code += f"df = my_transform(df, column='{node['params']['column']}')\n"
```

3. **Add a template** (optional) in `static/pipeline_templates/` if it's a common pattern.

## Adding a New Feature

1. Create or extend a blueprint in `blueprints/`
2. Add business logic in `utils/` if needed
3. Add database models in `models.py` if needed
4. Create HTML template in `templates/` — use HTMX for interactivity
5. Add audit logging for significant actions
6. Write tests in `tests/`
7. Run `uv run pytest && uv run ruff check .`

## Code Style

- Linted with `ruff` (config in `pyproject.toml`)
- Use `logging_config.logger` instead of `print()`
- All secrets via environment variables
- No `eval()` — use `safe_execute_pandas()` for dynamic code
- Match existing patterns in the codebase
- **HTMX attributes**: use `hx-*` attributes directly in templates, keep related attributes together
- **Dark mode**: use CSS variables from `static/css/dark.css`, test both themes

## Testing

```bash
# Run all tests (194 tests, 83% coverage)
uv run pytest -v

# Run with coverage
uv run pytest --cov=blueprints --cov=utils --cov=models --cov-report=term-missing

# Run a specific test file
uv run pytest tests/test_api.py -v

# Run tests matching a pattern
uv run pytest -k "test_audit" -v
```

**Test files:**
- `test_api.py` — REST API endpoints
- `test_auth.py` — authentication and RBAC
- `test_catalog.py` — analysis CRUD operations
- `test_data.py` — query runner and data upload
- `test_models.py` — database model tests
- `test_audit.py` — audit logging
- `test_webhooks.py` — webhook delivery and HMAC
- `test_pipeline.py` — pipeline builder and templates
- `test_search.py` — full-text search (FTS5)

## Security Rules

- Never hardcode secrets — use `.env`
- Never use `eval()` on user input — use AST-validated sandbox
- Always sanitize HTML input from query editor
- Password hashing via `werkzeug.security`
- API tokens use secure random generation
- Webhooks are signed with HMAC-SHA256

## Pull Request Guidelines

- Provide clear description of changes
- Reference any related issues
- Ensure all tests pass and linter is clean
- Update documentation if API or architecture changes
- Test dark mode if UI changes are involved

## Releasing a New Version

CI and Docker publish run only when you push a tag:

```bash
# 1. Commit your changes
git add .
git commit -m "feat: description"
git push origin main

# 2. Tag and push — this triggers lint, tests, and Docker image build
git tag v1.1.0
git push origin v1.1.0
```

The workflow publishes to `ghcr.io/giacomosaccaggi/projectcompass:latest` automatically.
See [PUBLISHING.md](PUBLISHING.md) for full details.

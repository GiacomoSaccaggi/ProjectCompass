# Changelog

All notable changes to ProjectCompass will be documented in this file.

## [2.0.0] - 2026-08-19

### Added

#### scomp-link v2.2.0 Integration
- **Pipeline Builder**: Visual ML pipeline designer with DSL `>>` syntax (`CleanStep >> SelectStep >> ModelStep >> TrainStep`)
- **ML Blocks**: 6 new blocks — Drift Detection, Explainability (SHAP/LIME), Fairness, Tuning (Optuna/Halving), Validation (K-Fold/Bootstrap), Text/NLP
- **Report Blocks**: 7 new blocks — Quick Report (expanded EDA), KPI Cards, Plotly Grid, Tabs, Comparison Table, Summary Stats, Dark Mode
- **Pipeline Templates**: 4 pre-built templates (Classification+Explainability, Anomaly Detection, Forecasting, Full ML)
- **Demo Analysis**: "ScompLink Advanced ML" showcasing all new capabilities

#### Database & Multi-User (Phase 1)
- **SQLite Backend**: Flask-SQLAlchemy with `projectcompass.db` for users, executions, comments, audit log
- **Multi-User RBAC**: Admin, editor, and viewer roles with granular permissions
- **User Management**: Admin page at `/admin/users` for creating, editing, and deleting users
- **HTMX Integration**: Progressive enhancement throughout — no full page reloads for most actions

#### UX Improvements (Phase 2)
- **Dark Mode**: Toggle with localStorage persistence, applied across all pages
- **Toast Notifications**: Success, error, info, and warning toasts for user feedback
- **Real-time Execution**: Server-Sent Events (SSE) for streaming logs, progress bar, and abort capability
- **Command Palette**: `Ctrl+K` / `Cmd+K` for quick navigation to any page or analysis

#### Pipeline & Versioning (Phase 3)
- **Execution History**: Full history page at `/executions` with status badges, filtering, and detailed logs
- **Pipeline Versioning**: Every save creates a version; restore to any previous state with one click
- **Data Lineage**: "Used by" badges on datasets showing which analyses depend on them

#### Collaboration & API (Phase 4)
- **Audit Log**: All user actions logged to database with timestamps and details
- **Activity Feed**: HTMX-loaded recent activity on dashboard
- **API Token Auth**: Bearer tokens for external integrations, manageable via `/api/tokens` endpoints
- **Comments**: Real-time HTMX comments on analyses for team collaboration
- **Webhooks**: HMAC-SHA256 signed payloads for external system integration

#### Polish (Phase 5)
- **Full-Text Search**: SQLite FTS5 with HTMX instant results dropdown
- **Pipeline Templates**: 4 pre-built templates, load with one click from Pipeline Builder
- **Export/Import**: Package analyses as ZIP for sharing and backup; import at `/import`
- **Observability Dashboard**: Admin metrics at `/admin/metrics` with Chart.js visualizations

#### Testing & Quality
- **Test Suite**: 194 pytest tests with 83% coverage
- **Linting**: Ruff lint clean with all rules passing

### Changed
- **Authentication**: Upgraded from single-user to multi-user with RBAC
- **API**: Added Bearer token authentication alongside session-based auth
- **Execution**: Replaced synchronous execution with SSE streaming and progress tracking
- **Search**: Upgraded from basic filtering to FTS5 full-text search
- **Architecture**: Added `models.py` for SQLAlchemy models, reorganized templates into `admin/` and `components/` subdirectories
- **Static Assets**: Added `static/css/dark.css` for dark mode, `static/pipeline_templates/` for ML templates

### Fixed
- **Execution Reliability**: Abort capability prevents orphaned long-running processes
- **State Persistence**: Pipeline versions and execution history now persisted to database
- **Data Integrity**: Lineage tracking prevents accidental deletion of datasets in use

---

## [1.0.0] - 2026-06-17

### Added
- **Docker image on ghcr.io**: `ghcr.io/giacomosaccaggi/projectcompass:latest`
- **GitHub Actions**: Auto-publish Docker image on version tags (`v*`)
- **`docker-compose.public.yml`**: One-command install for end users (no build required)

### Changed
- **CI**: Switched from pip to `uv` for consistent lint/test across local and CI
- **CI**: Lint and tests now run only on tag push (not every commit)
- **docker-compose.yml**: Uses published ghcr.io image by default (build commented out)
- **Ruff config**: Added per-file-ignores and additional rule suppressions for legacy code

### Fixed
- **`.gitignore`**: `*/data*` rule was excluding `blueprints/data.py` — changed to `*/data/`
- **Linting**: Resolved all 70+ ruff errors (import sorting, type comparisons, bare excepts, etc.)

## [0.1.0] - 2026-06-16

### Added
- **Flask Blueprints**: Refactored monolithic `app.py` into 5 blueprints (auth, catalog, data, agent, api)
- **REST API**: JSON endpoints at `/api/analyses`, `/api/data`, `/api/query` with pagination
- **AI Chat UI**: `/chat` route with real-time LLM interaction against datasets
- **Search & Filter**: Full-text search + filter by product/owner/country on catalog
- **Pagination**: Catalog (20/page), query results (100/page), API (configurable)
- **Test Suite**: 33 pytest tests covering auth, API, catalog, data utils, and agent safety
- **CI/CD**: GitHub Actions workflow with ruff linting and pytest
- **Ruff Linting**: Configured in `pyproject.toml`, all code passing
- **Unified Logging**: `logging_config.py` module, no more `print()` calls
- **Docker Healthcheck**: Native `curl /health` check in Dockerfile

### Changed
- **Security**: Passwords hashed via werkzeug (was plaintext in YAML)
- **Security**: Secret key from env variable (was hardcoded)
- **Security**: `eval()` replaced with AST-validated sandbox in agent
- **Security**: CORS restricted to API routes only
- **Security**: Ollama lazy-loaded (app works without LLM service)
- **Configuration**: All settings via `.env` file (python-dotenv)
- **Dependencies**: `pyproject.toml` with optional groups (`[llm]`, `[dev]`)
- **Dockerfile**: Updated to Python 3.12-slim with healthcheck

### Removed
- Monolithic `app.py` (52KB) — replaced by blueprint architecture
- Raw `eval()` in agent_utils — replaced by `safe_execute_pandas()`
- Top-level Ollama import — replaced by lazy loading
- Hardcoded credentials in YAML constants

## [0.0.0] - 2025-12-01

### Added
- Initial release of ProjectCompass
- Catalog system for analysis organization
- Data Exploration & Storage Tools
- Execution Engine functionality
- Flask web interface
- Multi-step analysis upload
- Tag-based flexible organization
- GitLab integration support
- Session management with automatic reset
- CORS configuration
- Dynamic project statistics
- Responsive web UI

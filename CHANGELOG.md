# Changelog

All notable changes to ProjectCompass will be documented in this file.

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

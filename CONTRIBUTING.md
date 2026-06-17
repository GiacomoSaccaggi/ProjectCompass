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
blueprints/     → Flask routes (auth, catalog, data, agent, api)
utils/          → Business logic (analysis, data, HTML, agent)
templates/      → Jinja2 HTML templates
tests/          → pytest test suite
static/         → CSS, JS, images, fonts
```

## Adding a New Feature

1. Create or extend a blueprint in `blueprints/`
2. Add business logic in `utils/` if needed
3. Create HTML template in `templates/` if needed
4. Write tests in `tests/`
5. Run `uv run pytest && uv run ruff check .`

## Code Style

- Linted with `ruff` (config in `pyproject.toml`)
- Use `logging_config.logger` instead of `print()`
- All secrets via environment variables
- No `eval()` — use `safe_execute_pandas()` for dynamic code
- Match existing patterns in the codebase

## Testing

```bash
# Run all tests
uv run pytest -v

# Run with coverage
uv run pytest --cov=blueprints --cov=utils --cov-report=term-missing

# Run a specific test file
uv run pytest tests/test_api.py -v
```

## Security Rules

- Never hardcode secrets — use `.env`
- Never use `eval()` on user input — use AST-validated sandbox
- Always sanitize HTML input from query editor
- Password hashing via `werkzeug.security`

## Pull Request Guidelines

- Provide clear description of changes
- Reference any related issues
- Ensure all tests pass and linter is clean
- Update documentation if API or architecture changes

# ProjectCompass

**Analysis catalog, execution engine, and data exploration platform.**

![Overview](static/img/overview_page.png)

ProjectCompass is a Python-based tool for teams that produce data analyses. It solves three problems that emerge after the analytical work is done:

1. **Organization** — a tag-based catalog of all analyses with metadata, documentation, and version tracking
2. **Execution** — a unified environment to run structured analyses consistently, with scheduling
3. **Exploration** — SQL queries on local datasets via DuckDB, with visualization and LLM-powered chat

---

## Features

| Feature | Description |
|---------|-------------|
| 📂 **Catalog** | Tag-based analysis repository with search, filter, pagination, and full-text search (FTS5) |
| 🔍 **Data Explorer** | SQL queries on CSV/SQLite via DuckDB with data lineage tracking |
| 📊 **RAWGraphs Visualization** | Custom chart builder with 30+ chart types, drag-and-drop mapping, visual options, SVG/PNG export |
| 🔧 **Pipeline Builder** | Visual ML pipeline designer with DSL syntax (`>>`) and 4 pre-built templates |
| 🧠 **scomp-link Integration** | 6 ML blocks (Drift, Explainability, Fairness, Tuning, Validation, NLP) + 7 Report blocks |
| ⚙️ **Execution Engine** | Run structured analyses with real-time SSE streaming, progress bar, and abort capability |
| 📜 **Execution History** | Full history with status badges, filtering, and detailed logs |
| 🔄 **Pipeline Versioning** | Every save creates a version; restore to any previous state |
| ⏰ **Scheduler** | Schedule analyses with cron/interval triggers (APScheduler + SQLite persistence) |
| 🤖 **AI Chat** | Ask questions about your data in natural language (Mithril — multi-model: Gemini, OpenAI, Anthropic, Groq, local GGUF) |
| 🧠 **RAG per Analysis** | Per-project retrieval-augmented generation with code-aware chunking, hybrid search (dense + BM25), LLM reranking, guardrails, and source provenance |
| 🔗 **REST API** | JSON endpoints with Bearer token authentication for external integrations |
| 👥 **Multi-User RBAC** | Admin, editor, viewer roles with user management |
| 💬 **Comments** | Real-time HTMX comments on analyses for team collaboration |
| 🔔 **Webhooks** | HMAC-SHA256 signed payloads for external system integration |
| 📊 **Observability** | Admin metrics dashboard with Chart.js visualizations |
| 🌙 **Dark Mode** | Toggle with localStorage persistence |
| 📦 **Export/Import** | Package analyses as ZIP for sharing and backup |
| 🐳 **Docker** | One-command deployment with Mithril multi-model LLM backend |

---

## Quick Start with Docker

The fastest way to run ProjectCompass — no cloning or building required:

```bash
# Download the compose file
curl -O https://raw.githubusercontent.com/GiacomoSaccaggi/ProjectCompass/main/docker-compose.public.yml

# Start
docker compose -f docker-compose.public.yml up -d

# Open browser
open http://localhost:8080
```

To enable AI chat, configure Mithril API keys in a `.env` file next to the compose file:
```bash
echo "MITHRIL_KEY_GEMINI=your-gemini-key" >> .env
# Or use any supported provider: MITHRIL_KEY_OPENAI, MITHRIL_KEY_ANTHROPIC, MITHRIL_KEY_GROQ
```

To update to the latest version:
```bash
docker compose -f docker-compose.public.yml pull
docker compose -f docker-compose.public.yml up -d
```

---

## Local Development

```bash
git clone https://github.com/GiacomoSaccaggi/ProjectCompass.git
cd ProjectCompass
uv sync

cp .env.example .env
# Edit .env with your settings

uv run python app.py
```

The app is available at `http://127.0.0.1:5000`

### Running Tests

```bash
uv run pytest -v
```

276 tests with 83% coverage.

### Linting

```bash
uv run ruff check .
uv run ruff check --fix .  # auto-fix
```

---

## Docker (Development)

To build and run from source:

```bash
docker compose up -d
```

This uses `docker-compose.yml` which builds the image locally. Services: ProjectCompass on `:8080`, Mithril on `:16180`.

See [DOCKER.md](DOCKER.md) for volumes, environment variables, health checks, and production settings.

---

## Architecture

```
ProjectCompass/
├── app.py                  # Application factory (Flask + APScheduler)
├── config.py               # Configuration from environment
├── logging_config.py       # Unified structured logging
├── basefun.py              # Core ProjectCompass class
├── models.py               # SQLAlchemy models (User, Analysis, Execution, Comment, etc.)
├── blueprints/
│   ├── auth.py             # Authentication (RBAC, sessions, API tokens)
│   ├── catalog.py          # Analysis CRUD, search, filter, scheduling, versioning
│   ├── data.py             # Query runner, data upload, RAWGraphs, lineage
│   ├── agent.py            # LLM chat with sandboxed execution (Mithril backend)
│   ├── rag.py              # RAG index build, status, and management
│   └── api.py              # REST API (JSON endpoints, Bearer auth)
├── utils/
│   ├── analysis_utils.py   # Analysis metadata management
│   ├── data_utils.py       # DuckDB SQL, file operations
│   ├── html_utils.py       # Template utilities
│   ├── mithril_client.py   # Mithril LLM client (httpx, Ollama-compatible API)
│   ├── chunker.py          # Code-aware document chunking for RAG
│   ├── rag_store.py        # ChromaDB vector store wrapper
│   └── rag_guardrails.py   # RAG input/output validation and prompt builder
├── templates/
│   ├── *.html              # Jinja2 HTML templates with HTMX
│   ├── admin/              # User management, metrics dashboard
│   └── components/         # HTMX partials (toasts, activity feed, search)
├── static/
│   ├── css/
│   │   ├── style.css       # Main styles
│   │   └── dark.css        # Dark mode theme
│   ├── js/                 # JavaScript (command palette, SSE, toasts)
│   └── pipeline_templates/ # Pre-built ML pipeline templates (JSON)
├── tests/                  # pytest test suite (276 tests)
├── Analyses/               # Analysis storage (file-based)
├── Saved_data/             # Uploaded datasets
├── Saved_queries/          # Saved SQL queries
├── projectcompass.db       # SQLite database (users, executions, comments, audit log)
└── scheduler_jobs.db       # APScheduler job persistence (SQLite)
```

### Tech Stack

- **Backend**: Flask 3.0, Flask-SQLAlchemy, Gunicorn, Python 3.13
- **Database**: SQLite with FTS5 full-text search
- **Data**: DuckDB (in-memory SQL on CSV), pandas
- **Visualization**: RAWGraphs via CDN, Chart.js, Plotly (via scomp-link)
- **ML Pipelines**: scomp-link v2.2.0 (DSL syntax, Optuna tuning, SHAP/LIME explainability)
- **Scheduling**: APScheduler with SQLite persistence
- **AI**: Mithril (multi-model orchestration — Gemini, OpenAI, Anthropic, Groq, local GGUF)
- **RAG**: ChromaDB (vector store), code-aware chunking, hybrid search (dense + BM25), LLM reranking
- **Embeddings**: Local E5-small (sentence-transformers, 384 dims, zero cost) — optional Mithril cloud proxy
- **Frontend**: W3.CSS, HTMX 2.0, Chart.js, jQuery
- **Real-time**: Server-Sent Events (SSE) for execution streaming
- **Security**: RBAC, werkzeug password hashing, API Bearer tokens, HMAC webhooks, AST sandbox
- **CI/CD**: GitHub Actions (ruff + pytest on tags), Docker image auto-published to ghcr.io

---

## Configuration

All configuration is via environment variables (`.env` file):

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | random | Flask session encryption key |
| `DATABASE_URL` | `sqlite:///projectcompass.db` | SQLAlchemy database URI |
| `ADMIN_USERNAME` | `admin` | Default admin username |
| `ADMIN_PASSWORD_HASH` | *(empty)* | Werkzeug-hashed password |
| `PORT` | `5000` | Server port |
| `FLASK_DEBUG` | `False` | Debug mode |
| `USE_GITLAB_REPO` | `False` | GitLab integration |
| `MITHRIL_HOST` | `http://localhost:16180` | Mithril LLM endpoint |
| `MITHRIL_EMBED_MODEL` | `gemini-embedding-exp-03-07` | Embedding model for RAG |
| `MITHRIL_RERANK_MODEL` | `gemini-2.5-flash` | Reranking model for RAG |
| `RAG_EMBED_BACKEND` | `local` | Embedding backend: `local` (E5, zero cost) or `mithril` (cloud) |
| `ALLOWED_ORIGINS` | `*` | CORS allowed origins |

### Generate a password hash

```bash
uv run python -c "from werkzeug.security import generate_password_hash; print(generate_password_hash('your-password'))"
```

---

## REST API

All endpoints return JSON. Supports session-based auth (web UI) or Bearer token auth (API).

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health` | Health check |
| GET | `/api/analyses` | List analyses (supports `?q=`, `?product=`, `?owner=`, `?page=`, `?per_page=`) |
| GET | `/api/analyses/<name>` | Get single analysis details |
| GET | `/api/data` | List available datasets |
| GET | `/api/data/<name>/preview?limit=10` | Preview dataset rows |
| POST | `/api/query` | Execute SQL query (`{"sql": "SELECT ..."}`) |
| GET | `/api/search?q=<term>` | Full-text search across analyses |
| GET | `/api/activity` | Recent activity feed (audit log) |
| GET | `/api/metrics` | System metrics (admin only) |
| GET | `/api/tokens` | List API tokens for current user |
| POST | `/api/tokens` | Create new API token |
| DELETE | `/api/tokens/<id>` | Revoke API token |
| GET | `/health` | Application health check |
| POST | `/rag/build/<name>` | Build RAG index for an analysis |
| GET | `/rag/status/<name>` | Get RAG index status |
| DELETE | `/rag/index/<name>` | Delete RAG index |
| POST | `/chat/analysis/rag` | RAG-enhanced analysis chat |
| POST | `/chat/analysis/rag/stream` | Streaming RAG chat (SSE) |

### Example

```bash
# List all analyses (session auth)
curl http://localhost:8080/api/analyses

# Search analyses
curl http://localhost:8080/api/analyses?q=marketing&product=Research

# Query data with Bearer token
curl -X POST http://localhost:8080/api/query \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_TOKEN" \
  -d '{"sql": "SELECT * FROM wine_quality LIMIT 5"}'
```

---

## Web Routes

| Route | Description |
|-------|-------------|
| `/` | Dashboard with statistics and activity feed |
| `/overview` | Project documentation page |
| `/analysis` | Analysis catalog with search/filter |
| `/load_analysis/` | Create or edit an analysis |
| `/create_investigations` | Run structured analysis with dynamic form |
| `/outputs/` | View analysis outputs (per run, with delete) |
| `/executions` | Execution history with status badges and filtering |
| `/schedules/` | View and manage scheduled analyses |
| `/pipeline_builder` | Visual ML pipeline designer |
| `/query_runner/` | SQL query editor |
| `/all_data/` | Browse uploaded datasets with lineage badges |
| `/upload_data/` | Upload new data files |
| `/rawgraphs` | RAWGraphs visualization (30+ chart types) |
| `/graph_analysis/` | Open query results in RAWGraphs |
| `/chat` | AI data assistant |
| `/settings` | User settings and preferences |
| `/import` | Import analysis from ZIP pack |
| `/admin/users` | User management (admin only) |
| `/admin/metrics` | Observability dashboard (admin only) |
| `/todo` | Notes/todo page |

---

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl+K` / `Cmd+K` | Open Command Palette |
| `Escape` | Close Command Palette / modals |
| `↑` / `↓` | Navigate Command Palette results |
| `Enter` | Select Command Palette item |

The Command Palette provides quick access to all pages, recent analyses, and common actions.

---

## Structured Analyses & Scheduling

Create analyses that can be run on-demand or scheduled:

```
Analyses/My Analysis/
├── metadata.yaml                          # Catalog metadata
├── readme.md                              # Description
├── output_versions.yaml                   # Version tracking
└── analysis/
    ├── metadata_automatic_report.yaml     # Form definition (inputs)
    └── structured_analysis_main.py        # Execution script (run function)
```

Schedule options: `Every day at HH:MM`, `Every hour`, `Every Monday`, `Every Friday`, `Custom cron expression`.

Jobs persist across restarts via SQLite.

---

## Pipeline Builder & scomp-link

Build ML pipelines visually or with DSL syntax:

```python
# DSL syntax example
CleanStep >> SelectStep >> ModelStep >> TrainStep
```

### ML Blocks
- **Drift Detection**: Monitor distribution shifts between training and production data
- **Explainability**: SHAP and LIME for model interpretation
- **Fairness**: Bias detection across protected attributes
- **Tuning**: Optuna and Halving search for hyperparameter optimization
- **Validation**: K-Fold and Bootstrap cross-validation
- **Text/NLP**: Text preprocessing and embedding pipelines

### Report Blocks
- **Quick Report**: Expanded EDA with automatic insights
- **KPI Cards**: Dashboard-style metric displays
- **Plotly Grid**: Multi-chart layouts
- **Tabs**: Tabbed report sections
- **Comparison Table**: Side-by-side model comparison
- **Summary Stats**: Automatic statistical summaries
- **Dark Mode**: Report theme toggle

### Pipeline Templates
1. **Classification + Explainability**: Train classifier with SHAP explanations
2. **Anomaly Detection**: Isolation Forest with drift monitoring
3. **Forecasting**: Time series with validation
4. **Full ML**: Complete pipeline with tuning, validation, and fairness checks

---

## RAG per Analysis

Each analysis project can have its own RAG (Retrieval-Augmented Generation) index. When a user asks a question in the analysis chat, the LLM answers using relevant context retrieved from the project's files, with source citations.

### How it works

1. **Build**: Click 🧠 **Build RAG** on any analysis page. All project files (metadata, readme, Python code, SQL, comments) are chunked and embedded.
2. **Chat**: In the analysis chat, the system automatically uses RAG when an index exists, falling back to metadata-only if not.
3. **Auto-rebuild**: Saving an analysis or adding a comment triggers a background RAG rebuild.

### Architecture

```
User asks question
  → Guardrails validate query (injection detection, length limits)
  → Hybrid search: dense vectors (ChromaDB) + keyword matching (BM25)
  → LLM reranks top results by relevance (via Mithril /api/rerank)
  → Build prompt with top-5 chunks + provenance instructions
  → LLM generates answer citing [Source N] references
  → Guardrails sanitize response (strip absolute paths, truncate)
  → Return answer + source citations
```

### Code-aware chunking

| File type | Strategy |
|-----------|----------|
| `.py` | Split by function/class using AST — each function is a chunk with docstring metadata |
| `.yaml` | Split by top-level keys |
| `.md` | Split by markdown headers |
| `.sql` | Split by SQL statements (`;` delimiter) |
| Other | Paragraph-based with ~500 token target and 50 token overlap |

### Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/rag/build/<name>` | Build/rebuild RAG index for an analysis |
| GET | `/rag/status/<name>` | Check if RAG index exists and chunk count |
| DELETE | `/rag/index/<name>` | Delete RAG index |
| POST | `/chat/analysis/rag` | Chat with RAG context (returns answer + sources) |
| POST | `/chat/analysis/rag/stream` | Streaming RAG chat via SSE |

### Guardrails

- **Input validation**: Blocks prompt injection attempts ("ignore previous instructions"), excessive length (>2000 chars), and special character abuse
- **Output sanitization**: Strips absolute file paths from responses, truncates at 5000 chars
- **Topic scoping**: Prompt instructs LLM to answer only from provided context and cite sources
- **Graceful fallback**: If Mithril is unavailable or RAG index doesn't exist, falls back to metadata-only chat

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development workflow, code style, and testing guidelines.

---

## Security

- **Authentication**: Session-based (web) or Bearer token (API) with werkzeug-hashed passwords
- **Role-Based Access Control (RBAC)**: Admin, editor, and viewer roles with granular permissions
- **API Tokens**: Generate tokens for external integrations, revocable at any time
- **Webhooks**: HMAC-SHA256 signed payloads for secure external notifications
- **Code Execution**: AST-validated sandbox blocks `import`, `open()`, `exec()`, `eval()`
- **CORS**: Restricted to configured origins for API routes
- **Secrets**: Environment variables, never in code or YAML
- **Input Sanitization**: HTML cleaning on query editor input
- **Audit Log**: All user actions logged for compliance and debugging

---

## License

Copyright ©2024 ProjectCompass. All rights reserved.

---

**ProjectCompass** — *Organization Is Everything®*

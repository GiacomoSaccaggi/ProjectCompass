# Utils

Business logic modules for ProjectCompass. These are consumed by the blueprints.

| Module | Purpose |
|--------|---------|
| `analysis_utils.py` | Analysis CRUD: read/write metadata YAML, upload files, extract requirements/queries, manage versions |
| `data_utils.py` | DuckDB SQL execution on CSV/SQLite files, file upload, data listing |
| `html_utils.py` | Template header parsing, constants loading, HTML substitution |
| `agent_utils.py` | LLM agent (lazy-loaded Ollama), AST-validated safe pandas execution |

## Class Hierarchy

```
HTMLUtils
    ↑
DataUtils
    ↑
AnalysisUtils
    ↑
ProjectCompass (basefun.py)
```

All utils use cooperative inheritance via `super().__init__()`.

## Key Functions

### `DataUtils.sql(query)` → DataFrame
Executes SQL against CSV files in `Saved_data/`. DuckDB reads files directly from disk.

### `DataUtils.list_data()` → list[str]
Returns available dataset names (CSV/SQLite files without extension).

### `AnalysisUtils.read_multiple_analysis()` → dict
Reads all analysis folders, parsing `metadata.yaml` and `output_versions.yaml`.

### `agent_utils.safe_pandas_query(expression, df)` → str
AST-validates and executes a pandas expression in a restricted namespace. Blocks `import`, `open`, `exec`, `eval`.

# Templates

Jinja2 HTML templates for ProjectCompass.

## Layout

All pages use `header.html` for shared components (parsed via `HTMLUtils`):
- `head` — CSS links, meta tags
- `top_container` — navigation bar
- `sidebar_menu` — left sidebar with navigation links

## Page Templates

| Template | Route | Description |
|----------|-------|-------------|
| `index.html` | `/` | Dashboard with stats and charts |
| `analysis.html` | `/analysis` | Analysis catalog with accordion cards |
| `create_analysis.html` | `/load_analysis/` | New/edit analysis form |
| `query_results.html` | `/query_runner/` | SQL editor + results table |
| `data_upload.html` | `/upload_data/` | File upload form |
| `data_list.html` | `/all_data/` | Browse uploaded datasets |
| `RAWGraphs.html` | `/rawgraphs` | Data visualization |
| `chat.html` | `/chat` | AI data assistant |
| `todopage.html` | `/todo` | Notes page |
| `iframetemplate.html` | various | Embedded content viewer |
| `versions_single_analysis.html` | `/open_version/` | Version management |
| `investigations.html` | `/create_investigations/` | Structured analysis input form |
| `process_complete.html` | POST results | Success confirmation |
| `internal_error.html` | errors | Error page |
| `login_page.html` | `/login/` | Authentication form |
| `loader.html` | `/loading/` | Loading spinner |

## Configuration Files

Located in `environment_variables/`:

| File | Purpose |
|------|---------|
| `constants.yaml` | App settings (port, logo SVG) |
| `tool_choices.yaml` | Product/country/input-type options for forms |
| `links.yaml` | External links shown on dashboard |
| `intro.txt` | Dashboard intro text |
| `title.txt` | App title |

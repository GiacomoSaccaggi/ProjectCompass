import datetime
import io
import json
import os
import signal
import subprocess
import zipfile

import numpy as np
from flask import (
    Blueprint,
    Response,
    current_app,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    session,
    stream_with_context,
    url_for,
)

from logging_config import logger
from models import Execution, PipelineVersion, User, db, log_action

catalog_bp = Blueprint('catalog', __name__)

# Track running processes for SSE execution
_running_processes = {}  # name -> Popen


def get_webapp():
    return current_app.config['WEBAPP']


def _save_execution(analysis_name, user_id, status, log_text='', inputs=None, outputs=None, output_path=''):
    """Save an execution record to the database."""
    now = datetime.datetime.now(datetime.timezone.utc)
    exe = Execution(
        analysis_name=analysis_name,
        user_id=user_id,
        started_at=now,
        finished_at=now if status != 'running' else None,
        status=status,
        output_path=output_path,
        log_text=log_text,
        inputs_json=json.dumps(inputs or {}),
        outputs_json=json.dumps(outputs or []),
    )
    db.session.add(exe)
    db.session.commit()
    return exe


def _extract_lineage_from_script(script_text):
    """Extract dataset names referenced in pd.read_csv calls."""
    import re
    inputs = re.findall(r'read_csv\(.*?["\']([^"\'/]+)\.csv["\']', script_text)
    return list(set(inputs))


@catalog_bp.route('/')
def index():
    webapp = get_webapp()
    html_part = webapp.substitute_html(port=webapp.constants["port"], project_folder=webapp.project_folder)
    img = '<img src="/static/img/first_page.png" style="width:100%;"><br>'
    intro = webapp.environments_info['intro']
    analyses = webapp.read_multiple_analysis()

    product_info = {}
    number_of_analysis = 0
    number_of_structured_analysis = 0
    n_last_uploaded = 0
    owners = []
    for info in analyses.values():
        number_of_analysis += 1
        owners.append(info['owner'])
        last_mod = datetime.datetime.now() - datetime.datetime.fromtimestamp(os.path.getmtime(info['folder']))
        if last_mod > datetime.timedelta(days=30):
            n_last_uploaded += 1
        if info['structured_analysis'] != 'n':
            number_of_structured_analysis += 1
        product_info[info['product']] = product_info.get(info['product'], 0) + 1

    number_of_owners = len(set(owners))
    products = list(product_info.keys())
    number_of_products = len(products)
    product_labels = ','.join([f'"{i}"' for i in products])
    product_res = []
    product_color = []
    for p in products:
        product_res.append(product_info[p])
        c1, c2, c3 = np.random.choice([-192, -128, -99, 0, 99, 132, 128, 192, 255], size=3)
        product_color.append([f"'rgba({c1}, {c2}, {c3}, 0.2)'", f"'rgba({c1}, {c2}, {c3}, 1)'"])
    product_res = ','.join([str(i) for i in product_res])

    return render_template('index.html',
                           title=webapp.environments_info['title'],
                           intro_title=img,
                           number_of_analysis=number_of_analysis,
                           number_of_structured_analysis=number_of_structured_analysis,
                           number_of_products=number_of_products,
                           number_of_owners=number_of_owners,
                           n_last_uploaded=n_last_uploaded,
                           product_labels=product_labels,
                           product_res=product_res,
                           product_color1=','.join([i[0] for i in product_color]),
                           product_color2=','.join([i[1] for i in product_color]),
                           intro=intro,
                           links=webapp.environments_info['links'],
                           head=html_part['head'],
                           top_container=html_part['top_container'],
                           port=webapp.constants["port"],
                           project_folder=webapp.project_folder,
                           sidebar_menu=html_part['sidebar_menu'])


@catalog_bp.route('/analysis')
def analysis_page():
    webapp = get_webapp()
    html_part = webapp.substitute_html(port=webapp.constants["port"], project_folder=webapp.project_folder)
    analyses = webapp.read_multiple_analysis()

    # Search and filter
    q = request.args.get('q', '').lower()
    product_filter = request.args.get('product', '')
    owner_filter = request.args.get('owner', '')
    country_filter = request.args.get('country', '')

    if q or product_filter or owner_filter or country_filter:
        filtered = {}
        for k, v in analyses.items():
            if q and q not in v.get('title', '').lower() and q not in v.get('description', '').lower():
                continue
            if product_filter and v.get('product', '') != product_filter:
                continue
            if owner_filter and v.get('owner', '') != owner_filter:
                continue
            if country_filter and country_filter not in v.get('countries', ''):
                continue
            filtered[k] = v
        analyses = filtered

    # Pagination
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 20))
    keys = list(analyses.keys())
    total = len(keys)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = max(1, min(page, total_pages))
    start = (page - 1) * per_page
    paginated_keys = keys[start:start + per_page]
    analyses = {k: analyses[k] for k in paginated_keys}

    # Collect unique values for filter dropdowns
    all_analyses = webapp.read_multiple_analysis()
    all_products = sorted(set(v.get('product', '') for v in all_analyses.values() if v.get('product')))
    all_owners = sorted(set(v.get('owner', '') for v in all_analyses.values() if v.get('owner')))

    return render_template('analysis.html',
                           port=webapp.constants["port"], title='Analyses', analysis=analyses,
                           head=html_part['head'], top_container=html_part['top_container'],
                           project_folder=webapp.project_folder,
                           sidebar_menu=html_part['sidebar_menu'], tool_choices=webapp.tool_choices,
                           page=page, total_pages=total_pages, total=total,
                           q=request.args.get('q', ''), product_filter=product_filter,
                           owner_filter=owner_filter, country_filter=country_filter,
                           all_products=all_products, all_owners=all_owners)


@catalog_bp.route('/load_analysis/', methods=['GET'])
def load_analysis():
    webapp = get_webapp()
    name = request.args.get('name', '')
    html_part = webapp.substitute_html(port=webapp.constants["port"], project_folder=webapp.project_folder)
    if name:
        analysis = webapp.read_single_analysis(webapp.extract_main_folder(), name.replace('512', ' '))
        new_analysis = False
    else:
        analysis = {'links': {}, 'inputs': {}, 'slides': {}}
        new_analysis = True
    return render_template('create_analysis.html', new_analysis=new_analysis, analysis=analysis,
                           port=webapp.constants["port"], project_folder=webapp.project_folder,
                           tool_choices=webapp.tool_choices,
                           head=html_part['head'], top_container=html_part['top_container'],
                           sidebar_menu=html_part['sidebar_menu'])


@catalog_bp.route('/produce_analysis/', methods=['POST'])
def produce_analysis():
    webapp = get_webapp()
    new_analysis = request.form['new_analysis']
    if new_analysis == 'new':
        error = webapp.upload_new_analysis(request)
    else:
        error = webapp.modify_analysis(request)
    if error == '':
        logger.info(f"Analysis saved: {request.form.get('title', 'unknown')}")
        return render_template('process_complete.html')
    else:
        logger.error(f"Analysis save failed: {error}")
        return render_template('internal_error.html')


@catalog_bp.route('/delete_analysis/', methods=['GET'])
def delete_analysis():
    import shutil
    webapp = get_webapp()
    name = request.args['name'].replace('512', ' ')
    path = f"{webapp.extract_main_folder()}/{name}"
    if os.path.isdir(path):
        shutil.rmtree(path, ignore_errors=True)
        logger.info(f"Deleted analysis: {name}")
    return redirect(url_for('catalog.analysis_page'))


@catalog_bp.route('/open_analysis/', methods=['GET'])
def open_analysis():
    webapp = get_webapp()
    name = request.args['name'].replace('512', ' ')
    source = f'{webapp.extract_main_folder()}/{name}'
    filename = name + f'export_{datetime.datetime.now():%Y-%m-%d}'
    tmp_dir = os.path.join(webapp.template_folder, 'tmp')
    os.makedirs(tmp_dir, exist_ok=True)
    webapp.make_archive(source, f'{tmp_dir}/{filename}.zip')
    return send_file(f'{tmp_dir}/{filename}.zip')


@catalog_bp.route('/export/<name>')
def export_analysis(name):
    """Export analysis as a ZIP file."""
    webapp = get_webapp()
    name = name.replace('512', ' ')
    analysis_dir = f"{webapp.extract_main_folder()}/{name}"
    if not os.path.isdir(analysis_dir):
        return 'Not found', 404
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root, _dirs, files in os.walk(analysis_dir):
            for file in files:
                filepath = os.path.join(root, file)
                arcname = os.path.relpath(filepath, os.path.dirname(analysis_dir))
                zf.write(filepath, arcname)
    buf.seek(0)
    return Response(buf.read(), mimetype='application/zip',
                    headers={'Content-Disposition': f'attachment; filename={name}.zip'})


@catalog_bp.route('/import', methods=['GET', 'POST'])
def import_analysis():
    """Import an analysis from a ZIP file."""
    webapp = get_webapp()
    if request.method == 'GET':
        html_part = webapp.substitute_html(port=webapp.constants['port'],
                                           project_folder=webapp.project_folder)
        return render_template('import.html', head=html_part['head'],
                               top_container=html_part['top_container'],
                               sidebar_menu=html_part['sidebar_menu'])
    # POST: handle ZIP upload
    f = request.files.get('file')
    if not f or not f.filename.endswith('.zip'):
        return jsonify(success=False, error='ZIP file required')
    buf = io.BytesIO(f.read())
    with zipfile.ZipFile(buf, 'r') as zf:
        zf.extractall(webapp.extract_main_folder())
    return redirect('/analysis')


@catalog_bp.route('/load_analysis_internal/', methods=['GET'])
def load_analysis_internal():
    webapp = get_webapp()
    if 'name' not in request.args:
        new_analysis = True
        analysis = {'links': {}, 'inputs': {}, 'slides': {}}
    else:
        new_analysis = False
        name = request.args['name'].replace('512', ' ')
        analysis = webapp.read_single_analysis(webapp.extract_main_folder(), name)
    return render_template('create_analysis.html', new_analysis=new_analysis, analysis=analysis,
                           port=webapp.constants["port"], project_folder=webapp.project_folder,
                           tool_choices=webapp.tool_choices)


@catalog_bp.route('/overview')
def overview_page():
    webapp = get_webapp()
    html_part = webapp.substitute_html(port=webapp.constants["port"], project_folder=webapp.project_folder)
    return render_template('overview.html',
                           title=webapp.environments_info['title'],
                           head=html_part['head'],
                           top_container=html_part['top_container'], port=webapp.constants["port"],
                           project_folder=webapp.project_folder,
                           sidebar_menu=html_part['sidebar_menu'])


@catalog_bp.route('/iframe/', methods=['GET'])
def iframe_page():
    webapp = get_webapp()
    name = request.args['name'].replace('512', ' ')
    analysis = webapp.read_single_analysis(webapp.extract_main_folder(), name)
    html_part = webapp.substitute_html(port=webapp.constants["port"], project_folder=webapp.project_folder)
    if 'version' not in request.args:
        if '<script' in analysis['dashboard link']:
            obj, url = analysis['dashboard link'], ''
        else:
            obj, url = '', analysis['dashboard link']
    else:
        version = request.args['version'].replace('512', ' ')
        if '<script' in analysis['versions_dashboard'][version]:
            obj, url = analysis['versions_dashboard'][version], ''
        else:
            obj, url = '', analysis['versions_dashboard'][version]
    title = f'<a href="{url}">{name}</a>' if obj == '' else name
    return render_template('iframetemplate.html', obj=obj, title=title, url=url, head=html_part['head'],
                           top_container=html_part['top_container'], project_folder=webapp.project_folder,
                           port=webapp.constants["port"], sidebar_menu=html_part['sidebar_menu'])


@catalog_bp.route('/outputs/', methods=['GET'])
def outputs_page():
    from collections import defaultdict
    webapp = get_webapp()
    name = request.args['name'].replace('512', ' ')
    html_part = webapp.substitute_html(port=webapp.constants["port"], project_folder=webapp.project_folder)
    output_base = f"{webapp.extract_main_folder()}/{name}/physical_output"
    runs = defaultdict(list)
    if os.path.exists(output_base):
        for f in os.listdir(output_base):
            if f == 'main' or f.startswith('.') or '.ini' in f:
                continue
            run_id = os.path.splitext(f)[0]
            fpath = f"Analyses/{name}/physical_output/{f}"
            runs[run_id].append({'name': f, 'path': fpath, 'is_html': f.endswith('.html')})
    # Sort runs by date descending
    sorted_runs = sorted(runs.items(), key=lambda x: x[0], reverse=True)
    return render_template('outputs.html',
                           title=f'Outputs: {name}',
                           analysis_name=name,
                           runs=sorted_runs,
                           head=html_part['head'],
                           top_container=html_part['top_container'],
                           sidebar_menu=html_part['sidebar_menu'],
                           port=webapp.constants["port"],
                           project_folder=webapp.project_folder)


@catalog_bp.route('/delete_run/', methods=['GET'])
def delete_run():
    webapp = get_webapp()
    name = request.args['name'].replace('512', ' ')
    run_id = request.args['run_id']
    output_base = f"{webapp.extract_main_folder()}/{name}/physical_output"
    for f in os.listdir(output_base):
        if os.path.splitext(f)[0] == run_id and f != 'main':
            os.remove(os.path.join(output_base, f))
    return redirect(f"/outputs/?name={request.args['name']}")


@catalog_bp.route('/physical_output/', methods=['GET'])
def physical_output():
    name = request.args.get('name', '')
    return redirect(f"/outputs/?name={name}")


@catalog_bp.route('/serve_output/<path:filepath>')
def serve_output(filepath):
    webapp = get_webapp()
    return send_file(os.path.join(webapp.dir_path, filepath))


@catalog_bp.route('/open_version/', methods=['GET'])
def version_page():
    webapp = get_webapp()
    name = request.args['name'].replace('512', ' ')
    analysis = webapp.read_single_analysis(webapp.extract_main_folder(), name)
    html_part = webapp.substitute_html(port=webapp.constants["port"], project_folder=webapp.project_folder)
    return render_template('versions_single_analysis.html', values=analysis, nome=name, head=html_part['head'],
                           top_container=html_part['top_container'], project_folder=webapp.project_folder,
                           port=webapp.constants["port"], sidebar_menu=html_part['sidebar_menu'])


@catalog_bp.route('/todo')
def todo():
    webapp = get_webapp()
    html_part = webapp.substitute_html(port=webapp.constants["port"], project_folder=webapp.project_folder)
    return render_template('todopage.html', head=html_part['head'], project_folder=webapp.project_folder,
                           top_container=html_part['top_container'],
                           port=webapp.constants["port"], sidebar_menu=html_part['sidebar_menu'])


@catalog_bp.route('/check', methods=['GET'])
def check():
    return jsonify(success=True)


@catalog_bp.route('/create_investigations', methods=['GET'])
def create_investigations():
    import yaml
    webapp = get_webapp()
    html_part = webapp.substitute_html(port=webapp.constants["port"], project_folder=webapp.project_folder)
    name = request.args.get('name', '').replace('512', ' ')
    metadata_path = f"{webapp.extract_main_folder()}/{name}/analysis/metadata_automatic_report.yaml"
    with open(metadata_path) as f:
        metadata = yaml.safe_load(f)

    # Build form inputs from metadata
    input_form = [f'<input type="hidden" name="analysis_name" value="{name}">']
    for field_name, field_info in metadata.get('inputs', {}).items():
        field_type = field_info.get('type', 'text')
        default = field_info.get('default', '')
        desc = field_info.get('description', field_name)
        style = 'padding:6px 12px;margin:4px;border:2px solid #00889B;border-radius:4px;width:90%'
        if field_type == 'select':
            options_html = ''.join(
                f'<option value="{opt}"{" selected" if str(opt) == str(default) else ""}>{opt}</option>'
                for opt in field_info.get('options', [])
            )
            input_form.append(
                f'<label><b>{desc}</b></label><br>'
                f'<select name="{field_name}" style="{style}"><br>{options_html}</select><br><br>'
            )
        else:
            html_type = 'date' if field_type == 'date' else 'text'
            input_form.append(
                f'<label><b>{desc}</b></label><br>'
                f'<input type="{html_type}" name="{field_name}" value="{default}" '
                f'style="{style}"><br><br>'
            )

    return render_template('investigations.html',
                           title=metadata.get('title', name),
                           input_form=input_form,
                           head=html_part['head'],
                           top_container=html_part['top_container'],
                           sidebar_menu=html_part['sidebar_menu'],
                           port=webapp.constants["port"],
                           project_folder=webapp.project_folder)


@catalog_bp.route('/run_investigation/', methods=['POST'])
def run_investigation():
    import importlib.util
    webapp = get_webapp()
    name = request.form.get('analysis_name', '')
    inputs = {k: v for k, v in request.form.items() if k not in ('analysis_name', 'run_investigation')}

    # Run the structured analysis
    script_path = f"{webapp.extract_main_folder()}/{name}/analysis/structured_analysis_main.py"
    output_dir = f"{webapp.extract_main_folder()}/{name}/physical_output/main"
    os.makedirs(output_dir, exist_ok=True)
    output_path = f"{output_dir}/output.csv"

    try:
        spec = importlib.util.spec_from_file_location("analysis_module", script_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.run(inputs=inputs, output_path=output_path)

        # Save timestamped version of outputs
        import datetime
        import shutil
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        version_dir = f"{webapp.extract_main_folder()}/{name}/physical_output"
        for f_name in os.listdir(output_dir):
            if f_name.startswith('.') or '.ini' in f_name:
                continue
            ext = os.path.splitext(f_name)[1]
            shutil.copy(f"{output_dir}/{f_name}", f"{version_dir}/{timestamp}{ext}")

        logger.info(f"Structured analysis '{name}' completed successfully")
        log_action('run', 'analysis', name)
        return redirect(f"/outputs/?name={name.replace(' ', '512')}")
    except Exception as e:
        logger.error(f"Structured analysis error: {e}")
        return f"<h3>Analysis Error</h3><pre>{e}</pre><br><a href='/analysis'>Back to catalog</a>", 500


@catalog_bp.route('/execute_stream/<name>')
def execute_stream(name):
    """SSE endpoint for real-time execution output."""
    webapp = get_webapp()
    script_path = f"{webapp.extract_main_folder()}/{name}/analysis/structured_analysis_main.py"
    output_dir = f"{webapp.extract_main_folder()}/{name}/physical_output/main"
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, 'output.csv')

    def generate():
        try:
            # Run as module with simple runner
            cmd = [
                'uv', 'run', 'python', '-u', '-c',
                (
                    f'import sys; sys.path.insert(0, "{os.path.dirname(script_path)}"); '
                    f'from structured_analysis_main import run; '
                    f'result = run({{}}, "{output_path}"); '
                    f'print("DONE:", result.get("status", "success") if result else "success")'
                )
            ]
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1
            )
            _running_processes[name] = proc
            for line in iter(proc.stdout.readline, ''):
                yield f'data: {json.dumps({"line": line.rstrip(), "status": "running"})}\n\n'
            proc.wait()
            status = 'success' if proc.returncode == 0 else 'failed'
            yield f'data: {json.dumps({"line": "", "status": status, "done": True})}\n\n'
        except Exception as e:
            yield f'data: {json.dumps({"line": str(e), "status": "failed", "done": True})}\n\n'
        finally:
            _running_processes.pop(name, None)

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'}
    )


@catalog_bp.route('/execute_abort/<name>', methods=['POST'])
def execute_abort(name):
    """Abort a running SSE execution."""
    proc = _running_processes.get(name)
    if proc:
        proc.send_signal(signal.SIGTERM)
        _running_processes.pop(name, None)
        return jsonify(success=True)
    return jsonify(success=False, error='No running process')


# --- PIPELINE BUILDER ---

@catalog_bp.route('/pipeline_builder')
def pipeline_builder():
    webapp = get_webapp()
    html_part = webapp.substitute_html(port=webapp.constants["port"], project_folder=webapp.project_folder)
    datasets = [f.replace('.csv', '') for f in os.listdir(webapp.save_data_path)
                if f.endswith('.csv') and not f.startswith('.')]
    return render_template('pipeline_builder.html',
                           head=html_part['head'],
                           top_container=html_part['top_container'],
                           sidebar_menu=html_part['sidebar_menu'],
                           port=webapp.constants["port"],
                           project_folder=webapp.project_folder,
                           datasets=sorted(datasets),
                           owner='')


@catalog_bp.route('/save_pipeline/', methods=['POST'])
def save_pipeline():
    from flask import jsonify
    webapp = get_webapp()
    data = request.get_json()
    name = data.get('name', '').strip()
    if not name:
        return jsonify(success=False, error='Name is required')

    graph = data.get('graph', {})
    description = data.get('description', '')
    product = data.get('product', 'Machine Learning')
    owner = data.get('owner', '')

    # Create analysis folder structure
    analysis_dir = f"{webapp.extract_main_folder()}/{name}"
    analysis_code_dir = f"{analysis_dir}/analysis"
    os.makedirs(analysis_code_dir, exist_ok=True)
    os.makedirs(f"{analysis_dir}/physical_output/main", exist_ok=True)

    # Parse graph to ordered steps
    nodes = graph.get('drawflow', {}).get('Home', {}).get('data', {})
    steps = _build_steps(nodes)

    # Generate structured_analysis_main.py
    script = _generate_pipeline_script(steps, webapp.save_data_path)
    with open(f"{analysis_code_dir}/structured_analysis_main.py", 'w') as f:
        f.write(script)

    # Generate metadata_automatic_report.yaml
    meta_inputs = _extract_inputs_from_steps(steps)
    import yaml
    meta = {'title': name, 'description': description, 'inputs': meta_inputs,
            'output': {'type': 'csv', 'description': 'Pipeline output'}}
    with open(f"{analysis_code_dir}/metadata_automatic_report.yaml", 'w') as f:
        yaml.dump(meta, f, default_flow_style=False)

    # Generate metadata.yaml for catalog
    catalog_meta = {
        'title': name, 'description': description, 'product': product,
        'owner': owner, 'collaborators': '', 'countries': 'Global',
        'start_date': __import__('datetime').date.today().isoformat(),
        'output_type': 'CSV + HTML Report',
        'output description': 'Auto-generated by Pipeline Builder',
        'dashboard link': '', 'gitlab': '', 'gdrive': '',
        'inputs': {}, 'links': {}
    }
    with open(f"{analysis_dir}/metadata.yaml", 'w') as f:
        yaml.dump(catalog_meta, f, default_flow_style=False)

    # Generate readme
    with open(f"{analysis_dir}/readme.md", 'w') as f:
        f.write(f"# {name}\n### Product: {product}\n## Description\n> {description}\n")

    # output_versions.yaml
    with open(f"{analysis_dir}/output_versions.yaml", 'w') as f:
        f.write("---\n")

    # Index in FTS for search
    try:
        from models import index_analysis_fts
        index_analysis_fts(
            name=name,
            title=name,
            description=description,
            readme_text=f"# {name}\n### Product: {product}\n## Description\n> {description}\n",
            script_text=script
        )
    except Exception:
        pass  # FTS indexing failure should not block save

    # Save pipeline version for history
    max_version = db.session.query(db.func.max(PipelineVersion.version_num)).filter_by(
        analysis_name=name
    ).scalar() or 0
    version = PipelineVersion(
        analysis_name=name,
        version_num=max_version + 1,
        graph_json=json.dumps(graph),
        script_text=script,
        user_id=session.get('user_id'),
        message='Pipeline saved'
    )
    db.session.add(version)
    db.session.commit()

    logger.info(f"Pipeline '{name}' saved as structured analysis (v{max_version + 1})")
    log_action('save', 'pipeline', name)
    return jsonify(success=True, name=name)


def _build_steps(nodes):
    """Order nodes by connections (topological sort)."""
    if not nodes:
        return []
    # Build adjacency: node_id -> list of connected output node_ids
    edges = {}  # from_id -> to_id
    for nid, node in nodes.items():
        for _out_key, conns in node.get('outputs', {}).items():
            for conn in conns.get('connections', []):
                edges[str(nid)] = conn['node']

    # Find start nodes (no incoming)
    has_incoming = set(edges.values())
    start_nodes = [nid for nid in nodes if nid not in has_incoming]

    # BFS ordering
    ordered = []
    visited = set()
    queue = start_nodes[:]
    while queue:
        nid = queue.pop(0)
        if nid in visited:
            continue
        visited.add(nid)
        node = nodes[nid]
        ordered.append({'id': nid, 'type': node['class'], 'config': node.get('data', {}).get('config', {})})
        if nid in edges:
            queue.append(str(edges[nid]))

    # Add any unvisited nodes
    for nid in nodes:
        if nid not in visited:
            node = nodes[nid]
            ordered.append({'id': nid, 'type': node['class'], 'config': node.get('data', {}).get('config', {})})

    return ordered


def _generate_pipeline_script(steps, data_path):
    """Generate a structured_analysis_main.py from pipeline steps using scomp-link DSL."""
    lines = [
        '"""Auto-generated pipeline by ProjectCompass Pipeline Builder."""',
        'import os',
        'import pandas as pd',
        'from scomp_link import (CleanStep, SelectStep, ModelStep, TrainStep,',
        '                        ScompArtifact, SectionStep, TitleStep, TableStep, SaveStep)',
        '',
        '',
        'def run(inputs, output_path):',
        '    data_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "Saved_data")',
        '    out_dir = os.path.dirname(output_path)',
        '    os.makedirs(out_dir, exist_ok=True)',
        '    df = None',
        '    results = {}',
        '',
    ]

    # Track whether we have report blocks to save at the end
    has_report_blocks = any(s['type'].startswith('report_') for s in steps)

    for i, step in enumerate(steps):
        cfg = step.get('config', {})
        t = step['type']
        lines.append(f'    # Step {i+1}: {t}')

        if t == 'load_data':
            ds = cfg.get('dataset', 'wine_quality')
            limit = cfg.get('limit', '0')
            lines.append(f'    df = pd.read_csv(os.path.join(data_dir, "{ds}.csv"))')
            if limit and limit != '0':
                lines.append(f'    df = df.head({limit})')

        elif t == 'feature_eng':
            lines.append('    from scomp_link import FeatureEngineer')
            opts = []
            for k in ['interactions', 'log_transform', 'date_features', 'target_encode']:
                opts.append(f'{k}={cfg.get(k, False)}')
            lines.append('    _target = inputs.get("target_col", df.columns[-1])')
            lines.append(f'    _fe = FeatureEngineer({", ".join(opts)})')
            lines.append('    _X = _fe.fit_transform(df.drop(columns=[_target]), df[_target])')
            lines.append('    _X[_target] = df[_target].values')
            lines.append('    df = _X')

        elif t == 'quality':
            lines.append('    from scomp_link import DataQualityReport')
            lines.append('    _dqr = DataQualityReport(df)')
            lines.append('    _dqr.generate()')
            lines.append('    _dqr.save_html(os.path.join(out_dir, "data_quality.html"))')

        elif t == 'train_model':
            task = cfg.get('task_type', 'regression')
            target = cfg.get('target_col', '')
            hint = cfg.get('model_hint', 'auto')
            test_size = cfg.get('test_size', '0.2')
            ensemble = cfg.get('ensemble', 'none')
            lines.append(f'    _target = inputs.get("target_col", "{target}") or df.columns[-1]')
            if hint == 'auto':
                objective = '"numerical_prediction" if "' + task + '" == "regression" else "categorical_known"'
            else:
                objective = f'"{hint}"'
            train_kwargs = f'"{task}", test_size={test_size}'
            if ensemble != 'none':
                train_kwargs += f', use_ensemble=True, ensemble_strategy="{ensemble}"'
            lines.append(f'    _objective = {objective}')
            lines.append('    results = (CleanStep(df) >> SelectStep(_target)')
            lines.append(f'               >> ModelStep(_objective) >> TrainStep({train_kwargs})).run()')

        elif t == 'predict':
            artifact = cfg.get('artifact_path', 'model.scomp')
            lines.append(f'    _artifact = ScompArtifact.load("{artifact}")')
            lines.append("    df['prediction'] = _artifact.predict(df)")

        elif t == 'anomaly':
            methods = cfg.get('methods', 'iforest,lof')
            contamination = cfg.get('contamination', '0.05')
            lines.append('    from scomp_link import AnomalyDetector')
            lines.append(f'    _det = AnomalyDetector(methods="{methods}".split(","), contamination={contamination})')
            lines.append('    _anom = _det.fit_predict(df)')
            lines.append("    df = _anom['data']")

        elif t == 'forecast':
            col = cfg.get('column', '')
            horizon = cfg.get('horizon', '10')
            method = cfg.get('method', 'auto')
            lines.append('    from scomp_link import TimeSeriesForecaster')
            lines.append(f'    _col = inputs.get("forecast_column", "{col}") or df.columns[0]')
            lines.append(f'    _fc = TimeSeriesForecaster(method="{method}", horizon={horizon})')
            lines.append('    _fc.fit(df[_col].dropna())')
            lines.append(f'    _fc.predict_with_ci(steps={horizon}).to_csv(os.path.join(out_dir, "forecast.csv"))')

        elif t == 'drift':
            ref_ds = cfg.get('reference_dataset', 'wine_quality')
            threshold = cfg.get('threshold', '0.1')
            lines.append('    from scomp_link import DriftDetector')
            lines.append(f'    _ref = pd.read_csv(os.path.join(data_dir, "{ref_ds}.csv"))')
            lines.append(f'    _drift = DriftDetector(_ref, df, threshold={threshold})')
            lines.append('    _drift_results = _drift.run()')
            lines.append('    _drift.save_html(os.path.join(out_dir, "drift_report.html"))')

        elif t == 'explainability':
            method = cfg.get('method', 'shap')
            num_features = cfg.get('num_features', '10')
            if method == 'shap':
                lines.append('    from scomp_link import ShapExplainer')
                lines.append('    _target = inputs.get("target_col", df.columns[-1])')
                lines.append('    _explainer = ShapExplainer(results.get("model"), df.drop(columns=[_target]))')
                lines.append(f'    _explainer.run(num_features={num_features})')
            else:
                lines.append('    from scomp_link import LimeExplainer')
                lines.append('    _target = inputs.get("target_col", df.columns[-1])')
                lines.append('    _explainer = LimeExplainer(results.get("model"), df.drop(columns=[_target]))')
                lines.append(f'    _explainer.run(num_features={num_features})')

        elif t == 'fairness':
            sensitive = cfg.get('sensitive_column', '')
            predicted = cfg.get('predicted_col', 'prediction')
            target_col = cfg.get('target_col', '')
            lines.append('    from scomp_link import FairnessMetrics')
            lines.append(f'    _fair = FairnessMetrics(df["{target_col}"], df["{predicted}"], df["{sensitive}"])')
            lines.append('    _fair_results = _fair.summary()')

        elif t == 'tuning':
            method = cfg.get('method', 'optuna')
            n_trials = cfg.get('n_trials', '50')
            scoring = cfg.get('scoring', 'r2')
            if method == 'optuna':
                lines.append('    from scomp_link import OptunaOptimizer')
                lines.append('    _target = inputs.get("target_col", df.columns[-1])')
                lines.append('    # Tuning is applied via TrainStep with use_ensemble or via standalone optimizer')
                lines.append(f'    # OptunaOptimizer: n_trials={n_trials}, scoring="{scoring}"')
            else:
                lines.append('    from scomp_link import HalvingSearchOptimizer')
                lines.append('    _target = inputs.get("target_col", df.columns[-1])')
                lines.append(f'    # HalvingSearchOptimizer: scoring="{scoring}"')

        elif t == 'validation':
            methods = cfg.get('methods', 'kfold')
            cv_folds = cfg.get('cv_folds', '5')
            bootstrap_iter = cfg.get('bootstrap_iterations', '100')
            lines.append('    from scomp_link import Validator')
            lines.append('    _target = inputs.get("target_col", df.columns[-1])')
            lines.append('    _validator = Validator(results.get("model"), df.drop(columns=[_target]), df[_target])')
            if methods == 'bootstrap':
                lines.append(
                    f'    _val_results = _validator.run(methods=["{methods}"], '
                    f'bootstrap_iterations={bootstrap_iter})')
            else:
                lines.append(f'    _val_results = _validator.run(methods=["{methods}"], cv_folds={cv_folds})')

        elif t == 'text_nlp':
            text_col = cfg.get('text_column', '')
            method = cfg.get('method', 'contrastive')
            head = cfg.get('head', 'auto')
            lines.append(f'    _text_col = inputs.get("text_column", "{text_col}")')
            lines.append('    _target = inputs.get("target_col", df.columns[-1])')
            lines.append('    from scomp_link import ScompLinkPipeline')
            lines.append('    _pipe = ScompLinkPipeline("Text Pipeline")')
            lines.append('    _pipe.import_and_clean_data(df)')
            lines.append('    _pipe.select_variables(target_col=_target)')
            lines.append(
                f'    results = _pipe.run_pipeline(task_type="text", '
                f'text_col=_text_col, method="{method}", head="{head}")')

        elif t == 'report':
            # Quick Report: generates a full report with optional KPI cards + summary
            include_kpi = cfg.get('include_kpi', True)
            include_summary = cfg.get('include_summary', True)
            dark_mode = cfg.get('dark_mode', False)
            lines.append('    from scomp_link.utils.report_html import ScompLinkHTMLReport')
            lines.append('    _rpath = os.path.join(out_dir, "report.html")')
            lines.append('    # Copy model-generated report if available')
            lines.append('    _auto_report = results.get("report_path", "")')
            lines.append('    if _auto_report and os.path.exists(_auto_report):')
            lines.append('        import shutil')
            lines.append('        shutil.copy(_auto_report, _rpath)')
            lines.append('    else:')
            lines.append('        class _Report(ScompLinkHTMLReport, title="Pipeline Report"): pass')
            lines.append('        _report = _Report()')
            if dark_mode:
                lines.append('        _report.add_dark_mode_toggle()')
            lines.append('        _report.open_section("Results")')
            if include_kpi:
                lines.append('        if results.get("metrics"):')
                lines.append(
                    '            _report.add_kpi_cards({k: {"value": f"{v:.4f}"'
                    ' if isinstance(v, float) else str(v)}'
                    ' for k, v in results["metrics"].items()})'
                )
            if include_summary:
                lines.append('        if df is not None:')
                lines.append('            _report.add_summary_stats(df, "Data Summary")')
            lines.append('        if results.get("metrics"):')
            lines.append('            _report.add_dataframe(pd.DataFrame([results["metrics"]]), "Model Metrics")')
            lines.append('        _report.close_section()')
            lines.append('        _report.save(_rpath)')

        elif t == 'report_kpi':
            cols = cfg.get('cols', '3')
            lines.append('    if results.get("metrics"):')
            lines.append('        if "_report" not in dir(): ')
            lines.append('            from scomp_link.utils.report_html import ScompLinkHTMLReport')
            lines.append('            class _Report(ScompLinkHTMLReport, title="Pipeline Report"): pass')
            lines.append('            _report = _Report()')
            lines.append(
                '        _report.add_kpi_cards({k: {"value": f"{v:.4f}" if isinstance(v, float)'
                f' else str(v)}} for k, v in results["metrics"].items()}}, cols={cols})'
            )

        elif t == 'report_plotly_grid':
            cols = cfg.get('cols', '2')
            lines.append('    # Plotly grid — requires figures to be created from data')
            lines.append(f'    # Add plotly figures to _report.add_plotly_grid(figures, cols={cols})')

        elif t == 'report_tabs':
            tab_labels = cfg.get('tab_labels', 'Overview,Details')
            lines.append(f'    # Tabs: {tab_labels}')
            lines.append('    # Use _report.add_tabs(tabs_dict) with content for each tab')

        elif t == 'report_comparison':
            baseline = cfg.get('baseline_col', '')
            compare = cfg.get('compare_cols', '')
            lines.append(f'    # Comparison table: baseline="{baseline}", compare="{compare}"')
            compare_list = compare.split(",") if compare else []
            lines.append(f'    # Use _report.add_comparison_table(df, "{baseline}", {compare_list})')

        elif t == 'report_summary':
            title = cfg.get('title', 'Data Summary')
            lines.append('    if "_report" not in dir():')
            lines.append('        from scomp_link.utils.report_html import ScompLinkHTMLReport')
            lines.append('        class _Report(ScompLinkHTMLReport, title="Pipeline Report"): pass')
            lines.append('        _report = _Report()')
            lines.append('    if df is not None:')
            lines.append(f'        _report.add_summary_stats(df, "{title}")')

        elif t == 'report_dark_mode':
            lines.append('    if "_report" not in dir():')
            lines.append('        from scomp_link.utils.report_html import ScompLinkHTMLReport')
            lines.append('        class _Report(ScompLinkHTMLReport, title="Pipeline Report"): pass')
            lines.append('        _report = _Report()')
            lines.append('    _report.add_dark_mode_toggle()')

        elif t == 'save_artifact':
            name = cfg.get('artifact_name', 'model.scomp')
            lines.append('    if results.get("model"):')
            lines.append('        _art = ScompArtifact()')
            lines.append('        _art.set_model(results["model"])')
            lines.append('        _art.set_metrics(results.get("metrics", {}))')
            lines.append(f'        _art.save(os.path.join(out_dir, "{name}"))')

        lines.append('')

    # Save granular report if created
    if has_report_blocks:
        lines.append('    # Save report if granular blocks created one')
        lines.append('    if "_report" in dir():')
        lines.append('        _report.save(os.path.join(out_dir, "report.html"))')
        lines.append('')

    # Final output
    lines.append('    # Save output')
    lines.append('    if results.get("metrics"):')
    lines.append('        pd.DataFrame([results["metrics"]]).to_csv(output_path, index=False)')
    lines.append('    elif df is not None:')
    lines.append('        df.head(1000).to_csv(output_path, index=False)')
    lines.append('    return results')

    return chr(10).join(lines) + chr(10)


def _extract_inputs_from_steps(steps):
    """Extract user-configurable inputs from pipeline steps."""
    inputs = {}
    for step in steps:
        cfg = step.get('config', {})
        t = step['type']
        if t == 'train_model' and cfg.get('target_col'):
            inputs['target_col'] = {
                'type': 'text', 'default': cfg['target_col'],
                'description': 'Target column to predict'
            }
        if t == 'forecast' and cfg.get('column'):
            inputs['forecast_column'] = {
                'type': 'text', 'default': cfg['column'],
                'description': 'Column for time series forecast'
            }
        if t == 'text_nlp' and cfg.get('text_column'):
            inputs['text_column'] = {
                'type': 'text', 'default': cfg['text_column'],
                'description': 'Text column for NLP'
            }
        if t == 'fairness' and cfg.get('sensitive_column'):
            inputs['sensitive_column'] = {
                'type': 'text', 'default': cfg['sensitive_column'],
                'description': 'Sensitive attribute column for fairness check'
            }
    if not inputs:
        inputs['target_col'] = {'type': 'text', 'default': '', 'description': 'Target column (optional override)'}
    return inputs


# --- COMMENTS ON ANALYSES ---

@catalog_bp.route('/analysis/<name>/comment', methods=['POST'])
def add_comment(name):
    from models import Comment, db
    text = request.form.get('text', '').strip()
    if not text:
        return '', 204
    name = name.replace('512', ' ')
    comment = Comment(analysis_name=name, user_id=session.get('user_id'), text=text)
    db.session.add(comment)
    db.session.commit()
    username = session.get('username', 'user')
    html = (
        f'<div style="padding:8px 0;border-bottom:1px solid #eee;">'
        f'<b>{username}</b> '
        f'<span style="color:#999;font-size:.75rem;">{comment.created_at.strftime("%Y-%m-%d %H:%M")}</span>'
        f'<p style="margin:4px 0;font-size:.85rem;">{text}</p></div>'
    )
    return html


@catalog_bp.route('/analysis/<name>/comments')
def get_comments(name):
    from models import Comment, User
    name = name.replace('512', ' ')
    comments = Comment.query.filter_by(analysis_name=name).order_by(Comment.created_at.desc()).all()
    html = ''
    for c in comments:
        user = User.query.get(c.user_id) if c.user_id else None
        username = user.username if user else 'user'
        html += (
            f'<div style="padding:8px 0;border-bottom:1px solid #eee;">'
            f'<b>{username}</b> '
            f'<span style="color:#999;font-size:.75rem;">{c.created_at.strftime("%Y-%m-%d %H:%M")}</span>'
            f'<p style="margin:4px 0;font-size:.85rem;">{c.text}</p></div>'
        )
    return html or (
        '<div style="text-align:center;padding:1.5rem;">'
        '<div style="font-size:2rem;opacity:.5;">💬</div>'
        '<p style="color:#999;font-size:.85rem;">No comments yet. Be the first to share your thoughts!</p>'
        '</div>'
    )


# --- WEBHOOKS ---

@catalog_bp.route('/analysis/<name>/webhooks', methods=['GET', 'POST'])
def manage_webhooks(name):
    from models import Webhook, db
    name = name.replace('512', ' ')
    if request.method == 'POST':
        url = request.form.get('url', '').strip()
        secret = request.form.get('secret', '')
        if url:
            wh = Webhook(analysis_name=name, url=url, secret=secret)
            db.session.add(wh)
            db.session.commit()
    webhooks = Webhook.query.filter_by(analysis_name=name).all()
    html = ''
    for w in webhooks:
        safe_name = name.replace(' ', '512')
        html += (
            f'<div style="display:flex;align-items:center;gap:.5rem;padding:4px 0;">'
            f'<code style="font-size:.75rem;">{w.url}</code>'
            f'<form method="post" action="/analysis/{safe_name}/webhooks/{w.id}/delete" style="margin:0;">'
            f'<button class="w3-button w3-tiny w3-red">×</button></form></div>'
        )
    return html or '<p style="color:#999;">No webhooks configured</p>'


@catalog_bp.route('/analysis/<name>/webhooks/<int:wh_id>/delete', methods=['POST'])
def delete_webhook(name, wh_id):
    from models import Webhook, db
    wh = Webhook.query.get_or_404(wh_id)
    db.session.delete(wh)
    db.session.commit()
    return redirect(f'/analysis/{name}/webhooks')


# --- SCHEDULER ---

def execute_scheduled_analysis(app, name, inputs):
    """Execute a structured analysis (called by APScheduler)."""
    import importlib.util
    import shutil
    with app.app_context():
        webapp = get_webapp()
        script_path = f"{webapp.extract_main_folder()}/{name}/analysis/structured_analysis_main.py"
        output_dir = f"{webapp.extract_main_folder()}/{name}/physical_output/main"
        os.makedirs(output_dir, exist_ok=True)
        output_path = f"{output_dir}/output.csv"

        # Create initial execution record with 'running' status
        exe = _save_execution(name, session.get('user_id'), 'running', inputs=inputs)

        try:
            spec = importlib.util.spec_from_file_location("analysis_module", script_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            module.run(inputs=inputs, output_path=output_path)
            timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
            version_dir = f"{webapp.extract_main_folder()}/{name}/physical_output"
            outputs = []
            for f_name in os.listdir(output_dir):
                if f_name.startswith('.') or '.ini' in f_name:
                    continue
                ext = os.path.splitext(f_name)[1]
                dest = f"{version_dir}/{timestamp}{ext}"
                shutil.copy(f"{output_dir}/{f_name}", dest)
                outputs.append(f"{timestamp}{ext}")

            # Update execution record to success
            exe.status = 'success'
            exe.finished_at = datetime.datetime.now(datetime.timezone.utc)
            exe.output_path = f"{version_dir}/{timestamp}"
            exe.outputs_json = json.dumps(outputs)
            db.session.commit()
            logger.info(f"Scheduled analysis '{name}' completed")
        except Exception as e:
            # Update execution record to failed
            exe.status = 'failed'
            exe.finished_at = datetime.datetime.now(datetime.timezone.utc)
            exe.log_text = str(e)
            db.session.commit()
            logger.error(f"Scheduled analysis '{name}' failed: {e}")


@catalog_bp.route('/schedule_analysis/', methods=['POST'])
def schedule_analysis():
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.interval import IntervalTrigger
    from flask import current_app

    name = request.form.get('analysis_name', '')
    inputs = {k: v for k, v in request.form.items()
              if k not in ('analysis_name', 'schedule_type', 'schedule_time', 'schedule_cron')}

    schedule_type = request.form.get('schedule_type', '')
    schedule_time = request.form.get('schedule_time', '07:00')
    schedule_cron = request.form.get('schedule_cron', '')

    scheduler = current_app.config['SCHEDULER']
    hour, minute = (int(x) for x in schedule_time.split(':')) if schedule_time else (7, 0)

    import datetime
    job_id = f"{name}_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}"

    if schedule_type == 'daily':
        trigger = CronTrigger(hour=hour, minute=minute)
    elif schedule_type == 'hourly':
        trigger = IntervalTrigger(hours=1)
    elif schedule_type == 'weekly_mon':
        trigger = CronTrigger(day_of_week='mon', hour=hour, minute=minute)
    elif schedule_type == 'weekly_fri':
        trigger = CronTrigger(day_of_week='fri', hour=hour, minute=minute)
    elif schedule_type == 'cron' and schedule_cron:
        trigger = CronTrigger.from_crontab(schedule_cron)
    else:
        return redirect(f"/create_investigations?name={name.replace(' ', '512')}")

    app = current_app._get_current_object()
    scheduler.add_job(
        id=job_id,
        func=execute_scheduled_analysis,
        trigger=trigger,
        args=[app, name, inputs],
        name=f"{name} ({schedule_type})"
    )
    logger.info(f"Scheduled '{name}' as '{schedule_type}' (job: {job_id})")
    return redirect('/schedules/')


@catalog_bp.route('/schedules/')
def schedules_page():
    from flask import current_app
    webapp = get_webapp()
    html_part = webapp.substitute_html(port=webapp.constants["port"], project_folder=webapp.project_folder)
    scheduler = current_app.config['SCHEDULER']
    jobs = []
    for job in scheduler.get_jobs():
        jobs.append({
            'id': job.id,
            'name': job.name or job.id,
            'next_run': str(job.next_run_time.strftime('%Y-%m-%d %H:%M')) if job.next_run_time else 'Paused',
            'trigger': str(job.trigger)
        })
    return render_template('schedules.html',
                           title='Scheduled Analyses',
                           jobs=jobs,
                           head=html_part['head'],
                           top_container=html_part['top_container'],
                           sidebar_menu=html_part['sidebar_menu'],
                           port=webapp.constants["port"],
                           project_folder=webapp.project_folder)


@catalog_bp.route('/delete_schedule/')
def delete_schedule():
    from flask import current_app
    job_id = request.args.get('id', '')
    scheduler = current_app.config['SCHEDULER']
    try:
        scheduler.remove_job(job_id)
        logger.info(f"Deleted scheduled job: {job_id}")
    except Exception:
        pass
    return redirect('/schedules/')


@catalog_bp.route('/run_schedule_now/')
def run_schedule_now():
    from flask import current_app
    job_id = request.args.get('id', '')
    scheduler = current_app.config['SCHEDULER']
    try:
        job = scheduler.get_job(job_id)
        if job:
            job.func(*job.args, **job.kwargs)
    except Exception as e:
        logger.error(f"Manual run failed for {job_id}: {e}")
    return redirect('/schedules/')


# --- EXECUTION HISTORY ---

@catalog_bp.route('/executions')
def executions_page():
    """View execution history with filtering and HTMX polling."""
    webapp = get_webapp()
    html_part = webapp.substitute_html(port=webapp.constants["port"], project_folder=webapp.project_folder)
    page = int(request.args.get('page', 1))
    status_filter = request.args.get('status', '')
    query = Execution.query.order_by(Execution.started_at.desc())
    if status_filter:
        query = query.filter_by(status=status_filter)
    executions = query.paginate(page=page, per_page=20, error_out=False)

    # Check if any executions are running for HTMX polling
    has_running = Execution.query.filter_by(status='running').count() > 0

    return render_template('executions.html',
                           head=html_part['head'],
                           top_container=html_part['top_container'],
                           sidebar_menu=html_part['sidebar_menu'],
                           executions=executions,
                           status_filter=status_filter,
                           has_running=has_running,
                           port=webapp.constants["port"],
                           project_folder=webapp.project_folder)


# --- PIPELINE VERSIONING ---

@catalog_bp.route('/analysis/<name>/versions')
def pipeline_versions(name):
    """View pipeline version history for an analysis."""
    webapp = get_webapp()
    html_part = webapp.substitute_html(port=webapp.constants["port"], project_folder=webapp.project_folder)
    name = name.replace('512', ' ')
    versions = PipelineVersion.query.filter_by(analysis_name=name).order_by(
        PipelineVersion.created_at.desc()
    ).all()

    # Get user info for each version
    version_data = []
    for v in versions:
        user = User.query.get(v.user_id) if v.user_id else None
        version_data.append({
            'id': v.id,
            'version_num': v.version_num,
            'created_at': v.created_at,
            'message': v.message,
            'username': user.username if user else 'system'
        })

    # Get current analysis info
    analysis = webapp.read_single_analysis(webapp.extract_main_folder(), name)

    return render_template('pipeline_versions.html',
                           head=html_part['head'],
                           top_container=html_part['top_container'],
                           sidebar_menu=html_part['sidebar_menu'],
                           analysis_name=name,
                           versions=version_data,
                           analysis=analysis,
                           port=webapp.constants["port"],
                           project_folder=webapp.project_folder)


@catalog_bp.route('/analysis/<name>/restore/<int:version_id>', methods=['POST'])
def restore_version(name, version_id):
    """Restore a pipeline to a previous version."""
    webapp = get_webapp()
    name = name.replace('512', ' ')
    version = PipelineVersion.query.get_or_404(version_id)

    # Write the script_text back to the analysis file
    script_path = f"{webapp.extract_main_folder()}/{name}/analysis/structured_analysis_main.py"
    with open(script_path, 'w') as f:
        f.write(version.script_text)

    # Create a new version record for the restore
    max_version = db.session.query(db.func.max(PipelineVersion.version_num)).filter_by(
        analysis_name=name
    ).scalar() or 0
    new_version = PipelineVersion(
        analysis_name=name,
        version_num=max_version + 1,
        graph_json=version.graph_json,
        script_text=version.script_text,
        user_id=session.get('user_id'),
        message=f'Restored from version {version.version_num}'
    )
    db.session.add(new_version)
    db.session.commit()

    logger.info(f"Pipeline '{name}' restored to version {version.version_num}")
    return redirect(f'/analysis/{name.replace(" ", "512")}/versions')

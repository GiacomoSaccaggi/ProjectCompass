import os

import pandas as pd
from flask import Blueprint, current_app, jsonify, request

from logging_config import logger
from models import DbConnection, db
from utils.db_errors import ConnectionNotFoundError, ConnectionValidationError, DbConnectionError

api_bp = Blueprint('api', __name__, url_prefix='/api')


def get_webapp():
    return current_app.config['WEBAPP']


def _resolve_connection_id(connection: int | str | None) -> int | None:
    """Resolve an optional API connection reference by ID or saved name."""
    if connection is None or connection == '':
        return None
    if isinstance(connection, bool):
        raise ConnectionValidationError('The connection value must be an ID or saved connection name.')
    if isinstance(connection, int):
        saved = db.session.get(DbConnection, connection)
        if saved is None:
            raise ConnectionNotFoundError('The saved database connection was not found.')
        return saved.id
    if not isinstance(connection, str) or not connection.strip():
        raise ConnectionValidationError('The connection value must be an ID or saved connection name.')

    connection_name = connection.strip()
    if connection_name.isdecimal():
        saved = db.session.get(DbConnection, int(connection_name))
        if saved is not None:
            return saved.id
    saved = DbConnection.query.filter_by(name=connection_name).first()
    if saved is None:
        raise ConnectionNotFoundError('The saved database connection was not found.')
    return saved.id


@api_bp.route('/health')
def health():
    try:
        from importlib.metadata import version
        ver = version("projectcompass")
    except Exception:
        ver = "unknown"
    return jsonify({'status': 'ok', 'version': ver})


@api_bp.route('/search')
def api_search():
    from sqlalchemy import text

    from models import db
    q = request.args.get('q', '').strip()
    if not q or len(q) < 2:
        return jsonify({'results': []})
    try:
        results = db.session.execute(
            text("SELECT name, title, snippet(analyses_fts, 2, '<b>', '</b>', '...', 30) "
                 "as snippet FROM analyses_fts WHERE analyses_fts MATCH :q LIMIT 10"),
            {'q': q}
        ).fetchall()
        return jsonify({'results': [{'name': r[0], 'title': r[1], 'snippet': r[2]} for r in results]})
    except Exception:
        return jsonify({'results': []})


@api_bp.route('/search_html')
def api_search_html():
    from sqlalchemy import text

    from models import db
    q = request.args.get('q', '').strip()
    if not q or len(q) < 2:
        return ''
    try:
        results = db.session.execute(
            text("SELECT name, title FROM analyses_fts WHERE analyses_fts MATCH :q LIMIT 8"),
            {'q': q + '*'}
        ).fetchall()
    except Exception:
        return '<div style="padding:10px;color:#999;">Search error</div>'
    if not results:
        return (
            '<div style="padding:10px 14px;color:var(--mariner-text-muted, #94a3b8);'
            'font-size:0.84rem;">No results</div>'
        )
    html = ''
    for r in results:
        name, title = r[0], r[1] or r[0]
        safe_name = name.replace(' ', '512')
        html += (
            f'<a href="/open_version?name={safe_name}" style="display:block;padding:9px 14px;'
            f'text-decoration:none;color:var(--mariner-text-primary, #0f172a);'
            f'border-bottom:1px solid var(--mariner-border-subtle, rgba(148,163,184,0.18));'
            f'font-size:0.86rem;font-weight:600;">'
            f'<i class="fa fa-compass" style="color:var(--mariner-cyan, #0284c7);margin-right:6px;"></i>{title}</a>'
        )
    return html


@api_bp.route('/analyses')
def list_analyses():
    webapp = get_webapp()
    analyses = webapp.read_multiple_analysis()

    # Search and filter
    q = request.args.get('q', '').lower()
    product = request.args.get('product', '')
    owner = request.args.get('owner', '')

    results = []
    for k, v in analyses.items():
        if q and q not in v.get('title', '').lower() and q not in v.get('description', '').lower():
            continue
        if product and v.get('product', '') != product:
            continue
        if owner and v.get('owner', '') != owner:
            continue
        results.append({
            'name': k,
            'title': v.get('title', ''),
            'owner': v.get('owner', ''),
            'product': v.get('product', ''),
            'countries': v.get('countries', ''),
            'description': v.get('description', ''),
            'start_date': v.get('start_date', ''),
            'last_modified': v.get('last_modified', ''),
            'structured_analysis': v.get('structured_analysis', 'n') == 'y',
        })

    # Pagination
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 20))
    total = len(results)
    start = (page - 1) * per_page
    paginated = results[start:start + per_page]

    return jsonify({
        'analyses': paginated,
        'total': total,
        'page': page,
        'per_page': per_page,
        'total_pages': max(1, (total + per_page - 1) // per_page),
    })


@api_bp.route('/analyses/<name>')
def get_analysis(name):
    webapp = get_webapp()
    name = name.replace('512', ' ')
    try:
        analysis = webapp.read_single_analysis(webapp.extract_main_folder(), name)
        return jsonify({
            'title': analysis.get('title', ''),
            'owner': analysis.get('owner', ''),
            'product': analysis.get('product', ''),
            'countries': analysis.get('countries', ''),
            'description': analysis.get('description', ''),
            'start_date': analysis.get('start_date', ''),
            'last_modified': analysis.get('last_modified', ''),
            'structured_analysis': analysis.get('structured_analysis', 'n') == 'y',
            'inputs': analysis.get('inputs', {}),
            'links': analysis.get('links', {}),
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 404


@api_bp.route('/analyses/<name>/run', methods=['POST'])
def run_analysis_api(name):
    """Trigger an analysis or flow inside Analyses/<name>/ as a Kubernetes Job and return run metadata."""
    from flask import session

    from models import log_action

    if not session.get('authenticated'):
        return jsonify({'error': 'Unauthorized'}), 401
    if session.get('role') == 'viewer':
        return jsonify({'error': 'Forbidden: viewer role cannot execute analyses or flows.'}), 403

    webapp = get_webapp()
    resolved_name = name.replace('512', ' ')
    flow = webapp.read_flow(resolved_name)
    if flow is None:
        return jsonify({'error': f"Analysis or flow '{resolved_name}' not found."}), 404

    payload = request.get_json(silent=True) if request.is_json else {}
    payload = payload or {}
    parameters = payload.get('parameters') or payload.get('inputs') or {}
    pip_requirements = payload.get('pip_requirements')
    env_vars = payload.get('env_vars')
    secret_refs = payload.get('secret_refs')
    image = payload.get('image')
    wait_sync = bool(
        payload.get('wait')
        or request.args.get('wait') == '1'
        or current_app.config.get('K8S_SYNC_WATCHER', False)
    )

    exe = webapp.launch_flow_run(
        flow_name=resolved_name,
        parameters=parameters,
        pip_requirements=pip_requirements,
        env_vars=env_vars,
        secret_refs=secret_refs,
        image=image,
        user_id=session.get('user_id'),
        trigger_type='manual',
        app=current_app._get_current_object(),
        wait_for_watcher=wait_sync,
    )
    log_action('run_analysis_api', 'analysis', resolved_name, details={'run_id': exe.id, 'job_name': exe.job_name})
    return jsonify({
        'run_id': exe.id,
        'id': exe.id,
        'analysis_name': exe.analysis_name,
        'flow_name': exe.analysis_name,
        'job_name': exe.job_name,
        'status': exe.status,
        'exit_code': exe.exit_code,
        'error_message': exe.error_message,
        'log_text': exe.log_text or '',
        'detail_url': f'/runs/{exe.id}',
        'stream_url': f'/runs/{exe.id}/stream',
    })


@api_bp.route('/data')
def list_data():
    webapp = get_webapp()
    datasets = webapp.list_data()
    return jsonify({'datasets': datasets})


@api_bp.route('/data/<name>/preview')
def preview_data(name):
    webapp = get_webapp()
    limit = int(request.args.get('limit', 10))
    path = os.path.join(webapp.save_data_path, f"{name}.csv")
    if not os.path.exists(path):
        return jsonify({'error': 'Dataset not found'}), 404
    df = pd.read_csv(path, nrows=limit)
    return jsonify({
        'columns': list(df.columns),
        'rows': df.to_dict(orient='records'),
        'total_rows': sum(1 for _ in open(path)) - 1,
    })


@api_bp.route('/query', methods=['POST'])
def run_query():
    webapp = get_webapp()
    data = request.get_json()
    if not data or 'sql' not in data:
        return jsonify({'error': 'Missing "sql" field'}), 400

    sql = data['sql']
    limit = data.get('limit', 100)
    logger.info(f"API query: {sql[:100]}...")

    try:
        connection_id = _resolve_connection_id(data.get('connection'))
        df = webapp.run_sql(sql, connection_id)
        total = len(df)
        if total > limit:
            df = df.head(limit)
        return jsonify({
            'columns': list(df.columns),
            'rows': df.to_dict(orient='records'),
            'total_rows': total,
            'truncated': total > limit,
        })
    except ConnectionNotFoundError as e:
        return jsonify({'error': str(e)}), 404
    except DbConnectionError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@api_bp.route('/activity')
def api_activity():
    from models import AuditLog, User
    limit = int(request.args.get('limit', 20))
    entries = AuditLog.query.order_by(AuditLog.created_at.desc()).limit(limit).all()
    result = []
    for e in entries:
        user = User.query.get(e.user_id) if e.user_id else None
        result.append({
            'action': e.action,
            'target_type': e.target_type,
            'target_name': e.target_name,
            'user': user.username if user else 'system',
            'created_at': e.created_at.isoformat() if e.created_at else '',
        })
    return jsonify(result)


@api_bp.route('/activity_html')
def api_activity_html():
    from models import AuditLog, User
    entries = AuditLog.query.order_by(AuditLog.created_at.desc()).limit(15).all()
    html = ''
    for e in entries:
        user = User.query.get(e.user_id) if e.user_id else None
        username = user.username if user else 'system'
        icon_map = {
            'login': 'fa-sign-in',
            'create': 'fa-plus',
            'run': 'fa-play',
            'upload': 'fa-upload',
            'delete': 'fa-trash',
            'save': 'fa-save',
        }
        icon = icon_map.get(e.action, 'fa-circle')
        html += (
            f'<div style="padding:7px 2px;border-bottom:1px solid '
            f'var(--mariner-border-subtle, rgba(15,23,42,0.1));font-size:.84rem;">'
            f'<i class="fa {icon}" style="width:22px;color:var(--mariner-cyan, #0284c7);"></i> '
            f'<b>{username}</b> '
            f'<span style="color:var(--mariner-teal, #0d9488);font-weight:600;">{e.action}</span> '
            f'<span style="color:var(--mariner-text-muted, #64748b);">'
            f'{e.target_type}: {e.target_name}</span></div>'
        )
    return html or '<div style="padding:10px;color:var(--mariner-text-muted, #94a3b8);">No activity yet</div>'

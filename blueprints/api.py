import os

import pandas as pd
from flask import Blueprint, current_app, jsonify, request

from logging_config import logger

api_bp = Blueprint('api', __name__, url_prefix='/api')


def get_webapp():
    return current_app.config['WEBAPP']


@api_bp.route('/health')
def health():
    return jsonify({'status': 'ok'})


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
        return '<div style="padding:10px;color:#999;">No results</div>'
    html = ''
    for r in results:
        name, title = r[0], r[1] or r[0]
        html += (
            f'<a href="/analysis?q={name}" style="display:block;padding:8px 12px;'
            f'text-decoration:none;color:#333;border-bottom:1px solid #f0f0f0;" '
            f'onmouseover="this.style.background=\'#f0f4ff\'" '
            f'onmouseout="this.style.background=\'\'">{title}</a>'
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
        df = webapp.sql(sql)
        total = len(df)
        if total > limit:
            df = df.head(limit)
        return jsonify({
            'columns': list(df.columns),
            'rows': df.to_dict(orient='records'),
            'total_rows': total,
            'truncated': total > limit,
        })
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
            f'<div style="padding:6px 0;border-bottom:1px solid #eee;font-size:.8rem;">'
            f'<i class="fa {icon}" style="width:20px;color:#3F51B5;"></i> '
            f'<b>{username}</b> {e.action} '
            f'<span style="color:#666;">{e.target_type}: {e.target_name}</span></div>'
        )
    return html or '<div style="padding:10px;color:#999;">No activity yet</div>'

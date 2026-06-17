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

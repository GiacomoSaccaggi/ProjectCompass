import json
import re

import pandas as pd
from flask import Blueprint, current_app, render_template, request
from markupsafe import escape
from werkzeug.utils import secure_filename

from logging_config import logger
from models import DbConnection, Execution, db, log_action
from utils.db_connection_service import DbConnectionService
from utils.db_errors import ConnectionNotFoundError, DbConnectionError

data_bp = Blueprint('data', __name__)


def get_webapp():
    return current_app.config['WEBAPP']


def _get_data_lineage():
    """Get which analyses use each dataset based on execution history and analysis scripts."""
    import os
    from sqlalchemy.exc import SQLAlchemyError
    from blueprints.catalog import _extract_lineage_from_script

    lineage: dict[str, set[str]] = {}
    try:
        executions = Execution.query.filter(Execution.inputs_json.isnot(None)).all()
        for exe in executions:
            try:
                inputs = json.loads(exe.inputs_json) if exe.inputs_json else {}
                values = inputs.values() if isinstance(inputs, dict) else (inputs if isinstance(inputs, list) else [])
                for val in values:
                    if isinstance(val, str) and val.endswith('.csv'):
                        ds_name = os.path.basename(val).replace('.csv', '')
                        lineage.setdefault(ds_name, set()).add(exe.analysis_name)
            except (json.JSONDecodeError, TypeError, AttributeError):
                pass
    except (SQLAlchemyError, Exception) as exc:
        logger.warning(f"Unable to read execution lineage from DB: {exc}")
        try:
            db.session.rollback()
        except Exception:
            pass

    try:
        webapp = get_webapp()
        analyses = webapp.read_multiple_analysis()
        for analysis_name, info in analyses.items():
            folder = info.get('folder', '')
            if not folder or not os.path.isdir(folder):
                continue
            for scan_dir in (folder, os.path.join(folder, 'analysis')):
                if not os.path.isdir(scan_dir):
                    continue
                try:
                    for fname in sorted(os.listdir(scan_dir)):
                        if not fname.endswith('.py'):
                            continue
                        script_path = os.path.join(scan_dir, fname)
                        if os.path.isfile(script_path):
                            with open(script_path, encoding='utf-8', errors='ignore') as sf:
                                script_text = sf.read()
                            for ds_name in _extract_lineage_from_script(script_text):
                                lineage.setdefault(ds_name, set()).add(analysis_name)
                except OSError:
                    pass
    except Exception:
        pass

    return {k: sorted(list(v)) for k, v in lineage.items()}


def clean_query(output_query: str) -> str:
    """Sanitize HTML from query editor input."""
    output_query = re.sub(r'<\/?span.*?>', ' ', output_query)
    output_query = re.sub(r'<\/?div.*?>', ' ', output_query)
    for tag in ['<br>', '\r']:
        output_query = output_query.replace(tag, '\n')
    for entity in ['\xa0', '&nbsp;']:
        output_query = output_query.replace(entity, ' ')
    output_query = re.sub(r'<.*?>', '\n', output_query)
    while '  ' in output_query:
        output_query = output_query.replace('  ', ' ')
    while '\n\n' in output_query:
        output_query = output_query.replace('\n\n', '\n')
    return output_query.strip()


def _connection_id_from_form() -> int | None:
    """Read an optional saved connection ID from the current form."""
    value = request.form.get('connection_id', '').strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError as exc:
        raise ConnectionNotFoundError('The selected database connection is invalid.') from exc


def _connection_options() -> list[DbConnection]:
    """Return saved connections for the Query Runner selector."""
    return DbConnectionService().list()


@data_bp.route('/list_of_data/')
def list_of_data():
    webapp = get_webapp()
    html_part = webapp.substitute_html(port=webapp.constants["port"], project_folder=webapp.project_folder)
    return render_template('data_upload.html',
                           title=webapp.environments_info['title'],
                           intro=webapp.environments_info['intro'],
                           links=webapp.environments_info['links'],
                           top_container=html_part['top_container'], port=webapp.constants["port"],
                           project_folder=webapp.project_folder,
                           sidebar_menu=html_part['sidebar_menu'],
                           head=html_part['head'])


@data_bp.route('/upload_data_file/', methods=['POST'])
def upload_data():
    webapp = get_webapp()
    webapp.upload_text_files(request)
    # Extract filename from request
    filename = 'unknown'
    if 'filename' in request.form:
        filename = request.form['filename']
    elif request.files:
        for f in request.files.values():
            if f.filename:
                filename = f.filename
                break
    log_action('upload', 'dataset', filename)
    logger.info(f"Data file uploaded: {filename}")
    html_part = webapp.substitute_html(port=webapp.constants["port"], project_folder=webapp.project_folder)
    all_data = webapp.list_data()
    lineage = _get_data_lineage()
    return render_template('data_list.html',
                           title=webapp.environments_info['title'],
                           intro=webapp.environments_info['intro'],
                           links=webapp.environments_info['links'],
                           all_data=all_data,
                           lineage=lineage,
                           top_container=html_part['top_container'], port=webapp.constants["port"],
                           project_folder=webapp.project_folder,
                           sidebar_menu=html_part['sidebar_menu'],
                           head=html_part['head'])


@data_bp.route('/all_data/')
def all_data():
    webapp = get_webapp()
    html_part = webapp.substitute_html(port=webapp.constants["port"], project_folder=webapp.project_folder)
    all_data_list = webapp.list_data()
    lineage = _get_data_lineage()
    return render_template('data_list.html',
                           title=webapp.environments_info['title'],
                           intro=webapp.environments_info['intro'],
                           links=webapp.environments_info['links'],
                           all_data=all_data_list,
                           lineage=lineage,
                           top_container=html_part['top_container'], port=webapp.constants["port"],
                           project_folder=webapp.project_folder,
                           sidebar_menu=html_part['sidebar_menu'],
                           head=html_part['head'])


@data_bp.route('/query_runner/')
def query_runner():
    webapp = get_webapp()
    raw_connection_id = request.args.get('connection_id', '').strip()
    try:
        connection_id = int(raw_connection_id) if raw_connection_id else None
    except ValueError:
        connection_id = None
    datasets = sorted(webapp.list_data())
    default_table = 'sales_data' if 'sales_data' in datasets else (datasets[0] if datasets else 'database.table')
    default_query = f'SELECT * FROM {default_table} LIMIT 10'
    html_part = webapp.substitute_html(port=webapp.constants["port"], project_folder=webapp.project_folder)
    return render_template('query_results.html',
                           message='',
                           title=webapp.environments_info['title'],
                           intro=webapp.environments_info['intro'],
                           links=webapp.environments_info['links'],
                           top_container=html_part['top_container'], port=webapp.constants["port"],
                           sidebar_menu=html_part['sidebar_menu'],
                           head=html_part['head'],
                           show_res='none', project_folder=webapp.project_folder,
                           query=default_query,
                           datasets=datasets,
                           columns=[],
                           df=pd.DataFrame(),
                           connections=_connection_options(),
                           selected_connection_id=connection_id,
                           page=1, total_pages=1)


@data_bp.route('/query_results/', methods=['POST'])
def query_results():
    webapp = get_webapp()
    output_query = clean_query(request.form['output_query'].encode().decode('utf-8', 'ignore'))
    logger.info(f"Executing query: {output_query[:100]}...")
    message = ''
    connection_id = None
    query_error = False
    try:
        connection_id = _connection_id_from_form()
        df = webapp.run_sql(output_query, connection_id)
    except DbConnectionError as exc:
        df = pd.DataFrame()
        query_error = True
        message = f'<br>Remote query error: {escape(str(exc))}'
    columns = df.columns

    # Pagination
    try:
        page = max(1, int(request.form.get('page', 1)))
    except ValueError:
        page = 1
    per_page = 100
    total = len(df)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = min(page, total_pages)
    if total > per_page:
        df = df.iloc[(page - 1) * per_page: page * per_page]
        if not message:
            message += f'<br>Showing rows {(page-1)*per_page+1}-{min(page*per_page, total)} of {total}'

    html_part = webapp.substitute_html(port=webapp.constants["port"], project_folder=webapp.project_folder)
    return render_template('query_results.html',
                           message=message,
                           title=webapp.environments_info['title'],
                           intro=webapp.environments_info['intro'],
                           links=webapp.environments_info['links'],
                           top_container=html_part['top_container'], port=webapp.constants["port"],
                           sidebar_menu=html_part['sidebar_menu'],
                           head=html_part['head'],
                           show_res='none' if query_error else 'block', project_folder=webapp.project_folder,
                           query=output_query,
                           datasets=sorted(webapp.list_data()),
                           columns=columns,
                           df=df,
                           connections=_connection_options(),
                           selected_connection_id=connection_id,
                           page=page, total_pages=total_pages)


@data_bp.route('/open_data', methods=['GET'])
def open_data():
    webapp = get_webapp()
    name = request.args['name']
    output_query = f'select * from {name}'
    df = webapp.sql(output_query)
    columns = df.columns
    message = ''
    total = len(df)
    if total > 100:
        df = df.head(100)
        message += f'<br>Showing first 100 of {total} rows'
    html_part = webapp.substitute_html(port=webapp.constants["port"], project_folder=webapp.project_folder)
    return render_template('query_results.html',
                           message=message,
                           title=webapp.environments_info['title'],
                           intro=webapp.environments_info['intro'],
                           links=webapp.environments_info['links'],
                           top_container=html_part['top_container'], port=webapp.constants["port"],
                           sidebar_menu=html_part['sidebar_menu'],
                           head=html_part['head'],
                           show_res='block', project_folder=webapp.project_folder,
                           query=output_query,
                           datasets=sorted(webapp.list_data()),
                           columns=columns,
                           df=df,
                           connections=_connection_options(),
                           selected_connection_id=None,
                           page=1, total_pages=1)


@data_bp.route('/rawgraphs')
def rawgraphs():
    webapp = get_webapp()
    raw_connection_id = request.args.get('connection_id', '').strip()
    try:
        connection_id = int(raw_connection_id) if raw_connection_id else None
    except ValueError:
        connection_id = None
    html_part = webapp.substitute_html(port=webapp.constants["port"], project_folder=webapp.project_folder)
    return render_template('RAWGraphs.html',
                           title=webapp.environments_info['title'],
                           head=html_part['head'],
                           input_data='',
                           query_error='',
                           connection_id=connection_id,
                           top_container=html_part['top_container'], port=webapp.constants["port"],
                           project_folder=webapp.project_folder,
                           sidebar_menu=html_part['sidebar_menu'])


@data_bp.route('/save_query/', methods=['POST'])
def save_query():
    import datetime

    webapp = get_webapp()
    output_query = clean_query(request.form['output_query_to_save'].encode().decode('utf-8', 'ignore'))
    title = secure_filename(request.form.get('title', '').strip()).strip('.') or 'query'
    connection_id = None
    connection = None
    query_error = ''
    try:
        connection_id = _connection_id_from_form()
        if connection_id is not None:
            connection = db.session.get(DbConnection, connection_id)
            if connection is None:
                raise ConnectionNotFoundError('The selected database connection was not found.')
    except DbConnectionError as exc:
        query_error = str(exc)

    save_path = webapp.save_queries_path
    with open(f"{save_path}/{title}.sql", 'w') as f:
        header = f'-- Query saved: {datetime.datetime.now()}\n'
        if connection is not None:
            safe_connection_name = connection.name.replace('\r', ' ').replace('\n', ' ')
            header += f'-- connection: {safe_connection_name}\n'
        f.write(f'{header}{output_query}')
    logger.info(f"Query saved: {title}")

    df = pd.DataFrame()
    columns = df.columns
    if not query_error:
        try:
            df = webapp.run_sql(output_query, connection_id)
        except DbConnectionError as exc:
            query_error = str(exc)
    columns = df.columns
    message = f'<br>Saved query: {title}.sql'
    if query_error:
        message += f'<br>Remote query error: {escape(query_error)}'
    elif len(df) > 100:
        df = df.head(100)
        message += '<br>Showing first 100 rows'
    html_part = webapp.substitute_html(port=webapp.constants["port"], project_folder=webapp.project_folder)
    return render_template('query_results.html',
                           message=message,
                           title=webapp.environments_info['title'],
                           intro=webapp.environments_info['intro'],
                           links=webapp.environments_info['links'],
                           top_container=html_part['top_container'], port=webapp.constants["port"],
                           sidebar_menu=html_part['sidebar_menu'],
                           head=html_part['head'],
                           show_res='none' if query_error else 'block', project_folder=webapp.project_folder,
                           query=output_query,
                           datasets=sorted(webapp.list_data()),
                           columns=columns,
                           df=df,
                           connections=_connection_options(),
                           selected_connection_id=connection_id,
                           page=1, total_pages=1)


@data_bp.route('/upload_data/')
def upload_data_form():
    webapp = get_webapp()
    html_part = webapp.substitute_html(port=webapp.constants["port"], project_folder=webapp.project_folder)
    return render_template('data_upload.html',
                           title=webapp.environments_info['title'],
                           intro=webapp.environments_info['intro'],
                           links=webapp.environments_info['links'],
                           top_container=html_part['top_container'], port=webapp.constants["port"],
                           project_folder=webapp.project_folder,
                           sidebar_menu=html_part['sidebar_menu'],
                           head=html_part['head'])


@data_bp.route('/graph_analysis/', methods=['POST'])
def graph_analysis():
    webapp = get_webapp()
    html_part = webapp.substitute_html(port=webapp.constants["port"], project_folder=webapp.project_folder)
    query = request.form.get('output_query_to_rawgraph', '')
    query_error = ''
    connection_id = None
    try:
        connection_id = _connection_id_from_form()
    except ConnectionNotFoundError as exc:
        query_error = str(exc)
    input_data = ''
    if query and not query_error:
        try:
            df = webapp.run_sql(query, connection_id)
            input_data = df.to_csv(index=False, sep='\t')
        except DbConnectionError as exc:
            query_error = str(exc)
        except Exception:
            query_error = 'The query could not be prepared for RAWGraphs.'
    return render_template('RAWGraphs.html',
                           title=webapp.environments_info['title'],
                           head=html_part['head'],
                           input_data=input_data,
                           query_error=query_error,
                           connection_id=connection_id,
                           top_container=html_part['top_container'], port=webapp.constants["port"],
                           project_folder=webapp.project_folder,
                           sidebar_menu=html_part['sidebar_menu'])

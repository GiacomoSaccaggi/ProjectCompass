import re

import pandas as pd
from flask import Blueprint, current_app, render_template, request

from logging_config import logger

data_bp = Blueprint('data', __name__)


def get_webapp():
    return current_app.config['WEBAPP']


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
    logger.info("Data file uploaded")
    html_part = webapp.substitute_html(port=webapp.constants["port"], project_folder=webapp.project_folder)
    all_data = webapp.list_data()
    return render_template('data_list.html',
                           title=webapp.environments_info['title'],
                           intro=webapp.environments_info['intro'],
                           links=webapp.environments_info['links'],
                           all_data=all_data,
                           top_container=html_part['top_container'], port=webapp.constants["port"],
                           project_folder=webapp.project_folder,
                           sidebar_menu=html_part['sidebar_menu'],
                           head=html_part['head'])


@data_bp.route('/all_data/')
def all_data():
    webapp = get_webapp()
    html_part = webapp.substitute_html(port=webapp.constants["port"], project_folder=webapp.project_folder)
    all_data_list = webapp.list_data()
    return render_template('data_list.html',
                           title=webapp.environments_info['title'],
                           intro=webapp.environments_info['intro'],
                           links=webapp.environments_info['links'],
                           all_data=all_data_list,
                           top_container=html_part['top_container'], port=webapp.constants["port"],
                           project_folder=webapp.project_folder,
                           sidebar_menu=html_part['sidebar_menu'],
                           head=html_part['head'])


@data_bp.route('/query_runner/')
def query_runner():
    webapp = get_webapp()
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
                           query='select * from database.table limit 10',
                           columns=[],
                           df=pd.DataFrame(),
                           page=1, total_pages=1)


@data_bp.route('/query_results/', methods=['POST'])
def query_results():
    webapp = get_webapp()
    output_query = clean_query(request.form['output_query'].encode().decode('utf-8', 'ignore'))
    logger.info(f"Executing query: {output_query[:100]}...")

    df = webapp.sql(output_query)
    columns = df.columns
    message = ''

    # Pagination
    page = int(request.form.get('page', 1))
    per_page = 100
    total = len(df)
    total_pages = max(1, (total + per_page - 1) // per_page)
    if total > per_page:
        df = df.iloc[(page - 1) * per_page: page * per_page]
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
                           show_res='block', project_folder=webapp.project_folder,
                           query=output_query,
                           columns=columns,
                           df=df,
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
                           columns=columns,
                           df=df,
                           page=1, total_pages=1)


@data_bp.route('/rawgraphs')
def rawgraphs():
    webapp = get_webapp()
    html_part = webapp.substitute_html(port=webapp.constants["port"], project_folder=webapp.project_folder)
    return render_template('RAWGraphs.html',
                           title=webapp.environments_info['title'],
                           head=html_part['head'],
                           input_data='',
                           top_container=html_part['top_container'], port=webapp.constants["port"],
                           project_folder=webapp.project_folder,
                           sidebar_menu=html_part['sidebar_menu'])


@data_bp.route('/save_query/', methods=['POST'])
def save_query():
    import datetime
    webapp = get_webapp()
    output_query = clean_query(request.form['output_query_to_save'].encode().decode('utf-8', 'ignore'))
    title = request.form['title']
    save_path = webapp.save_queries_path
    with open(f"{save_path}/{title}.sql", 'w') as f:
        f.write(f'-- Query saved: {datetime.datetime.now()}\n{output_query}')
    logger.info(f"Query saved: {title}")

    df = webapp.sql(output_query)
    columns = df.columns
    message = f'<br>Saved query: {title}.sql'
    if len(df) > 100:
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
                           show_res='block', project_folder=webapp.project_folder,
                           query=output_query,
                           columns=columns,
                           df=df,
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

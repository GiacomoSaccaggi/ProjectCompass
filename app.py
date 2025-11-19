# -*- coding: utf-8 -*-
"""


░██╗░░░░░░░██╗███████╗██████╗░░█████╗░██████╗░██████╗░
░██║░░██╗░░██║██╔════╝██╔══██╗██╔══██╗██╔══██╗██╔══██╗
░╚██╗████╗██╔╝█████╗░░██████╦╝███████║██████╔╝██████╔╝
░░████╔═████║░██╔══╝░░██╔══██╗██╔══██║██╔═══╝░██╔═══╝░
░░╚██╔╝░╚██╔╝░███████╗██████╦╝██║░░██║██║░░░░░██║░░░░░
░░░╚═╝░░░╚═╝░░╚══════╝╚═════╝░╚═╝░░╚═╝╚═╝░░░░░╚═╝░░░░░

"""

# Import Pkg
import os
import re
import sys
import git
import json
import yaml
import shutil
import logging
import datetime
import subprocess
import numpy as np
import pandas as pd
from flask_cors import CORS
try:
    path = os.path.abspath(__file__)
except NameError:
    path = '/Users/giacomo.saccaggi/Documents/ProjectCompass/'
sys.path.append(path)
from basefun import ProjectCompass, encrypt_and_compress
from flask import Flask, render_template, request, redirect, url_for, jsonify, send_file, session
dir_path = os.path.dirname(path) + '/'
print(dir_path)
# Init WebApp
app = Flask(__name__, template_folder=f'{dir_path}Templates', static_folder=f'{dir_path}/')
CORS(app, resources={r"/*": {"origins": ["https://site_to_embedded_in.com"]}})
#CORS(app, resources={r"/*": {"origins": "*"}})
app.secret_key = b'_5#y2L"F4Q8z\n\xec]/'
gunicorn_error_logger = logging.getLogger('gunicorn.error')
app.logger.handlers.extend(gunicorn_error_logger.handlers)
app.logger.setLevel(logging.DEBUG)

webapp = ProjectCompass(dir_path=dir_path)

use_gitlab_repo = False
username = 'tester'
if use_gitlab_repo:
    # init git repository

    try:
        os.remove(f"{dir_path}Analyses/.git/index.lock")
    except Exception:
        pass
    try:
        os.remove(f"{dir_path}Analyses/.git/COMMIT_EDITMSG")
    except Exception:
        pass
    from git.repo import Repo
    err = ''
    try:
        repo = Repo(f'{dir_path}Analyses', search_parent_directories=True)
    except Exception as e:
        err += str(e)
        try:
            os.mkdir(f'{dir_path}Analyses')
        except Exception as e:
            err += str(e)
            print(err)



@app.route("/")
def index():
    """
    First page
    """
    html_part = webapp.substitute_html(port=webapp.constants["port"], project_folder=webapp.project_folder)
    img = f'<img src="http://127.0.0.1:{webapp.constants["port"]}/{webapp.project_folder}static/img/first_page.png" style="width:100%;"><br>'
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
        last_mod = datetime.datetime.now()-datetime.datetime.fromtimestamp(os.path.getmtime(info['folder']))
        if last_mod > datetime.timedelta(days=30):
            n_last_uploaded += 1
        if info['structured_analysis'] != 'n':
            number_of_structured_analysis += 1
        if info['product'] in product_info.keys():
            product_info[info['product']] += 1
        else:
            product_info[info['product']] = 1
    number_of_owners = len(set(owners))
    products = list(product_info.keys())
    number_of_products = len(products)
    product_labels = ','.join([f'"{i}"' for i in products])
    product_res = []
    product_color = []
    for p in products:
        product_res.append(product_info[p])
        c1, c2, c3 = np.random.choice([-192, -128, -99, 0, 99, 132, 128, 192, 255], size = 3)
        product_color.append([f"'rgba({c1}, {c2}, {c3}, 0.2)'", f"'rgba({c1}, {c2}, {c3}, 1)'"])
    product_res = ','.join([str(i) for i in product_res])
    return render_template('index.html',
                           title=webapp.environments_info['title'],
                           intro_title = img,
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
                           top_container=html_part['top_container'], port=webapp.constants["port"],
                           project_folder=webapp.project_folder,
                           sidebar_menu=html_part['sidebar_menu'])


@app.route("/overview")
def overview_page():
    """
    First page
    """
    html_part = webapp.substitute_html(port=webapp.constants["port"], project_folder=webapp.project_folder)
    img = f'<img src="http://127.0.0.1:{webapp.constants["port"]}/{webapp.project_folder}static/img/overview_page.png" style="width:100%;"><br>'
    img += f'<div class="w3-col w3-bar w3-text-projectcompass" style="padding: 10%;"><strong><img src="http://127.00.1:{webapp.constants["port"]}/{webapp.project_folder}static/img/description1.png" style="width:100%;"><br>'
    img += """<p>This tool was developed to address common challenges encountered beyond the initial creation of data analyses or projects. After completing a significant piece of work, three critical questions often emerge:
                <ul>
                <li>How can we effectively organize and categorize these analyses or projects?</li>
                <li>How can we ensure accessible and standardized documentation for everyone involved?</li>
                <li>How can we consistently execute processes or pipelines within a common, reliable environment?</li>
                </ul>
                Initially, we explored various organizational structures, such as sorting by product, owner, or project type. However, none of these approaches fully met our needs. This led us to conceive a flexible tag-based structure, enabling comprehensive searching and sorting across all relevant dimensions.
                Once a robust method for organizing projects was established, the next challenge was centralizing all associated documents, presentations, and different versions to foster shareable knowledge.
                The final crucial step was to create a unified platform where analyses and processes could be launched consistently, eliminating compatibility issues arising from differing software environments.</p>"""
    img += f'<img src="http://127.0.0.1:{webapp.constants["port"]}/{webapp.project_folder}static/img/description2.png" style="width:100%;"><br>'
    img += """<p>Consequently, we decided to create a user-friendly Python-based tool designed to perform four primary functions:
            <ul>
            <li>The first and core functionality is the **Catalog**: it collects all available analyses and projects with their comprehensive information and documentation, automatically extracting valuable details such as queries, technical requirements, and other relevant metadata.</li>
            <li>The second is **Data Exploration & Storage Tools**, which allows users to perform exploratory analyses directly within a specified saved data environment and save the results back into that same environment.</li>
            <li>Next, we have the **Execution Engine** functionality. This enables the consistent launching of analyses that produce physical outputs, such as reports or data extractions, and also facilitates the execution of complex workflows using existing API integrations.</li>
            <li>The last, but not least, is the **Analysis Shareability** functionality. This allows users to easily share their generated analyses, reports, or data extractions with internal stakeholders via integrated communication channels, and also enables the tracking of consumption and feedback on shared outputs.</li>
            </ul>"""
    img += f'<img src="http://127.0.0.1:{webapp.constants["port"]}/{webapp.project_folder}static/img/description3.png" style="width:100%;"><br></strong></div>'
    return render_template('index.html',
                           title=webapp.environments_info['title'],
                           intro_title = img,
                           intro=False,
                           head=html_part['head'],
                           top_container=html_part['top_container'], port=webapp.constants["port"],
                           project_folder=webapp.project_folder,
                           sidebar_menu=html_part['sidebar_menu'])



@app.route("/list_of_data/")
def list_of_data():
    """
    First page
    """



    html_part = webapp.substitute_html(port=webapp.constants["port"], project_folder=webapp.project_folder)
    return render_template('data_upload.html',
                           title=webapp.environments_info['title'],
                           intro=webapp.environments_info['intro'],
                           links=webapp.environments_info['links'],
                           top_container=html_part['top_container'], port=webapp.constants["port"],
                           project_folder=webapp.project_folder,
                           sidebar_menu=html_part['sidebar_menu'],
                           head=html_part['head'])

@app.route("/upload_data/")
def upload_data_form():
    """
    First page
    """

    html_part = webapp.substitute_html(port=webapp.constants["port"], project_folder=webapp.project_folder)
    return render_template('data_upload.html',
                           title=webapp.environments_info['title'],
                           intro=webapp.environments_info['intro'],
                           links=webapp.environments_info['links'],
                           top_container=html_part['top_container'], port=webapp.constants["port"],
                           project_folder=webapp.project_folder,
                           sidebar_menu=html_part['sidebar_menu'],
                           head=html_part['head'])
@app.route("/upload_data_file/", methods=['POST'])
def upload_data():
    """
    First page
    """
    webapp.upload_text_files(request)
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
@app.route("/all_data/")
def all_data():
    """
    First page
    """
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

@app.route("/open_data", methods=['GET'])
def open_data():
    """
    First page
    """
    name = request.args['name']
    output_query = f'select * from {name}'
    df = webapp.sql(output_query)
    columns = df.columns
    message = ''
    if len(df) > 2000:
        df = df.head()
        message += '<br>The result is too big to show on the page'
    html_part = webapp.substitute_html(port=webapp.constants["port"], project_folder=webapp.project_folder)
    return render_template('query_results.html',
                           message=message,
                           title=webapp.environments_info['title'],
                           intro=webapp.environments_info['intro'],
                           links=webapp.environments_info['links'],
                           top_container=html_part['top_container'], port=webapp.constants["port"],
                           sidebar_menu=html_part['sidebar_menu'],
                           head=html_part['head'],
                           show_res= 'block', project_folder=webapp.project_folder,
                           query = output_query,
                           colonne = columns,
                           df = df)


@app.route("/rawgraphs")
def rawgraphs_fun():
    """
    First page
    """
    html_part = webapp.substitute_html(port=webapp.constants["port"], project_folder=webapp.project_folder)

    return render_template('RAWGraphs.html',
                           title=webapp.environments_info['title'],
                           head=html_part['head'],
                           input_data='',
                           top_container=html_part['top_container'], port=webapp.constants["port"],
                           project_folder=webapp.project_folder,
                           sidebar_menu=html_part['sidebar_menu'])


@app.route("/query_runner/")
def query_runner():
    """
    First page
    """
    html_part = webapp.substitute_html(port=webapp.constants["port"], project_folder=webapp.project_folder)
    return render_template('query_results.html',
                           title=webapp.environments_info['title'],
                           intro=webapp.environments_info['intro'],
                           links=webapp.environments_info['links'],
                           top_container=html_part['top_container'], port=webapp.constants["port"],
                           sidebar_menu=html_part['sidebar_menu'],
                           head=html_part['head'],
                           show_res= 'none', project_folder=webapp.project_folder,
                           query = 'select * from database.table limit 10',
                           colonne = [],
                           env='',
                           df = pd.DataFrame())


@app.route("/query_results/", methods=['POST'])
def query_results():
    """
    First page
    """
    output_query = request.form['output_query'].encode().decode('utf-8', 'ignore')
    # regex = r'<span class="(.*)">(.*?)</span>'
    try:
        regex = r'<\/?span.*?>'
        output_query = re.sub(regex, r' ', output_query)
        regex = r'<\/?div.*?>'
        output_query = re.sub(regex, r' ', output_query)
        for i in ['<span class="hljs-number">', '<span class="hljs-keyword">', '<span class="hljs-operator">']:
            output_query = output_query.replace(i, '')
        for i in ['<div>', '</div>',  '</span>', '<br>', '\r']:
            output_query = output_query.replace(i, '\n')
        for i in [u'\xa0', '&nbsp;']:
            output_query = output_query.replace(i, ' ')
        cleaner = re.compile('<.*?>')
        output_query = re.sub(cleaner, '\n', output_query)
        while '    ' in output_query:
            output_query = output_query.replace('    ', '\t')
        while '  ' in output_query:
            output_query = output_query.replace('  ', ' ')
        while '\n ' in output_query:
            output_query = output_query.replace('\n ', '\n')
        while '\t ' in output_query:
            output_query = output_query.replace('\t ', '\t')
        while '\n\n' in output_query:
            output_query = output_query.replace('\n\n', '\n')
        while '\n\t\n' in output_query:
            output_query = output_query.replace('\n\t\n', '\n')
        while '\n=' in output_query or '\n =' in output_query:
            output_query = output_query.replace('\n=', '=').replace('\n =', '=')
        while '=\n' in output_query or '= \n' in output_query:
            output_query = output_query.replace('=\n', '=').replace('= \n', '=')
    except Exception:
        pass
    app.logger.info(output_query)
    df = webapp.sql(output_query)
    columns = df.columns
    message = ''
    if len(df) > 2000:
        df = df.head()
        message += '<br>The result is too big to show on the page'
    html_part = webapp.substitute_html(port=webapp.constants["port"], project_folder=webapp.project_folder)
    return render_template('query_results.html',
                           message=message,
                           title=webapp.environments_info['title'],
                           intro=webapp.environments_info['intro'],
                           links=webapp.environments_info['links'],
                           top_container=html_part['top_container'], port=webapp.constants["port"],
                           sidebar_menu=html_part['sidebar_menu'],
                           head=html_part['head'],
                           show_res= 'block', project_folder=webapp.project_folder,
                           query = output_query,
                           colonne = columns,
                           df = df)


@app.route("/save_query/", methods=['POST'])
def save_query_local():
    """
    First page
    """
    output_query = request.form['output_query_to_save'].encode().decode('utf-8', 'ignore')
    title = request.form['title']
    for i in ['<span class="hljs-number">']:
        output_query = output_query.replace(i, '')
    for i in ['<div>', '</div>', '<br>', '\r']:
        output_query = output_query.replace(i, '\n')
    for i in [u'\xa0', '&nbsp;']:
        output_query = output_query.replace(i, ' ')
    cleaner = re.compile('<.*?>')
    output_query = re.sub(cleaner, '\n', output_query)
    while '\n\n' in output_query:
        output_query = output_query.replace('\n\n', '\n')
    final_query = '-- Query saved in date:' + str(datetime.datetime.now())
    final_query += '\n-- Tables used: ' + '; '.join(list(
        set([i.strip() for i in re.findall(r'(?<=from)(.*?)(?=\n|as|--|where|limit|group|order)', output_query.lower())
             if '.' in i])))
    final_query += '\n' + output_query
    save_queries_path = webapp.save_queries_path
    with open(f"{save_queries_path}/{title}.sql", 'w') as f:
        f.write(final_query)
    df = webapp.sql(output_query)
    columns = df.columns
    message = f'<br>Saved query: {save_queries_path}/{title}.sql'
    if len(df) > 2000:
        df = df.head()
        message += '<br>The result is too big to show on the page'
    html_part = webapp.substitute_html(port = webapp.constants["port"], project_folder=webapp.project_folder)
    return render_template('query_results.html',
                           message= message,
                           title = webapp.environments_info['title'],
                           intro = webapp.environments_info['intro'],
                           links = webapp.environments_info['links'],
                           top_container = html_part['top_container'], port=webapp.constants["port"],
                           sidebar_menu = html_part['sidebar_menu'],
                           head = html_part['head'],
                           show_res = 'block', project_folder=webapp.project_folder,
                           query = output_query,
                           colonne = columns,
                           df = df)



@app.route("/graph_analysis/", methods=['POST'])
def graph_analysis_load():
    """
    First page
    """

    html_part = webapp.substitute_html(port=webapp.constants["port"], project_folder=webapp.project_folder)
    output_query = request.form['output_query_to_rawgraph'].encode().decode('utf-8', 'ignore')
    for i in ['<span class="hljs-number">']:
        output_query = output_query.replace(i, '')
    for i in ['<div>', '</div>', '<br>', '\r']:
        output_query = output_query.replace(i, '\n')
    for i in [u'\xa0', '&nbsp;']:
        output_query = output_query.replace(i, ' ')
    cleaner = re.compile('<.*?>')
    output_query = re.sub(cleaner, '\n', output_query)
    while '\n\n' in output_query:
        output_query = output_query.replace('\n\n', '\n')
    df = webapp.sql(output_query)
    df_input = df.to_csv(index=False)
    df_input = df_input.replace('\r', '').replace('\t', '').replace('\n', '\\n')
    return render_template('RAWGraphs.html',
                           title=webapp.environments_info['title'],
                           head=html_part['head'],
                           input_data=df_input,
                           top_container=html_part['top_container'], port=webapp.constants["port"],
                           project_folder=webapp.project_folder,
                           sidebar_menu=html_part['sidebar_menu'])



@app.route("/tmp_table/", methods=['POST'])
def tmp_table_load():
    """
    First page
    """
    output_query = request.form['output_query_to_save_data'].encode().decode('utf-8', 'ignore')
    name_table = request.form['name_table']
    for i in ['<span class="hljs-number">']:
        output_query = output_query.replace(i, '')
    for i in ['<div>', '</div>', '<br>', '\r']:
        output_query = output_query.replace(i, '\n')
    for i in [u'\xa0', '&nbsp;']:
        output_query = output_query.replace(i, ' ')
    cleaner = re.compile('<.*?>')
    output_query = re.sub(cleaner, '\n', output_query)
    while '\n\n' in output_query:
        output_query = output_query.replace('\n\n', '\n')
    df = webapp.sql(output_query)
    df.to_csv(f'{webapp.save_data_path}/name_table.csv', index=False)
    columns = df.columns
    message = f'<br>Created table: {name_table}'
    if len(df) > 2000:
        df = df.head()
        message += '<br>The result is too big to show on the page'
    html_part = webapp.substitute_html(port = webapp.constants["port"], project_folder=webapp.project_folder)
    return render_template('query_results.html',
                           message= message,
                           title = webapp.environments_info['title'],
                           intro = webapp.environments_info['intro'],
                           links = webapp.environments_info['links'],
                           top_container = html_part['top_container'], port=webapp.constants["port"],
                           sidebar_menu = html_part['sidebar_menu'],
                           head = html_part['head'],
                           show_res = 'block', project_folder=webapp.project_folder,
                           query = output_query,
                           colonne = columns,
                           df = df)


@app.route("/load_analysis_internal/", methods=['GET'])
def load_analysis_internal():
    """
    First page
    """
    if 'name' not in request.args:
        new_analysis = True
        analysis = {}
        analysis['links'] = {}
        analysis['inputs'] = {}
        analysis['slides'] = {}
    else:
        new_analysis = False
        name = request.args['name'].replace('512', ' ')
        analysis = webapp.read_single_analysis(webapp.extract_main_folder(), name)
        print(analysis)
    return render_template('create_analysis.html', new_analysis=new_analysis, analysis=analysis,
                           port=webapp.constants["port"], project_folder=webapp.project_folder
                           , tool_choices=webapp.tool_choices)


@app.route("/load_analysis/", methods=['GET'])
def load_analysis():
    """
    First page
    """
    name = '' if 'name' not in request.args else f"?name={request.args['name']}"
    html_part = webapp.substitute_html(port=webapp.constants["port"], project_folder=webapp.project_folder)
    link = f'http://127.0.0.1:{webapp.constants["port"]}/load_analysis_internal/{name}'
    obj = ''
    title = False
    return render_template('iframetemplate.html', obj=obj, title=title, url=link, head=html_part['head'],
                           top_container=html_part['top_container'], project_folder=webapp.project_folder,
                           port=webapp.constants["port"],
                           sidebar_menu=html_part['sidebar_menu'])


@app.route("/produce_analysis/", methods=['POST'])
def produce_analysis():
    new_analysis = request.form['new_analysis']
    if new_analysis == 'new':
        error = webapp.upload_new_analysis(request)
    else:
        error = webapp.modify_analysis(request)
    if error == '':
        resp = jsonify(success = True)
        resp.status_code = 200
    else:
        resp = error
    if use_gitlab_repo:
        repo.git.add('.')
        repo.index.commit(f'Analysis tool automatic commit - {username}')
        origin = repo.remote(name = 'origin')
        origin.push()
        # return resp
    return render_template('process_complete.html' if error == '' else 'internal_error.html')



@app.route("/todo")
def todo():
    """
    Notes page
    """
    html_part = webapp.substitute_html(port=webapp.constants["port"], project_folder=webapp.project_folder)
    return render_template('todopage.html', head=html_part['head'], project_folder=webapp.project_folder,
                           top_container=html_part['top_container'],
                           port=webapp.constants["port"], sidebar_menu=html_part['sidebar_menu'])


@app.route("/analysis")
def analysis_page():
    """
    Analysis/Structured_Analyses page
    """
    html_part = webapp.substitute_html(port=webapp.constants["port"], project_folder=webapp.project_folder)
    analysis = webapp.read_multiple_analysis()
    return render_template('analysis.html', port=webapp.constants["port"], title='Analyses', analysis=analysis,
                           head=html_part['head'], top_container=html_part['top_container'],
                           project_folder=webapp.project_folder,
                           sidebar_menu=html_part['sidebar_menu'], tool_choices=webapp.tool_choices)


@app.route("/show_site/", methods=['GET'])
def show_sitefun():
    """
    Show sites page

    """

    html_part = webapp.substitute_html(port=webapp.constants["port"], project_folder=webapp.project_folder)
    link = request.args['url']
    obj = ''
    title = f'<a href="{link}">Go direct to the link</a>'
    return render_template('iframetemplate.html', obj=obj, title=title, url=link, head=html_part['head'],
                           top_container=html_part['top_container'], project_folder=webapp.project_folder,
                           port=webapp.constants["port"],
                           sidebar_menu=html_part['sidebar_menu'])


@app.route("/license/")
def license_page():
    """
    Show sites page

    """

    html_part = webapp.substitute_html(port=webapp.constants["port"], project_folder=webapp.project_folder)
    link = 'https://github.com/GiacomoSaccaggi/ProjectCompass'
    obj = ''
    title = f'<a href="{link}">Go direct to the link</a>'
    return render_template('iframetemplate.html', obj=obj, title=title, url=link, head=html_part['head'],
                           top_container=html_part['top_container'], project_folder=webapp.project_folder,
                           port=webapp.constants["port"],
                           sidebar_menu=html_part['sidebar_menu'])


@app.route("/documentation/")
def documentation():
    """
    Show sites page

    """

    html_part = webapp.substitute_html(port=webapp.constants["port"], project_folder=webapp.project_folder)
    link = 'https://github.com/GiacomoSaccaggi/ProjectCompass'
    obj = ''
    title = f'<a href="{link}">Go direct to the link</a>'
    return render_template('iframetemplate.html', obj=obj, title=title, url=link, head=html_part['head'],
                           top_container=html_part['top_container'], project_folder=webapp.project_folder,
                           port=webapp.constants["port"],
                           sidebar_menu=html_part['sidebar_menu'])


@app.route("/iframe/", methods=['GET'])
def iframe_page():
    """
    Analysis/Structured_Analyses page

    """
    name = request.args['name'].replace('512', ' ')
    analysis = webapp.read_single_analysis(webapp.extract_main_folder(), name)
    if 'version' not in request.args.keys():
        if '<script' in analysis['dashboard link']:
            obj = analysis['dashboard link']
            url = ''
        else:
            obj = ''
            url = analysis['dashboard link']
    else:
        version = request.args['version'].replace('512', ' ')
        if '<script' in analysis['versions_dashboard'][version]:
            obj = analysis['versions_dashboard'][version]
            url = ''
        else:
            obj = ''
            url = analysis['versions_dashboard'][version]
    html_part = webapp.substitute_html(port=webapp.constants["port"], project_folder=webapp.project_folder)
    title = f'<a href="{url}">{name}</a>' if obj == '' else name
    return render_template('iframetemplate.html', obj=obj, title=title, url=url, head=html_part['head'],
                           top_container=html_part['top_container'], project_folder=webapp.project_folder,
                           port=webapp.constants["port"],
                           sidebar_menu=html_part['sidebar_menu'])

@app.route("/physical_output/", methods=['GET'])
def physical_output_page():
    """
    Analysis/Structured_Analyses page

    """
    name = request.args['name'].replace('512', ' ')
    analysis = webapp.read_single_analysis(webapp.extract_main_folder(), name)
    if 'version' not in request.args.keys():
        if '.html' in analysis['physical_output']:
            obj = ''
            url = f'http://127.0.0.1:{webapp.constants["port"]}/'+webapp.project_folder+analysis['physical_output'].replace(' ', '%20')
            html_part = webapp.substitute_html(port=webapp.constants["port"], project_folder=webapp.project_folder)
            title = f'<a href="{url}">{name}</a>' if obj == '' else name
            return render_template('iframetemplate.html', obj=obj, title=title, url=url, head=html_part['head'],
                                   top_container=html_part['top_container'], project_folder=webapp.project_folder,
                                   port=webapp.constants["port"],
                                   sidebar_menu=html_part['sidebar_menu'])
        else:
            return send_file(f"{webapp.dir_path}/{analysis['physical_output']}")
    else:
        version = request.args['version'].replace('512', ' ')
        if '.html' in analysis['versions_output'][version]:
            obj = ''
            url = '../'+webapp.project_folder+analysis['versions_output'][version].replace(' ', '%20')
            html_part = webapp.substitute_html(port=webapp.constants["port"], project_folder=webapp.project_folder)
            title = f'<a href="{url}">{name}</a>' if obj == '' else name
            return render_template('iframetemplate.html', obj=obj, title=title, url=url, head=html_part['head'],
                                   top_container=html_part['top_container'], project_folder=webapp.project_folder,
                                   port=webapp.constants["port"],
                                   sidebar_menu=html_part['sidebar_menu'])
        else:
            return send_file(f"{webapp.dir_path}/{analysis['versions_output'][version]}")


@app.route("/delete_version/", methods=['GET'])
def delete_version_page():
    """
    Analysis/Structured_Analyses page

    """
    name = request.args['name'].replace('512', ' ')
    version = request.args['version'].replace('512', ' ')
    category = request.args['category']
    analysis = webapp.read_single_analysis(webapp.extract_main_folder(), name)
    if category == 'output':
        os.remove(f"{webapp.dir_path}/{analysis['versions_output'][version]}")
    else:
        with open(f"{analysis.save_folder_path}/{name}/output_versions.yaml", "w") as f:
            for k, v in analysis['versions_dashboard'].items():
                if k != version:
                    f.write(f'{k}: "{v}"\n')
    analysis = webapp.read_single_analysis(webapp.extract_main_folder(), name)
    html_part = webapp.substitute_html(port=webapp.constants["port"], project_folder=webapp.project_folder)
    return render_template('versions_single_analysis.html', values=analysis, nome= name, head=html_part['head'],
                           top_container=html_part['top_container'], project_folder=webapp.project_folder,
                           port=webapp.constants["port"],
                           sidebar_menu=html_part['sidebar_menu'])

@app.route("/add_version/", methods=['POST'])
def add_version_page():
    """
    Analysis/Structured_Analyses page

    """
    name = request.form['name'].replace('512', ' ')
    category = request.form['category']
    if category == 'output':
        file_name = request.files['output_file'].filename
        request.files['output_file'].save(f"{webapp.save_folder_path}/{name}/physical_output/{file_name}")
    else:
        new_name_link = request.form['new_name_link']
        new_link_dashboard = request.form['new_link_dashboard']
        with open(f"{webapp.save_folder_path}/{name}/output_versions.yaml", 'r') as file:
            try:
                versions = yaml.safe_load(file)
            except yaml.YAMLError as exc:
                print(exc)
        versions[new_name_link] = new_link_dashboard
        with open(f"{webapp.save_folder_path}/{name}/output_versions.yaml", "w") as f:
            for k, v in versions.items():
                f.write(f'{k}: "{v}"\n')
    analysis = webapp.read_single_analysis(webapp.extract_main_folder(), name)
    html_part = webapp.substitute_html(port=webapp.constants["port"], project_folder=webapp.project_folder)
    return render_template('versions_single_analysis.html', values=analysis, nome= name, head=html_part['head'],
                           top_container=html_part['top_container'], project_folder=webapp.project_folder,
                           port=webapp.constants["port"],
                           sidebar_menu=html_part['sidebar_menu'])


@app.route("/open_version/", methods=['GET'])
def version_page():
    """
    Analysis/Structured_Analyses page

    """
    name = request.args['name'].replace('512', ' ')
    analysis = webapp.read_single_analysis(webapp.extract_main_folder(), name)
    print(analysis)
    html_part = webapp.substitute_html(port=webapp.constants["port"], project_folder=webapp.project_folder)
    return render_template('versions_single_analysis.html', values=analysis, nome= name, head=html_part['head'],
                           top_container=html_part['top_container'], project_folder=webapp.project_folder,
                           port=webapp.constants["port"],
                           sidebar_menu=html_part['sidebar_menu'])


@app.route("/open_analysis/", methods=['GET'])
def open_analysis_page():
    """
    Analysis/Structured_Analyses page

    """
    name = request.args['name'].replace('512', ' ')
    locally = False
    if locally:
        error = ""
        try:
            # windows
            subprocess.run(f'explorer "{webapp.extract_main_folder()}/{name}"')
            # subprocess.run('msg %username% Open in explorer')
        except Exception as e:
            error += f'Windows open folder error:\n{e}'
            try:
                # OSX
                subprocess.Popen(['xdg-open', f"{webapp.extract_main_folder()}/{name}"])
                # subprocess.run(f"notify-send 'Done' 'Open in explorer'")
            except Exception as e:
                error += f'Windows open folder error:\n{e}'
                print(error)
    else:
        for file in os.listdir(f'{webapp.template_folder}/tmp'):
            last_mod = datetime.datetime.now()-datetime.datetime.fromtimestamp(os.path.getmtime(f'{webapp.template_folder}/tmp/{file}'))
            if last_mod > datetime.timedelta(days=2):
                os.remove(f'{webapp.template_folder}/tmp/{file}')
        source = f'{webapp.extract_main_folder()}/{name}'
        filename = name+'export_{:%Y-%m-%d}'.format(datetime.datetime.now())

        webapp.make_archive(source, f'{webapp.template_folder}/tmp/{filename}.zip')


    return redirect(url_for('analysis_page')) if locally else send_file(f'{webapp.template_folder}/tmp/{filename}.zip')



@app.route("/delete_analysis/", methods=['GET'])
def delete_analysis_page():
    """
    Analysis/Structured_Analyses page

    """
    name = request.args['name'].replace('512', ' ')
    try:
        os.rmdir(f"{webapp.extract_main_folder()}/{name}")
    except:
        shutil.rmtree(f"{webapp.extract_main_folder()}/{name}", ignore_errors = True)
    if use_gitlab_repo:
        try:
            os.remove(f"{dir_path}Analyses/.git/index.lock")
        except Exception:
            pass
        try:
            os.remove(f"{dir_path}Analyses/.git/COMMIT_EDITMSG")
        except Exception:
            pass
        repo.git.add('.')
        repo.index.commit(f'Analysis tool automatic commit - {username}')
        origin = repo.remote(name = 'origin')
        origin.push()
        app.logger.debug('Git add commit and push only for Post Requests')


    html_part = webapp.substitute_html(port=webapp.constants["port"], project_folder=webapp.project_folder)
    analysis = webapp.read_multiple_analysis()
    return render_template('analysis.html', port=webapp.constants["port"], title='Analyses', analysis=analysis,
                           head=html_part['head'], top_container=html_part['top_container'],
                           project_folder=webapp.project_folder,
                           sidebar_menu=html_part['sidebar_menu'], tool_choices=webapp.tool_choices)



@app.route("/loading/")
def loader():
    html_part = webapp.substitute_html(port=webapp.constants["port"], project_folder=webapp.project_folder)
    return render_template('loader.html', head=html_part['head'],
                           top_container=html_part['top_container'], project_folder=webapp.project_folder,
                           port=webapp.constants["port"],
                           sidebar_menu=html_part['sidebar_menu'])



@app.route("/create_investigations/", methods=['GET'])
def create_investigations_page():
    """
    Analysis/Investigations page

    """
    name_r = request.args['name'].replace('512', ' ')
    analysis = webapp.read_single_analysis(webapp.extract_main_folder(), name_r)
    input_form = [f'<input type="hidden" name="name_static_hidden" value="{name_r}">']
    for name, input_info in analysis['structured_metadata']['input'].items():
        if input_info['HTML_input_type'] == 'text' or input_info['HTML_input_type'] == 'color' \
                or input_info['HTML_input_type'] == 'email' or input_info['HTML_input_type'] == 'number' \
                or input_info['HTML_input_type'] == 'password' or input_info['HTML_input_type'] == 'tel' \
                or input_info['HTML_input_type'] == 'url':
            input_form.append(f'<label for="{name}">{name.upper()}:</label>'
                              f'<input type="{input_info["HTML_input_type"]}" name="{name}" class="w3-input '
                              f'w3-padding-16 w3-border" placeholder="{name}" required>')
        elif input_info['HTML_input_type'] == 'datalist':
            input_form.append(f'<label for="{name}">{name.upper()}:</label><input list="{name}s" name="{name}" '
                              f'id="{name}" class="w3-input w3-border" placeholder="{name}" '
                              f'required><datalist id="{name}s">' +
                              "".join(['<option value="' + l + '">' for l in input_info["list"]]) +
                              f'</datalist>')
        elif input_info['HTML_input_type'] == 'month' or input_info['HTML_input_type'] == 'datetime-local' \
                or input_info['HTML_input_type'] == 'date' or input_info['HTML_input_type'] == 'time' \
                or input_info['HTML_input_type'] == 'week' or input_info['HTML_input_type'] == 'time':
            input_form.append(f'<label for="{name}">{name.upper()}:</label>'
                              f'<input type="{input_info["HTML_input_type"]}" id="{name}" name="{name}" '
                              f'class="w3-input w3-border" required>')
        elif input_info['HTML_input_type'] == 'radio':
            input_form.append(f'<label for="{name}">{name.upper()}:</label><ul>' +
                              "".join([f'<input type="{input_info["HTML_input_type"]}" name="{name}" value="{l}"> {l}<br>'
                                       for l in input_info["list"]]) +
                              f'</ul>')
    html_part = webapp.substitute_html(port=webapp.constants["port"], project_folder=webapp.project_folder)
    return render_template('investigations.html', input_form=input_form, title=name_r,
                           head=html_part['head'], top_container=html_part['top_container'],
                           sidebar_menu=html_part['sidebar_menu'], port=webapp.constants["port"], project_folder=webapp.project_folder)


@app.route("/run_investigation/", methods=['POST'])
def result_investigation_page():
    """
    Analysis/Investigations page

    """
    name_r = request.form['name_static_hidden']
    main_folder = webapp.extract_main_folder()
    analysis = webapp.read_single_analysis(main_folder, name_r)
    if analysis['structured_analysis'] != 'n':
        app.logger.warning('Running locally')
        tmp_paths_original = [i for i in sys.path if True not in [e in i for e in webapp.environments]]
        tmp_paths = tmp_paths_original
        tmp_paths.append(f"{main_folder}/{name_r}/analysis")
        output_folder = f"{main_folder}/{name_r}/physical_output/"
        folder = f"{main_folder}/{name_r}/analysis/"
        id = '{:%Y_%m_%d_%H_%M_%S}_'.format(datetime.datetime.now())
        sys.path.clear()
        sys.path = tmp_paths
        # inizialize logger
        file_logging = f'{main_folder.replace("Analyses", "Templates")}/static/logs.log'
        logger = logging.getLogger('Analysis tool loading logs')
        logger.setLevel(logging.INFO)
        formatter = logging.Formatter('+++ %(asctime)s - %(name)s (%(levelname)s) <br><b>%(message)s</b><br><br>')
        stdout_handler = logging.StreamHandler(sys.stdout)
        stdout_handler.setLevel(logging.DEBUG)
        stdout_handler.setFormatter(formatter)
        file_handler = logging.FileHandler(file_logging)
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        logger.addHandler(stdout_handler)
        logger.info('Start structured analysis')

        from structured_analysis_main import structured_analysis
        output_file = structured_analysis(folder=folder, output_folder=output_folder, id=id, logger=logger, **dict(request.form))

        logger.removeHandler(file_handler)
        logger.handlers.clear()
        file_handler.close()
        os.remove(file_logging)
        if '.html' in output_file:
            obj = ''
            url = f'http://127.0.0.1:{webapp.constants["port"]}/'+webapp.project_folder+output_file.replace(webapp.dir_path, '').replace(' ', '%20')
            html_part = webapp.substitute_html(port = webapp.constants["port"], project_folder = webapp.project_folder)
            title = f'<a href="{url}">{name_r}</a>' if obj == '' else name_r
            sys.path.clear()
            sys.path = tmp_paths_original
            return render_template('iframetemplate.html', obj = obj, title = title, url = url, head = html_part['head'],
                                   top_container = html_part['top_container'], project_folder = webapp.project_folder,
                                   port = webapp.constants["port"],
                                   sidebar_menu = html_part['sidebar_menu'])
        elif '.' in output_file:
            sys.path.clear()
            sys.path = tmp_paths_original
            return send_file(output_file)
        else:
            url = f"{analysis['output']['file']}"
            obj = f'{webapp.constants["logo_svg"]}<br><br><br><center><h1><a href="{url}" style="background-color: red;color: white;padding: 1em 1.5em;text-decoration: none;text-transform: uppercase;">Download the result</a></h1></center><br><br><br>'

            html_part = webapp.substitute_html(port=webapp.constants["port"], project_folder=webapp.project_folder)
            title = f'<a href="{url}">{name_r}</a>'
            sys.path.clear()
            sys.path = tmp_paths_original
            return render_template('iframetemplate.html', obj=obj,
                                   title=title, url=url, head=html_part['head'],
                                   top_container=html_part['top_container'],
                                   sidebar_menu=html_part['sidebar_menu'])
    else:
        html_part = webapp.substitute_html(port=webapp.constants["port"], project_folder=webapp.project_folder)
        return render_template('analysis.html', port=webapp.constants["port"], title='Analyses', analysis=analysis,
                               head=html_part['head'], top_container=html_part['top_container'],
                               project_folder=webapp.project_folder,
                               sidebar_menu=html_part['sidebar_menu'], tool_choices=webapp.tool_choices)



@app.route("/check", methods=['GET'])
def check_function():
    """
    First page
    """
    resp = jsonify(success = True)
    resp.status_code = 200
    return resp



@app.route("/post_repo", methods=['GET'])
def post_repo_function():
    """
    First page
    """
    if use_gitlab_repo:
        list_rm = [i for i in os.listdir(f'{dir_path}') if '~' in i]
        if len(list_rm) > 0:
            for folder in list_rm:
                try:
                    shutil.rmtree(f'{dir_path}Analyses/{folder}')
                except Exception:
                    pass
        try:
            os.remove(f"{dir_path}Analyses/.git/index.lock")
        except Exception:
            pass
        try:
            os.remove(f"{dir_path}Analyses/.git/COMMIT_EDITMSG")
        except Exception:
            pass
        repo.git.reset('--hard')
    resp = jsonify(success = True)
    resp.status_code = 200
    return resp



@app.route("/reset/")
def reset():
    session.clear()
    resp = jsonify(success = True)
    resp.status_code = 200
    return resp

@app.route("/login/", methods=['POST'])
def login_function():
    """
    First page
    """
    import os
    uname = request.form['uname']
    psw = request.form['psw']
    os.environ['uname'] = uname
    os.environ['psw'] = uname
    if uname == webapp.constants['uname'] and psw == str(webapp.constants['psw']):
        print('Authenticated')
        session['authenticated'] = True
    html_part = webapp.substitute_html(port=webapp.constants["port"], project_folder=webapp.project_folder)
    img = f'<img src="http://127.0.0.1:{webapp.constants["port"]}/{webapp.project_folder}static/img/first_page.png" style="width:100%;"><br>'
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
        if info['product'] in product_info.keys():
            product_info[info['product']] += 1
        else:
            product_info[info['product']] = 1
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
                           top_container=html_part['top_container'], port=webapp.constants["port"],
                           project_folder=webapp.project_folder,
                           sidebar_menu=html_part['sidebar_menu'])


@app.before_request
def before_request_func():
    method = request.method
    path = request.path
    # Read constants from encrypted file
    import os
    import jwt
    if not session.get('authenticated', False) and 'login' not in path:
        return render_template('login_page.html')
    if use_gitlab_repo:
        if '.' not in path and method in ["POST", "GET"] and 'login' not in path:
            list_rm = [i for i in os.listdir(f'{dir_path}') if '~' in i]
            if len(list_rm) > 0:
                for folder in list_rm:
                    shutil.rmtree(f'{dir_path}Analyses/{folder}')
            try:
                os.remove(f"{dir_path}Analyses/.git/index.lock")
            except Exception:
                pass
            try:
                os.remove(f"{dir_path}Analyses/.git/COMMIT_EDITMSG")
            except Exception:
                pass
            repo.git.reset('--hard')
            # g = git.cmd.Git(repo)
            # g.pull()
            app.logger.debug('Git reset and pull the folder')


@app.after_request
def after_request_func(response):
    method = request.method
    path = request.path

    if '.' not in path and method in ["POST"] and use_gitlab_repo:
        #repo.git.add(update=True)
        try:
            os.remove(f"{dir_path}Analyses/.git/index.lock")
        except Exception:
            pass
        try:
            os.remove(f"{dir_path}Analyses/.git/COMMIT_EDITMSG")
        except Exception:
            pass
        repo.git.add('.')
        repo.index.commit(f'Analysis tool automatic commit - {username}')
        origin = repo.remote(name='origin')
        origin.push()
        app.logger.debug('Git add commit and push only for Post Requests')
    return response



if __name__ == '__main__':
    app.run(port=webapp.constants["port"], debug='true' in str(webapp.constants["debug"]).strip().lower())


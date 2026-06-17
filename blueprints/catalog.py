import datetime
import os

import numpy as np
from flask import Blueprint, current_app, jsonify, redirect, render_template, request, send_file, url_for

from logging_config import logger

catalog_bp = Blueprint('catalog', __name__)


def get_webapp():
    return current_app.config['WEBAPP']


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
    return render_template('index.html',
                           title=webapp.environments_info['title'],
                           intro_title='',
                           intro=False,
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


@catalog_bp.route('/physical_output/', methods=['GET'])
def physical_output():
    webapp = get_webapp()
    name = request.args['name'].replace('512', ' ')
    analysis = webapp.read_single_analysis(webapp.extract_main_folder(), name)
    html_part = webapp.substitute_html(port=webapp.constants["port"], project_folder=webapp.project_folder)
    if 'version' not in request.args:
        output_path = analysis.get('physical_output', '')
        if '.html' in output_path:
            url = f'/static/../{output_path}'
            title = f'<a href="{url}">{name}</a>'
            return render_template('iframetemplate.html', obj='', title=title, url=url, head=html_part['head'],
                                   top_container=html_part['top_container'], project_folder=webapp.project_folder,
                                   port=webapp.constants["port"], sidebar_menu=html_part['sidebar_menu'])
        elif output_path:
            return send_file(os.path.join(webapp.dir_path, output_path))
    return redirect(url_for('catalog.analysis_page'))


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
        html_type = 'date' if field_type == 'date' else 'text'
        input_form.append(
            f'<label><b>{desc}</b></label><br>'
            f'<input type="{html_type}" name="{field_name}" value="{default}" '
            f'style="padding:6px 12px;margin:4px;border:2px solid #00889B;border-radius:4px;width:90%"><br><br>'
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
        logger.info(f"Structured analysis '{name}' completed successfully")
        return redirect(f"/open_version/?name={name.replace(' ', '512')}")
    except Exception as e:
        logger.error(f"Structured analysis error: {e}")
        return f"<h3>Analysis Error</h3><pre>{e}</pre><br><a href='/analysis'>Back to catalog</a>", 500

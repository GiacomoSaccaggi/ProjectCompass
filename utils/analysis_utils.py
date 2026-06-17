

# Import Pkg
import datetime
import os
import re
import shutil

import yaml


class AnalysisUtils:
    def __init__(self, dir_path, **kwargs):
        self.analysis_folder = 'Analyses'
        self.save_folder_path = f'{dir_path}{self.analysis_folder}'
        os.makedirs(self.save_folder_path, exist_ok=True)
        super().__init__(dir_path=dir_path, **kwargs)

    def extract_main_folder(self):
        return self.save_folder_path

    @staticmethod
    def make_archive(source, destination):
        base = os.path.basename(destination)
        name = base.split('.')[0]
        format = base.split('.')[1]
        archive_from = os.path.dirname(source)
        archive_to = os.path.basename(source.strip(os.sep))
        shutil.make_archive(name, format, archive_from, archive_to)
        shutil.move(f'{name}.{format}', destination)


    def read_single_analysis(self, main_folder, folder):
        analysis = {}
        with open(f"{main_folder}/{folder}/metadata.yaml") as file:
            try:
                analysis = yaml.safe_load(file)
                analysis['start_date'] = analysis['start_date'].strftime("%Y-%m-%d")
                analysis['last_modified'] = datetime.datetime.fromtimestamp(
                    os.path.getmtime(f"{main_folder}/{folder}")).strftime("%Y-%m-%d")
                analysis['gitlab_link_viz'] = '<br><h6><b><i class="fa fa-gitlab"></i>    <a href="' + analysis[
                    'gitlab'] + '" target="_blank">Gitlab repository</a></b></h6>' if analysis['gitlab'] != '' and \
                                                                                      analysis[
                                                                                          'gitlab'] is not None else ''
                gdrive = analysis['gdrive']
                analysis['gdrive_link_viz'] = (
                    '<br><h6><b><i class="fa fa-google"></i>    <a href="'
                    + gdrive + '" target="_blank">Google drive workspace</a></b></h6>'
                    if gdrive and gdrive != '' else ''
                )
                analysis['inputs'] = {} if analysis['inputs'] is None else analysis['inputs']
                analysis['inline_inputs'] = ';'.join(
                    [f"{k}:{v['type']}={v['default']}" for k, v in analysis['inputs'].items()])
                analysis['links'] = {} if analysis['links'] is None else analysis['links']
                analysis['inline_links'] = ';'.join([k + '===' + v for k, v in analysis['links'].items()])
                analysis['embedded'] = 'y' if '<' in analysis['dashboard link'] else 'n'
                analysis['folder'] = f"{main_folder}/{folder}"
                for k, v in analysis.items():
                    if v is None:
                        analysis[k] = ""
            except yaml.YAMLError as exc:
                print(exc)
        analysis['versions_dashboard'] = {}
        with open(f"{main_folder}/{folder}/output_versions.yaml") as file:
            try:
                verions = yaml.safe_load(file)
            except yaml.YAMLError as exc:
                print(exc)
        for k, v in verions.items():
            if ('<' in analysis['dashboard link']) == ('<' in v):
                analysis['versions_dashboard'][k] = v
        analysis['versions_output'] = {}
        analysis['physical_output'] = ''
        try:
            for f in os.listdir(f"{main_folder}/{folder}/physical_output"):
                if f == 'main' and len([i for i in os.listdir(f"{main_folder}/{folder}/physical_output/main") if
                                        '.ini' not in i]) > 0:
                    analysis['physical_output'] = f'{self.analysis_folder}/{folder}/physical_output/main/' + \
                                                  [i for i in
                                                   os.listdir(f"{main_folder}/{folder}/physical_output/main") if
                                                   '.ini' not in i][0]
                    # versions_output main path removed for brevity
                elif '.' in f and '.ini' not in f:
                    analysis['versions_output'][
                        f.split('.')[0]] = f'{self.analysis_folder}/{folder}/physical_output/' + f
        except Exception:
            pass
        if 'analysis' in os.listdir(f"{main_folder}/{folder}") and 'structured_analysis_main.py' in os.listdir(
                f"{main_folder}/{folder}/analysis") and 'metadata_automatic_report.yaml' in os.listdir(
                f"{main_folder}/{folder}/analysis"):
            analysis['structured_analysis'] = 'y'
            with open(f"{main_folder}/{folder}/analysis/metadata_automatic_report.yaml") as file:
                try:
                    metadata_struct = yaml.safe_load(file)
                except yaml.YAMLError as exc:
                    print(exc)
            analysis['structured_metadata'] = metadata_struct
        else:
            analysis['structured_analysis'] = 'n'
            analysis['structured_metadata'] = {}
        try:
            with open(f"{main_folder}/{folder}/readme.md", 'w') as file:
                file.write(f"# {analysis['title']}\n")
                file.write(f"### Author: {analysis['owner']} ({analysis['collaborators']})\n")
                file.write(f"### Product: {analysis['product']} ({analysis['countries']})\n")
                file.write("## Description\n")
                file.write(f"> {analysis['description']}\n")
                file.write("## Output description:\n")
                file.write(f"> {analysis['output description']}\n")
        except Exception:
            pass
        return analysis

    def read_multiple_analysis(self):
        main_folder = self.extract_main_folder()

        analyses = {i: {} for i in os.listdir(main_folder) if '.' not in i and '~' not in i}
        for folder in analyses.keys():
            analyses[folder] = self.read_single_analysis(main_folder, folder)
        return analyses

    def produce_readme(self):
        main_folder = self.extract_main_folder()

        analyses = {i: {} for i in os.listdir(main_folder) if '.' not in i and '~' not in i}
        for folder in analyses.keys():
            analyses[folder] = self.read_single_analysis(main_folder, folder)

        try:
            with open(f"{main_folder}/readme.md", 'w') as file:
                file.write("""<svg width="100" height="100" viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg">
                              <rect width="100" height="100" rx="20" fill="#F0F4F8"/>
                              <circle cx="50" cy="50" r="35" fill="#FFFFFF" stroke="#2D323A" stroke-width="4"/>
                              <path d="M50 25L65 75L50 60L35 75L50 25Z" fill="#4DFFD6"/>
                              <path d="M50 25L65 75L50 60L35 75L50 25Z" fill-opacity="0.2" stroke="#4DFFD6" stroke-width="2"/>
                              <path d="M50 25L50 50L70 50" stroke="#2D323A" stroke-width="3" stroke-linecap="round"/>
                              <path d="M50 50L30 50L50 75" stroke="#2D323A" stroke-width="3" stroke-linecap="round"/>
                              <circle cx="50" cy="50" r="5" fill="#2D323A"/>
                              <path d="M75 50C75 63.8071 63.8071 75 50 75C36.1929 75 25 63.8071 25 50C25 36.1929 36.1929 25 50 25" stroke="#9E9E9E" stroke-width="2" stroke-dasharray="2 4"/>
                              </svg>\n\n\n""")
                file.write("# ProjectCompass - Analysis catalog\n")
                for _k, v in analyses.items():
                    file.write(f"### {v['product']}: {v['title']} ({v['owner']})\n")
        except Exception:
            pass
        return analyses

    def upload_new_analysis(self, request):
        error = ""
        try:
            title = request.form['title']
            description = request.form['description'].replace('\n', '\n    ')
            owner = request.form['email']
            collaborators = request.form['collaborators']
            start_date = request.form['start_date']
            product = request.form['product']
            countries = request.form['countries']
            listinputs = request.form['inputs'].split(';')
            listlinks = request.form['links'].split(';')
            gdrive = request.form['gdrive']
            gitlab = request.form['gitlab']
            dashboard = request.form['dashboard']
            output_type = request.form['output_type']
            output_description = request.form['output_description'].replace('\n', '\n    ')
            os.mkdir(f"{self.save_folder_path}/{title}")
            os.mkdir(f"{self.save_folder_path}/{title}/analysis")
            os.mkdir(f"{self.save_folder_path}/{title}/physical_output")
            os.mkdir(f"{self.save_folder_path}/{title}/physical_output/main")
            os.mkdir(f"{self.save_folder_path}/{title}/sql_extractions")
            with open(f"{self.save_folder_path}/{title}/metadata.yaml", "w") as f:
                f.write(f"title: {title}\n")
                f.write(f"start_date: {start_date}\n")
                f.write(f"description:\n    {description}\n")
                f.write(f"owner: {owner}\n")
                f.write(f"collaborators: {collaborators}\n")
                f.write(f"product: {product}\n")
                f.write(f"countries: {countries}\n")
                f.write("inputs:\n")
                if listinputs != ['']:
                    for single_input in [i for i in listinputs if i != '' and ':' in i and '=' in i]:
                        var = single_input.split(':')[0]
                        var_type, var_default = single_input.split(':')[1].split('=')
                        f.write(f"    {var}:\n")
                        f.write(f'        default: "{var_default}"\n')
                        f.write(f"        type: {var_type}\n")
                f.write("links:\n")
                if listlinks != ['']:
                    for single_link in [i for i in listlinks if i != '' and ':' in i]:
                        name, link = single_link.split("===")
                        f.write(f"    {name}: {link}\n")
                f.write(f"gitlab: {gitlab}\n")
                f.write(f"gdrive: {gdrive}\n")
                f.write(f'dashboard link: "{dashboard}"\n')
                f.write(f"output_type: {output_type}\n")
                f.write(f"output description:\n    {output_description}\n")
            with open(f"{self.save_folder_path}/{title}/output_versions.yaml", "w") as f:
                f.write(f'main version: "{dashboard}"\n')
            if request.files['output_file'].filename != '':
                file_name = request.files['output_file'].filename
                request.files['output_file'].save(f'{self.save_folder_path}/{title}/physical_output/{file_name}')
                request.files['output_file'].save(
                    f"{self.save_folder_path}/{title}/physical_output/main/{file_name}")
            files = []
            files_py = []
            files_sql = []
            for file in request.files.getlist('upload_files'):
                if '/' in file.filename and '/.' not in file.filename and isinstance(file.filename, str):
                    file_name = '/'.join(file.filename.split('/')[1:])
                    files.append(f"{self.save_folder_path}/{title}/analysis/{file_name}")
                    if '.py' == file_name[-3:] or '.ipynb' == file_name[-6:]:
                        files_py.append(f"{self.save_folder_path}/{title}/analysis/{file_name}")
                    if '.sql' == file_name[-4:]:
                        files_sql.append(f"{self.save_folder_path}/{title}/analysis/{file_name}")
                        file.save(f"{self.save_folder_path}/{title}/analysis/{file_name}")
                        file.save(f"{self.save_folder_path}/{title}/sql_extractions/{file_name.split('/')[-1]}")
                    if '/' in file_name:
                        path_subfolders = ''
                        for subfolder in file_name.split('/')[:-1]:
                            path_subfolders_ = path_subfolders
                            path_subfolders += f"/{subfolder}"
                            if subfolder not in os.listdir(
                                    f'{self.save_folder_path}/{title}/analysis{path_subfolders_}'):
                                try:
                                    os.mkdir(f"{self.save_folder_path}/{title}/analysis{path_subfolders}")
                                except Exception as e:
                                    print(e)
                                    pass
                    try:
                        file.save(f"{self.save_folder_path}/{title}/analysis/{file_name}")
                    except Exception as e:
                        print(e)
            if files_py:
                try:
                    res = os.system(f" cd {self.save_folder_path}/{title} && " +
                                    "set PYTHONPATH=analysis && " +
                                    "python -m pdoc --html --output-dir documentation analysis --force --skip-errors")
                    if res == 1:
                        os.system(f" cd {self.save_folder_path}/{title} && " +
                                  "export PYTHONPATH=analysis && " +
                                  "python -m pdoc --html --output-dir documentation analysis --force --skip-errors")
                except Exception:
                    try:
                        res = os.system(f" cd {self.save_folder_path}/{title} && " +
                                        "set PYTHONPATH=analysis && " +
                                        "python -m pdoc --output-dir documentation analysis")
                        if res == 1:
                            os.system(f" cd {self.save_folder_path}/{title} && " +
                                      "export PYTHONPATH=analysis && " +
                                      "python -m pdoc --output-dir documentation analysis")
                    except Exception:
                        os.mkdir(f"{self.save_folder_path}/{title}/documentation")
                # if files_py != []:
                requirements = []
                queries = []
                for file in files_py:
                    with open(file, encoding="utf-8") as f:
                        texts = '\n'.join(f.readlines())
                        requirements.extend([i[1] if i[0] == '' and i[1] != '' else i[0]
                                             for i in re.findall(
                                r'\s*(?:import)\s+(\w+(?:\s*,\s*\w+)*)|\s*(?:from)\s(.*)\s(?:import)\s\*',
                                texts
                            )
                                             if
                                             ',' not in i[0] and ',' not in i[1] and '_' not in i[0] and '_' not in
                                             i[1]
                                             and i[0] == i[0].lower() and i[1] == i[1].lower()
                                             ])
                        queries.extend(
                            [i.replace('$$$another_line$$$', '\n').replace('$$$tab$$$', '\n') for n, i in enumerate(
                                re.findall(r'(?<=###PARAGRAPH###)(.*?)(?=###PARAGRAPH###)',
                                           texts.replace('\n', '$$$another_line$$$').replace('\n', '$$$tab$$$')
                                           .replace('"""', ' ###PARAGRAPH### ').replace("'''", ' ###PARAGRAPH### ')
                                           )) if 'select' in i.lower() and 'from' in i.lower() and n % 2 != 1])
                with open(f"{self.save_folder_path}/{title}/requirements.txt", 'w') as f:
                    f.write('# Requirements extract automatically from analysis tool')
                    for pkg in set(requirements):
                        f.write(f'{pkg}\n')
                for n, q in enumerate(queries):
                    final_query = '-- Query generate automatically from the python scripts'
                    final_query += '\n-- Parameters: ' + '; '.join(list(set(re.findall(r'(?<=\{)(.*?)(?=\})', q))))
                    tables = [i.strip() for i in
                              re.findall(r'(?<=from)(.*?)(?=\n|as|--|where|limit|group|order)', q.lower())
                              if '.' in i]
                    final_query += '\n-- Tables used: ' + '; '.join(list(set(tables)))
                    final_query += '\n' + q
                    with open(f"{self.save_folder_path}/{title}/sql_extractions/query{n}.sql", 'w') as f:
                        f.write(final_query)
            self.produce_readme()
        except Exception as e:
            error += str(e)
            pass
        return error

    def modify_analysis(self, request):
        error = ""
        try:
            title = request.form['title']
            description = request.form['description'].replace('\n', '\n    ')
            owner = request.form['email']
            collaborators = request.form['collaborators']
            start_date = request.form['start_date']
            product = request.form['product']
            countries = request.form['countries']
            listinputs = request.form['inputs'].split(';')
            listlinks = request.form['links'].split(';')
            gdrive = request.form['gdrive']
            gitlab = request.form['gitlab']
            dashboard = request.form['dashboard']
            output_type = request.form['output_type']
            output_description = request.form['output_description'].replace('\n', '\n    ')
            with open(f"{self.save_folder_path}/{title}/metadata.yaml", "w") as f:
                f.write(f"title: {title}\n")
                f.write(f"start_date: {start_date}\n")
                f.write(f"description:\n    {description}\n")
                f.write(f"owner: {owner}\n")
                f.write(f"collaborators: {collaborators}\n")
                f.write(f"product: {product}\n")
                f.write(f"countries: {countries}\n")
                f.write("inputs:\n")
                if listinputs != ['']:
                    for single_input in [i for i in listinputs if i != '' and ':' in i and '=' in i]:
                        var = single_input.split(':')[0]
                        var_type, var_default = single_input.split(':')[1].split('=')
                        f.write(f"    {var}:\n")
                        f.write(f'        default: "{var_default}"\n')
                        f.write(f"        type: {var_type}\n")
                f.write("links:\n")
                if listlinks != ['']:
                    for single_link in [i for i in listlinks if i != '' and ':' in i]:
                        name, link = single_link.split("===")
                        f.write(f"    {name}: {link}\n")
                f.write(f"gitlab: {gitlab}\n")
                f.write(f"gdrive: {gdrive}\n")
                f.write(f'dashboard link: "{dashboard}"\n')
                f.write(f"output_type: {output_type}\n")
                f.write(f"output description:\n    {output_description}\n")
            try:
                with open(f"{self.save_folder_path}/{title}/output_versions.yaml") as file:
                    try:
                        versions = yaml.safe_load(file)
                    except yaml.YAMLError as exc:
                        print(exc)
                versions['main version'] = dashboard
                with open(f"{self.save_folder_path}/{title}/output_versions.yaml", "w") as f:
                    for k, v in versions.items():
                        f.write(f'{k}: "{v}"\n')
                if len(os.listdir(f"{self.save_folder_path}/{title}/physical_output/main/")) > 0:
                    for filename in os.listdir(f"{self.save_folder_path}/{title}/physical_output/main/"):
                        os.remove(f"{self.save_folder_path}/{title}/physical_output/main/{filename}")
                self.produce_readme()
                if request.files['output_file'].filename != '':
                    file_name = request.files['output_file'].filename
                    request.files['output_file'].save(
                        f'{self.save_folder_path}/{title}/physical_output/{file_name}')
                    request.files['output_file'].save(
                        f"{self.save_folder_path}/{title}/physical_output/main/{file_name}")
            except Exception:
                pass
        except Exception as e:
            error += str(e)
            pass
        return error

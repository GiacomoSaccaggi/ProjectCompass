

"""
░█████╗░███╗░░██╗░█████╗░██╗░░░░░██╗░░░██╗░██████╗██╗░██████╗░░░░░░██╗░░░██╗████████╗██╗██╗░░░░░░██████╗
██╔══██╗████╗░██║██╔══██╗██║░░░░░╚██╗░██╔╝██╔════╝██║██╔════╝░░░░░░██║░░░██║╚══██╔══╝██║██║░░░░░██╔════╝
███████║██╔██╗██║███████║██║░░░░░░╚████╔╝░╚█████╗░██║╚█████╗░█████╗██║░░░██║░░░██║░░░██║██║░░░░░╚█████╗░
██╔══██║██║╚████║██╔══██║██║░░░░░░░╚██╔╝░░░╚═══██╗██║░╚═══██╗╚════╝██║░░░██║░░░██║░░░██║██║░░░░░░╚═══██╗
██║░░██║██║░╚███║██║░░██║███████╗░░░██║░░░██████╔╝██║██████╔╝░░░░░░╚██████╔╝░░░██║░░░██║███████╗██████╔╝
╚═╝░░╚═╝╚═╝░░╚══╝╚═╝░░╚═╝╚══════╝░░░╚═╝░░░╚═════╝░╚═╝╚═════╝░░░░░░░░╚═════╝░░░░╚═╝░░░╚═╝╚══════╝╚═════╝░
"""

from __future__ import annotations

import base64
import datetime
import json
import os
import re
import shutil
from typing import Any

import yaml

from utils.git_utils import GitSyncUtils


class AnalysisUtils(GitSyncUtils):
    def __init__(self, dir_path, data_dir=None, **kwargs):
        base_data = data_dir or dir_path
        if not base_data.endswith('/'):
            base_data = base_data + '/'
        self.data_dir = base_data
        self.analysis_folder = 'Analyses'
        self.save_folder_path = f'{base_data}{self.analysis_folder}'
        os.makedirs(self.save_folder_path, exist_ok=True)
        super().__init__(dir_path=dir_path, data_dir=base_data, **kwargs)

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
                analysis['start_date'] = analysis['start_date'].strftime("%Y-%m-%d") if hasattr(analysis['start_date'], 'strftime') else str(analysis['start_date'])
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
                analysis['inputs'] = {} if not isinstance(analysis.get('inputs'), dict) else analysis['inputs']
                analysis['inline_inputs'] = ';'.join(
                    [f"{k}:{v['type']}={v['default']}" for k, v in analysis['inputs'].items()])
                analysis['links'] = {} if analysis['links'] is None else analysis['links']
                analysis['inline_links'] = ';'.join([k + '===' + v for k, v in analysis['links'].items()])
                analysis['embedded'] = 'y' if '<' in analysis['dashboard link'] else 'n'
                analysis['folder'] = f"{main_folder}/{folder}"
                analysis.setdefault('slides', {})
                analysis.setdefault('confluence_link_viz', '')
                for k, v in analysis.items():
                    if v is None:
                        analysis[k] = ""
            except yaml.YAMLError as exc:
                print(exc)
        analysis['versions_dashboard'] = {}
        versions_file = f"{main_folder}/{folder}/output_versions.yaml"
        verions = {}
        if os.path.exists(versions_file):
            with open(versions_file) as file:
                try:
                    verions = yaml.safe_load(file) or {}
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

        # --- compass_flow.yaml + Dockerfile → is_flow ---
        compass_flow_path = os.path.join(main_folder, folder, 'compass_flow.yaml')
        dockerfile_path = os.path.join(main_folder, folder, 'Dockerfile')
        analysis['has_dockerfile'] = os.path.isfile(dockerfile_path)
        analysis['is_flow'] = os.path.isfile(compass_flow_path) and analysis['has_dockerfile']
        analysis['flow_config'] = {}
        analysis['structured_analysis'] = 'n'
        analysis['structured_metadata'] = {}
        if os.path.isfile(compass_flow_path):
            try:
                with open(compass_flow_path, encoding='utf-8') as f_flow:
                    analysis['flow_config'] = yaml.safe_load(f_flow) or {}
            except (yaml.YAMLError, OSError):
                pass
        if analysis['is_flow']:
            analysis['structured_analysis'] = 'y'
            if isinstance(analysis['flow_config'].get('inputs'), dict):
                analysis['structured_metadata'] = {
                    'title': analysis['flow_config'].get('description', analysis.get('title', folder)),
                    'inputs': analysis['flow_config']['inputs'],
                }
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
            if self._is_git_sync_on_save_enabled():
                self.git_commit_and_push(
                    target_dir=self.save_folder_path,
                    message=f"Add analysis {title}",
                )
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
            if self._is_git_sync_on_save_enabled():
                self.git_commit_and_push(
                    target_dir=self.save_folder_path,
                    message=f"Update analysis {title}",
                )
        except Exception as e:
            error += str(e)
            pass
        return error

    @staticmethod
    def parse_flow_parameters(raw_params: str | dict[str, Any] | None) -> dict[str, Any]:
        """Parse flow parameters from a dict, JSON string, or KEY=VALUE lines."""
        if raw_params is None:
            return {}
        if isinstance(raw_params, dict):
            return dict(raw_params)
        text = str(raw_params).strip()
        if not text:
            return {}
        if text.startswith("{"):
            try:
                parsed = json.loads(text)
                if isinstance(parsed, dict):
                    return parsed
            except ValueError:
                pass
        result: dict[str, Any] = {}
        for chunk in re.split(r"[\r\n;]+", text):
            line = chunk.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, val = line.split("=", 1)
                k = key.strip()
                if ":" in k:
                    k = k.split(":", 1)[0].strip()
                v_str = val.strip()
                if k:
                    result[k] = v_str
        return result

    @staticmethod
    def parse_pip_requirements(raw_reqs: str | list[str] | None) -> list[str]:
        """Parse pip package requirements from a list or newline/comma-separated string."""
        if raw_reqs is None:
            return []
        if isinstance(raw_reqs, list):
            return [str(pkg).strip() for pkg in raw_reqs if str(pkg).strip() and not str(pkg).strip().startswith("#")]
        text = str(raw_reqs).strip()
        if not text:
            return []
        packages: list[str] = []
        for token in re.split(r"[\r\n,]+", text):
            cleaned = token.strip()
            if cleaned and not cleaned.startswith("#"):
                packages.append(cleaned)
        return packages

    @staticmethod
    def parse_env_vars(raw_env: str | dict[str, str] | None) -> dict[str, str]:
        """Parse environment variable / credential key-values from dict, JSON, or KEY=VALUE lines."""
        if raw_env is None:
            return {}
        if isinstance(raw_env, dict):
            return {str(k).strip(): str(v) for k, v in raw_env.items() if str(k).strip()}
        text = str(raw_env).strip()
        if not text:
            return {}
        if text.startswith("{"):
            try:
                parsed = json.loads(text)
                if isinstance(parsed, dict):
                    return {str(k).strip(): str(v) for k, v in parsed.items() if str(k).strip()}
            except ValueError:
                pass
        env_map: dict[str, str] = {}
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, val = stripped.split("=", 1)
            k = key.strip()
            if k:
                env_map[k] = val.strip()
        return env_map

    @staticmethod
    def parse_secret_refs(raw_refs: str | list[str] | None) -> list[str]:
        """Parse pre-existing Kubernetes Secret names from a list or comma/newline-separated string."""
        if raw_refs is None:
            return []
        items: list[str]
        if isinstance(raw_refs, list):
            items = [str(item).strip() for item in raw_refs]
        else:
            items = [token.strip() for token in re.split(r"[\r\n,]+", str(raw_refs))]
        seen: set[str] = set()
        result: list[str] = []
        for item in items:
            if item and not item.startswith("#") and item not in seen:
                seen.add(item)
                result.append(item)
        return result

    def _validate_flow_name(self, name: str) -> str:
        """Sanitize and validate a flow folder name inside Analyses/."""
        cleaned = (name or "").strip()
        if not cleaned or "/" in cleaned or "\\" in cleaned or ".." in cleaned or cleaned.startswith("."):
            raise ValueError(f"Invalid flow name: {name!r}")
        return cleaned

    def save_flow(
        self,
        name: str,
        code: str,
        description: str = "",
        parameters: str | dict[str, Any] | None = None,
        pip_requirements: str | list[str] | None = None,
        env_vars: str | dict[str, str] | None = None,
        secret_refs: str | list[str] | None = None,
        image: str | None = "",
        owner: str = "flow-author",
        user_id: int | None = None,
        version_message: str = "",
        product: str = "k0s Flow",
    ) -> dict[str, Any]:
        """Create or update a generic Python Flow inside Analyses/<name>/ and record a FlowVersion."""
        flow_name = self._validate_flow_name(name)
        flow_dir = os.path.join(self.save_folder_path, flow_name)
        analysis_subdir = os.path.join(flow_dir, "analysis")
        phys_main_dir = os.path.join(flow_dir, "physical_output", "main")
        sql_dir = os.path.join(flow_dir, "sql_extractions")

        os.makedirs(analysis_subdir, exist_ok=True)
        os.makedirs(phys_main_dir, exist_ok=True)
        os.makedirs(sql_dir, exist_ok=True)

        existing_cfg: dict[str, Any] = {}
        flow_cfg_path = os.path.join(flow_dir, "flow_config.yaml")
        if os.path.isfile(flow_cfg_path):
            try:
                with open(flow_cfg_path, encoding="utf-8") as f_existing:
                    existing_cfg = yaml.safe_load(f_existing) or {}
            except (OSError, yaml.YAMLError):
                existing_cfg = {}

        parsed_params = self.parse_flow_parameters(parameters)
        parsed_reqs = self.parse_pip_requirements(pip_requirements)
        parsed_env = self.parse_env_vars(env_vars)
        if secret_refs is None and "secret_refs" in existing_cfg:
            parsed_secret_refs = self.parse_secret_refs(existing_cfg.get("secret_refs"))
        else:
            parsed_secret_refs = self.parse_secret_refs(secret_refs)
        resolved_env_keys = (
            sorted(parsed_env.keys())
            if parsed_env
            else list(existing_cfg.get("env_keys") or [])
        )
        resolved_image = (
            (image or "").strip()
            or str(existing_cfg.get("image") or "").strip()
            or os.environ.get("K8S_DEFAULT_IMAGE", "python:3.11-slim")
        )
        today_str = datetime.date.today().strftime("%Y-%m-%d")

        script_body = code if code.endswith("\n") else f"{code}\n"
        flow_py_path = os.path.join(flow_dir, "flow.py")
        with open(flow_py_path, "w", encoding="utf-8") as f_py:
            f_py.write(script_body)

        flow_cfg = {
            "name": flow_name,
            "description": description or "Generic Python flow executed on k0s",
            "parameters": parsed_params,
            "pip_requirements": parsed_reqs,
            "env_keys": resolved_env_keys,
            "secret_refs": parsed_secret_refs,
            "image": resolved_image,
            "owner": owner,
            "updated_at": datetime.datetime.utcnow().isoformat(),
        }
        with open(flow_cfg_path, "w", encoding="utf-8") as f_cfg:
            yaml.safe_dump(flow_cfg, f_cfg, sort_keys=False)

        req_path = os.path.join(flow_dir, "requirements.txt")
        with open(req_path, "w", encoding="utf-8") as f_req:
            for pkg in parsed_reqs:
                f_req.write(f"{pkg}\n")

        inputs_meta = {
            str(k): {"default": str(v), "type": "str"}
            for k, v in parsed_params.items()
        }
        metadata_payload = {
            "title": flow_name,
            "start_date": today_str,
            "description": description or "Generic Python flow executed on k0s",
            "owner": owner,
            "collaborators": "",
            "product": product or "k0s Flow",
            "countries": "All",
            "inputs": inputs_meta,
            "links": {},
            "gitlab": "",
            "gdrive": "",
            "dashboard link": "",
            "output_type": "log",
            "output description": "Standard output/error logs captured per Kubernetes Job run",
        }
        with open(os.path.join(flow_dir, "metadata.yaml"), "w", encoding="utf-8") as f_meta:
            yaml.safe_dump(metadata_payload, f_meta, sort_keys=False)

        versions_path = os.path.join(flow_dir, "output_versions.yaml")
        if not os.path.exists(versions_path):
            with open(versions_path, "w", encoding="utf-8") as f_ver:
                f_ver.write('main version: ""\n')

        # --- Generate compass_flow.yaml + Dockerfile ---
        compass_flow_path = os.path.join(flow_dir, "compass_flow.yaml")
        compass_flow_data = {
            "description": description or "Python flow executed on k0s",
            "inputs": {
                str(k): {"type": "text", "default": str(v)}
                for k, v in parsed_params.items()
            } if parsed_params else {},
        }
        with open(compass_flow_path, "w", encoding="utf-8") as f_cf:
            yaml.safe_dump(compass_flow_data, f_cf, sort_keys=False)

        dockerfile_path = os.path.join(flow_dir, "Dockerfile")
        if not os.path.isfile(dockerfile_path):
            dockerfile_content = (
                f"FROM {resolved_image}\n"
                "WORKDIR /app\n"
                "COPY . .\n"
                "RUN if [ -s requirements.txt ]; then pip install --no-cache-dir -r requirements.txt; fi\n"
                'ENTRYPOINT ["/bin/sh", "scripts/pc_entrypoint.sh", "python", "flow.py"]\n'
            )
            with open(dockerfile_path, "w", encoding="utf-8") as f_docker:
                f_docker.write(dockerfile_content)



        self._record_flow_version(
            flow_name=flow_name,
            code=script_body,
            flow_cfg=flow_cfg,
            user_id=user_id,
            message=version_message,
        )

        if self._is_git_sync_on_save_enabled():
            self.git_commit_and_push(
                target_dir=self.save_folder_path,
                message=version_message or f"Save flow {flow_name}",
            )

        return self.read_flow(flow_name) or flow_cfg

    def _record_flow_version(
        self,
        flow_name: str,
        code: str,
        flow_cfg: dict[str, Any],
        user_id: int | None = None,
        message: str = "",
    ) -> int | None:
        """Persist an auto-incrementing FlowVersion snapshot in SQLite when an app context is active."""
        from flask import has_app_context

        if not has_app_context():
            return None

        from models import FlowVersion, db

        try:
            max_ver = (
                db.session.query(db.func.max(FlowVersion.version_num))
                .filter_by(flow_name=flow_name)
                .scalar()
                or 0
            )
            next_ver = int(max_ver) + 1
            snap = FlowVersion(
                flow_name=flow_name,
                version_num=next_ver,
                code=code,
                config_json=json.dumps(flow_cfg),
                user_id=user_id,
                message=(message or "").strip() or f"Version {next_ver}",
            )
            db.session.add(snap)
            db.session.commit()
            return next_ver
        except Exception:
            db.session.rollback()
            return None

    def read_flow_versions(self, name: str) -> list[dict[str, Any]]:
        """Return all version snapshots for a flow ordered by version_num descending."""
        try:
            flow_name = self._validate_flow_name(name)
        except ValueError:
            return []

        from flask import has_app_context

        if not has_app_context():
            return []

        from models import FlowVersion, User, db

        try:
            rows = (
                FlowVersion.query.filter_by(flow_name=flow_name)
                .order_by(FlowVersion.version_num.desc())
                .all()
            )
        except Exception:
            db.session.rollback()
            return []

        versions: list[dict[str, Any]] = []
        for row in rows:
            cfg_dict: dict[str, Any] = {}
            if row.config_json:
                try:
                    parsed = json.loads(row.config_json)
                    if isinstance(parsed, dict):
                        cfg_dict = parsed
                except ValueError:
                    cfg_dict = {}
            user_obj = db.session.get(User, row.user_id) if row.user_id else None
            username = user_obj.username if user_obj else str(cfg_dict.get("owner") or "flow-author")
            versions.append(
                {
                    "id": row.id,
                    "flow_name": row.flow_name,
                    "version_num": row.version_num,
                    "code": row.code,
                    "config_json": row.config_json,
                    "config": cfg_dict,
                    "user_id": row.user_id,
                    "username": username,
                    "created_at": row.created_at,
                    "message": row.message or "",
                }
            )
        return versions

    def restore_flow_version(
        self,
        name: str,
        version_num: int,
        user_id: int | None = None,
    ) -> dict[str, Any]:
        """Non-destructively restore a Flow to a previous version snapshot (creating a new version)."""
        flow_name = self._validate_flow_name(name)
        from models import FlowVersion

        target = FlowVersion.query.filter_by(flow_name=flow_name, version_num=int(version_num)).first()
        if target is None:
            raise ValueError(f"Version {version_num} for flow '{flow_name}' not found.")

        cfg: dict[str, Any] = {}
        if target.config_json:
            try:
                parsed = json.loads(target.config_json)
                if isinstance(parsed, dict):
                    cfg = parsed
            except ValueError:
                cfg = {}

        return self.save_flow(
            name=flow_name,
            code=target.code,
            description=str(cfg.get("description") or ""),
            parameters=cfg.get("parameters") or {},
            pip_requirements=cfg.get("pip_requirements") or [],
            secret_refs=cfg.get("secret_refs") or [],
            image=str(cfg.get("image") or ""),
            owner=str(cfg.get("owner") or "flow-author"),
            user_id=user_id,
            version_message=f"Restored from version {version_num}",
        )

    def read_flow(self, name: str) -> dict[str, Any] | None:
        """Read a Flow definition from Analyses/<name>/."""
        try:
            flow_name = self._validate_flow_name(name)
        except ValueError:
            return None

        flow_dir = os.path.join(self.save_folder_path, flow_name)
        if not os.path.isdir(flow_dir):
            return None

        flow_py_path = os.path.join(flow_dir, "flow.py")
        flow_cfg_path = os.path.join(flow_dir, "flow_config.yaml")
        compass_flow_path = os.path.join(flow_dir, "compass_flow.yaml")
        dockerfile_path = os.path.join(flow_dir, "Dockerfile")
        metadata_path = os.path.join(flow_dir, "metadata.yaml")

        code = ""
        script_candidates = [
            flow_py_path,
            os.path.join(flow_dir, "analysis", "flow_main.py"),
            os.path.join(flow_dir, "analysis", "pipeline_main.py"),
        ]
        for candidate_path in script_candidates:
            if os.path.isfile(candidate_path):
                with open(candidate_path, encoding="utf-8") as f_py:
                    code = f_py.read()
                break

        cfg: dict[str, Any] = {}
        if os.path.isfile(flow_cfg_path):
            with open(flow_cfg_path, encoding="utf-8") as f_cfg:
                try:
                    cfg = yaml.safe_load(f_cfg) or {}
                except yaml.YAMLError:
                    cfg = {}

        compass_flow: dict[str, Any] = {}
        if os.path.isfile(compass_flow_path):
            with open(compass_flow_path, encoding="utf-8") as f_cf:
                try:
                    compass_flow = yaml.safe_load(f_cf) or {}
                except yaml.YAMLError:
                    compass_flow = {}

        meta: dict[str, Any] = {}
        if os.path.isfile(metadata_path):
            with open(metadata_path, encoding="utf-8") as f_meta:
                try:
                    meta = yaml.safe_load(f_meta) or {}
                except yaml.YAMLError:
                    meta = {}

        params: dict[str, Any] = cfg.get("parameters") or {}
        if not params and isinstance(compass_flow.get("inputs"), dict):
            params = {
                str(k): (v.get("default", "") if isinstance(v, dict) else str(v))
                for k, v in compass_flow["inputs"].items()
            }
        if not params and isinstance(meta.get("inputs"), dict):
            params = {
                str(k): (v.get("default", "") if isinstance(v, dict) else str(v))
                for k, v in meta["inputs"].items()
            }

        pip_reqs: list[str] = cfg.get("pip_requirements") or []
        req_file = os.path.join(flow_dir, "requirements.txt")
        if not pip_reqs and os.path.isfile(req_file):
            with open(req_file, encoding="utf-8") as f_req:
                pip_reqs = self.parse_pip_requirements(f_req.read())

        default_image = os.environ.get("K8S_DEFAULT_IMAGE", "python:3.11-slim")
        last_mod = datetime.datetime.fromtimestamp(os.path.getmtime(flow_dir)).strftime("%Y-%m-%d %H:%M")
        secret_refs = self.parse_secret_refs(cfg.get("secret_refs"))
        versions = self.read_flow_versions(flow_name)
        latest_version_num = versions[0]["version_num"] if versions else 1
        is_flow = os.path.isfile(compass_flow_path) and os.path.isfile(dockerfile_path)

        return {
            "name": flow_name,
            "description": str(
                cfg.get("description")
                or compass_flow.get("description")
                or meta.get("description")
                or ""
            ).strip(),
            "code": code,
            "parameters": params,
            "parameters_json": json.dumps(params, indent=2),
            "pip_requirements": pip_reqs,
            "pip_requirements_text": "\n".join(pip_reqs),
            "env_keys": cfg.get("env_keys") or [],
            "secret_refs": secret_refs,
            "secret_refs_text": ", ".join(secret_refs),
            "image": str(cfg.get("image") or default_image),
            "owner": str(cfg.get("owner") or meta.get("owner") or ""),
            "version_num": latest_version_num,
            "versions": versions,
            "is_flow": is_flow,
            "has_flow_py": os.path.isfile(flow_py_path) or bool(code),
            "last_modified": last_mod,
            "folder": flow_dir,
        }

    def list_flows(self) -> list[dict[str, Any]]:
        """Return all executable Flows available in the Analyses/ directory."""
        if not os.path.isdir(self.save_folder_path):
            return []
        flows: list[dict[str, Any]] = []
        for entry in sorted(os.listdir(self.save_folder_path)):
            if "." in entry or "~" in entry:
                continue
            full_path = os.path.join(self.save_folder_path, entry)
            if not os.path.isdir(full_path):
                continue
            flow_data = self.read_flow(entry)
            if flow_data is not None and (
                flow_data.get("is_flow")
                or flow_data.get("has_flow_py")
                or os.path.isfile(os.path.join(full_path, "flow_config.yaml"))
            ):
                flows.append(flow_data)
        return flows

    def delete_flow(self, name: str) -> bool:
        """Delete a Flow from the filesystem and its FlowVersion records from the database."""
        try:
            flow_name = self._validate_flow_name(name)
        except ValueError:
            return False

        flow_dir = os.path.join(self.save_folder_path, flow_name)
        if not os.path.isdir(flow_dir):
            return False

        from flask import has_app_context
        if has_app_context():
            from models import FlowVersion, db
            try:
                FlowVersion.query.filter_by(flow_name=flow_name).delete()
                db.session.commit()
            except Exception:
                db.session.rollback()

        shutil.rmtree(flow_dir)

        if self._is_git_sync_on_save_enabled():
            self.git_commit_and_push(
                target_dir=self.save_folder_path,
                message=f"Delete flow {flow_name}",
            )
        return True

    def _resolve_connector_spec(
        self,
        step_type: str,
        connector: Any | None = None,
        connectors_map: Any | None = None,
    ) -> dict[str, Any] | None:
        """Resolve a connector specification dict by step_type from explicit arguments or AppSettings."""
        clean_type = (step_type or "").strip()
        if not clean_type:
            return None

        candidate: Any = connector
        if candidate is None and isinstance(connectors_map, dict):
            candidate = connectors_map.get(clean_type)
        elif candidate is None and isinstance(connectors_map, (list, tuple)):
            for item in connectors_map:
                item_name = item.get("name") if isinstance(item, dict) else getattr(item, "name", None)
                if item_name == clean_type:
                    candidate = item
                    break

        if candidate is None:
            settings_obj = getattr(self, "_settings", None)
            if settings_obj is None:
                from flask import current_app, has_app_context

                if has_app_context():
                    settings_obj = current_app.config.get("PC_SETTINGS")
            if settings_obj is not None and hasattr(settings_obj, "connectors"):
                for conn_item in getattr(settings_obj, "connectors") or ():
                    if getattr(conn_item, "name", None) == clean_type:
                        candidate = conn_item
                        break

        if candidate is None:
            from utils.app_settings import DefaultsSource

            for raw_conn in DefaultsSource().load().get("connectors") or []:
                if isinstance(raw_conn, dict) and raw_conn.get("name") == clean_type:
                    candidate = raw_conn
                    break

        if candidate is None:
            return None

        if hasattr(candidate, "to_dict") and callable(candidate.to_dict):
            return dict(candidate.to_dict())

        if isinstance(candidate, dict):
            raw_params = candidate.get("parameters") or []
            norm_params: list[dict[str, Any]] = []
            if isinstance(raw_params, dict):
                for p_name, p_spec in raw_params.items():
                    spec_dict = dict(p_spec) if isinstance(p_spec, dict) else {"type": "text", "default": p_spec}
                    p_type = str(spec_dict.get("type") or spec_dict.get("param_type") or "text")
                    norm_params.append(
                        {
                            "name": str(p_name),
                            "type": p_type,
                            "param_type": p_type,
                            "required": bool(spec_dict.get("required", False)),
                            "default": spec_dict.get("default", ""),
                            "source": spec_dict.get("source"),
                            "options": list(spec_dict.get("options") or []),
                        }
                    )
            elif isinstance(raw_params, (list, tuple)):
                for p_item in raw_params:
                    if hasattr(p_item, "to_dict") and callable(p_item.to_dict):
                        norm_params.append(dict(p_item.to_dict()))
                    elif isinstance(p_item, dict) and p_item.get("name"):
                        p_type = str(p_item.get("type") or p_item.get("param_type") or "text")
                        norm_params.append(
                            {
                                "name": str(p_item["name"]),
                                "type": p_type,
                                "param_type": p_type,
                                "required": bool(p_item.get("required", False)),
                                "default": p_item.get("default", ""),
                                "source": p_item.get("source"),
                                "options": list(p_item.get("options") or []),
                            }
                        )
            return {
                "name": str(candidate.get("name") or clean_type),
                "description": str(candidate.get("description") or ""),
                "image": str(candidate.get("image") or "python:3.12-slim"),
                "builtin": bool(candidate.get("builtin", False)),
                "parameters": norm_params,
            }

        return None

    def _build_connector_step_code(
        self,
        pipeline_name: str,
        step_idx: int,
        step_type: str,
        step_config: dict[str, Any],
        connector_spec: dict[str, Any] | None,
    ) -> tuple[str, dict[str, Any], str]:
        """Generate (flow_code, parameters, image) for a Pipeline Builder step."""
        step_params: dict[str, Any] = {}
        if connector_spec and isinstance(connector_spec.get("parameters"), list):
            for p_spec in connector_spec["parameters"]:
                if isinstance(p_spec, dict) and p_spec.get("name"):
                    p_name = str(p_spec["name"])
                    default_val = p_spec.get("default")
                    step_params[p_name] = "" if default_val is None else default_val

        for cfg_key, cfg_val in (step_config or {}).items():
            step_params[str(cfg_key)] = cfg_val

        if connector_spec:
            connector_image = str(connector_spec.get("image") or "python:3.12-slim").strip()
            is_builtin = bool(connector_spec.get("builtin", False))
        else:
            connector_image = str(
                step_config.get("image") or os.environ.get("K8S_DEFAULT_IMAGE", "python:3.12-slim")
            ).strip()
            is_builtin = False

        header_lines = [
            f'"""Auto-generated ProjectCompass Connector Flow for pipeline {pipeline_name!r} step {step_idx} ({step_type})."""',
            "from __future__ import annotations",
            "",
            "import base64",
            "import csv",
            "import json",
            "import os",
            "import sys",
            "from typing import Any",
            "",
            f"PIPELINE_NAME: str = {pipeline_name!r}",
            f"STEP_INDEX: int = {int(step_idx)}",
            f"STEP_TYPE: str = {step_type!r}",
            f"CONNECTOR_IMAGE: str = {connector_image!r}",
            f"DEFAULT_PARAMS: dict[str, Any] = {json.dumps(step_params, sort_keys=True)}",
            "",
            "",
            "def _load_step_params() -> dict[str, Any]:",
            "    params: dict[str, Any] = dict(DEFAULT_PARAMS)",
            '    params_file = os.environ.get("FLOW_PARAMS_FILE", "/workspace/params.json")',
            "    if params_file and os.path.isfile(params_file):",
            "        try:",
            '            with open(params_file, encoding="utf-8") as f_p:',
            "                loaded = json.load(f_p)",
            "            if isinstance(loaded, dict):",
            "                params.update(loaded)",
            "        except Exception:",
            "            pass",
            '    raw_env_json = os.environ.get("FLOW_PARAMS_JSON", "").strip()',
            "    if raw_env_json:",
            "        try:",
            "            loaded_env = json.loads(raw_env_json)",
            "            if isinstance(loaded_env, dict):",
            "                params.update(loaded_env)",
            "        except Exception:",
            "            pass",
            "    for key in list(params.keys()):",
            '        env_key = "PC_PARAM_" + "".join(ch if ch.isalnum() else "_" for ch in str(key)).upper()',
            "        if env_key in os.environ:",
            "            params[key] = os.environ[env_key]",
            "    return params",
            "",
            "",
            "def _emit_step_artifacts(output_dir: str) -> None:",
            "    if not os.path.isdir(output_dir):",
            "        return",
            "    for entry in sorted(os.listdir(output_dir)):",
            "        full_path = os.path.join(output_dir, entry)",
            "        if not os.path.isfile(full_path):",
            "            continue",
            '        with open(full_path, "rb") as f_art:',
            '            encoded = base64.b64encode(f_art.read()).decode("ascii")',
            '        print(f"[PC_ARTIFACT_BEGIN:{entry}]", flush=True)',
            "        print(encoded, flush=True)",
            '        print("[PC_ARTIFACT_END]", flush=True)',
            "",
        ]

        if step_type == "python_script":
            body_lines = [
                "def main() -> None:",
                "    params = _load_step_params()",
                '    output_dir = "/tmp/pc_output/main"',
                "    os.makedirs(output_dir, exist_ok=True)",
                '    output_path = os.path.join(output_dir, "output.csv")',
                '    user_code = str(params.get("code") or "")',
                '    print(f"[ProjectCompass] Executing python_script step {STEP_INDEX}...", flush=True)',
                "    exec_ns: dict[str, Any] = {",
                '        "__name__": "__main__",',
                '        "params": params,',
                '        "inputs": params,',
                '        "output_path": output_path,',
                '        "output_dir": output_dir,',
                '        "os": os,',
                '        "json": json,',
                "    }",
                "    if user_code.strip():",
                '        exec(compile(user_code, "<python_script>", "exec"), exec_ns)',
                '        run_fn = exec_ns.get("run")',
                "        if callable(run_fn):",
                "            run_fn(params, output_path)",
                "    _emit_step_artifacts(output_dir)",
            ]
        elif step_type == "sql_query":
            body_lines = [
                "def main() -> None:",
                "    params = _load_step_params()",
                '    output_dir = "/tmp/pc_output/main"',
                "    os.makedirs(output_dir, exist_ok=True)",
                '    output_path = os.path.join(output_dir, "output.csv")',
                '    query = str(params.get("query") or "SELECT 1 AS result")',
                '    connection = str(params.get("connection") or "default")',
                '    print(f"[ProjectCompass] Executing sql_query on connection {connection!r}: {query}", flush=True)',
                '    db_uri = os.environ.get("PC_DB_URI") or os.environ.get("DATABASE_URL") or ""',
                '    if not db_uri or db_uri.startswith("sqlite"):',
                "        import sqlite3",
                '        db_target = db_uri.replace("sqlite:///", "") if db_uri.startswith("sqlite:///") else ":memory:"',
                "        conn = sqlite3.connect(db_target)",
                "        try:",
                "            cur = conn.execute(query)",
                "            rows = cur.fetchall()",
                '            headers = [d[0] for d in cur.description] if cur.description else ["result"]',
                '            with open(output_path, "w", newline="", encoding="utf-8") as f_csv:',
                "                writer = csv.writer(f_csv)",
                "                writer.writerow(headers)",
                "                writer.writerows(rows)",
                "        finally:",
                "            conn.close()",
                "    else:",
                '        with open(output_path, "w", newline="", encoding="utf-8") as f_csv:',
                "            writer = csv.writer(f_csv)",
                '            writer.writerow(["connection", "query", "status"])',
                '            writer.writerow([connection, query, "executed"])',
                "    _emit_step_artifacts(output_dir)",
            ]
        elif connector_spec is not None and not is_builtin:
            body_lines = [
                "def main() -> None:",
                "    params = _load_step_params()",
                '    output_dir = "/tmp/pc_output/main"',
                "    os.makedirs(output_dir, exist_ok=True)",
                '    output_path = os.path.join(output_dir, "output.csv")',
                '    print(f"[ProjectCompass] Running connector {STEP_TYPE!r} with image {CONNECTOR_IMAGE!r}", flush=True)',
                '    print(f"[ProjectCompass] Connector parameters: {json.dumps(params, sort_keys=True)}", flush=True)',
                '    with open(output_path, "w", newline="", encoding="utf-8") as f_csv:',
                "        writer = csv.writer(f_csv)",
                '        writer.writerow(["connector", "image", "parameters_json"])',
                "        writer.writerow([STEP_TYPE, CONNECTOR_IMAGE, json.dumps(params, sort_keys=True)])",
                "    _emit_step_artifacts(output_dir)",
            ]
        else:
            body_lines = [
                "def main() -> None:",
                "    params = _load_step_params()",
                '    output_dir = "/tmp/pc_output/main"',
                "    os.makedirs(output_dir, exist_ok=True)",
                '    output_path = os.path.join(output_dir, "output.csv")',
                '    print(f"[ProjectCompass] Running pipeline step {STEP_INDEX} ({STEP_TYPE})", flush=True)',
                '    with open(output_path, "w", newline="", encoding="utf-8") as f_csv:',
                "        writer = csv.writer(f_csv)",
                '        writer.writerow(["step_index", "step_type", "config_json"])',
                "        writer.writerow([STEP_INDEX, STEP_TYPE, json.dumps(params, sort_keys=True)])",
                "    _emit_step_artifacts(output_dir)",
            ]

        footer_lines = [
            "",
            "",
            'if __name__ == "__main__":',
            "    main()",
            "",
        ]
        full_code = "\n".join(header_lines + body_lines + footer_lines)
        return full_code, step_params, connector_image

    def compile_connector_step_flow(
        self,
        pipeline_name: str,
        step_idx: int,
        step_type: str,
        step_config: dict[str, Any] | None = None,
        connector: Any | None = None,
        connectors_map: Any | None = None,
        owner: str = "Anonymous",
        product: str = "General",
    ) -> dict[str, Any]:
        """Compile a single Pipeline Builder step into a parameterized Flow."""
        safe_pipe = re.sub(r"[^A-Za-z0-9_-]+", "_", (pipeline_name or "").strip()).strip("_") or "pipeline"
        safe_type = re.sub(r"[^A-Za-z0-9_-]+", "_", (step_type or "").strip()).strip("_") or "step"
        step_flow_name = f"{safe_pipe}__step_{int(step_idx)}_{safe_type}"

        connector_spec = self._resolve_connector_spec(
            step_type=step_type,
            connector=connector,
            connectors_map=connectors_map,
        )
        step_code, step_params, connector_image = self._build_connector_step_code(
            pipeline_name=pipeline_name,
            step_idx=int(step_idx),
            step_type=step_type,
            step_config=step_config or {},
            connector_spec=connector_spec,
        )
        conn_desc = str(connector_spec.get("description") or "").strip() if connector_spec else ""
        description = (
            f"Pipeline '{pipeline_name}' step {int(step_idx)} ({step_type})"
            + (f" — {conn_desc}" if conn_desc else "")
        )

        saved_flow = self.save_flow(
            name=step_flow_name,
            code=step_code,
            description=description,
            parameters=step_params,
            image=connector_image,
            owner=owner or "flow-author",
            version_message=f"Compile pipeline '{pipeline_name}' step {int(step_idx)} ({step_type})",
            product=product or "Pipeline Step",
        )
        saved_flow["step_idx"] = int(step_idx)
        saved_flow["step_type"] = step_type
        return saved_flow

    def compile_pipeline_steps(
        self,
        name: str,
        steps: list[dict[str, Any]],
        description: str = "",
        owner: str = "Anonymous",
        product: str = "Machine Learning",
        connectors_map: Any | None = None,
        connectors: Any | None = None,
    ) -> dict[str, Any]:
        """Compile an ordered list of Pipeline Builder steps into per-step Flows."""
        pipeline_name = self._validate_flow_name(name)
        resolved_connectors = connectors_map if connectors_map is not None else connectors
        step_flows: list[str] = []
        compiled_steps: list[dict[str, Any]] = []

        for idx, step in enumerate(steps, start=1):
            step_type = str(step.get("type") or step.get("connector") or step.get("class") or "python_script")
            raw_cfg = step.get("config")
            if not isinstance(raw_cfg, dict):
                raw_cfg = step.get("parameters") if isinstance(step.get("parameters"), dict) else {}
            flow_info = self.compile_connector_step_flow(
                pipeline_name=pipeline_name,
                step_idx=idx,
                step_type=step_type,
                step_config=raw_cfg,
                connectors_map=resolved_connectors,
                owner=owner or "flow-author",
                product=product or "Machine Learning",
            )
            step_flows.append(flow_info["name"])
            compiled_steps.append(flow_info)

        return {
            "name": pipeline_name,
            "step_flows": step_flows,
            "steps": compiled_steps,
        }

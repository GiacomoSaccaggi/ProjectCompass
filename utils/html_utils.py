

# Import Pkg
import os
import re
import jwt
import yaml
import shutil
import datetime
import zlib
import base64
import pandas as pd
from typing import Union

class HTMLUtils:
    def __init__(self, dir_path, **kwargs):
        self.template = f'{dir_path}templates/header.html'
        self.template_folder = f'{dir_path}templates'
        with open(f"{self.template_folder}/environment_variables/constants.yaml", 'r') as file:
            try:
                self.constants = yaml.safe_load(file)
            except yaml.YAMLError as exc:
                print(exc)
        with open(f"{self.template_folder}/environment_variables/tool_choices.yaml", 'r') as file:
            try:
                self.tool_choices = yaml.safe_load(file)
            except yaml.YAMLError as exc:
                print(exc)
        if 'PORT' in os.environ:
            self.constants['port'] = os.environ['PORT']
        self.environments_info = {}
        for file in ['intro.txt', 'links.yaml', 'title.txt']:
            if '.yaml' in file:
                with open(f"{self.template_folder}/environment_variables/{file}", 'r') as f:
                    try:
                        self.environments_info[file.split('.')[0]] = yaml.safe_load(f)
                    except yaml.YAMLError as exc:
                        print(exc)
            else:
                with open(f'{self.template_folder}/environment_variables/{file}', 'r', encoding='utf-8') as f:
                    self.environments_info[file.split('.')[0]] = '\n'.join(f.readlines())
        with open(self.template, 'r', encoding='utf-8') as f:
            text = '\n'.join(f.readlines())
        self.tags = [i.replace(' start ', '').replace('start ', '') for i in re.findall(r'<!--(.*)-->', text)
                     if 'start' in i]
        self.html_parts = {}
        for t in self.tags:
            try:
                self.html_parts[t.strip()] = text[
                                        (text.index(f'start {t}-->')
                                         + len(f'start {t}-->')): text.index(f'<!-- end {t}-->')]
            except ValueError:
                self.html_parts[t.strip()] = text[
                                        (text.index(f'start {t}-->')
                                         + len(f'start {t}-->')):text.index(f'<!--end {t}-->')]
        super().__init__(**kwargs)

    def substitute_html(self, **kwargs):
        tmp_html_parts = {}
        for html_k, html_text in self.html_parts.items():
            for k, v in kwargs.items():
                html_text = html_text.replace('{{ '+str(k)+' }}', str(v)).replace('{{'+str(k)+'}}', str(v))
            tmp_html_parts[html_k] = html_text.replace('\n/n', '\n')
        return tmp_html_parts
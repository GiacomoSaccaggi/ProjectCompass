

from __future__ import annotations

# Import Pkg
import copy
import os
import re
from html import escape as escape_html
from typing import TYPE_CHECKING

import yaml
from jinja2 import Environment, FileSystemLoader

if TYPE_CHECKING:
    from utils.app_settings import PublicAppSettings


class HTMLUtils:
    def __init__(self, dir_path, **kwargs):
        self.template = f'{dir_path}templates/header.html'
        self.template_folder = f'{dir_path}templates'
        with open(f"{self.template_folder}/environment_variables/constants.yaml") as file:
            try:
                self.constants = yaml.safe_load(file)
            except yaml.YAMLError as exc:
                print(exc)
        with open(f"{self.template_folder}/environment_variables/tool_choices.yaml") as file:
            try:
                self.tool_choices = yaml.safe_load(file)
            except yaml.YAMLError as exc:
                print(exc)
        if 'PORT' in os.environ:
            self.constants['port'] = os.environ['PORT']
        self.environments_info = {}
        for file in ['intro.txt', 'links.yaml', 'title.txt']:
            if '.yaml' in file:
                with open(f"{self.template_folder}/environment_variables/{file}") as f:
                    try:
                        self.environments_info[file.split('.')[0]] = yaml.safe_load(f)
                    except yaml.YAMLError as exc:
                        print(exc)
            else:
                with open(f'{self.template_folder}/environment_variables/{file}', encoding='utf-8') as f:
                    self.environments_info[file.split('.')[0]] = '\n'.join(f.readlines())
        self._base_environments_info = copy.deepcopy(self.environments_info)
        with open(self.template, encoding='utf-8') as f:
            text = f.read()
        self._split_header(text)
        super().__init__()

    def apply_settings(self, settings: PublicAppSettings) -> None:
        """Render shared navigation with escaped branding and theme values."""
        safe_app_name = escape_html(settings.branding.app_name)
        self.environments_info = copy.deepcopy(self._base_environments_info)
        for key, value in self.environments_info.items():
            if isinstance(value, str):
                replacement = safe_app_name if key == 'intro' else settings.branding.app_name
                self.environments_info[key] = value.replace('ProjectCompass', replacement)
            elif isinstance(value, dict):
                self.environments_info[key] = {
                    settings.branding.app_name if label == 'ProjectCompass' else label: link
                    for label, link in value.items()
                }
        environment = Environment(
            loader=FileSystemLoader(self.template_folder),
            autoescape=True,
        )
        rendered_header = environment.get_template('header.html').render(pc=settings)
        self._split_header(rendered_header)
        self._settings = settings
        if hasattr(self, 'configure_worker_provider') and getattr(settings, 'workers', None) is not None:
            self.configure_worker_provider(settings.workers)

    def _split_header(self, text: str) -> None:
        """Split rendered header markup into the legacy shared page fragments."""
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

    def substitute_html(self, **kwargs):
        tmp_html_parts = {}
        for html_k, html_text in self.html_parts.items():
            for k, v in kwargs.items():
                html_text = html_text.replace('{{ '+str(k)+' }}', str(v)).replace('{{'+str(k)+'}}', str(v))
            tmp_html_parts[html_k] = html_text.replace('\n/n', '\n')
        return tmp_html_parts

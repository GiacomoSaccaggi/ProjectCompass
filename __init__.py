# -*- coding: utf-8 -*-
"""


░██╗░░░░░░░██╗███████╗██████╗░░█████╗░██████╗░██████╗░
░██║░░██╗░░██║██╔════╝██╔══██╗██╔══██╗██╔══██╗██╔══██╗
░╚██╗████╗██╔╝█████╗░░██████╦╝███████║██████╔╝██████╔╝
░░████╔═████║░██╔══╝░░██╔══██╗██╔══██║██╔═══╝░██╔═══╝░
░░╚██╔╝░╚██╔╝░███████╗██████╦╝██║░░██║██║░░░░░██║░░░░░
░░░╚═╝░░░╚═╝░░╚══════╝╚═════╝░╚═╝░░╚═╝╚═╝░░░░░╚═╝░░░░░


"""

import requests
import subprocess
from .app import *


def run_locally():
    status_code = 404
    try:
        status_code = requests.get(f'http://127.0.0.1:{webapp.constants["port"]}/check').status_code
    except requests.exceptions.ConnectionError:
        status_code = 501
    if status_code == 200:
        print('App it is running in other script')
    else:
        app.run(port=webapp.constants["port"], debug='true' in str(webapp.constants["debug"]).strip().lower())


def run_jupyter():
    status_code = 404
    try:
        status_code = requests.get(f'http://127.0.0.1:{webapp.constants["port"]}/check').status_code
    except requests.exceptions.ConnectionError:
        status_code = 501
    if status_code != 200:
        subprocess.run(["python", f"{dir_path}main.py", "5"])
    from IPython.display import IFrame
    IFrame(src = f'http://127.0.0.1:{webapp.constants["port"]}/', width = '100%', height = 600)


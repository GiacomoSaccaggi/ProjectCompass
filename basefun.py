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
import jwt
import yaml
import shutil
import datetime
import zlib
import base64
import pandas as pd
from typing import Union
from utils.data_utils import DataUtils
from utils.html_utils import HTMLUtils
from utils.analysis_utils import AnalysisUtils

# Import env variables
class ProjectCompass(DataUtils, AnalysisUtils, HTMLUtils):
    def __init__(self, dir_path):

        self.dir_path = dir_path
        super().__init__(dir_path=dir_path)

        self.environments = [self.template, self.save_folder_path]
        if dir_path[:-1].split('/')[0] != dir_path[:-1]:
            self.project_folder = dir_path[:-1].split('/')[-1].replace(' ', '%20') + '/'
        elif dir_path[:-1].split('\\')[0] != dir_path[:-1]:
            self.project_folder = dir_path[:-1].split('\\')[-1].replace(' ', '%20') + '/'
        elif dir_path[:-1].split('/')[-1].replace(' ', '%20') != '':
            self.project_folder = ''
        elif dir_path[:-1].split('\\')[-1].replace(' ', '%20') != '':
            self.project_folder = ''
        else:
            self.project_folder = dir_path[:-1].split('/')[-1].replace(' ', '%20') + '/'

    @staticmethod
    def create_job_request(RECIPE_ID, RECIPE_VERSION, **kwargs):
        job_request_dict = {
            'spec_version': "v2",
            'recipe_id': RECIPE_ID,
            'recipe_version': RECIPE_VERSION,
            'system_configuration': {
                'send_dag_complete_email': False,
                'prefer_user_pyenv': True,
                'allow_unpublished_recipe_runs': True
            },
            'configuration': {k: v for k, v in kwargs.get('input_recipe', {}).items()}

        }
        return job_request_dict



def encrypt_and_compress(text, key='key'):
    # Crittografia della stringa utilizzando la chiave di crittografia fornita
    encoded = text.encode('utf-8')
    encrypted = bytearray()
    for i in range(len(encoded)):
        key_c = key[i % len(key)]
        encrypted_c = (encoded[i] + ord(key_c)) % 256
        encrypted.append(encrypted_c)

    # Compressione della stringa utilizzando l'algoritmo di compressione zlib
    compressed = zlib.compress(bytes(encrypted))

    # Codifica della stringa utilizzando il metodo di codifica Base64
    encrypted_string = base64.b64encode(compressed)

    # Restituzione della stringa crittografata e compressa
    return encrypted_string.decode('utf-8')

def decrypt_and_decompress(encrypted_string, key='key'):
    # Decodifica della stringa utilizzando il metodo di codifica Base64
    decoded = base64.b64decode(encrypted_string.encode('utf-8'))

    # Decompressione della stringa utilizzando l'algoritmo di compressione zlib
    decompressed = zlib.decompress(decoded)

    # Decrittografia della stringa utilizzando la chiave di crittografia fornita
    decrypted = bytearray()
    for i in range(len(decompressed)):
        key_c = key[i % len(key)]
        decrypted_c = (decompressed[i] - ord(key_c)) % 256
        decrypted.append(decrypted_c)

    # Decodifica della stringa decrittografata in una stringa di testo
    text = decrypted.decode('utf-8')

    # Restituzione della stringa decrittografata e decompressa
    return text

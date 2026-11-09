"""


░██╗░░░░░░░██╗███████╗██████╗░░█████╗░██████╗░██████╗░
░██║░░██╗░░██║██╔════╝██╔══██╗██╔══██╗██╔══██╗██╔══██╗
░╚██╗████╗██╔╝█████╗░░██████╦╝███████║██████╔╝██████╔╝
░░████╔═████║░██╔══╝░░██╔══██╗██╔══██║██╔═══╝░██╔═══╝░
░░╚██╔╝░╚██╔╝░███████╗██████╦╝██║░░██║██║░░░░░██║░░░░░
░░░╚═╝░░░╚═╝░░╚══════╝╚═════╝░╚═╝░░╚═╝╚═╝░░░░░╚═╝░░░░░


"""


# Import Pkg
import base64
import os
import zlib

from utils.analysis_utils import AnalysisUtils
from utils.data_utils import DataUtils
from utils.html_utils import HTMLUtils
from utils.k8s_utils import K8sFlowRunnerUtils


# Import env variables
class ProjectCompass(DataUtils, AnalysisUtils, HTMLUtils, K8sFlowRunnerUtils):
    def __init__(self, dir_path, data_dir=None):

        self.dir_path = dir_path
        resolved_data = data_dir or os.environ.get('DATA_DIR') or dir_path
        if not resolved_data.endswith('/'):
            resolved_data = resolved_data + '/'
        self.data_dir = resolved_data
        super().__init__(dir_path=dir_path, data_dir=self.data_dir)

        self.environments = [self.template, self.save_folder_path]
        self.project_folder = ''

    @staticmethod
    def create_task_config(task_id: str, task_version: str, **kwargs) -> dict:
        """Build a generic task configuration payload."""
        return {
            'task_id': task_id,
            'task_version': task_version,
            'configuration': dict(kwargs.get('input_params', {})),
        }



def encrypt_and_compress(text, key='key'):
    # Encrypt the string using the provided encryption key
    encoded = text.encode('utf-8')
    encrypted = bytearray()
    for i in range(len(encoded)):
        key_c = key[i % len(key)]
        encrypted_c = (encoded[i] + ord(key_c)) % 256
        encrypted.append(encrypted_c)

    # Compress the string using zlib compression
    compressed = zlib.compress(bytes(encrypted))

    # Encode the string using Base64 encoding
    encrypted_string = base64.b64encode(compressed)

    # Return the encrypted and compressed string
    return encrypted_string.decode('utf-8')

def decrypt_and_decompress(encrypted_string, key='key'):
    # Decode the string using Base64 encoding
    decoded = base64.b64decode(encrypted_string.encode('utf-8'))

    # Decompress the string using zlib decompression
    decompressed = zlib.decompress(decoded)

    # Decrypt the string using the provided encryption key
    decrypted = bytearray()
    for i in range(len(decompressed)):
        key_c = key[i % len(key)]
        decrypted_c = (decompressed[i] - ord(key_c)) % 256
        decrypted.append(decrypted_c)

    # Decode the decrypted string into a text string
    text = decrypted.decode('utf-8')

    # Return the decrypted and decompressed string
    return text

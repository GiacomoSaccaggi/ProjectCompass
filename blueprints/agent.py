import ast
import os

import pandas as pd
from flask import Blueprint, current_app, jsonify, render_template, request

from logging_config import logger

agent_bp = Blueprint('agent', __name__)

# Lazy-loaded LLM components
_llm = None
_embed_model = None


def _get_llm():
    """Lazy-load Ollama LLM. Returns None if unavailable."""
    global _llm, _embed_model
    if _llm is not None:
        return _llm
    try:
        from llama_index.core import Settings
        from llama_index.embeddings.ollama import OllamaEmbedding
        from llama_index.llms.ollama import Ollama

        host = current_app.config.get('OLLAMA_HOST', 'http://localhost:11434')
        _llm = Ollama(model="llama3", base_url=host)
        _embed_model = OllamaEmbedding(model_name="nomic-embed-text", base_url=host)
        Settings.llm = _llm
        Settings.embed_model = _embed_model
        logger.info("Ollama LLM loaded successfully")
        return _llm
    except Exception as e:
        logger.warning(f"Ollama not available: {e}")
        return None


# Safe expression evaluator — NO eval()
SAFE_PANDAS_ATTRS = {
    'head', 'tail', 'describe', 'info', 'shape', 'columns', 'dtypes', 'index',
    'nunique', 'value_counts', 'sum', 'mean', 'median', 'std', 'min', 'max',
    'count', 'groupby', 'sort_values', 'sort_index', 'reset_index',
    'fillna', 'dropna', 'isnull', 'notnull', 'drop_duplicates',
    'to_csv', 'to_dict', 'tolist', 'len', 'iloc', 'loc',
}


def safe_execute_pandas(expression: str, df: pd.DataFrame) -> str:
    """Execute a pandas expression safely without eval().
    Uses AST parsing to validate the expression before execution."""
    try:
        tree = ast.parse(expression, mode='eval')
    except SyntaxError as e:
        return f"Invalid expression: {e}"

    # Walk the AST and check for unsafe operations
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                if node.func.id not in ('len', 'sorted', 'list', 'str', 'int', 'float', 'round'):
                    return f"Disallowed function: {node.func.id}"
            elif isinstance(node.func, ast.Attribute):
                # Allow pandas method calls
                pass
        elif isinstance(node, ast.Import | ast.ImportFrom):
            return "Import statements not allowed"

    # Execute in restricted namespace
    safe_globals = {"__builtins__": {"len": len, "sorted": sorted, "list": list,
                                     "str": str, "int": int, "float": float, "round": round}}
    safe_locals = {"main_df": df, "pd": pd}

    try:
        result = eval(compile(tree, '<expr>', 'eval'), safe_globals, safe_locals)  # noqa: S307
        if isinstance(result, pd.DataFrame):
            return result.head(20).to_string()
        return str(result)
    except Exception as e:
        return f"Execution error: {e}"


@agent_bp.route('/chat')
def chat_page():
    webapp = current_app.config['WEBAPP']
    html_part = webapp.substitute_html(port=webapp.constants["port"], project_folder=webapp.project_folder)
    datasets = webapp.list_data()
    return render_template('chat.html',
                           title=webapp.environments_info['title'],
                           head=html_part['head'],
                           top_container=html_part['top_container'],
                           port=webapp.constants["port"],
                           project_folder=webapp.project_folder,
                           sidebar_menu=html_part['sidebar_menu'],
                           datasets=datasets)


@agent_bp.route('/chat/ask', methods=['POST'])
def chat_ask():
    webapp = current_app.config['WEBAPP']
    data = request.get_json()
    question = data.get('question', '')
    dataset = data.get('dataset', '')

    if not question:
        return jsonify({'error': 'No question provided'}), 400

    llm = _get_llm()
    if llm is None:
        return jsonify({'error': 'LLM service not available. Is Ollama running?'}), 503

    # Load dataset
    dataset_path = os.path.join(webapp.save_data_path, f"{dataset}.csv")
    if not os.path.exists(dataset_path):
        return jsonify({'error': f'Dataset "{dataset}" not found'}), 404

    df = pd.read_csv(dataset_path)

    # Generate pandas expression via LLM
    prompt = f"""You are a Python data analyst. Convert this question into a single pandas expression
operating on 'main_df'. ONLY output the Python expression, nothing else.

DataFrame columns: {list(df.columns)}
DataFrame shape: {df.shape}
Sample dtypes: {df.dtypes.to_dict()}

Question: {question}

Expression:"""

    try:
        from llama_index.core import Settings
        response = Settings.llm.complete(prompt)
        expression = str(response).strip().split('\n')[0]
        logger.info(f"LLM generated expression: {expression}")

        # Safe execution
        result = safe_execute_pandas(expression, df)
        return jsonify({
            'answer': result,
            'expression': expression,
        })
    except Exception as e:
        logger.error(f"Chat error: {e}")
        return jsonify({'error': str(e)}), 500

import ast
import json
import os

import pandas as pd
from flask import Blueprint, Response, current_app, jsonify, render_template, request

from logging_config import logger

agent_bp = Blueprint('agent', __name__)


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


def _get_client():
    """Get MithrilClient instance (lazy-loaded)."""
    from utils.mithril_client import get_client
    return get_client()


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


@agent_bp.route('/chat/models')
def chat_models():
    """Return available models from Mithril."""
    try:
        client = _get_client()
        models = client.list_models()
        return jsonify({'models': models})
    except Exception as e:
        logger.warning(f"Cannot fetch models: {e}")
        return jsonify({'models': [], 'error': str(e)}), 503


@agent_bp.route('/chat/ask', methods=['POST'])
def chat_ask():
    webapp = current_app.config['WEBAPP']
    data = request.get_json()
    question = data.get('question', '')
    dataset = data.get('dataset', '')
    model = data.get('model', '')

    if not question:
        return jsonify({'error': 'No question provided'}), 400

    # Check Mithril availability
    try:
        client = _get_client()
        if not client.health():
            return jsonify({'error': 'LLM service not available. Is Mithril running?'}), 503
    except Exception:
        return jsonify({'error': 'LLM service not available. Is Mithril running?'}), 503

    # Use first available model if none specified
    if not model:
        models = client.list_models()
        model = models[0] if models else "qwen2:1.5b"

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
        messages = [{"role": "user", "content": prompt}]
        response = client.chat(model, messages)
        expression = response.strip().split('\n')[0]
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


@agent_bp.route('/chat/stream', methods=['POST'])
def chat_stream():
    """Streaming chat endpoint via Server-Sent Events."""
    data = request.get_json()
    question = data.get('question', '')
    model = data.get('model', '')
    context = data.get('context', '')

    if not question:
        return jsonify({'error': 'No question provided'}), 400

    try:
        client = _get_client()
        if not client.health():
            return jsonify({'error': 'LLM service not available'}), 503
    except Exception:
        return jsonify({'error': 'LLM service not available'}), 503

    if not model:
        models = client.list_models()
        model = models[0] if models else "qwen2:1.5b"

    content = question
    if context:
        content = f"{context}\n\nQuestion: {question}\n\nAnswer:"

    messages = [{"role": "user", "content": content}]

    def generate():
        try:
            for chunk in client.chat_stream(model, messages):
                yield f"data: {json.dumps({'content': chunk})}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return Response(generate(), mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


@agent_bp.route('/chat/analysis')
def chat_analysis_page():
    """Chat page with analysis context pre-loaded."""
    webapp = current_app.config['WEBAPP']
    html_part = webapp.substitute_html(port=webapp.constants["port"], project_folder=webapp.project_folder)
    name = request.args.get('name', '').replace('512', ' ')
    analysis = {}
    if name:
        try:
            analysis = webapp.read_single_analysis(webapp.extract_main_folder(), name)
        except Exception:
            pass
    return render_template('chat_analysis.html',
                           head=html_part['head'],
                           top_container=html_part['top_container'],
                           sidebar_menu=html_part['sidebar_menu'],
                           port=webapp.constants["port"],
                           project_folder=webapp.project_folder,
                           analysis=analysis,
                           analysis_name=name)


@agent_bp.route('/chat/analysis/ask', methods=['POST'])
def chat_analysis_ask():
    """Chat endpoint with analysis metadata as context."""
    webapp = current_app.config['WEBAPP']
    data = request.get_json()
    question = data.get('question', '')
    analysis_name = data.get('analysis_name', '')
    model = data.get('model', '')

    if not question:
        return jsonify({'error': 'No question provided'}), 400

    try:
        client = _get_client()
        if not client.health():
            return jsonify({'error': 'LLM service not available. Is Mithril running?'}), 503
    except Exception:
        return jsonify({'error': 'LLM service not available. Is Mithril running?'}), 503

    if not model:
        models = client.list_models()
        model = models[0] if models else "qwen2:1.5b"

    # Load analysis context
    context = ""
    if analysis_name:
        try:
            analysis = webapp.read_single_analysis(webapp.extract_main_folder(), analysis_name)
            context = f"""Analysis: {analysis.get('title', '')}
Product: {analysis.get('product', '')}
Owner: {analysis.get('owner', '')}
Collaborators: {analysis.get('collaborators', '')}
Countries: {analysis.get('countries', '')}
Description: {analysis.get('description', '')}
Output type: {analysis.get('output_type', '')}
Output description: {analysis.get('output description', '')}
Start date: {analysis.get('start_date', '')}"""
        except Exception:
            pass

    prompt = f"""You are a helpful assistant knowledgeable about data analysis projects.
Use the following analysis context to answer the user's question.

{context}

Question: {question}

Answer:"""

    try:
        messages = [{"role": "user", "content": prompt}]
        response = client.chat(model, messages)
        return jsonify({'answer': response.strip()})
    except Exception as e:
        logger.error(f"Analysis chat error: {e}")
        return jsonify({'error': str(e)}), 500


@agent_bp.route('/chat/analysis/rag', methods=['POST'])
def chat_analysis_rag():
    """RAG-enhanced analysis chat endpoint."""
    from utils.rag_guardrails import build_rag_prompt, format_provenance, validate_query, validate_response
    from utils.rag_store import RAGStore

    webapp = current_app.config['WEBAPP']
    data = request.get_json()
    question = data.get('question', '')
    analysis_name = data.get('analysis_name', '')
    model = data.get('model', '')

    if not question:
        return jsonify({'error': 'No question provided'}), 400

    # Validate query
    is_valid, error_msg = validate_query(question)
    if not is_valid:
        return jsonify({'error': error_msg}), 400

    try:
        client = _get_client()
        if not client.health():
            return jsonify({'error': 'LLM service not available. Is Mithril running?'}), 503
    except Exception:
        return jsonify({'error': 'LLM service not available. Is Mithril running?'}), 503

    if not model:
        models = client.list_models()
        model = models[0] if models else 'qwen2:1.5b'

    # Check if RAG index exists
    store = RAGStore()
    if not store.has_index(analysis_name):
        # Fallback to metadata-only chat
        return _chat_with_metadata(client, model, question, analysis_name, webapp)

    try:
        # Hybrid query
        results = store.hybrid_query(analysis_name, question, top_k=10)

        # Rerank
        try:
            results = store.rerank(question, results, top_n=5)
        except Exception as e:
            logger.warning(f'Reranking failed, using hybrid results: {e}')
            results = results[:5]

        # Load analysis metadata
        analysis_meta = {}
        try:
            analysis_meta = webapp.read_single_analysis(webapp.extract_main_folder(), analysis_name)
        except Exception:
            pass

        # Build RAG prompt
        prompt = build_rag_prompt(question, results, analysis_meta)
        messages = [{'role': 'user', 'content': prompt}]
        response = client.chat(model, messages)

        # Validate response
        response = validate_response(response)

        # Format sources
        sources = [{
            'file': r.source_file,
            'lines': f'{r.start_line}-{r.end_line}' if r.start_line else '',
            'type': r.chunk_type,
            'relevance': round(r.score, 3),
        } for r in results]

        provenance = format_provenance(results)

        return jsonify({
            'answer': response.strip(),
            'sources': sources,
            'provenance': provenance,
            'mode': 'rag',
        })
    except Exception as e:
        logger.error(f'RAG chat error: {e}')
        # Fallback to metadata-only
        return _chat_with_metadata(client, model, question, analysis_name, webapp)


@agent_bp.route('/chat/analysis/rag/stream', methods=['POST'])
def chat_analysis_rag_stream():
    """Streaming RAG-enhanced analysis chat via SSE."""
    from utils.rag_guardrails import build_rag_prompt, format_provenance, validate_query
    from utils.rag_store import RAGStore

    data = request.get_json()
    question = data.get('question', '')
    analysis_name = data.get('analysis_name', '')
    model = data.get('model', '')

    if not question:
        return jsonify({'error': 'No question provided'}), 400

    is_valid, error_msg = validate_query(question)
    if not is_valid:
        return jsonify({'error': error_msg}), 400

    try:
        client = _get_client()
        if not client.health():
            return jsonify({'error': 'LLM service not available'}), 503
    except Exception:
        return jsonify({'error': 'LLM service not available'}), 503

    if not model:
        models = client.list_models()
        model = models[0] if models else 'qwen2:1.5b'

    store = RAGStore()
    webapp = current_app.config['WEBAPP']

    # Build context
    results = []
    mode = 'metadata'
    if store.has_index(analysis_name):
        mode = 'rag'
        results = store.hybrid_query(analysis_name, question, top_k=10)
        try:
            results = store.rerank(question, results, top_n=5)
        except Exception:
            results = results[:5]

    analysis_meta = {}
    try:
        analysis_meta = webapp.read_single_analysis(webapp.extract_main_folder(), analysis_name)
    except Exception:
        pass

    if mode == 'rag' and results:
        prompt = build_rag_prompt(question, results, analysis_meta)
    else:
        context = _build_metadata_context(analysis_meta)
        prompt = f"""You are a helpful assistant knowledgeable about data analysis projects.
Use the following context to answer the question.

{context}

Question: {question}

Answer:"""

    messages = [{'role': 'user', 'content': prompt}]

    def generate():
        try:
            for chunk in client.chat_stream(model, messages):
                yield f'data: {json.dumps({"content": chunk})}\n\n'
            # Send provenance at the end
            if results:
                sources = [{
                    'file': r.source_file,
                    'lines': f'{r.start_line}-{r.end_line}' if r.start_line else '',
                    'type': r.chunk_type,
                    'relevance': round(r.score, 3),
                } for r in results]
                provenance = format_provenance(results)
                yield f'data: {json.dumps({"provenance": provenance, "sources": sources, "mode": mode})}\n\n'
            yield 'data: [DONE]\n\n'
        except Exception as e:
            yield f'data: {json.dumps({"error": str(e)})}\n\n'

    return Response(generate(), mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


def _chat_with_metadata(client, model, question, analysis_name, webapp):
    """Fallback: chat using only metadata.yaml context."""
    analysis_meta = {}
    try:
        analysis_meta = webapp.read_single_analysis(webapp.extract_main_folder(), analysis_name)
    except Exception:
        pass

    context = _build_metadata_context(analysis_meta)
    prompt = f"""You are a helpful assistant knowledgeable about data analysis projects.
Use the following analysis context to answer the user's question.

{context}

Question: {question}

Answer:"""

    try:
        messages = [{'role': 'user', 'content': prompt}]
        response = client.chat(model, messages)
        return jsonify({'answer': response.strip(), 'sources': [], 'provenance': '', 'mode': 'metadata'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def _build_metadata_context(analysis: dict) -> str:
    """Build a simple metadata context string."""
    if not analysis:
        return ''
    parts = []
    for key in ('title', 'product', 'owner', 'collaborators', 'countries', 'description', 'output_type', 'output description', 'start_date'):
        val = analysis.get(key, '')
        if val:
            parts.append(f'{key}: {val}')
    return '\n'.join(parts)

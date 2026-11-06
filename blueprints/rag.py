"""RAG blueprint — build, query, and manage per-analysis RAG indices."""
import threading

from flask import Blueprint, current_app, jsonify, request

from logging_config import logger

rag_bp = Blueprint('rag', __name__)


def _get_rag_store():
    from utils.rag_store import RAGStore
    if 'RAG_STORE' not in current_app.config:
        current_app.config['RAG_STORE'] = RAGStore()
    return current_app.config['RAG_STORE']


@rag_bp.route('/rag/build/<analysis_name>', methods=['POST'])
def build_rag(analysis_name):
    """Build or rebuild the RAG index for an analysis.

    Uses local E5 embeddings by default — no external service required.
    Set RAG_EMBED_BACKEND=mithril in config to use cloud embeddings instead.
    """
    import os
    from utils.chunker import chunk_analysis, chunk_comments

    analysis_name = analysis_name.replace('512', ' ')
    webapp = current_app.config['WEBAPP']
    analysis_path = os.path.join(webapp.extract_main_folder(), analysis_name)

    if not os.path.isdir(analysis_path):
        return jsonify({'error': f'Analysis not found: {analysis_name}'}), 404

    # If using Mithril backend, check availability
    backend = current_app.config.get('RAG_EMBED_BACKEND', 'local')
    if backend == 'mithril':
        try:
            from utils.mithril_client import get_client
            client = get_client()
            if not client.health():
                return jsonify({'error': 'Mithril is not available. Cannot generate embeddings.'}), 503
        except Exception:
            return jsonify({'error': 'Mithril is not available. Cannot generate embeddings.'}), 503

    try:
        chunks = chunk_analysis(analysis_path)

        try:
            comment_chunks = chunk_comments(analysis_name)
            chunks.extend(comment_chunks)
        except Exception as e:
            logger.warning(f'Could not chunk comments for {analysis_name}: {e}')

        if not chunks:
            return jsonify({'status': 'empty', 'message': 'No content to index', 'chunks': 0})

        store = _get_rag_store()
        result = store.build_index(analysis_name, chunks)

        files = len(set(c.source_file for c in chunks))

        logger.info(f'RAG built for {analysis_name}: {result["chunks"]} chunks from {files} files')
        return jsonify({
            'status': 'ok',
            'chunks': result['chunks'],
            'files': files,
            'message': f'Indexed {result["chunks"]} chunks from {files} files'
        })
    except Exception as e:
        logger.error(f'RAG build failed for {analysis_name}: {e}')
        return jsonify({'error': str(e)}), 500


@rag_bp.route('/rag/status/<analysis_name>')
def rag_status(analysis_name):
    """Get RAG index status for an analysis."""
    analysis_name = analysis_name.replace('512', ' ')
    try:
        store = _get_rag_store()
        return jsonify(store.index_status(analysis_name))
    except Exception as e:
        return jsonify({'exists': False, 'error': str(e)})


@rag_bp.route('/rag/index/<analysis_name>', methods=['DELETE'])
def delete_rag(analysis_name):
    """Delete the RAG index for an analysis."""
    analysis_name = analysis_name.replace('512', ' ')
    try:
        store = _get_rag_store()
        store.delete_index(analysis_name)
        return jsonify({'status': 'ok', 'message': f'RAG index deleted for {analysis_name}'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def trigger_rag_rebuild(app, analysis_name: str):
    """Fire-and-forget RAG rebuild in a background thread.

    Works with local embeddings — no Mithril dependency for the build itself.
    """
    def _rebuild():
        with app.app_context():
            try:
                import os
                from utils.chunker import chunk_analysis, chunk_comments

                webapp = app.config['WEBAPP']
                analysis_path = os.path.join(webapp.extract_main_folder(), analysis_name)
                if not os.path.isdir(analysis_path):
                    return

                chunks = chunk_analysis(analysis_path)
                try:
                    chunks.extend(chunk_comments(analysis_name))
                except Exception:
                    pass

                if chunks:
                    from utils.rag_store import RAGStore
                    store = RAGStore()
                    store.build_index(analysis_name, chunks)
                    logger.info(f'RAG auto-rebuilt for {analysis_name}')
            except Exception as e:
                logger.warning(f'RAG auto-rebuild failed for {analysis_name}: {e}')

    thread = threading.Thread(target=_rebuild, daemon=True)
    thread.start()

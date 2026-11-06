"""ChromaDB-backed RAG store with per-analysis collections.

Thin wrapper around scomp_link.llm.rag — all logic lives in scomp-link.
ProjectCompass-specific additions: Flask config integration, Mithril reranking.
"""
import os

from scomp_link.llm.rag.pipeline import RAGPipeline, RetrievalResult, _sanitize_collection_name

from logging_config import logger


def _get_embed_backend() -> str:
    """Determine embedding backend: 'local' (default) or 'mithril'."""
    try:
        from flask import current_app
        return current_app.config.get('RAG_EMBED_BACKEND', 'local')
    except RuntimeError:
        return os.environ.get('RAG_EMBED_BACKEND', 'local')


class RAGStore:
    """ProjectCompass wrapper around scomp-link's RAGPipeline.

    Adds: Flask config integration, Mithril cloud embedding option, LLM reranking.
    """

    def __init__(self, persist_dir: str | None = None, mithril_client=None, embedder=None):
        if persist_dir is None:
            persist_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'rag_data')

        # Determine embedder
        if embedder is not None:
            embed_fn = embedder
        elif _get_embed_backend() == 'mithril' and mithril_client is not None:
            embed_fn = _MithrilEmbedAdapter(mithril_client)
        else:
            embed_fn = None  # Let scomp-link use its default LocalEmbedder

        self._pipeline = RAGPipeline(persist_dir=persist_dir, embed_fn=embed_fn)
        self._mithril = mithril_client

    def _get_mithril(self):
        if self._mithril is None:
            from utils.mithril_client import get_client
            self._mithril = get_client()
        return self._mithril

    def _get_rerank_model(self) -> str:
        try:
            from flask import current_app
            return current_app.config.get('MITHRIL_RERANK_MODEL', 'gemini-2.5-flash')
        except RuntimeError:
            return os.environ.get('MITHRIL_RERANK_MODEL', 'gemini-2.5-flash')

    def build_index(self, analysis_name: str, chunks: list) -> dict:
        """Build index from pre-chunked content (ProjectCompass chunks files + comments externally)."""
        col_name = _sanitize_collection_name(analysis_name)

        # Delete existing collection if it exists
        try:
            self._pipeline.delete_index(analysis_name)
        except Exception:
            pass

        if not chunks:
            return {'status': 'empty', 'chunks': 0, 'collection': col_name}

        # Embed and store using the pipeline's internal ChromaDB client
        import time
        collection = self._pipeline._client.get_or_create_collection(
            name=col_name, metadata={'analysis': analysis_name}
        )

        texts = [c.text for c in chunks]
        batch_size = 32
        all_embeddings = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            embeddings = self._pipeline._embedder.embed(batch)
            all_embeddings.extend(embeddings)

        ids = [f'chunk_{i}' for i in range(len(chunks))]
        metadatas = [{
            'source_file': c.source_file,
            'chunk_type': c.chunk_type,
            'start_line': c.start_line,
            'end_line': c.end_line,
            'built_at': time.time(),
        } for c in chunks]

        collection.upsert(ids=ids, embeddings=all_embeddings, documents=texts, metadatas=metadatas)

        logger.info(f"RAG index built: {col_name} with {len(chunks)} chunks")
        return {'status': 'ok', 'chunks': len(chunks), 'collection': col_name}

    def query(self, analysis_name: str, question: str, top_k: int = 5) -> list[RetrievalResult]:
        return self._pipeline.query(analysis_name, question, top_k=top_k)

    def hybrid_query(self, analysis_name: str, question: str, top_k: int = 10) -> list[RetrievalResult]:
        return self._pipeline.hybrid_query(analysis_name, question, top_k=top_k)

    def rerank(self, query: str, results: list[RetrievalResult], top_n: int = 3) -> list[RetrievalResult]:
        """Rerank results using Mithril's /api/rerank endpoint."""
        if not results:
            return []
        try:
            client = self._get_mithril()
            model = self._get_rerank_model()
            documents = [r.text[:500] for r in results]
            ranked = client.rerank(model, query, documents, top_n=top_n)
            reranked = []
            for item in ranked:
                idx = item.get('index', 0)
                if idx < len(results):
                    result = results[idx]
                    result.score = item.get('relevance_score', result.score)
                    reranked.append(result)
            return reranked
        except Exception as e:
            logger.warning(f"Reranking failed, returning original order: {e}")
            return results[:top_n]

    def delete_index(self, analysis_name: str):
        try:
            self._pipeline.delete_index(analysis_name)
            logger.info(f"RAG index deleted for: {analysis_name}")
        except Exception:
            pass

    def has_index(self, analysis_name: str) -> bool:
        return self._pipeline.has_index(analysis_name)

    def index_status(self, analysis_name: str) -> dict:
        return self._pipeline.index_status(analysis_name)


class _MithrilEmbedAdapter:
    """Adapter: makes MithrilClient look like a LocalEmbedder for RAGPipeline."""

    def __init__(self, client):
        self._client = client
        self._model = os.environ.get('MITHRIL_EMBED_MODEL', 'gemini-embedding-exp-03-07')

    def embed(self, texts: list[str]) -> list[list[float]]:
        return self._client.embed(self._model, texts)

    def embed_query(self, text: str) -> list[float]:
        return self._client.embed(self._model, [text])[0]

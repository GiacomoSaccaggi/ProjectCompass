"""Tests for utils/rag_store.py"""
import tempfile

import pytest

from utils.chunker import Chunk
from utils.rag_store import RAGStore, RetrievalResult, _sanitize_collection_name


def test_sanitize_collection_name():
    assert _sanitize_collection_name('My Analysis') == 'rag_My_Analysis'
    assert _sanitize_collection_name('Test 123!@#') == 'rag_Test_123'
    assert _sanitize_collection_name('a') == 'rag_a__'


@pytest.fixture
def mock_mithril():
    """Mock embedder returning deterministic vectors."""
    class MockEmbedder:
        def embed(self, texts):
            return [[0.1, 0.2, 0.3] * 128 for _ in texts]
        def embed_query(self, text):
            return [0.1, 0.2, 0.3] * 128
    return MockEmbedder()


@pytest.fixture
def store(mock_mithril):
    with tempfile.TemporaryDirectory() as tmpdir:
        s = RAGStore(persist_dir=tmpdir, embedder=mock_mithril)
        yield s


def test_build_index(store, mock_mithril):
    chunks = [
        Chunk(text='def hello(): pass', source_file='main.py', chunk_type='python_function', start_line=1, end_line=2),
        Chunk(text='title: Test', source_file='metadata.yaml', chunk_type='yaml_section', start_line=1, end_line=1),
    ]
    result = store.build_index('Test Analysis', chunks)
    assert result['status'] == 'ok'
    assert result['chunks'] == 2


def test_has_index(store, mock_mithril):
    assert not store.has_index('Nonexistent')
    chunks = [Chunk(text='test', source_file='f.py', chunk_type='python_module')]
    store.build_index('Exists', chunks)
    assert store.has_index('Exists')


def test_delete_index(store, mock_mithril):
    chunks = [Chunk(text='test', source_file='f.py', chunk_type='python_module')]
    store.build_index('ToDelete', chunks)
    assert store.has_index('ToDelete')
    store.delete_index('ToDelete')
    assert not store.has_index('ToDelete')


def test_index_status(store, mock_mithril):
    status = store.index_status('Nonexistent')
    assert not status['exists']
    chunks = [Chunk(text='test', source_file='f.py', chunk_type='python_module')]
    store.build_index('WithStatus', chunks)
    status = store.index_status('WithStatus')
    assert status['exists']
    assert status['chunks'] == 1


def test_query(store, mock_mithril):
    chunks = [
        Chunk(text='machine learning model', source_file='main.py', chunk_type='python_function'),
        Chunk(text='data loading code', source_file='data.py', chunk_type='python_function'),
    ]
    store.build_index('QueryTest', chunks)
    results = store.query('QueryTest', 'what model?', top_k=2)
    assert len(results) >= 1
    assert all(isinstance(r, RetrievalResult) for r in results)


def test_build_empty_chunks(store):
    result = store.build_index('Empty', [])
    assert result['status'] == 'empty'

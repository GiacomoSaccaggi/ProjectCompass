"""Tests for MithrilClient embed() and rerank() methods."""
import json
from unittest.mock import MagicMock, patch

import httpx
import pytest

from utils.mithril_client import MithrilClient


@pytest.fixture
def client():
    return MithrilClient(host='http://localhost:16180')


def test_embed_success(client):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {'embeddings': [[0.1, 0.2, 0.3]]}
    mock_response.raise_for_status = MagicMock()

    with patch.object(client._http, 'post', return_value=mock_response):
        result = client.embed('gemini-embedding-exp-03-07', ['hello'])
        assert result == [[0.1, 0.2, 0.3]]


def test_embed_batch(client):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {'embeddings': [[0.1, 0.2], [0.3, 0.4]]}
    mock_response.raise_for_status = MagicMock()

    with patch.object(client._http, 'post', return_value=mock_response):
        result = client.embed('test', ['hello', 'world'])
        assert len(result) == 2


def test_embed_timeout(client):
    with patch.object(client._http, 'post', side_effect=httpx.TimeoutException('timeout')):
        with pytest.raises(RuntimeError, match='timed out'):
            client.embed('test', ['hello'])


def test_embed_connection_error(client):
    with patch.object(client._http, 'post', side_effect=httpx.ConnectError('fail')):
        with pytest.raises(RuntimeError, match='Cannot connect'):
            client.embed('test', ['hello'])


def test_rerank_success(client):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        'results': [
            {'index': 0, 'document': 'doc1', 'relevance_score': 0.9},
            {'index': 1, 'document': 'doc2', 'relevance_score': 0.3},
        ]
    }
    mock_response.raise_for_status = MagicMock()

    with patch.object(client._http, 'post', return_value=mock_response):
        result = client.rerank('gemini-2.5-flash', 'query', ['doc1', 'doc2'], top_n=2)
        assert len(result) == 2
        assert result[0]['relevance_score'] == 0.9


def test_rerank_timeout(client):
    with patch.object(client._http, 'post', side_effect=httpx.TimeoutException('timeout')):
        with pytest.raises(RuntimeError, match='timed out'):
            client.rerank('test', 'query', ['doc'])

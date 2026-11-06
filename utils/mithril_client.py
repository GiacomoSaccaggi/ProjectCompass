"""Mithril LLM client for ProjectCompass.
Lightweight HTTP client that talks to Mithril's Ollama-compatible API.
Lazy-loaded — the application works fully without Mithril running.
"""
import json

import httpx

from logging_config import logger

_client = None


class MithrilClient:
    """HTTP client for Mithril's Ollama-compatible API."""

    def __init__(self, host: str = "http://localhost:16180"):
        self.host = host.rstrip("/")
        self._http = httpx.Client(base_url=self.host, timeout=httpx.Timeout(10.0, read=120.0))

    def health(self) -> bool:
        """Check if Mithril is running."""
        try:
            r = self._http.get("/health", timeout=5.0)
            return r.status_code == 200
        except (httpx.ConnectError, httpx.TimeoutException):
            return False

    def list_models(self) -> list[str]:
        """Return list of available model names from /api/tags."""
        try:
            r = self._http.get("/api/tags", timeout=10.0)
            r.raise_for_status()
            data = r.json()
            return [m["name"] for m in data.get("models", [])]
        except Exception as e:
            logger.warning(f"Mithril list_models failed: {e}")
            return []

    def chat(self, model: str, messages: list[dict], stream: bool = False) -> str:
        """Send a chat request and return the full response text."""
        payload = {"model": model, "messages": messages, "stream": stream}
        try:
            if stream:
                return self._chat_collect_stream(payload)
            r = self._http.post("/api/chat", json=payload)
            r.raise_for_status()
            data = r.json()
            return data.get("message", {}).get("content", "")
        except httpx.TimeoutException:
            raise RuntimeError("Mithril request timed out") from None
        except httpx.ConnectError:
            raise RuntimeError("Cannot connect to Mithril") from None
        except Exception as e:
            raise RuntimeError(f"Mithril chat error: {e}") from e

    def chat_stream(self, model: str, messages: list[dict]):
        """Generator that yields response chunks (streaming)."""
        payload = {"model": model, "messages": messages, "stream": True}
        try:
            with self._http.stream("POST", "/api/chat", json=payload) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                        content = chunk.get("message", {}).get("content", "")
                        if content:
                            yield content
                        if chunk.get("done", False):
                            return
                    except json.JSONDecodeError:
                        continue
        except httpx.TimeoutException:
            yield "[Error: request timed out]"
        except httpx.ConnectError:
            yield "[Error: cannot connect to Mithril]"

    def _chat_collect_stream(self, payload: dict) -> str:
        """Internal: collect a streaming response into a single string."""
        parts = []
        with self._http.stream("POST", "/api/chat", json=payload) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                    content = chunk.get("message", {}).get("content", "")
                    if content:
                        parts.append(content)
                    if chunk.get("done", False):
                        break
                except json.JSONDecodeError:
                    continue
        return "".join(parts)

    def embed(self, model: str, texts: list[str]) -> list[list[float]]:
        """Generate embeddings via Mithril's /api/embed endpoint."""
        payload = {"model": model, "input": texts}
        try:
            r = self._http.post("/api/embed", json=payload, timeout=httpx.Timeout(30.0, read=120.0))
            r.raise_for_status()
            data = r.json()
            return data.get("embeddings", [])
        except httpx.TimeoutException:
            raise RuntimeError("Mithril embed request timed out") from None
        except httpx.ConnectError:
            raise RuntimeError("Cannot connect to Mithril for embeddings") from None
        except Exception as e:
            raise RuntimeError(f"Mithril embed error: {e}") from e

    def rerank(self, model: str, query: str, documents: list[str], top_n: int = 5) -> list[dict]:
        """Rerank documents by relevance using Mithril's /api/rerank endpoint."""
        payload = {"model": model, "query": query, "documents": documents, "top_n": top_n}
        try:
            r = self._http.post("/api/rerank", json=payload, timeout=httpx.Timeout(30.0, read=120.0))
            r.raise_for_status()
            data = r.json()
            return data.get("results", [])
        except httpx.TimeoutException:
            raise RuntimeError("Mithril rerank request timed out") from None
        except httpx.ConnectError:
            raise RuntimeError("Cannot connect to Mithril for reranking") from None
        except Exception as e:
            raise RuntimeError(f"Mithril rerank error: {e}") from e

    def close(self):
        self._http.close()


def get_client(host: str | None = None) -> MithrilClient:
    """Get or create the singleton MithrilClient instance."""
    global _client
    if _client is None:
        from flask import current_app
        if host is None:
            host = current_app.config.get('MITHRIL_HOST', 'http://localhost:16180')
        _client = MithrilClient(host)
        logger.info(f"MithrilClient initialized → {host}")
    return _client

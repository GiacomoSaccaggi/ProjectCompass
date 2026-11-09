# +----------------------------------------------+
# | APPLICATION FEATURE GATE                     |
# +----------------------------------------------+
"""Block routes and entry points for disabled application modules."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, ClassVar

from flask import Flask, abort, jsonify, request

from utils.app_settings import FeatureSettings


class FeatureGate:
    """Apply configured module availability to requests before authentication."""

    PREFIXES: ClassVar[dict[str, tuple[str, ...]]] = {
        'ai_chat': ('/chat',),
        'rag': ('/rag', '/chat/analysis/rag'),
        'k8s': ('/workers', '/flows', '/k8s'),
        'pipeline_builder': ('/pipeline_builder', '/save_pipeline'),
        'schedules': ('/schedules', '/schedule_analysis', '/delete_schedule', '/run_schedule_now'),
        'executions': (
            '/executions', '/outputs', '/physical_output', '/serve_output',
            '/execute_stream', '/execute_abort',
        ),
        'rawgraphs': ('/rawgraphs', '/graph_analysis'),
        'query_runner': ('/query_runner', '/query_results', '/save_query', '/api/query'),
        'db_connections': ('/connections',),
        'todo': ('/todo',),
    }

    def __init__(self, features: FeatureSettings) -> None:
        """Create a request gate using the validated module settings."""
        self._features = features

    def blocked_feature(self, path: str) -> str | None:
        """Return the disabled feature owning a path, if any."""
        if self._matches_execution_api(path) and not self._features.executions:
            return 'executions'
        for feature, prefixes in self.PREFIXES.items():
            if self._features.is_enabled(feature):
                continue
            if any(self._path_matches_prefix(path, prefix) for prefix in prefixes):
                return feature
        return None

    def install(self, app: Flask) -> None:
        """Install the gate before app-wide authentication handlers."""

        @app.before_request
        def gate_disabled_feature() -> tuple[Any, int] | None:
            feature = self.blocked_feature(request.path)
            if feature is None and not self._features.db_connections and self._uses_remote_connection():
                feature = 'db_connections'
            if feature is None:
                return None
            if self._expects_json():
                return jsonify({'error': 'Not found'}), 404
            abort(404)

    def _path_matches_prefix(self, path: str, prefix: str) -> bool:
        """Match exact routes and nested endpoints without matching lookalikes."""
        normalized_prefix = prefix.rstrip('/')
        normalized_path = path.rstrip('/')
        return normalized_path == normalized_prefix or normalized_path.startswith(f'{normalized_prefix}/')

    def _matches_execution_api(self, path: str) -> bool:
        """Identify the single run action nested under the analyses API."""
        return path.startswith('/api/analyses/') and path.endswith('/run')

    def _uses_remote_connection(self) -> bool:
        """Detect remote-source requests while preserving local Query Runner use."""
        if request.path in {'/query_results', '/query_results/'}:
            return bool(request.values.get('connection_id'))
        if request.path == '/api/query':
            payload = request.get_json(silent=True)
            if isinstance(payload, Mapping):
                return bool(payload.get('connection') or payload.get('connection_id'))
        return False

    def _expects_json(self) -> bool:
        """Prefer JSON 404 responses for APIs and explicitly JSON-oriented clients."""
        if request.path.startswith('/api/') or request.path.endswith('/tables') or request.is_json:
            return True
        accepted = request.accept_mimetypes.best_match(['text/html', 'application/json'])
        return accepted == 'application/json'

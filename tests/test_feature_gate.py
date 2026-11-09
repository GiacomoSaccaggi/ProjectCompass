# +----------------------------------------------+
# | FEATURE GATE TESTS                           |
# +----------------------------------------------+
"""Verify disabled modules return 404 and disappear from entry points."""

from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
from flask import Flask

from utils.app_settings import DefaultsSource, FeatureSettings, SettingsLoader, YamlFileSource
from utils.feature_gate import FeatureGate


class TestFeatureGate:
    """Exercise module route blocking, response format and rendered menus."""

    @pytest.mark.parametrize(
        ('feature', 'path'),
        [
            ('ai_chat', '/chat/ask'),
            ('rag', '/rag/status/demo'),
            ('k8s', '/flows/new'),
            ('pipeline_builder', '/save_pipeline/'),
            ('schedules', '/schedule_analysis/'),
            ('executions', '/execute_stream/demo'),
            ('rawgraphs', '/graph_analysis/'),
            ('query_runner', '/query_results/'),
            ('db_connections', '/connections/2/tables'),
            ('todo', '/todo'),
        ],
    )
    def test_disabled_module_prefix_is_blocked(self, feature: str, path: str) -> None:
        """Map every configured module prefix to its disabled feature."""
        gate = FeatureGate(self._features(**{feature: False}))

        assert gate.blocked_feature(path) == feature

    def test_route_prefixes_do_not_match_unrelated_lookalikes(self) -> None:
        """Keep routes whose paths only share a disabled prefix's letters."""
        gate = FeatureGate(self._features(ai_chat=False, db_connections=False))

        assert gate.blocked_feature('/chat') == 'ai_chat'
        assert gate.blocked_feature('/chatty') is None
        assert gate.blocked_feature('/overview') is None

    def test_execution_api_run_action_is_blocked(self) -> None:
        """Disable the API action that launches an analysis execution."""
        gate = FeatureGate(self._features(executions=False))

        assert gate.blocked_feature('/api/analyses/demo/run') == 'executions'
        assert gate.blocked_feature('/api/analyses/demo') is None

    def test_disabled_route_returns_html_or_json_404(self) -> None:
        """Return 404 before route authentication and preserve response formats."""
        app = Flask(__name__)
        gate = FeatureGate(self._features(ai_chat=False, db_connections=False))
        gate.install(app)

        @app.route('/health')
        def health() -> str:
            return 'ok'

        client = app.test_client()
        html_response = client.get('/chat')
        json_response = client.post('/chat/ask', json={'prompt': 'hello'})
        accepted_json_response = client.get('/chat/models', headers={'Accept': 'application/json'})
        tables_response = client.get('/connections/3/tables')

        assert html_response.status_code == 404
        assert html_response.mimetype == 'text/html'
        assert json_response.status_code == 404
        assert json_response.is_json
        assert json_response.get_json() == {'error': 'Not found'}
        assert accepted_json_response.status_code == 404
        assert accepted_json_response.is_json
        assert tables_response.status_code == 404
        assert tables_response.is_json
        assert client.get('/health').status_code == 200

    def test_disabling_connections_blocks_remote_queries_but_keeps_local(self) -> None:
        """Allow local Query Runner requests but reject saved-connection sources."""
        app = Flask(__name__)
        gate = FeatureGate(self._features(db_connections=False))

        @app.route('/api/query', methods=['POST'])
        def query_api() -> str:
            return 'local query accepted'

        @app.route('/query_results/', methods=['POST'])
        def query_results() -> str:
            return 'local query accepted'

        gate.install(app)
        client = app.test_client()
        local_response = client.post('/api/query', json={'sql': 'SELECT 1'})
        remote_response = client.post('/api/query', json={'sql': 'SELECT 1', 'connection': 1})
        remote_form_response = client.post('/query_results/', data={'connection_id': '1'})

        assert local_response.status_code == 200
        assert remote_response.status_code == 404
        assert remote_response.is_json
        assert remote_form_response.status_code == 404

    def test_disabled_features_disappear_from_header_and_data_entry_points(
        self, app: Flask, tmp_path: Path,
    ) -> None:
        """Hide disabled module links and palette commands in rendered HTML."""
        settings_path = tmp_path / 'projectcompass.yaml'
        settings_path.write_text(
            'features:\n'
            '  ai_chat: false\n'
            '  k8s: false\n'
            '  pipeline_builder: false\n'
            '  schedules: false\n'
            '  executions: false\n'
            '  rawgraphs: false\n'
            '  query_runner: false\n'
            '  db_connections: false\n'
            '  todo: false\n',
            encoding='utf-8',
        )
        settings = SettingsLoader((DefaultsSource(), YamlFileSource(settings_path, {}))).load()
        webapp = app.config['WEBAPP']
        template_settings = settings.for_templates()
        webapp.apply_settings(template_settings)
        top_container = webapp.html_parts['top_container']
        sidebar_menu = webapp.html_parts['sidebar_menu']

        with app.test_request_context('/'):
            data_list = app.jinja_env.get_template('data_list.html').render(
                pc=template_settings,
                all_data=[],
                head='',
                top_container='',
                sidebar_menu='',
                lineage={},
            )
            query_results = app.jinja_env.get_template('query_results.html').render(
                pc=template_settings,
                head='',
                top_container='',
                sidebar_menu='',
                connections=[SimpleNamespace(id=1, name='Warehouse')],
                selected_connection_id=None,
                query='SELECT 1',
                message='',
                show_res='none',
                columns=[],
                df=pd.DataFrame(),
                total_pages=1,
                page=1,
            )

        hidden_paths = (
            '/chat', '/workers', '/flows', '/pipeline_builder', '/schedules/', '/executions',
        )
        for hidden_path in hidden_paths:
            assert hidden_path not in sidebar_menu
        hidden_labels = (
            'Go to Chat', 'Pipeline Builder', 'Query Runner', 'DB Connections',
            'Schedules', 'RAWGraphs', 'Todo',
        )
        for hidden_label in hidden_labels:
            assert hidden_label not in top_container
        assert '/query_runner' not in data_list
        assert '/connections/' not in data_list
        assert '/all_data' in sidebar_menu
        assert 'Warehouse' not in query_results
        assert 'action="/graph_analysis/"' not in query_results
        assert 'id="connection_id"' not in query_results

    def test_feature_gate_precedes_global_authentication(self, app: Flask) -> None:
        """Run feature checks before the login hook can redirect disabled routes."""
        handler_names = [handler.__name__ for handler in app.before_request_funcs[None]]

        assert handler_names.index('gate_disabled_feature') < handler_names.index('require_login')

    def _features(self, **overrides: bool) -> FeatureSettings:
        """Create a feature settings object with modules enabled by default."""
        values = {key: True for key in FeatureSettings._FEATURE_KEYS}
        values.update(overrides)
        return FeatureSettings(**values)

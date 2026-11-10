# +----------------------------------------------+
# | APPLICATION SETTINGS TESTS                   |
# +----------------------------------------------+
"""Verify settings precedence, validation, interpolation and app wiring."""

import re
from pathlib import Path

import pytest
from flask import Flask

from utils.app_settings import (
    AppSettings,
    ConnectorParameterSpec,
    ConnectorSettings,
    DefaultsSource,
    DockerWorkerSettings,
    EnvOverrideSource,
    ExternalWorkerSettings,
    SettingsLoader,
    WorkerSettings,
    YamlFileSource,
)
from utils.settings_errors import SettingsFileError, SettingsValidationError


class TestSettingsLoader:
    """Exercise the complete settings source chain and its validation rules."""

    def test_defaults_match_current_application_values(self) -> None:
        """Preserve current branding, theme and enabled modules by default."""
        settings = SettingsLoader((DefaultsSource(),)).load()

        assert isinstance(settings, AppSettings)
        assert settings.branding.app_name == 'ProjectCompass'
        assert settings.branding.page_title == 'ProjectCompass'
        assert settings.branding.logo_icon_url == '/static/img/logo.svg'
        assert settings.theme.primary_color == '#222831'
        assert settings.demo.enabled is False
        assert settings.features.is_enabled('ai_chat') is False
        assert settings.features.is_enabled('executions') is True
        assert settings.features.is_enabled('schedules') is True
        assert settings.features.is_enabled('k8s') is True
        assert settings.connection_errors == ()
        assert isinstance(settings.workers, WorkerSettings)
        assert settings.workers.provider == 'docker'
        assert settings.workers.auto_provision is True
        assert settings.workers.auto_cleanup is True
        assert settings.workers.docker == DockerWorkerSettings(
            image='docker.io/k0sproject/k0s:latest',
            cpus='2',
            memory='4g',
            auto_cleanup=True,
            network='bridge',
            join_token_file=None,
            controller_container=None,
            ready_timeout_seconds=120,
        )
        assert settings.workers.external == ExternalWorkerSettings(
            ensure_script=None,
            release_script=None,
            status_script=None,
        )
        connector_names = [c.name for c in settings.connectors]
        assert connector_names == ['python_script', 'sql_query']
        assert all(isinstance(c, ConnectorSettings) and c.builtin for c in settings.connectors)
        assert all(c.image == 'python:3.12-slim' for c in settings.connectors)

    def test_yaml_values_are_overridden_by_typed_environment_variables(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Apply precedence defaults < YAML < environment, parsing boolean values."""
        config_path = tmp_path / 'projectcompass.yaml'
        config_path.write_text(
            'branding:\n  app_name: YAML Compass\n'
            'theme:\n  primary_color: "#123"\n'
            'demo:\n  enabled: true\n'
            'features:\n  ai_chat: true\n',
            encoding='utf-8',
        )
        monkeypatch.setenv('PC_BRANDING__APP_NAME', 'Environment Compass')
        monkeypatch.setenv('PC_THEME__PRIMARY_COLOR', '#ABCDEF')
        monkeypatch.setenv('PC_DEMO__ENABLED', 'no')
        monkeypatch.setenv('PC_FEATURES__AI_CHAT', '0')
        monkeypatch.setenv('PC_THEME__DEFAULT_DARK_MODE', 'yes')
        settings = SettingsLoader.from_environment(str(config_path), str(tmp_path)).load()

        assert settings.branding.app_name == 'Environment Compass'
        assert settings.branding.page_title == 'Environment Compass'
        assert settings.theme.primary_color == '#ABCDEF'
        assert settings.theme.default_dark_mode is True
        assert settings.demo.enabled is False
        assert settings.features.ai_chat is False

    def test_environment_source_parses_integer_values(self) -> None:
        """Parse integer overrides according to the supplied settings schema."""
        source = EnvOverrideSource({'PC_SAMPLE__COUNT': '42'}, defaults={'sample': {'count': 1}})

        assert source.load() == {'sample': {'count': 42}}

    def test_yaml_interpolates_environment_variables_and_defaults(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Substitute set variables and use the declared fallback for missing ones."""
        config_path = tmp_path / 'projectcompass.yaml'
        config_path.write_text(
            'branding:\n  app_name: "${APP_NAME:-Fallback Compass}"\n'
            '  sidebar_title: "${SIDEBAR_TITLE}"\n',
            encoding='utf-8',
        )
        monkeypatch.setenv('SIDEBAR_TITLE', 'Workspace')
        settings = SettingsLoader.from_environment(str(config_path), str(tmp_path)).load()

        assert settings.branding.app_name == 'Fallback Compass'
        assert settings.branding.sidebar_title == 'Workspace'

    def test_missing_default_config_file_is_optional(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Start with defaults when DATA_DIR has no projectcompass.yaml."""
        monkeypatch.delenv('PC_CONFIG_FILE', raising=False)

        settings = SettingsLoader.from_environment(None, str(tmp_path)).load()

        assert settings.branding.app_name == 'ProjectCompass'

    @pytest.mark.parametrize(
        ('yaml_text', 'key'),
        [
            ('theme:\n  primary_color: red\n', 'theme.primary_color'),
            ("theme:\n  font_family: 'Arial; body { color: red }'\n", 'theme.font_family'),
            ('branding:\n  favicon_url: javascript:alert(1)\n', 'branding.favicon_url'),
            ("branding:\n  favicon_url: 'https://cdn.example/\" onerror=alert(1)'\n", 'branding.favicon_url'),
            ('features:\n  unknown_module: true\n', 'features.unknown_module'),
        ],
    )
    def test_invalid_settings_name_the_rejected_key(
        self, tmp_path: Path, yaml_text: str, key: str,
    ) -> None:
        """Reject unsafe URLs, invalid colors and unknown feature names clearly."""
        config_path = tmp_path / 'projectcompass.yaml'
        config_path.write_text(yaml_text, encoding='utf-8')

        with pytest.raises(SettingsValidationError, match=key.replace('.', r'\.')):
            SettingsLoader((DefaultsSource(), YamlFileSource(config_path, {}))).load()

    def test_invalid_environment_boolean_names_its_setting(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Reject unsupported boolean strings rather than treating them as truthy."""
        monkeypatch.setenv('PC_FEATURES__AI_CHAT', 'sometimes')

        with pytest.raises(SettingsValidationError, match='features.ai_chat'):
            SettingsLoader.from_environment(None, '/nonexistent').load()

    def test_malformed_yaml_raises_settings_file_error(self, tmp_path: Path) -> None:
        """Report malformed YAML with the typed settings-file exception."""
        config_path = tmp_path / 'projectcompass.yaml'
        config_path.write_text('branding: [unterminated', encoding='utf-8')

        with pytest.raises(SettingsFileError, match='Invalid YAML'):
            SettingsLoader((DefaultsSource(), YamlFileSource(config_path, {}))).load()

    def test_unresolved_preset_variable_is_skipped_without_logging_secret(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Skip an incomplete preset and report only its unresolved variable name."""
        config_path = tmp_path / 'projectcompass.yaml'
        config_path.write_text(
            'connections:\n'
            '  - name: Warehouse\n'
            '    type: postgres\n'
            '    host: db.example.com\n'
            '    port: 5432\n'
            '    database: analytics\n'
            '    username: reader\n'
            '    password: "${MISSING_PASSWORD}"\n',
            encoding='utf-8',
        )

        settings = SettingsLoader((DefaultsSource(), YamlFileSource(config_path, {}))).load()

        assert settings.connections == ()
        assert settings.connection_errors == (
            'connections[0]: unresolved environment variable(s) MISSING_PASSWORD; entry skipped.',
        )
        assert 'MISSING_PASSWORD' in settings.connection_errors[0]
        assert 'reader' not in caplog.text

    def test_valid_preset_is_validated_by_dialect_registry(self, tmp_path: Path) -> None:
        """Normalize a valid database preset for the managed connection service."""
        config_path = tmp_path / 'projectcompass.yaml'
        config_path.write_text(
            'connections:\n'
            '  - name: Warehouse\n'
            '    type: postgres\n'
            '    host: db.example.com\n'
            '    port: 5432\n'
            '    database: analytics\n'
            '    username: reader\n'
            '    password: secret-value\n'
            '    extra_params:\n'
            '      sslmode: require\n',
            encoding='utf-8',
        )

        settings = SettingsLoader((DefaultsSource(), YamlFileSource(config_path, {}))).load()
        preset = settings.connections[0]

        assert preset.db_type == 'postgres'
        assert preset.to_form() == {
            'name': 'Warehouse',
            'db_type': 'postgres',
            'host': 'db.example.com',
            'port': '5432',
            'database': 'analytics',
            'username': 'reader',
            'password': 'secret-value',
            'extra_params': 'sslmode=require',
        }
        assert 'secret-value' not in repr(preset)

    def test_unknown_non_feature_keys_are_warned_without_values(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Warn on typo keys without echoing any supplied value to logs."""
        config_path = tmp_path / 'projectcompass.yaml'
        config_path.write_text(
            'branding:\n  app_nam: confidential-value\n',
            encoding='utf-8',
        )

        SettingsLoader((DefaultsSource(), YamlFileSource(config_path, {}))).load()

        assert 'branding.app_nam' in caplog.text
        assert 'confidential-value' not in caplog.text

    def test_example_yaml_loads_without_errors_or_warnings(
        self, caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Ensure projectcompass.example.yaml stays in sync with the settings schema."""
        example_path = Path(__file__).resolve().parent.parent / 'projectcompass.example.yaml'

        settings = SettingsLoader((DefaultsSource(), YamlFileSource(example_path, {}))).load()

        assert settings.workers.provider == 'docker'
        assert settings.workers.docker.image == 'docker.io/k0sproject/k0s:latest'
        assert [c.name for c in settings.connectors] == ['python_script', 'sql_query']
        assert 'Unknown application settings key' not in caplog.text

    def test_workers_yaml_and_environment_overrides(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Merge 2-level and 3-level PC_WORKERS__* environment overrides into WorkerSettings."""
        config_path = tmp_path / 'projectcompass.yaml'
        config_path.write_text(
            'workers:\n'
            '  provider: docker\n'
            '  docker:\n'
            '    image: docker.io/k0sproject/k0s:v1.30\n'
            '    cpus: 4\n'
            '    memory: 8g\n'
            '    auto_cleanup: false\n'
            '    network: bridge\n'
            '    join_token_file: /run/secrets/worker.token\n'
            '    controller_container: k0s-controller\n'
            '    ready_timeout_seconds: 90\n',
            encoding='utf-8',
        )
        monkeypatch.setenv('PC_WORKERS__PROVIDER', 'external')
        monkeypatch.setenv('PC_WORKERS__DOCKER__IMAGE', 'docker.io/k0sproject/k0s:custom')
        monkeypatch.setenv('PC_WORKERS__DOCKER__CPUS', '6')
        monkeypatch.setenv('PC_WORKERS__DOCKER__MEMORY', '16g')
        monkeypatch.setenv('PC_WORKERS__DOCKER__AUTO_CLEANUP', 'true')
        monkeypatch.setenv('PC_WORKERS__DOCKER__NETWORK', 'host')
        monkeypatch.setenv('PC_WORKERS__DOCKER__JOIN_TOKEN_FILE', '/run/token')
        monkeypatch.setenv('PC_WORKERS__DOCKER__CONTROLLER_CONTAINER', 'k0s-controller-2')
        monkeypatch.setenv('PC_WORKERS__DOCKER__READY_TIMEOUT_SECONDS', '150')
        monkeypatch.setenv('PC_WORKERS__AUTO_PROVISION', 'false')
        monkeypatch.setenv('PC_WORKERS__AUTO_CLEANUP', 'false')
        monkeypatch.setenv('PC_WORKERS__EXTERNAL__ENSURE_SCRIPT', '/opt/workers/ensure.sh')
        monkeypatch.setenv('PC_WORKERS__EXTERNAL__RELEASE_SCRIPT', '/opt/workers/release.sh')
        monkeypatch.setenv('PC_WORKERS__EXTERNAL__STATUS_SCRIPT', '/opt/workers/status.sh')

        settings = SettingsLoader.from_environment(str(config_path), str(tmp_path)).load()

        assert settings.workers.provider == 'external'
        assert settings.workers.docker.image == 'docker.io/k0sproject/k0s:custom'
        assert settings.workers.docker.cpus == '6'
        assert settings.workers.docker.memory == '16g'
        assert settings.workers.docker.auto_cleanup is True
        assert settings.workers.docker.network == 'host'
        assert settings.workers.docker.join_token_file == '/run/token'
        assert settings.workers.docker.controller_container == 'k0s-controller-2'
        assert settings.workers.docker.ready_timeout_seconds == 150
        assert settings.workers.auto_provision is False
        assert settings.workers.auto_cleanup is False
        assert settings.workers.external.ensure_script == '/opt/workers/ensure.sh'
        assert settings.workers.external.release_script == '/opt/workers/release.sh'
        assert settings.workers.external.status_script == '/opt/workers/status.sh'

    def test_custom_connectors_merge_with_builtins_and_support_mapping_and_list_params(
        self, tmp_path: Path,
    ) -> None:
        """Preserve built-in connectors while adding custom YAML connectors with typed parameters."""
        config_path = tmp_path / 'projectcompass.yaml'
        config_path.write_text(
            'connectors:\n'
            '  - name: trino_etl\n'
            '    description: "Run Trino ETL job"\n'
            '    image: "custom-trino-runner:latest"\n'
            '    parameters:\n'
            '      query: {type: text, required: true}\n'
            '      connection: {type: select, source: connections}\n'
            '  - name: spark_batch\n'
            '    description: "Spark batch step"\n'
            '    image: "custom-spark-runner:latest"\n'
            '    parameters:\n'
            '      - name: partitions\n'
            '        type: number\n'
            '        default: 8\n'
            '      - name: mode\n'
            '        type: select\n'
            '        options: [append, overwrite]\n',
            encoding='utf-8',
        )

        settings = SettingsLoader((DefaultsSource(), YamlFileSource(config_path, {}))).load()
        by_name = {c.name: c for c in settings.connectors}

        assert list(by_name.keys()) == ['python_script', 'sql_query', 'trino_etl', 'spark_batch']
        assert by_name['python_script'].builtin is True
        assert by_name['sql_query'].builtin is True

        trino = by_name['trino_etl']
        assert trino.builtin is False
        assert trino.image == 'custom-trino-runner:latest'
        assert trino.parameters == (
            ConnectorParameterSpec(name='query', param_type='text', required=True),
            ConnectorParameterSpec(name='connection', param_type='select', required=False, source='connections'),
        )
        assert trino.parameters[0].type == 'text'

        spark = by_name['spark_batch']
        assert spark.parameters == (
            ConnectorParameterSpec(name='partitions', param_type='number', required=False, default=8),
            ConnectorParameterSpec(
                name='mode', param_type='select', required=False, options=('append', 'overwrite'),
            ),
        )

    @pytest.mark.parametrize(
        ('yaml_text', 'key'),
        [
            ('workers:\n  provider: unsupported_provider\n', 'workers.provider'),
            ('workers:\n  docker:\n    cpus: ""\n', 'workers.docker.cpus'),
            ('workers:\n  docker:\n    auto_cleanup: invalid\n', 'workers.docker.auto_cleanup'),
            ('connectors: not-a-list\n', 'connectors'),
            (
                'connectors:\n  - name: bad_param\n    parameters:\n      p1: {type: invalid_kind}\n',
                'connectors[0].parameters.p1.type',
            ),
            (
                'connectors:\n  - name: dup\n  - name: dup\n',
                'connectors[1].name',
            ),
        ],
    )
    def test_invalid_workers_and_connectors_raise_validation_error(
        self, tmp_path: Path, yaml_text: str, key: str,
    ) -> None:
        """Reject invalid worker providers and malformed connector schemas."""
        config_path = tmp_path / 'projectcompass.yaml'
        config_path.write_text(yaml_text, encoding='utf-8')

        with pytest.raises(SettingsValidationError, match=re.escape(key)):
            SettingsLoader((DefaultsSource(), YamlFileSource(config_path, {}))).load()


class TestSettingsAppIntegration:
    """Verify settings are available through Flask configuration and templates."""

    def test_app_stores_settings_and_injects_pc(self, app: Flask) -> None:
        """Expose the same loaded settings in app config and template context."""
        context: dict[str, object] = {}
        with app.app_context():
            app.update_template_context(context)
            rendered = app.jinja_env.from_string('{{ pc.connectors | tojson }}').render(**context)

        assert context['pc'].branding is app.config['PC_SETTINGS'].branding
        assert context['pc'].workers is app.config['PC_SETTINGS'].workers
        assert context['pc'].connectors is app.config['PC_SETTINGS'].connectors
        assert not hasattr(context['pc'], 'connections')
        assert '"python_script"' in rendered
        assert '"sql_query"' in rendered

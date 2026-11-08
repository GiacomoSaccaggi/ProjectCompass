# +----------------------------------------------+
# | APPLICATION SETTINGS TESTS                   |
# +----------------------------------------------+
"""Verify settings precedence, validation, interpolation and app wiring."""

from pathlib import Path

import pytest
from flask import Flask

from utils.app_settings import (
    AppSettings,
    DefaultsSource,
    EnvOverrideSource,
    SettingsLoader,
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
        assert settings.branding.logo_icon_url == '/static/img/logo_icon.png'
        assert settings.theme.primary_color == '#222831'
        assert settings.demo.enabled is True
        assert settings.features.is_enabled('ai_chat') is True
        assert settings.connection_errors == ()

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


class TestSettingsAppIntegration:
    """Verify settings are available through Flask configuration and templates."""

    def test_app_stores_settings_and_injects_pc(self, app: Flask) -> None:
        """Expose the same loaded settings in app config and template context."""
        context: dict[str, object] = {}
        with app.app_context():
            app.update_template_context(context)

        assert context['pc'].branding is app.config['PC_SETTINGS'].branding
        assert not hasattr(context['pc'], 'connections')

# +----------------------------------------------+
# | APPLICATION SETTINGS                         |
# +----------------------------------------------+
"""Load immutable application settings from defaults, YAML and environment overrides."""

from __future__ import annotations

import copy
import logging
import os
import re
from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, ClassVar
from urllib.parse import urlsplit

import yaml

from utils.db_dialects import ConnectionParams, DialectRegistry
from utils.db_errors import DbConnectionError
from utils.settings_errors import SettingsFileError, SettingsValidationError


@dataclass(frozen=True)
class BrandingSettings:
    """Hold branding values used by rendered pages."""

    app_name: str
    page_title: str
    sidebar_title: str
    logo_url: str | None
    logo_icon_url: str
    logo_text_url: str
    favicon_url: str
    backgrounds: Mapping[str, str]
    demo_notice: NoticeSettings
    footer: FooterSettings

    def __post_init__(self) -> None:
        object.__setattr__(self, 'backgrounds', MappingProxyType(dict(self.backgrounds)))


@dataclass(frozen=True)
class NoticeSettings:
    """Configure whether the demo notice is shown and what it says."""

    enabled: bool
    text: str


@dataclass(frozen=True)
class FooterSettings:
    """Configure shared footer text and visibility."""

    enabled: bool
    about: str
    slogan: str
    copyright: str


@dataclass(frozen=True)
class ThemeSettings:
    """Hold the application color, font and dark-mode defaults."""

    primary_color: str
    accent_color: str
    highlight_color: str
    hover_color: str
    font_family: str
    default_dark_mode: bool


@dataclass(frozen=True)
class DemoSettings:
    """Configure optional demo content and alternate seed directories."""

    enabled: bool
    analyses_dir: str | None
    data_dir: str | None


@dataclass(frozen=True)
class FeatureSettings:
    """Control whether individual application modules are available."""

    ai_chat: bool
    rag: bool
    k8s: bool
    pipeline_builder: bool
    schedules: bool
    executions: bool
    rawgraphs: bool
    query_runner: bool
    db_connections: bool
    todo: bool

    _FEATURE_KEYS: ClassVar[tuple[str, ...]] = (
        'ai_chat', 'rag', 'k8s', 'pipeline_builder', 'schedules', 'executions',
        'rawgraphs', 'query_runner', 'db_connections', 'todo',
    )

    def is_enabled(self, key: str) -> bool:
        """Return the configured state for a known module."""
        if key not in self._FEATURE_KEYS:
            raise KeyError(f'Unknown feature: {key}')
        return bool(getattr(self, key))


@dataclass(frozen=True)
class PresetConnection:
    """Represent a validated connection declared in the settings file."""

    name: str
    db_type: str
    fields: Mapping[str, str] = field(repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, 'fields', MappingProxyType(dict(self.fields)))

    def to_form(self) -> dict[str, str]:
        """Return form-compatible values for the managed connection service."""
        return {'name': self.name, 'db_type': self.db_type, **self.fields}


@dataclass(frozen=True)
class AppSettings:
    """Expose the validated settings used by startup and templates."""

    branding: BrandingSettings
    theme: ThemeSettings
    demo: DemoSettings
    features: FeatureSettings
    connections: tuple[PresetConnection, ...]
    connection_errors: tuple[str, ...]

    def for_templates(self) -> PublicAppSettings:
        """Return the non-secret settings exposed to Jinja templates."""
        return PublicAppSettings(self.branding, self.theme, self.demo, self.features)


@dataclass(frozen=True)
class PublicAppSettings:
    """Expose presentation settings without database credentials or sync errors."""

    branding: BrandingSettings
    theme: ThemeSettings
    demo: DemoSettings
    features: FeatureSettings


class BaseSettingsSource(ABC):
    """Provide one layer of settings values in precedence order."""

    @abstractmethod
    def load(self) -> dict[str, Any]:
        """Return this source's settings as a nested mapping."""


class DefaultsSource(BaseSettingsSource):
    """Provide built-in values that reproduce the current application defaults."""

    def load(self) -> dict[str, Any]:
        """Return a fresh copy of the documented default settings."""
        return {
            'branding': {
                'app_name': 'ProjectCompass',
                'page_title': None,
                'sidebar_title': 'Analysis',
                'logo_url': None,
                'logo_icon_url': '/static/img/logo_icon.png',
                'logo_text_url': '/static/img/logo_text.png',
                'favicon_url': '/static/img/logo.png',
                'backgrounds': {
                    'data': '/static/img/background1.PNG',
                    'analysis': '/static/img/background2.PNG',
                    'upload': '/static/img/upload_analysis.png',
                },
                'demo_notice': {
                    'enabled': True,
                    'text': (
                        'DEMO Project Notice: This is a demonstration-only project intended for evaluation purposes. '
                        'Although it may resemble a final product, the creators assume no liability for any errors, '
                        'malfunctions, or damages resulting from its use.'
                    ),
                },
                'footer': {
                    'enabled': True,
                    'about': 'About ProjectCompass',
                    'slogan': 'Organization Is Everything®',
                    'copyright': 'Copyright ©2025 ProjectCompass. All rights reserved.',
                },
            },
            'theme': {
                'primary_color': '#222831',
                'accent_color': '#3F51B5',
                'highlight_color': '#4DFFD6',
                'hover_color': '#DCD2FF',
                'font_family': '"Raleway", sans-serif',
                'default_dark_mode': False,
            },
            'demo': {'enabled': True, 'analyses_dir': None, 'data_dir': None},
            'features': {
                'ai_chat': True,
                'rag': True,
                'k8s': True,
                'pipeline_builder': True,
                'schedules': True,
                'executions': True,
                'rawgraphs': True,
                'query_runner': True,
                'db_connections': True,
                'todo': True,
            },
            'connections': [],
        }


class YamlFileSource(BaseSettingsSource):
    """Read and interpolate a YAML settings file."""

    def __init__(
        self,
        path: str | Path | None,
        environ: Mapping[str, str],
        optional_if_missing: bool = False,
    ) -> None:
        """Create a YAML source.

        Args:
            path: YAML path, or ``None`` to contribute no values.
            environ: Environment used to interpolate ``${VAR}`` expressions.
            optional_if_missing: Allow a missing default settings file.
        """
        self._path = Path(path) if path is not None else None
        self._environ = environ
        self._optional_if_missing = optional_if_missing

    def load(self) -> dict[str, Any]:
        """Read YAML values and interpolate environment references."""
        if self._path is None:
            return {}
        if not self._path.exists() and self._optional_if_missing:
            return {}
        try:
            content = self._path.read_text(encoding='utf-8')
        except OSError as exc:
            raise SettingsFileError(f'Unable to read settings file: {self._path}') from exc
        try:
            values = yaml.safe_load(content)
        except yaml.YAMLError as exc:
            raise SettingsFileError(f'Invalid YAML in settings file: {self._path}') from exc
        if values is None:
            return {}
        if not isinstance(values, Mapping):
            raise SettingsValidationError('settings: the YAML document must contain a mapping.')
        return self._interpolate(dict(values))

    def _interpolate(self, value: Any) -> Any:
        """Recursively replace environment references without exposing values."""
        if isinstance(value, str):
            pattern = re.compile(r'\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}')

            def replace(match: re.Match[str]) -> str:
                variable = match.group(1)
                default = match.group(2)
                found = self._environ.get(variable)
                if found is not None and (found != '' or default is None):
                    return found
                if default is not None:
                    return default
                return match.group(0)

            return pattern.sub(replace, value)
        if isinstance(value, Mapping):
            return {key: self._interpolate(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._interpolate(item) for item in value]
        return value


class EnvOverrideSource(BaseSettingsSource):
    """Build nested settings overrides from typed ``PC_*`` variables."""

    _BOOLEAN_VALUES = {
        'true': True, '1': True, 'yes': True,
        'false': False, '0': False, 'no': False,
    }

    def __init__(
        self,
        environ: Mapping[str, str],
        prefix: str = 'PC_',
        defaults: Mapping[str, Any] | None = None,
    ) -> None:
        """Create an environment source.

        Args:
            environ: Environment variables to inspect.
            prefix: Prefix that selects application settings overrides.
            defaults: Schema values used to parse bool, int and string types.
        """
        self._environ = environ
        self._prefix = prefix
        self._defaults = defaults if defaults is not None else DefaultsSource().load()

    def load(self) -> dict[str, Any]:
        """Return nested overrides with primitive types parsed from the schema."""
        overrides: dict[str, Any] = {}
        for env_key, raw_value in self._environ.items():
            if not env_key.startswith(self._prefix) or '__' not in env_key[len(self._prefix):]:
                continue
            path = [part.lower() for part in env_key[len(self._prefix):].split('__')]
            if not all(path):
                continue
            dotted_key = '.'.join(path)
            expected = self._default_at_path(path)
            parsed = self._parse_value(raw_value, expected, dotted_key)
            self._set_nested(overrides, path, parsed)
        return overrides

    def _default_at_path(self, path: Sequence[str]) -> Any:
        """Find the schema value for a nested environment override."""
        value: Any = self._defaults
        for part in path:
            if not isinstance(value, Mapping) or part not in value:
                return None
            value = value[part]
        return value

    def _parse_value(self, value: str, expected: Any, key: str) -> Any:
        """Parse an environment value using its built-in setting type."""
        if isinstance(expected, bool):
            parsed = self._BOOLEAN_VALUES.get(value.strip().lower())
            if parsed is None:
                raise SettingsValidationError(f'{key}: expected a boolean value (true/false/1/0/yes/no).')
            return parsed
        if isinstance(expected, int) and not isinstance(expected, bool):
            try:
                return int(value)
            except ValueError as exc:
                raise SettingsValidationError(f'{key}: expected an integer value.') from exc
        return value

    def _set_nested(self, target: dict[str, Any], path: Sequence[str], value: Any) -> None:
        """Place an override in a nested settings mapping."""
        current = target
        for part in path[:-1]:
            nested = current.get(part)
            if not isinstance(nested, dict):
                nested = {}
                current[part] = nested
            current = nested
        current[path[-1]] = value


class SettingsLoader:
    """Merge ordered sources and validate a single immutable settings object."""

    _COLOR_KEYS = ('primary_color', 'accent_color', 'highlight_color', 'hover_color')
    _URL_PATTERN = re.compile(r'\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}')
    _SENSITIVE_EXTRA_KEYS = {
        'password', 'passwd', 'pwd', 'secret', 'token', 'key', 'api_key', 'access_key',
    }

    def __init__(self, sources: Sequence[BaseSettingsSource]) -> None:
        """Create a loader for a precedence-ordered source sequence."""
        self._sources = tuple(sources)
        self._defaults = DefaultsSource().load()
        self._logger = logging.getLogger(__name__)

    def load(self) -> AppSettings:
        """Load, merge and validate settings from every configured source."""
        merged: dict[str, Any] = {}
        for source in self._sources:
            merged = self._deep_merge(merged, source.load())
        self._validate_feature_keys(merged.get('features'))
        self._warn_unknown_keys(merged, self._defaults)
        self._validate_interpolations(merged)
        return self._build_settings(merged)

    @classmethod
    def from_environment(cls, config_file: str | None, data_dir: str) -> SettingsLoader:
        """Create the standard defaults → YAML → environment source chain."""
        environ = os.environ
        selected_path = config_file or environ.get('PC_CONFIG_FILE')
        if selected_path:
            yaml_source = YamlFileSource(selected_path, environ)
        else:
            yaml_source = YamlFileSource(
                Path(data_dir) / 'projectcompass.yaml', environ, optional_if_missing=True,
            )
        defaults = DefaultsSource().load()
        return cls((DefaultsSource(), yaml_source, EnvOverrideSource(environ, defaults=defaults)))

    def _deep_merge(self, base: Mapping[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
        """Recursively merge mappings, replacing scalar and sequence values."""
        result = copy.deepcopy(dict(base))
        for key, value in override.items():
            if isinstance(result.get(key), Mapping) and isinstance(value, Mapping):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = copy.deepcopy(value)
        return result

    def _validate_feature_keys(self, features: Any) -> None:
        """Reject unknown module flags before general unknown-key warnings."""
        if not isinstance(features, Mapping):
            return
        for key in features:
            if key not in FeatureSettings._FEATURE_KEYS:
                raise SettingsValidationError(f'features.{key}: unknown feature key.')

    def _warn_unknown_keys(self, values: Mapping[str, Any], schema: Mapping[str, Any], prefix: str = '') -> None:
        """Log unknown configuration keys without including their values."""
        for key, value in values.items():
            dotted_key = f'{prefix}.{key}' if prefix else str(key)
            if key not in schema:
                self._logger.warning('Unknown application settings key: %s', dotted_key)
                continue
            expected = schema[key]
            if isinstance(value, Mapping) and isinstance(expected, Mapping):
                self._warn_unknown_keys(value, expected, dotted_key)

    def _validate_interpolations(self, values: Mapping[str, Any]) -> None:
        """Reject unresolved variables outside preset connections by variable name only."""
        for section, value in values.items():
            if section == 'connections':
                continue
            self._check_unresolved_value(value, str(section))

    def _check_unresolved_value(self, value: Any, key: str) -> None:
        """Find unresolved interpolation tokens in nested non-secret settings."""
        if isinstance(value, str):
            match = self._URL_PATTERN.search(value)
            if match:
                raise SettingsValidationError(
                    f'{key}: unresolved environment variable {match.group(1)}.'
                )
        elif isinstance(value, Mapping):
            for nested_key, nested_value in value.items():
                self._check_unresolved_value(nested_value, f'{key}.{nested_key}')
        elif isinstance(value, list):
            for index, nested_value in enumerate(value):
                self._check_unresolved_value(nested_value, f'{key}[{index}]')

    def _build_settings(self, values: Mapping[str, Any]) -> AppSettings:
        """Validate settings sections and instantiate frozen value objects."""
        branding_values = self._require_mapping(values, 'branding')
        backgrounds = self._require_mapping(branding_values, 'backgrounds', 'branding')
        notice_values = self._require_mapping(branding_values, 'demo_notice', 'branding')
        footer_values = self._require_mapping(branding_values, 'footer', 'branding')
        theme_values = self._require_mapping(values, 'theme')
        demo_values = self._require_mapping(values, 'demo')
        feature_values = self._require_mapping(values, 'features')

        app_name = self._required_string(branding_values, 'app_name', 'branding')
        page_title_value = branding_values.get('page_title')
        page_title = app_name if page_title_value is None else self._string_value(
            page_title_value, 'branding.page_title', allow_empty=False,
        )
        sidebar_title = self._required_string(branding_values, 'sidebar_title', 'branding')
        logo_url = self._optional_string(branding_values.get('logo_url'), 'branding.logo_url')
        logo_icon_url = self._required_string(branding_values, 'logo_icon_url', 'branding')
        logo_text_url = self._required_string(branding_values, 'logo_text_url', 'branding')
        favicon_url = self._required_string(branding_values, 'favicon_url', 'branding')

        validated_backgrounds: dict[str, str] = {}
        for name in ('data', 'analysis', 'upload'):
            if name not in backgrounds:
                raise SettingsValidationError(f'branding.backgrounds.{name}: is required.')
            validated_backgrounds[name] = self._validate_url(
                backgrounds[name], f'branding.backgrounds.{name}',
            )
        self._validate_url(logo_url, 'branding.logo_url', allow_none=True)
        self._validate_url(logo_icon_url, 'branding.logo_icon_url')
        self._validate_url(logo_text_url, 'branding.logo_text_url')
        self._validate_url(favicon_url, 'branding.favicon_url')

        notice = NoticeSettings(
            enabled=self._boolean_value(notice_values.get('enabled'), 'branding.demo_notice.enabled'),
            text=self._string_value(notice_values.get('text'), 'branding.demo_notice.text'),
        )
        footer_about = self._string_value(footer_values.get('about'), 'branding.footer.about')
        if footer_about == 'About ProjectCompass':
            footer_about = f'About {app_name}'
        footer_copyright = self._string_value(footer_values.get('copyright'), 'branding.footer.copyright')
        if footer_copyright == 'Copyright ©2025 ProjectCompass. All rights reserved.':
            footer_copyright = footer_copyright.replace('ProjectCompass', app_name)
        footer = FooterSettings(
            enabled=self._boolean_value(footer_values.get('enabled'), 'branding.footer.enabled'),
            about=footer_about,
            slogan=self._string_value(footer_values.get('slogan'), 'branding.footer.slogan'),
            copyright=footer_copyright,
        )
        branding = BrandingSettings(
            app_name=app_name,
            page_title=page_title,
            sidebar_title=sidebar_title,
            logo_url=logo_url,
            logo_icon_url=logo_icon_url,
            logo_text_url=logo_text_url,
            favicon_url=favicon_url,
            backgrounds=validated_backgrounds,
            demo_notice=notice,
            footer=footer,
        )

        colors: dict[str, str] = {}
        for key in self._COLOR_KEYS:
            color = self._required_string(theme_values, key, 'theme')
            if re.fullmatch(r'#[0-9A-Fa-f]{3}(?:[0-9A-Fa-f]{3})?', color) is None:
                raise SettingsValidationError(f'theme.{key}: expected a #RGB or #RRGGBB color.')
            colors[key] = color
        font_family = self._required_string(theme_values, 'font_family', 'theme')
        font_family_pattern = r'''(?:\s*(?:"[\w -]+"|'[\w -]+'|[\w-]+)\s*)(?:,\s*(?:"[\w -]+"|'[\w -]+'|[\w-]+)\s*)*'''
        if re.fullmatch(font_family_pattern, font_family) is None:
            raise SettingsValidationError('theme.font_family: contains unsupported CSS characters.')
        theme = ThemeSettings(
            **colors,
            font_family=font_family,
            default_dark_mode=self._boolean_value(theme_values.get('default_dark_mode'), 'theme.default_dark_mode'),
        )

        demo = DemoSettings(
            enabled=self._boolean_value(demo_values.get('enabled'), 'demo.enabled'),
            analyses_dir=self._optional_string(demo_values.get('analyses_dir'), 'demo.analyses_dir'),
            data_dir=self._optional_string(demo_values.get('data_dir'), 'demo.data_dir'),
        )
        features = FeatureSettings(**{
            key: self._boolean_value(feature_values.get(key), f'features.{key}')
            for key in FeatureSettings._FEATURE_KEYS
        })
        connections, connection_errors = self._parse_connections(values.get('connections', []))
        return AppSettings(branding, theme, demo, features, connections, connection_errors)

    def _parse_connections(self, raw_connections: Any) -> tuple[tuple[PresetConnection, ...], tuple[str, ...]]:
        """Validate preset connections individually while retaining safe diagnostics."""
        if not isinstance(raw_connections, list):
            raise SettingsValidationError('connections: expected a list of preset connections.')
        registry = DialectRegistry()
        connections: list[PresetConnection] = []
        errors: list[str] = []
        names: set[str] = set()
        for index, raw_connection in enumerate(raw_connections):
            connection, error = self._parse_connection(index, raw_connection, registry)
            if error:
                errors.append(error)
                continue
            if connection is None:
                continue
            normalized_name = connection.name.casefold()
            if normalized_name in names:
                errors.append(f'connections[{index}]: duplicate preset connection name; entry skipped.')
                continue
            names.add(normalized_name)
            connections.append(connection)
        return tuple(connections), tuple(errors)

    def _parse_connection(
        self,
        index: int,
        raw_connection: Any,
        registry: DialectRegistry,
    ) -> tuple[PresetConnection | None, str | None]:
        """Validate and normalize one preset without exposing any credentials."""
        prefix = f'connections[{index}]'
        if not isinstance(raw_connection, Mapping):
            return None, f'{prefix}: expected a mapping; entry skipped.'

        unresolved = self._unresolved_variables(raw_connection)
        if unresolved:
            variables = ', '.join(sorted(unresolved))
            return None, f'{prefix}: unresolved environment variable(s) {variables}; entry skipped.'

        allowed_keys = {'name', 'type', 'host', 'port', 'database', 'username', 'password', 'file_path',
                        'extra_params', 'custom_uri'}
        for key in raw_connection:
            if key not in allowed_keys:
                self._logger.warning('Unknown application settings key: %s.%s', prefix, key)

        name = raw_connection.get('name')
        db_type = raw_connection.get('type')
        if not isinstance(name, str) or not name.strip() or len(name.strip()) > 100:
            return None, f'{prefix}: name must be a non-empty string of at most 100 characters; entry skipped.'
        if not isinstance(db_type, str) or not db_type.strip():
            return None, f'{prefix}: type is required; entry skipped.'
        name = name.strip()
        db_type = db_type.strip()
        try:
            dialect = registry.get(db_type)
        except DbConnectionError:
            return None, f'{prefix}: unsupported database type; entry skipped.'

        extra_params = raw_connection.get('extra_params', {})
        if not isinstance(extra_params, Mapping):
            return None, f'{prefix}.extra_params: expected a mapping; entry skipped.'
        normalized_extra_params: dict[str, str] = {}
        for key, value in extra_params.items():
            if not isinstance(key, str) or not key.strip() or not self._is_scalar(value):
                return None, f'{prefix}.extra_params: invalid key or value; entry skipped.'
            normalized_key = key.strip().lower().replace('-', '_')
            if normalized_key in self._SENSITIVE_EXTRA_KEYS or normalized_key.endswith(
                ('_password', '_secret', '_token', '_key'),
            ):
                return None, f'{prefix}.extra_params: credentials must use password or custom_uri; entry skipped.'
            normalized_extra_params[key.strip()] = str(value)

        dialect_fields = {field_spec.key for field_spec in dialect.fields}
        form_fields: dict[str, str] = {}
        for key in ('host', 'port', 'database', 'username', 'password', 'file_path', 'custom_uri'):
            value = raw_connection.get(key)
            if value is None:
                continue
            if key not in dialect_fields:
                return None, f'{prefix}.{key}: field is not valid for this database type; entry skipped.'
            if not self._is_scalar(value):
                return None, f'{prefix}.{key}: expected a scalar value; entry skipped.'
            form_fields[key] = str(value)

        try:
            port = int(form_fields['port']) if form_fields.get('port') else None
        except ValueError:
            return None, f'{prefix}.port: expected an integer; entry skipped.'
        params = ConnectionParams(
            type_key=db_type,
            host=form_fields.get('host') or None,
            port=port,
            database=form_fields.get('database') or None,
            username=form_fields.get('username') or None,
            password=form_fields.get('password') or None,
            file_path=form_fields.get('file_path') or None,
            custom_uri=form_fields.get('custom_uri') or None,
            extra_params=normalized_extra_params,
        )
        try:
            dialect.build_uri(params)
            dialect.list_tables_query(params)
        except DbConnectionError as exc:
            return None, f'{prefix}: invalid connection fields ({exc}); entry skipped.'
        except (TypeError, ValueError):
            return None, f'{prefix}: invalid connection fields; entry skipped.'

        form_fields['extra_params'] = '\n'.join(
            f'{key}={value}' for key, value in normalized_extra_params.items()
        )
        return PresetConnection(name, db_type, form_fields), None

    def _unresolved_variables(self, value: Any) -> set[str]:
        """Return unresolved environment variable names without their values."""
        unresolved: set[str] = set()
        if isinstance(value, str):
            unresolved.update(match.group(1) for match in self._URL_PATTERN.finditer(value))
        elif isinstance(value, Mapping):
            for nested_value in value.values():
                unresolved.update(self._unresolved_variables(nested_value))
        elif isinstance(value, list):
            for nested_value in value:
                unresolved.update(self._unresolved_variables(nested_value))
        return unresolved

    def _is_scalar(self, value: Any) -> bool:
        """Return whether a YAML connection value can be represented as text."""
        return isinstance(value, (str, int, float, bool))

    def _require_mapping(
        self,
        values: Mapping[str, Any],
        key: str,
        prefix: str = '',
    ) -> Mapping[str, Any]:
        """Get a required nested settings mapping."""
        value = values.get(key)
        dotted_key = f'{prefix}.{key}' if prefix else key
        if not isinstance(value, Mapping):
            raise SettingsValidationError(f'{dotted_key}: expected a mapping.')
        return value

    def _required_string(self, values: Mapping[str, Any], key: str, prefix: str) -> str:
        """Get a required non-empty string setting."""
        return self._string_value(values.get(key), f'{prefix}.{key}', allow_empty=False)

    def _optional_string(self, value: Any, key: str) -> str | None:
        """Validate an optional string value."""
        if value is None:
            return None
        return self._string_value(value, key)

    def _string_value(self, value: Any, key: str, allow_empty: bool = True) -> str:
        """Validate a string setting and optionally require non-empty content."""
        if not isinstance(value, str) or (not allow_empty and not value.strip()):
            suffix = 'a non-empty string' if not allow_empty else 'a string'
            raise SettingsValidationError(f'{key}: expected {suffix}.')
        return value

    def _boolean_value(self, value: Any, key: str) -> bool:
        """Validate a boolean setting without accepting ambiguous strings."""
        if not isinstance(value, bool):
            raise SettingsValidationError(f'{key}: expected a boolean value.')
        return value

    def _validate_url(self, value: Any, key: str, allow_none: bool = False) -> str | None:
        """Validate a URL against supported HTTP, local and image-data schemes."""
        if value is None and allow_none:
            return None
        url = self._string_value(value, key, allow_empty=False)
        if re.search(r'''[\s"'()<>\\{}]''', url):
            raise SettingsValidationError(f'{key}: contains characters unsafe for HTML or CSS URLs.')
        lowered = url.lower()
        if lowered.startswith('data:image/'):
            return url
        if url.startswith('/') and not url.startswith('//'):
            return url
        parsed = urlsplit(url)
        if parsed.scheme in {'http', 'https'} and parsed.netloc:
            return url
        raise SettingsValidationError(f'{key}: expected an http(s)://, /... or data:image/... URL.')

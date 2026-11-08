# +----------------------------------------------+
# | DATABASE DIALECT REGISTRY                    |
# +----------------------------------------------+
"""Describe supported database forms and ConnectorX connection syntax."""

import re
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import quote, quote_plus, urlencode

from utils.db_errors import ConnectionValidationError, UnknownDialectError


@dataclass(frozen=True)
class FieldSpec:
    """Describe a single connection-form field."""

    key: str
    label: str
    input_type: str
    required: bool
    placeholder: str = ''
    help: str = ''


@dataclass(frozen=True)
class ConnectionParams:
    """Hold the values used to construct one database connection URI."""

    type_key: str | None = None
    host: str | None = None
    port: int | None = None
    database: str | None = None
    username: str | None = None
    password: str | None = None
    file_path: str | None = None
    custom_uri: str | None = None
    extra_params: dict[str, str] = field(default_factory=dict)


class BaseDbDialect(ABC):
    """Define the fields and SQL behavior required for a database type."""

    type_key: str
    label: str
    icon: str = 'fa-database'
    default_port: int | None

    @property
    @abstractmethod
    def fields(self) -> list[FieldSpec]:
        """Return the fields displayed for this connection type."""

    @abstractmethod
    def build_uri(self, params: ConnectionParams) -> str:
        """Build a ConnectorX URI from the supplied connection values."""

    @abstractmethod
    def wrap_limit(self, sql: str, max_rows: int) -> str:
        """Wrap a query with a dialect-specific result-row limit."""

    @abstractmethod
    def list_tables_query(self, params: ConnectionParams | None = None) -> str:
        """Return a query that lists tables visible to this connection."""

    def test_query(self) -> str:
        """Return a lightweight query used to test a connection."""
        return 'SELECT 1'

    def _network_fields(self, database_label: str = 'Database') -> list[FieldSpec]:
        """Return the common host-based connection fields."""
        return [
            FieldSpec('host', 'Host', 'text', True, 'db.example.com'),
            FieldSpec('port', 'Port', 'number', True, str(self.default_port or '')),
            FieldSpec('database', database_label, 'text', True, 'database_name'),
            FieldSpec('username', 'Username', 'text', True, 'database_user'),
            FieldSpec('password', 'Password', 'password', False, help='Leave blank only if the database allows it.'),
        ]

    def _validate_required_fields(self, params: ConnectionParams) -> None:
        """Reject missing values before constructing a URI."""
        for field_spec in self.fields:
            value = getattr(params, field_spec.key)
            if field_spec.key == 'port' and value is None:
                value = self.default_port
            if field_spec.key == 'port' and field_spec.required and (
                not isinstance(value, int) or value < 1 or value > 65535
            ):
                raise ConnectionValidationError('Port must be between 1 and 65535.')
            if field_spec.required and (value is None or value == ''):
                raise ConnectionValidationError(f'{field_spec.label} is required.')

    def _network_uri(self, scheme: str, params: ConnectionParams) -> str:
        """Build a URL-encoded URI for a host-based database."""
        self._validate_required_fields(params)
        host = (params.host or '').strip()
        if ':' in host and not host.startswith('['):
            host = f'[{host}]'
        port = params.port or self.default_port
        host_port = f'{host}:{port}' if port is not None else host
        username = quote_plus(params.username or '')
        password = quote_plus(params.password or '')
        auth = f'{username}:{password}@' if username else ''
        database = quote(params.database or '', safe='')
        return self._append_extra_params(f'{scheme}://{auth}{host_port}/{database}', params.extra_params)

    def _append_extra_params(self, uri: str, extra_params: dict[str, str]) -> str:
        """Append URL-encoded driver parameters without changing credentials."""
        if not extra_params:
            return uri
        return f'{uri}?{urlencode(sorted(extra_params.items()))}'

    def _wrap_query(self, sql: str, max_rows: int, clause: str, use_top: bool = False,
                    use_as: bool = True) -> str:
        """Apply a safe outer row limit using the dialect's limit syntax."""
        if max_rows < 1:
            raise ConnectionValidationError('The maximum row count must be greater than zero.')
        query = sql.strip().rstrip(';').strip()
        if not query:
            raise ConnectionValidationError('The SQL query cannot be empty.')
        alias = ' AS _pc_limited_query' if use_as else ' _pc_limited_query'
        if use_top:
            return f'SELECT TOP ({max_rows}) * FROM ({query}){alias}'
        return f'SELECT * FROM ({query}){alias} {clause}'


class PostgresDialect(BaseDbDialect):
    """PostgreSQL connection and SQL conventions."""

    type_key = 'postgres'
    label = 'PostgreSQL'
    default_port = 5432

    @property
    def fields(self) -> list[FieldSpec]:
        return self._network_fields()

    def build_uri(self, params: ConnectionParams) -> str:
        return self._network_uri('postgresql', params)

    def wrap_limit(self, sql: str, max_rows: int) -> str:
        return self._wrap_query(sql, max_rows, f'LIMIT {max_rows}')

    def list_tables_query(self, params: ConnectionParams | None = None) -> str:
        return (
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema NOT IN ('pg_catalog', 'information_schema') "
            "AND table_type = 'BASE TABLE' ORDER BY table_name"
        )


class RedshiftDialect(PostgresDialect):
    """Amazon Redshift connection and SQL conventions."""

    type_key = 'redshift'
    label = 'Redshift'
    default_port = 5439

    def build_uri(self, params: ConnectionParams) -> str:
        return self._network_uri('redshift', params)

    def list_tables_query(self, params: ConnectionParams | None = None) -> str:
        return (
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema NOT IN ('pg_catalog', 'information_schema') "
            "AND table_type = 'BASE TABLE' ORDER BY table_name"
        )


class MySQLDialect(BaseDbDialect):
    """MySQL connection and SQL conventions."""

    type_key = 'mysql'
    label = 'MySQL'
    default_port = 3306

    @property
    def fields(self) -> list[FieldSpec]:
        return self._network_fields()

    def build_uri(self, params: ConnectionParams) -> str:
        return self._network_uri('mysql', params)

    def wrap_limit(self, sql: str, max_rows: int) -> str:
        return self._wrap_query(sql, max_rows, f'LIMIT {max_rows}')

    def list_tables_query(self, params: ConnectionParams | None = None) -> str:
        return (
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = DATABASE() AND table_type = 'BASE TABLE' ORDER BY table_name"
        )


class MariaDBDialect(MySQLDialect):
    """MariaDB connection syntax, using ConnectorX's MySQL protocol."""

    type_key = 'mariadb'
    label = 'MariaDB'


class MsSQLDialect(BaseDbDialect):
    """Microsoft SQL Server connection and SQL conventions."""

    type_key = 'mssql'
    label = 'SQL Server'
    default_port = 1433

    @property
    def fields(self) -> list[FieldSpec]:
        return self._network_fields()

    def build_uri(self, params: ConnectionParams) -> str:
        return self._network_uri('mssql', params)

    def wrap_limit(self, sql: str, max_rows: int) -> str:
        if max_rows < 1:
            raise ConnectionValidationError('The maximum row count must be greater than zero.')
        query = sql.strip().rstrip(';').strip()
        if not query:
            raise ConnectionValidationError('The SQL query cannot be empty.')
        select_span = self._find_main_select(query)
        if select_span is None:
            raise ConnectionValidationError('SQL Server queries must contain a SELECT statement.')
        _, select_end = select_span
        insertion_point = select_end
        distinct_match = re.match(r'\s+DISTINCT\b', query[insertion_point:], flags=re.IGNORECASE)
        if distinct_match:
            insertion_point += distinct_match.end()
        remaining = query[insertion_point:]
        top_match = re.match(r'\s+TOP\s*(?:\(\s*([^)]*)\s*\)|(\d+))', remaining, flags=re.IGNORECASE)
        if top_match:
            raw_limit = top_match.group(1) or top_match.group(2)
            if not raw_limit or not raw_limit.strip().isdigit():
                raise ConnectionValidationError('Existing SQL Server TOP limits must use an integer row count.')
            suffix = remaining[top_match.end():].lstrip()
            if re.match(r'(?:PERCENT\b|WITH\s+TIES\b)', suffix, flags=re.IGNORECASE):
                raise ConnectionValidationError('TOP PERCENT and WITH TIES are not allowed with the safety limit.')
            final_limit = min(int(raw_limit), max_rows)
            prefix = query[:insertion_point + top_match.start()]
            return f'{prefix} TOP ({final_limit}) {suffix}'
        prefix = query[:insertion_point]
        return f'{prefix} TOP ({max_rows}) {remaining.lstrip()}'

    def _find_main_select(self, query: str) -> tuple[int, int] | None:
        """Find the top-level SELECT while ignoring nested queries and quoted text."""
        index = 0
        depth = 0
        while index < len(query):
            if query.startswith('--', index):
                line_end = query.find('\n', index)
                index = len(query) if line_end < 0 else line_end + 1
                continue
            if query.startswith('/*', index):
                comment_end = query.find('*/', index + 2)
                index = len(query) if comment_end < 0 else comment_end + 2
                continue
            character = query[index]
            if character in ('\'', '"', '`'):
                quote_character = character
                index += 1
                while index < len(query):
                    if query[index] == quote_character:
                        if index + 1 < len(query) and query[index + 1] == quote_character:
                            index += 2
                            continue
                        index += 1
                        break
                    index += 1
                continue
            if character == '[':
                index += 1
                while index < len(query):
                    if query[index] == ']':
                        if index + 1 < len(query) and query[index + 1] == ']':
                            index += 2
                            continue
                        index += 1
                        break
                    index += 1
                continue
            if character == '(':
                depth += 1
                index += 1
                continue
            if character == ')':
                depth = max(0, depth - 1)
                index += 1
                continue
            if character.isalpha() or character == '_':
                start = index
                while index < len(query) and (query[index].isalnum() or query[index] in '_$'):
                    index += 1
                if depth == 0 and query[start:index].upper() == 'SELECT':
                    return start, index
                continue
            index += 1
        return None

    def list_tables_query(self, params: ConnectionParams | None = None) -> str:
        return (
            "SELECT TABLE_SCHEMA + '.' + TABLE_NAME AS table_name FROM INFORMATION_SCHEMA.TABLES "
            "WHERE TABLE_TYPE = 'BASE TABLE' ORDER BY TABLE_SCHEMA, TABLE_NAME"
        )


class OracleDialect(BaseDbDialect):
    """Oracle connection and SQL conventions."""

    type_key = 'oracle'
    label = 'Oracle'
    default_port = 1521

    @property
    def fields(self) -> list[FieldSpec]:
        return self._network_fields('Service name')

    def build_uri(self, params: ConnectionParams) -> str:
        return self._network_uri('oracle', params)

    def wrap_limit(self, sql: str, max_rows: int) -> str:
        return self._wrap_query(sql, max_rows, f'FETCH FIRST {max_rows} ROWS ONLY', use_as=False)

    def list_tables_query(self, params: ConnectionParams | None = None) -> str:
        return 'SELECT table_name FROM user_tables ORDER BY table_name'


class SQLiteDialect(BaseDbDialect):
    """SQLite file connection and SQL conventions."""

    type_key = 'sqlite'
    label = 'SQLite'
    default_port = None

    @property
    def fields(self) -> list[FieldSpec]:
        return [FieldSpec('file_path', 'Database file', 'text', True, '/path/to/database.sqlite')]

    def build_uri(self, params: ConnectionParams) -> str:
        self._validate_required_fields(params)
        file_path = quote(str(Path(params.file_path or '').expanduser().resolve()), safe='/')
        return self._append_extra_params(f'sqlite://{file_path}', params.extra_params)

    def wrap_limit(self, sql: str, max_rows: int) -> str:
        return self._wrap_query(sql, max_rows, f'LIMIT {max_rows}')

    def list_tables_query(self, params: ConnectionParams | None = None) -> str:
        return (
            "SELECT name AS table_name FROM sqlite_master "
            "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )


class ClickHouseDialect(BaseDbDialect):
    """ClickHouse connection and SQL conventions."""

    type_key = 'clickhouse'
    label = 'ClickHouse'
    default_port = 9000

    @property
    def fields(self) -> list[FieldSpec]:
        return self._network_fields()

    def build_uri(self, params: ConnectionParams) -> str:
        return self._network_uri('clickhouse', params)

    def wrap_limit(self, sql: str, max_rows: int) -> str:
        return self._wrap_query(sql, max_rows, f'LIMIT {max_rows}')

    def list_tables_query(self, params: ConnectionParams | None = None) -> str:
        return 'SELECT name AS table_name FROM system.tables WHERE database = currentDatabase() ORDER BY name'


class TrinoDialect(BaseDbDialect):
    """Trino connection and SQL conventions."""

    type_key = 'trino'
    label = 'Trino'
    default_port = 8080

    @property
    def fields(self) -> list[FieldSpec]:
        return self._network_fields('Catalog')

    def build_uri(self, params: ConnectionParams) -> str:
        return self._network_uri('trino', params)

    def wrap_limit(self, sql: str, max_rows: int) -> str:
        return self._wrap_query(sql, max_rows, f'LIMIT {max_rows}')

    def list_tables_query(self, params: ConnectionParams | None = None) -> str:
        return (
            "SELECT table_schema || '.' || table_name AS table_name FROM information_schema.tables "
            "WHERE table_schema <> 'information_schema' ORDER BY table_schema, table_name"
        )


class BigQueryDialect(BaseDbDialect):
    """BigQuery connection and SQL conventions."""

    type_key = 'bigquery'
    label = 'BigQuery'
    default_port = None

    @property
    def fields(self) -> list[FieldSpec]:
        return [
            FieldSpec('file_path', 'Credentials JSON file', 'text', True, '/path/to/credentials.json'),
            FieldSpec('database', 'Project / dataset', 'text', False, 'project.dataset'),
        ]

    def build_uri(self, params: ConnectionParams) -> str:
        self._validate_required_fields(params)
        file_path = quote(str(Path(params.file_path or '').expanduser().resolve()), safe='/')
        return self._append_extra_params(f'bigquery://{file_path}', params.extra_params)

    def wrap_limit(self, sql: str, max_rows: int) -> str:
        return self._wrap_query(sql, max_rows, f'LIMIT {max_rows}')

    def list_tables_query(self, params: ConnectionParams | None = None) -> str:
        database = params.database if params else None
        if not database:
            return 'SELECT table_name FROM INFORMATION_SCHEMA.TABLES ORDER BY table_name'
        if not re.fullmatch(r'[A-Za-z0-9_-]+\.[A-Za-z0-9_]+', database):
            raise ConnectionValidationError('BigQuery project and dataset must use project.dataset format.')
        return f'SELECT table_name FROM `{database}.INFORMATION_SCHEMA.TABLES` ORDER BY table_name'


class CustomUriDialect(BaseDbDialect):
    """Advanced connection type for a user-provided ConnectorX URI."""

    type_key = 'custom'
    label = 'Custom URI'
    default_port = None

    @property
    def fields(self) -> list[FieldSpec]:
        return [FieldSpec('custom_uri', 'Connection URI', 'text', True, 'postgresql://user:password@host:5432/database')]

    def build_uri(self, params: ConnectionParams) -> str:
        self._validate_required_fields(params)
        return (params.custom_uri or '').strip()

    def wrap_limit(self, sql: str, max_rows: int) -> str:
        return self._wrap_query(sql, max_rows, f'LIMIT {max_rows}')

    def list_tables_query(self, params: ConnectionParams | None = None) -> str:
        return (
            'SELECT table_name FROM information_schema.tables '
            "WHERE table_type = 'BASE TABLE' ORDER BY table_name"
        )


class DialectRegistry:
    """Look up the supported database dialects and their form metadata."""

    def __init__(self) -> None:
        """Register each supported dialect exactly once."""
        dialects: list[BaseDbDialect] = [
            PostgresDialect(),
            RedshiftDialect(),
            MySQLDialect(),
            MariaDBDialect(),
            MsSQLDialect(),
            OracleDialect(),
            SQLiteDialect(),
            ClickHouseDialect(),
            TrinoDialect(),
            BigQueryDialect(),
            CustomUriDialect(),
        ]
        self._dialects: dict[str, BaseDbDialect] = {dialect.type_key: dialect for dialect in dialects}

    def get(self, type_key: str) -> BaseDbDialect:
        """Return a dialect by its stable form key.

        Args:
            type_key: The database type selected by the user.

        Raises:
            UnknownDialectError: If the type key is not registered.
        """
        try:
            return self._dialects[type_key]
        except KeyError as exc:
            raise UnknownDialectError(f'Unsupported database type: {type_key}') from exc

    def all(self) -> list[BaseDbDialect]:
        """Return all registered dialects in display order."""
        return list(self._dialects.values())

    def to_json_specs(self) -> list[dict[str, Any]]:
        """Serialize dialect form metadata for the guided connection form."""
        return [
            {
                'type_key': dialect.type_key,
                'label': dialect.label,
                'icon': dialect.icon,
                'default_port': dialect.default_port,
                'fields': [asdict(field_spec) for field_spec in dialect.fields],
            }
            for dialect in self.all()
        ]

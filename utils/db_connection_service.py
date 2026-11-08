# +----------------------------------------------+
# | DATABASE CONNECTION SERVICE                  |
# +----------------------------------------------+
"""Manage saved database connections and execute remote read queries."""

from __future__ import annotations

import json
import re
import time
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit, urlunsplit

import connectorx
import pandas as pd
from flask import current_app

from logging_config import logger
from models import DbConnection, db, log_action
from utils.credential_vault import CredentialVault
from utils.db_dialects import BaseDbDialect, ConnectionParams, DialectRegistry
from utils.db_errors import (
    ConnectionNotFoundError,
    ConnectionValidationError,
    DbConnectionError,
    RemoteQueryError,
)


@dataclass(frozen=True)
class TestResult:
    """Describe the result and duration of a connection test."""

    ok: bool
    message: str
    elapsed_ms: int


class DbConnectionService:
    """Store credentials securely and route read-only queries through ConnectorX."""

    def __init__(self, vault: CredentialVault | None = None, registry: DialectRegistry | None = None,
                 max_rows: int | None = None) -> None:
        """Create a service from Flask configuration and optional test dependencies.

        Args:
            vault: Optional credential vault, primarily for isolated tests.
            registry: Optional registry of database dialects.
            max_rows: Optional override for the remote result safety limit.
        """
        self._registry = registry or DialectRegistry()
        data_dir = Path(str(current_app.config['DATA_DIR']))
        self._vault = vault or CredentialVault(
            current_app.config.get('DB_CONNECTIONS_KEY'),
            data_dir / 'tmp' / '.db_connections.key',
        )
        self._max_rows = int(max_rows if max_rows is not None else current_app.config['DB_CONNECTIONS_MAX_ROWS'])
        if self._max_rows < 1:
            raise ConnectionValidationError('DB_CONNECTIONS_MAX_ROWS must be greater than zero.')

    def list(self) -> list[DbConnection]:
        """Return saved connections in name order."""
        return DbConnection.query.order_by(DbConnection.name).all()

    def save(
        self,
        form: Mapping[str, str],
        user_id: int | None,
        conn_id: int | None = None,
        allow_managed: bool = False,
    ) -> DbConnection:
        """Create or update a connection after validating its form values.

        Args:
            form: Submitted connection fields.
            user_id: User responsible for creating a new connection.
            conn_id: Existing connection ID for an update.
            allow_managed: Permit updates reserved for configuration synchronization.

        Returns:
            The persisted connection model.

        Raises:
            ConnectionValidationError: If form values are incomplete or the name is duplicated.
            ConnectionNotFoundError: If ``conn_id`` does not identify a saved connection.
        """
        type_key = (form.get('db_type') or '').strip()
        dialect = self._registry.get(type_key)
        name = (form.get('name') or '').strip()
        if not name:
            raise ConnectionValidationError('Connection name is required.')
        if len(name) > 100:
            raise ConnectionValidationError('Connection name must be 100 characters or fewer.')

        connection = db.session.get(DbConnection, conn_id) if conn_id is not None else None
        if conn_id is not None and connection is None:
            raise ConnectionNotFoundError(f'Connection {conn_id} was not found.')
        if connection is not None and connection.managed and not allow_managed:
            raise ConnectionValidationError('This connection is managed by configuration and cannot be changed here.')
        duplicate_query = DbConnection.query.filter_by(name=name)
        if conn_id is not None:
            duplicate_query = duplicate_query.filter(DbConnection.id != conn_id)
        if duplicate_query.first() is not None:
            raise ConnectionValidationError('A connection with this name already exists.')

        params = self._params_from_form(
            type_key, form, connection, preserve_empty_secrets=not allow_managed,
        )
        dialect.build_uri(params)
        extra_params_json = json.dumps(params.extra_params, sort_keys=True) if params.extra_params else None
        if type_key == 'custom':
            password_encrypted = None
            custom_uri_encrypted = self._vault.encrypt(params.custom_uri or '')
        else:
            password_encrypted = self._vault.encrypt(params.password) if params.password else None
            custom_uri_encrypted = None

        if connection is None:
            connection = DbConnection(name=name, db_type=type_key, created_by=user_id, managed=allow_managed)
            db.session.add(connection)
        elif allow_managed:
            connection.managed = True
        connection.name = name
        connection.db_type = type_key
        connection.host = params.host
        connection.port = params.port
        connection.database = params.database
        connection.username = params.username
        connection.password_encrypted = password_encrypted
        connection.file_path = params.file_path
        connection.extra_params_json = extra_params_json
        connection.custom_uri_encrypted = custom_uri_encrypted

        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise
        return connection

    def delete(self, conn_id: int, allow_managed: bool = False) -> None:
        """Delete a saved connection unless managed deletion is explicitly allowed."""
        connection = db.session.get(DbConnection, conn_id)
        if connection is None:
            raise ConnectionNotFoundError(f'Connection {conn_id} was not found.')
        if connection.managed and not allow_managed:
            raise ConnectionValidationError('This connection is managed by configuration and cannot be deleted here.')
        db.session.delete(connection)
        db.session.commit()

    def matches(self, connection: DbConnection, form: Mapping[str, str]) -> bool:
        """Return whether a saved connection already matches normalized config values."""
        name = (form.get('name') or '').strip()
        type_key = (form.get('db_type') or '').strip()
        if connection.name != name or connection.db_type != type_key:
            return False
        params = self._params_from_form(type_key, form, preserve_empty_secrets=False)
        return self._params_from_connection(connection) == params

    def test(self, params: ConnectionParams) -> TestResult:
        """Run the dialect's lightweight test query without saving credentials."""
        started = time.perf_counter()
        try:
            dialect = self._dialect_for_params(params)
            self._validate_file_connection(params)
            uri = dialect.build_uri(params)
            connectorx.read_sql(uri, dialect.test_query(), return_type='pandas')
        except DbConnectionError as exc:
            return TestResult(False, str(exc), self._elapsed_ms(started))
        except Exception:
            return TestResult(
                False,
                'Connection test failed. Check the host, credentials, database, and network settings.',
                self._elapsed_ms(started),
            )
        return TestResult(True, 'Connection test succeeded.', self._elapsed_ms(started))

    def test_form(self, form: Mapping[str, str], existing_conn_id: int | None = None) -> TestResult:
        """Build parameters from an unsaved form and test the connection."""
        type_key = (form.get('db_type') or '').strip()
        existing = db.session.get(DbConnection, existing_conn_id) if existing_conn_id is not None else None
        if existing_conn_id is not None and existing is None:
            raise ConnectionNotFoundError(f'Connection {existing_conn_id} was not found.')
        return self.test(self._params_from_form(type_key, form, existing))

    def test_saved_connection(self, conn_id: int) -> TestResult:
        """Test a saved connection and persist its latest status."""
        connection = db.session.get(DbConnection, conn_id)
        if connection is None:
            raise ConnectionNotFoundError(f'Connection {conn_id} was not found.')
        try:
            result = self.test(self._params_from_connection(connection))
        except DbConnectionError as exc:
            result = TestResult(False, str(exc), 0)
        connection.last_tested_at = datetime.now(timezone.utc).replace(tzinfo=None)
        connection.last_test_ok = result.ok
        connection.last_test_message = result.message
        db.session.commit()
        return result

    def run_query(self, conn_id: int, sql: str) -> pd.DataFrame:
        """Execute a row-limited SQL query against one saved remote connection."""
        connection = db.session.get(DbConnection, conn_id)
        if connection is None:
            raise ConnectionNotFoundError(f'Connection {conn_id} was not found.')
        params = self._params_from_connection(connection)
        dialect = self._registry.get(connection.db_type)
        query_dialect = self._query_dialect(params, dialect)
        self._validate_file_connection(params)
        self._validate_read_only_query(sql)
        uri = dialect.build_uri(params)
        masked_uri = self.masked_uri(params)
        limited_sql = query_dialect.wrap_limit(sql, self._max_rows)

        logger.info('Executing remote query for connection %s using %s', connection.name, masked_uri)
        log_action(
            'remote_query',
            'db_connection',
            connection.name,
            details={'connection_id': connection.id},
        )
        try:
            return connectorx.read_sql(uri, limited_sql, return_type='pandas')
        except Exception:
            raise RemoteQueryError('Remote query failed. Check the SQL and saved connection settings.') from None

    def list_tables(self, conn_id: int) -> list[str]:
        """Return table names visible to a saved remote connection."""
        connection = db.session.get(DbConnection, conn_id)
        if connection is None:
            raise ConnectionNotFoundError(f'Connection {conn_id} was not found.')
        params = self._params_from_connection(connection)
        dialect = self._query_dialect(params, self._registry.get(connection.db_type))
        result = self.run_query(conn_id, dialect.list_tables_query(params))
        columns = {str(column).lower(): column for column in result.columns}
        if 'table_name' not in columns:
            raise RemoteQueryError('The database did not return a table-name column.')
        return sorted(result[columns['table_name']].dropna().astype(str).tolist())

    def masked_uri(self, params: ConnectionParams) -> str:
        """Build a URI preview that hides credentials and sensitive query values."""
        dialect = self._dialect_for_params(params)
        parsed = urlsplit(dialect.build_uri(params))
        netloc = parsed.netloc
        if '@' in netloc:
            user_info, _, host = netloc.rpartition('@')
            username, separator, _password = user_info.partition(':')
            if separator:
                netloc = f'{username}:****@{host}'
        sensitive_names = {'password', 'passwd', 'pwd', 'secret', 'token', 'key', 'api_key', 'access_key'}
        query = urlencode([
            (key, '****' if key.lower() in sensitive_names or key.lower().endswith(
                ('_password', '_secret', '_token', '_key'),
            )
             else value)
            for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        ])
        return urlunsplit((parsed.scheme, netloc, parsed.path, query, parsed.fragment))

    def _params_from_form(
        self,
        type_key: str,
        form: Mapping[str, str],
        existing: DbConnection | None = None,
        preserve_empty_secrets: bool = True,
    ) -> ConnectionParams:
        """Normalize submitted form fields into typed connection parameters."""
        dialect = self._registry.get(type_key)
        raw_port_value = form.get('port')
        raw_port = str(raw_port_value).strip() if raw_port_value is not None else ''
        if raw_port:
            try:
                port = int(raw_port)
            except ValueError as exc:
                raise ConnectionValidationError('Port must be a whole number.') from exc
        else:
            port = dialect.default_port

        password = form.get('password') or ''
        custom_uri = (form.get('custom_uri') or '').strip()
        if (
            preserve_empty_secrets and existing is not None and existing.db_type == type_key
            and existing.password_encrypted and not password
        ):
            password = self._vault.decrypt(existing.password_encrypted)
        if (
            preserve_empty_secrets and existing is not None and existing.db_type == type_key
            and existing.custom_uri_encrypted and not custom_uri
        ):
            custom_uri = self._vault.decrypt(existing.custom_uri_encrypted)

        return ConnectionParams(
            type_key=type_key,
            host=(form.get('host') or '').strip() or None,
            port=port,
            database=(form.get('database') or '').strip() or None,
            username=(form.get('username') or '').strip() or None,
            password=password or None,
            file_path=(form.get('file_path') or '').strip() or None,
            custom_uri=custom_uri or None,
            extra_params=self._parse_extra_params(form.get('extra_params', '')),
        )

    def _params_from_connection(self, connection: DbConnection) -> ConnectionParams:
        """Restore encrypted credentials and serialized connection parameters."""
        try:
            extra_params = json.loads(connection.extra_params_json) if connection.extra_params_json else {}
        except json.JSONDecodeError as exc:
            raise ConnectionValidationError('Saved connection parameters are invalid.') from exc
        if not isinstance(extra_params, dict):
            raise ConnectionValidationError('Saved connection parameters are invalid.')
        password = self._vault.decrypt(connection.password_encrypted) if connection.password_encrypted else None
        custom_uri = (
            self._vault.decrypt(connection.custom_uri_encrypted) if connection.custom_uri_encrypted else None
        )
        return ConnectionParams(
            type_key=connection.db_type,
            host=connection.host,
            port=connection.port,
            database=connection.database,
            username=connection.username,
            password=password,
            file_path=connection.file_path,
            custom_uri=custom_uri,
            extra_params=extra_params,
        )

    def _dialect_for_params(self, params: ConnectionParams) -> BaseDbDialect:
        """Resolve the dialect selected by a parameter set."""
        if not params.type_key:
            raise ConnectionValidationError('Database type is required.')
        return self._registry.get(params.type_key)

    def _validate_file_connection(self, params: ConnectionParams) -> None:
        """Prevent a SQLite URI from creating a new file during a read operation."""
        if params.type_key == 'sqlite':
            database_path = Path(params.file_path or '').expanduser()
        elif params.type_key == 'custom' and urlsplit(params.custom_uri or '').scheme.lower() == 'sqlite':
            database_path = Path(unquote(urlsplit(params.custom_uri or '').path)).expanduser()
        else:
            return
        if not database_path.is_file():
            raise ConnectionValidationError('SQLite database file was not found.')

    def _validate_read_only_query(self, sql: str) -> None:
        """Reject non-read statements before passing SQL to a remote driver."""
        without_comments = re.sub(r'--[^\r\n]*|/\*.*?\*/', ' ', sql, flags=re.DOTALL)
        without_literals = re.sub(
            r"'(?:''|\\.|[^'])*'|\"(?:\"\"|\\.|[^\"])*\"|`(?:``|\\.|[^`])*`|\[(?:[^\]])*\]",
            ' ',
            without_comments,
            flags=re.DOTALL,
        )
        first_token = re.match(r'\s*([A-Za-z]+)', without_literals)
        write_token = re.search(
            r'\b(INSERT|UPDATE|DELETE|MERGE|REPLACE|CREATE|ALTER|DROP|TRUNCATE|CALL|EXEC(?:UTE)?|'
            r'GRANT|REVOKE|COPY|ATTACH|DETACH|PRAGMA)\b',
            without_literals,
            flags=re.IGNORECASE,
        )
        if first_token is None or first_token.group(1).upper() not in {'SELECT', 'WITH'} or write_token:
            raise ConnectionValidationError('Only read-only SELECT queries are allowed on saved connections.')

    def _query_dialect(self, params: ConnectionParams, fallback: BaseDbDialect) -> BaseDbDialect:
        """Select a custom URI's native dialect when ConnectorX can identify it."""
        if params.type_key != 'custom':
            return fallback
        scheme = urlsplit(params.custom_uri or '').scheme.lower().split('+', maxsplit=1)[0]
        type_key = {
            'postgres': 'postgres',
            'postgresql': 'postgres',
            'redshift': 'redshift',
            'mysql': 'mysql',
            'mssql': 'mssql',
            'oracle': 'oracle',
            'sqlite': 'sqlite',
            'clickhouse': 'clickhouse',
            'trino': 'trino',
            'bigquery': 'bigquery',
        }.get(scheme)
        return self._registry.get(type_key) if type_key else fallback

    def _parse_extra_params(self, raw_params: str | None) -> dict[str, str]:
        """Parse newline- or ampersand-separated key-value driver options."""
        result: dict[str, str] = {}
        for item in (raw_params or '').replace('&', '\n').splitlines():
            item = item.strip()
            if not item:
                continue
            key, separator, value = item.partition('=')
            if not separator or not key.strip():
                raise ConnectionValidationError('Extra parameters must use key=value format.')
            normalized_key = key.strip().lower().replace('-', '_')
            if normalized_key in {'password', 'passwd', 'pwd', 'secret', 'token', 'key', 'api_key', 'access_key'} \
                    or normalized_key.endswith(('_password', '_secret', '_token', '_key')):
                raise ConnectionValidationError(
                    'Credentials must use the dedicated password or custom URI field, not extra parameters.'
                )
            result[key.strip()] = value.strip()
        return result

    def _elapsed_ms(self, started: float) -> int:
        """Convert elapsed wall time to a nonnegative millisecond count."""
        return max(0, round((time.perf_counter() - started) * 1000))

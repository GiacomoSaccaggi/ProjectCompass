# +----------------------------------------------+
# | DATABASE DIALECT TESTS                       |
# +----------------------------------------------+
"""Tests for database forms, ConnectorX URIs, and SQL limits."""

from pathlib import Path

import pytest

from utils.db_dialects import ConnectionParams, DialectRegistry
from utils.db_errors import ConnectionValidationError, UnknownDialectError


class TestDialectRegistry:
    """Verify dialect registration and serialized form metadata."""

    def test_registry_contains_every_supported_dialect(self) -> None:
        """Expose each supported connection type exactly once."""
        registry = DialectRegistry()

        assert [dialect.type_key for dialect in registry.all()] == [
            'postgres', 'redshift', 'mysql', 'mariadb', 'mssql', 'oracle',
            'sqlite', 'clickhouse', 'trino', 'bigquery', 'custom',
        ]
        assert len({dialect.type_key for dialect in registry.all()}) == 11

    def test_form_specs_include_dynamic_fields_and_default_ports(self) -> None:
        """Provide serializable field metadata for the guided form."""
        specs = DialectRegistry().to_json_specs()
        postgres = next(spec for spec in specs if spec['type_key'] == 'postgres')
        sqlite = next(spec for spec in specs if spec['type_key'] == 'sqlite')

        assert postgres['default_port'] == 5432
        assert [field['key'] for field in sqlite['fields']] == ['file_path']

    def test_unknown_database_type_raises_typed_error(self) -> None:
        """Reject unregistered database type keys explicitly."""
        with pytest.raises(UnknownDialectError, match='Unsupported database type'):
            DialectRegistry().get('not-a-database')


class TestDialectUris:
    """Verify URI syntax and escaping for every supported connection style."""

    def test_postgres_uri_escapes_credentials_and_extra_parameters(self) -> None:
        """Encode special characters in credentials and query parameters."""
        credential_value = 'p@ss word'
        uri = DialectRegistry().get('postgres').build_uri(ConnectionParams(
            host='db.example.com', database='analytics', username='alice', password=credential_value,
            extra_params={'sslmode': 'require'},
        ))

        assert uri == 'postgresql://alice:p%40ss+word@db.example.com:5432/analytics?sslmode=require'

    def test_redshift_and_mysql_uris_use_their_default_ports(self) -> None:
        """Apply each dialect's native URI scheme and default port."""
        registry = DialectRegistry()
        credential_value = 'secret'
        params = ConnectionParams(
            host='db.example.com', database='analytics', username='alice', password=credential_value,
        )

        assert registry.get('redshift').build_uri(params) == 'redshift://alice:secret@db.example.com:5439/analytics'
        assert registry.get('mysql').build_uri(params) == 'mysql://alice:secret@db.example.com:3306/analytics'
        assert registry.get('mariadb').build_uri(params) == 'mysql://alice:secret@db.example.com:3306/analytics'

    def test_mssql_oracle_clickhouse_and_trino_uris(self) -> None:
        """Generate valid scheme, port, and database segments for network dialects."""
        registry = DialectRegistry()
        credential_value = 'secret'
        params = ConnectionParams(
            host='db.example.com', database='warehouse', username='analyst', password=credential_value,
        )

        assert registry.get('mssql').build_uri(params) == 'mssql://analyst:secret@db.example.com:1433/warehouse'
        assert registry.get('oracle').build_uri(params) == 'oracle://analyst:secret@db.example.com:1521/warehouse'
        assert registry.get('clickhouse').build_uri(params) == 'clickhouse://analyst:secret@db.example.com:9000/warehouse'
        assert registry.get('trino').build_uri(params) == 'trino://analyst:secret@db.example.com:8080/warehouse'

    def test_sqlite_and_bigquery_uris_quote_file_paths(self, tmp_path: Path) -> None:
        """Build file-based URIs while preserving path separators."""
        sqlite_path = tmp_path / 'database file.sqlite'
        credentials_path = tmp_path / 'credentials file.json'
        registry = DialectRegistry()

        sqlite_uri = registry.get('sqlite').build_uri(ConnectionParams(file_path=str(sqlite_path)))
        bigquery_uri = registry.get('bigquery').build_uri(ConnectionParams(file_path=str(credentials_path)))

        assert sqlite_uri == f'sqlite://{sqlite_path.resolve().as_posix().replace(" ", "%20")}'
        assert bigquery_uri == f'bigquery://{credentials_path.resolve().as_posix().replace(" ", "%20")}'

    def test_custom_uri_is_returned_unchanged(self) -> None:
        """Preserve a custom ConnectorX URI for advanced connections."""
        custom_uri = 'postgresql://alice:p%40ss@db.example.com:5432/analytics?sslmode=require'

        assert DialectRegistry().get('custom').build_uri(ConnectionParams(custom_uri=custom_uri)) == custom_uri

    def test_missing_required_fields_raise_validation_error(self) -> None:
        """Prevent malformed network and file-based connection URIs."""
        with pytest.raises(ConnectionValidationError, match='Host is required'):
            DialectRegistry().get('postgres').build_uri(ConnectionParams(database='analytics'))
        with pytest.raises(ConnectionValidationError, match='Database file is required'):
            DialectRegistry().get('sqlite').build_uri(ConnectionParams())
        with pytest.raises(ConnectionValidationError, match='Port must be between'):
            DialectRegistry().get('postgres').build_uri(ConnectionParams(
                host='db.example.com', port=70000, database='analytics', username='alice',
            ))


class TestDialectLimits:
    """Verify dialect-specific result limits and table queries."""

    def test_limit_wrappers_use_dialect_syntax(self) -> None:
        """Apply LIMIT, TOP, or FETCH FIRST according to the selected dialect."""
        registry = DialectRegistry()

        assert registry.get('postgres').wrap_limit('SELECT * FROM orders;', 50).endswith('LIMIT 50')
        assert registry.get('mssql').wrap_limit('SELECT * FROM orders ORDER BY id', 50) == (
            'SELECT TOP (50) * FROM orders ORDER BY id'
        )
        assert registry.get('mssql').wrap_limit(
            'WITH orders_cte AS (SELECT * FROM orders) SELECT * FROM orders_cte ORDER BY id', 50,
        ) == 'WITH orders_cte AS (SELECT * FROM orders) SELECT TOP (50) * FROM orders_cte ORDER BY id'
        assert registry.get('mssql').wrap_limit('SELECT TOP (200) * FROM orders', 50) == (
            'SELECT TOP (50) * FROM orders'
        )
        assert registry.get('oracle').wrap_limit('SELECT * FROM orders', 50).endswith('FETCH FIRST 50 ROWS ONLY')

    def test_limit_rejects_empty_queries_and_nonpositive_maximum(self) -> None:
        """Avoid producing invalid SQL when the safety limit is misconfigured."""
        dialect = DialectRegistry().get('postgres')

        with pytest.raises(ConnectionValidationError, match='greater than zero'):
            dialect.wrap_limit('SELECT 1', 0)
        with pytest.raises(ConnectionValidationError, match='cannot be empty'):
            dialect.wrap_limit(' ; ', 10)

    def test_each_dialect_has_a_table_listing_query(self) -> None:
        """Keep table-browser SQL configured for every database type."""
        assert all(dialect.list_tables_query() for dialect in DialectRegistry().all())

    def test_bigquery_table_query_uses_the_selected_project_and_dataset(self) -> None:
        """Scope BigQuery table discovery to a validated dataset when provided."""
        query = DialectRegistry().get('bigquery').list_tables_query(
            ConnectionParams(database='analytics-project.events'),
        )

        assert query == (
            'SELECT table_name FROM `analytics-project.events.INFORMATION_SCHEMA.TABLES` ORDER BY table_name'
        )

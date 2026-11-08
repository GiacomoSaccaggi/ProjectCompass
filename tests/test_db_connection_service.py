# +----------------------------------------------+
# | DATABASE CONNECTION SERVICE TESTS            |
# +----------------------------------------------+
"""Tests for saved database connections and ConnectorX query execution."""

import sqlite3
from pathlib import Path
from unittest.mock import Mock

import pandas as pd
import pytest
from cryptography.fernet import Fernet
from flask import Flask

from utils.credential_vault import CredentialVault
from utils.db_connection_service import DbConnectionService
from utils.db_dialects import ConnectionParams
from utils.db_errors import ConnectionNotFoundError, ConnectionValidationError, RemoteQueryError


class TestDbConnectionService:
    """Verify credential persistence, connection tests, and remote query routing."""

    def _service(self, app: Flask) -> DbConnectionService:
        """Create a service with an isolated, valid encryption key."""
        app.config['DB_CONNECTIONS_KEY'] = Fernet.generate_key().decode('ascii')
        return DbConnectionService()

    def _create_sqlite_database(self, path: Path) -> None:
        """Create a local database used as the remote ConnectorX fixture."""
        with sqlite3.connect(path) as connection:
            connection.execute('CREATE TABLE inventory (id INTEGER PRIMARY KEY, name TEXT NOT NULL)')
            connection.execute('INSERT INTO inventory (name) VALUES (?), (?)', ('pen', 'notebook'))

    def _sqlite_form(self, name: str, file_path: Path) -> dict[str, str]:
        """Return a valid form payload for a SQLite connection."""
        return {'name': name, 'db_type': 'sqlite', 'file_path': str(file_path)}

    def test_sqlite_connection_test_query_and_table_listing(self, app: Flask, tmp_path: Path) -> None:
        """Test a SQLite connection and query it through the DataUtils router."""
        service = self._service(app)
        database_path = tmp_path / 'inventory.sqlite'
        self._create_sqlite_database(database_path)
        saved = service.save(self._sqlite_form('Inventory', database_path), user_id=None)
        test_result = service.test(ConnectionParams(type_key='sqlite', file_path=str(database_path)))

        assert test_result.ok is True
        assert test_result.elapsed_ms >= 0
        with app.test_request_context():
            result = app.config['WEBAPP'].run_sql('SELECT id, name FROM inventory', saved.id)
            tables = service.list_tables(saved.id)

        assert isinstance(result, pd.DataFrame)
        assert result.to_dict(orient='records') == [{'id': 1, 'name': 'pen'}, {'id': 2, 'name': 'notebook'}]
        assert tables == ['inventory']

    def test_missing_sqlite_file_returns_readable_test_failure(self, app: Flask, tmp_path: Path) -> None:
        """Return a safe failure result when ConnectorX cannot open a file."""
        service = self._service(app)

        result = service.test(ConnectionParams(type_key='sqlite', file_path=str(tmp_path / 'missing.sqlite')))

        assert result.ok is False
        assert 'SQLite database file was not found' in result.message
        assert not (tmp_path / 'missing.sqlite').exists()

    def test_custom_sqlite_uri_does_not_create_a_missing_file(self, app: Flask, tmp_path: Path) -> None:
        """Apply the SQLite read-only path guard to advanced custom URIs too."""
        service = self._service(app)
        missing_path = tmp_path / 'custom-missing.sqlite'

        result = service.test(ConnectionParams(type_key='custom', custom_uri=f'sqlite://{missing_path}'))

        assert result.ok is False
        assert 'SQLite database file was not found' in result.message
        assert not missing_path.exists()

    def test_password_is_encrypted_and_empty_edit_keeps_it(self, app: Flask) -> None:
        """Persist only encrypted passwords and retain the prior value on a blank edit."""
        service = self._service(app)
        credential_value = 'database-secret'
        form = {
            'name': 'Warehouse', 'db_type': 'postgres', 'host': 'db.example.com',
            'database': 'warehouse', 'username': 'analyst', 'password': credential_value,
        }
        saved = service.save(form, user_id=None)
        encrypted = saved.password_encrypted
        vault = CredentialVault(app.config['DB_CONNECTIONS_KEY'], Path(app.config['DATA_DIR']) / 'unused-key')

        assert encrypted is not None
        assert credential_value not in encrypted
        assert vault.decrypt(encrypted) == credential_value

        form['password'] = ''
        updated = service.save(form, user_id=None, conn_id=saved.id)

        assert updated.password_encrypted is not None
        assert vault.decrypt(updated.password_encrypted) == credential_value

    def test_custom_uri_is_encrypted_and_masked(self, app: Flask) -> None:
        """Keep a custom URI containing credentials encrypted and mask its preview."""
        service = self._service(app)
        credential_value = 'custom-secret'
        uri = f'postgresql://analyst:{credential_value}@db.example.com:5432/warehouse'
        saved = service.save({'name': 'Custom warehouse', 'db_type': 'custom', 'custom_uri': uri}, user_id=None)
        params = ConnectionParams(type_key='custom', custom_uri=uri)

        assert saved.custom_uri_encrypted is not None
        assert credential_value not in saved.custom_uri_encrypted
        assert credential_value not in service.masked_uri(params)
        assert '****' in service.masked_uri(params)

    def test_custom_uri_uses_the_native_dialect_row_limit(
        self, app: Flask, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Apply SQL Server's TOP limit when the custom URI identifies SQL Server."""
        service = self._service(app)
        credential_value = 'mssql-secret'
        saved = service.save({
            'name': 'Custom SQL Server', 'db_type': 'custom',
            'custom_uri': f'mssql://analyst:{credential_value}@db.example.com:1433/warehouse',
        }, user_id=None)
        read_sql = Mock(return_value=pd.DataFrame({'value': [1]}))
        monkeypatch.setattr('utils.db_connection_service.connectorx.read_sql', read_sql)

        with app.test_request_context():
            service.run_query(saved.id, 'SELECT 1')

        query = read_sql.call_args.args[1]
        assert 'SELECT TOP (100000)' in query

    def test_duplicate_names_and_sensitive_extra_params_are_rejected(self, app: Flask, tmp_path: Path) -> None:
        """Prevent duplicate display names and clear-text credential options."""
        service = self._service(app)
        database_path = tmp_path / 'inventory.sqlite'
        self._create_sqlite_database(database_path)
        service.save(self._sqlite_form('Inventory', database_path), user_id=None)

        with pytest.raises(ConnectionValidationError, match='already exists'):
            service.save(self._sqlite_form('Inventory', database_path), user_id=None)
        with pytest.raises(ConnectionValidationError, match='dedicated password'):
            service.save({
                'name': 'Unsafe options', 'db_type': 'sqlite', 'file_path': str(database_path),
                'extra_params': 'client_secret=clear-text',
            }, user_id=None)

    def test_remote_errors_are_wrapped_without_driver_details(self, app: Flask, tmp_path: Path) -> None:
        """Hide raw ConnectorX errors when a remote query fails."""
        service = self._service(app)
        database_path = tmp_path / 'inventory.sqlite'
        self._create_sqlite_database(database_path)
        saved = service.save(self._sqlite_form('Inventory', database_path), user_id=None)

        with app.test_request_context(), pytest.raises(RemoteQueryError, match='Remote query failed'):
            service.run_query(saved.id, 'SELECT * FROM missing_table')

    def test_remote_write_statements_are_rejected_before_driver_execution(
        self, app: Flask, tmp_path: Path,
    ) -> None:
        """Reject direct writes and data-changing CTEs for saved connections."""
        service = self._service(app)
        database_path = tmp_path / 'inventory.sqlite'
        self._create_sqlite_database(database_path)
        saved = service.save(self._sqlite_form('Inventory', database_path), user_id=None)

        with app.test_request_context(), pytest.raises(ConnectionValidationError, match='read-only SELECT'):
            service.run_query(saved.id, 'DELETE FROM inventory')
        with app.test_request_context(), pytest.raises(ConnectionValidationError, match='read-only SELECT'):
            service.run_query(
                saved.id,
                'WITH removed AS (DELETE FROM inventory RETURNING id) SELECT * FROM removed',
            )

    def test_unknown_connection_raises_not_found_error(self, app: Flask) -> None:
        """Report missing saved connections with the typed service error."""
        service = self._service(app)

        with pytest.raises(ConnectionNotFoundError):
            service.run_query(99999, 'SELECT 1')

    def test_local_run_sql_still_uses_duckdb(self, app: Flask) -> None:
        """Preserve local query behavior when no connection ID is selected."""
        result = app.config['WEBAPP'].run_sql('SELECT 1 AS value')

        assert result.to_dict(orient='records') == [{'value': 1}]

# +----------------------------------------------+
# | DATABASE CONNECTION ROUTE TESTS              |
# +----------------------------------------------+
"""Tests for connection management routes, permissions, and secret handling."""

import sqlite3
from pathlib import Path

from cryptography.fernet import Fernet
from flask import Flask
from flask.testing import FlaskClient

from models import AuditLog, DbConnection, db


class TestConnectionsBlueprint:
    """Verify connection pages and endpoints enforce their public contracts."""

    def _set_role(self, client: FlaskClient, role: str) -> None:
        """Set the authenticated test session's role."""
        with client.session_transaction() as session:
            session['role'] = role

    def _configure_key(self, app: Flask) -> None:
        """Use a test-only encryption key for saved credentials."""
        app.config['DB_CONNECTIONS_KEY'] = Fernet.generate_key().decode('ascii')

    def _create_sqlite_database(self, path: Path) -> None:
        """Create a table for connection endpoint integration tests."""
        with sqlite3.connect(path) as connection:
            connection.execute('CREATE TABLE inventory (id INTEGER PRIMARY KEY, label TEXT NOT NULL)')
            connection.execute('INSERT INTO inventory (label) VALUES (?)', ('item',))

    def _sqlite_form(self, name: str, file_path: Path) -> dict[str, str]:
        """Return a valid form payload for a SQLite connection."""
        return {'name': name, 'db_type': 'sqlite', 'file_path': str(file_path)}

    def test_create_edit_delete_and_audit(self, app: Flask, client: FlaskClient, tmp_path: Path) -> None:
        """Allow an editor to manage a connection and record each mutation."""
        self._configure_key(app)
        self._set_role(client, 'editor')
        database_path = tmp_path / 'inventory.sqlite'
        self._create_sqlite_database(database_path)

        created = client.post('/connections/save', data=self._sqlite_form('Inventory', database_path))
        assert created.status_code == 302
        with app.app_context():
            connection = DbConnection.query.filter_by(name='Inventory').one()
            connection_id = connection.id

        edit_page = client.get(f'/connections/{connection_id}/edit')
        assert edit_page.status_code == 200
        assert b'Edit database connection' in edit_page.data

        updated = client.post('/connections/save', data={
            **self._sqlite_form('Inventory updated', database_path),
            'conn_id': str(connection_id),
        })
        assert updated.status_code == 302

        deleted = client.post(f'/connections/{connection_id}/delete')
        assert deleted.status_code == 302
        with app.app_context():
            assert db.session.get(DbConnection, connection_id) is None
            actions = {
                entry.action for entry in AuditLog.query.filter_by(target_type='db_connection').all()
            }
        assert {'create', 'update', 'delete'} <= actions

    def test_connection_list_and_edit_page_never_return_a_password(
        self, app: Flask, client: FlaskClient,
    ) -> None:
        """Keep saved credentials out of HTML responses and leave password inputs blank."""
        self._configure_key(app)
        self._set_role(client, 'admin')
        credential_value = 'database-response-secret'
        response = client.post('/connections/save', data={
            'name': 'Warehouse', 'db_type': 'postgres', 'host': 'db.example.com',
            'database': 'warehouse', 'username': 'analyst', 'password': credential_value,
        })
        assert response.status_code == 302

        with app.app_context():
            connection = DbConnection.query.filter_by(name='Warehouse').one()
            connection_id = connection.id
            encrypted_value = connection.password_encrypted
        list_page = client.get('/connections/')
        edit_page = client.get(f'/connections/{connection_id}/edit')

        assert credential_value.encode() not in list_page.data
        assert credential_value.encode() not in edit_page.data
        assert encrypted_value.encode() not in list_page.data
        assert encrypted_value.encode() not in edit_page.data
        assert b'Leave blank to keep the current password' in edit_page.data

    def test_unsaved_test_and_saved_table_browser(self, app: Flask, client: FlaskClient, tmp_path: Path) -> None:
        """Test a temporary SQLite connection and list its tables after saving."""
        self._configure_key(app)
        self._set_role(client, 'admin')
        database_path = tmp_path / 'inventory.sqlite'
        self._create_sqlite_database(database_path)
        credential_value = 'not-returned-secret'

        unsaved_test = client.post('/connections/test', json={
            'db_type': 'sqlite', 'file_path': str(database_path), 'password': credential_value,
        })
        assert unsaved_test.status_code == 200
        assert unsaved_test.get_json()['ok'] is True
        assert credential_value.encode() not in unsaved_test.data

        saved = client.post('/connections/save', data=self._sqlite_form('Inventory', database_path))
        assert saved.status_code == 302
        with app.app_context():
            connection_id = DbConnection.query.filter_by(name='Inventory').one().id

        table_response = client.get(f'/connections/{connection_id}/tables')
        test_response = client.post(f'/connections/{connection_id}/test', json={})

        assert table_response.status_code == 200
        assert table_response.get_json() == {'tables': ['inventory']}
        assert test_response.status_code == 200
        assert test_response.get_json()['ok'] is True
        with app.app_context():
            connection = db.session.get(DbConnection, connection_id)
            assert connection.last_test_ok is True
            assert connection.last_tested_at is not None

    def test_viewers_can_list_and_use_but_cannot_manage_connections(
        self, app: Flask, client: FlaskClient, tmp_path: Path,
    ) -> None:
        """Allow viewer access to read routes while blocking mutations and tests."""
        self._configure_key(app)
        self._set_role(client, 'admin')
        database_path = tmp_path / 'inventory.sqlite'
        self._create_sqlite_database(database_path)
        client.post('/connections/save', data=self._sqlite_form('Inventory', database_path))
        with app.app_context():
            connection_id = DbConnection.query.filter_by(name='Inventory').one().id

        self._set_role(client, 'viewer')
        assert client.get('/connections/').status_code == 200
        assert client.get(f'/connections/{connection_id}/tables').status_code == 200
        assert client.get('/connections/new').status_code == 302
        assert client.post('/connections/save', data=self._sqlite_form('Blocked', database_path)).status_code == 302
        assert client.post('/connections/test', json={'db_type': 'sqlite'}).status_code == 302
        assert client.post(f'/connections/{connection_id}/test', json={}).status_code == 302
        assert client.post(f'/connections/{connection_id}/delete').status_code == 302

    def test_invalid_or_duplicate_connection_form_returns_safe_validation_error(
        self, app: Flask, client: FlaskClient, tmp_path: Path,
    ) -> None:
        """Show validation errors without echoing a submitted password or URI."""
        self._configure_key(app)
        self._set_role(client, 'editor')
        database_path = tmp_path / 'inventory.sqlite'
        self._create_sqlite_database(database_path)
        client.post('/connections/save', data=self._sqlite_form('Inventory', database_path))
        credential_value = 'form-secret-value'

        response = client.post('/connections/save', data={
            **self._sqlite_form('Inventory', database_path),
            'password': credential_value,
            'extra_params': 'client_secret=' + credential_value,
        })

        assert response.status_code == 400
        assert b'already exists' in response.data
        assert credential_value.encode() not in response.data

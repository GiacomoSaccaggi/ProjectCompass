# +----------------------------------------------+
# | MANAGED CONNECTION TESTS                     |
# +----------------------------------------------+
"""Verify preset synchronization, schema migration and managed UI restrictions."""

import sqlite3
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from flask import Flask
from flask.testing import FlaskClient
from sqlalchemy import inspect, text

from models import DbConnection, _ensure_db_connection_columns, db
from utils.app_settings import PresetConnection
from utils.credential_vault import CredentialVault
from utils.db_connection_service import DbConnectionService
from utils.db_errors import ConnectionValidationError
from utils.managed_connections import ManagedConnectionSync


class TestManagedConnectionSync:
    """Cover idempotent preset reconciliation and its non-destructive cases."""

    def test_create_update_unchanged_and_remove_preset(self, app: Flask, tmp_path: Path) -> None:
        """Encrypt preset credentials and reconcile additions, changes and removal."""
        service = self._service(app)
        synchronizer = ManagedConnectionSync(service)
        first = self._postgres_preset('Warehouse', 'db.example.com', 'first-secret')

        created = synchronizer.sync((first,))

        with app.app_context():
            connection = DbConnection.query.filter_by(name='Warehouse').one()
            connection_id = connection.id
            encrypted_password = connection.password_encrypted
            vault = CredentialVault(
                app.config['DB_CONNECTIONS_KEY'], tmp_path / 'unused-key',
            )
            assert connection.managed is True
            assert encrypted_password is not None
            assert 'first-secret' not in encrypted_password
            assert vault.decrypt(encrypted_password) == 'first-secret'
        assert created.created == ('Warehouse',)
        assert created.updated == ()

        unchanged = synchronizer.sync((first,))
        assert unchanged.unchanged == ('Warehouse',)
        assert unchanged.updated == ()

        changed = synchronizer.sync((self._postgres_preset('Warehouse', 'new.example.com', 'second-secret'),))
        with app.app_context():
            connection = db.session.get(DbConnection, connection_id)
            assert connection is not None
            assert connection.host == 'new.example.com'
            assert connection.managed is True
            assert vault.decrypt(connection.password_encrypted) == 'second-secret'
        assert changed.updated == ('Warehouse',)

        removed = synchronizer.sync(())
        with app.app_context():
            assert db.session.get(DbConnection, connection_id) is None
        assert removed.removed == ('Warehouse',)

    def test_name_clash_skips_ui_connection(self, app: Flask, tmp_path: Path) -> None:
        """Never take ownership of an existing UI-managed connection with the same name."""
        service = self._service(app)
        database_path = tmp_path / 'warehouse.sqlite'
        self._create_sqlite_database(database_path)
        user_connection = service.save(
            {'name': 'Warehouse', 'db_type': 'sqlite', 'file_path': str(database_path)},
            user_id=None,
        )

        report = ManagedConnectionSync(service).sync((self._postgres_preset('Warehouse'),))

        with app.app_context():
            saved = db.session.get(DbConnection, user_connection.id)
            assert saved is not None
            assert saved.db_type == 'sqlite'
            assert saved.managed is False
            assert DbConnection.query.count() == 1
        assert report.skipped == ('Warehouse',)
        assert report.created == ()

    def test_invalid_preset_configuration_preserves_unlisted_managed_rows(self, app: Flask) -> None:
        """Avoid deleting last-good managed connections when a config entry is invalid."""
        service = self._service(app)
        synchronizer = ManagedConnectionSync(service)
        synchronizer.sync((self._postgres_preset('Warehouse'),))

        report = synchronizer.sync((), preserve_unlisted=True)

        with app.app_context():
            saved = DbConnection.query.filter_by(name='Warehouse').one()
            assert saved.managed is True
        assert report.removed == ()
        assert report.skipped == ('Warehouse',)

    def test_non_managed_connections_survive_empty_config(self, app: Flask, tmp_path: Path) -> None:
        """Remove only records explicitly owned by configuration."""
        service = self._service(app)
        database_path = tmp_path / 'manual.sqlite'
        self._create_sqlite_database(database_path)
        manual = service.save(
            {'name': 'Manual', 'db_type': 'sqlite', 'file_path': str(database_path)},
            user_id=None,
        )
        synchronizer = ManagedConnectionSync(service)
        synchronizer.sync((self._postgres_preset('Configured'),))

        report = synchronizer.sync(())

        with app.app_context():
            assert db.session.get(DbConnection, manual.id) is not None
            assert DbConnection.query.filter_by(name='Configured').first() is None
        assert report.removed == ('Configured',)

    def test_legacy_connection_table_gets_managed_column(self, app: Flask) -> None:
        """Migrate an existing database table that predates managed connections."""
        with app.app_context():
            db.session.execute(text('DROP TABLE db_connections'))
            db.session.execute(text('CREATE TABLE db_connections (id INTEGER PRIMARY KEY, name TEXT)'))
            db.session.commit()

            _ensure_db_connection_columns()

            columns = {column['name']: column for column in inspect(db.engine).get_columns('db_connections')}

        assert 'managed' in columns
        assert columns['managed']['nullable'] is False

    def _service(self, app: Flask) -> DbConnectionService:
        """Create a service with a stable test-only Fernet key."""
        app.config['DB_CONNECTIONS_KEY'] = Fernet.generate_key().decode('ascii')
        return DbConnectionService()

    def _postgres_preset(
        self,
        name: str,
        host: str = 'db.example.com',
        password: str | None = None,
    ) -> PresetConnection:
        """Build a valid PostgreSQL preset without connecting to a live server."""
        return PresetConnection(
            name,
            'postgres',
            {
                'host': host,
                'port': '5432',
                'database': 'analytics',
                'username': 'readonly',
                'password': password or 'warehouse-secret',
                'extra_params': '',
            },
        )

    def _create_sqlite_database(self, path: Path) -> None:
        """Create a temporary SQLite file for manual connection rows."""
        with sqlite3.connect(path) as connection:
            connection.execute('CREATE TABLE inventory (id INTEGER PRIMARY KEY, label TEXT NOT NULL)')
            connection.execute('INSERT INTO inventory (label) VALUES (?)', ('item',))


class TestManagedConnectionRoutes:
    """Verify UI and HTTP mutations cannot edit or delete managed records."""

    def test_managed_connection_is_read_only_but_can_be_tested_and_queried(
        self, app: Flask, client: FlaskClient, tmp_path: Path,
    ) -> None:
        """Show the managed badge, reject mutations, and allow connection testing."""
        app.config['DB_CONNECTIONS_KEY'] = Fernet.generate_key().decode('ascii')
        database_path = tmp_path / 'managed.sqlite'
        with sqlite3.connect(database_path) as connection:
            connection.execute('CREATE TABLE inventory (id INTEGER PRIMARY KEY, label TEXT NOT NULL)')
            connection.execute('INSERT INTO inventory (label) VALUES (?)', ('managed row',))
        service = DbConnectionService()
        saved = service.save(
            {'name': 'Managed warehouse', 'db_type': 'sqlite', 'file_path': str(database_path)},
            user_id=None,
            allow_managed=True,
        )
        with client.session_transaction() as session:
            session['role'] = 'editor'

        list_page = client.get('/connections/')
        edit_page = client.get(f'/connections/{saved.id}/edit')
        save_response = client.post('/connections/save', data={
            'conn_id': str(saved.id),
            'name': 'Changed name',
            'db_type': 'sqlite',
            'file_path': str(database_path),
        })
        delete_response = client.post(f'/connections/{saved.id}/delete')
        test_response = client.post(f'/connections/{saved.id}/test', json={})

        assert b'Managed by config' in list_page.data
        assert f'/connections/{saved.id}/edit'.encode() not in list_page.data
        assert f'/connections/{saved.id}/delete'.encode() not in list_page.data
        assert edit_page.status_code == 403
        assert save_response.status_code == 403
        assert delete_response.status_code == 403
        assert test_response.status_code == 200
        assert test_response.get_json()['ok'] is True

        with app.test_request_context(), app.app_context():
            result = service.run_query(saved.id, 'SELECT label FROM inventory')
            assert result.to_dict(orient='records') == [{'label': 'managed row'}]
            with pytest.raises(ConnectionValidationError, match='managed by configuration'):
                service.save(
                    {'name': 'Changed name', 'db_type': 'sqlite', 'file_path': str(database_path)},
                    user_id=None,
                    conn_id=saved.id,
                )
            with pytest.raises(ConnectionValidationError, match='managed by configuration'):
                service.delete(saved.id)

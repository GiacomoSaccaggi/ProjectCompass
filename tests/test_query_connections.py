# +----------------------------------------------+
# | QUERY CONNECTION INTEGRATION TESTS           |
# +----------------------------------------------+
"""Tests for remote Query Runner and API workflows."""

import sqlite3
from pathlib import Path

from cryptography.fernet import Fernet
from flask import Flask
from flask.testing import FlaskClient

from models import DbConnection


class TestQueryConnections:
    """Verify connection selection persists through query-related workflows."""

    def _set_up(self, app: Flask, client: FlaskClient) -> None:
        """Configure encrypted connections and an editor session."""
        app.config['DB_CONNECTIONS_KEY'] = Fernet.generate_key().decode('ascii')
        with client.session_transaction() as session:
            session['role'] = 'editor'

    def _create_sqlite_database(self, path: Path, row_count: int = 3) -> None:
        """Create a local database that ConnectorX can read during tests."""
        with sqlite3.connect(path) as connection:
            connection.execute('CREATE TABLE records (id INTEGER PRIMARY KEY, label TEXT NOT NULL)')
            connection.executemany(
                'INSERT INTO records (id, label) VALUES (?, ?)',
                [(row_id, f'record-{row_id}') for row_id in range(1, row_count + 1)],
            )

    def _save_connection(self, app: Flask, client: FlaskClient, path: Path, name: str) -> int:
        """Save a SQLite connection through the managed route."""
        response = client.post('/connections/save', data={
            'name': name,
            'db_type': 'sqlite',
            'file_path': str(path),
        })
        assert response.status_code == 302
        with app.app_context():
            return DbConnection.query.filter_by(name=name).one().id

    def test_query_runner_keeps_source_across_pagination(self, app: Flask, client: FlaskClient, tmp_path: Path) -> None:
        """Select a remote source, paginate its result, and retain the selection."""
        self._set_up(app, client)
        database_path = tmp_path / 'records.sqlite'
        self._create_sqlite_database(database_path, row_count=125)
        connection_id = self._save_connection(app, client, database_path, 'Records')

        runner_page = client.get(f'/query_runner/?connection_id={connection_id}')
        result_page = client.post('/query_results/', data={
            'output_query': 'SELECT id, label FROM records ORDER BY id',
            'connection_id': str(connection_id),
            'page': '2',
        })

        assert runner_page.status_code == 200
        assert f'<option value="{connection_id}" selected>'.encode() in runner_page.data
        assert result_page.status_code == 200
        assert b'Page 2 of 2' in result_page.data
        assert f'name="connection_id" value="{connection_id}"'.encode() in result_page.data
        assert b'record-101' in result_page.data
        assert b'record-1<' not in result_page.data

    def test_saved_query_and_rawgraphs_retain_remote_connection(self, app: Flask, client: FlaskClient,
                                                                 tmp_path: Path) -> None:
        """Write the selected source into saved SQL and return from RAWGraphs with it."""
        self._set_up(app, client)
        database_path = tmp_path / 'records.sqlite'
        self._create_sqlite_database(database_path)
        connection_id = self._save_connection(app, client, database_path, 'Records')
        saved_queries_path = tmp_path / 'Saved_queries'
        saved_queries_path.mkdir()
        app.config['WEBAPP'].save_queries_path = str(saved_queries_path)
        query = 'SELECT id, label FROM records'

        saved = client.post('/save_query/', data={
            'title': 'remote-query',
            'output_query_to_save': query,
            'connection_id': str(connection_id),
        })
        rawgraphs = client.post('/graph_analysis/', data={
            'output_query_to_rawgraph': query,
            'connection_id': str(connection_id),
        })
        saved_sql = (saved_queries_path / 'remote-query.sql').read_text()

        assert saved.status_code == 200
        assert f'name="connection_id" value="{connection_id}"'.encode() in saved.data
        assert '-- connection: Records' in saved_sql
        assert query in saved_sql
        assert rawgraphs.status_code == 200
        assert f'connection_id={connection_id}'.encode() in rawgraphs.data
        assert b'Data loaded from query' in rawgraphs.data

    def test_api_query_accepts_connection_id_name_and_local_default(
        self, app: Flask, client: FlaskClient, tmp_path: Path,
    ) -> None:
        """Route API queries to a saved source by ID or name and retain local default."""
        self._set_up(app, client)
        database_path = tmp_path / 'records.sqlite'
        self._create_sqlite_database(database_path)
        connection_id = self._save_connection(app, client, database_path, 'Records')

        by_id = client.post('/api/query', json={
            'sql': 'SELECT id, label FROM records ORDER BY id', 'connection': connection_id,
        })
        by_name = client.post('/api/query', json={
            'sql': 'SELECT id, label FROM records ORDER BY id', 'connection': 'Records',
        })
        local = client.post('/api/query', json={'sql': 'SELECT 1 AS value'})
        missing = client.post('/api/query', json={
            'sql': 'SELECT 1', 'connection': 'unknown-connection',
        })

        assert by_id.status_code == 200
        assert by_name.status_code == 200
        assert by_id.get_json()['rows'][0] == {'id': 1, 'label': 'record-1'}
        assert by_name.get_json()['rows'] == by_id.get_json()['rows']
        assert local.status_code == 200
        assert local.get_json()['rows'] == [{'value': 1}]
        assert missing.status_code == 404
        assert missing.get_json() == {'error': 'The saved database connection was not found.'}

    def test_missing_query_runner_connection_shows_a_message(self, app: Flask, client: FlaskClient) -> None:
        """Show a readable message instead of a server error for deleted sources."""
        self._set_up(app, client)

        response = client.post('/query_results/', data={
            'output_query': 'SELECT 1',
            'connection_id': '99999',
        })

        assert response.status_code == 200
        assert b'Remote query error' in response.data
        assert b'Connection 99999 was not found' in response.data
        assert b'id="query-results" style="display:none;"' in response.data

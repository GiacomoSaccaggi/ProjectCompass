# +----------------------------------------------+
# | DATABASE CONNECTION ROUTES                   |
# +----------------------------------------------+
"""Routes for guided management of saved database connections."""

from __future__ import annotations

import json

from flask import Blueprint, Response, abort, current_app, jsonify, redirect, render_template, request, session, url_for

from blueprints.auth import require_role
from models import DbConnection, db, log_action
from utils.db_connection_service import DbConnectionService, TestResult
from utils.db_dialects import DialectRegistry
from utils.db_errors import ConnectionNotFoundError, DbConnectionError

connections_bp = Blueprint('connections', __name__, url_prefix='/connections')


def _render_connection_form(form_values: dict[str, str | int], conn_id: int | None = None,
                            error: str = '', status_code: int = 200) -> tuple[str, int]:
    """Render the dynamic connection form without returning stored secrets."""
    webapp = current_app.config['WEBAPP']
    html_part = webapp.substitute_html(port=webapp.constants['port'], project_folder=webapp.project_folder)
    return render_template(
        'connection_form.html',
        title=webapp.environments_info['title'],
        top_container=html_part['top_container'],
        sidebar_menu=html_part['sidebar_menu'],
        head=html_part['head'],
        project_folder=webapp.project_folder,
        dialect_specs=DialectRegistry().to_json_specs(),
        form_values=form_values,
        conn_id=conn_id,
        error=error,
    ), status_code


def _saved_form_values(connection: DbConnection) -> dict[str, str | int]:
    """Build safe form values while excluding encrypted or sensitive fields."""
    try:
        extra_params = json.loads(connection.extra_params_json) if connection.extra_params_json else {}
    except json.JSONDecodeError:
        extra_params = {}
    if not isinstance(extra_params, dict):
        extra_params = {}
    sensitive_names = {'password', 'passwd', 'pwd', 'secret', 'token', 'key', 'api_key', 'access_key'}
    safe_extra_params = [
        f'{key}={value}' for key, value in extra_params.items()
        if str(key).lower() not in sensitive_names
        and not str(key).lower().endswith(('_password', '_secret', '_token', '_key'))
    ]
    return {
        'name': connection.name,
        'db_type': connection.db_type,
        'host': connection.host or '',
        'port': connection.port or '',
        'database': connection.database or '',
        'username': connection.username or '',
        'file_path': connection.file_path or '',
        'custom_uri': '',
        'password': '',
        'extra_params': '\n'.join(safe_extra_params),
    }


def _submitted_form_values() -> dict[str, str | int]:
    """Keep non-secret fields after validation errors without echoing credentials."""
    return {
        key: request.form.get(key, '')
        for key in ('name', 'db_type', 'host', 'port', 'database', 'username', 'file_path')
    } | {'password': '', 'custom_uri': '', 'extra_params': ''}


def _result_response(result: TestResult, status_code: int | None = None) -> tuple[Response, int]:
    """Serialize a safe connection-test result."""
    response_code = status_code if status_code is not None else (200 if result.ok else 400)
    return jsonify({'ok': result.ok, 'message': result.message, 'elapsed_ms': result.elapsed_ms}), response_code


@connections_bp.route('/')
def index() -> str:
    """Show saved connections to any authenticated user."""
    webapp = current_app.config['WEBAPP']
    html_part = webapp.substitute_html(port=webapp.constants['port'], project_folder=webapp.project_folder)
    registry = DialectRegistry()
    dialects = {dialect.type_key: {'label': dialect.label, 'icon': dialect.icon} for dialect in registry.all()}
    role = session.get('role') or 'admin'
    return render_template(
        'connections_list.html',
        title=webapp.environments_info['title'],
        top_container=html_part['top_container'],
        sidebar_menu=html_part['sidebar_menu'],
        head=html_part['head'],
        project_folder=webapp.project_folder,
        connections=DbConnectionService().list(),
        dialects=dialects,
        dialect_specs=registry.to_json_specs(),
        can_manage=role in ('admin', 'editor'),
    )


@connections_bp.route('/new')
@require_role('admin', 'editor')
def new() -> tuple[str, int]:
    """Show the guided form for a new connection."""
    return _render_connection_form({'db_type': 'postgres'})


@connections_bp.route('/<int:conn_id>/edit')
@require_role('admin', 'editor')
def edit(conn_id: int) -> tuple[str, int]:
    """Show a connection's editable fields, leaving credentials blank."""
    connection = db.session.get(DbConnection, conn_id)
    if connection is None:
        abort(404)
    if connection.managed:
        abort(403)
    return _render_connection_form(_saved_form_values(connection), conn_id)


@connections_bp.route('/save', methods=['POST'])
@require_role('admin', 'editor')
def save() -> Response | tuple[str, int]:
    """Create or update a saved connection and record the change."""
    raw_conn_id = request.form.get('conn_id', '').strip()
    try:
        conn_id = int(raw_conn_id) if raw_conn_id else None
    except ValueError:
        return _render_connection_form(
            _submitted_form_values(), error='Invalid connection identifier.', status_code=400,
        )
    existing = db.session.get(DbConnection, conn_id) if conn_id is not None else None
    if conn_id is not None and existing is None:
        abort(404)
    if existing is not None and existing.managed:
        return _render_connection_form(
            _saved_form_values(existing), conn_id,
            error='This connection is managed by configuration and cannot be changed here.',
            status_code=403,
        )

    try:
        connection = DbConnectionService().save(request.form, session.get('user_id'), conn_id)
    except DbConnectionError as exc:
        return _render_connection_form(_submitted_form_values(), conn_id, str(exc), 400)

    action = 'update' if conn_id is not None else 'create'
    log_action(action, 'db_connection', connection.name, details={'db_type': connection.db_type})
    return redirect(url_for('connections.index'))


@connections_bp.route('/<int:conn_id>/delete', methods=['POST'])
@require_role('admin', 'editor')
def delete(conn_id: int) -> Response:
    """Delete a saved connection and record the change."""
    connection = db.session.get(DbConnection, conn_id)
    if connection is None:
        abort(404)
    if connection.managed:
        abort(403)
    name = connection.name
    DbConnectionService().delete(conn_id)
    log_action('delete', 'db_connection', name)
    return redirect(url_for('connections.index'))


@connections_bp.route('/test', methods=['POST'])
@require_role('admin', 'editor')
def test_unsaved() -> tuple[Response, int]:
    """Test submitted connection fields without saving them."""
    form = request.get_json(silent=True) or request.form.to_dict()
    raw_conn_id = str(form.get('conn_id') or '').strip()
    try:
        existing_conn_id = int(raw_conn_id) if raw_conn_id else None
        result = DbConnectionService().test_form(form, existing_conn_id)
    except ValueError:
        return _result_response(_failed_test('Invalid connection identifier.'), 400)
    except DbConnectionError as exc:
        status_code = 404 if isinstance(exc, ConnectionNotFoundError) else 400
        return _result_response(_failed_test(str(exc)), status_code)
    log_action('test_connection', 'db_connection', str(form.get('name') or form.get('db_type') or 'unsaved'),
               details={'ok': result.ok})
    return _result_response(result)


@connections_bp.route('/<int:conn_id>/test', methods=['POST'])
@require_role('admin', 'editor')
def test_saved(conn_id: int) -> tuple[Response, int]:
    """Test a saved connection and update its latest test status."""
    service = DbConnectionService()
    try:
        result = service.test_saved_connection(conn_id)
    except ConnectionNotFoundError as exc:
        return _result_response(_failed_test(str(exc)), 404)
    connection = db.session.get(DbConnection, conn_id)
    log_action('test_connection', 'db_connection', connection.name, details={'ok': result.ok})
    return _result_response(result)


@connections_bp.route('/<int:conn_id>/tables')
def tables(conn_id: int) -> tuple[Response, int]:
    """Return table names for the Query Runner's selected connection."""
    try:
        return jsonify({'tables': DbConnectionService().list_tables(conn_id)})
    except ConnectionNotFoundError as exc:
        return jsonify({'error': str(exc)}), 404
    except DbConnectionError as exc:
        return jsonify({'error': str(exc)}), 400


def _failed_test(message: str) -> TestResult:
    """Create an unsuccessful test result for a request-level validation error."""
    return TestResult(False, message, 0)

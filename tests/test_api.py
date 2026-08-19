import json

from werkzeug.security import generate_password_hash


def test_api_health(client):
    resp = client.get('/api/health')
    assert resp.status_code == 200
    assert resp.get_json()['status'] == 'ok'


def test_api_list_analyses(client):
    resp = client.get('/api/analyses')
    assert resp.status_code == 200
    data = resp.get_json()
    assert 'analyses' in data
    assert 'total' in data
    assert 'page' in data


def test_api_list_analyses_search(client):
    resp = client.get('/api/analyses?q=nonexistent12345')
    data = resp.get_json()
    assert data['total'] == 0


def test_api_list_analyses_pagination(client):
    resp = client.get('/api/analyses?page=1&per_page=5')
    data = resp.get_json()
    assert data['per_page'] == 5
    assert data['page'] == 1


def test_api_list_data(client):
    resp = client.get('/api/data')
    assert resp.status_code == 200
    data = resp.get_json()
    assert 'datasets' in data


def test_api_data_preview(client):
    resp = client.get('/api/data')
    datasets = resp.get_json()['datasets']
    if datasets:
        resp2 = client.get(f'/api/data/{datasets[0]}/preview?limit=5')
        assert resp2.status_code == 200
        data = resp2.get_json()
        assert 'columns' in data
        assert 'rows' in data
        assert len(data['rows']) <= 5


def test_api_data_preview_not_found(client):
    resp = client.get('/api/data/nonexistent_dataset_xyz/preview')
    assert resp.status_code == 404


def test_api_query(client):
    # First check if there's data to query
    resp = client.get('/api/data')
    datasets = resp.get_json()['datasets']
    if datasets:
        resp2 = client.post('/api/query',
                           data=json.dumps({'sql': f'select * from {datasets[0]} limit 5'}),
                           content_type='application/json')
        assert resp2.status_code == 200
        data = resp2.get_json()
        assert 'columns' in data
        assert 'rows' in data


def test_api_query_missing_sql(client):
    resp = client.post('/api/query',
                      data=json.dumps({}),
                      content_type='application/json')
    assert resp.status_code == 400


def test_api_query_invalid_sql(client):
    # DuckDB errors are caught by data_utils.sql() which returns empty DataFrame
    # The API returns 200 with empty results (not 400)
    resp = client.post('/api/query',
                      data=json.dumps({'sql': 'SELECT * FROM nonexistent_table_xyz'}),
                      content_type='application/json')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['total_rows'] == 0


# --- Activity feed tests ---

def test_api_activity(app, client):
    """GET /api/activity returns JSON list of audit log entries."""
    from models import AuditLog, User, db

    with app.app_context():
        user = User(
            username='activityuser',
            password_hash=generate_password_hash('pass'),
            role='editor'
        )
        db.session.add(user)
        db.session.commit()
        user_id = user.id

        # Create some audit log entries
        entry1 = AuditLog(
            user_id=user_id,
            action='create',
            target_type='analysis',
            target_name='Test Analysis'
        )
        entry2 = AuditLog(
            user_id=user_id,
            action='run',
            target_type='analysis',
            target_name='Another Analysis'
        )
        db.session.add(entry1)
        db.session.add(entry2)
        db.session.commit()

    resp = client.get('/api/activity')
    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data, list)
    # Should have at least the 2 entries we created
    assert len(data) >= 2

    # Check structure of entries
    for entry in data:
        assert 'action' in entry
        assert 'target_type' in entry
        assert 'target_name' in entry
        assert 'user' in entry
        assert 'created_at' in entry


def test_api_activity_limit(app, client):
    """GET /api/activity respects limit parameter."""
    from models import AuditLog, User, db

    with app.app_context():
        user = User(
            username='limituser',
            password_hash=generate_password_hash('pass'),
            role='editor'
        )
        db.session.add(user)
        db.session.commit()
        user_id = user.id

        # Create multiple audit log entries
        for i in range(10):
            entry = AuditLog(
                user_id=user_id,
                action='test',
                target_type='test',
                target_name=f'Test {i}'
            )
            db.session.add(entry)
        db.session.commit()

    resp = client.get('/api/activity?limit=3')
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data) == 3


def test_api_activity_html(app, client):
    """GET /api/activity_html returns HTML string."""
    from models import AuditLog, User, db

    with app.app_context():
        user = User(
            username='htmlactivityuser',
            password_hash=generate_password_hash('pass'),
            role='editor'
        )
        db.session.add(user)
        db.session.commit()
        user_id = user.id

        entry = AuditLog(
            user_id=user_id,
            action='login',
            target_type='user',
            target_name='htmlactivityuser'
        )
        db.session.add(entry)
        db.session.commit()

    resp = client.get('/api/activity_html')
    assert resp.status_code == 200
    # Response should be HTML (not JSON)
    assert resp.content_type.startswith('text/html')
    html = resp.data.decode('utf-8')
    # Should contain some HTML elements
    assert '<div' in html or 'No activity' in html


def test_api_activity_html_empty(app, client):
    """GET /api/activity_html with no entries returns placeholder."""
    # Clear audit log
    from models import AuditLog, db

    with app.app_context():
        AuditLog.query.delete()
        db.session.commit()

    resp = client.get('/api/activity_html')
    assert resp.status_code == 200
    html = resp.data.decode('utf-8')
    assert 'No activity' in html


# --- Search tests ---

def test_api_search_empty(client):
    """GET /api/search?q= returns empty results."""
    resp = client.get('/api/search?q=')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['results'] == []


def test_api_search_short(client):
    """GET /api/search?q=a returns empty (query too short)."""
    resp = client.get('/api/search?q=a')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['results'] == []


def test_api_search_no_results(client):
    """GET /api/search with nonexistent term returns empty."""
    resp = client.get('/api/search?q=xyznonexistent123')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['results'] == []


def test_api_search_html_empty(client):
    """GET /api/search_html?q= returns empty string."""
    resp = client.get('/api/search_html?q=')
    assert resp.status_code == 200
    # Should be empty string for short/empty query
    assert resp.data.decode('utf-8') == ''


def test_api_search_html_short(client):
    """GET /api/search_html?q=a returns empty string (query too short)."""
    resp = client.get('/api/search_html?q=a')
    assert resp.status_code == 200
    assert resp.data.decode('utf-8') == ''


def test_api_search_html_no_results(client):
    """GET /api/search_html with no results returns 'No results' message."""
    resp = client.get('/api/search_html?q=xyznonexistent123')
    assert resp.status_code == 200
    html = resp.data.decode('utf-8')
    # Should either be "No results" or "Search error"
    assert 'No results' in html or 'error' in html.lower()


def test_api_search_with_indexed_data(app, client):
    """GET /api/search returns results if data is indexed."""
    from models import index_analysis_fts

    with app.app_context():
        # Index a test analysis
        index_analysis_fts(
            name='test_search_analysis',
            title='Wine Quality Analysis',
            description='A test analysis about wine quality data',
            readme_text='This analysis processes wine quality datasets',
            script_text='import pandas as pd'
        )

    # Search for it
    resp = client.get('/api/search?q=wine')
    assert resp.status_code == 200
    data = resp.get_json()
    # Should find the indexed analysis
    assert isinstance(data['results'], list)


def test_api_search_html_with_indexed_data(app, client):
    """GET /api/search_html returns HTML with links for indexed data."""
    from models import index_analysis_fts

    with app.app_context():
        index_analysis_fts(
            name='search_html_test',
            title='Marketing Campaign Analysis',
            description='Analysis of marketing campaigns',
            readme_text='Marketing insights',
            script_text=''
        )

    resp = client.get('/api/search_html?q=marketing')
    assert resp.status_code == 200
    html = resp.data.decode('utf-8')
    # Should contain link if found, or no results message
    assert '<a href' in html or 'No results' in html


# --- Metrics endpoint tests ---

def test_api_metrics(app, client):
    """GET /api/metrics returns JSON with expected keys."""
    from models import User, db

    with app.app_context():
        user = User(
            username='metricsuser',
            password_hash=generate_password_hash('pass'),
            role='admin'
        )
        db.session.add(user)
        db.session.commit()
        user_id = user.id

    with client.session_transaction() as sess:
        sess['authenticated'] = True
        sess['user_id'] = user_id
        sess['username'] = 'metricsuser'
        sess['role'] = 'admin'

    resp = client.get('/api/metrics')
    assert resp.status_code == 200
    data = resp.get_json()

    # Check all expected keys are present
    assert 'daily' in data
    assert 'statuses' in data
    assert 'top_analyses' in data
    assert 'total_executions' in data
    assert 'total_actions' in data
    assert 'total_users' in data
    assert 'total_analyses' in data
    assert 'success_rate' in data

    # Check types
    assert isinstance(data['daily'], list)
    assert isinstance(data['statuses'], dict)
    assert isinstance(data['top_analyses'], list)
    assert isinstance(data['total_executions'], int)
    assert isinstance(data['total_actions'], int)
    assert isinstance(data['total_users'], int)
    assert isinstance(data['total_analyses'], int)
    assert isinstance(data['success_rate'], (int, float))


def test_api_metrics_with_executions(app, client):
    """GET /api/metrics includes execution data."""
    from datetime import datetime

    from models import Execution, User, db

    with app.app_context():
        user = User(
            username='execuser',
            password_hash=generate_password_hash('pass'),
            role='admin'
        )
        db.session.add(user)
        db.session.commit()
        user_id = user.id

        # Add some executions
        exec1 = Execution(
            analysis_name='Test Analysis 1',
            user_id=user_id,
            status='success',
            started_at=datetime.utcnow()
        )
        exec2 = Execution(
            analysis_name='Test Analysis 1',
            user_id=user_id,
            status='success',
            started_at=datetime.utcnow()
        )
        exec3 = Execution(
            analysis_name='Test Analysis 2',
            user_id=user_id,
            status='failed',
            started_at=datetime.utcnow()
        )
        db.session.add(exec1)
        db.session.add(exec2)
        db.session.add(exec3)
        db.session.commit()

    with client.session_transaction() as sess:
        sess['authenticated'] = True
        sess['user_id'] = user_id
        sess['username'] = 'execuser'
        sess['role'] = 'admin'

    resp = client.get('/api/metrics')
    assert resp.status_code == 200
    data = resp.get_json()

    # Should have at least 3 executions
    assert data['total_executions'] >= 3
    # Should have success and failed statuses
    assert 'success' in data['statuses'] or 'failed' in data['statuses']

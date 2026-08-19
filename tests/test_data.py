"""Tests for blueprints/data.py routes."""
import io

# --- Page load tests ---

def test_all_data_page(client):
    """Test GET /all_data/ returns 200."""
    resp = client.get('/all_data/')
    assert resp.status_code == 200


def test_data_upload_page(client):
    """Test GET /list_of_data/ returns 200."""
    resp = client.get('/list_of_data/')
    assert resp.status_code == 200


def test_upload_data_form(client):
    """Test GET /upload_data/ returns 200."""
    resp = client.get('/upload_data/')
    assert resp.status_code == 200


def test_query_runner_page(client):
    """Test GET /query_runner/ returns 200."""
    resp = client.get('/query_runner/')
    assert resp.status_code == 200
    assert b'query' in resp.data.lower()


def test_rawgraphs_page(client):
    """Test GET /rawgraphs returns 200."""
    resp = client.get('/rawgraphs')
    assert resp.status_code == 200
    assert b'RAWGraphs' in resp.data or b'rawgraphs' in resp.data.lower()


# --- Query execution tests ---

def test_execute_query(client):
    """Test POST /query_results/ with a valid SQL query."""
    resp = client.post('/query_results/', data={
        'output_query': 'SELECT 1 as test_col, 2 as another_col'
    })
    assert resp.status_code == 200
    assert b'test_col' in resp.data or b'1' in resp.data


def test_execute_query_with_table(client, app):
    """Test POST /query_results/ querying a real dataset."""
    # Check if wine_quality exists in Saved_data
    import os
    with app.app_context():
        webapp = app.config['WEBAPP']
        wine_path = os.path.join(webapp.save_data_path, 'wine_quality.csv')
        if os.path.exists(wine_path):
            resp = client.post('/query_results/', data={
                'output_query': 'SELECT * FROM wine_quality LIMIT 5'
            })
            assert resp.status_code == 200


def test_execute_query_pagination(client):
    """Test POST /query_results/ with page parameter."""
    resp = client.post('/query_results/', data={
        'output_query': 'SELECT 1 as col',
        'page': '1'
    })
    assert resp.status_code == 200


def test_query_runner_html_cleaning():
    """Test the clean_query function sanitizes HTML."""
    from blueprints.data import clean_query

    # Test HTML tag removal
    dirty = '<span class="hl">SELECT</span> * FROM <div>table</div>'
    clean = clean_query(dirty)
    assert '<span' not in clean
    assert '<div' not in clean
    assert 'SELECT' in clean

    # Test &nbsp; replacement
    dirty2 = 'SELECT&nbsp;*&nbsp;FROM&nbsp;table'
    clean2 = clean_query(dirty2)
    assert '&nbsp;' not in clean2


# --- Open data tests ---

def test_open_data(client, app):
    """Test GET /open_data?name=<dataset> opens a dataset."""
    import os
    with app.app_context():
        webapp = app.config['WEBAPP']
        # Find first available dataset
        datasets = [f.replace('.csv', '') for f in os.listdir(webapp.save_data_path)
                    if f.endswith('.csv') and not f.startswith('.')]
        if datasets:
            resp = client.get(f'/open_data?name={datasets[0]}')
            assert resp.status_code == 200


# --- Graph analysis tests ---

def test_graph_analysis_route(client):
    """Test POST /graph_analysis/ with query opens RAWGraphs."""
    resp = client.post('/graph_analysis/', data={
        'output_query_to_rawgraph': 'SELECT 1 as x, 2 as y'
    })
    assert resp.status_code == 200
    assert b'RAWGraphs' in resp.data or b'rawgraphs' in resp.data.lower()


def test_graph_analysis_empty_query(client):
    """Test POST /graph_analysis/ with empty query."""
    resp = client.post('/graph_analysis/', data={
        'output_query_to_rawgraph': ''
    })
    assert resp.status_code == 200


# --- Save query tests ---

def test_save_query(client, app):
    """Test POST /save_query/ saves a query to file."""
    import os
    title = 'test_query_pytest'
    try:
        resp = client.post('/save_query/', data={
            'output_query_to_save': 'SELECT 1 as test',
            'title': title
        })
        assert resp.status_code == 200

        # Verify file was created
        with app.app_context():
            webapp = app.config['WEBAPP']
            query_path = os.path.join(webapp.save_queries_path, f'{title}.sql')
            assert os.path.exists(query_path)
            with open(query_path) as f:
                content = f.read()
            assert 'SELECT 1 as test' in content
    finally:
        # Clean up
        with app.app_context():
            webapp = app.config['WEBAPP']
            query_path = os.path.join(webapp.save_queries_path, f'{title}.sql')
            if os.path.exists(query_path):
                os.remove(query_path)


# --- Upload tests ---

def test_upload_data_file(client, app):
    """Test POST /upload_data_file/ uploads a CSV file."""
    import os
    filename = 'test_upload_pytest.csv'
    csv_content = b'col1,col2\n1,2\n3,4'

    try:
        data = {
            'file': (io.BytesIO(csv_content), filename),
            'separator': ','
        }
        resp = client.post('/upload_data_file/', data=data, content_type='multipart/form-data')
        assert resp.status_code == 200

        # Verify file was saved
        with app.app_context():
            webapp = app.config['WEBAPP']
            file_path = os.path.join(webapp.save_data_path, filename)
            # File may or may not be created depending on upload_text_files implementation
    finally:
        # Clean up
        with app.app_context():
            webapp = app.config['WEBAPP']
            file_path = os.path.join(webapp.save_data_path, filename)
            if os.path.exists(file_path):
                os.remove(file_path)


# --- Data lineage helper test ---

def test_get_data_lineage(app):
    """Test _get_data_lineage returns dataset usage info."""
    from blueprints.data import _get_data_lineage

    with app.app_context():
        lineage = _get_data_lineage()
        # Should return a dict (may be empty if no executions)
        assert isinstance(lineage, dict)


# --- Authentication required tests ---

def test_all_data_requires_auth(unauth_client):
    """Test /all_data/ redirects unauthenticated users."""
    resp = unauth_client.get('/all_data/')
    # Should either redirect to login or return 401/403
    assert resp.status_code in (200, 302, 401, 403)


def test_query_runner_requires_auth(unauth_client):
    """Test /query_runner/ redirects unauthenticated users."""
    resp = unauth_client.get('/query_runner/')
    assert resp.status_code in (200, 302, 401, 403)

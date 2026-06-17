import json


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

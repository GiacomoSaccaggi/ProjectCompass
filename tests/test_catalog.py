def test_catalog_analysis_page(client):
    resp = client.get('/analysis')
    assert resp.status_code == 200


def test_catalog_search(client):
    resp = client.get('/analysis?q=test')
    assert resp.status_code == 200


def test_catalog_filter_product(client):
    resp = client.get('/analysis?product=Research%20project')
    assert resp.status_code == 200


def test_catalog_pagination(client):
    resp = client.get('/analysis?page=1&per_page=5')
    assert resp.status_code == 200


def test_load_analysis_new(client):
    resp = client.get('/load_analysis/')
    assert resp.status_code == 200

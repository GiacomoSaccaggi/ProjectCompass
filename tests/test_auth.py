def test_health_endpoint(client):
    resp = client.get('/health')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['status'] == 'ok'


def test_health_no_auth_required(unauth_client):
    resp = unauth_client.get('/health')
    assert resp.status_code == 200


def test_unauthenticated_redirect(unauth_client):
    resp = unauth_client.get('/')
    # Should render login page (200 with login form)
    assert resp.status_code == 200
    assert b'login' in resp.data.lower() or b'uname' in resp.data.lower()


def test_authenticated_index(client):
    resp = client.get('/')
    assert resp.status_code == 200


def test_logout(client):
    resp = client.get('/logout/', follow_redirects=True)
    assert resp.status_code == 200

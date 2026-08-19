import hashlib

from werkzeug.security import generate_password_hash


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
    # Should render login page (200 with login form) or setup wizard if no users exist
    assert resp.status_code == 200
    # Could be landing page (with login form), setup wizard (with username form), or old login page
    assert (b'login' in resp.data.lower() or
            b'uname' in resp.data.lower() or
            b'username' in resp.data.lower() or
            b'setup' in resp.data.lower())


def test_authenticated_index(client):
    resp = client.get('/')
    assert resp.status_code == 200


def test_logout(client):
    resp = client.get('/logout/', follow_redirects=True)
    assert resp.status_code == 200


# --- Multi-user login tests ---

def test_login_with_db_user(app, unauth_client):
    """Login with a user created in the database."""
    from models import User, db

    with app.app_context():
        user = User(
            username='testlogin',
            password_hash=generate_password_hash('correctpass'),
            role='editor'
        )
        db.session.add(user)
        db.session.commit()

    # Now login with correct credentials
    resp = unauth_client.post('/login/', data={
        'uname': 'testlogin',
        'psw': 'correctpass'
    }, follow_redirects=False)

    # Should redirect after successful login
    assert resp.status_code == 302

    # Check session was set
    with unauth_client.session_transaction() as sess:
        assert sess.get('authenticated') is True
        assert sess.get('username') == 'testlogin'
        assert sess.get('role') == 'editor'


def test_login_wrong_password(app, unauth_client):
    """Login attempt with wrong password should not authenticate."""
    from models import User, db

    with app.app_context():
        user = User(
            username='wrongpassuser',
            password_hash=generate_password_hash('realpassword'),
            role='viewer'
        )
        db.session.add(user)
        db.session.commit()

    # Try login with wrong password
    resp = unauth_client.post('/login/', data={
        'uname': 'wrongpassuser',
        'psw': 'wrongpassword'
    }, follow_redirects=False)

    # Still redirects, but session should NOT be authenticated
    assert resp.status_code == 302

    with unauth_client.session_transaction() as sess:
        assert sess.get('authenticated') is not True


# --- RBAC (Role-Based Access Control) tests ---

def test_require_role_admin_allowed(app, client):
    """Admin user can access /admin/users."""
    from models import User, db

    with app.app_context():
        user = User(
            username='adminuser',
            password_hash=generate_password_hash('adminpass'),
            role='admin'
        )
        db.session.add(user)
        db.session.commit()
        user_id = user.id

    with client.session_transaction() as sess:
        sess['authenticated'] = True
        sess['user_id'] = user_id
        sess['username'] = 'adminuser'
        sess['role'] = 'admin'

    resp = client.get('/admin/users')
    assert resp.status_code == 200


def test_require_role_viewer_blocked(app, client):
    """Viewer user should be redirected from /admin/users."""
    from models import User, db

    with app.app_context():
        user = User(
            username='vieweruser',
            password_hash=generate_password_hash('viewerpass'),
            role='viewer'
        )
        db.session.add(user)
        db.session.commit()
        user_id = user.id

    with client.session_transaction() as sess:
        sess['authenticated'] = True
        sess['user_id'] = user_id
        sess['username'] = 'vieweruser'
        sess['role'] = 'viewer'

    resp = client.get('/admin/users', follow_redirects=False)
    # Should redirect to index (302)
    assert resp.status_code == 302


# --- Admin user management tests ---

def test_admin_users_page(app, client):
    """GET /admin/users returns 200 for admin user."""
    from models import User, db

    with app.app_context():
        user = User(
            username='adminpage',
            password_hash=generate_password_hash('pass'),
            role='admin'
        )
        db.session.add(user)
        db.session.commit()
        user_id = user.id

    with client.session_transaction() as sess:
        sess['authenticated'] = True
        sess['user_id'] = user_id
        sess['username'] = 'adminpage'
        sess['role'] = 'admin'

    resp = client.get('/admin/users')
    assert resp.status_code == 200


def test_create_user(app, client):
    """POST /admin/users/create creates a new user in the database."""
    from models import User, db

    with app.app_context():
        admin = User(
            username='creatoradmin',
            password_hash=generate_password_hash('pass'),
            role='admin'
        )
        db.session.add(admin)
        db.session.commit()
        admin_id = admin.id

    with client.session_transaction() as sess:
        sess['authenticated'] = True
        sess['user_id'] = admin_id
        sess['username'] = 'creatoradmin'
        sess['role'] = 'admin'

    resp = client.post('/admin/users/create', data={
        'username': 'newcreateduser',
        'password': 'newuserpass',
        'role': 'editor',
        'email': 'newuser@test.com'
    }, follow_redirects=False)

    assert resp.status_code == 302

    # Verify user was created
    with app.app_context():
        created = User.query.filter_by(username='newcreateduser').first()
        assert created is not None
        assert created.role == 'editor'
        assert created.email == 'newuser@test.com'


def test_delete_user(app, client):
    """POST /admin/users/<id>/delete removes user from database."""
    from models import User, db

    with app.app_context():
        admin = User(
            username='deleteadmin',
            password_hash=generate_password_hash('pass'),
            role='admin'
        )
        target = User(
            username='tobedeleted',
            password_hash=generate_password_hash('pass'),
            role='viewer'
        )
        db.session.add(admin)
        db.session.add(target)
        db.session.commit()
        admin_id = admin.id
        target_id = target.id

    with client.session_transaction() as sess:
        sess['authenticated'] = True
        sess['user_id'] = admin_id
        sess['username'] = 'deleteadmin'
        sess['role'] = 'admin'

    resp = client.post(f'/admin/users/{target_id}/delete', follow_redirects=False)
    assert resp.status_code == 302

    # Verify user was deleted
    with app.app_context():
        deleted = User.query.get(target_id)
        assert deleted is None


# --- Settings page tests ---

def test_settings_page(app, client):
    """GET /settings returns 200 for authenticated user."""
    from models import User, db

    with app.app_context():
        user = User(
            username='settingsuser',
            password_hash=generate_password_hash('pass'),
            role='editor'
        )
        db.session.add(user)
        db.session.commit()
        user_id = user.id

    with client.session_transaction() as sess:
        sess['authenticated'] = True
        sess['user_id'] = user_id
        sess['username'] = 'settingsuser'
        sess['role'] = 'editor'

    resp = client.get('/settings')
    assert resp.status_code == 200


# --- API Token tests ---

def test_create_api_token(app, client):
    """POST /api/tokens creates and returns a token."""
    from models import User, db

    with app.app_context():
        user = User(
            username='tokenuser',
            password_hash=generate_password_hash('pass'),
            role='editor'
        )
        db.session.add(user)
        db.session.commit()
        user_id = user.id

    with client.session_transaction() as sess:
        sess['authenticated'] = True
        sess['user_id'] = user_id
        sess['username'] = 'tokenuser'
        sess['role'] = 'editor'

    resp = client.post('/api/tokens',
                       json={'name': 'Test Token'},
                       content_type='application/json')
    assert resp.status_code == 200
    data = resp.get_json()
    assert 'token' in data
    assert 'id' in data
    assert data['name'] == 'Test Token'


def test_bearer_token_auth(app, unauth_client):
    """Request with valid Bearer token should authenticate."""
    from models import ApiToken, User, db

    # Create user and token
    with app.app_context():
        user = User(
            username='beareruser',
            password_hash=generate_password_hash('pass'),
            role='editor'
        )
        db.session.add(user)
        db.session.commit()

        # Create a known token
        raw_token = 'test_token_abc123'
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        api_token = ApiToken(
            user_id=user.id,
            token_hash=token_hash,
            name='Test Bearer Token',
            revoked=False
        )
        db.session.add(api_token)
        db.session.commit()

    # Make request with Bearer token
    resp = unauth_client.get('/api/analyses', headers={
        'Authorization': f'Bearer {raw_token}'
    })
    assert resp.status_code == 200


def test_bearer_token_invalid(app, unauth_client):
    """Request with invalid Bearer token should return 401."""
    # Use a protected route (not /api/* since those are always allowed)
    resp = unauth_client.get('/settings', headers={
        'Authorization': 'Bearer invalid_token_xyz'
    })
    assert resp.status_code == 401
    data = resp.get_json()
    assert 'error' in data


# --- Admin metrics page test ---

def test_admin_metrics_page(app, client):
    """GET /admin/metrics returns 200 for admin user."""
    from models import User, db

    with app.app_context():
        user = User(
            username='metricsadmin',
            password_hash=generate_password_hash('pass'),
            role='admin'
        )
        db.session.add(user)
        db.session.commit()
        user_id = user.id

    with client.session_transaction() as sess:
        sess['authenticated'] = True
        sess['user_id'] = user_id
        sess['username'] = 'metricsadmin'
        sess['role'] = 'admin'

    resp = client.get('/admin/metrics')
    assert resp.status_code == 200

"""Tests for basefun.py — ProjectCompass class and utility functions."""
from basefun import decrypt_and_decompress, encrypt_and_compress


def test_encrypt_and_compress_basic():
    """Test encrypt_and_compress returns different string than original."""
    original = "Hello, World!"
    encrypted = encrypt_and_compress(original)

    assert encrypted != original
    assert isinstance(encrypted, str)
    # Should be base64 encoded
    assert all(c.isalnum() or c in '+/=' for c in encrypted)


def test_encrypt_and_compress_with_key():
    """Test encrypt_and_compress with custom key."""
    original = "Secret message"
    key = "my_custom_key"

    encrypted = encrypt_and_compress(original, key=key)
    assert encrypted != original
    assert isinstance(encrypted, str)


def test_encrypt_decrypt_roundtrip():
    """Test that decrypt_and_decompress reverses encrypt_and_compress."""
    original = "The quick brown fox jumps over the lazy dog"
    key = "testkey123"

    encrypted = encrypt_and_compress(original, key=key)
    decrypted = decrypt_and_decompress(encrypted, key=key)

    assert decrypted == original


def test_encrypt_decrypt_roundtrip_default_key():
    """Test roundtrip with default key."""
    original = "Testing default key encryption"

    encrypted = encrypt_and_compress(original)
    decrypted = decrypt_and_decompress(encrypted)

    assert decrypted == original


def test_encrypt_decrypt_unicode():
    """Test encryption/decryption with unicode characters."""
    original = "Unicode: 日本語 émojis 🎉"
    key = "unicode_key"

    encrypted = encrypt_and_compress(original, key=key)
    decrypted = decrypt_and_decompress(encrypted, key=key)

    assert decrypted == original


def test_encrypt_compress_empty_string():
    """Test encryption of empty string."""
    original = ""
    encrypted = encrypt_and_compress(original)
    decrypted = decrypt_and_decompress(encrypted)

    assert decrypted == original


def test_encrypt_compress_long_text():
    """Test encryption of long text."""
    original = "A" * 10000
    encrypted = encrypt_and_compress(original)
    decrypted = decrypt_and_decompress(encrypted)

    assert decrypted == original
    # Compression should make it smaller
    assert len(encrypted) < len(original)


def test_encrypt_different_keys_different_output():
    """Test that different keys produce different output."""
    original = "Same text"

    encrypted1 = encrypt_and_compress(original, key="key1")
    encrypted2 = encrypt_and_compress(original, key="key2")

    assert encrypted1 != encrypted2


def test_create_job_request_basic():
    """Test create_job_request returns correct structure."""
    from basefun import ProjectCompass

    job_request = ProjectCompass.create_job_request(
        RECIPE_ID='my_recipe',
        RECIPE_VERSION='1_0_0'
    )

    assert job_request['spec_version'] == 'v2'
    assert job_request['recipe_id'] == 'my_recipe'
    assert job_request['recipe_version'] == '1_0_0'
    assert 'system_configuration' in job_request
    assert job_request['system_configuration']['send_dag_complete_email'] is False
    assert job_request['system_configuration']['prefer_user_pyenv'] is True
    assert job_request['system_configuration']['allow_unpublished_recipe_runs'] is True
    assert 'configuration' in job_request
    assert job_request['configuration'] == {}


def test_create_job_request_with_inputs():
    """Test create_job_request with input_recipe kwargs."""
    from basefun import ProjectCompass

    input_config = {
        'country': 'DNK',
        'start_date': '2026-01-01',
        'end_date': '2026-01-31',
        'debug_mode': True
    }

    job_request = ProjectCompass.create_job_request(
        RECIPE_ID='pam_pipeline',
        RECIPE_VERSION='2_3_4',
        input_recipe=input_config
    )

    assert job_request['recipe_id'] == 'pam_pipeline'
    assert job_request['recipe_version'] == '2_3_4'
    assert job_request['configuration']['country'] == 'DNK'
    assert job_request['configuration']['start_date'] == '2026-01-01'
    assert job_request['configuration']['end_date'] == '2026-01-31'
    assert job_request['configuration']['debug_mode'] is True


def test_create_job_request_empty_inputs():
    """Test create_job_request with empty input_recipe."""
    from basefun import ProjectCompass

    job_request = ProjectCompass.create_job_request(
        RECIPE_ID='test_recipe',
        RECIPE_VERSION='0_0_1',
        input_recipe={}
    )

    assert job_request['configuration'] == {}


def test_create_job_request_nested_inputs():
    """Test create_job_request with nested configuration."""
    from basefun import ProjectCompass

    input_config = {
        'database': {
            'host': 'localhost',
            'port': 5432
        },
        'features': ['feature1', 'feature2']
    }

    job_request = ProjectCompass.create_job_request(
        RECIPE_ID='nested_recipe',
        RECIPE_VERSION='1_0_0',
        input_recipe=input_config
    )

    assert job_request['configuration']['database']['host'] == 'localhost'
    assert job_request['configuration']['database']['port'] == 5432
    assert job_request['configuration']['features'] == ['feature1', 'feature2']


def test_projectcompass_init_via_app(app):
    """Test ProjectCompass is initialized correctly through Flask app."""
    with app.app_context():
        from flask import current_app
        webapp = current_app.config.get('WEBAPP')
        if webapp is not None:
            # Verify it has the expected attributes
            assert hasattr(webapp, 'dir_path')
            assert hasattr(webapp, 'constants')
            assert hasattr(webapp, 'save_folder_path')
            assert hasattr(webapp, 'save_data_path')
            assert hasattr(webapp, 'save_queries_path')

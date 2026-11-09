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


def test_create_task_config_basic():
    """Test create_task_config returns correct structure."""
    from basefun import ProjectCompass

    cfg = ProjectCompass.create_task_config(
        task_id='my_task',
        task_version='1_0_0',
    )

    assert cfg['task_id'] == 'my_task'
    assert cfg['task_version'] == '1_0_0'
    assert cfg['configuration'] == {}


def test_create_task_config_with_inputs():
    """Test create_task_config with input_params kwargs."""
    from basefun import ProjectCompass

    params = {
        'region': 'EU',
        'start_date': '2026-01-01',
        'end_date': '2026-01-31',
        'debug_mode': True,
    }

    cfg = ProjectCompass.create_task_config(
        task_id='etl_pipeline',
        task_version='2_3_4',
        input_params=params,
    )

    assert cfg['task_id'] == 'etl_pipeline'
    assert cfg['task_version'] == '2_3_4'
    assert cfg['configuration']['region'] == 'EU'
    assert cfg['configuration']['start_date'] == '2026-01-01'
    assert cfg['configuration']['end_date'] == '2026-01-31'
    assert cfg['configuration']['debug_mode'] is True


def test_create_task_config_empty_inputs():
    """Test create_task_config with empty input_params."""
    from basefun import ProjectCompass

    cfg = ProjectCompass.create_task_config(
        task_id='test_task',
        task_version='0_0_1',
        input_params={},
    )

    assert cfg['configuration'] == {}


def test_create_task_config_nested_inputs():
    """Test create_task_config with nested configuration."""
    from basefun import ProjectCompass

    params = {
        'database': {
            'host': 'localhost',
            'port': 5432,
        },
        'features': ['feature1', 'feature2'],
    }

    cfg = ProjectCompass.create_task_config(
        task_id='nested_task',
        task_version='1_0_0',
        input_params=params,
    )

    assert cfg['configuration']['database']['host'] == 'localhost'
    assert cfg['configuration']['database']['port'] == 5432
    assert cfg['configuration']['features'] == ['feature1', 'feature2']


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

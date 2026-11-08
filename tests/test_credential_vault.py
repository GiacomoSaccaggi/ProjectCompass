# +----------------------------------------------+
# | DATABASE CREDENTIAL VAULT TESTS              |
# +----------------------------------------------+
"""Tests for persistent encryption of saved database credentials."""

from pathlib import Path

import pytest

from utils.credential_vault import CredentialVault
from utils.db_errors import VaultKeyError


class TestCredentialVault:
    """Verify credential encryption and key persistence."""

    def test_encrypt_decrypt_round_trip(self, tmp_path: Path) -> None:
        """Ensure an encrypted value can be recovered with the same key."""
        vault = CredentialVault(None, tmp_path / 'key')

        encrypted = vault.encrypt('sensitive-password')

        assert encrypted != 'sensitive-password'
        assert vault.decrypt(encrypted) == 'sensitive-password'

    def test_generated_key_is_reused_and_has_restricted_permissions(self, tmp_path: Path) -> None:
        """Keep generated keys stable between vault instances and private on disk."""
        key_file = tmp_path / 'tmp' / '.db_connections.key'
        first_vault = CredentialVault(None, key_file)
        encrypted = first_vault.encrypt('sensitive-password')

        second_vault = CredentialVault(None, key_file)

        assert second_vault.decrypt(encrypted) == 'sensitive-password'
        assert key_file.stat().st_mode & 0o777 == 0o600

    def test_invalid_token_raises_vault_key_error(self, tmp_path: Path) -> None:
        """Report unreadable credentials through the typed vault error."""
        vault = CredentialVault(None, tmp_path / 'key')

        with pytest.raises(VaultKeyError, match='Stored credentials cannot be decrypted'):
            vault.decrypt('not-a-valid-token')

    def test_invalid_configured_key_raises_vault_key_error(self, tmp_path: Path) -> None:
        """Reject malformed configured keys without revealing their contents."""
        with pytest.raises(VaultKeyError, match='encryption key is invalid'):
            CredentialVault('not-a-valid-key', tmp_path / 'unused-key')

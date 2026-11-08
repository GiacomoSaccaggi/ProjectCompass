# +----------------------------------------------+
# | DATABASE CREDENTIAL VAULT                    |
# +----------------------------------------------+
"""Protect database credentials with a stable Fernet key."""

import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from utils.db_errors import VaultKeyError


class CredentialVault:
    """Encrypt and decrypt credentials without exposing key material."""

    def __init__(self, key: str | None, key_file: str | Path) -> None:
        """Create a vault using a configured key or a persistent key file.

        Args:
            key: Optional URL-safe base64 Fernet key from configuration.
            key_file: Path used to persist a generated key when ``key`` is empty.

        Raises:
            VaultKeyError: If the configured or persisted key is invalid.
        """
        self._key_file = Path(key_file)
        try:
            key_bytes = key.encode('ascii') if key else self._load_or_create_key()
            self._fernet = Fernet(key_bytes)
        except (TypeError, ValueError) as exc:
            raise VaultKeyError('The database credential encryption key is invalid.') from exc

    def encrypt(self, plain: str) -> str:
        """Encrypt a credential for storage.

        Args:
            plain: The clear-text credential to protect.

        Returns:
            A Fernet token suitable for storing in the database.
        """
        return self._fernet.encrypt(plain.encode('utf-8')).decode('ascii')

    def decrypt(self, token: str) -> str:
        """Decrypt a stored credential.

        Args:
            token: The Fernet token read from storage.

        Returns:
            The clear-text credential.

        Raises:
            VaultKeyError: If the token cannot be decrypted with this key.
        """
        try:
            return self._fernet.decrypt(token.encode('ascii')).decode('utf-8')
        except (InvalidToken, UnicodeDecodeError, UnicodeEncodeError) as exc:
            raise VaultKeyError(
                'Stored credentials cannot be decrypted. Restore the original key or re-enter the password.'
            ) from exc

    def _load_or_create_key(self) -> bytes:
        """Read the persistent key, creating it securely if it is missing."""
        try:
            self._key_file.parent.mkdir(parents=True, exist_ok=True)
            try:
                descriptor = os.open(self._key_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError:
                key_bytes = self._key_file.read_bytes()
            else:
                with os.fdopen(descriptor, 'wb') as key_stream:
                    key_stream.write(Fernet.generate_key())
                key_bytes = self._key_file.read_bytes()
            os.chmod(self._key_file, 0o600)
            return key_bytes
        except OSError as exc:
            raise VaultKeyError('Unable to read or create the database credential encryption key file.') from exc

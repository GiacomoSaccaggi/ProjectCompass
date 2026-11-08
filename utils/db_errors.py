# +----------------------------------------------+
# | DATABASE CONNECTION ERRORS                   |
# +----------------------------------------------+
"""Typed errors raised by database connection operations."""


class DbConnectionError(Exception):
    """Base error for database connection operations."""


class UnknownDialectError(DbConnectionError):
    """Raised when a database type is not supported."""


class ConnectionValidationError(DbConnectionError):
    """Raised when saved connection details are invalid."""


class ConnectionNotFoundError(DbConnectionError):
    """Raised when a requested saved connection does not exist."""


class VaultKeyError(DbConnectionError):
    """Raised when credentials cannot be encrypted or decrypted."""


class RemoteQueryError(DbConnectionError):
    """Raised when a query against a remote database fails."""

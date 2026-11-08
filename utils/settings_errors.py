# +----------------------------------------------+
# | APPLICATION SETTINGS ERRORS                  |
# +----------------------------------------------+
"""Typed errors raised while loading application settings."""


class SettingsError(Exception):
    """Base error for application settings failures."""


class SettingsFileError(SettingsError):
    """Raised when a settings file cannot be read or parsed."""


class SettingsValidationError(SettingsError):
    """Raised when a setting has an invalid value."""

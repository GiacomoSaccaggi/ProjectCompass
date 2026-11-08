# +----------------------------------------------+
# | MANAGED CONNECTION SYNCHRONIZATION           |
# +----------------------------------------------+
"""Synchronize configured database connections without exposing credentials."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass

from models import db
from utils.app_settings import PresetConnection
from utils.db_connection_service import DbConnectionService
from utils.db_errors import DbConnectionError


@dataclass(frozen=True)
class SyncReport:
    """Summarize managed connection synchronization without storing secrets."""

    created: tuple[str, ...]
    updated: tuple[str, ...]
    removed: tuple[str, ...]
    skipped: tuple[str, ...]
    unchanged: tuple[str, ...]


class ManagedConnectionSync:
    """Create, update and remove only connections owned by configuration."""

    def __init__(self, service: DbConnectionService) -> None:
        """Create a synchronizer using the application's validated connection service."""
        self._service = service
        self._logger = logging.getLogger(__name__)

    def sync(
        self,
        presets: Sequence[PresetConnection],
        preserve_unlisted: bool = False,
    ) -> SyncReport:
        """Reconcile configured presets with saved records by exact connection name.

        Args:
            presets: Valid preset connections from the application settings.
            preserve_unlisted: Avoid deletions if one or more preset entries were invalid.

        Returns:
            Created, changed, removed, unchanged and skipped connection names.
        """
        saved_connections = self._service.list()
        saved_by_name = {connection.name: connection for connection in saved_connections}
        created: list[str] = []
        updated: list[str] = []
        skipped: list[str] = []
        unchanged: list[str] = []
        configured_names: set[str] = set()

        for preset in presets:
            name = preset.name
            if name in configured_names:
                self._logger.warning('Skipping duplicate configured database connection %s.', name)
                skipped.append(name)
                continue
            configured_names.add(name)
            existing = saved_by_name.get(name)
            if existing is not None and not existing.managed:
                self._logger.warning(
                    'Configured database connection %s conflicts with a UI-managed connection; skipping it.', name,
                )
                skipped.append(name)
                continue

            form = preset.to_form()
            try:
                if existing is not None and self._service.matches(existing, form):
                    unchanged.append(name)
                    continue
                self._service.save(
                    form,
                    user_id=None,
                    conn_id=existing.id if existing is not None else None,
                    allow_managed=True,
                )
            except DbConnectionError:
                db.session.rollback()
                self._logger.warning('Unable to synchronize configured database connection %s; skipping it.', name)
                skipped.append(name)
                continue
            except Exception:
                db.session.rollback()
                self._logger.warning('Unable to synchronize configured database connection %s; skipping it.', name)
                skipped.append(name)
                continue

            if existing is None:
                created.append(name)
            else:
                updated.append(name)

        removed: list[str] = []
        for connection in saved_connections:
            if not connection.managed or connection.name in configured_names:
                continue
            if preserve_unlisted:
                skipped.append(connection.name)
                continue
            try:
                self._service.delete(connection.id, allow_managed=True)
            except Exception:
                db.session.rollback()
                self._logger.warning('Unable to remove stale configured database connection %s.', connection.name)
                skipped.append(connection.name)
                continue
            removed.append(connection.name)

        return SyncReport(
            created=tuple(created),
            updated=tuple(updated),
            removed=tuple(removed),
            skipped=tuple(skipped),
            unchanged=tuple(unchanged),
        )

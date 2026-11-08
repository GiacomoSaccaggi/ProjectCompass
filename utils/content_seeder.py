# +----------------------------------------------+
# | DEMO CONTENT SEEDER                          |
# +----------------------------------------------+
"""Seed bundled or configured demo content into empty data directories."""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path

from utils.app_settings import DemoSettings, SettingsLoader


class DemoContentSeeder:
    """Copy demo analysis and data files once before application workers start."""

    def __init__(self, settings: DemoSettings, app_root: Path, data_dir: Path) -> None:
        """Create a seeder for one application root and persistent data directory."""
        self._settings = settings
        self._app_root = app_root.resolve()
        self._data_dir = data_dir.resolve()
        self._logger = logging.getLogger(__name__)

    @classmethod
    def from_environment(cls) -> DemoContentSeeder:
        """Load settings and paths for the startup command."""
        app_root = Path(__file__).resolve().parent.parent
        data_dir = Path(os.environ.get('DATA_DIR', str(app_root)))
        settings = SettingsLoader.from_environment(
            os.environ.get('PC_CONFIG_FILE'), str(data_dir),
        ).load()
        return cls(settings.demo, app_root, data_dir)

    def seed(self) -> list[str]:
        """Copy enabled demo folders into empty targets and return seeded names."""
        if not self._settings.enabled:
            self._logger.info('Demo content seeding is disabled.')
            return []

        seed_sources = (
            (self._settings.analyses_dir, 'Analyses'),
            (self._settings.data_dir, 'Saved_data'),
        )
        seeded: list[str] = []
        for configured_source, target_name in seed_sources:
            source = self._resolve_source(configured_source, target_name)
            target = self._data_dir / target_name
            if self._seed_target(source, target, target_name):
                seeded.append(target_name)
        return seeded

    def _resolve_source(self, configured_source: str | None, bundled_name: str) -> Path:
        """Resolve custom sources relative to the app root or use the bundled folder."""
        if configured_source is None:
            return self._app_root / bundled_name
        source = Path(configured_source)
        return source if source.is_absolute() else self._app_root / source

    def _seed_target(self, source: Path, target: Path, target_name: str) -> bool:
        """Copy source contents only when the target is empty and distinct."""
        target.mkdir(parents=True, exist_ok=True)
        if any(target.iterdir()):
            self._logger.info('Keeping existing %s content; target is not empty.', target_name)
            return False
        if not source.is_dir():
            self._logger.warning('Demo source directory for %s does not exist: %s', target_name, source)
            return False
        if source.resolve() == target.resolve():
            self._logger.warning('Skipping demo seed for %s because source and target are identical.', target_name)
            return False

        source_entries = tuple(source.iterdir())
        if not source_entries:
            return False
        for source_entry in source_entries:
            destination = target / source_entry.name
            if source_entry.is_dir():
                shutil.copytree(source_entry, destination)
            else:
                shutil.copy2(source_entry, destination)
        self._logger.info('Seeded demo content for %s from %s.', target_name, source)
        return True


if __name__ == '__main__':
    DemoContentSeeder.from_environment().seed()

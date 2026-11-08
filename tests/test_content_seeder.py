# +----------------------------------------------+
# | DEMO CONTENT SEEDER TESTS                    |
# +----------------------------------------------+
"""Verify demo seeding honors enabled state, custom sources and empty targets."""

from pathlib import Path

from utils.app_settings import DemoSettings
from utils.content_seeder import DemoContentSeeder


class TestDemoContentSeeder:
    """Cover enabled, disabled and non-destructive demo content copies."""

    def test_enabled_seeder_copies_into_empty_targets(self, tmp_path: Path) -> None:
        """Copy bundled analyses and data into empty persistent directories."""
        app_root = tmp_path / 'app'
        data_dir = tmp_path / 'data'
        self._write_file(app_root / 'Analyses' / 'demo' / 'analysis.yaml', 'analysis')
        self._write_file(app_root / 'Saved_data' / 'demo.csv', 'value\n1\n')
        seeder = DemoContentSeeder(DemoSettings(True, None, None), app_root, data_dir)

        seeded = seeder.seed()

        assert seeded == ['Analyses', 'Saved_data']
        assert (data_dir / 'Analyses' / 'demo' / 'analysis.yaml').read_text(encoding='utf-8') == 'analysis'
        assert (data_dir / 'Saved_data' / 'demo.csv').read_text(encoding='utf-8') == 'value\n1\n'

    def test_disabled_seeder_copies_nothing(self, tmp_path: Path) -> None:
        """Leave empty target directories untouched when demo content is disabled."""
        app_root = tmp_path / 'app'
        data_dir = tmp_path / 'data'
        self._write_file(app_root / 'Analyses' / 'demo.yaml', 'analysis')
        seeder = DemoContentSeeder(DemoSettings(False, None, None), app_root, data_dir)

        seeded = seeder.seed()

        assert seeded == []
        assert not (data_dir / 'Analyses').exists()
        assert not (data_dir / 'Saved_data').exists()

    def test_custom_source_folders_replace_bundled_sources(self, tmp_path: Path) -> None:
        """Use configured source paths, resolving relative paths from the app root."""
        app_root = tmp_path / 'app'
        data_dir = tmp_path / 'data'
        self._write_file(app_root / 'custom_analyses' / 'custom.yaml', 'custom analysis')
        self._write_file(app_root / 'custom_data' / 'custom.csv', 'custom data')
        self._write_file(app_root / 'Analyses' / 'bundled.yaml', 'bundled analysis')
        seeder = DemoContentSeeder(
            DemoSettings(True, 'custom_analyses', 'custom_data'), app_root, data_dir,
        )

        seeded = seeder.seed()

        assert seeded == ['Analyses', 'Saved_data']
        assert (data_dir / 'Analyses' / 'custom.yaml').exists()
        assert not (data_dir / 'Analyses' / 'bundled.yaml').exists()
        assert (data_dir / 'Saved_data' / 'custom.csv').exists()

    def test_non_empty_targets_are_never_overwritten(self, tmp_path: Path) -> None:
        """Preserve all existing user files and avoid partial bundled copies."""
        app_root = tmp_path / 'app'
        data_dir = tmp_path / 'data'
        self._write_file(app_root / 'Analyses' / 'demo.yaml', 'bundled analysis')
        self._write_file(data_dir / 'Analyses' / 'user.yaml', 'user analysis')
        self._write_file(app_root / 'Saved_data' / 'demo.csv', 'bundled data')
        seeder = DemoContentSeeder(DemoSettings(True, None, None), app_root, data_dir)

        seeded = seeder.seed()

        assert seeded == ['Saved_data']
        assert (data_dir / 'Analyses' / 'user.yaml').read_text(encoding='utf-8') == 'user analysis'
        assert not (data_dir / 'Analyses' / 'demo.yaml').exists()
        assert (data_dir / 'Saved_data' / 'demo.csv').exists()

    def _write_file(self, path: Path, contents: str) -> None:
        """Create a UTF-8 test file and its parent directories."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding='utf-8')

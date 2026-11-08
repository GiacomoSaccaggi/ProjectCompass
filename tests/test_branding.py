# +----------------------------------------------+
# | BRANDING AND THEME TESTS                     |
# +----------------------------------------------+
"""Verify configured branding renders safely across shared and standalone pages."""

from pathlib import Path

from flask import Flask

from utils.app_settings import AppSettings, DefaultsSource, SettingsLoader, YamlFileSource


class TestBranding:
    """Check default rendering, custom branding and HTML escaping."""

    def test_default_header_preserves_current_branding(self, app: Flask) -> None:
        """Keep the shared header's current name, assets and theme by default."""
        webapp = app.config['WEBAPP']
        parts = webapp.html_parts

        assert '<title>ProjectCompass</title>' in parts['head']
        assert 'href = "/static/img/logo.png"' in parts['head']
        assert '--pc-primary: #222831' in parts['head']
        assert '/static/img/logo_icon.png' in parts['top_container']
        assert '<div id="cmd-palette"' in parts['top_container']
        assert 'var CMD_ITEMS=' in parts['top_container']
        assert 'var defaultDarkMode=false' in parts['top_container']
        assert 'Analysis' in parts['sidebar_menu']
        assert 'DEMO Project Notice: This is a demonstration-only project intended for evaluation purposes.' in parts[
            'sidebar_menu'
        ]

    def test_custom_branding_renders_in_header_and_standalone_pages(
        self, app: Flask, tmp_path: Path,
    ) -> None:
        """Apply configured names, images and colors in every header style."""
        settings = self._load_settings(
            tmp_path,
            'branding:\n'
            '  app_name: "<script>alert(1)</script> Compass"\n'
            '  logo_url: https://cdn.example/logo.svg\n'
            '  favicon_url: https://cdn.example/favicon.ico\n'
            '  backgrounds:\n'
            '    data: "https://cdn.example/data.png?v=2&theme=blue"\n'
            'theme:\n'
            '  primary_color: "#123"\n'
            '  accent_color: "#456"\n'
            '  highlight_color: "#789"\n'
            '  hover_color: "#ABC"\n',
        )
        webapp = app.config['WEBAPP']
        template_settings = settings.for_templates()
        webapp.apply_settings(template_settings)
        parts = webapp.html_parts

        assert '&lt;script&gt;alert(1)&lt;/script&gt; Compass' in parts['head']
        assert 'https://cdn.example/favicon.ico' in parts['head']
        assert '--pc-primary: #123' in parts['head']
        assert 'src="https://cdn.example/logo.svg"' in parts['sidebar_menu']
        assert '<svg width="100" height="100"' not in parts['sidebar_menu']
        assert '<script>alert(1)</script>' not in parts['sidebar_menu']
        assert '&lt;script&gt;alert(1)&lt;/script&gt; Compass' in webapp.environments_info['intro']
        assert '<script>alert(1)</script>' not in webapp.environments_info['intro']
        assert settings.branding.app_name in webapp.environments_info['links']
        assert 'ProjectCompass' not in webapp.environments_info['title']

        with app.test_request_context('/'):
            landing = app.jinja_env.get_template('landing.html').render(pc=template_settings)
            setup = app.jinja_env.get_template('setup_wizard.html').render(pc=template_settings, step='3')
            data_list = app.jinja_env.get_template('data_list.html').render(pc=template_settings)
            footer = app.jinja_env.get_template('components/branding_footer.html').render(pc=template_settings)

        assert '<h1>&lt;script&gt;alert(1)&lt;/script&gt; Compass</h1>' in landing
        assert '<title>&lt;script&gt;alert(1)&lt;/script&gt; Compass' in setup
        assert 'src="https://cdn.example/logo.svg"' in landing
        assert 'src="https://cdn.example/logo.svg"' in setup
        assert 'url("https://cdn.example/data.png?v=2&theme=blue")' in data_list
        assert '&lt;script&gt;alert(1)&lt;/script&gt; Compass' in footer
        assert '<script>alert(1)</script>' not in landing
        assert '<script>alert(1)</script>' not in setup

    def test_disabled_footer_is_not_rendered(self, app: Flask, tmp_path: Path) -> None:
        """Hide the shared footer when its setting is disabled."""
        settings = self._load_settings(tmp_path, 'branding:\n  footer:\n    enabled: false\n')

        with app.test_request_context('/'):
            footer = app.jinja_env.get_template('components/branding_footer.html').render(
                pc=settings.for_templates(),
            )

        assert '<footer' not in footer

    def _load_settings(self, tmp_path: Path, yaml_text: str) -> AppSettings:
        """Load a test configuration on top of built-in defaults."""
        config_path = tmp_path / 'projectcompass.yaml'
        config_path.write_text(yaml_text, encoding='utf-8')
        return SettingsLoader((DefaultsSource(), YamlFileSource(config_path, {}))).load()

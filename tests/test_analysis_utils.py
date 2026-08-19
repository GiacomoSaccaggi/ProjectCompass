"""Tests for utils/analysis_utils.py — covers read_single_analysis, read_multiple_analysis, make_archive, etc."""
import os
import shutil

import pytest
import yaml


@pytest.fixture
def analysis_dir(tmp_path):
    """Create a temporary analysis directory structure for testing."""
    analyses_dir = tmp_path / "Analyses"
    analyses_dir.mkdir()

    # Create a complete analysis
    analysis = analyses_dir / "Test Analysis"
    analysis.mkdir()
    (analysis / "analysis").mkdir()
    (analysis / "physical_output").mkdir()
    (analysis / "physical_output" / "main").mkdir()

    # metadata.yaml
    metadata = {
        'title': 'Test Analysis',
        'description': 'A test analysis for unit testing',
        'product': 'Research',
        'owner': 'testuser',
        'collaborators': 'collab1',
        'countries': 'Global',
        'start_date': '2024-01-15',
        'output_type': 'CSV',
        'output description': 'Test output',
        'dashboard link': '',
        'gitlab': 'https://gitlab.com/test/repo',
        'gdrive': 'https://drive.google.com/test',
        'inputs': {'param1': {'type': 'text', 'default': 'value1'}},
        'links': {'docs': 'https://docs.example.com'},
    }
    with open(analysis / "metadata.yaml", 'w') as f:
        yaml.dump(metadata, f)

    # output_versions.yaml
    with open(analysis / "output_versions.yaml", 'w') as f:
        f.write('---\n')

    # readme.md
    with open(analysis / "readme.md", 'w') as f:
        f.write("# Test Analysis\n")

    # structured analysis
    (analysis / "analysis" / "structured_analysis_main.py").write_text("def run(inputs, output_path): return {}")
    (analysis / "analysis" / "metadata_automatic_report.yaml").write_text("title: Test\ninputs: {}\n")

    # A physical output file
    (analysis / "physical_output" / "main" / "output.csv").write_text("col1,col2\n1,2\n")

    return tmp_path


@pytest.fixture
def analysis_utils(analysis_dir):
    """Create an AnalysisUtils instance pointed at the temp dir."""
    from utils.analysis_utils import AnalysisUtils

    class TestUtils(AnalysisUtils):
        def __init__(self, dir_path):
            self.analysis_folder = 'Analyses'
            self.save_folder_path = f'{dir_path}Analyses'
            os.makedirs(self.save_folder_path, exist_ok=True)

    return TestUtils(str(analysis_dir) + '/')


def test_extract_main_folder(analysis_utils, analysis_dir):
    assert analysis_utils.extract_main_folder() == str(analysis_dir / "Analyses")


def test_read_single_analysis_basic(analysis_utils):
    main_folder = analysis_utils.extract_main_folder()
    result = analysis_utils.read_single_analysis(main_folder, "Test Analysis")
    assert result['title'] == 'Test Analysis'
    assert result['product'] == 'Research'
    assert result['owner'] == 'testuser'
    assert result['description'] == 'A test analysis for unit testing'


def test_read_single_analysis_start_date(analysis_utils):
    main_folder = analysis_utils.extract_main_folder()
    result = analysis_utils.read_single_analysis(main_folder, "Test Analysis")
    assert result['start_date'] == '2024-01-15'


def test_read_single_analysis_gitlab_link(analysis_utils):
    main_folder = analysis_utils.extract_main_folder()
    result = analysis_utils.read_single_analysis(main_folder, "Test Analysis")
    assert 'gitlab' in result['gitlab_link_viz'].lower()
    assert 'href' in result['gitlab_link_viz']


def test_read_single_analysis_gdrive_link(analysis_utils):
    main_folder = analysis_utils.extract_main_folder()
    result = analysis_utils.read_single_analysis(main_folder, "Test Analysis")
    assert 'google' in result['gdrive_link_viz'].lower()


def test_read_single_analysis_inputs(analysis_utils):
    main_folder = analysis_utils.extract_main_folder()
    result = analysis_utils.read_single_analysis(main_folder, "Test Analysis")
    assert isinstance(result['inputs'], dict)
    assert 'param1' in result['inputs']
    assert 'inline_inputs' in result


def test_read_single_analysis_links(analysis_utils):
    main_folder = analysis_utils.extract_main_folder()
    result = analysis_utils.read_single_analysis(main_folder, "Test Analysis")
    assert isinstance(result['links'], dict)
    assert 'docs' in result['links']
    assert 'inline_links' in result


def test_read_single_analysis_structured(analysis_utils):
    main_folder = analysis_utils.extract_main_folder()
    result = analysis_utils.read_single_analysis(main_folder, "Test Analysis")
    assert result['structured_analysis'] == 'y'
    assert 'structured_metadata' in result


def test_read_single_analysis_physical_output(analysis_utils):
    main_folder = analysis_utils.extract_main_folder()
    result = analysis_utils.read_single_analysis(main_folder, "Test Analysis")
    assert 'physical_output' in result
    assert 'output.csv' in result['physical_output']


def test_read_single_analysis_last_modified(analysis_utils):
    main_folder = analysis_utils.extract_main_folder()
    result = analysis_utils.read_single_analysis(main_folder, "Test Analysis")
    assert 'last_modified' in result
    # Should be a date string
    assert len(result['last_modified']) == 10


def test_read_single_analysis_embedded_flag(analysis_utils):
    main_folder = analysis_utils.extract_main_folder()
    result = analysis_utils.read_single_analysis(main_folder, "Test Analysis")
    assert result['embedded'] == 'n'  # No '<' in dashboard link


def test_read_single_analysis_none_values_become_empty(analysis_utils, analysis_dir):
    """Test that None values in metadata are converted to empty strings."""
    # Overwrite metadata with a None field
    meta_path = analysis_dir / "Analyses" / "Test Analysis" / "metadata.yaml"
    metadata = {
        'title': 'Test Analysis', 'description': 'test', 'product': 'Test',
        'owner': 'user', 'collaborators': None, 'countries': 'US',
        'start_date': '2024-01-01', 'output_type': 'CSV',
        'output description': 'out', 'dashboard link': '',
        'gitlab': '', 'gdrive': '', 'inputs': {}, 'links': {},
    }
    with open(meta_path, 'w') as f:
        yaml.dump(metadata, f)

    main_folder = analysis_utils.extract_main_folder()
    result = analysis_utils.read_single_analysis(main_folder, "Test Analysis")
    assert result['collaborators'] == ''


def test_read_single_analysis_no_structured(analysis_utils, analysis_dir):
    """Analysis without structured_analysis_main.py marks structured_analysis='n'."""
    # Remove the structured files
    sa_dir = analysis_dir / "Analyses" / "Test Analysis" / "analysis"
    os.remove(sa_dir / "structured_analysis_main.py")

    main_folder = analysis_utils.extract_main_folder()
    result = analysis_utils.read_single_analysis(main_folder, "Test Analysis")
    assert result['structured_analysis'] == 'n'


def test_read_multiple_analysis(analysis_utils, analysis_dir):
    """read_multiple_analysis returns dict of all analyses."""
    # Create a second analysis
    analysis2 = analysis_dir / "Analyses" / "Second Analysis"
    analysis2.mkdir()
    (analysis2 / "analysis").mkdir()
    (analysis2 / "physical_output").mkdir()
    (analysis2 / "physical_output" / "main").mkdir()
    metadata = {
        'title': 'Second Analysis', 'description': 'another', 'product': 'ML',
        'owner': 'user2', 'collaborators': '', 'countries': 'EU',
        'start_date': '2024-06-01', 'output_type': 'HTML',
        'output description': 'report', 'dashboard link': '',
        'gitlab': '', 'gdrive': '', 'inputs': {}, 'links': {},
    }
    with open(analysis2 / "metadata.yaml", 'w') as f:
        yaml.dump(metadata, f)
    with open(analysis2 / "output_versions.yaml", 'w') as f:
        f.write('---\n')

    result = analysis_utils.read_multiple_analysis()
    assert 'Test Analysis' in result
    assert 'Second Analysis' in result
    assert result['Second Analysis']['product'] == 'ML'


def test_read_multiple_analysis_skips_dotfiles(analysis_utils, analysis_dir):
    """read_multiple_analysis skips files/folders with dots."""
    (analysis_dir / "Analyses" / ".DS_Store").write_text("")
    result = analysis_utils.read_multiple_analysis()
    assert '.DS_Store' not in result


def test_make_archive(tmp_path):
    """Test make_archive creates a zip file."""
    from utils.analysis_utils import AnalysisUtils

    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "file.txt").write_text("hello")

    dest = str(tmp_path / "output.zip")
    AnalysisUtils.make_archive(str(source_dir), dest)
    assert os.path.exists(dest)
    assert os.path.getsize(dest) > 0


def test_read_single_analysis_empty_gitlab(analysis_utils, analysis_dir):
    """Empty gitlab field produces no link HTML."""
    meta_path = analysis_dir / "Analyses" / "Test Analysis" / "metadata.yaml"
    metadata = {
        'title': 'Test Analysis', 'description': 'test', 'product': 'Test',
        'owner': 'user', 'collaborators': '', 'countries': 'US',
        'start_date': '2024-01-01', 'output_type': 'CSV',
        'output description': 'out', 'dashboard link': '',
        'gitlab': '', 'gdrive': '', 'inputs': {}, 'links': {},
    }
    with open(meta_path, 'w') as f:
        yaml.dump(metadata, f)

    result = analysis_utils.read_single_analysis(analysis_utils.extract_main_folder(), "Test Analysis")
    assert result['gitlab_link_viz'] == ''
    assert result['gdrive_link_viz'] == ''


def test_read_single_analysis_embedded_dashboard(analysis_utils, analysis_dir):
    """Dashboard link with '<' marks embedded='y'."""
    meta_path = analysis_dir / "Analyses" / "Test Analysis" / "metadata.yaml"
    metadata = {
        'title': 'Test Analysis', 'description': 'test', 'product': 'Test',
        'owner': 'user', 'collaborators': '', 'countries': 'US',
        'start_date': '2024-01-01', 'output_type': 'HTML',
        'output description': 'out',
        'dashboard link': '<iframe src="https://example.com"></iframe>',
        'gitlab': '', 'gdrive': '', 'inputs': {}, 'links': {},
    }
    with open(meta_path, 'w') as f:
        yaml.dump(metadata, f)

    result = analysis_utils.read_single_analysis(analysis_utils.extract_main_folder(), "Test Analysis")
    assert result['embedded'] == 'y'


def test_read_single_analysis_date_as_datetime(analysis_utils, analysis_dir):
    """start_date as a Python date object gets formatted correctly."""
    import datetime
    meta_path = analysis_dir / "Analyses" / "Test Analysis" / "metadata.yaml"
    metadata = {
        'title': 'Test Analysis', 'description': 'test', 'product': 'Test',
        'owner': 'user', 'collaborators': '', 'countries': 'US',
        'start_date': datetime.date(2024, 3, 15), 'output_type': 'CSV',
        'output description': 'out', 'dashboard link': '',
        'gitlab': '', 'gdrive': '', 'inputs': {}, 'links': {},
    }
    with open(meta_path, 'w') as f:
        yaml.dump(metadata, f)

    result = analysis_utils.read_single_analysis(analysis_utils.extract_main_folder(), "Test Analysis")
    assert result['start_date'] == '2024-03-15'


# --- Tests via the real ProjectCompass class (hits the actual module for coverage) ---

def test_read_single_analysis_via_app(client, app):
    """read_single_analysis works through the app's webapp object."""
    with app.app_context():
        webapp = app.config['WEBAPP']
        main_folder = webapp.extract_main_folder()
        # Use one of the real analyses in the project
        analyses = [d for d in os.listdir(main_folder) if os.path.isdir(os.path.join(main_folder, d)) and '.' not in d]
        if analyses:
            result = webapp.read_single_analysis(main_folder, analyses[0])
            assert 'title' in result
            assert 'folder' in result
            assert 'structured_analysis' in result


def test_read_multiple_analysis_via_app(client, app):
    """read_multiple_analysis works through the app."""
    with app.app_context():
        webapp = app.config['WEBAPP']
        result = webapp.read_multiple_analysis()
        assert isinstance(result, dict)
        # Should find the existing analyses in the project
        assert len(result) >= 1


def test_produce_readme_via_app(client, app):
    """produce_readme generates readme.md in the analyses folder."""
    with app.app_context():
        webapp = app.config['WEBAPP']
        result = webapp.produce_readme()
        assert isinstance(result, dict)
        readme_path = os.path.join(webapp.extract_main_folder(), 'readme.md')
        assert os.path.exists(readme_path)


def test_upload_new_analysis(client, app):
    """Test upload_new_analysis creates all expected files/folders."""
    import io

    from werkzeug.datastructures import FileStorage

    with app.app_context():
        webapp = app.config['WEBAPP']
        title = '_TestUpload_Temp'

        # Mock request with form data
        class MockRequest:
            def __init__(self):
                self.form = {
                    'title': title,
                    'description': 'Test description',
                    'email': 'test@test.com',
                    'collaborators': 'collab1',
                    'start_date': '2024-01-01',
                    'product': 'Testing',
                    'countries': 'Global',
                    'inputs': 'param1:text=default1',
                    'links': 'doc===https://example.com',
                    'gdrive': '',
                    'gitlab': '',
                    'dashboard': '',
                    'output_type': 'CSV',
                    'output_description': 'Test output',
                }
                # Mock file objects
                self.files = {
                    'output_file': FileStorage(io.BytesIO(b''), filename=''),
                }

            def getlist(self, key):
                return []

        class MockFiles(dict):
            def getlist(self, key):
                return []

        mock_req = MockRequest()
        mock_req.files = MockFiles(mock_req.files)

        webapp.upload_new_analysis(mock_req)

        # Verify folder was created
        analysis_path = os.path.join(webapp.extract_main_folder(), title)
        assert os.path.isdir(analysis_path)
        assert os.path.exists(os.path.join(analysis_path, 'metadata.yaml'))
        assert os.path.exists(os.path.join(analysis_path, 'output_versions.yaml'))

        # Cleanup
        shutil.rmtree(analysis_path, ignore_errors=True)


def test_modify_analysis(client, app):
    """Test modify_analysis updates metadata.yaml correctly."""
    import io

    from werkzeug.datastructures import FileStorage

    with app.app_context():
        webapp = app.config['WEBAPP']
        # Use a temp analysis — create it first
        title = '_TestModify_Temp'
        analysis_path = os.path.join(webapp.extract_main_folder(), title)
        os.makedirs(os.path.join(analysis_path, 'physical_output', 'main'), exist_ok=True)
        os.makedirs(os.path.join(analysis_path, 'analysis'), exist_ok=True)

        # Write initial metadata
        with open(os.path.join(analysis_path, 'metadata.yaml'), 'w') as f:
            f.write("title: _TestModify_Temp\n")
        with open(os.path.join(analysis_path, 'output_versions.yaml'), 'w') as f:
            f.write('main version: ""\n')

        class MockRequest:
            def __init__(self):
                self.form = {
                    'title': title,
                    'description': 'Updated description',
                    'email': 'updated@test.com',
                    'collaborators': 'new_collab',
                    'start_date': '2024-06-01',
                    'product': 'Updated Product',
                    'countries': 'EU',
                    'inputs': '',
                    'links': '',
                    'gdrive': 'https://drive.google.com/updated',
                    'gitlab': 'https://gitlab.com/updated',
                    'dashboard': '',
                    'output_type': 'HTML',
                    'output_description': 'Updated output',
                }
                self.files = {'output_file': FileStorage(io.BytesIO(b''), filename='')}

        webapp.modify_analysis(MockRequest())

        # Verify metadata was updated
        with open(os.path.join(analysis_path, 'metadata.yaml')) as f:
            content = f.read()
        assert 'Updated description' in content
        assert 'updated@test.com' in content
        assert 'Updated Product' in content

        # Cleanup
        shutil.rmtree(analysis_path, ignore_errors=True)

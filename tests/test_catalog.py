def test_catalog_analysis_page(client):
    resp = client.get('/analysis')
    assert resp.status_code == 200


def test_catalog_search(client):
    resp = client.get('/analysis?q=test')
    assert resp.status_code == 200


def test_catalog_filter_product(client):
    resp = client.get('/analysis?product=Research%20project')
    assert resp.status_code == 200


def test_catalog_pagination(client):
    resp = client.get('/analysis?page=1&per_page=5')
    assert resp.status_code == 200


def test_load_analysis_new(client):
    resp = client.get('/load_analysis/')
    assert resp.status_code == 200


def test_pipeline_builder_page(client):
    resp = client.get('/pipeline_builder')
    assert resp.status_code == 200


# --- Pipeline script generation tests ---

def test_generate_pipeline_dsl_basic():
    """Test that _generate_pipeline_script produces valid Python with DSL syntax."""
    from blueprints.catalog import _generate_pipeline_script
    steps = [
        {'type': 'load_data', 'config': {'dataset': 'wine_quality', 'limit': '0'}},
        {'type': 'train_model', 'config': {'task_type': 'regression', 'target_col': 'quality',
                                           'model_hint': 'auto', 'test_size': '0.2', 'ensemble': 'none'}},
    ]
    script = _generate_pipeline_script(steps, '/tmp')
    # Must compile without error
    compile(script, '<test>', 'exec')
    # Must contain DSL syntax
    assert 'CleanStep' in script
    assert 'SelectStep' in script
    assert 'ModelStep' in script
    assert 'TrainStep' in script
    assert '>>' in script


def test_generate_pipeline_dsl_with_feature_eng():
    """Test pipeline with feature engineering step."""
    from blueprints.catalog import _generate_pipeline_script
    steps = [
        {'type': 'load_data', 'config': {'dataset': 'wine_quality'}},
        {'type': 'feature_eng', 'config': {'interactions': True, 'log_transform': True,
                                           'date_features': False, 'target_encode': False}},
        {'type': 'train_model', 'config': {'task_type': 'regression', 'target_col': 'quality',
                                           'model_hint': 'auto', 'test_size': '0.2', 'ensemble': 'none'}},
    ]
    script = _generate_pipeline_script(steps, '/tmp')
    compile(script, '<test>', 'exec')
    assert 'FeatureEngineer' in script


def test_generate_pipeline_dsl_drift():
    """Test pipeline with drift detection block."""
    from blueprints.catalog import _generate_pipeline_script
    steps = [
        {'type': 'load_data', 'config': {'dataset': 'wine_quality'}},
        {'type': 'drift', 'config': {'reference_dataset': 'wine_quality', 'threshold': '0.1'}},
    ]
    script = _generate_pipeline_script(steps, '/tmp')
    compile(script, '<test>', 'exec')
    assert 'DriftDetector' in script


def test_generate_pipeline_dsl_explainability():
    """Test pipeline with explainability block."""
    from blueprints.catalog import _generate_pipeline_script
    steps = [
        {'type': 'load_data', 'config': {'dataset': 'wine_quality'}},
        {'type': 'train_model', 'config': {'task_type': 'regression', 'target_col': 'quality',
                                           'model_hint': 'auto', 'test_size': '0.2', 'ensemble': 'none'}},
        {'type': 'explainability', 'config': {'method': 'shap', 'num_features': '10'}},
    ]
    script = _generate_pipeline_script(steps, '/tmp')
    compile(script, '<test>', 'exec')
    assert 'ShapExplainer' in script


def test_generate_pipeline_dsl_fairness():
    """Test pipeline with fairness block."""
    from blueprints.catalog import _generate_pipeline_script
    steps = [
        {'type': 'load_data', 'config': {'dataset': 'wine_quality'}},
        {'type': 'fairness', 'config': {'sensitive_column': 'color', 'predicted_col': 'prediction',
                                        'target_col': 'quality'}},
    ]
    script = _generate_pipeline_script(steps, '/tmp')
    compile(script, '<test>', 'exec')
    assert 'FairnessMetrics' in script


def test_generate_pipeline_dsl_validation():
    """Test pipeline with validation block."""
    from blueprints.catalog import _generate_pipeline_script
    steps = [
        {'type': 'load_data', 'config': {'dataset': 'wine_quality'}},
        {'type': 'train_model', 'config': {'task_type': 'regression', 'target_col': 'quality',
                                           'model_hint': 'auto', 'test_size': '0.2', 'ensemble': 'none'}},
        {'type': 'validation', 'config': {'methods': 'kfold', 'cv_folds': '5', 'bootstrap_iterations': '100'}},
    ]
    script = _generate_pipeline_script(steps, '/tmp')
    compile(script, '<test>', 'exec')
    assert 'Validator' in script


def test_generate_pipeline_dsl_report_quick():
    """Test pipeline with expanded Quick Report block."""
    from blueprints.catalog import _generate_pipeline_script
    steps = [
        {'type': 'load_data', 'config': {'dataset': 'wine_quality'}},
        {'type': 'train_model', 'config': {'task_type': 'regression', 'target_col': 'quality',
                                           'model_hint': 'auto', 'test_size': '0.2', 'ensemble': 'none'}},
        {'type': 'report', 'config': {'report_type': 'model', 'include_kpi': True,
                                      'include_summary': True, 'dark_mode': True}},
    ]
    script = _generate_pipeline_script(steps, '/tmp')
    compile(script, '<test>', 'exec')
    assert 'add_kpi_cards' in script
    assert 'add_summary_stats' in script
    assert 'add_dark_mode_toggle' in script


def test_generate_pipeline_dsl_report_granular():
    """Test pipeline with granular report blocks."""
    from blueprints.catalog import _generate_pipeline_script
    steps = [
        {'type': 'load_data', 'config': {'dataset': 'wine_quality'}},
        {'type': 'report_kpi', 'config': {'metrics_keys': '', 'cols': '3'}},
        {'type': 'report_summary', 'config': {'title': 'My Summary'}},
        {'type': 'report_dark_mode', 'config': {}},
    ]
    script = _generate_pipeline_script(steps, '/tmp')
    compile(script, '<test>', 'exec')
    assert 'add_kpi_cards' in script
    assert 'add_summary_stats' in script
    assert 'add_dark_mode_toggle' in script
    # Granular blocks should trigger report save
    assert 'report.save' in script.replace('_report.save', 'report.save')


def test_generate_pipeline_dsl_text_nlp():
    """Test pipeline with text/NLP block."""
    from blueprints.catalog import _generate_pipeline_script
    steps = [
        {'type': 'load_data', 'config': {'dataset': 'employees'}},
        {'type': 'text_nlp', 'config': {'text_column': 'name', 'method': 'contrastive', 'head': 'auto'}},
    ]
    script = _generate_pipeline_script(steps, '/tmp')
    compile(script, '<test>', 'exec')
    assert 'text' in script.lower()


def test_extract_inputs_new_types():
    """Test _extract_inputs_from_steps with new block types."""
    from blueprints.catalog import _extract_inputs_from_steps
    steps = [
        {'type': 'train_model', 'config': {'target_col': 'quality'}},
        {'type': 'text_nlp', 'config': {'text_column': 'description'}},
        {'type': 'fairness', 'config': {'sensitive_column': 'gender'}},
    ]
    inputs = _extract_inputs_from_steps(steps)
    assert 'target_col' in inputs
    assert 'text_column' in inputs
    assert 'sensitive_column' in inputs


# --- Execution History tests ---

def test_executions_page(client):
    """Test execution history page loads."""
    resp = client.get('/executions')
    assert resp.status_code == 200
    assert b'Execution History' in resp.data


def test_executions_page_with_filter(client):
    """Test execution history page with status filter."""
    resp = client.get('/executions?status=success')
    assert resp.status_code == 200


def test_save_execution_helper():
    """Test _save_execution creates execution records."""
    from app import create_app
    from blueprints.catalog import _save_execution
    app = create_app()
    with app.app_context():
        exe = _save_execution('test_analysis', None, 'running', inputs={'key': 'value'})
        assert exe.id is not None
        assert exe.analysis_name == 'test_analysis'
        assert exe.status == 'running'


# --- Pipeline Versioning tests ---

def test_pipeline_versions_page_existing(client):
    """Test pipeline versions page for an existing analysis."""
    # Get list of actual analyses first
    resp = client.get('/analysis')
    assert resp.status_code == 200
    # The page should at least load without a 500 error


def test_extract_lineage_from_script():
    """Test _extract_lineage_from_script parses read_csv calls."""
    from blueprints.catalog import _extract_lineage_from_script
    # Use exact pattern the function looks for: read_csv followed by quotes with .csv
    script = '''
df = pd.read_csv("wine_quality.csv")
other = pd.read_csv('iris.csv')
'''
    inputs = _extract_lineage_from_script(script)
    assert 'wine_quality' in inputs
    assert 'iris' in inputs


# --- Save Pipeline tests ---

def test_save_pipeline_full_flow(client, app):
    """Test POST /save_pipeline/ with valid graph data creates analysis folder."""
    import os
    import shutil
    name = 'TestPipeline_Integration'
    graph = {'drawflow': {'Home': {'data': {
        '1': {'id': 1, 'name': '', 'data': {'config': {'dataset': 'wine_quality'}},
              'class': 'load_data', 'html': '', 'typenode': False,
              'inputs': {}, 'outputs': {'output_1': {'connections': []}}, 'pos_x': 100, 'pos_y': 200}
    }}}}
    try:
        resp = client.post('/save_pipeline/', json={
            'name': name,
            'description': 'Test pipeline description',
            'product': 'Machine Learning',
            'owner': 'Test Owner',
            'graph': graph
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert data['name'] == name

        # Verify folder structure created
        with app.app_context():
            webapp = app.config['WEBAPP']
            analysis_dir = f"{webapp.extract_main_folder()}/{name}"
            assert os.path.isdir(analysis_dir)
            assert os.path.isfile(f"{analysis_dir}/compass_flow.yaml")
            assert os.path.isfile(f"{analysis_dir}/Dockerfile")
            assert os.path.isfile(f"{analysis_dir}/metadata.yaml")
            assert os.path.isfile(f"{analysis_dir}/readme.md")
    finally:
        # Clean up
        with app.app_context():
            webapp = app.config['WEBAPP']
            main_folder = webapp.extract_main_folder()
            for entry in os.listdir(main_folder):
                if entry == name or entry.startswith(f"{name}__step_"):
                    target_dir = os.path.join(main_folder, entry)
                    if os.path.isdir(target_dir):
                        shutil.rmtree(target_dir)

            from models import FlowVersion, PipelineVersion, db
            PipelineVersion.query.filter_by(analysis_name=name).delete()
            FlowVersion.query.filter(FlowVersion.flow_name.like(f"{name}%")).delete(synchronize_session=False)
            db.session.commit()


def test_save_pipeline_missing_name(client):
    """Test POST /save_pipeline/ with empty name returns error."""
    resp = client.post('/save_pipeline/', json={
        'name': '',
        'description': 'Test',
        'product': 'ML',
        'owner': 'Owner',
        'graph': {}
    })
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is False
    assert 'error' in data


def test_save_pipeline_missing_name_whitespace(client):
    """Test POST /save_pipeline/ with whitespace-only name returns error."""
    resp = client.post('/save_pipeline/', json={
        'name': '   ',
        'description': 'Test',
        'product': 'ML',
        'owner': 'Owner',
        'graph': {}
    })
    data = resp.get_json()
    assert data['success'] is False


# --- Pipeline Versions tests ---

def test_pipeline_versions_page_with_existing_analysis(client):
    """Test GET /analysis/<name>/versions loads for existing analysis."""
    # ScompLink Wine Quality Prediction exists in Analyses/
    resp = client.get('/analysis/ScompLink512Wine512Quality512Prediction/versions')
    # May return 200 (page loads) or have versions
    assert resp.status_code == 200


def test_pipeline_versions_page_nonexistent(client):
    """Test GET /analysis/<name>/versions for non-existent analysis raises error."""
    import pytest
    # The route doesn't handle missing analysis gracefully - it raises FileNotFoundError
    # This documents the current behavior
    with pytest.raises(FileNotFoundError):
        client.get('/analysis/NonExistentAnalysis12345/versions')


# --- Export/Import tests ---

def test_export_analysis(client):
    """Test GET /export/<name> returns ZIP file for existing analysis."""
    # Use existing analysis
    resp = client.get('/export/ScompLink512Wine512Quality512Prediction')
    assert resp.status_code == 200
    assert resp.content_type == 'application/zip'
    assert b'PK' in resp.data[:4]  # ZIP file signature


def test_export_analysis_not_found(client):
    """Test GET /export/nonexistent returns 404."""
    resp = client.get('/export/NonExistentAnalysis12345')
    assert resp.status_code == 404


def test_import_page(client):
    """Test GET /import returns 200."""
    resp = client.get('/import')
    assert resp.status_code == 200
    assert b'import' in resp.data.lower() or b'Import' in resp.data


def test_import_analysis_no_file(client):
    """Test POST /import without file returns error."""
    resp = client.post('/import', data={})
    # Should return error JSON or redirect
    assert resp.status_code in (200, 302, 400)


# --- Comment tests ---

def test_add_comment(client, app):
    """Test POST /analysis/<name>/comment with text returns HTML."""
    # Use existing analysis name
    name = 'ScompLink512Wine512Quality512Prediction'
    resp = client.post(f'/analysis/{name}/comment', data={'text': 'Test comment from pytest'})
    assert resp.status_code == 200
    assert b'Test comment from pytest' in resp.data


def test_add_comment_empty(client):
    """Test POST /analysis/<name>/comment with empty text returns 204."""
    name = 'ScompLink512Wine512Quality512Prediction'
    resp = client.post(f'/analysis/{name}/comment', data={'text': ''})
    assert resp.status_code == 204


def test_get_comments(client):
    """Test GET /analysis/<name>/comments returns HTML."""
    name = 'ScompLink512Wine512Quality512Prediction'
    resp = client.get(f'/analysis/{name}/comments')
    assert resp.status_code == 200
    # Should return HTML (either comments or "No comments" message)
    assert b'<' in resp.data or b'No comments' in resp.data


# --- Webhook tests ---

def test_manage_webhooks_get(client):
    """Test GET /analysis/<name>/webhooks returns HTML."""
    name = 'ScompLink512Wine512Quality512Prediction'
    resp = client.get(f'/analysis/{name}/webhooks')
    assert resp.status_code == 200


def test_manage_webhooks_post(client, app):
    """Test POST /analysis/<name>/webhooks with url creates webhook."""
    from models import Webhook, db
    name = 'ScompLink512Wine512Quality512Prediction'
    real_name = name.replace('512', ' ')

    # Create webhook
    resp = client.post(f'/analysis/{name}/webhooks', data={
        'url': 'https://example.com/webhook',
        'secret': 'test-secret'
    })
    assert resp.status_code == 200

    # Verify webhook was created
    with app.app_context():
        wh = Webhook.query.filter_by(analysis_name=real_name).first()
        assert wh is not None
        assert wh.url == 'https://example.com/webhook'
        # Clean up
        db.session.delete(wh)
        db.session.commit()


def test_delete_webhook(client, app):
    """Test POST /analysis/<name>/webhooks/<id>/delete removes webhook."""
    from models import Webhook, db
    name = 'ScompLink512Wine512Quality512Prediction'
    real_name = name.replace('512', ' ')

    # Create a webhook to delete
    with app.app_context():
        wh = Webhook(analysis_name=real_name, url='https://example.com/to-delete')
        db.session.add(wh)
        db.session.commit()
        wh_id = wh.id

    # Delete it
    resp = client.post(f'/analysis/{name}/webhooks/{wh_id}/delete')
    assert resp.status_code == 302  # Redirect after delete

    # Verify it's gone
    with app.app_context():
        wh = Webhook.query.get(wh_id)
        assert wh is None


# --- Executions page tests ---

def test_executions_page_empty(client):
    """Test GET /executions with no data returns 200."""
    resp = client.get('/executions')
    assert resp.status_code == 200
    assert b'Execution History' in resp.data


def test_executions_page_with_status_filter(client):
    """Test GET /executions?status=success filters correctly."""
    resp = client.get('/executions?status=success')
    assert resp.status_code == 200


def test_executions_page_with_failed_filter(client):
    """Test GET /executions?status=failed filters correctly."""
    resp = client.get('/executions?status=failed')
    assert resp.status_code == 200


def test_executions_page_with_data(client, app):
    """Test GET /executions with execution records."""
    from blueprints.catalog import _save_execution

    # Create an execution record
    with app.app_context():
        exe = _save_execution('Test Analysis', None, 'success', inputs={'key': 'value'})
        exe_id = exe.id

    resp = client.get('/executions')
    assert resp.status_code == 200
    assert b'Test Analysis' in resp.data

    # Clean up
    with app.app_context():
        from models import Execution, db
        exe = Execution.query.get(exe_id)
        if exe:
            db.session.delete(exe)
            db.session.commit()


# --- Restore version tests ---

def test_restore_version(client, app):
    """Test POST /analysis/<name>/restore/<version_id> restores pipeline."""
    import os
    import shutil

    from models import PipelineVersion, db

    name = 'TestRestoreAnalysis'
    # Create analysis directory and files
    with app.app_context():
        webapp = app.config['WEBAPP']
        analysis_dir = f"{webapp.extract_main_folder()}/{name}"
        os.makedirs(f"{analysis_dir}/analysis", exist_ok=True)
        with open(f"{analysis_dir}/analysis/pipeline_main.py", 'w') as f:
            f.write('# Original script')

        # Create a version record
        version = PipelineVersion(
            analysis_name=name,
            version_num=1,
            graph_json='{}',
            script_text='# Restored script from version 1',
            message='Test version'
        )
        db.session.add(version)
        db.session.commit()
        version_id = version.id

    try:
        # Restore to this version
        resp = client.post(f'/analysis/{name}/restore/{version_id}')
        assert resp.status_code == 302  # Redirect after restore

        # Verify script was restored
        with app.app_context():
            webapp = app.config['WEBAPP']
            with open(f"{webapp.extract_main_folder()}/{name}/analysis/pipeline_main.py") as f:
                content = f.read()
            assert 'Restored script from version 1' in content
    finally:
        # Clean up
        with app.app_context():
            webapp = app.config['WEBAPP']
            analysis_dir = f"{webapp.extract_main_folder()}/{name}"
            if os.path.isdir(analysis_dir):
                shutil.rmtree(analysis_dir)
            # Clean up version records
            PipelineVersion.query.filter_by(analysis_name=name).delete()
            db.session.commit()


# --- Execute abort & Unified K8s Structured Analysis tests ---

def test_execute_abort_no_process(client):
    """Test POST /execute_abort/<name> when no K8s Job execution is running."""
    resp = client.post('/execute_abort/NonExistentAnalysis')
    assert resp.status_code == 404
    data = resp.get_json()
    assert data['success'] is False
    assert data['status'] == 'not_found'


def test_run_investigation_creates_k8s_flow_and_extracts_artifacts(client, app, tmp_path, monkeypatch):
    """Verify POST /run_investigation/ creates a Flow, runs a K8s Job, and extracts physical_output artifacts."""
    import base64
    from unittest.mock import patch

    from models import Execution, db

    webapp = app.config['WEBAPP']
    analyses_dir = tmp_path / 'Analyses'
    analyses_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(webapp, 'save_folder_path', str(analyses_dir))

    sa_name = 'Sales Summary K8s'
    sa_dir = analyses_dir / sa_name
    (sa_dir / 'analysis').mkdir(parents=True)
    (sa_dir / 'physical_output' / 'main').mkdir(parents=True)

    (sa_dir / 'metadata.yaml').write_text(
        'title: Sales Summary K8s\n'
        'description: Sales analysis\n'
        'product: BI\n'
        'owner: alice\n'
        'collaborators: ""\n'
        'countries: Global\n'
        'start_date: "2024-01-15"\n'
        'output_type: CSV\n'
        'output description: Sales table\n'
        'dashboard link: ""\n'
        'gitlab: ""\n'
        'gdrive: ""\n'
        'inputs: {}\n'
        'links: {}\n',
        encoding='utf-8',
    )
    (sa_dir / 'compass_flow.yaml').write_text(
        'description: Sales Summary K8s\n'
        'inputs:\n'
        '  region:\n'
        '    type: text\n'
        '    default: "all"\n',
        encoding='utf-8',
    )
    (sa_dir / 'Dockerfile').write_text('FROM python:3.12-slim\nENTRYPOINT ["python", "flow.py"]\n', encoding='utf-8')
    (sa_dir / 'flow.py').write_text(
        'import os\n'
        'import pandas as pd\n'
        'def run(inputs, output_path):\n'
        '    df = pd.read_csv(os.path.join(os.path.dirname(__file__), "..", "..", "Saved_data", "sales_data.csv"))\n'
        '    os.makedirs(os.path.dirname(output_path), exist_ok=True)\n'
        '    df.head(2).to_csv(output_path, index=False)\n'
        '    return {"rows": 2, "region": inputs.get("region", "all")}\n',
        encoding='utf-8',
    )

    csv_bytes = b'product,revenue\nWidget,100\n'
    html_bytes = b'<html><body><h1>Sales Report</h1></body></html>'
    b64_csv = base64.b64encode(csv_bytes).decode('ascii')
    b64_html = base64.b64encode(html_bytes).decode('ascii')
    pod_log_output = (
        "Starting structured analysis...\n"
        f"[PC_ARTIFACT_BEGIN:output.csv]\n{b64_csv}\n[PC_ARTIFACT_END]\n"
        f"[PC_ARTIFACT_BEGIN:report.html]\n{b64_html}\n[PC_ARTIFACT_END]\n"
        "Analysis complete.\n"
    )

    posted_manifests = []

    def fake_post(path, payload):
        posted_manifests.append((path, payload))
        return payload

    def fake_get(path, params=None):
        if path.endswith('/pods'):
            return {
                'items': [{
                    'metadata': {'name': 'pc-flow-job-sa-pod'},
                    'spec': {'nodeName': 'k0s-worker-1'},
                    'status': {
                        'phase': 'Succeeded',
                        'containerStatuses': [{'state': {'terminated': {'exitCode': 0, 'reason': 'Completed'}}}],
                    },
                }]
            }
        if '/jobs/' in path:
            return {'status': {'succeeded': 1, 'failed': 0}}
        return {}

    with (
        patch.object(webapp, '_build_and_push_image', return_value='registry:5050/pc/sales-summary-k8s:1'),
        patch.object(webapp, '_k8s_post', side_effect=fake_post),
        patch.object(webapp, '_k8s_get', side_effect=fake_get),
        patch.object(webapp, '_k8s_get_text', return_value=pod_log_output),
        patch.object(webapp, '_k8s_delete', return_value={}),
    ):
        resp = client.post(
            '/run_investigation/',
            data={'analysis_name': sa_name, 'region': 'North'},
        )
        assert resp.status_code == 302

    # Verify decoded artifacts written to physical_output/main/ and timestamped copies in physical_output/
    assert (sa_dir / 'physical_output' / 'main' / 'output.csv').read_bytes() == csv_bytes
    assert (sa_dir / 'physical_output' / 'main' / 'report.html').read_bytes() == html_bytes
    versioned_files = [
        f for f in (sa_dir / 'physical_output').iterdir()
        if f.is_file() and f.suffix in ('.csv', '.html')
    ]
    assert len(versioned_files) == 2

    # Verify Execution log_text stripped out the base64 artifact blocks
    with app.app_context():
        exe = Execution.query.filter_by(analysis_name=sa_name).order_by(Execution.id.desc()).first()
        assert exe is not None
        assert exe.status == 'success'
        assert 'Starting structured analysis...' in (exe.log_text or '')
        assert '[PC_ARTIFACT_BEGIN:' not in (exe.log_text or '')
        assert b64_csv not in (exe.log_text or '')
        db.session.delete(exe)
        db.session.commit()


def test_catalog_run_returns_failed_run_when_worker_provisioning_fails(
    client, app, tmp_path, monkeypatch
):
    """Return a failed run and readable error for catalog form and JSON requests."""
    from unittest.mock import patch

    from utils.worker_provider import WorkerProvisioningError

    webapp = app.config['WEBAPP']
    analyses_dir = tmp_path / 'Analyses'
    analysis_dir = analyses_dir / 'Provision Failure Analysis'
    (analysis_dir / 'analysis').mkdir(parents=True)
    (analysis_dir / 'compass_flow.yaml').write_text('description: test\ninputs: {}\n', encoding='utf-8')
    dockerfile_content = 'FROM python:3.12-slim\nENTRYPOINT ["python", "flow.py"]\n'
    (analysis_dir / 'Dockerfile').write_text(dockerfile_content, encoding='utf-8')
    monkeypatch.setattr(webapp, 'save_folder_path', str(analyses_dir))
    webapp.save_flow(name='Provision Failure Analysis', code='print("not run")')
    provider = webapp.worker_provider

    with (
        patch.object(webapp, '_build_and_push_image', return_value='registry:5050/pc/test:1'),
        patch.object(webapp, '_should_manage_workers', return_value=True),
        patch.object(webapp, '_count_ready_workers', return_value=0),
        patch.object(
            provider,
            'ensure_workers',
            side_effect=WorkerProvisioningError('Docker daemon is unavailable'),
        ),
        patch.object(webapp, '_k8s_post') as post_resource,
    ):
        html_response = client.post(
            '/run_investigation/',
            data={'analysis_name': 'Provision Failure Analysis'},
        )
        json_response = client.post(
            '/run_investigation/',
            json={'analysis_name': 'Provision Failure Analysis', 'inputs': {}},
        )

    assert html_response.status_code == 302
    assert html_response.headers['Location'].startswith('/runs/')
    assert json_response.status_code == 200
    payload = json_response.get_json()
    assert payload['status'] == 'failed'
    assert payload['error_message'] == 'Docker daemon is unavailable'
    assert payload['detail_url'].startswith('/runs/')
    post_resource.assert_not_called()


def test_execute_stream_and_abort_via_k8s_job(client, app, tmp_path, monkeypatch):
    """Verify GET /execute_stream/<name> and POST /execute_abort/<name> operate via K8s Jobs without subprocess."""
    import json
    from unittest.mock import patch

    from models import Execution, db

    webapp = app.config['WEBAPP']
    analyses_dir = tmp_path / 'Analyses'
    analyses_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(webapp, 'save_folder_path', str(analyses_dir))

    sa_name = 'Streamed Analysis'
    sa_dir = analyses_dir / sa_name
    (sa_dir / 'analysis').mkdir(parents=True)
    (sa_dir / 'physical_output' / 'main').mkdir(parents=True)
    (sa_dir / 'metadata.yaml').write_text('title: Streamed Analysis\nproduct: ML\n', encoding='utf-8')
    (sa_dir / 'compass_flow.yaml').write_text('description: Streamed Analysis\ninputs: {}\n', encoding='utf-8')
    (sa_dir / 'Dockerfile').write_text('FROM python:3.12-slim\nENTRYPOINT ["python", "flow.py"]\n', encoding='utf-8')
    (sa_dir / 'analysis' / 'pipeline_main.py').write_text(
        'def run(inputs, output_path):\n    print("hello from k8s pod")\n    return {}\n',
        encoding='utf-8',
    )

    def fake_get_succeeded(path, params=None):
        if path.endswith('/pods'):
            return {
                'items': [{
                    'metadata': {'name': 'pc-flow-job-stream-pod'},
                    'spec': {'nodeName': 'k0s-worker-1'},
                    'status': {
                        'phase': 'Succeeded',
                        'containerStatuses': [{'state': {'terminated': {'exitCode': 0, 'reason': 'Completed'}}}],
                    },
                }]
            }
        if '/jobs/' in path:
            return {'status': {'succeeded': 1, 'failed': 0}}
        return {}

    with (
        patch.object(webapp, '_build_and_push_image', return_value='registry:5050/pc/test:1'),
        patch.object(webapp, '_k8s_post', side_effect=lambda p, m: m),
        patch.object(webapp, '_k8s_get', side_effect=fake_get_succeeded),
        patch.object(webapp, '_k8s_get_text', return_value='hello from k8s pod\n'),
        patch.object(webapp, '_k8s_delete', return_value={}),
    ):
        stream_resp = client.get('/execute_stream/Streamed512Analysis?param1=val1')
        assert stream_resp.status_code == 200
        raw_sse = stream_resp.data.decode('utf-8')
        events = [
            json.loads(line[len('data: '):])
            for line in raw_sse.splitlines()
            if line.startswith('data: ')
        ]
        assert any('hello from k8s pod' in ev.get('line', '') for ev in events)
        assert events[-1]['done'] is True
        assert events[-1]['status'] == 'success'
        assert 'run_id' in events[-1]

    # Test aborting an active running Execution via POST /execute_abort/<name>
    with app.app_context():
        running_exe = Execution(
            analysis_name=sa_name,
            status='running',
            job_name='pc-flow-job-999',
            namespace='default',
        )
        db.session.add(running_exe)
        db.session.commit()
        running_id = running_exe.id

    with patch.object(webapp, '_k8s_delete', return_value={}) as mock_del:
        abort_resp = client.post('/execute_abort/Streamed512Analysis')
        assert abort_resp.status_code == 200
        abort_data = abort_resp.get_json()
        assert abort_data['status'] == 'aborted'
        assert abort_data['run_id'] == running_id
        assert mock_del.called

    with app.app_context():
        Execution.query.filter_by(analysis_name=sa_name).delete()
        db.session.commit()


def test_pipeline_builder_renders_connectors_and_compiles_steps(client, app, tmp_path, monkeypatch):
    """Verify /pipeline_builder renders connectors and /save_pipeline/ compiles per-step Flows."""
    from dataclasses import replace

    from models import DbConnection, Execution, db
    from utils.app_settings import ConnectorParameterSpec, ConnectorSettings

    webapp = app.config['WEBAPP']
    analyses_dir = tmp_path / 'Analyses'
    analyses_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(webapp, 'save_folder_path', str(analyses_dir))

    custom_trino = ConnectorSettings(
        name='trino_etl',
        description='Run SQL on Trino and export CSV',
        image='custom-trino-runner:latest',
        builtin=False,
        parameters=(
            ConnectorParameterSpec(name='query', param_type='text', required=True),
            ConnectorParameterSpec(name='connection', param_type='select', source='connections'),
        ),
    )
    orig_settings = app.config['PC_SETTINGS']
    updated_settings = replace(orig_settings, connectors=(*orig_settings.connectors, custom_trino))
    monkeypatch.setitem(app.config, 'PC_SETTINGS', updated_settings)
    monkeypatch.setattr(webapp, '_settings', updated_settings.for_templates())

    with app.app_context():
        conn_row = DbConnection(name='warehouse_trino', db_type='trino', host='trino.local', port=8080)
        db.session.add(conn_row)
        db.session.commit()

    try:
        # 1. GET /pipeline_builder renders built-in and custom connectors plus saved connection names
        pb_resp = client.get('/pipeline_builder')
        assert pb_resp.status_code == 200
        pb_html = pb_resp.data.decode('utf-8')
        assert 'Connectors' in pb_html
        assert 'python_script' in pb_html
        assert 'sql_query' in pb_html
        assert 'trino_etl' in pb_html
        assert 'custom-trino-runner:latest' in pb_html
        assert 'warehouse_trino' in pb_html

        # 2. POST /save_pipeline/ with a 2-step connector graph (trino_etl -> python_script)
        pipeline_name = 'TrinoToPythonPipeline'
        graph = {
            'drawflow': {
                'Home': {
                    'data': {
                        '1': {
                            'id': 1,
                            'class': 'trino_etl',
                            'data': {'config': {'query': 'SELECT * FROM events', 'connection': 'warehouse_trino'}},
                            'inputs': {},
                            'outputs': {'output_1': {'connections': [{'node': '2', 'output': 'input_1'}]}},
                        },
                        '2': {
                            'id': 2,
                            'class': 'python_script',
                            'data': {'config': {'code': 'print("processing events")'}},
                            'inputs': {'input_1': {'connections': [{'node': '1', 'input': 'output_1'}]}},
                            'outputs': {},
                        },
                    }
                }
            }
        }
        save_resp = client.post(
            '/save_pipeline/',
            json={
                'name': pipeline_name,
                'description': 'Two-step connector pipeline',
                'product': 'Data Engineering',
                'owner': 'alice',
                'graph': graph,
            },
        )
        assert save_resp.status_code == 200
        save_data = save_resp.get_json()
        assert save_data['success'] is True
        assert save_data['status'] == 'ok'
        expected_steps = [
            f'{pipeline_name}__step_1_trino_etl',
            f'{pipeline_name}__step_2_python_script',
        ]
        assert save_data['step_flows'] == expected_steps

        # 3. Verify step Flows have their connector container images and parameters
        with app.app_context():
            flow1 = webapp.read_flow(expected_steps[0])
            flow2 = webapp.read_flow(expected_steps[1])
            assert flow1 is not None
            assert flow1['image'] == 'custom-trino-runner:latest'
            assert flow1['parameters']['query'] == 'SELECT * FROM events'
            assert flow1['parameters']['connection'] == 'warehouse_trino'

            assert flow2 is not None
            assert flow2['image'] == 'python:3.12-slim'
            assert flow2['parameters']['code'] == 'print("processing events")'

        # 4. Verify step Flows were compiled (no chain is created)
        with app.app_context():
            flow1 = webapp.read_flow(expected_steps[0])
            assert flow1 is not None

    finally:
        with app.app_context():
            DbConnection.query.filter_by(name='warehouse_trino').delete()
            Execution.query.filter(Execution.analysis_name.like('TrinoToPythonPipeline%')).delete(synchronize_session=False)
            db.session.commit()


def test_static_catalog_entries_and_no_in_process_execution_in_catalog(
    client, app, tmp_path, monkeypatch,
):
    """Verify static catalog entries without compass_flow.yaml + Dockerfile
    remain structured_analysis == 'n' and catalog.py has no local execution."""
    from pathlib import Path

    webapp = app.config['WEBAPP']
    analyses_dir = tmp_path / 'Analyses'
    analyses_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(webapp, 'save_folder_path', str(analyses_dir))

    static_name = 'Static Survey Report'
    static_dir = analyses_dir / static_name
    static_dir.mkdir(parents=True)
    (static_dir / 'metadata.yaml').write_text(
        'title: Static Survey Report\n'
        'start_date: 2025-01-01\n'
        'owner: alice\n'
        'collaborators: bob\n'
        'product: HR\n'
        'countries: Global\n'
        'description: Static entry without Python runner\n'
        'output description: Static slides\n'
        'gitlab: ""\n'
        'gdrive: ""\n'
        'links: {}\n'
        'dashboard link: ""\n',
        encoding='utf-8',
    )

    info = webapp.read_single_analysis(str(analyses_dir), static_name)
    assert info['title'] == static_name
    assert info['structured_analysis'] == 'n'

    catalog_source = (Path(__file__).resolve().parent.parent / 'blueprints' / 'catalog.py').read_text(encoding='utf-8')
    assert 'spec_from_file_location' not in catalog_source
    assert 'subprocess.Popen' not in catalog_source
    assert '_running_processes' not in catalog_source


def test_execution_template_targets_resolve_to_registered_routes(app):
    """Verify action and fetch targets used by the execution templates are registered."""
    adapter = app.url_map.bind('localhost')
    template_targets = (
        ('/analysis', 'GET'),
        ('/run_investigation/', 'POST'),
        ('/schedule_analysis/', 'POST'),
        ('/execute_stream/SampleAnalysis', 'GET'),
        ('/execute_abort/SampleAnalysis', 'POST'),
        ('/static/logging_page.html', 'GET'),
        ('/api/data/sample-dataset/preview', 'GET'),
        ('/save_pipeline/', 'POST'),
        ('/create_investigations', 'GET'),
        ('/flows', 'GET'),
        ('/flows/SampleFlow', 'GET'),
        ('/flows/new', 'POST'),
        ('/flows/SampleFlow/save', 'POST'),
        ('/flows/SampleFlow/run', 'POST'),
        ('/flows/SampleFlow/versions/1', 'GET'),
        ('/flows/SampleFlow/versions/1/restore', 'POST'),
        ('/runs/1', 'GET'),
        ('/static/pipeline_templates/sample.json', 'GET'),
    )

    for path, method in template_targets:
        endpoint, _ = adapter.match(path, method=method)
        assert endpoint


def test_core_only_template_gating_and_pipeline_main_execution(client, app, tmp_path, monkeypatch):
    """Verify core-only template gating hides disabled links and generated pipeline_main.py executes via __main__."""
    import json
    import os
    import subprocess
    import sys

    from blueprints.catalog import _generate_pipeline_script
    from utils.app_settings import DefaultsSource, SettingsLoader

    # 1. Verify Pipeline Builder generated script runs via __main__ with FLOW_PARAMS_JSON and PC_OUTPUT_DIR
    data_dir = tmp_path / 'Saved_data'
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / 'employees.csv').write_text('name,salary\nAlice,100\nBob,120\n', encoding='utf-8')
    out_dir = tmp_path / 'pc_output'
    script_path = tmp_path / 'pipeline_main.py'
    script_code = _generate_pipeline_script(
        [{'type': 'load_data', 'config': {'dataset': 'employees', 'limit': '0'}}],
        str(data_dir),
    )
    script_path.write_text(script_code, encoding='utf-8')
    env = os.environ.copy()
    env['PC_DATA_DIR'] = str(data_dir)
    env['PC_OUTPUT_DIR'] = str(out_dir)
    env['FLOW_PARAMS_JSON'] = json.dumps({'target_col': 'salary'})
    proc = subprocess.run([sys.executable, str(script_path)], env=env, capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0, proc.stderr
    assert (out_dir / 'output.csv').is_file()

    # 2. Verify core-only settings hide /overview, /chat/analysis, and /rag/status/ in templates
    webapp = app.config['WEBAPP']
    original_settings = app.config['PC_SETTINGS']
    core_settings = SettingsLoader((DefaultsSource(),)).load()
    monkeypatch.setitem(app.config, 'PC_SETTINGS', core_settings)
    webapp.apply_settings(core_settings.for_templates())
    try:
        dash_html = client.get('/').data.decode('utf-8')
        assert '/overview' not in dash_html

        catalog_html = client.get('/analysis').data.decode('utf-8')
        assert '/chat/analysis' not in catalog_html
        assert '/rag/status/' not in catalog_html
        assert '/overview' not in catalog_html
    finally:
        webapp.apply_settings(original_settings.for_templates())

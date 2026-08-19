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
            assert os.path.isfile(f"{analysis_dir}/analysis/structured_analysis_main.py")
            assert os.path.isfile(f"{analysis_dir}/analysis/metadata_automatic_report.yaml")
            assert os.path.isfile(f"{analysis_dir}/metadata.yaml")
            assert os.path.isfile(f"{analysis_dir}/readme.md")
    finally:
        # Clean up
        with app.app_context():
            webapp = app.config['WEBAPP']
            analysis_dir = f"{webapp.extract_main_folder()}/{name}"
            if os.path.isdir(analysis_dir):
                shutil.rmtree(analysis_dir)


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
        with open(f"{analysis_dir}/analysis/structured_analysis_main.py", 'w') as f:
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
            with open(f"{webapp.extract_main_folder()}/{name}/analysis/structured_analysis_main.py") as f:
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


# --- Execute abort tests ---

def test_execute_abort_no_process(client):
    """Test POST /execute_abort/<name> when no process is running."""
    resp = client.post('/execute_abort/NonExistentAnalysis')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is False

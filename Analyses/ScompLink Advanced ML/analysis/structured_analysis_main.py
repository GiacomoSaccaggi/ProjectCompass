"""ScompLink Advanced ML — demonstrates scomp-link v2.x features.

Features used:
- Pipeline DSL (>> operator): CleanStep >> SelectStep >> ModelStep >> TrainStep
- FeatureEngineer (Polars backend): interactions + log transforms
- SHAP Explainability: top feature importance
- Drift Detection: PSI-based distribution drift (train vs test split)
- Rich HTML Report: KPI cards, summary stats, comparison table, dark mode
"""
import os
import shutil

import pandas as pd
from scomp_link import CleanStep, DriftDetector, FeatureEngineer, ModelStep, SelectStep, ShapExplainer, TrainStep


def detect_task_type(df, target_col):
    """Auto-detect regression vs classification based on target column."""
    target = df[target_col]
    n_unique = target.nunique()
    if target.dtype == 'object' or n_unique <= 10:
        return 'classification'
    return 'regression'


def run(inputs, output_path):
    """Run advanced scomp-link pipeline with v2.x features."""
    data_path = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'Saved_data', 'wine_quality.csv')
    df = pd.read_csv(data_path)

    target_col = inputs.get('target_col', 'quality')
    task_type = inputs.get('task_type', 'auto')
    test_size = float(inputs.get('test_size', '0.2'))
    use_fe = inputs.get('feature_engineering', 'true') == 'true'
    use_explain = inputs.get('explainability', 'true') == 'true'

    if task_type == 'auto':
        task_type = detect_task_type(df, target_col)

    out_dir = os.path.dirname(output_path)
    os.makedirs(out_dir, exist_ok=True)

    # --- Feature Engineering ---
    if use_fe:
        fe = FeatureEngineer(interactions=True, log_transform=True)
        X = fe.fit_transform(df.drop(columns=[target_col]), df[target_col])
        X[target_col] = df[target_col].values
        df = X

    # --- Train with DSL ---
    objective = "numerical_prediction" if task_type == "regression" else "categorical_known"
    results = (
        CleanStep(df)
        >> SelectStep(target_col)
        >> ModelStep(objective)
        >> TrainStep(task_type, test_size=test_size)
    ).run()

    # --- Explainability (SHAP) ---
    if use_explain and results.get('model'):
        try:
            explainer = ShapExplainer(results['model'], df.drop(columns=[target_col]).head(100))
            explainer.run(num_features=10)
        except Exception:
            pass  # SHAP may not support all model types

    # --- Drift Detection (simulated: split data as reference vs current) ---
    n = len(df)
    split_idx = int(n * 0.7)
    ref_df = df.iloc[:split_idx].drop(columns=[target_col])
    cur_df = df.iloc[split_idx:].drop(columns=[target_col])
    try:
        drift = DriftDetector(ref_df, cur_df, threshold=0.1)
        drift_results = drift.run()
        drift.save_html(os.path.join(out_dir, "drift_report.html"))
    except Exception:
        drift_results = {}

    # --- Rich HTML Report ---
    from scomp_link.utils.report_html import ScompLinkHTMLReport

    class AdvancedReport(ScompLinkHTMLReport, title="ScompLink Advanced ML Report"):
        pass

    report = AdvancedReport()
    report.add_dark_mode_toggle()
    report.open_section("Model Performance")

    # KPI Cards
    metrics = results.get('metrics', {})
    if metrics:
        kpi = {k: {"value": f"{v:.4f}" if isinstance(v, float) else str(v), "status": "good"}
               for k, v in metrics.items()}
        report.add_kpi_cards(kpi, cols=min(len(kpi), 4))

    # Model info
    report.add_text(f"<b>Model:</b> {results.get('model_type', 'N/A')} | "
                    f"<b>Task:</b> {task_type} | <b>Test size:</b> {test_size}")

    report.close_section()
    report.open_section("Data Overview")
    report.add_summary_stats(df, "Dataset Summary")
    report.close_section()

    # Drift section
    if drift_results:
        report.open_section("Drift Analysis")
        drifted = drift_results.get('drifted_features', [])
        report.add_text(f"Features with significant drift (PSI > 0.1): <b>{len(drifted)}</b> / {len(ref_df.columns)}")
        if drifted:
            drift_df = pd.DataFrame([{'Feature': f, 'PSI': drift_results.get('psi', {}).get(f, 0)} for f in drifted])
            report.add_dataframe(drift_df, "Drifted Features")
        report.close_section()

    # Copy model report if available
    model_report = results.get('report_path', '')
    if model_report and os.path.exists(model_report):
        shutil.copy(model_report, os.path.join(out_dir, 'model_validation_report.html'))

    # Save our custom report
    report.save(os.path.join(out_dir, "advanced_report.html"))

    # --- Save CSV output ---
    metrics_df = pd.DataFrame([metrics])
    metrics_df.insert(0, 'model_type', results.get('model_type', ''))
    metrics_df.insert(1, 'task_type', task_type)
    metrics_df.insert(2, 'feature_engineering', use_fe)
    metrics_df.insert(3, 'n_features', len(df.columns) - 1)
    metrics_df.to_csv(output_path, index=False)

    return results


if __name__ == '__main__':
    result = run(
        inputs={'target_col': 'quality', 'task_type': 'auto', 'test_size': '0.2',
                'feature_engineering': 'true', 'explainability': 'true'},
        output_path='output/output.csv'
    )
    print(f"Model: {result.get('model_type')}")
    print(f"Metrics: {result.get('metrics')}")

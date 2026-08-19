"""ScompLink Wine Quality Prediction — structured analysis using DSL."""
import os
import shutil

import pandas as pd
from scomp_link import CleanStep, ModelStep, SelectStep, TrainStep


def detect_task_type(df, target_col):
    """Auto-detect regression vs classification based on target column."""
    target = df[target_col]
    n_unique = target.nunique()
    if target.dtype == 'object' or n_unique <= 10:
        return 'classification'
    return 'regression'


def run(inputs, output_path):
    """Run scomp-link DSL pipeline on wine quality data."""
    data_path = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'Saved_data', 'wine_quality.csv')
    df = pd.read_csv(data_path)

    task_type = inputs.get('task_type', 'auto')
    test_size = float(inputs.get('test_size', 0.2))
    target_col = inputs.get('target_column', 'quality')

    if task_type == 'auto':
        task_type = detect_task_type(df, target_col)

    objective = "numerical_prediction" if task_type == "regression" else "categorical_known"

    # DSL pipeline: CleanStep >> SelectStep >> ModelStep >> TrainStep
    results = (
        CleanStep(df)
        >> SelectStep(target_col)
        >> ModelStep(objective)
        >> TrainStep(task_type, test_size=test_size)
    ).run()

    # Save outputs
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    output_dir = os.path.dirname(output_path)

    metrics_df = pd.DataFrame([results.get('metrics', {})])
    metrics_df.insert(0, 'model_type', results.get('model_type', ''))
    metrics_df.insert(1, 'task_type', task_type)
    metrics_df.to_csv(output_path, index=False)

    # Copy HTML report if generated
    report_path = results.get('report_path', 'ScompLink_Validation_Report.html')
    if report_path and os.path.exists(report_path):
        shutil.copy(report_path, os.path.join(output_dir, 'ScompLink_Validation_Report.html'))

    return results


if __name__ == '__main__':
    result = run(
        inputs={'task_type': 'auto', 'test_size': '0.2', 'target_column': 'quality'},
        output_path='output/output.csv'
    )
    print(f"Model: {result['model_type']}")
    print(f"Metrics: {result['metrics']}")

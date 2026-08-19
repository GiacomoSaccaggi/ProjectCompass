"""Auto-generated pipeline by ProjectCompass Pipeline Builder."""
import os

import pandas as pd


def run(inputs, output_path):
    data_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "Saved_data")
    df = None
    results = {}

    # Step 1: load_data
    df = pd.read_csv(os.path.join(data_dir, "employees.csv"))

    # Step 2: report
    _report_path = results.get("report_path", "")
    if _report_path and os.path.exists(_report_path):
        import shutil
        shutil.copy(_report_path, os.path.join(os.path.dirname(output_path), "report.html"))

    # Save output
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    if results.get("metrics"):
        pd.DataFrame([results["metrics"]]).to_csv(output_path, index=False)
    elif df is not None:
        df.head(1000).to_csv(output_path, index=False)
    return results

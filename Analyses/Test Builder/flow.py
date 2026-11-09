"""Auto-generated pipeline by ProjectCompass Pipeline Builder."""
import json
import os
import shutil

import pandas as pd


def _resolve_data_dir() -> str:
    env_dir = os.environ.get("PC_DATA_DIR", "").strip()
    if env_dir and os.path.isdir(env_dir):
        return env_dir
    local_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Saved_data")
    if os.path.isdir(local_dir):
        return local_dir
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "Saved_data")


def run(inputs, output_path):
    data_dir = _resolve_data_dir()
    df = None
    results = {}

    # Step 1: load_data
    df = pd.read_csv(os.path.join(data_dir, "employees.csv"))

    # Step 2: report
    _report_path = results.get("report_path", "")
    if _report_path and os.path.exists(_report_path):
        shutil.copy(_report_path, os.path.join(os.path.dirname(output_path) or ".", "report.html"))

    # Save output
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    if results.get("metrics"):
        pd.DataFrame([results["metrics"]]).to_csv(output_path, index=False)
    elif df is not None:
        df.head(1000).to_csv(output_path, index=False)
    return results


if __name__ == "__main__":
    default_inputs = {"target_col": ""}
    raw_params = os.environ.get("FLOW_PARAMS_JSON", "").strip()
    if raw_params:
        try:
            parsed = json.loads(raw_params)
            if isinstance(parsed, dict):
                default_inputs.update(parsed)
        except ValueError:
            pass
    out_dir = os.environ.get("PC_OUTPUT_DIR", "output").strip() or "output"
    run(
        inputs=default_inputs,
        output_path=os.path.join(out_dir, "output.csv"),
    )

"""Sales Performance Report — executable flow."""
import json
import os

import pandas as pd


def _resolve_data_dir() -> str:
    env_dir = os.environ.get('PC_DATA_DIR', '').strip()
    if env_dir and os.path.isdir(env_dir):
        return env_dir
    local_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'Saved_data')
    if os.path.isdir(local_dir):
        return local_dir
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'Saved_data')


def run(inputs, output_path):
    """Generate sales summary filtered by date range and region."""
    data_path = os.path.join(_resolve_data_dir(), 'sales_data.csv')
    df = pd.read_csv(data_path, parse_dates=['date'])

    # Filter by date range
    start = pd.to_datetime(inputs.get('start_date', '2024-01-15'))
    end = pd.to_datetime(inputs.get('end_date', '2024-01-21'))
    df = df[(df['date'] >= start) & (df['date'] <= end)]

    # Filter by region
    region = inputs.get('region', 'all')
    if region and region.lower() != 'all':
        df = df[df['region'].str.lower() == region.lower()]

    # Aggregate
    summary = df.groupby(['product', 'category', 'region']).agg(
        total_quantity=('quantity', 'sum'),
        total_revenue=('revenue', 'sum'),
        total_cost=('cost', 'sum'),
    ).reset_index()
    summary['profit'] = summary['total_revenue'] - summary['total_cost']
    summary['margin_pct'] = (summary['profit'] / summary['total_revenue'] * 100).round(1)

    # Sort by revenue
    summary = summary.sort_values('total_revenue', ascending=False)

    # Save output
    os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
    summary.to_csv(output_path, index=False)
    return summary


if __name__ == '__main__':
    default_inputs = {'start_date': '2024-01-15', 'end_date': '2024-01-21', 'region': 'all'}
    raw_params = os.environ.get('FLOW_PARAMS_JSON', '').strip()
    if raw_params:
        try:
            parsed = json.loads(raw_params)
            if isinstance(parsed, dict):
                default_inputs.update(parsed)
        except ValueError:
            pass
    out_dir = os.environ.get('PC_OUTPUT_DIR', 'output').strip() or 'output'
    result = run(
        inputs=default_inputs,
        output_path=os.path.join(out_dir, 'sales_summary.csv'),
    )
    print(result.to_string())

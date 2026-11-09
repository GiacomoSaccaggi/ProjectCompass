"""Upload output files from a Job Pod to the MinIO/S3 artifact store.

Injected into every Dockerfile-mode Job. Called automatically at the end
of the entrypoint or manually by the user script.

Environment variables (set by ProjectCompass in the Job manifest):
    PC_S3_ENDPOINT   — e.g. http://minio:9000
    PC_S3_ACCESS_KEY  — MinIO access key
    PC_S3_SECRET_KEY  — MinIO secret key
    PC_S3_BUCKET      — e.g. pc-artifacts
    FLOW_RUN_ID       — unique run identifier (used as S3 prefix)
    PC_OUTPUT_DIR     — directory to scan for output files (default: /tmp/pc_output)
"""
from __future__ import annotations

import os
import sys


def upload_outputs() -> int:
    endpoint = os.environ.get("PC_S3_ENDPOINT", "").strip()
    access_key = os.environ.get("PC_S3_ACCESS_KEY", "").strip()
    secret_key = os.environ.get("PC_S3_SECRET_KEY", "").strip()
    bucket = os.environ.get("PC_S3_BUCKET", "pc-artifacts").strip()
    run_id = os.environ.get("FLOW_RUN_ID", "0").strip()
    output_dir = os.environ.get("PC_OUTPUT_DIR", "/tmp/pc_output").strip()

    if not endpoint or not access_key:
        print("[pc_s3_upload] S3 not configured — skipping artifact upload.")
        return 0

    try:
        import boto3
        from botocore.config import Config as BotoConfig
    except ImportError:
        print("[pc_s3_upload] boto3 not installed — skipping artifact upload.")
        return 0

    s3 = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        config=BotoConfig(signature_version="s3v4"),
        region_name="us-east-1",
    )

    uploaded = 0
    for root, _dirs, files in os.walk(output_dir):
        for fname in sorted(files):
            if fname.startswith(".") or ".ini" in fname:
                continue
            local_path = os.path.join(root, fname)
            rel_path = os.path.relpath(local_path, output_dir)
            s3_key = f"{run_id}/{rel_path}"
            try:
                s3.upload_file(local_path, bucket, s3_key)
                print(f"[pc_s3_upload] Uploaded {rel_path} → s3://{bucket}/{s3_key}")
                uploaded += 1
            except Exception as exc:
                print(f"[pc_s3_upload] Failed to upload {rel_path}: {exc}", file=sys.stderr)

    print(f"[pc_s3_upload] {uploaded} file(s) uploaded to s3://{bucket}/{run_id}/")
    return uploaded


if __name__ == "__main__":
    upload_outputs()

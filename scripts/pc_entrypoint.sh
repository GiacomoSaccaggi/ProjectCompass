#!/bin/sh
# ProjectCompass Job entrypoint wrapper.
# Runs the main script, then uploads outputs to S3 if configured.
set -e

# Run the user's command
"$@"

# Upload outputs to S3
if [ -n "$PC_S3_ENDPOINT" ] && python -c "import boto3" 2>/dev/null; then
    python -c "
import os, sys, boto3
from botocore.config import Config
endpoint = os.environ.get('PC_S3_ENDPOINT','')
s3 = boto3.client('s3', endpoint_url=endpoint,
    aws_access_key_id=os.environ.get('PC_S3_ACCESS_KEY',''),
    aws_secret_access_key=os.environ.get('PC_S3_SECRET_KEY',''),
    config=Config(signature_version='s3v4'), region_name='us-east-1')
bucket = os.environ.get('PC_S3_BUCKET','pc-artifacts')
run_id = os.environ.get('FLOW_RUN_ID','0')
out_dir = os.environ.get('PC_OUTPUT_DIR','/tmp/pc_output')
n = 0
for root, dirs, files in os.walk(out_dir):
    for f in sorted(files):
        if f.startswith('.') or '.ini' in f: continue
        local = os.path.join(root, f)
        key = f'{run_id}/{os.path.relpath(local, out_dir)}'
        s3.upload_file(local, bucket, key)
        print(f'[pc_s3] Uploaded {f} -> s3://{bucket}/{key}')
        n += 1
print(f'[pc_s3] {n} file(s) uploaded.')
"
fi

FROM python:3.12-slim

WORKDIR /app
COPY . .

RUN pip install --no-cache-dir pandas boto3

# pc_entrypoint.sh runs the analysis then uploads /tmp/pc_output to S3
COPY scripts/pc_entrypoint.sh /usr/local/bin/pc_entrypoint.sh
RUN chmod +x /usr/local/bin/pc_entrypoint.sh

ENTRYPOINT ["pc_entrypoint.sh", "python", "flow.py"]

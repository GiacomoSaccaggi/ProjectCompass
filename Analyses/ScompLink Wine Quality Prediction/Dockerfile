FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . .

RUN pip install --no-cache-dir scomp-link pandas boto3

# pc_entrypoint.sh runs the analysis then uploads /tmp/pc_output to S3
COPY scripts/pc_entrypoint.sh /usr/local/bin/pc_entrypoint.sh
RUN chmod +x /usr/local/bin/pc_entrypoint.sh

ENTRYPOINT ["pc_entrypoint.sh", "python", "flow.py"]

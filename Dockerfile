FROM python:3.12-slim

EXPOSE 8080
ENV FLASK_ENV=production
ENV FLASK_DEBUG=False
ENV PORT=8080
ENV DATA_DIR=/app/data

WORKDIR /app
RUN mkdir -p /app/data log Analyses Saved_data Saved_queries templates static utils blueprints tmp

# Install system dependencies + Docker CLI (for building flow images)
RUN apt-get update && apt-get install -y --no-install-recommends git curl \
    && curl -fsSL https://download.docker.com/linux/static/stable/$(uname -m | sed 's/aarch64/aarch64/;s/x86_64/x86_64/')/docker-27.5.1.tgz \
       | tar xz --strip-components=1 -C /usr/local/bin docker/docker \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY app.py basefun.py config.py logging_config.py models.py run.py ./
COPY pyproject.toml ./
COPY templates/ templates/
COPY static/ static/
COPY utils/ utils/
COPY blueprints/ blueprints/
COPY Saved_data/ Saved_data/
COPY Analyses/ Analyses/
COPY scripts/ scripts/

COPY docker_startup.sh /usr/local/bin/startup.sh
RUN chmod +x /usr/local/bin/startup.sh /app/scripts/pc_entrypoint.sh

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

ENTRYPOINT ["startup.sh"]

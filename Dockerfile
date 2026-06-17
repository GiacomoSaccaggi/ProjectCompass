FROM python:3.12-slim

EXPOSE 8080
ENV FLASK_ENV=production
ENV FLASK_DEBUG=False
ENV PORT=8080

WORKDIR /app
RUN mkdir -p log Analyses Saved_data Saved_queries templates static utils blueprints tmp

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends git curl && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY app.py basefun.py config.py logging_config.py run.py ./
COPY pyproject.toml ./
COPY templates/ templates/
COPY static/ static/
COPY utils/ utils/
COPY blueprints/ blueprints/
COPY Saved_data/ Saved_data/
COPY Analyses/ Analyses/

COPY docker_startup.sh /usr/local/bin/startup.sh
RUN chmod +x /usr/local/bin/startup.sh

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

ENTRYPOINT ["startup.sh"]

FROM python:3.12-slim

EXPOSE 8080
ENV FLASK_ENV=production
ENV FLASK_DEBUG=False
ENV GUNICORN_ENDPOINT=0.0.0.0:8080

WORKDIR /app
RUN mkdir -p log Analyses Saved_data Saved_queries templates static utils

# Install system dependencies
RUN apt-get update && apt-get install -y git build-essential && rm -rf /var/lib/apt/lists/*

# Upgrade pip
RUN pip install --upgrade pip

# Install Python dependencies
COPY requirements.txt .
RUN pip install -r requirements.txt --no-cache-dir

# Copy application files
COPY app.py .
COPY basefun.py .
COPY config.py .
COPY __init__.py .
COPY run.py .
COPY templates/ templates/
COPY static/ static/
COPY utils/ utils/

# Create startup script
COPY docker_startup.sh /usr/local/bin/startup.sh
RUN chmod +x /usr/local/bin/startup.sh

ENTRYPOINT ["startup.sh"]
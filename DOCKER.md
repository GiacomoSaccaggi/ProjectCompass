# Docker Documentation for ProjectCompass

## Overview

ProjectCompass is containerized using Docker with multi-service architecture including:
- **ProjectCompass Application**: Flask web application with Gunicorn
- **Ollama**: Local LLM service for AI capabilities

## Architecture

```
┌─────────────────┐    ┌─────────────────┐
│  ProjectCompass │    │     Ollama      │
│   (Port 8080)   │◄──►│  (Port 11434)   │
│                 │    │                 │
│  Flask + GUI    │    │  LLM Models     │
└─────────────────┘    └─────────────────┘
```

## Quick Start

### Prerequisites
- Docker Engine 20.10+
- Docker Compose 2.0+
- 8GB+ RAM (for Ollama models)
- 10GB+ free disk space

### Launch Services
```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

## Service Configuration

### ProjectCompass Service
- **Image**: Built from local Dockerfile
- **Port**: 8080 (external) → 5000 (internal)
- **Runtime**: Python 3.10 + Gunicorn
- **Workers**: 4 Gunicorn workers
- **Volumes**:
  - `./Analyses` → `/app/Analyses` (analysis storage)
  - `./Saved_data` → `/app/Saved_data` (data files)
  - `./Saved_queries` → `/app/Saved_queries` (query cache)
  - `./logs` → `/app/log` (application logs)

### Ollama Service
- **Image**: `ollama/ollama:latest`
- **Port**: 11434 (LLM API)
- **Models**: 
  - `llama3` (7B parameters)
  - `nomic-embed-text` (embedding model)
- **Volume**: `ollama_data` (persistent model storage)

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `FLASK_ENV` | `production` | Flask environment |
| `FLASK_DEBUG` | `False` | Debug mode |
| `PORT` | `5000` | Internal Flask port |
| `USE_GITLAB_REPO` | `False` | GitLab integration |
| `USERNAME` | `docker_user` | Default username |
| `OLLAMA_HOST` | `ollama:11434` | Ollama service endpoint |

## Build Process

### Dockerfile Stages
1. **Base Image**: Python 3.10.5-buster
2. **System Dependencies**: OpenCV, pip upgrade
3. **Python Dependencies**: From requirements.txt
4. **Application Code**: Copy source files
5. **Runtime**: Gunicorn with custom startup script

### Build Commands
```bash
# Manual build
docker build -t projectcompass:latest .

# Build with compose
docker-compose build
```

## Data Persistence

### Volumes
- **Application Data**: Host directories mounted as volumes
- **Ollama Models**: Named volume `ollama_data`
- **Logs**: Host `./logs` directory

### Backup Strategy
```bash
# Backup application data
tar -czf backup_$(date +%Y%m%d).tar.gz Analyses/ Saved_data/ Saved_queries/

# Backup Ollama models
docker run --rm -v ollama_data:/data -v $(pwd):/backup alpine tar czf /backup/ollama_models.tar.gz -C /data .
```

## Monitoring & Debugging

### Health Checks
```bash
# Check service status
docker-compose ps

# Test ProjectCompass
curl http://localhost:8080

# Test Ollama
curl http://localhost:11434/api/tags
```

### Log Access
```bash
# Application logs
docker-compose logs projectcompass

# Ollama logs
docker-compose logs ollama

# Follow logs
docker-compose logs -f
```

### Container Access
```bash
# Access ProjectCompass container
docker exec -it projectcompass_app bash

# Access Ollama container
docker exec -it ollama bash
```

## Troubleshooting

### Common Issues

#### Port Conflicts
```bash
# Check port usage
netstat -tulpn | grep :8080
netstat -tulpn | grep :11434

# Use different ports
docker-compose -f docker-compose.yml up -d
```

#### Memory Issues
```bash
# Check container memory usage
docker stats

# Increase Docker memory limit (Docker Desktop)
# Settings → Resources → Memory → 8GB+
```

#### Model Download Failures
```bash
# Manually pull models
docker exec ollama ollama pull llama3
docker exec ollama ollama pull nomic-embed-text

# Check available models
docker exec ollama ollama list
```

#### Permission Issues
```bash
# Fix volume permissions
sudo chown -R $USER:$USER Analyses/ Saved_data/ Saved_queries/ logs/
```

## Production Deployment

### Security Considerations
- Change default secret keys
- Configure CORS origins
- Use reverse proxy (nginx)
- Enable HTTPS
- Implement authentication

### Performance Tuning
```yaml
# docker-compose.override.yml
services:
  projectcompass:
    deploy:
      resources:
        limits:
          memory: 2G
        reservations:
          memory: 1G
  
  ollama:
    deploy:
      resources:
        limits:
          memory: 8G
        reservations:
          memory: 4G
```

### Scaling
```bash
# Scale ProjectCompass instances
docker-compose up -d --scale projectcompass=3

# Load balancer configuration required
```

## Development

### Development Override
```yaml
# docker-compose.dev.yml
services:
  projectcompass:
    environment:
      - FLASK_ENV=development
      - FLASK_DEBUG=True
    volumes:
      - .:/app
    command: python app.py
```

### Hot Reload
```bash
# Development mode with hot reload
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up
```

## Maintenance

### Updates
```bash
# Update base images
docker-compose pull

# Rebuild with latest code
docker-compose build --no-cache

# Update and restart
docker-compose up -d --build
```

### Cleanup
```bash
# Remove stopped containers
docker container prune

# Remove unused images
docker image prune

# Remove unused volumes (WARNING: data loss)
docker volume prune
```
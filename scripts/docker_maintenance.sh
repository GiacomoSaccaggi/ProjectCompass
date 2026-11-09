#!/bin/bash

# Docker Maintenance Script for ProjectCompass

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

echo "=== ProjectCompass Docker Maintenance ==="

# Function to show usage
show_usage() {
    echo "Usage: $0 [COMMAND]"
    echo ""
    echo "Commands:"
    echo "  backup     - Backup application data and Ollama models"
    echo "  restore    - Restore from backup"
    echo "  update     - Update images and rebuild"
    echo "  cleanup    - Clean unused Docker resources"
    echo "  logs       - Show service logs"
    echo "  status     - Show service status"
    echo "  restart    - Restart all services"
    echo ""
}

# Backup function
backup_data() {
    echo "Creating backup..."
    BACKUP_DIR="backups/$(date +%Y%m%d_%H%M%S)"
    mkdir -p "$BACKUP_DIR"
    
    # Backup application data
    if [ -d "Analyses" ]; then
        tar -czf "$BACKUP_DIR/analyses.tar.gz" Analyses/
        echo "✓ Analyses backed up"
    fi
    
    if [ -d "Saved_data" ]; then
        tar -czf "$BACKUP_DIR/saved_data.tar.gz" Saved_data/
        echo "✓ Saved_data backed up"
    fi
    
    if [ -d "Saved_queries" ]; then
        tar -czf "$BACKUP_DIR/saved_queries.tar.gz" Saved_queries/
        echo "✓ Saved_queries backed up"
    fi
    
    # Backup Ollama models
    if docker volume ls | grep -q ollama_data; then
        docker run --rm -v ollama_data:/data -v "$(pwd)/$BACKUP_DIR":/backup alpine tar czf /backup/ollama_models.tar.gz -C /data .
        echo "✓ Ollama models backed up"
    fi
    
    echo "Backup completed: $BACKUP_DIR"
}

# Update function
update_services() {
    echo "Updating services..."
    docker-compose pull
    docker-compose build --no-cache
    docker-compose up -d
    echo "✓ Services updated"
}

# Cleanup function
cleanup_docker() {
    echo "Cleaning up Docker resources..."
    docker container prune -f
    docker image prune -f
    docker network prune -f
    echo "✓ Cleanup completed"
}

# Main command handling
case "${1:-}" in
    backup)
        backup_data
        ;;
    update)
        update_services
        ;;
    cleanup)
        cleanup_docker
        ;;
    logs)
        docker-compose logs -f
        ;;
    status)
        docker-compose ps
        ;;
    restart)
        docker-compose restart
        ;;
    *)
        show_usage
        exit 1
        ;;
esac
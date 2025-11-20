#!/bin/bash

# ProjectCompass Docker Build and Run Script

echo "Enter Docker image tag (default: latest):"
read -r TAG
TAG=${TAG:-latest}

CONTAINER_NAME="projectcompass"
IMAGE_NAME="projectcompass:${TAG}"
EXTERNAL_PORT="8080"
INTERNAL_PORT="5000"

echo "Building Docker image: ${IMAGE_NAME}"
docker build --pull --rm -t ${IMAGE_NAME} .

echo "Stopping and removing existing container if it exists..."
docker stop ${CONTAINER_NAME} 2>/dev/null || true
docker rm ${CONTAINER_NAME} 2>/dev/null || true

# Start Ollama first
echo "Starting Ollama container..."
docker stop ollama 2>/dev/null || true
docker rm ollama 2>/dev/null || true
docker run -d -v ollama_data:/root/.ollama -p 11434:11434 --name ollama ollama/ollama

# Wait for Ollama to be ready
echo "Waiting for Ollama to start..."
sleep 10

# Pull LLM models
echo "Downloading Llama3 model..."
docker exec ollama ollama pull llama3

echo "Downloading nomic-embed-text model..."
docker exec ollama ollama pull nomic-embed-text

# Start ProjectCompass
echo "Running ProjectCompass container..."
docker run -d \
    -p ${EXTERNAL_PORT}:${INTERNAL_PORT} \
    --name ${CONTAINER_NAME} \
    --link ollama:ollama \
    -e OLLAMA_HOST=ollama:11434 \
    -v "$(pwd)/Analyses:/app/Analyses" \
    -v "$(pwd)/Saved_data:/app/Saved_data" \
    -v "$(pwd)/Saved_queries:/app/Saved_queries" \
    -v "$(pwd)/logs:/app/log" \
    ${IMAGE_NAME}

echo "Container started successfully!"
echo "Access the application at: http://localhost:${EXTERNAL_PORT}"
echo ""
echo "Useful commands:"
echo "  View ProjectCompass logs: docker logs ${CONTAINER_NAME}"
echo "  View Ollama logs: docker logs ollama"
echo "  Stop containers: docker stop ${CONTAINER_NAME} ollama"
echo "  Access ProjectCompass: docker exec -it ${CONTAINER_NAME} bash"
echo "  Access Ollama: docker exec -it ollama bash"
echo "  Test Ollama: curl http://localhost:11434/api/tags"
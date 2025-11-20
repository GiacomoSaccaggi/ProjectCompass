#!/bin/bash

# Setup script for Ollama with required models

echo "Setting up Ollama with LLM models..."

# Start Ollama container if not running
if ! docker ps | grep -q ollama; then
    echo "Starting Ollama container..."
    docker run -d -v ollama_data:/root/.ollama -p 11434:11434 --name ollama ollama/ollama
    sleep 10
fi

# Pull required models
echo "Downloading Llama3 model (this may take a while)..."
docker exec ollama ollama pull llama3

echo "Downloading nomic-embed-text model..."
docker exec ollama ollama pull nomic-embed-text

echo "Ollama setup complete!"
echo "Available at: http://localhost:11434"
echo "Test with: curl http://localhost:11434/api/tags"
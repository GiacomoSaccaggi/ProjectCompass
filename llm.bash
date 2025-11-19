# Avvia il container Ollama
docker run -d -v ollama:/root/.ollama -p 11434:11434 --name ollama ollama/ollama

# Scarica un modello LLM (useremo 'llama3' come LLM per le query)
docker exec ollama ollama pull llama3

# Scarica un modello di Embedding (useremo 'nomic-embed-text' per gli embedding)
docker exec ollama ollama pull nomic-embed-text
# Publishing the Docker Image

This guide explains how to publish the ProjectCompass Docker image to GitHub Container Registry (ghcr.io) so anyone can install it with a single `docker compose up`.

---

## Prerequisites

- GitHub repository: `GiacomoSaccaggi/ProjectCompass`
- Repository must be **public** (for free ghcr.io hosting)
- GitHub Actions enabled (default for all repos)

---

## How It Works

The file `.github/workflows/docker-publish.yml` automatically builds and pushes the Docker image whenever you push a git tag starting with `v`.

**Tags generated:**
- `ghcr.io/giacomosaccaggi/projectcompass:latest`
- `ghcr.io/giacomosaccaggi/projectcompass:0.1.0` (from tag `v0.1.0`)
- `ghcr.io/giacomosaccaggi/projectcompass:0.1` (major.minor)

---

## Step-by-Step: First Publish

### 1. Enable ghcr.io on the repository

Go to **Settings → Actions → General → Workflow permissions** and select:
- ✅ Read and write permissions

This allows the workflow to push images to `ghcr.io`.

### 2. Commit all files and push

```bash
git add .
git commit -m "Add Docker publish workflow"
git push origin main
```

### 3. Create and push a version tag

```bash
git tag v0.1.0
git push origin v0.1.0
```

This triggers the `docker-publish.yml` workflow. Monitor progress at:
`https://github.com/GiacomoSaccaggi/ProjectCompass/actions`

### 4. Verify the image is published

Go to: `https://github.com/GiacomoSaccaggi/ProjectCompass/pkgs/container/projectcompass`

Or pull it locally:
```bash
docker pull ghcr.io/giacomosaccaggi/projectcompass:latest
```

### 5. Make the package public (first time only)

By default ghcr.io packages inherit repo visibility, but verify:
1. Go to the package page (link above)
2. Click **Package settings**
3. Under "Danger Zone" → Change visibility → **Public**

---

## How Users Install ProjectCompass

Users only need one file. Give them `docker-compose.public.yml` (or they can copy-paste this):

```yaml
services:
  projectcompass:
    image: ghcr.io/giacomosaccaggi/projectcompass:latest
    ports:
      - "8080:8080"
    environment:
      - SECRET_KEY=change-me-to-a-random-string
      - ADMIN_USERNAME=admin
      - ADMIN_PASSWORD_HASH=
      - PORT=8080
      - OLLAMA_HOST=http://ollama:11434
    volumes:
      - ./data/Analyses:/app/Analyses
      - ./data/Saved_data:/app/Saved_data
      - ./data/Saved_queries:/app/Saved_queries
    restart: unless-stopped
    depends_on:
      - ollama

  ollama:
    image: ollama/ollama
    ports:
      - "11434:11434"
    volumes:
      - ollama_data:/root/.ollama
    restart: unless-stopped

volumes:
  ollama_data:
```

Then:

```bash
# Download the compose file
curl -O https://raw.githubusercontent.com/GiacomoSaccaggi/ProjectCompass/main/docker-compose.public.yml

# Start
docker compose -f docker-compose.public.yml up -d

# Open browser
open http://localhost:8080

# (Optional) Setup AI models
docker exec ollama ollama pull llama3
docker exec ollama ollama pull nomic-embed-text
```

---

## Releasing a New Version

```bash
# 1. Make changes and commit
git add .
git commit -m "feat: description of changes"
git push origin main

# 2. Tag the release
git tag v0.2.0
git push origin v0.2.0

# The workflow automatically builds and publishes:
#   ghcr.io/giacomosaccaggi/projectcompass:0.2.0
#   ghcr.io/giacomosaccaggi/projectcompass:0.2
#   ghcr.io/giacomosaccaggi/projectcompass:latest
```

Users update with:
```bash
docker compose -f docker-compose.public.yml pull
docker compose -f docker-compose.public.yml up -d
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Workflow fails with "permission denied" | Settings → Actions → Workflow permissions → Read and write |
| Image not visible to public | Package settings → Change visibility → Public |
| Users get "manifest unknown" | Tag wasn't pushed: `git push origin v0.1.0` |
| Build fails | Check Actions tab for error logs |

---

## File Summary

| File | Purpose |
|------|---------|
| `.github/workflows/docker-publish.yml` | Automated build+push on `v*` tags |
| `docker-compose.public.yml` | Ready-to-use compose for end users |
| `docker-compose.yml` | Development compose (builds from source) |
| `Dockerfile` | Image definition with healthcheck |

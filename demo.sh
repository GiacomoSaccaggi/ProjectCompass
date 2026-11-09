#!/bin/bash
set -e

cd "$(dirname "$0")"

echo "Building and starting ProjectCompass + k0s cluster + demo databases..."
docker compose -f docker-compose.yml -f docker-compose.demo.yml up -d --build

echo ""
bash scripts/k0s_setup.sh -f docker-compose.yml -f docker-compose.demo.yml

#!/bin/bash
set -e

# ProjectCompass k0s Cluster Bootstrap
# Run AFTER: docker compose up -d --build (or via bash demo.sh)
#
# What this does:
#   1. Waits for the k0s controller to be ready
#   2. Generates a worker join token → workers pick it up and join
#   3. Creates a K8s ServiceAccount for ProjectCompass → bearer token
#   4. Saves the token to .env.k0s → compose reads it on restart
#   5. Restarts ProjectCompass with K8s credentials

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

if [ $# -gt 0 ]; then
    COMPOSE_ARGS="$*"
elif [ -n "${COMPOSE_FILES:-}" ]; then
    COMPOSE_ARGS="$COMPOSE_FILES"
else
    COMPOSE_ARGS="-f docker-compose.yml"
fi
COMPOSE="docker compose $COMPOSE_ARGS"

echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║   ProjectCompass — k0s Cluster Bootstrap         ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""

# 1. Wait for controller
echo "[1/5] Waiting for k0s controller..."
until docker exec k0s k0s status 2>/dev/null | grep -q "Process ID"; do
    printf "."
    sleep 3
done
echo " ready."

echo "[2/5] Waiting for K8s API..."
until docker exec k0s k0s kubectl get --raw /readyz 2>/dev/null | grep -q "ok"; do
    printf "."
    sleep 3
done
echo " API ready."

# 2. Generate worker join token
echo "[3/5] Generating worker join token..."
WORKER_TOKEN=$(docker exec k0s k0s token create --role=worker --expiry=0)
# Write token to the shared Docker volume via a temp container
VOLUME_NAME="${COMPOSE_PROJECT_NAME:-projectcompass}_k0s-tokens"
echo "$WORKER_TOKEN" | docker run -i --rm -v "${VOLUME_NAME}:/tokens" alpine sh -c 'cat > /tokens/worker && chmod 444 /tokens/worker'
echo "  Token written. Workers will join automatically."

# 3. Wait for workers
echo "  Waiting for workers to become Ready..."
for attempt in $(seq 1 40); do
    READY=$(docker exec k0s k0s kubectl get nodes --no-headers 2>/dev/null | grep -c " Ready" || true)
    if [ "$READY" -ge 2 ]; then
        break
    fi
    printf "."
    sleep 5
done
echo ""
docker exec k0s k0s kubectl get nodes 2>/dev/null || true
echo ""

# 4. Create ServiceAccount + bearer token for ProjectCompass
echo "[4/5] Creating K8s ServiceAccount for ProjectCompass..."
docker exec k0s k0s kubectl create serviceaccount projectcompass -n default 2>/dev/null || true
docker exec k0s k0s kubectl create clusterrolebinding projectcompass-admin \
    --clusterrole=admin --serviceaccount=default:projectcompass 2>/dev/null || true
K8S_TOKEN=$(docker exec k0s k0s kubectl create token projectcompass -n default --duration=8760h 2>/dev/null)

if [ -z "$K8S_TOKEN" ]; then
    echo "  ERROR: Failed to generate bearer token."
    exit 1
fi
echo "  ServiceAccount ready (token valid for 1 year)."

# 5. Save token and restart ProjectCompass
echo "[5/5] Configuring ProjectCompass..."
echo "K8S_BEARER_TOKEN=${K8S_TOKEN}" > .env.k0s
$COMPOSE up -d projectcompass
echo ""

# Summary
echo "╔══════════════════════════════════════════════════╗"
echo "║   ✅  k0s Cluster Ready                          ║"
echo "╠══════════════════════════════════════════════════╣"
echo "║                                                  ║"
echo "║   ProjectCompass:  http://localhost:8080          ║"
echo "║   K8s API:         https://localhost:6443         ║"
echo "║   MinIO Console:   http://localhost:9001          ║"
echo "║   MinIO S3 API:    http://localhost:9002          ║"
echo "║   Registry:        http://localhost:5050          ║"
echo "║   Login:           admin / admin                  ║"
echo "║   MinIO Login:     minioadmin / minioadmin        ║"
echo "║                                                  ║"
echo "║   Workers:                                        ║"
docker exec k0s k0s kubectl get nodes --no-headers 2>/dev/null | while read -r line; do
    NAME=$(echo "$line" | awk '{print $1}')
    STATUS=$(echo "$line" | awk '{print $2}')
    printf "║     %-20s %s\n" "$NAME" "$STATUS"
done
echo "║                                                  ║"
echo "║   Flows submitted via /flows → run as K8s Jobs   ║"
echo "║   on the worker nodes above.                     ║"
echo "║                                                  ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""
echo "kubectl access:  docker exec k0s k0s kubectl get pods -A"
echo "Cluster logs:    $COMPOSE logs -f"
echo "Teardown:        $COMPOSE down -v"

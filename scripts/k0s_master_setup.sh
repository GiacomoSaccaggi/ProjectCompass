#!/usr/bin/env bash
# ==============================================================================
# ProjectCompass — Reproducible k0s Master + Worker Setup Script
# ==============================================================================
# Provisions a single-cluster k0s control plane with local worker capability
# (--enable-worker) on an existing Linux host so the ProjectCompass web console
# and initial flows are immediately executable before external workers join.
#
# Usage:
#   sudo ./scripts/k0s_master_setup.sh
# ==============================================================================

set -euo pipefail

K0S_CONFIG_DIR="/etc/k0s"
K0S_CONFIG_FILE="${K0S_CONFIG_DIR}/k0s.yaml"
KUBECONFIG_EXPORT="/etc/k0s/projectcompass.kubeconfig"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo "[1/5] Checking for k0s binary..."
if ! command -v k0s >/dev/null 2>&1; then
  echo "Installing k0s via official download script..."
  curl -sSLf https://get.k0s.sh | sh
fi

echo "[2/5] Generating default k0s configuration at ${K0S_CONFIG_FILE}..."
mkdir -p "${K0S_CONFIG_DIR}"
if [ ! -f "${K0S_CONFIG_FILE}" ]; then
  k0s config create > "${K0S_CONFIG_FILE}"
fi

echo "[3/5] Installing k0s controller with worker capability (--enable-worker)..."
if ! systemctl is-active --quiet k0scontroller 2>/dev/null; then
  k0s install controller --enable-worker --no-taints -c "${K0S_CONFIG_FILE}"
  k0s start
fi

echo "[4/5] Waiting for k0s Kubernetes API and node readiness..."
for _ in $(seq 1 30); do
  if k0s kubectl get nodes >/dev/null 2>&1; then
    break
  fi
  sleep 2
done
k0s kubectl get nodes -o wide

echo "[5/5] Applying ProjectCompass least-privilege RBAC and exporting kubeconfig..."
if [ -f "${REPO_ROOT}/k8s/projectcompass-rbac.yaml" ]; then
  k0s kubectl apply -f "${REPO_ROOT}/k8s/projectcompass-rbac.yaml"
fi

cp /var/lib/k0s/pki/admin.conf "${KUBECONFIG_EXPORT}"
chmod 600 "${KUBECONFIG_EXPORT}"

cat <<EOF

================================================================================
k0s Master + Worker is ready!
- Kubeconfig exported to: ${KUBECONFIG_EXPORT}
- Start ProjectCompass with:
    export K8S_KUBECONFIG=${KUBECONFIG_EXPORT}
    export K8S_NAMESPACE=default
    uv run python app.py

To generate a join token for external worker machines (AWS, GCP, Azure, bare-metal):
    sudo k0s token create --role=worker --expiry=24h > worker-join.token
================================================================================
EOF

"""
░██╗░░██╗░█████╗░░██████╗░░░░░░██╗░░░██╗████████╗██╗██╗░░░░░░██████╗
░██║░██╔╝██╔══██╗██╔════╝░░░░░░██║░░░██║╚══██╔══╝██║██║░░░░░██╔════╝
░█████═╝░╚█████╔╝╚█████╗░█████╗██║░░░██║░░░██║░░░██║██║░░░░░╚█████╗░
░██╔═██╗░██╔══██╗░╚═══██╗╚════╝██║░░░██║░░░██║░░░██║██║░░░░░░╚═══██╗
░██║░╚██╗╚█████╔╝██████╔╝░░░░░░╚██████╔╝░░░██║░░░██║███████╗██████╔╝
░╚═╝░░╚═╝░╚════╝░╚═════╝░░░░░░░░╚═════╝░░░░╚═╝░░░╚═╝╚══════╝╚═════╝░
"""

from __future__ import annotations

import base64
import json
import os
import re
import threading
import time
from abc import ABC, abstractmethod
from datetime import datetime
from typing import TYPE_CHECKING, Any

import httpx
import yaml

from logging_config import logger
from models import Execution, K8sWorkerNode, db, fire_webhooks
from utils.worker_provider import (
    DockerWorkerProvider,
    WorkerProvider,
    WorkerProviderError,
)

if TYPE_CHECKING:
    from utils.app_settings import WorkerSettings


class K8sClientError(Exception):
    """Base exception for Kubernetes API and configuration errors."""


class K8sConfigurationError(K8sClientError):
    """Raised when Kubernetes API credentials or endpoints are not configured."""


class K8sApiError(K8sClientError):
    """Raised when the Kubernetes API returns an error status or fails to connect."""

    def __init__(self, message: str, status_code: int | None = None, body: str = "") -> None:
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class BaseK8sClient(ABC):
    """Abstract parent class encapsulating Kubernetes REST API transport.

    Provides authenticated REST primitives over httpx using either in-cluster
    ServiceAccount credentials, a k0s/Kubernetes kubeconfig file, or explicit
    environment variables, without requiring external cluster agents.
    """

    IN_CLUSTER_TOKEN_PATH: str = "/var/run/secrets/kubernetes.io/serviceaccount/token"
    IN_CLUSTER_CA_PATH: str = "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"
    DEFAULT_K0S_KUBECONFIG: str = "/var/lib/k0s/pki/admin.conf"

    def __init__(self, dir_path: str = "", data_dir: str = "", **kwargs: Any) -> None:
        """Initialize Kubernetes API transport state and forward cooperative kwargs."""
        self.dir_path: str = dir_path
        self.data_dir: str = data_dir or dir_path
        self._k8s_namespace: str = os.environ.get("K8S_NAMESPACE", "default")
        self._k8s_api_url: str = ""
        self._k8s_token: str = ""
        self._k8s_verify: bool | str = True
        self._k8s_client_cert: tuple[str, str] | None = None
        self._k8s_timeout: float = 15.0
        self._last_k8s_error: str | None = None
        self._load_k8s_credentials()
        super().__init__(**kwargs)

    def _load_k8s_credentials(self) -> None:
        """Discover Kubernetes API endpoint and authentication credentials."""
        self._k8s_namespace = os.environ.get("K8S_NAMESPACE", "default")
        explicit_url = os.environ.get("K8S_API_URL", "").strip()
        explicit_token = os.environ.get("K8S_BEARER_TOKEN", "").strip()
        verify_env = os.environ.get("K8S_VERIFY_SSL", "true").strip().lower()

        if explicit_url:
            self._k8s_api_url = explicit_url.rstrip("/")
            self._k8s_token = explicit_token
            self._k8s_verify = verify_env not in ("false", "0", "no")
            return

        in_cluster_pref = os.environ.get("K8S_IN_CLUSTER", "auto").strip().lower()
        k8s_host = os.environ.get("KUBERNETES_SERVICE_HOST", "").strip()
        k8s_port = os.environ.get("KUBERNETES_SERVICE_PORT", "443").strip()

        if in_cluster_pref in ("true", "1", "auto") and k8s_host and os.path.exists(self.IN_CLUSTER_TOKEN_PATH):
            try:
                with open(self.IN_CLUSTER_TOKEN_PATH, encoding="utf-8") as token_file:
                    self._k8s_token = token_file.read().strip()
                self._k8s_api_url = f"https://{k8s_host}:{k8s_port}"
                if os.path.exists(self.IN_CLUSTER_CA_PATH) and verify_env not in ("false", "0", "no"):
                    self._k8s_verify = self.IN_CLUSTER_CA_PATH
                else:
                    self._k8s_verify = False
                return
            except OSError as exc:
                logger.warning(f"Failed reading in-cluster Kubernetes credentials: {exc}")

        kubeconfig_candidates = [
            os.environ.get("K8S_KUBECONFIG", "").strip(),
            os.environ.get("KUBECONFIG", "").strip(),
            self.DEFAULT_K0S_KUBECONFIG,
            os.path.expanduser("~/.kube/config"),
        ]
        for candidate in kubeconfig_candidates:
            if candidate and os.path.isfile(candidate):
                if self._parse_kubeconfig_file(candidate, verify_env):
                    return

    def _parse_kubeconfig_file(self, kubeconfig_path: str, verify_env: str) -> bool:
        """Load server URL, CA bundle, and token/client certs from a kubeconfig file."""
        try:
            with open(kubeconfig_path, encoding="utf-8") as cfg_file:
                cfg = yaml.safe_load(cfg_file) or {}
        except (OSError, yaml.YAMLError) as exc:
            logger.warning(f"Could not parse kubeconfig at {kubeconfig_path}: {exc}")
            return False

        clusters = cfg.get("clusters") or []
        users = cfg.get("users") or []
        contexts = cfg.get("contexts") or []
        current_ctx_name = cfg.get("current-context")

        cluster_info: dict[str, Any] = {}
        user_info: dict[str, Any] = {}

        if contexts:
            selected_ctx = next(
                (c.get("context", {}) for c in contexts if c.get("name") == current_ctx_name),
                contexts[0].get("context", {}),
            )
            cluster_name = selected_ctx.get("cluster")
            user_name = selected_ctx.get("user")
            if selected_ctx.get("namespace") and not os.environ.get("K8S_NAMESPACE"):
                self._k8s_namespace = str(selected_ctx["namespace"])
            cluster_info = next(
                (c.get("cluster", {}) for c in clusters if c.get("name") == cluster_name),
                clusters[0].get("cluster", {}) if clusters else {},
            )
            user_info = next(
                (u.get("user", {}) for u in users if u.get("name") == user_name),
                users[0].get("user", {}) if users else {},
            )
        else:
            if clusters:
                cluster_info = clusters[0].get("cluster", {})
            if users:
                user_info = users[0].get("user", {})

        server = str(cluster_info.get("server", "")).strip()
        if not server:
            return False

        self._k8s_api_url = server.rstrip("/")
        self._k8s_token = str(user_info.get("token", "")).strip()

        tmp_dir = os.path.join(self.dir_path or ".", "tmp")
        os.makedirs(tmp_dir, exist_ok=True)

        if verify_env in ("false", "0", "no") or cluster_info.get("insecure-skip-tls-verify"):
            self._k8s_verify = False
        elif cluster_info.get("certificate-authority") and os.path.isfile(str(cluster_info["certificate-authority"])):
            self._k8s_verify = str(cluster_info["certificate-authority"])
        elif cluster_info.get("certificate-authority-data"):
            try:
                ca_bytes = base64.b64decode(cluster_info["certificate-authority-data"])
                ca_path = os.path.join(tmp_dir, "k8s_ca.crt")
                with open(ca_path, "wb") as ca_file:
                    ca_file.write(ca_bytes)
                self._k8s_verify = ca_path
            except Exception:
                self._k8s_verify = False

        cert_path = user_info.get("client-certificate")
        key_path = user_info.get("client-key")
        if cert_path and key_path and os.path.isfile(str(cert_path)) and os.path.isfile(str(key_path)):
            self._k8s_client_cert = (str(cert_path), str(key_path))
        elif user_info.get("client-certificate-data") and user_info.get("client-key-data"):
            try:
                cert_bytes = base64.b64decode(user_info["client-certificate-data"])
                key_bytes = base64.b64decode(user_info["client-key-data"])
                c_file = os.path.join(tmp_dir, "k8s_client.crt")
                k_file = os.path.join(tmp_dir, "k8s_client.key")
                with open(c_file, "wb") as cf:
                    cf.write(cert_bytes)
                with open(k_file, "wb") as kf:
                    kf.write(key_bytes)
                self._k8s_client_cert = (c_file, k_file)
            except Exception as exc:
                logger.warning(f"Failed writing client certificate from kubeconfig: {exc}")

        return True

    def _build_headers(self, accept: str = "application/json") -> dict[str, str]:
        """Construct HTTP headers for Kubernetes API requests."""
        headers: dict[str, str] = {"Accept": accept}
        if self._k8s_token:
            headers["Authorization"] = f"Bearer {self._k8s_token}"
        return headers

    def _ensure_configured(self) -> None:
        """Reload credentials if needed and raise if no API endpoint is configured."""
        if not self._k8s_api_url:
            self._load_k8s_credentials()
        if not self._k8s_api_url:
            raise K8sConfigurationError(
                "Kubernetes API endpoint is not configured. Set K8S_API_URL / K8S_KUBECONFIG "
                "or run on a host with k0s (/var/lib/k0s/pki/admin.conf)."
            )

    def _k8s_request(
        self,
        method: str,
        path: str,
        json_body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute an authenticated JSON request against the Kubernetes API server."""
        self._ensure_configured()
        url = f"{self._k8s_api_url}/{path.lstrip('/')}"
        try:
            with httpx.Client(
                verify=self._k8s_verify,
                cert=self._k8s_client_cert,
                timeout=self._k8s_timeout,
            ) as client:
                response = client.request(
                    method=method.upper(),
                    url=url,
                    headers=self._build_headers(),
                    json=json_body,
                    params=params,
                )
        except httpx.HTTPError as exc:
            self._last_k8s_error = str(exc)
            raise K8sApiError(f"Kubernetes API request failed ({method} {path}): {exc}") from exc

        if response.status_code >= 400:
            err_msg = f"Kubernetes API returned HTTP {response.status_code} for {method} {path}"
            try:
                err_payload = response.json()
                if isinstance(err_payload, dict) and err_payload.get("message"):
                    err_msg = f"{err_msg}: {err_payload['message']}"
            except ValueError:
                pass
            self._last_k8s_error = err_msg
            raise K8sApiError(err_msg, status_code=response.status_code, body=response.text)

        self._last_k8s_error = None
        if not response.text.strip():
            return {}
        try:
            return response.json()
        except ValueError as exc:
            raise K8sApiError(f"Invalid JSON from Kubernetes API ({path}): {exc}") from exc

    def _k8s_get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Perform an authenticated GET request against the Kubernetes REST API."""
        return self._k8s_request("GET", path, params=params)

    def _k8s_post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Perform an authenticated POST request against the Kubernetes REST API."""
        return self._k8s_request("POST", path, json_body=payload)

    def _k8s_delete(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Perform an authenticated DELETE request against the Kubernetes REST API."""
        return self._k8s_request("DELETE", path, json_body=json_body, params=params)

    def _k8s_get_text(self, path: str, params: dict[str, Any] | None = None) -> str:
        """Perform an authenticated GET request returning plain text (such as Pod logs)."""
        self._ensure_configured()
        url = f"{self._k8s_api_url}/{path.lstrip('/')}"
        try:
            with httpx.Client(
                verify=self._k8s_verify,
                cert=self._k8s_client_cert,
                timeout=self._k8s_timeout,
            ) as client:
                response = client.get(
                    url,
                    headers=self._build_headers(accept="text/plain, */*"),
                    params=params,
                )
        except httpx.HTTPError as exc:
            raise K8sApiError(f"Kubernetes log fetch failed ({path}): {exc}") from exc

        if response.status_code >= 400:
            raise K8sApiError(
                f"Kubernetes API returned HTTP {response.status_code} for GET {path}",
                status_code=response.status_code,
                body=response.text,
            )
        return response.text

    @abstractmethod
    def get_cluster_summary(self) -> dict[str, Any]:
        """Return synchronized cluster worker state and summary metrics."""


class K8sClusterUtils(BaseK8sClient):
    """Child class responsible for read-only worker node discovery and state tracking.

    Synchronizes `/api/v1/nodes` (and optional `metrics.k8s.io` node metrics)
    with the `K8sWorkerNode` SQLite table so the UI distinguishes active (`Ready`),
    unreachable (`NotReady`), and deleted (`Removed`) cluster nodes.
    """

    def __init__(self, dir_path: str = "", **kwargs: Any) -> None:
        """Initialize cluster node monitor state and default worker provider."""
        self._settings: Any = None
        self._worker_provider_customized: bool = False
        self._worker_provider: WorkerProvider = self._build_worker_provider(None)
        super().__init__(dir_path=dir_path, **kwargs)

    def _fetch_raw_nodes(self) -> dict[str, Any]:
        """Query `/api/v1/nodes` and return the raw payload or an empty dict on error."""
        try:
            payload = self._k8s_get("/api/v1/nodes")
            return payload if isinstance(payload, dict) else {}
        except K8sClientError:
            return {}

    def _delete_k8s_node(self, node_name: str) -> None:
        """Delete a Kubernetes Node object by name, ignoring errors if already absent."""
        try:
            self._k8s_delete(f"/api/v1/nodes/{node_name}")
        except K8sClientError:
            pass

    def _build_worker_provider(self, worker_settings: WorkerSettings | None) -> WorkerProvider:
        """Create a WorkerProvider instance bound to this cluster's node callbacks."""
        return WorkerProvider.from_settings(
            settings=worker_settings,
            k8s_nodes_callback=self._fetch_raw_nodes,
            k8s_delete_node_callback=self._delete_k8s_node,
        )

    def configure_worker_provider(self, worker_settings: WorkerSettings | None = None) -> WorkerProvider:
        """Reconfigure the active WorkerProvider from application settings."""
        self._worker_provider = self._build_worker_provider(worker_settings)
        self._worker_provider_customized = False
        return self._worker_provider

    @property
    def worker_provider(self) -> WorkerProvider:
        """Return the active WorkerProvider managing k0s worker nodes."""
        return self._worker_provider

    @worker_provider.setter
    def worker_provider(self, provider: WorkerProvider) -> None:
        """Assign a custom or mock WorkerProvider instance."""
        self._worker_provider = provider
        self._worker_provider_customized = True

    def _should_manage_workers(self) -> bool:
        """Determine whether automatic worker provisioning/cleanup should execute."""
        worker_settings = getattr(self._settings, "workers", None)
        return bool(getattr(worker_settings, "auto_provision", False))

    def _count_ready_workers(self) -> int:
        """Return the number of Ready worker nodes reported by `/api/v1/nodes`."""
        payload = self._fetch_raw_nodes()
        return len(DockerWorkerProvider.extract_ready_worker_names(payload))

    @staticmethod
    def _parse_node_status(node_item: dict[str, Any]) -> str:
        """Determine whether a Kubernetes Node is Ready, NotReady, or Unknown."""
        conditions = node_item.get("status", {}).get("conditions") or []
        for cond in conditions:
            if cond.get("type") == "Ready":
                cond_status = str(cond.get("status", "")).strip()
                if cond_status == "True":
                    return "Ready"
                return "NotReady"
        return "Unknown"

    @staticmethod
    def _parse_node_roles(node_item: dict[str, Any]) -> str:
        """Extract node roles from standard Kubernetes and k0s labels."""
        labels = node_item.get("metadata", {}).get("labels") or {}
        roles: list[str] = []
        for key, val in labels.items():
            if key.startswith("node-role.kubernetes.io/"):
                role_name = key.split("/", 1)[1].strip()
                if role_name and role_name not in roles:
                    roles.append(role_name)
            elif key in ("kubernetes.io/role", "node.k0sproject.io/role") and val:
                role_val = str(val).strip()
                if role_val and role_val not in roles:
                    roles.append(role_val)
        if not roles:
            return "worker"
        return ",".join(sorted(roles))

    @staticmethod
    def _parse_node_ip(node_item: dict[str, Any]) -> str:
        """Extract the primary IP address of a node from status.addresses."""
        addresses = node_item.get("status", {}).get("addresses") or []
        internal_ip = ""
        external_ip = ""
        hostname = ""
        for addr in addresses:
            addr_type = addr.get("type")
            addr_val = str(addr.get("address", "")).strip()
            if addr_type == "InternalIP" and addr_val:
                internal_ip = addr_val
            elif addr_type == "ExternalIP" and addr_val:
                external_ip = addr_val
            elif addr_type == "Hostname" and addr_val:
                hostname = addr_val
        return internal_ip or external_ip or hostname or "-"

    @staticmethod
    def _format_memory(raw_mem: str | None) -> str:
        """Format Kubernetes memory quantities (Ki, Mi, Gi) into human-readable units."""
        if not raw_mem:
            return "-"
        val = str(raw_mem).strip()
        try:
            if val.endswith("Ki"):
                kib = int(val[:-2])
                gib = kib / (1024 * 1024)
                if gib >= 1.0:
                    return f"{gib:.1f} GiB"
                mib = kib / 1024
                return f"{mib:.0f} MiB"
            if val.endswith("Mi"):
                mib_val = float(val[:-2])
                if mib_val >= 1024:
                    return f"{mib_val / 1024:.1f} GiB"
                return f"{mib_val:.0f} MiB"
            if val.endswith("Gi"):
                return f"{float(val[:-2]):.1f} GiB"
        except ValueError:
            pass
        return val

    def _fetch_node_metrics(self) -> dict[str, dict[str, str]]:
        """Query optional metrics.k8s.io endpoint for live CPU and RAM usage per node."""
        try:
            payload = self._k8s_get("/apis/metrics.k8s.io/v1beta1/nodes")
        except K8sClientError:
            return {}

        usage_by_node: dict[str, dict[str, str]] = {}
        for item in payload.get("items") or []:
            name = item.get("metadata", {}).get("name")
            usage = item.get("usage") or {}
            if name:
                usage_by_node[str(name)] = {
                    "cpu": str(usage.get("cpu", "")),
                    "memory": self._format_memory(usage.get("memory")),
                }
        return usage_by_node

    def sync_worker_nodes(self) -> tuple[list[K8sWorkerNode], str | None]:
        """Synchronize live Kubernetes nodes with the SQLite K8sWorkerNode table.

        Nodes returned by `/api/v1/nodes` are inserted or updated with their live
        `Ready` or `NotReady` condition. Previously known nodes that are no longer
        present in `/api/v1/nodes` are marked as `Removed` with `removed_at` set,
        preserving the distinction between an unreachable node and a deleted node.
        """
        try:
            nodes_payload = self._k8s_get("/api/v1/nodes")
        except K8sClientError as exc:
            existing_nodes = K8sWorkerNode.query.order_by(K8sWorkerNode.name.asc()).all()
            return existing_nodes, str(exc)

        metrics_map = self._fetch_node_metrics()
        items = nodes_payload.get("items") or []
        now = datetime.utcnow()
        seen_names: set[str] = set()

        for item in items:
            metadata = item.get("metadata") or {}
            node_name = str(metadata.get("name", "")).strip()
            if not node_name:
                continue

            seen_names.add(node_name)
            uid = str(metadata.get("uid", "")).strip() or None
            node_status = self._parse_node_status(item)
            roles = self._parse_node_roles(item)
            internal_ip = self._parse_node_ip(item)

            status_block = item.get("status") or {}
            capacity = status_block.get("capacity") or {}
            allocatable = status_block.get("allocatable") or {}
            node_info = status_block.get("nodeInfo") or {}

            cpu_cap = str(capacity.get("cpu", "-"))
            mem_cap = self._format_memory(capacity.get("memory"))
            cpu_alloc = str(allocatable.get("cpu", "-"))
            mem_alloc = self._format_memory(allocatable.get("memory"))
            kubelet_ver = str(node_info.get("kubeletVersion", "")) or None

            node_metrics = metrics_map.get(node_name, {})
            cpu_use = node_metrics.get("cpu") or None
            mem_use = node_metrics.get("memory") or None

            record = K8sWorkerNode.query.filter_by(name=node_name).first()
            if record is None:
                record = K8sWorkerNode(
                    name=node_name,
                    uid=uid,
                    status=node_status,
                    roles=roles,
                    internal_ip=internal_ip,
                    cpu_capacity=cpu_cap,
                    memory_capacity=mem_cap,
                    cpu_allocatable=cpu_alloc,
                    memory_allocatable=mem_alloc,
                    cpu_usage=cpu_use,
                    memory_usage=mem_use,
                    kubelet_version=kubelet_ver,
                    first_seen_at=now,
                    last_seen_at=now,
                    removed_at=None,
                )
                db.session.add(record)
            else:
                record.uid = uid
                record.status = node_status
                record.roles = roles
                record.internal_ip = internal_ip
                record.cpu_capacity = cpu_cap
                record.memory_capacity = mem_cap
                record.cpu_allocatable = cpu_alloc
                record.memory_allocatable = mem_alloc
                record.cpu_usage = cpu_use
                record.memory_usage = mem_use
                record.kubelet_version = kubelet_ver
                record.last_seen_at = now
                record.removed_at = None

        all_records = K8sWorkerNode.query.all()
        for existing in all_records:
            if existing.name not in seen_names and existing.status != "Removed":
                existing.status = "Removed"
                existing.removed_at = now

        db.session.commit()
        ordered_nodes = K8sWorkerNode.query.order_by(K8sWorkerNode.name.asc()).all()
        return ordered_nodes, None

    def get_cluster_summary(self) -> dict[str, Any]:
        """Synchronize worker nodes and compute cluster health summary counters."""
        nodes, error = self.sync_worker_nodes()
        ready_count = sum(1 for n in nodes if n.status == "Ready")
        not_ready_count = sum(1 for n in nodes if n.status in ("NotReady", "Unknown"))
        removed_count = sum(1 for n in nodes if n.status == "Removed")
        return {
            "nodes": nodes,
            "total_active": ready_count + not_ready_count,
            "ready": ready_count,
            "not_ready": not_ready_count,
            "removed": removed_count,
            "connected": error is None,
            "error": error,
            "updated_at": datetime.utcnow(),
        }


class K8sFlowRunnerUtils(K8sClusterUtils):
    """Child class orchestrating isolated Kubernetes batch/v1 Jobs and log persistence.

    Each manual or scheduled Flow execution creates a distinct `Execution` record
    (`run_id`), provisions a per-run `ConfigMap` (`pc-flow-cfg-<run_id>`) and optional
    `Secret` (`pc-flow-sec-<run_id>`), submits a `batch/v1` `Job` (`backoffLimit: 0`,
    `automountServiceAccountToken: false`), and streams Pod stdout/stderr into SQLite.
    """

    ARTIFACT_BLOCK_RE = re.compile(
        r"\[PC_ARTIFACT_BEGIN:([^\]]+)\]\r?\n?(.*?)\r?\n?\[PC_ARTIFACT_END\]\r?\n?",
        re.DOTALL,
    )
    INCOMPLETE_ARTIFACT_RE = re.compile(
        r"\[PC_ARTIFACT_BEGIN:[^\]]*\].*\Z",
        re.DOTALL,
    )

    def __init__(self, dir_path: str = "", **kwargs: Any) -> None:
        """Initialize Flow runner state and watcher synchronization Settings."""
        self._watcher_poll_interval: float = 0.5
        self._watcher_max_polls: int = 7200
        self._active_watchers: dict[int, threading.Thread] = {}
        super().__init__(dir_path=dir_path, **kwargs)

    @staticmethod
    def _sanitize_k8s_label(value: str) -> str:
        """Convert an arbitrary string into a valid Kubernetes label value (<=63 chars)."""
        cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", (value or "flow").strip()).strip("-._")
        return (cleaned or "flow")[:63]

    @staticmethod
    def _build_entrypoint_script(pip_requirements: list[str]) -> str:
        """Build the container shell entrypoint that optionally installs pip packages."""
        lines = [
            "#!/bin/sh",
            "set -e",
            "export HOME=/tmp",
            "export PATH=\"/tmp/.local/bin:$PATH\"",
            "export PYTHONPATH=\"/tmp/.local/lib/python/site-packages:$PYTHONPATH\"",
            "export PC_DATA_DIR=\"/tmp/pc_work/Saved_data\"",
            "mkdir -p /tmp/pc_work/Saved_data /tmp/pc_output/main",
            "for f in /workspace/saved_data__*; do",
            "  if [ -f \"$f\" ]; then",
            "    cp \"$f\" \"/tmp/pc_work/Saved_data/${f#/workspace/saved_data__}\"",
            "  fi",
            "done",
        ]
        if pip_requirements:
            lines.extend(
                [
                    "if [ -s /workspace/requirements.txt ]; then",
                    "  echo \"[ProjectCompass] Installing pip requirements...\"",
                    "  pip install --no-cache-dir --quiet --user -r /workspace/requirements.txt",
                    "fi",
                ]
            )
        lines.append("exec python -u /workspace/flow.py")
        return "\n".join(lines) + "\n"

    def _collect_saved_data_for_configmap(
        self,
        flow_name: str,
        code: str,
        skipped_warnings: list[str] | None = None,
    ) -> dict[str, str]:
        """Bundle referenced Saved_data/*.csv files into ConfigMap keys (saved_data__<file>)."""
        save_data_dir = getattr(self, "save_data_path", "") or os.path.join(
            self.data_dir or self.dir_path or "",
            "Saved_data",
        )
        if not save_data_dir or not os.path.isdir(save_data_dir):
            return {}

        base_analyses_dir = getattr(self, "save_folder_path", "") or os.path.join(
            self.data_dir or self.dir_path or "",
            "Analyses",
        )
        flow_dir = os.path.join(base_analyses_dir, flow_name)
        combined_source = code or ""
        for scan_dir in (flow_dir, os.path.join(flow_dir, "analysis")):
            if os.path.isdir(scan_dir):
                try:
                    for fname in sorted(os.listdir(scan_dir)):
                        if fname.endswith(".py"):
                            fpath = os.path.join(scan_dir, fname)
                            if os.path.isfile(fpath):
                                with open(fpath, encoding="utf-8", errors="ignore") as f_src:
                                    combined_source = combined_source + "\n" + f_src.read()
                except OSError:
                    pass

        referenced_csvs = {
            f"{ds}.csv"
            for ds in re.findall(r'read_csv\(.*?["\']([^"\'/\\]+)\.csv["\']', combined_source)
        } | set(re.findall(r'["\']([A-Za-z0-9_.-]+\.csv)["\']', combined_source))

        include_all_small = (
            "Saved_data" in combined_source
            or "STRUCTURED_SCRIPT_B64" in combined_source
            or bool(referenced_csvs)
        )
        if not include_all_small:
            return {}

        try:
            all_csvs = sorted(
                f for f in os.listdir(save_data_dir)
                if f.endswith(".csv") and not f.startswith(".")
            )
        except OSError:
            return {}

        ordered_candidates = [f for f in all_csvs if f in referenced_csvs] + [
            f for f in all_csvs if f not in referenced_csvs
        ]

        bundled: dict[str, str] = {}
        total_bytes = 0
        max_single_bytes = 512 * 1024
        max_total_bytes = 800 * 1024

        for csv_name in ordered_candidates:
            if csv_name not in referenced_csvs and not ("Saved_data" in combined_source or "STRUCTURED_SCRIPT_B64" in combined_source):
                continue
            full_csv_path = os.path.join(save_data_dir, csv_name)
            if not os.path.isfile(full_csv_path):
                continue
            try:
                size = os.path.getsize(full_csv_path)
                if size > max_single_bytes:
                    if skipped_warnings is not None:
                        skipped_warnings.append(
                            f"[ProjectCompass] WARNING: Saved_data/{csv_name} skipped; "
                            "file exceeds the 512 KB ConfigMap dataset limit."
                        )
                    continue
                if (total_bytes + size) > max_total_bytes:
                    if skipped_warnings is not None:
                        skipped_warnings.append(
                            f"[ProjectCompass] WARNING: Saved_data/{csv_name} skipped; "
                            "bundled datasets would exceed the 800 KB ConfigMap limit."
                        )
                    continue
                with open(full_csv_path, encoding="utf-8", errors="ignore") as f_csv:
                    bundled[f"saved_data__{csv_name}"] = f_csv.read()
                total_bytes += size
            except OSError:
                continue

        return bundled

    def build_configmap_manifest(
        self,
        run_id: int,
        flow_name: str,
        code: str,
        parameters: dict[str, Any],
        pip_requirements: list[str],
        namespace: str,
        skipped_warnings: list[str] | None = None,
    ) -> dict[str, Any]:
        """Construct the per-run Kubernetes ConfigMap manifest containing flow.py and entrypoint."""
        cm_name = f"pc-flow-cfg-{run_id}"
        reqs_text = "\n".join(pip_requirements) + ("\n" if pip_requirements else "")
        cm_data: dict[str, str] = {
            "flow.py": code if code.endswith("\n") else f"{code}\n",
            "params.json": json.dumps(parameters, indent=2),
            "requirements.txt": reqs_text,
            "entrypoint.sh": self._build_entrypoint_script(pip_requirements),
        }
        cm_data.update(self._collect_saved_data_for_configmap(flow_name, code, skipped_warnings))
        return {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {
                "name": cm_name,
                "namespace": namespace,
                "labels": {
                    "app.kubernetes.io/managed-by": "projectcompass",
                    "projectcompass/run-id": str(run_id),
                    "projectcompass/flow": self._sanitize_k8s_label(flow_name),
                },
            },
            "data": cm_data,
        }

    def build_secret_manifest(
        self,
        run_id: int,
        flow_name: str,
        env_vars: dict[str, str],
        namespace: str,
    ) -> dict[str, Any]:
        """Construct the temporary per-run Kubernetes Secret manifest for flow credentials."""
        sec_name = f"pc-flow-sec-{run_id}"
        return {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {
                "name": sec_name,
                "namespace": namespace,
                "labels": {
                    "app.kubernetes.io/managed-by": "projectcompass",
                    "projectcompass/run-id": str(run_id),
                    "projectcompass/flow": self._sanitize_k8s_label(flow_name),
                },
            },
            "type": "Opaque",
            "stringData": {str(k): str(v) for k, v in env_vars.items()},
        }

    def build_job_manifest(
        self,
        run_id: int,
        flow_name: str,
        image: str,
        parameters: dict[str, Any],
        has_secret: bool,
        namespace: str,
        ttl_seconds: int = 300,
        secret_refs: list[str] | str | None = None,
        dockerfile_mode: bool = False,
        total_pods: int = 1,
        workers: int = 1,
        pods_per_worker: int = 1,
    ) -> dict[str, Any]:
        """Construct the isolated Kubernetes batch/v1 Job manifest with backoffLimit=0.

        When *total_pods* > 1 the Job uses ``completionMode: Indexed`` so
        each Pod receives a unique ``JOB_COMPLETION_INDEX`` (0 … total_pods-1)
        set automatically by the Kubernetes API.
        """
        job_name = f"pc-flow-job-{run_id}"
        cm_name = f"pc-flow-cfg-{run_id}"
        sec_name = f"pc-flow-sec-{run_id}"

        cpu_request = os.environ.get("K8S_DEFAULT_CPU_REQUEST", "500m").strip() or "500m"
        cpu_limit = os.environ.get("K8S_DEFAULT_CPU_LIMIT", "1").strip() or "1"
        mem_request = os.environ.get("K8S_DEFAULT_MEMORY_REQUEST", "512Mi").strip() or "512Mi"
        mem_limit = os.environ.get("K8S_DEFAULT_MEMORY_LIMIT", "1Gi").strip() or "1Gi"

        env_list: list[dict[str, str]] = [
            {"name": "PYTHONUNBUFFERED", "value": "1"},
            {"name": "FLOW_NAME", "value": flow_name},
            {"name": "FLOW_RUN_ID", "value": str(run_id)},
            {"name": "FLOW_PARAMS_JSON", "value": json.dumps(parameters)},
            {"name": "FLOW_PARAMS_FILE", "value": "/workspace/params.json"},
            {"name": "PC_TOTAL_PODS", "value": str(total_pods)},
            {"name": "PC_WORKERS", "value": str(workers)},
            {"name": "PC_PODS_PER_WORKER", "value": str(pods_per_worker)},
        ]
        if dockerfile_mode:
            env_list.append({"name": "PC_DATA_DIR", "value": "/app/Saved_data"})
        # S3 artifact store credentials (MinIO)
        s3_endpoint = os.environ.get("PC_S3_ENDPOINT", "").strip()
        if s3_endpoint:
            env_list.extend([
                {"name": "PC_S3_ENDPOINT", "value": s3_endpoint},
                {"name": "PC_S3_ACCESS_KEY", "value": os.environ.get("PC_S3_ACCESS_KEY", "")},
                {"name": "PC_S3_SECRET_KEY", "value": os.environ.get("PC_S3_SECRET_KEY", "")},
                {"name": "PC_S3_BUCKET", "value": os.environ.get("PC_S3_BUCKET", "pc-artifacts")},
                {"name": "PC_OUTPUT_DIR", "value": "/tmp/pc_output"},
            ])
        for key, val in parameters.items():
            safe_env_key = re.sub(r"[^A-Za-z0-9_]", "_", str(key)).upper()
            if safe_env_key:
                env_list.append({"name": f"PC_PARAM_{safe_env_key}", "value": str(val)})

        container_spec: dict[str, Any] = {
            "name": "flow-runner",
            "image": image,
            "env": env_list,
            "resources": {
                "requests": {"cpu": cpu_request, "memory": mem_request},
                "limits": {"cpu": cpu_limit, "memory": mem_limit},
            },
        }

        if not dockerfile_mode:
            container_spec["workingDir"] = "/tmp"
            container_spec["command"] = ["/bin/sh", "/workspace/entrypoint.sh"]
            container_spec["volumeMounts"] = [
                {
                    "name": "flow-workspace",
                    "mountPath": "/workspace",
                    "readOnly": True,
                }
            ]

        cluster_secret_refs_raw = os.environ.get("K8S_SECRET_REFS", "")
        combined_secret_names: list[str] = []
        for token in re.split(r"[\r\n,]+", cluster_secret_refs_raw):
            cleaned = token.strip()
            if cleaned and cleaned not in combined_secret_names:
                combined_secret_names.append(cleaned)

        if secret_refs:
            flow_refs = (
                [str(s).strip() for s in secret_refs]
                if isinstance(secret_refs, list)
                else [t.strip() for t in re.split(r"[\r\n,]+", str(secret_refs))]
            )
            for ref in flow_refs:
                if ref and ref not in combined_secret_names:
                    combined_secret_names.append(ref)

        env_from: list[dict[str, Any]] = [
            {"secretRef": {"name": ref_name}} for ref_name in combined_secret_names
        ]
        if has_secret:
            env_from.append({"secretRef": {"name": sec_name}})
        if env_from:
            container_spec["envFrom"] = env_from

        job_spec: dict[str, Any] = {
                "backoffLimit": 0,
                "ttlSecondsAfterFinished": ttl_seconds,
            }
        if total_pods > 1:
            job_spec["completions"] = total_pods
            job_spec["parallelism"] = total_pods
            job_spec["completionMode"] = "Indexed"

        return {
            "apiVersion": "batch/v1",
            "kind": "Job",
            "metadata": {
                "name": job_name,
                "namespace": namespace,
                "labels": {
                    "app.kubernetes.io/managed-by": "projectcompass",
                    "projectcompass/run-id": str(run_id),
                    "projectcompass/flow": self._sanitize_k8s_label(flow_name),
                },
            },
            "spec": {
                **job_spec,
                "template": {
                    "metadata": {
                        "labels": {
                            "app.kubernetes.io/managed-by": "projectcompass",
                            "projectcompass/run-id": str(run_id),
                            "projectcompass/flow": self._sanitize_k8s_label(flow_name),
                            "job-name": job_name,
                        }
                    },
                    "spec": {
                        "automountServiceAccountToken": False,
                        "restartPolicy": "Never",
                        "dnsPolicy": "Default",
                        "containers": [container_spec],
                        **({"volumes": [
                            {
                                "name": "flow-workspace",
                                "configMap": {
                                    "name": cm_name,
                                    "defaultMode": 365,
                                },
                            }
                        ]} if not dockerfile_mode else {}),
                    },
                },
            },
        }

    def _build_and_push_image(
        self,
        analysis_name: str,
        analysis_dir: str,
        run_id: int,
    ) -> str:
        """Build a Docker image from the analysis Dockerfile and push it to the local registry."""
        import shutil
        import subprocess

        registry_host = os.environ.get("PC_REGISTRY_HOST", "localhost:5050")
        k8s_registry_host = os.environ.get("PC_REGISTRY_K8S_HOST", registry_host)
        safe_name = re.sub(r"[^a-z0-9_.-]", "-", analysis_name.lower().strip()).strip("-") or "flow"
        tag = f"{registry_host}/pc/{safe_name}:{run_id}"
        k8s_tag = f"{k8s_registry_host}/pc/{safe_name}:{run_id}"

        # Inject pc_entrypoint.sh and Saved_data/*.csv into the build context
        staged_files: list[str] = []
        created_dirs: list[str] = []

        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        entrypoint_src = os.path.join(repo_root, "scripts", "pc_entrypoint.sh")
        scripts_dst_dir = os.path.join(analysis_dir, "scripts")
        entrypoint_dst = os.path.join(scripts_dst_dir, "pc_entrypoint.sh")
        if os.path.isfile(entrypoint_src) and not os.path.exists(entrypoint_dst):
            if not os.path.isdir(scripts_dst_dir):
                os.makedirs(scripts_dst_dir, exist_ok=True)
                created_dirs.append(scripts_dst_dir)
            shutil.copy2(entrypoint_src, entrypoint_dst)
            staged_files.append(entrypoint_dst)

        save_data_dir = getattr(self, "save_data_path", "") or os.path.join(
            getattr(self, "data_dir", None) or getattr(self, "dir_path", None) or repo_root,
            "Saved_data",
        )
        if not os.path.isdir(save_data_dir):
            save_data_dir = os.path.join(repo_root, "Saved_data")

        if os.path.isdir(save_data_dir):
            combined_source = ""
            for scan_dir in (analysis_dir, os.path.join(analysis_dir, "analysis")):
                if os.path.isdir(scan_dir):
                    try:
                        for fname in sorted(os.listdir(scan_dir)):
                            if fname.endswith(".py"):
                                fpath = os.path.join(scan_dir, fname)
                                if os.path.isfile(fpath):
                                    with open(fpath, encoding="utf-8", errors="ignore") as f_src:
                                        combined_source += "\n" + f_src.read()
                    except OSError:
                        pass
            referenced_csvs = {
                f"{ds}.csv"
                for ds in re.findall(r'read_csv\(.*?["\']([^"\'/\\]+)\.csv["\']', combined_source)
            } | set(re.findall(r'["\']([A-Za-z0-9_.-]+\.csv)["\']', combined_source))
            stage_all_csvs = (
                "Saved_data" in combined_source
                or "PC_DATA_DIR" in combined_source
                or not referenced_csvs
            )
            try:
                all_csvs = sorted(
                    f for f in os.listdir(save_data_dir)
                    if f.endswith(".csv") and not f.startswith(".")
                )
            except OSError:
                all_csvs = []

            csvs_to_stage = [
                f for f in all_csvs
                if f in referenced_csvs or stage_all_csvs
            ]
            if csvs_to_stage:
                saved_data_dst_dir = os.path.join(analysis_dir, "Saved_data")
                if not os.path.isdir(saved_data_dst_dir):
                    os.makedirs(saved_data_dst_dir, exist_ok=True)
                    created_dirs.append(saved_data_dst_dir)
                for csv_name in csvs_to_stage:
                    src_csv = os.path.join(save_data_dir, csv_name)
                    dst_csv = os.path.join(saved_data_dst_dir, csv_name)
                    if os.path.isfile(src_csv) and not os.path.exists(dst_csv):
                        shutil.copy2(src_csv, dst_csv)
                        staged_files.append(dst_csv)

        try:
            build_result = subprocess.run(
                ["docker", "build", "-t", tag, analysis_dir],
                capture_output=True,
                text=True,
                timeout=600,
            )
            if build_result.returncode != 0:
                raise K8sApiError(
                    f"Docker build failed (exit {build_result.returncode}): {build_result.stderr[-500:]}",
                )

            push_result = subprocess.run(
                ["docker", "push", tag],
                capture_output=True,
                text=True,
                timeout=300,
            )
            if push_result.returncode != 0:
                raise K8sApiError(
                    f"Docker push failed (exit {push_result.returncode}): {push_result.stderr[-500:]}",
                )

            if k8s_tag != tag:
                tag_result = subprocess.run(
                    ["docker", "tag", tag, k8s_tag],
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                if tag_result.returncode != 0:
                    logger.debug(f"docker tag {tag} -> {k8s_tag} failed: {tag_result.stderr[:200]}")

            # Import image into k0s containerd for single-node setups using the K8s Job image reference
            import_cmd = f"docker save {k8s_tag} | docker exec -i k0s k0s ctr images import --all-platforms -"
            import_result = subprocess.run(  # noqa: S602
                import_cmd, shell=True, capture_output=True, text=True, timeout=120,
            )
            if import_result.returncode != 0:
                logger.debug(f"k0s ctr import skipped or failed: {import_result.stderr[:200]}")
        except subprocess.TimeoutExpired as exc:
            raise K8sApiError(f"Docker build/push timed out for '{analysis_name}'") from exc
        except FileNotFoundError as exc:
            raise K8sApiError("Docker CLI not found — ensure docker is available in the container") from exc
        finally:
            for fpath in staged_files:
                try:
                    if os.path.isfile(fpath):
                        os.remove(fpath)
                except OSError:
                    pass
            for dpath in reversed(created_dirs):
                try:
                    if os.path.isdir(dpath) and not os.listdir(dpath):
                        os.rmdir(dpath)
                except OSError:
                    pass

        return k8s_tag

    def launch_flow_run(
        self,
        flow_name: str,
        parameters: dict[str, Any] | str | None = None,
        pip_requirements: list[str] | str | None = None,
        env_vars: dict[str, str] | str | None = None,
        secret_refs: list[str] | str | None = None,
        image: str | None = None,
        user_id: int | None = None,
        trigger_type: str = "manual",
        app: Any | None = None,
        wait_for_watcher: bool = False,
        triggered_by: str | None = None,
        poll_interval: float | None = None,
        max_wait_seconds: float | None = None,
        workers: int = 1,
        pods_per_worker: int = 1,
        **kwargs: Any,
    ) -> Execution:
        """Create a unique Execution record, submit a Kubernetes Job, and start log watching.

        *workers* controls how many physical nodes the ExternalWorkerProvider
        should provision.  *pods_per_worker* is multiplied with *workers* to
        set the Job's ``completions`` / ``parallelism`` for Indexed mode.
        """
        total_pods = max(1, workers) * max(1, pods_per_worker)
        flow_data = self.read_flow(flow_name)  # type: ignore[attr-defined]
        if flow_data is None:
            raise ValueError(f"Flow '{flow_name}' does not exist.")

        merged_params: dict[str, Any] = dict(flow_data.get("parameters") or {})
        if parameters is not None:
            override_params = self.parse_flow_parameters(parameters)  # type: ignore[attr-defined]
            if override_params or isinstance(parameters, dict):
                merged_params.update(override_params)

        if pip_requirements is not None and str(pip_requirements).strip() != "":
            resolved_reqs: list[str] = self.parse_pip_requirements(pip_requirements)  # type: ignore[attr-defined]
        else:
            resolved_reqs = list(flow_data.get("pip_requirements") or [])

        if secret_refs is not None and str(secret_refs).strip() != "":
            resolved_secret_refs: list[str] = self.parse_secret_refs(secret_refs)  # type: ignore[attr-defined]
        else:
            resolved_secret_refs = list(flow_data.get("secret_refs") or [])

        parsed_env: dict[str, str] = self.parse_env_vars(env_vars)  # type: ignore[attr-defined]
        default_img = os.environ.get("K8S_DEFAULT_IMAGE", "python:3.11-slim")
        resolved_image = (image or "").strip() or str(flow_data.get("image") or default_img)
        namespace = self._k8s_namespace or os.environ.get("K8S_NAMESPACE", "default")
        ttl_seconds = int(os.environ.get("K8S_JOB_TTL_SECONDS", 300))

        # Store only secret KEYS in inputs_json — never store secret values in plaintext
        safe_inputs_metadata: dict[str, Any] = {
            "parameters": merged_params,
            "pip_requirements": resolved_reqs,
            "image": resolved_image,
            "secret_keys": sorted(parsed_env.keys()),
            "secret_refs": resolved_secret_refs,
            "trigger_type": trigger_type,
            "workers": workers,
            "pods_per_worker": pods_per_worker,
            "total_pods": total_pods,
        }
        if triggered_by:
            safe_inputs_metadata["triggered_by"] = triggered_by

        exe = Execution(
            analysis_name=flow_data["name"],
            user_id=user_id,
            status="running",
            namespace=namespace,
            trigger_type=trigger_type,
            inputs_json=json.dumps(safe_inputs_metadata),
            log_text=f"[ProjectCompass] Submitting Kubernetes Job for flow '{flow_data['name']}'...\n",
        )
        db.session.add(exe)
        db.session.commit()

        run_id = int(exe.id)
        job_name = f"pc-flow-job-{run_id}"
        cm_name = f"pc-flow-cfg-{run_id}"
        sec_name = f"pc-flow-sec-{run_id}" if parsed_env else None

        exe.job_name = job_name
        db.session.commit()

        # --- Detect Dockerfile-based flow ---
        analyses_base = (
            getattr(self, "save_folder_path", "")
            or os.path.join(self.data_dir or self.dir_path or "", "Analyses")
        )
        analysis_dir = os.path.join(analyses_base, flow_data["name"])
        dockerfile_path = os.path.join(analysis_dir, "Dockerfile")
        use_dockerfile = os.path.isfile(dockerfile_path)

        if use_dockerfile:
            # Dockerfile mode: build image, no ConfigMap
            try:
                exe.log_text = f"[ProjectCompass] Building Docker image for '{flow_data['name']}'...\n"
                db.session.commit()

                if self._should_manage_workers() and self._count_ready_workers() < workers:
                    self.worker_provider.reset_tracking()
                    self.worker_provider.ensure_workers(workers, email=triggered_by or "")

                built_image = self._build_and_push_image(flow_data["name"], analysis_dir, run_id)
                job_manifest = self.build_job_manifest(
                    run_id=run_id,
                    flow_name=flow_data["name"],
                    image=built_image,
                    parameters=merged_params,
                    has_secret=bool(parsed_env),
                    namespace=namespace,
                    ttl_seconds=ttl_seconds,
                    secret_refs=resolved_secret_refs,
                    dockerfile_mode=True,
                    total_pods=total_pods,
                    workers=workers,
                    pods_per_worker=pods_per_worker,
                )
                if parsed_env:
                    sec_manifest = self.build_secret_manifest(
                        run_id=run_id, flow_name=flow_data["name"],
                        env_vars=parsed_env, namespace=namespace,
                    )
                    self._k8s_post(f"/api/v1/namespaces/{namespace}/secrets", sec_manifest)

                self._k8s_post(f"/apis/batch/v1/namespaces/{namespace}/jobs", job_manifest)
                exe.log_text = (
                    f"[ProjectCompass] Built image '{built_image}'.\n"
                    f"[ProjectCompass] Submitted Kubernetes Job '{job_name}'.\n"
                )
                db.session.commit()
            except (K8sClientError, WorkerProviderError) as exc:
                if parsed_env:
                    self._cleanup_k8s_resource(f"/api/v1/namespaces/{namespace}/secrets/pc-flow-sec-{run_id}")
                exe.status = "failed"
                exe.finished_at = datetime.utcnow()
                exe.error_message = str(exc)
                exe.log_text = (exe.log_text or "") + f"[ProjectCompass] ERROR: {exc}\n"
                db.session.commit()
                return exe
        else:
            # Legacy ConfigMap mode
            skipped_data_warnings: list[str] = []
            cm_manifest = self.build_configmap_manifest(
                run_id=run_id,
                flow_name=flow_data["name"],
                code=flow_data["code"],
                parameters=merged_params,
                pip_requirements=resolved_reqs,
                namespace=namespace,
                skipped_warnings=skipped_data_warnings,
            )
            warning_log = "".join(f"{warning}\n" for warning in skipped_data_warnings)
            job_manifest = self.build_job_manifest(
                run_id=run_id,
                flow_name=flow_data["name"],
                image=resolved_image,
                parameters=merged_params,
                has_secret=bool(parsed_env),
                namespace=namespace,
                ttl_seconds=ttl_seconds,
                secret_refs=resolved_secret_refs,
                total_pods=total_pods,
                workers=workers,
                pods_per_worker=pods_per_worker,
            )

            created_cm = False
            created_secret = False
            try:
                if self._should_manage_workers() and self._count_ready_workers() < workers:
                    self.worker_provider.reset_tracking()
                    self.worker_provider.ensure_workers(workers, email=triggered_by or "")

                self._k8s_post(f"/api/v1/namespaces/{namespace}/configmaps", cm_manifest)
                created_cm = True
                if parsed_env:
                    sec_manifest = self.build_secret_manifest(
                        run_id=run_id,
                        flow_name=flow_data["name"],
                        env_vars=parsed_env,
                        namespace=namespace,
                    )
                    self._k8s_post(f"/api/v1/namespaces/{namespace}/secrets", sec_manifest)
                    created_secret = True

                self._k8s_post(f"/apis/batch/v1/namespaces/{namespace}/jobs", job_manifest)
                exe.log_text = warning_log + (
                    f"[ProjectCompass] Submitted Kubernetes Job '{job_name}' (image: {resolved_image}).\n"
                )
                db.session.commit()
            except WorkerProviderError as exc:
                exe.status = "failed"
                exe.finished_at = datetime.utcnow()
                exe.error_message = str(exc)
                exe.log_text = warning_log + f"[ProjectCompass] ERROR provisioning worker: {exc}\n"
                db.session.commit()
                return exe
            except K8sClientError as exc:
                if created_secret and sec_name:
                    self._cleanup_k8s_resource(f"/api/v1/namespaces/{namespace}/secrets/{sec_name}")
                if created_cm:
                    self._cleanup_k8s_resource(f"/api/v1/namespaces/{namespace}/configmaps/{cm_name}")

                exe.status = "failed"
                exe.finished_at = datetime.utcnow()
                exe.error_message = str(exc)
                exe.log_text = warning_log + (exe.log_text or "") + (
                    f"[ProjectCompass] ERROR launching Kubernetes Job: {exc}\n"
                )
                db.session.commit()
                return exe

        flask_app = app
        if flask_app is None:
            from flask import current_app
            try:
                flask_app = current_app._get_current_object()  # type: ignore[attr-defined]
            except RuntimeError:
                flask_app = None

        is_in_memory_db = bool(
            flask_app is not None
            and ":memory:" in str(flask_app.config.get("SQLALCHEMY_DATABASE_URI", ""))
        )

        if wait_for_watcher or is_in_memory_db:
            self._watch_k8s_job(
                app=flask_app,
                run_id=run_id,
                namespace=namespace,
                job_name=job_name,
                cm_name=cm_name,
                secret_name=sec_name,
                poll_interval=poll_interval,
                max_wait_seconds=max_wait_seconds,
                stop_if_still_running=bool(not wait_for_watcher and is_in_memory_db),
            )
            db.session.refresh(exe)
        else:
            watcher_thread = threading.Thread(
                target=self._watch_k8s_job,
                kwargs={
                    "app": flask_app,
                    "run_id": run_id,
                    "namespace": namespace,
                    "job_name": job_name,
                    "cm_name": cm_name,
                    "secret_name": sec_name,
                    "poll_interval": poll_interval,
                    "max_wait_seconds": max_wait_seconds,
                },
                daemon=True,
                name=f"k8s-watcher-run-{run_id}",
            )
            self._active_watchers[run_id] = watcher_thread
            watcher_thread.start()

        return exe

    def _cleanup_k8s_resource(self, path: str, params: dict[str, Any] | None = None) -> None:
        """Delete a temporary Kubernetes resource (Secret/ConfigMap/Job) ignoring 404 errors."""
        try:
            self._k8s_delete(path, params=params)
        except K8sClientError as exc:
            logger.debug(f"Cleanup of Kubernetes resource {path} skipped or failed: {exc}")

    def _download_s3_artifacts(
        self,
        flow_name: str,
        run_id: int,
        run_timestamp: str | None = None,
    ) -> list[str]:
        """Download output artifacts from MinIO/S3 into Analyses/<flow>/physical_output/."""
        endpoint = os.environ.get("PC_S3_ENDPOINT", "").strip()
        access_key = os.environ.get("PC_S3_ACCESS_KEY", "").strip()
        secret_key = os.environ.get("PC_S3_SECRET_KEY", "").strip()
        bucket = os.environ.get("PC_S3_BUCKET", "pc-artifacts").strip()
        if not endpoint or not access_key:
            return []

        try:
            import boto3
            from botocore.config import Config as BotoConfig
        except ImportError:
            logger.warning("boto3 not installed — cannot download S3 artifacts")
            return []

        s3 = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            config=BotoConfig(signature_version="s3v4"),
            region_name="us-east-1",
        )

        prefix = f"{run_id}/"
        try:
            response = s3.list_objects_v2(Bucket=bucket, Prefix=prefix)
        except Exception as exc:
            logger.warning(f"Failed to list S3 artifacts for run {run_id}: {exc}")
            return []

        base_analyses_dir = (
            getattr(self, "save_folder_path", "")
            or os.path.join(self.data_dir or self.dir_path or "", "Analyses")
        )
        phys_dir = os.path.join(base_analyses_dir, flow_name, "physical_output")
        main_dir = os.path.join(phys_dir, "main")
        os.makedirs(main_dir, exist_ok=True)
        ts = run_timestamp or datetime.utcnow().strftime("%Y%m%d_%H%M%S")

        downloaded: list[str] = []
        for obj in response.get("Contents", []):
            s3_key = obj["Key"]
            filename = s3_key[len(prefix):]
            if not filename or filename.startswith("."):
                continue

            local_main = os.path.join(main_dir, os.path.basename(filename))
            try:
                os.makedirs(os.path.dirname(local_main), exist_ok=True)
                s3.download_file(bucket, s3_key, local_main)
                downloaded.append(os.path.basename(filename))

                stem, ext = os.path.splitext(os.path.basename(filename))
                versioned = os.path.join(phys_dir, f"{ts}_{stem}{ext}")
                s3.download_file(bucket, s3_key, versioned)
            except Exception as exc:
                logger.warning(f"Failed to download {s3_key}: {exc}")

        return downloaded

    def _extract_and_persist_artifacts(
        self,
        flow_name: str,
        raw_logs: str,
        persisted_files: set[str] | None = None,
        run_timestamp: str | None = None,
    ) -> str:
        """Decode base64 artifact frames from Pod stdout, persist to physical_output/, and return clean logs."""
        if not raw_logs:
            return ""

        seen_files = persisted_files if persisted_files is not None else set()
        ts = run_timestamp or datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        base_analyses_dir = (
            getattr(self, "save_folder_path", "")
            or os.path.join(self.data_dir or self.dir_path or "", "Analyses")
        )
        phys_dir = os.path.join(base_analyses_dir, flow_name, "physical_output")
        main_dir = os.path.join(phys_dir, "main")

        used_exts_in_batch: set[str] = set()
        for existing_f in seen_files:
            _, existing_ext = os.path.splitext(existing_f)
            if existing_ext:
                used_exts_in_batch.add(existing_ext.lower())

        for match in self.ARTIFACT_BLOCK_RE.finditer(raw_logs):
            raw_fname = match.group(1).strip()
            b64_payload = re.sub(r"\s+", "", match.group(2) or "")
            filename = os.path.basename(raw_fname)
            if not filename or filename in (".", "..") or filename in seen_files:
                continue

            try:
                file_bytes = base64.b64decode(b64_payload) if b64_payload else b""
            except Exception as exc:
                logger.warning(f"Failed decoding artifact '{filename}' for flow '{flow_name}': {exc}")
                continue

            try:
                os.makedirs(main_dir, exist_ok=True)
                main_path = os.path.join(main_dir, filename)
                with open(main_path, "wb") as f_main:
                    f_main.write(file_bytes)

                stem, ext = os.path.splitext(filename)
                ext_lower = ext.lower()
                if ext_lower and ext_lower not in used_exts_in_batch:
                    versioned_name = f"{ts}{ext}"
                    used_exts_in_batch.add(ext_lower)
                else:
                    versioned_name = f"{ts}_{stem}{ext}"

                versioned_path = os.path.join(phys_dir, versioned_name)
                with open(versioned_path, "wb") as f_ver:
                    f_ver.write(file_bytes)

                seen_files.add(filename)
            except OSError as exc:
                logger.warning(f"Failed writing artifact '{filename}' for flow '{flow_name}': {exc}")

        cleaned = self.ARTIFACT_BLOCK_RE.sub("", raw_logs)
        cleaned = self.INCOMPLETE_ARTIFACT_RE.sub("", cleaned)
        return cleaned

    def _watch_k8s_job(
        self,
        app: Any | None,
        run_id: int,
        namespace: str,
        job_name: str,
        cm_name: str,
        secret_name: str | None,
        poll_interval: float | None = None,
        max_wait_seconds: float | None = None,
        stop_if_still_running: bool = False,
    ) -> None:
        """Background worker that tails Pod stdout/stderr into Execution.log_text and updates status."""
        from flask import has_app_context

        if has_app_context() or app is None:
            self._watch_k8s_job_in_context(
                run_id=run_id,
                namespace=namespace,
                job_name=job_name,
                cm_name=cm_name,
                secret_name=secret_name,
                poll_interval=poll_interval,
                max_wait_seconds=max_wait_seconds,
                stop_if_still_running=stop_if_still_running,
            )
        else:
            with app.app_context():
                self._watch_k8s_job_in_context(
                    run_id=run_id,
                    namespace=namespace,
                    job_name=job_name,
                    cm_name=cm_name,
                    secret_name=secret_name,
                    poll_interval=poll_interval,
                    max_wait_seconds=max_wait_seconds,
                    stop_if_still_running=stop_if_still_running,
                )

    def _watch_k8s_job_in_context(
        self,
        run_id: int,
        namespace: str,
        job_name: str,
        cm_name: str,
        secret_name: str | None,
        poll_interval: float | None = None,
        max_wait_seconds: float | None = None,
        stop_if_still_running: bool = False,
    ) -> None:
        """Execute Pod log polling and status synchronization inside an active Flask app context."""
        initial_execution = db.session.get(Execution, run_id)
        warning_lines = "".join(
            f"{line}\n"
            for line in (initial_execution.log_text or "").splitlines()
            if line.startswith("[ProjectCompass] WARNING")
        ) if initial_execution is not None else ""
        header_line = warning_lines + f"[ProjectCompass] Submitted Kubernetes Job '{job_name}'.\n"
        captured_pod_logs = ""
        last_raw_logs: str | None = None
        pod_name: str | None = None
        assigned_node: str | None = None
        persisted_artifacts: set[str] = set()
        run_timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        effective_poll = (
            float(poll_interval)
            if poll_interval is not None and poll_interval > 0
            else self._watcher_poll_interval
        )
        max_polls = 3 if stop_if_still_running else self._watcher_max_polls
        if max_wait_seconds is not None and max_wait_seconds > 0 and effective_poll > 0 and not stop_if_still_running:
            max_polls = max(1, min(max_polls, int(max_wait_seconds / effective_poll) + 1))

        should_cleanup = True
        try:
            for poll_idx in range(max_polls):
                exe = db.session.get(Execution, run_id)
                if exe is None or exe.status == "aborted":
                    return

                try:
                    pods_resp = self._k8s_get(
                        f"/api/v1/namespaces/{namespace}/pods",
                        params={"labelSelector": f"job-name={job_name}"},
                    )
                except K8sClientError as exc:
                    exe.status = "failed"
                    exe.finished_at = datetime.utcnow()
                    exe.error_message = str(exc)
                    exe.log_text = (exe.log_text or header_line) + f"\n[ProjectCompass] K8s API error: {exc}\n"
                    db.session.commit()
                    return

                pod_items = pods_resp.get("items") or []
                pod: dict[str, Any] | None = pod_items[0] if pod_items else None
                pod_phase = ""
                exit_code: int | None = None
                term_error: str | None = None

                # --- Multi-pod support for indexed Jobs ---
                all_pods_logs: list[str] = []
                any_pod_running = False
                any_pod_failed = False
                worst_exit_code: int | None = None

                for p_item in pod_items:
                    p_meta = p_item.get("metadata", {})
                    p_name = str(p_meta.get("name", ""))
                    p_labels = p_meta.get("labels", {})
                    p_index = p_labels.get("batch.kubernetes.io/job-completion-index", "")
                    p_status_obj = p_item.get("status") or {}
                    p_phase = str(p_status_obj.get("phase", ""))
                    p_node = p_item.get("spec", {}).get("nodeName")

                    if p_phase in ("Running", "Succeeded", "Failed"):
                        any_pod_running = any_pod_running or (p_phase == "Running")
                        if p_phase == "Failed":
                            any_pod_failed = True

                    # Track container exit code
                    p_cstatuses = p_status_obj.get("containerStatuses") or []
                    if p_cstatuses:
                        p_state = p_cstatuses[0].get("state") or {}
                        p_term = p_state.get("terminated")
                        if isinstance(p_term, dict) and "exitCode" in p_term:
                            p_exit = int(p_term["exitCode"])
                            if p_exit != 0 and worst_exit_code is None:
                                worst_exit_code = p_exit
                                reason = p_term.get("reason") or ""
                                msg = p_term.get("message") or ""
                                term_error = f"{reason}: {msg}".strip(": ") or f"Container exited with code {p_exit}"

                    # Read logs for this pod
                    if p_name and p_phase in ("Running", "Succeeded", "Failed"):
                        try:
                            p_raw = self._k8s_get_text(
                                f"/api/v1/namespaces/{namespace}/pods/{p_name}/log"
                            )
                            prefix = f"[pod-{p_index}] " if len(pod_items) > 1 and p_index else ""
                            if p_raw:
                                prefixed_lines = "".join(
                                    f"{prefix}{line}\n"
                                    for line in p_raw.splitlines()
                                )
                                all_pods_logs.append(prefixed_lines)
                        except K8sClientError:
                            pass

                # Use first pod for backward-compatible fields
                if pod is not None:
                    pod_name = str(pod.get("metadata", {}).get("name", "")) or pod_name
                    spec_node = pod.get("spec", {}).get("nodeName")
                    if spec_node and spec_node != assigned_node:
                        assigned_node = str(spec_node)
                        exe.node_name = assigned_node
                        db.session.commit()

                    pod_status = pod.get("status") or {}
                    pod_phase = str(pod_status.get("phase", ""))
                    container_statuses = pod_status.get("containerStatuses") or []
                    if container_statuses:
                        state = container_statuses[0].get("state") or {}
                        terminated = state.get("terminated")
                        if isinstance(terminated, dict):
                            if "exitCode" in terminated:
                                exit_code = int(terminated["exitCode"])
                            if exit_code not in (None, 0) and not term_error:
                                reason = terminated.get("reason") or ""
                                msg = terminated.get("message") or ""
                                term_error = f"{reason}: {msg}".strip(": ") or f"Container exited with code {exit_code}"

                if worst_exit_code is not None:
                    exit_code = worst_exit_code

                # Aggregate logs from all pods
                aggregated_raw = "".join(all_pods_logs)
                if aggregated_raw and aggregated_raw != last_raw_logs:
                    last_raw_logs = aggregated_raw
                    captured_pod_logs = self._extract_and_persist_artifacts(
                        flow_name=exe.analysis_name,
                        raw_logs=aggregated_raw,
                        persisted_files=persisted_artifacts,
                        run_timestamp=run_timestamp,
                    )
                    if persisted_artifacts:
                        base_analyses_dir = (
                            getattr(self, "save_folder_path", "")
                            or os.path.join(self.data_dir or self.dir_path or "", "Analyses")
                        )
                        main_out_dir = os.path.join(
                            base_analyses_dir,
                            exe.analysis_name,
                            "physical_output",
                            "main",
                        )
                        preferred = (
                            "output.csv"
                            if "output.csv" in persisted_artifacts
                            else sorted(persisted_artifacts)[0]
                        )
                        exe.output_path = os.path.join(main_out_dir, preferred)
                        exe.outputs_json = json.dumps(sorted(persisted_artifacts))
                    node_banner = (
                        f"[ProjectCompass] Running on {len(pod_items)} pod(s)"
                        + (f", worker node '{assigned_node}'" if assigned_node else "")
                        + ".\n"
                    ) if pod_items else ""
                    exe.log_text = header_line + node_banner + captured_pod_logs
                    db.session.commit()

                job_succeeded = False
                job_failed = False
                job_fail_msg: str | None = None
                try:
                    job_obj = self._k8s_get(f"/apis/batch/v1/namespaces/{namespace}/jobs/{job_name}")
                    job_status = job_obj.get("status") or {}
                    job_completions = int(job_obj.get("spec", {}).get("completions", 1) or 1)
                    if int(job_status.get("succeeded", 0) or 0) >= job_completions:
                        job_succeeded = True
                    if int(job_status.get("failed", 0) or 0) >= 1:
                        job_failed = True
                    for cond in job_status.get("conditions") or []:
                        if cond.get("type") == "Failed" and cond.get("status") == "True":
                            job_failed = True
                            job_fail_msg = cond.get("message") or cond.get("reason")
                        elif cond.get("type") == "Complete" and cond.get("status") == "True":
                            job_succeeded = True
                except K8sClientError:
                    pass

                if (job_succeeded or job_failed) and pod_items and last_raw_logs is None:
                    # Final attempt to read aggregated logs from all pods
                    final_logs_parts: list[str] = []
                    for p_item in pod_items:
                        p_name = str(p_item.get("metadata", {}).get("name", ""))
                        p_index = p_item.get("metadata", {}).get("labels", {}).get(
                            "batch.kubernetes.io/job-completion-index", ""
                        )
                        if not p_name:
                            continue
                        try:
                            p_raw = self._k8s_get_text(
                                f"/api/v1/namespaces/{namespace}/pods/{p_name}/log"
                            )
                            prefix = f"[pod-{p_index}] " if len(pod_items) > 1 and p_index else ""
                            if p_raw:
                                final_logs_parts.append(
                                    "".join(f"{prefix}{line}\n" for line in p_raw.splitlines())
                                )
                        except K8sClientError:
                            pass
                    if final_logs_parts:
                        last_raw_logs = "".join(final_logs_parts)
                        captured_pod_logs = self._extract_and_persist_artifacts(
                            flow_name=exe.analysis_name,
                            raw_logs=last_raw_logs,
                            persisted_files=persisted_artifacts,
                            run_timestamp=run_timestamp,
                        )
                        if persisted_artifacts:
                            base_analyses_dir = (
                                getattr(self, "save_folder_path", "")
                                or os.path.join(self.data_dir or self.dir_path or "", "Analyses")
                            )
                            main_out_dir = os.path.join(
                                base_analyses_dir,
                                exe.analysis_name,
                                "physical_output",
                                "main",
                            )
                            preferred = (
                                "output.csv"
                                if "output.csv" in persisted_artifacts
                                else sorted(persisted_artifacts)[0]
                            )
                            exe.output_path = os.path.join(main_out_dir, preferred)
                            exe.outputs_json = json.dumps(sorted(persisted_artifacts))

                if pod_phase == "Succeeded" or job_succeeded:
                    # For indexed jobs, wait for ALL pods — only trust job_succeeded
                    if not job_succeeded and job_completions > 1:
                        time.sleep(effective_poll)
                        continue
                    exe = db.session.get(Execution, run_id)
                    if exe and exe.status != "aborted":
                        node_banner = (
                            f"[ProjectCompass] Running on worker node '{assigned_node}' (Pod '{pod_name}').\n"
                            if assigned_node
                            else ""
                        )
                        # Download artifacts from S3 if available
                        s3_files = self._download_s3_artifacts(
                            exe.analysis_name, run_id, run_timestamp,
                        )
                        if s3_files:
                            base_analyses_dir = (
                                getattr(self, "save_folder_path", "")
                                or os.path.join(self.data_dir or self.dir_path or "", "Analyses")
                            )
                            main_out_dir = os.path.join(
                                base_analyses_dir, exe.analysis_name, "physical_output", "main",
                            )
                            preferred = "output.csv" if "output.csv" in s3_files else sorted(s3_files)[0]
                            exe.output_path = os.path.join(main_out_dir, preferred)
                            exe.outputs_json = json.dumps(sorted(s3_files))
                            captured_pod_logs += f"[ProjectCompass] Downloaded {len(s3_files)} artifact(s) from S3.\n"
                        exe.status = "success"
                        exe.exit_code = 0 if exit_code is None else exit_code
                        exe.finished_at = datetime.utcnow()
                        exe.log_text = header_line + node_banner + captured_pod_logs
                        db.session.commit()
                        fire_webhooks(
                            exe.analysis_name,
                            {"run_id": exe.id, "analysis": exe.analysis_name, "status": "success"},
                        )
                    return

                if pod_phase == "Failed" or job_failed:
                    exe = db.session.get(Execution, run_id)
                    if exe and exe.status != "aborted":
                        node_banner = (
                            f"[ProjectCompass] Running on worker node '{assigned_node}' (Pod '{pod_name}').\n"
                            if assigned_node
                            else ""
                        )
                        resolved_err = term_error or job_fail_msg or "Flow script exited with non-zero status"
                        exe.status = "failed"
                        exe.exit_code = exit_code if exit_code is not None else 1
                        exe.error_message = resolved_err
                        exe.finished_at = datetime.utcnow()
                        exe.log_text = (
                            header_line
                            + node_banner
                            + captured_pod_logs
                            + ("" if captured_pod_logs.endswith("\n") or not captured_pod_logs else "\n")
                            + f"[ProjectCompass] Run failed ({resolved_err}).\n"
                        )
                        db.session.commit()
                        fire_webhooks(
                            exe.analysis_name,
                            {
                                "run_id": exe.id,
                                "analysis": exe.analysis_name,
                                "status": "failed",
                                "error": resolved_err,
                            },
                        )
                    return

                if stop_if_still_running and poll_idx + 1 >= max_polls:
                    should_cleanup = False
                    return

                time.sleep(effective_poll)
        finally:
            if should_cleanup:
                if secret_name:
                    self._cleanup_k8s_resource(f"/api/v1/namespaces/{namespace}/secrets/{secret_name}")
                self._cleanup_k8s_resource(f"/api/v1/namespaces/{namespace}/configmaps/{cm_name}")
                self._active_watchers.pop(run_id, None)
                self._release_workers_if_idle(run_id)

    def _release_workers_if_idle(self, finished_run_id: int) -> None:
        """Release worker nodes when auto_cleanup is enabled and no other Jobs are running."""
        if not self._should_manage_workers():
            return
        if not getattr(self.worker_provider, "auto_cleanup", False):
            return
        try:
            active_runs = Execution.query.filter(
                Execution.status == "running",
                Execution.id != finished_run_id,
            ).count()
            if active_runs == 0:
                self.worker_provider.release_workers()
        except Exception as exc:
            logger.warning(f"Failed releasing idle workers after run {finished_run_id}: {exc}")

    def abort_flow_run(self, run_id: int) -> Execution | None:
        """Abort an active Kubernetes Job run and persist the aborted status."""
        exe = db.session.get(Execution, run_id)
        if exe is None:
            return None
        if exe.status == "running":
            ns = exe.namespace or self._k8s_namespace or "default"
            if exe.job_name:
                self._cleanup_k8s_resource(
                    f"/apis/batch/v1/namespaces/{ns}/jobs/{exe.job_name}",
                    params={"propagationPolicy": "Background"},
                )
            self._cleanup_k8s_resource(f"/api/v1/namespaces/{ns}/secrets/pc-flow-sec-{run_id}")
            self._cleanup_k8s_resource(f"/api/v1/namespaces/{ns}/configmaps/pc-flow-cfg-{run_id}")
            exe.status = "aborted"
            exe.finished_at = datetime.utcnow()
            exe.error_message = "Aborted by user"
            exe.log_text = (exe.log_text or "") + "\n[ProjectCompass] Run aborted by user.\n"
            db.session.commit()
        return exe

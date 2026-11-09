"""
░██╗░░░░░░░██╗░█████╗░██████╗░██╗░░██╗███████╗██████╗░██████╗░██████╗░░█████╗░██╗░░░██╗██╗██████╗░███████╗██████╗░
░██║░░██╗░░██║██╔══██╗██╔══██╗██║░██╔╝██╔════╝██╔══██╗██╔══██╗██╔══██╗██╔══██╗██║░░░██║██║██╔══██╗██╔════╝██╔══██╗
░╚██╗████╗██╔╝██║░░██║██████╔╝█████═╝░█████╗░░██████╔╝██████╔╝██████╔╝██║░░██║╚██╗░██╔╝██║██║░░██║█████╗░░██████╔╝
░░████╔═████║░██║░░██║██╔══██╗██╔═██╗░██╔══╝░░██╔══██╗██╔═══╝░██╔══██╗██║░░██║░╚████╔╝░██║██║░░██║██╔══╝░░██╔══██╗
░░╚██╔╝░╚██╔╝░╚█████╔╝██║░░██║██║░╚██╗███████╗██║░░██║██║░░░░░██║░░██║╚█████╔╝░░╚██╔╝░░██║██████╔╝███████╗██║░░██║
░░░╚═╝░░░╚═╝░░░╚════╝░╚═╝░░╚═╝╚═╝░░╚═╝╚══════╝╚═╝░░╚═╝╚═╝░░░░░╚═╝░░╚═╝░╚════╝░░░░╚═╝░░░╚═╝╚═════╝░╚══════╝╚═╝░░╚═╝
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from logging_config import logger

if TYPE_CHECKING:
    from utils.app_settings import DockerWorkerSettings, ExternalWorkerSettings, WorkerSettings


class WorkerProviderError(Exception):
    """Represent a base error in worker node lifecycle management."""


class WorkerProvisioningError(WorkerProviderError):
    """Raise when provisioning or waiting for worker nodes fails."""


class WorkerReleaseError(WorkerProviderError):
    """Raise when releasing or terminating worker nodes fails."""


class WorkerProvider(ABC):
    """Manage worker node lifecycle for the k0s cluster in a cloud-agnostic manner."""

    def __init__(self, auto_cleanup: bool = True) -> None:
        """Initialize shared worker provider state."""
        self._auto_cleanup: bool = bool(auto_cleanup)
        self._managed_nodes: list[str] = []

    @property
    def auto_cleanup(self) -> bool:
        """Return whether idle worker nodes should be automatically released."""
        return self._auto_cleanup

    @auto_cleanup.setter
    def auto_cleanup(self, value: bool) -> None:
        """Update whether idle worker nodes should be automatically released."""
        self._auto_cleanup = bool(value)

    @property
    def managed_nodes(self) -> list[str]:
        """Return a copy of the currently tracked worker node names."""
        return list(self._managed_nodes)

    def reset_tracking(self) -> None:
        """Forget locally tracked worker names without affecting live resources."""
        self._managed_nodes.clear()

    @abstractmethod
    def ensure_workers(self, count: int = 1, **kwargs: Any) -> list[str]:
        """Ensure at least `count` workers are available and Ready. Returns node names."""

    @abstractmethod
    def release_workers(self, node_names: list[str] | None = None) -> None:
        """Release/terminate worker nodes. None = release all managed workers."""

    @abstractmethod
    def status(self) -> dict[str, Any]:
        """Return current worker status: nodes, capacity, health, provider type."""

    @classmethod
    def from_settings(
        cls,
        settings: WorkerSettings | None = None,
        k8s_nodes_callback: Callable[[], dict[str, Any] | list[dict[str, Any]]] | None = None,
        k8s_delete_node_callback: Callable[[str], Any] | None = None,
    ) -> WorkerProvider:
        """Instantiate the configured WorkerProvider implementation from WorkerSettings."""
        if settings is not None and settings.provider == "external":
            ext = settings.external
            return ExternalWorkerProvider(
                ensure_script=ext.ensure_script,
                release_script=ext.release_script,
                status_script=ext.status_script,
                auto_cleanup=settings.auto_cleanup,
                settings=ext,
            )

        docker_cfg = settings.docker if settings is not None else None
        return DockerWorkerProvider(
            settings=docker_cfg,
            auto_cleanup=settings.auto_cleanup if settings is not None else None,
            k8s_nodes_callback=k8s_nodes_callback,
            k8s_delete_node_callback=k8s_delete_node_callback,
        )


class DockerWorkerProvider(WorkerProvider):
    """Provision and clean up local k0s worker containers using the Docker CLI."""

    MANAGED_BY_LABEL: str = "app.kubernetes.io/managed-by=projectcompass"
    DEFAULT_IMAGE: str = "docker.io/k0sproject/k0s:latest"
    DEFAULT_CPUS: str = "2"
    DEFAULT_MEMORY: str = "4g"
    DEFAULT_NETWORK: str = "bridge"
    DEFAULT_READY_TIMEOUT: float = 120.0

    def __init__(
        self,
        image: str | None = None,
        cpus: str | None = None,
        memory: str | None = None,
        auto_cleanup: bool | None = None,
        settings: DockerWorkerSettings | None = None,
        k8s_nodes_callback: Callable[[], dict[str, Any] | list[dict[str, Any]]] | None = None,
        k8s_delete_node_callback: Callable[[str], Any] | None = None,
        join_token: str | None = None,
        join_token_file: str | None = None,
        controller_container: str | None = None,
        ready_timeout: float | None = None,
        poll_interval: float = 0.05,
        network: str | None = None,
        container_prefix: str = "pc-k0s-worker",
    ) -> None:
        """Configure Docker-based k0s worker container provisioning."""
        resolved_auto_cleanup = (
            auto_cleanup
            if auto_cleanup is not None
            else (settings.auto_cleanup if settings is not None else True)
        )
        super().__init__(auto_cleanup=resolved_auto_cleanup)

        self._image: str = (
            image
            if image is not None
            else (settings.image if settings is not None else self.DEFAULT_IMAGE)
        )
        self._cpus: str = (
            str(cpus)
            if cpus is not None
            else (str(settings.cpus) if settings is not None else self.DEFAULT_CPUS)
        )
        self._memory: str = (
            memory
            if memory is not None
            else (settings.memory if settings is not None else self.DEFAULT_MEMORY)
        )
        self._k8s_nodes_callback = k8s_nodes_callback
        self._k8s_delete_node_callback = k8s_delete_node_callback
        self._join_token: str | None = join_token
        self._join_token_file: str | None = join_token_file or (
            settings.join_token_file if settings is not None else None
        )
        self._controller_container: str | None = controller_container or (
            settings.controller_container if settings is not None else None
        )
        self._ready_timeout: float = float(
            ready_timeout
            if ready_timeout is not None
            else (settings.ready_timeout_seconds if settings is not None else self.DEFAULT_READY_TIMEOUT)
        )
        self._poll_interval: float = float(poll_interval)
        self._network: str = network or (settings.network if settings is not None else self.DEFAULT_NETWORK)
        self._container_prefix: str = container_prefix
        self._spawn_counter: int = 0
        self._spawned_containers: list[str] = []

    @property
    def network(self) -> str:
        """Return the configured Docker network mode."""
        return self._network

    @property
    def ready_timeout(self) -> float:
        """Return the worker readiness timeout in seconds."""
        return self._ready_timeout

    def reset_tracking(self) -> None:
        """Forget locally tracked workers without stopping their containers."""
        super().reset_tracking()
        self._spawned_containers.clear()

    @property
    def image(self) -> str:
        """Return the configured k0s worker container image."""
        return self._image

    @property
    def cpus(self) -> str:
        """Return the configured CPU limit per worker container."""
        return self._cpus

    @property
    def memory(self) -> str:
        """Return the configured memory limit per worker container."""
        return self._memory

    @staticmethod
    def _is_node_ready(node_item: dict[str, Any]) -> bool:
        """Return True if a Kubernetes Node object reports Condition Ready=True."""
        if str(node_item.get("status", "")).strip() == "Ready":
            return True
        conditions = (node_item.get("status") or {}).get("conditions") or []
        for cond in conditions:
            if isinstance(cond, dict) and cond.get("type") == "Ready":
                return str(cond.get("status", "")).strip() == "True"
        return False

    @staticmethod
    def _is_worker_node(node_item: dict[str, Any]) -> bool:
        """Return True if a Kubernetes Node is a worker rather than a dedicated control-plane node."""
        metadata = node_item.get("metadata") or {}
        name = str(metadata.get("name", "")).strip().lower()
        labels = metadata.get("labels") or {}
        if not isinstance(labels, dict):
            return True

        roles: list[str] = []
        for key, val in labels.items():
            if key.startswith("node-role.kubernetes.io/"):
                role_name = key.split("/", 1)[1].strip().lower()
                if role_name:
                    roles.append(role_name)
            elif key in ("kubernetes.io/role", "node.k0sproject.io/role") and val:
                roles.append(str(val).strip().lower())

        if not roles or "worker" in roles or "worker" in name:
            return True
        return not any(r in ("control-plane", "master") for r in roles)

    @classmethod
    def extract_ready_worker_names(cls, payload: dict[str, Any] | list[ Any] | None) -> list[str]:
        """Extract Ready worker node names from a `/api/v1/nodes` response payload."""
        if payload is None:
            return []
        if isinstance(payload, list):
            items = payload
        elif isinstance(payload, dict):
            items = payload.get("items") or []
        else:
            return []

        ready_names: list[str] = []
        for item in items:
            if isinstance(item, str) and item.strip():
                ready_names.append(item.strip())
            elif isinstance(item, dict):
                name = str((item.get("metadata") or {}).get("name") or item.get("name") or "").strip()
                if name and cls._is_node_ready(item) and cls._is_worker_node(item):
                    ready_names.append(name)
        return ready_names

    def _query_ready_worker_names(self) -> tuple[list[str], bool]:
        """Query the Kubernetes nodes callback and return (ready_names, has_items_field)."""
        if self._k8s_nodes_callback is None:
            return [], False
        try:
            payload = self._k8s_nodes_callback()
        except Exception as exc:
            logger.debug(f"Kubernetes node callback failed during worker check: {exc}")
            return [], False

        has_items = isinstance(payload, list) or (isinstance(payload, dict) and "items" in payload)
        return self.extract_ready_worker_names(payload), has_items

    def _resolve_join_token(self, explicit_token: str | None = None) -> str | None:
        """Resolve an optional k0s worker join token from arguments, environment, or controller."""
        token = (
            explicit_token
            or self._join_token
            or os.environ.get("PC_K0S_JOIN_TOKEN")
            or os.environ.get("K0S_JOIN_TOKEN")
        )
        if token and str(token).strip():
            return str(token).strip()

        token_file = (
            os.environ.get("PC_K0S_TOKEN_FILE", "").strip()
            or (self._join_token_file or "").strip()
        )
        if token_file and os.path.isfile(token_file):
            try:
                with open(token_file, encoding="utf-8") as fh:
                    file_tok = fh.read().strip()
                if file_tok:
                    return file_tok
            except OSError:
                pass

        controller = os.environ.get("PC_K0S_CONTROLLER_CONTAINER", "").strip() or (
            self._controller_container or ""
        ).strip()
        if controller:
            try:
                res = subprocess.run(
                    ["docker", "exec", controller, "k0s", "token", "create", "--role=worker"],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                if isinstance(res.stdout, str) and res.stdout.strip():
                    return res.stdout.strip()
            except (subprocess.SubprocessError, OSError) as exc:
                logger.warning(f"Failed generating k0s join token from '{controller}': {exc}")

        return None

    def _next_container_name(self) -> str:
        """Generate the next sequential worker container name."""
        while True:
            self._spawn_counter += 1
            candidate = f"{self._container_prefix}-{self._spawn_counter}"
            if candidate not in self._managed_nodes and candidate not in self._spawned_containers:
                return candidate

    def ensure_workers(self, count: int = 1, **kwargs: Any) -> list[str]:
        """Ensure at least `count` k0s worker containers are running and Ready."""
        if count <= 0:
            return []

        if self._network == "host" and count > 1:
            raise WorkerProvisioningError(
                "Docker workers using the host network are limited to one worker; "
                "set workers.docker.network to 'bridge' to provision more."
            )

        live_ready: list[str] = []
        has_items = False
        if self._k8s_nodes_callback is not None:
            live_ready, has_items = self._query_ready_worker_names()
            if has_items:
                self._managed_nodes = [n for n in self._managed_nodes if n in live_ready]
                if len(live_ready) >= count:
                    return list(live_ready[:count])
        available_count = len(live_ready) if has_items else len(self._managed_nodes)
        if available_count >= count:
            return list(live_ready[:count] if has_items else self._managed_nodes[:count])
        if len(self._managed_nodes) >= count and not has_items:
            return list(self._managed_nodes[:count])

        needed = max(0, count - available_count)
        token = self._resolve_join_token(kwargs.get("join_token"))
        if not token:
            raise WorkerProvisioningError(
                "No k0s worker join token is configured. Set workers.docker.join_token_file, "
                "PC_K0S_TOKEN_FILE, PC_K0S_JOIN_TOKEN, or workers.docker.controller_container."
            )
        spawned_now: list[str] = []

        for _ in range(needed):
            container_name = self._next_container_name()
            cmd: list[str] = [
                "docker",
                "run",
                "-d",
                "--privileged",
                "--name",
                container_name,
                "--hostname",
                container_name,
                "--network",
                self._network,
                "--cgroupns=host",
                "-v",
                "/var/lib/k0s",
                "--cpus",
                str(self._cpus),
                "--memory",
                str(self._memory),
                "--label",
                self.MANAGED_BY_LABEL,
                self._image,
                "k0s",
                "worker",
            ]
            cmd.append(token)

            try:
                subprocess.run(
                    cmd,
                    check=True,
                    capture_output=True,
                    text=True,
                )
            except (subprocess.SubprocessError, OSError) as exc:
                raise WorkerProvisioningError(
                    f"Failed to start Docker k0s worker container '{container_name}': {exc}"
                ) from exc

            spawned_now.append(container_name)
            if container_name not in self._spawned_containers:
                self._spawned_containers.append(container_name)
            if container_name not in self._managed_nodes:
                self._managed_nodes.append(container_name)

        if self._k8s_nodes_callback is None:
            return list(self._managed_nodes[:count])

        timeout = float(kwargs.get("timeout", self._ready_timeout))
        require_ready = bool(kwargs.get("require_ready", False))
        deadline = time.monotonic() + max(0.0, timeout)
        empty_polls = 0

        while True:
            ready_names, has_items = self._query_ready_worker_names()
            if len(ready_names) >= count:
                for r_name in ready_names:
                    if r_name in self._spawned_containers and r_name not in self._managed_nodes:
                        self._managed_nodes.append(r_name)
                return list(ready_names[:count])

            if not has_items:
                return list(self._managed_nodes[:count])

            if not ready_names:
                empty_polls += 1
                if not require_ready and empty_polls >= 2 and time.monotonic() >= deadline:
                    break

            if time.monotonic() >= deadline:
                break

            time.sleep(self._poll_interval)

        if require_ready:
            raise WorkerProvisioningError(
                f"Timed out waiting for {count} k0s worker node(s) to report Ready."
            )

        return list(self._managed_nodes[:count])

    def _discover_managed_containers(self) -> list[str]:
        """List existing Docker containers owned by this provider or its management label."""
        try:
            res = subprocess.run(
                [
                    "docker",
                    "ps",
                    "-a",
                    "--format",
                    "{{.Names}}\t{{.Labels}}",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
        except (subprocess.SubprocessError, OSError):
            return []

        if not isinstance(res.stdout, str):
            return []
        containers: list[str] = []
        for line in res.stdout.splitlines():
            name, _, labels = line.partition("\t")
            name = name.strip()
            if name and (name in self._spawned_containers or self.MANAGED_BY_LABEL in labels):
                containers.append(name)
        return containers

    def release_workers(self, node_names: list[str] | None = None) -> None:
        """Stop and remove managed Docker worker containers and delete their K8s node objects."""
        labeled_containers = self._discover_managed_containers()
        owned_containers = set(self._spawned_containers) | set(labeled_containers)
        requested = (
            [str(n).strip() for n in node_names if str(n).strip()]
            if node_names is not None
            else list(dict.fromkeys([*self._spawned_containers, *labeled_containers]))
        )
        targets = [name for name in dict.fromkeys(requested) if name in owned_containers]

        for name in targets:
            try:
                subprocess.run(
                    ["docker", "stop", name],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                subprocess.run(
                    ["docker", "rm", "-f", name],
                    check=True,
                    capture_output=True,
                    text=True,
                )
            except (subprocess.SubprocessError, OSError) as exc:
                raise WorkerReleaseError(
                    f"Failed to stop/remove Docker worker container '{name}': {exc}"
                ) from exc

            if self._k8s_delete_node_callback is not None:
                try:
                    self._k8s_delete_node_callback(name)
                except Exception as exc:
                    logger.debug(f"Skipping Kubernetes node object deletion for '{name}': {exc}")

            if name in self._managed_nodes:
                self._managed_nodes.remove(name)
            if name in self._spawned_containers:
                self._spawned_containers.remove(name)

        if node_names is None:
            self.reset_tracking()

    def status(self) -> dict[str, Any]:
        """Return current Docker worker provider state, node list, and resource capacity."""
        ready_names, has_items = self._query_ready_worker_names()
        active_nodes: list[str] = list(dict.fromkeys([*self._managed_nodes, *ready_names]))
        healthy = bool(ready_names) if has_items else True
        return {
            "provider": "docker",
            "image": self._image,
            "nodes": active_nodes,
            "capacity": {
                "cpus": self._cpus,
                "memory": self._memory,
                "count": len(active_nodes),
            },
            "healthy": healthy,
            "auto_cleanup": self._auto_cleanup,
        }


class ExternalWorkerProvider(WorkerProvider):
    """Delegate worker node provisioning, release, and status to external shell scripts."""

    def __init__(
        self,
        ensure_script: str | None = None,
        release_script: str | None = None,
        status_script: str | None = None,
        auto_cleanup: bool | None = None,
        settings: ExternalWorkerSettings | None = None,
        timeout: float = 120.0,
    ) -> None:
        """Configure script paths for external worker node lifecycle hooks."""
        resolved_ensure = (
            ensure_script
            if ensure_script is not None
            else (settings.ensure_script if settings is not None else None)
        )
        resolved_release = (
            release_script
            if release_script is not None
            else (settings.release_script if settings is not None else None)
        )
        resolved_status = (
            status_script
            if status_script is not None
            else (settings.status_script if settings is not None else None)
        )
        resolved_auto_cleanup = (
            auto_cleanup if auto_cleanup is not None else bool(resolved_release)
        )
        super().__init__(auto_cleanup=resolved_auto_cleanup)

        self._ensure_script: str | None = resolved_ensure
        self._release_script: str | None = resolved_release
        self._status_script: str | None = resolved_status
        self._timeout: float = float(timeout)

    @property
    def ensure_script(self) -> str | None:
        """Return the configured ensure_script path."""
        return self._ensure_script

    @property
    def release_script(self) -> str | None:
        """Return the configured release_script path."""
        return self._release_script

    @property
    def status_script(self) -> str | None:
        """Return the configured status_script path."""
        return self._status_script

    @staticmethod
    def _parse_node_output(raw_stdout: str, fallback_count: int = 0) -> list[str]:
        """Parse JSON array, JSON object with `nodes`, or newline-delimited node names."""
        text = (raw_stdout or "").strip()
        if not text:
            return [f"external-worker-{i + 1}" for i in range(fallback_count)]

        if text.startswith(("[", "{")):
            try:
                parsed = json.loads(text)
                if isinstance(parsed, list):
                    return [str(item).strip() for item in parsed if str(item).strip()]
                if isinstance(parsed, dict):
                    for key in ("nodes", "workers", "node_names"):
                        val = parsed.get(key)
                        if isinstance(val, list):
                            return [
                                str(item.get("name") if isinstance(item, dict) else item).strip()
                                for item in val
                                if str(item.get("name") if isinstance(item, dict) else item).strip()
                            ]
                    for single_key in ("node", "name"):
                        if isinstance(parsed.get(single_key), str) and parsed[single_key].strip():
                            return [parsed[single_key].strip()]
            except ValueError:
                pass

        return [line.strip() for line in text.splitlines() if line.strip()]

    def ensure_workers(self, count: int = 1, **kwargs: Any) -> list[str]:
        """Invoke `ensure_script` to provision at least `count` Ready worker nodes."""
        if count <= 0:
            return []

        if not self._ensure_script or not str(self._ensure_script).strip():
            raise WorkerProvisioningError(
                "External worker provider 'ensure_script' is not configured."
            )

        env = dict(os.environ)
        env["PC_WORKER_COUNT"] = str(count)
        for key, val in kwargs.items():
            env[f"PC_WORKER_{str(key).upper()}"] = str(val)

        try:
            result = subprocess.run(
                [str(self._ensure_script), str(count)],
                env=env,
                check=True,
                capture_output=True,
                text=True,
                timeout=self._timeout,
            )
        except (subprocess.SubprocessError, OSError) as exc:
            raise WorkerProvisioningError(
                f"External worker ensure_script '{self._ensure_script}' failed: {exc}"
            ) from exc

        stdout_text = result.stdout if isinstance(result.stdout, str) else ""
        nodes = self._parse_node_output(stdout_text, fallback_count=count)
        for node in nodes:
            if node not in self._managed_nodes:
                self._managed_nodes.append(node)
        return nodes

    def release_workers(self, node_names: list[str] | None = None) -> None:
        """Invoke `release_script` to terminate specified or managed worker nodes."""
        if not self._release_script or not str(self._release_script).strip():
            raise WorkerReleaseError(
                "External worker provider 'release_script' is not configured."
            )

        targets = (
            [str(n).strip() for n in node_names if str(n).strip()]
            if node_names is not None
            else list(self._managed_nodes)
        )
        env = dict(os.environ)
        env["PC_WORKER_NODES"] = ",".join(targets)

        try:
            subprocess.run(
                [str(self._release_script), *targets],
                env=env,
                check=True,
                capture_output=True,
                text=True,
                timeout=self._timeout,
            )
        except (subprocess.SubprocessError, OSError) as exc:
            raise WorkerReleaseError(
                f"External worker release_script '{self._release_script}' failed: {exc}"
            ) from exc

        if node_names is None:
            self._managed_nodes.clear()
        else:
            for name in targets:
                if name in self._managed_nodes:
                    self._managed_nodes.remove(name)

    def status(self) -> dict[str, Any]:
        """Invoke `status_script` and return structured worker status information."""
        if not self._status_script or not str(self._status_script).strip():
            return {
                "provider": "external",
                "nodes": list(self._managed_nodes),
                "capacity": {"count": len(self._managed_nodes)},
                "healthy": False,
                "configured": False,
                "auto_cleanup": self._auto_cleanup,
            }

        try:
            result = subprocess.run(
                [str(self._status_script)],
                env=dict(os.environ),
                check=True,
                capture_output=True,
                text=True,
                timeout=self._timeout,
            )
        except (subprocess.SubprocessError, OSError) as exc:
            return {
                "provider": "external",
                "nodes": list(self._managed_nodes),
                "capacity": {"count": len(self._managed_nodes)},
                "healthy": False,
                "configured": True,
                "error": str(exc),
                "auto_cleanup": self._auto_cleanup,
            }

        stdout_text = (result.stdout if isinstance(result.stdout, str) else "").strip()
        if stdout_text.startswith("{"):
            try:
                parsed = json.loads(stdout_text)
                if isinstance(parsed, dict):
                    nodes = parsed.get("nodes", list(self._managed_nodes))
                    capacity = parsed.get(
                        "capacity",
                        {"count": len(nodes) if isinstance(nodes, list) else 0},
                    )
                    return {
                        **parsed,
                        "provider": "external",
                        "nodes": nodes,
                        "capacity": capacity,
                        "healthy": bool(parsed.get("healthy", True)),
                        "configured": True,
                        "auto_cleanup": self._auto_cleanup,
                    }
            except ValueError:
                pass

        nodes = self._parse_node_output(stdout_text, fallback_count=0)
        return {
            "provider": "external",
            "nodes": nodes,
            "capacity": {"count": len(nodes)},
            "healthy": True,
            "configured": True,
            "auto_cleanup": self._auto_cleanup,
        }

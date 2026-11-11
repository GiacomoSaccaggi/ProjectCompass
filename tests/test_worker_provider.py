"""
░████████╗███████╗░██████╗████████╗░░░░░░░██╗░░░░░░░██╗░█████╗░██████╗░██╗░░██╗███████╗██████╗░
░╚══██╔══╝██╔════╝██╔════╝╚══██╔══╝░░░░░░░██║░░██╗░░██║██╔══██╗██╔══██╗██║░██╔╝██╔════╝██╔══██╗
░░░░██║░░░█████╗░░╚█████╗░░░░██║░░░█████╗░╚██╗████╗██╔╝██║░░██║���█████╔╝█████═╝░█████╗░░██████╔╝
░░░░██║░░░██╔══╝░░░╚═══██╗░░░██║░░░╚════╝░░████╔═████║░██║░░██║██╔══██╗██╔═██╗░██╔══╝░░██╔══██╗
░░░░██║░░░███████╗██████╔╝░░░██║░░░░░░░░░░░╚██╔╝░╚██╔╝░╚█████╔╝██║░░██║██║░╚██╗███████╗██║░░██║
░░░░╚═╝░░░╚══════╝╚═════╝░░░░╚═╝░░░░░░░░░░░░╚═╝░░░╚═╝░░░╚════╝░╚═╝░░╚═╝╚═╝░░╚═╝╚══════╝╚═╝░░╚═╝
"""

from __future__ import annotations

import re
import stat
import subprocess
from dataclasses import replace
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from models import Execution, db
from utils.app_settings import DockerWorkerSettings, ExternalWorkerSettings, WorkerSettings
from utils.worker_provider import (
    DockerWorkerProvider,
    ExternalWorkerProvider,
    WorkerProvider,
    WorkerProvisioningError,
    WorkerReleaseError,
)


def _make_ready_node_item(name: str, ready: str = "True", role: str = "worker") -> dict[str, Any]:
    """Construct a Kubernetes `/api/v1/nodes` item for worker provider tests."""
    return {
        "metadata": {
            "name": name,
            "labels": {f"node-role.kubernetes.io/{role}": "true"},
        },
        "status": {
            "conditions": [{"type": "Ready", "status": ready}],
        },
    }


class TestWorkerProviderABC:
    """Verify abstract contract enforcement and factory dispatch on WorkerProvider."""

    def test_cannot_instantiate_abc_or_incomplete_subclass(self) -> None:
        """Enforce implementation of ensure_workers, release_workers, and status."""
        with pytest.raises(TypeError):
            WorkerProvider()  # type: ignore[abstract]

        class IncompleteProvider(WorkerProvider):
            def ensure_workers(self, count: int = 1, **kwargs: Any) -> list[str]:
                return []

        with pytest.raises(TypeError):
            IncompleteProvider()  # type: ignore[abstract]

    def test_from_settings_dispatches_docker_and_external_providers(self) -> None:
        """Instantiate DockerWorkerProvider or ExternalWorkerProvider based on WorkerSettings."""
        docker_settings = WorkerSettings(
            provider="docker",
            docker=DockerWorkerSettings(
                image="docker.io/k0sproject/k0s:latest",
                cpus="4",
                memory="8g",
                auto_cleanup=True,
                network="bridge",
                join_token_file="/run/secrets/k0s-worker.token",
                controller_container="k0s-controller",
                ready_timeout_seconds=120,
            ),
        )
        docker_provider = WorkerProvider.from_settings(docker_settings)
        assert isinstance(docker_provider, DockerWorkerProvider)
        assert docker_provider.image == "docker.io/k0sproject/k0s:latest"
        assert docker_provider.cpus == "4"
        assert docker_provider.memory == "8g"
        assert docker_provider.auto_cleanup is True
        assert docker_provider.network == "bridge"
        assert docker_provider.ready_timeout == 120

        ext_settings = WorkerSettings(
            provider="external",
            external=ExternalWorkerSettings(
                ensure_script="/usr/local/bin/ensure.sh",
                release_script="/usr/local/bin/release.sh",
                status_script="/usr/local/bin/status.sh",
            ),
        )
        ext_provider = WorkerProvider.from_settings(ext_settings)
        assert isinstance(ext_provider, ExternalWorkerProvider)
        assert ext_provider.ensure_script == "/usr/local/bin/ensure.sh"
        assert ext_provider.release_script == "/usr/local/bin/release.sh"
        assert ext_provider.status_script == "/usr/local/bin/status.sh"


class TestDockerWorkerProvider:
    """Verify Docker CLI container lifecycle, readiness polling, and error handling."""

    def test_ensure_workers_spawns_containers_and_waits_for_ready(self) -> None:
        """Spawn two k0s worker containers with configured resources and wait for Ready status."""
        poll_count = {"n": 0}

        def nodes_callback() -> dict[str, Any]:
            poll_count["n"] += 1
            if poll_count["n"] <= 2:
                return {
                    "items": [
                        _make_ready_node_item("k0s-controller-1", ready="True", role="control-plane"),
                        _make_ready_node_item("pc-k0s-worker-1", ready="False"),
                    ]
                }
            return {
                "items": [
                    _make_ready_node_item("k0s-controller-1", ready="True", role="control-plane"),
                    _make_ready_node_item("pc-k0s-worker-1", ready="True"),
                    _make_ready_node_item("pc-k0s-worker-2", ready="True"),
                ]
            }

        provider = DockerWorkerProvider(
            image="docker.io/k0sproject/k0s:latest",
            cpus="2",
            memory="4g",
            auto_cleanup=True,
            k8s_nodes_callback=nodes_callback,
            join_token="join-token-xyz",
            ready_timeout=1.0,
            poll_interval=0.01,
        )

        docker_cmds: list[list[str]] = []

        def fake_subprocess_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            docker_cmds.append(list(cmd))
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="cid-123\n", stderr="")

        with patch("utils.worker_provider.subprocess.run", side_effect=fake_subprocess_run):
            ready_nodes = provider.ensure_workers(2, require_ready=True)

        assert ready_nodes == ["pc-k0s-worker-1", "pc-k0s-worker-2"]
        assert len(docker_cmds) == 2

        for idx, cmd in enumerate(docker_cmds, start=1):
            expected_name = f"pc-k0s-worker-{idx}"
            assert cmd[:4] == ["docker", "run", "-d", "--privileged"]
            assert "--name" in cmd and cmd[cmd.index("--name") + 1] == expected_name
            assert "--hostname" in cmd and cmd[cmd.index("--hostname") + 1] == expected_name
            assert "--network" in cmd and cmd[cmd.index("--network") + 1] == "bridge"
            assert "--cgroupns=host" in cmd
            assert "-v" in cmd and cmd[cmd.index("-v") + 1] == "/var/lib/k0s"
            assert "--cpus" in cmd and cmd[cmd.index("--cpus") + 1] == "2"
            assert "--memory" in cmd and cmd[cmd.index("--memory") + 1] == "4g"
            assert "--label" in cmd and cmd[cmd.index("--label") + 1] == DockerWorkerProvider.MANAGED_BY_LABEL
            assert "docker.io/k0sproject/k0s:latest" in cmd
            assert cmd[-3:] == ["k0s", "worker", "join-token-xyz"]

    def test_ensure_workers_is_noop_when_ready_worker_already_exists(self) -> None:
        """Skip spawning new Docker containers when `/api/v1/nodes` already has a Ready worker."""
        provider = DockerWorkerProvider(
            k8s_nodes_callback=lambda: {
                "items": [_make_ready_node_item("existing-worker-1", ready="True")]
            },
        )

        with patch("utils.worker_provider.subprocess.run") as mock_run:
            nodes = provider.ensure_workers(1)

        assert nodes == ["existing-worker-1"]
        mock_run.assert_not_called()

    def test_release_workers_stops_and_removes_containers_and_deletes_k8s_nodes(self) -> None:
        """Stop and remove managed worker containers and invoke k8s_delete_node_callback."""
        deleted_k8s_nodes: list[str] = []
        provider = DockerWorkerProvider(
            k8s_delete_node_callback=lambda name: deleted_k8s_nodes.append(name),
        )

        recorded_cmds: list[list[str]] = []

        def fake_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            recorded_cmds.append(list(cmd))
            if cmd[:2] == ["docker", "ps"]:
                return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="ok\n", stderr="")

        with patch("utils.worker_provider.subprocess.run", side_effect=fake_run):
            spawned = provider.ensure_workers(2, join_token="test-token")
            assert spawned == ["pc-k0s-worker-1", "pc-k0s-worker-2"]
            recorded_cmds.clear()

            provider.release_workers()

        assert recorded_cmds == [
            [
                "docker", "ps", "-a", "--format", "{{.Names}}\t{{.Labels}}",
            ],
            ["docker", "stop", "pc-k0s-worker-1"],
            ["docker", "rm", "-f", "pc-k0s-worker-1"],
            ["docker", "stop", "pc-k0s-worker-2"],
            ["docker", "rm", "-f", "pc-k0s-worker-2"],
        ]
        assert deleted_k8s_nodes == ["pc-k0s-worker-1", "pc-k0s-worker-2"]
        assert provider.managed_nodes == []

    def test_status_returns_provider_nodes_capacity_and_health(self) -> None:
        """Report provider type, active nodes, CPU/memory capacity, health, and auto_cleanup."""
        provider = DockerWorkerProvider(
            image="docker.io/k0sproject/k0s:latest",
            cpus="4",
            memory="8g",
            auto_cleanup=False,
            k8s_nodes_callback=lambda: {
                "items": [_make_ready_node_item("worker-node-1", ready="True")]
            },
        )
        info = provider.status()

        assert info["provider"] == "docker"
        assert info["image"] == "docker.io/k0sproject/k0s:latest"
        assert info["nodes"] == ["worker-node-1"]
        assert info["capacity"] == {"cpus": "4", "memory": "8g", "count": 1}
        assert info["healthy"] is True
        assert info["auto_cleanup"] is False

    def test_docker_error_handling_raises_typed_exceptions(self) -> None:
        """Raise WorkerProvisioningError on docker run failure/timeout and WorkerReleaseError on rm failure."""
        provider = DockerWorkerProvider(
            k8s_nodes_callback=lambda: {"items": []},
            ready_timeout=0.05,
            poll_interval=0.01,
            join_token="test-token",
        )

        # 1. docker run failure -> WorkerProvisioningError
        with patch(
            "utils.worker_provider.subprocess.run",
            side_effect=subprocess.CalledProcessError(1, ["docker", "run"], stderr="daemon error"),
        ):
            with pytest.raises(WorkerProvisioningError, match="Failed to start Docker k0s worker"):
                provider.ensure_workers(1)

        # 2. Readiness timeout when require_ready=True -> WorkerProvisioningError
        with patch(
            "utils.worker_provider.subprocess.run",
            return_value=subprocess.CompletedProcess(args=["docker"], returncode=0, stdout="cid\n", stderr=""),
        ):
            with pytest.raises(WorkerProvisioningError, match="Timed out waiting"):
                provider.ensure_workers(1, require_ready=True, timeout=0.02)

        # 3. docker stop/rm failure -> WorkerReleaseError
        with patch("utils.worker_provider.subprocess.run") as mock_run:
            mock_run.side_effect = lambda cmd, **kwargs: (
                subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")
                if cmd[:2] == ["docker", "ps"]
                else subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")
                if cmd[:2] == ["docker", "run"]
                else (_ for _ in ()).throw(
                    subprocess.CalledProcessError(1, cmd, stderr="cannot stop")
                )
            )
            provider.ensure_workers(1, join_token="test-token")
            with pytest.raises(WorkerReleaseError, match="Failed to stop/remove Docker worker"):
                provider.release_workers()

    def test_missing_join_token_fails_before_starting_container(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Fail fast with the relevant setting name when no join token is configured."""
        monkeypatch.delenv("PC_K0S_JOIN_TOKEN", raising=False)
        monkeypatch.delenv("K0S_JOIN_TOKEN", raising=False)
        monkeypatch.delenv("PC_K0S_TOKEN_FILE", raising=False)
        monkeypatch.delenv("PC_K0S_CONTROLLER_CONTAINER", raising=False)
        provider = DockerWorkerProvider()

        with patch("utils.worker_provider.subprocess.run") as mock_run:
            with pytest.raises(WorkerProvisioningError, match="PC_K0S_TOKEN_FILE"):
                provider.ensure_workers(1)

        mock_run.assert_not_called()

    def test_host_network_rejects_multiple_workers(self) -> None:
        """Reject requests that would start multiple workers on host networking."""
        provider = DockerWorkerProvider(network="host", join_token="test-token")

        with patch("utils.worker_provider.subprocess.run") as mock_run:
            with pytest.raises(WorkerProvisioningError, match="host network.*one"):
                provider.ensure_workers(2)

        mock_run.assert_not_called()

    def test_preexisting_ready_nodes_are_capacity_not_owned_containers(self) -> None:
        """Count pre-existing Ready nodes without tracking or releasing them."""
        provider = DockerWorkerProvider(
            k8s_nodes_callback=lambda: {
                "items": [_make_ready_node_item("preexisting-worker-1", ready="True")]
            },
        )
        commands: list[list[str]] = []

        def fake_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            commands.append(list(cmd))
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

        with patch("utils.worker_provider.subprocess.run", side_effect=fake_run):
            assert provider.ensure_workers(1) == ["preexisting-worker-1"]
            assert provider.managed_nodes == []
            provider.release_workers(["preexisting-worker-1"])

        assert commands == [[
            "docker", "ps", "-a", "--format", "{{.Names}}\t{{.Labels}}",
        ]]

    def test_configured_token_file_and_controller_are_used(self, tmp_path: Path) -> None:
        """Resolve join tokens from a configured file or configured controller container."""
        token_path = tmp_path / "worker.token"
        token_path.write_text("file-token\n", encoding="utf-8")
        provider = DockerWorkerProvider(
            settings=DockerWorkerSettings(join_token_file=str(token_path)),
        )
        commands: list[list[str]] = []

        def fake_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            commands.append(list(cmd))
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

        with patch("utils.worker_provider.subprocess.run", side_effect=fake_run):
            assert provider.ensure_workers(1) == ["pc-k0s-worker-1"]

        assert commands[0][-1] == "file-token"

        controller_provider = DockerWorkerProvider(controller_container="k0s-controller")
        commands.clear()

        def fake_controller_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            commands.append(list(cmd))
            stdout = "controller-token\n" if cmd[:2] == ["docker", "exec"] else ""
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=stdout, stderr="")

        with patch("utils.worker_provider.subprocess.run", side_effect=fake_controller_run):
            assert controller_provider.ensure_workers(1) == ["pc-k0s-worker-1"]

        assert commands[0] == [
            "docker", "exec", "k0s-controller", "k0s", "token", "create", "--role=worker",
        ]
        assert commands[1][-1] == "controller-token"

    def test_release_can_discover_only_labelled_containers_after_restart(self) -> None:
        """Allow cleanup of labelled workers without claiming unlabelled containers."""
        provider = DockerWorkerProvider()
        commands: list[list[str]] = []

        def fake_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            commands.append(list(cmd))
            stdout = (
                f"managed-from-label\t{DockerWorkerProvider.MANAGED_BY_LABEL}\n"
                if cmd[:2] == ["docker", "ps"]
                else ""
            )
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=stdout, stderr="")

        with patch("utils.worker_provider.subprocess.run", side_effect=fake_run):
            provider.release_workers(["managed-from-label", "unmanaged-container"])

        assert commands == [
            [
                "docker", "ps", "-a", "--format", "{{.Names}}\t{{.Labels}}",
            ],
            ["docker", "stop", "managed-from-label"],
            ["docker", "rm", "-f", "managed-from-label"],
        ]


class TestExternalWorkerProvider:
    """Verify ExternalWorkerProvider execution of real shell scripts and error handling."""

    def test_executes_real_shell_scripts_for_ensure_release_and_status(self, tmp_path: Path) -> None:
        """Execute temporary shell scripts and verify environment variables and output parsing."""
        env_log_file = tmp_path / "env_log.txt"

        ensure_script = tmp_path / "ensure_workers.sh"
        ensure_script.write_text(
            "#!/bin/sh\n"
            f'echo "COUNT=$PC_WORKER_COUNT ARG=$1" >> "{env_log_file}"\n'
            'echo \'{"nodes": ["ext-worker-1", "ext-worker-2"]}\'\n',
            encoding="utf-8",
        )
        ensure_script.chmod(ensure_script.stat().st_mode | stat.S_IEXEC)

        release_script = tmp_path / "release_workers.sh"
        release_script.write_text(
            "#!/bin/sh\n"
            f'echo "RELEASE=$PC_WORKER_NODES ARGS=$*" >> "{env_log_file}"\n',
            encoding="utf-8",
        )
        release_script.chmod(release_script.stat().st_mode | stat.S_IEXEC)

        status_script = tmp_path / "status_workers.sh"
        status_script.write_text(
            "#!/bin/sh\n"
            'echo \'{"nodes": ["ext-worker-1", "ext-worker-2"],'
            ' "capacity": {"count": 2, "cpus": "8"}, "healthy": true}\'\n',
            encoding="utf-8",
        )
        status_script.chmod(status_script.stat().st_mode | stat.S_IEXEC)

        provider = ExternalWorkerProvider(
            ensure_script=str(ensure_script),
            release_script=str(release_script),
            status_script=str(status_script),
            auto_cleanup=True,
        )

        provisioned = provider.ensure_workers(2)
        assert provisioned == ["ext-worker-1", "ext-worker-2"]
        assert provider.managed_nodes == ["ext-worker-1", "ext-worker-2"]

        status_info = provider.status()
        assert status_info["provider"] == "external"
        assert status_info["healthy"] is True
        assert status_info["configured"] is True
        assert status_info["nodes"] == ["ext-worker-1", "ext-worker-2"]
        assert status_info["capacity"] == {"count": 2, "cpus": "8"}

        provider.release_workers(["ext-worker-1"])
        assert provider.managed_nodes == ["ext-worker-2"]

        provider.release_workers()
        assert provider.managed_nodes == []

        logged_lines = env_log_file.read_text(encoding="utf-8").splitlines()
        assert "COUNT=2 ARG=2" in logged_lines[0]
        assert "RELEASE=ext-worker-1 ARGS=ext-worker-1" in logged_lines[1]
        assert "RELEASE=ext-worker-2 ARGS=ext-worker-2" in logged_lines[2]

    def test_newline_delimited_output_and_error_handling(self, tmp_path: Path) -> None:
        """Parse newline-delimited node names and raise typed errors when scripts are missing or fail."""
        unconfigured = ExternalWorkerProvider(ensure_script=None, release_script=None, status_script=None)
        with pytest.raises(WorkerProvisioningError, match="ensure_script"):
            unconfigured.ensure_workers(1)
        with pytest.raises(WorkerReleaseError, match="release_script"):
            unconfigured.release_workers()
        assert unconfigured.status()["configured"] is False

        newline_script = tmp_path / "ensure_lines.sh"
        newline_script.write_text("#!/bin/sh\necho node-alpha\necho node-beta\n", encoding="utf-8")
        newline_script.chmod(newline_script.stat().st_mode | stat.S_IEXEC)

        failing_script = tmp_path / "fail.sh"
        failing_script.write_text("#!/bin/sh\nexit 2\n", encoding="utf-8")
        failing_script.chmod(failing_script.stat().st_mode | stat.S_IEXEC)

        provider = ExternalWorkerProvider(
            ensure_script=str(newline_script),
            release_script=str(failing_script),
            status_script=str(newline_script),
        )
        assert provider.ensure_workers(2) == ["node-alpha", "node-beta"]
        assert provider.status()["nodes"] == ["node-alpha", "node-beta"]

        with pytest.raises(WorkerReleaseError, match="failed"):
            provider.release_workers()

        fail_ensure = ExternalWorkerProvider(ensure_script=str(failing_script))
        with pytest.raises(WorkerProvisioningError, match="failed"):
            fail_ensure.ensure_workers(1)


class TestAutoWorkerLifecycleInFlowExecution:
    """Verify automatic worker provisioning on Job launch and shared idle auto-cleanup on completion."""

    def test_launch_flow_run_auto_provisions_worker_and_releases_when_idle(
        self,
        app: Any,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Provision a worker when 0 Ready workers exist and release it after the Job completes."""
        webapp = app.config["WEBAPP"]
        original_settings = app.config["PC_SETTINGS"].for_templates()
        webapp.apply_settings(replace(
            original_settings,
            workers=replace(original_settings.workers, auto_provision=True),
        ))
        analyses_dir = tmp_path / "Analyses"
        analyses_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(webapp, "save_folder_path", str(analyses_dir))

        webapp.save_flow(name="AutoScaleFlow", code='print("scaled run")')

        events: list[str] = []
        mock_provider = MagicMock(spec=WorkerProvider)
        mock_provider.auto_cleanup = True

        def track_ensure(count: int = 1, **kwargs: Any) -> list[str]:
            events.append(f"ensure:{count}")
            return ["pc-k0s-worker-1"]

        def track_release(node_names: list[str] | None = None) -> None:
            events.append("release")

        mock_provider.ensure_workers.side_effect = track_ensure
        mock_provider.release_workers.side_effect = track_release
        webapp.worker_provider = mock_provider

        def fake_post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
            if path.endswith("/jobs"):
                events.append("post_job")
            return payload

        def fake_get(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
            if path == "/api/v1/nodes":
                return {
                    "items": [
                        _make_ready_node_item("k0s-controller", ready="True", role="control-plane"),
                    ]
                }
            if path.endswith("/pods"):
                return {
                    "items": [
                        {
                            "metadata": {"name": "pc-flow-job-pod"},
                            "spec": {"nodeName": "pc-k0s-worker-1"},
                            "status": {
                                "phase": "Succeeded",
                                "containerStatuses": [
                                    {"state": {"terminated": {"exitCode": 0, "reason": "Completed"}}}
                                ],
                            },
                        }
                    ]
                }
            if "/jobs/" in path:
                return {"status": {"succeeded": 1, "failed": 0}}
            return {}

        try:
            with (
                patch.object(webapp, "_build_and_push_image", return_value="registry:5050/pc/test:1"),
                patch.object(webapp, "_k8s_post", side_effect=fake_post),
                patch.object(webapp, "_k8s_get", side_effect=fake_get),
                patch.object(webapp, "_k8s_get_text", return_value="scaled run\n"),
                patch.object(webapp, "_k8s_delete", return_value={}),
            ):
                exe = webapp.launch_flow_run(
                    flow_name="AutoScaleFlow",
                    app=app,
                    wait_for_watcher=True,
                )
                assert exe.status == "success"

            assert events == ["ensure:1", "post_job", "release"]
        finally:
            webapp.apply_settings(original_settings)

    def test_concurrent_runs_skip_release_until_last_active_run_completes(
        self,
        app: Any,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Skip release_workers() when another Execution is still running, releasing only when idle."""
        webapp = app.config["WEBAPP"]
        original_settings = app.config["PC_SETTINGS"].for_templates()
        webapp.apply_settings(replace(
            original_settings,
            workers=replace(original_settings.workers, auto_provision=True),
        ))
        analyses_dir = tmp_path / "Analyses"
        analyses_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(webapp, "save_folder_path", str(analyses_dir))

        webapp.save_flow(name="ConcurrentFlow", code='print("concurrent")')

        mock_provider = MagicMock(spec=WorkerProvider)
        mock_provider.auto_cleanup = True
        mock_provider.ensure_workers.return_value = ["pc-k0s-worker-1"]
        webapp.worker_provider = mock_provider

        def fake_get(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
            if path == "/api/v1/nodes":
                return {"items": [_make_ready_node_item("pc-k0s-worker-1", ready="True")]}
            if path.endswith("/pods"):
                return {
                    "items": [
                        {
                            "metadata": {"name": "pc-concurrent-pod"},
                            "spec": {"nodeName": "pc-k0s-worker-1"},
                            "status": {
                                "phase": "Succeeded",
                                "containerStatuses": [
                                    {"state": {"terminated": {"exitCode": 0, "reason": "Completed"}}}
                                ],
                            },
                        }
                    ]
                }
            if "/jobs/" in path:
                return {"status": {"succeeded": 1, "failed": 0}}
            return {}

        try:
            with app.app_context():
                # Simulate Run #2 already active in 'running' state while Run #1 finishes
                concurrent_exe = Execution(
                    analysis_name="ConcurrentFlow",
                    status="running",
                    job_name="pc-flow-job-active",
                    namespace="default",
                )
                db.session.add(concurrent_exe)
                db.session.commit()
                active_id = concurrent_exe.id

            with (
                patch.object(webapp, "_build_and_push_image", return_value="registry:5050/pc/test:1"),
                patch.object(webapp, "_k8s_post", side_effect=lambda p, m: m),
                patch.object(webapp, "_k8s_get", side_effect=fake_get),
                patch.object(webapp, "_k8s_get_text", return_value="done 1\n"),
                patch.object(webapp, "_k8s_delete", return_value={}),
            ):
                exe_1 = webapp.launch_flow_run(
                    flow_name="ConcurrentFlow",
                    app=app,
                    wait_for_watcher=True,
                )
                assert exe_1.status == "success"
                # Because concurrent_exe is still 'running', release_workers must NOT have been called
                mock_provider.release_workers.assert_not_called()

                # Now mark the second run as finished and trigger idle check
                with app.app_context():
                    active_row = db.session.get(Execution, active_id)
                    assert active_row is not None
                    active_row.status = "success"
                    db.session.commit()
                    webapp._release_workers_if_idle(active_id)

                mock_provider.release_workers.assert_called_once_with()
        finally:
            webapp.apply_settings(original_settings)


def test_cloud_agnostic_codebase_audit() -> None:
    """Verify zero occurrences of banned cloud-vendor terms across application code, templates, and configs."""
    project_root = Path(__file__).resolve().parent.parent
    banned_pattern = re.compile(
        r"\b(boto3|botocore|anduril|AWS_SECRET_ACCESS_KEY|AWS_ACCESS_KEY_ID|worker-aws|worker-gcp)\b",
        re.IGNORECASE,
    )

    scan_Targets: list[Path] = [
        project_root / "app.py",
        project_root / "basefun.py",
        project_root / "config.py",
        project_root / "models.py",
        project_root / "projectcompass.example.yaml",
    ]
    for folder in ("blueprints", "utils", "templates", "tests"):
        folder_path = project_root / folder
        if folder_path.is_dir():
            for ext in ("*.py", "*.html", "*.yaml", "*.yml"):
                scan_Targets.extend(sorted(folder_path.rglob(ext)))

    current_file = Path(__file__).resolve()
    # k8s_utils.py uses boto3 for the S3 artifact store (MinIO) — not a cloud-vendor lock-in
    s3_exempt = {(project_root / "utils" / "k8s_utils.py").resolve()}
    violations: list[str] = []
    for file_path in scan_Targets:
        if file_path.resolve() == current_file or file_path.resolve() in s3_exempt or not file_path.is_file():
            continue
        text = file_path.read_text(encoding="utf-8", errors="ignore")
        match = banned_pattern.search(text)
        if match:
            rel = file_path.relative_to(project_root)
            violations.append(f"{rel}: matched '{match.group(0)}'")

    assert violations == [], f"Found cloud-vendor strings in codebase: {violations}"

"""
░████████╗███████╗░██████╗████████╗░░░░░░██████╗░██╗░░░██╗███╗░░██╗░██████╗
░╚══██╔══╝██╔════╝██╔════╝╚══██╔══╝░░░░░░██╔══██╗██║░░░██║████╗░██║██╔════╝
░░░░██║░░░█████╗░░╚█████╗░░░░██║░░░█████╗██████╔╝██║░░░██║██╔██╗██║╚█████╗░
░░░░██║░░░██╔══╝░░░╚═══██╗░░░██║░░░╚════╝██╔══██╗██║░░░██║██║╚████║░╚═══██╗
░░░░██║░░░███████╗██████╔╝░░░██║░░░░░░░░░██║░░██║╚██████╔╝██║░╚███║██████╔╝
░░░░╚═╝░░░╚══════╝╚═════╝░░░░╚═╝░░░░░░░░░╚═╝░░╚═╝░╚═════╝░╚═╝░░╚══╝╚═════╝░
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from basefun import ProjectCompass
from models import Execution, db
from utils.k8s_utils import BaseK8sClient, K8sClusterUtils, K8sFlowRunnerUtils


@pytest.fixture
def isolated_analyses_dir(app: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point webapp.save_folder_path to a temporary Analyses directory for tests."""
    webapp = app.config["WEBAPP"]
    analyses_dir = tmp_path / "Analyses"
    analyses_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(webapp, "save_folder_path", str(analyses_dir))
    return analyses_dir


def test_flow_runner_inheritance_hierarchy() -> None:
    """Verify BaseK8sClient -> K8sClusterUtils -> K8sFlowRunnerUtils -> ProjectCompass MRO."""
    assert issubclass(K8sFlowRunnerUtils, K8sClusterUtils)
    assert issubclass(K8sFlowRunnerUtils, BaseK8sClient)
    assert issubclass(ProjectCompass, K8sFlowRunnerUtils)


def test_hello_world_k8s_job_and_sse_idempotency(
    app: Any,
    client: Any,
    isolated_analyses_dir: Path,
) -> None:
    """Verify print('hello world') creates a K8s Job, captures stdout, and SSE reconnect is idempotent."""
    webapp = app.config["WEBAPP"]
    app.config["K8S_SYNC_WATCHER"] = True

    webapp.save_flow(
        name="HelloFlow",
        code='print("hello world")',
        description="Hello world flow",
        parameters={"target": "k0s"},
        pip_requirements=["requests==2.31.0"],
        image="python:3.11-slim",
    )

    posted_resources: list[tuple[str, dict[str, Any]]] = []
    deleted_resources: list[str] = []

    def fake_post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
        posted_resources.append((path, payload))
        return payload

    def fake_get(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if path.endswith("/pods"):
            return {
                "items": [
                    {
                        "metadata": {"name": "pc-flow-job-1-podxyz"},
                        "spec": {"nodeName": "worker-node-1"},
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

    def fake_get_text(path: str, params: dict[str, Any] | None = None) -> str:
        return "hello world\n"

    def fake_delete(
        path: str,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        deleted_resources.append(path)
        return {}

    with (
        patch.object(webapp, "_build_and_push_image", return_value="registry:5050/pc/test:1"),
        patch.object(webapp, "_k8s_post", side_effect=fake_post),
        patch.object(webapp, "_k8s_get", side_effect=fake_get),
        patch.object(webapp, "_k8s_get_text", side_effect=fake_get_text),
        patch.object(webapp, "_k8s_delete", side_effect=fake_delete),
    ):
        run_resp = client.post(
            "/flows/HelloFlow/run",
            json={
                "parameters": {"target": "k0s-cluster"},
                "pip_requirements": "requests==2.31.0",
                "env_vars": "API_KEY=secret123",
                "image": "python:3.11-slim",
                "wait": True,
            },
        )
        assert run_resp.status_code == 200
        run_data = run_resp.get_json()
        run_id = run_data["run_id"]
        assert run_data["status"] == "success"

        # Verify Secret and batch/v1 Job manifests were created (Dockerfile mode: no ConfigMap)
        paths = [p for p, _ in posted_resources]
        assert "/api/v1/namespaces/default/secrets" in paths
        assert "/apis/batch/v1/namespaces/default/jobs" in paths

        job_manifest = next(m for p, m in posted_resources if p.endswith("/jobs"))
        assert job_manifest["spec"]["backoffLimit"] == 0
        pod_spec = job_manifest["spec"]["template"]["spec"]
        assert pod_spec["automountServiceAccountToken"] is False
        container = pod_spec["containers"][0]
        assert container["image"] == "registry:5050/pc/test:1"
        assert container["envFrom"] == [{"secretRef": {"name": f"pc-flow-sec-{run_id}"}}]

        sec_manifest = next(m for p, m in posted_resources if p.endswith("/secrets"))
        assert sec_manifest["stringData"] == {"API_KEY": "secret123"}

        # Verify temporary Secret was deleted in finally block after run finished
        assert f"/api/v1/namespaces/default/secrets/pc-flow-sec-{run_id}" in deleted_resources

        # Verify Execution record in SQLite does NOT leak secret123 in inputs_json
        with app.app_context():
            exe = db.session.get(Execution, run_id)
            assert exe is not None
            assert exe.status == "success"
            assert exe.node_name == "worker-node-1"
            assert exe.exit_code == 0
            assert "hello world" in (exe.log_text or "")
            assert "secret123" not in (exe.inputs_json or "")
            parsed_inputs = json.loads(exe.inputs_json or "{}")
            assert parsed_inputs["secret_keys"] == ["API_KEY"]

        # Verify SSE /runs/<run_id>/stream can be called multiple times (refresh/reconnect)
        # without ever creating a second Kubernetes Job, even after Pod/Job deletion
        job_post_count_before = sum(1 for p, _ in posted_resources if p.endswith("/jobs"))
        sse_resp_1 = client.get(f"/runs/{run_id}/stream")
        sse_resp_2 = client.get(f"/runs/{run_id}/stream")
        detail_resp = client.get(f"/runs/{run_id}")
        exec_list_resp = client.get("/executions")
        job_post_count_after = sum(1 for p, _ in posted_resources if p.endswith("/jobs"))

        assert job_post_count_before == 1
        assert job_post_count_after == 1
        assert b"data: hello world" in sse_resp_1.data
        assert b"data: hello world" in sse_resp_2.data
        assert b"event: done" in sse_resp_1.data
        assert b"hello world" in detail_resp.data
        assert b"worker-node-1" in exec_list_resp.data


def test_failed_flow_captures_stderr_and_never_retries(
    app: Any,
    isolated_analyses_dir: Path,
) -> None:
    """Verify non-zero exit code records failed status, stderr traceback, and backoffLimit=0."""
    webapp = app.config["WEBAPP"]
    webapp.save_flow(
        name="FailingFlow",
        code='raise RuntimeError("boom error")',
        description="Fails intentionally",
    )

    def fake_post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
        return payload

    def fake_get(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if path.endswith("/pods"):
            return {
                "items": [
                    {
                        "metadata": {"name": "pc-flow-job-fail-pod"},
                        "spec": {"nodeName": "k0s-master-1"},
                        "status": {
                            "phase": "Failed",
                            "containerStatuses": [
                                {
                                    "state": {
                                        "terminated": {
                                            "exitCode": 1,
                                            "reason": "Error",
                                            "message": "RuntimeError: boom error",
                                        }
                                    }
                                }
                            ],
                        },
                    }
                ]
            }
        if "/jobs/" in path:
            return {"status": {"succeeded": 0, "failed": 1}}
        return {}

    def fake_get_text(path: str, params: dict[str, Any] | None = None) -> str:
        return 'Traceback (most recent call last):\n  File "/workspace/flow.py", line 1\nRuntimeError: boom error\n'

    with (
        patch.object(webapp, "_build_and_push_image", return_value="registry:5050/pc/test:1"),
        patch.object(webapp, "_k8s_post", side_effect=fake_post),
        patch.object(webapp, "_k8s_get", side_effect=fake_get),
        patch.object(webapp, "_k8s_get_text", side_effect=fake_get_text),
        patch.object(webapp, "_k8s_delete", return_value={}),
    ):
        exe = webapp.launch_flow_run(
            flow_name="FailingFlow",
            app=app,
            wait_for_watcher=True,
        )
        assert exe.status == "failed"
        assert exe.exit_code == 1
        assert "boom error" in (exe.error_message or "")
        assert "RuntimeError: boom error" in (exe.log_text or "")


def test_worker_provisioning_failure_returns_failed_runs_from_flow_and_api_routes(
    app: Any,
    client: Any,
    isolated_analyses_dir: Path,
) -> None:
    """Return a readable failed Execution instead of an HTTP 500 on provisioning errors."""
    from utils.worker_provider import WorkerProvisioningError

    webapp = app.config["WEBAPP"]
    webapp.save_flow(name="ProvisionFailureFlow", code='print("never submitted")')
    provider = webapp.worker_provider

    with (
        patch.object(webapp, "_should_manage_workers", return_value=True),
        patch.object(webapp, "_count_ready_workers", return_value=0),
        patch.object(
            provider,
            "ensure_workers",
            side_effect=WorkerProvisioningError("worker token is missing"),
        ),
        patch.object(webapp, "_build_and_push_image", return_value="registry:5050/pc/test:1"),
        patch.object(webapp, "_k8s_post") as post_resource,
    ):
        html_response = client.post("/flows/ProvisionFailureFlow/run", data={})
        assert html_response.status_code == 302
        assert html_response.headers["Location"].startswith("/runs/")

        json_response = client.post("/flows/ProvisionFailureFlow/run", json={})
        api_response = client.post("/api/analyses/ProvisionFailureFlow/run", json={})

    for response in (json_response, api_response):
        assert response.status_code == 200
        payload = response.get_json()
        assert payload["status"] == "failed"
        assert "worker token is missing" in payload["error_message"]
        assert payload["run_id"]
    post_resource.assert_not_called()


def test_oversized_saved_data_dataset_adds_execution_warning(
    app: Any,
    isolated_analyses_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Explain when a CSV is omitted because it exceeds the ConfigMap dataset cap."""
    webapp = app.config["WEBAPP"]
    saved_data_dir = tmp_path / "Saved_data"
    saved_data_dir.mkdir()
    (saved_data_dir / "oversized.csv").write_bytes(b"x" * (512 * 1024 + 1))
    monkeypatch.setattr(webapp, "save_data_path", str(saved_data_dir))
    webapp.save_flow(
        name="OversizedDatasetFlow",
        code='print("Saved_data/oversized.csv")',
    )
    # Remove Dockerfile to force ConfigMap mode (this test verifies dataset bundling warnings)
    for _f in ("Dockerfile", "compass_flow.yaml"):
        _p = Path(webapp.save_folder_path) / "OversizedDatasetFlow" / _f
        _p.unlink(missing_ok=True)

    def fake_get(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if path.endswith("/pods"):
            return {
                "items": [{
                    "metadata": {"name": "oversized-dataset-pod"},
                    "spec": {"nodeName": "worker-node-1"},
                    "status": {
                        "phase": "Succeeded",
                        "containerStatuses": [
                            {"state": {"terminated": {"exitCode": 0, "reason": "Completed"}}}
                        ],
                    },
                }]
            }
        if "/jobs/" in path:
            return {"status": {"succeeded": 1, "failed": 0}}
        return {}

    with (
        patch.object(webapp, "_build_and_push_image", return_value="registry:5050/pc/test:1"),
        patch.object(webapp, "_k8s_post", side_effect=lambda path, payload: payload),
        patch.object(webapp, "_k8s_get", side_effect=fake_get),
        patch.object(webapp, "_k8s_get_text", return_value="done\n"),
        patch.object(webapp, "_k8s_delete", return_value={}),
    ):
        execution = webapp.launch_flow_run(
            flow_name="OversizedDatasetFlow",
            app=app,
            wait_for_watcher=True,
        )

    assert execution.status == "success"
    assert "[ProjectCompass] WARNING" in (execution.log_text or "")
    assert "Saved_data/oversized.csv skipped" in (execution.log_text or "")


def test_job_manifest_resource_limits_and_secret_refs(
    app: Any,
    isolated_analyses_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify build_job_manifest injects resource requests/limits and cluster + per-flow secretRefs."""
    webapp = app.config["WEBAPP"]

    # 1. Verify defaults when env vars are unset and no secrets are used
    monkeypatch.delenv("K8S_DEFAULT_CPU_REQUEST", raising=False)
    monkeypatch.delenv("K8S_DEFAULT_CPU_LIMIT", raising=False)
    monkeypatch.delenv("K8S_DEFAULT_MEMORY_REQUEST", raising=False)
    monkeypatch.delenv("K8S_DEFAULT_MEMORY_LIMIT", raising=False)
    monkeypatch.delenv("K8S_SECRET_REFS", raising=False)

    minimal_job = webapp.build_job_manifest(
        run_id=42,
        flow_name="MinimalFlow",
        image="python:3.11-slim",
        parameters={},
        has_secret=False,
        namespace="default",
    )
    min_container = minimal_job["spec"]["template"]["spec"]["containers"][0]
    assert min_container["resources"] == {
        "requests": {"cpu": "500m", "memory": "512Mi"},
        "limits": {"cpu": "1", "memory": "1Gi"},
    }
    assert "envFrom" not in min_container

    # 2. Verify custom CPU/memory limits and additive secretRef ordering:
    #    cluster-wide K8S_SECRET_REFS -> per-flow secret_refs -> per-run Secret
    monkeypatch.setenv("K8S_DEFAULT_CPU_REQUEST", "250m")
    monkeypatch.setenv("K8S_DEFAULT_CPU_LIMIT", "2")
    monkeypatch.setenv("K8S_DEFAULT_MEMORY_REQUEST", "256Mi")
    monkeypatch.setenv("K8S_DEFAULT_MEMORY_LIMIT", "2Gi")
    monkeypatch.setenv("K8S_SECRET_REFS", "cluster-db-creds, cluster-s3-creds")

    flow_secret_names = ["flow-api-creds", "cluster-s3-creds"]
    saved_flow = webapp.save_flow(
        name="SecretRefsFlow",
        code='import os\nprint(os.environ.get("DB_HOST"))',
        secret_refs=flow_secret_names,
    )
    assert saved_flow["secret_refs"] == ["flow-api-creds", "cluster-s3-creds"]

    job_with_secrets = webapp.build_job_manifest(
        run_id=99,
        flow_name="SecretRefsFlow",
        image="python:3.11-slim",
        parameters={"env": "prod"},
        has_secret=True,
        namespace="default",
        secret_refs=saved_flow["secret_refs"],
    )
    sec_container = job_with_secrets["spec"]["template"]["spec"]["containers"][0]
    assert sec_container["resources"] == {
        "requests": {"cpu": "250m", "memory": "256Mi"},
        "limits": {"cpu": "2", "memory": "2Gi"},
    }
    assert sec_container["envFrom"] == [
        {"secretRef": {"name": "cluster-db-creds"}},
        {"secretRef": {"name": "cluster-s3-creds"}},
        {"secretRef": {"name": "flow-api-creds"}},
        {"secretRef": {"name": "pc-flow-sec-99"}},
    ]


def test_extract_and_persist_artifacts_and_structured_analysis_flow_run(
    app: Any,
    isolated_analyses_dir: Path,
) -> None:
    """Verify log-stream artifact extraction persists output.csv and report.html and strips base64 frames."""
    import base64

    webapp = app.config["WEBAPP"]
    sa_name = "StructuredArtifactFlow"
    sa_dir = isolated_analyses_dir / sa_name
    (sa_dir / "analysis").mkdir(parents=True, exist_ok=True)
    (sa_dir / "physical_output" / "main").mkdir(parents=True, exist_ok=True)
    (sa_dir / "metadata.yaml").write_text(
        "title: StructuredArtifactFlow\nproduct: Analytics\ndescription: Artifact test\n",
        encoding="utf-8",
    )
    (sa_dir / "compass_flow.yaml").write_text(
        "description: StructuredArtifactFlow\ninputs:\n  threshold:\n    type: text\n    default: \"10\"\n",
        encoding="utf-8",
    )
    dockerfile_content = "FROM python:3.12-slim\nENTRYPOINT [\"python\", \"flow.py\"]\n"
    (sa_dir / "Dockerfile").write_text(dockerfile_content, encoding="utf-8")
    (sa_dir / "flow.py").write_text(
        "def run(inputs, output_path):\n"
        "    with open(output_path, 'w') as fh:\n"
        "        fh.write('col1,col2\\n1,2\\n')\n"
        "    return {'ok': True}\n",
        encoding="utf-8",
    )

    flow_info = webapp.read_flow(sa_name)
    assert flow_info is not None
    assert flow_info["name"] == sa_name

    csv_payload = b"metric,value\naccuracy,0.98\n"
    html_payload = b"<!DOCTYPE html><html><body><h2>Summary</h2></body></html>"
    b64_csv = base64.b64encode(csv_payload).decode("ascii")
    b64_html = base64.b64encode(html_payload).decode("ascii")
    raw_pod_logs = (
        "Running structured analysis step 1...\n"
        f"[PC_ARTIFACT_BEGIN:output.csv]\n{b64_csv}\n[PC_ARTIFACT_END]\n"
        f"[PC_ARTIFACT_BEGIN:report.html]\n{b64_html}\n[PC_ARTIFACT_END]\n"
        "Finished structured analysis.\n"
    )

    def fake_get(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if path.endswith("/pods"):
            return {
                "items": [
                    {
                        "metadata": {"name": "pc-sa-artifact-pod"},
                        "spec": {"nodeName": "worker-node-1"},
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

    with (
        patch.object(webapp, "_build_and_push_image", return_value="registry:5050/pc/test:1"),
        patch.object(webapp, "_k8s_post", side_effect=lambda p, m: m),
        patch.object(webapp, "_k8s_get", side_effect=fake_get),
        patch.object(webapp, "_k8s_get_text", return_value=raw_pod_logs),
        patch.object(webapp, "_k8s_delete", return_value={}),
    ):
        exe = webapp.launch_flow_run(
            flow_name=sa_name,
            parameters={"threshold": 25},
            app=app,
            wait_for_watcher=True,
        )
        assert exe.status == "success"
        assert "Running structured analysis step 1..." in (exe.log_text or "")
        assert "Finished structured analysis." in (exe.log_text or "")
        assert "[PC_ARTIFACT_BEGIN:" not in (exe.log_text or "")
        assert b64_csv not in (exe.log_text or "")
        assert json.loads(exe.outputs_json or "[]") == ["output.csv", "report.html"]

    main_csv = sa_dir / "physical_output" / "main" / "output.csv"
    main_html = sa_dir / "physical_output" / "main" / "report.html"
    assert main_csv.read_bytes() == csv_payload
    assert main_html.read_bytes() == html_payload

    history_files = [
        p for p in (sa_dir / "physical_output").iterdir()
        if p.is_file() and p.suffix in (".csv", ".html")
    ]
    assert len(history_files) == 2


def test_build_and_push_image_tags_k8s_host_and_stages_saved_data(
    app: Any,
    isolated_analyses_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify _build_and_push_image tags k8s_tag, imports it, stages Saved_data, and cleans up."""
    import subprocess

    webapp = app.config["WEBAPP"]
    sa_dir = isolated_analyses_dir / "DockerBuildFlow"
    sa_dir.mkdir(parents=True, exist_ok=True)
    (sa_dir / "flow.py").write_text(
        'import pandas as pd\ndf = pd.read_csv("Saved_data/sales_data.csv")\n',
        encoding="utf-8",
    )
    (sa_dir / "Dockerfile").write_text("FROM python:3.12-slim\n", encoding="utf-8")

    monkeypatch.setenv("PC_REGISTRY_HOST", "localhost:5050")
    monkeypatch.setenv("PC_REGISTRY_K8S_HOST", "registry:5000")

    commands: list[Any] = []
    staged_during_build: dict[str, bool] = {}

    class DummyCompleted:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(cmd: Any, *args: Any, **kwargs: Any) -> DummyCompleted:
        commands.append(cmd)
        if isinstance(cmd, list) and cmd[:2] == ["docker", "build"]:
            staged_during_build["entrypoint"] = (sa_dir / "scripts" / "pc_entrypoint.sh").is_file()
            staged_during_build["sales_csv"] = (sa_dir / "Saved_data" / "sales_data.csv").is_file()
        return DummyCompleted()

    monkeypatch.setattr(subprocess, "run", fake_run)

    returned_tag = webapp._build_and_push_image("DockerBuildFlow", str(sa_dir), 42)
    assert returned_tag == "registry:5000/pc/dockerbuildflow:42"
    assert staged_during_build.get("entrypoint") is True
    assert staged_during_build.get("sales_csv") is True
    assert ["docker", "tag", "localhost:5050/pc/dockerbuildflow:42", "registry:5000/pc/dockerbuildflow:42"] in commands
    assert any(
        isinstance(c, str) and "docker save registry:5000/pc/dockerbuildflow:42" in c
        for c in commands
    )
    # Temporary staged files are cleaned up after build
    assert not (sa_dir / "scripts" / "pc_entrypoint.sh").exists()
    assert not (sa_dir / "Saved_data" / "sales_data.csv").exists()

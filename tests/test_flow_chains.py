"""
░████████╗███████╗░██████╗████████╗░░░░░░░█████╗░██╗░░██╗░█████╗░██╗███╗░░██╗░██████╗
░╚══██╔══╝██╔════╝██╔════╝╚══██╔══╝░░░░░░██╔══██╗██║░░██║██╔══██╗██║████╗░██║██╔════╝
░░░░██║░░░█████╗░░╚█████╗░░░░██║░░░█████╗██║░░╚═╝███████║███████║██║██╔██╗██║╚█████╗░
░░░░██║░░░██╔══╝░░░╚═══██╗░░��██║░░░╚════╝██║░░██╗██╔══██║██╔══██║██║██║╚████║░╚═══██╗
░░░░██║░░░███████╗██████╔╝░░░██║░░░░░░░░░╚█████╔╝██║░░██║██║░░██║██║██║░╚███║██████╔╝
░░░░╚═╝░░░╚══════╝╚═════╝░░░░╚═╝░░░░░░░░░░╚════╝░╚═╝░░╚═╝╚═╝░░╚═╝╚═╝╚═╝░░╚══╝╚═════╝░
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from basefun import ProjectCompass
from models import ChainExecution, Execution
from utils.k8s_utils import BaseK8sClient, K8sChainRunnerUtils, K8sClusterUtils, K8sFlowRunnerUtils


@pytest.fixture
def isolated_analyses_dir(app: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point webapp.save_folder_path to a temporary Analyses directory for tests."""
    webapp = app.config["WEBAPP"]
    analyses_dir = tmp_path / "Analyses"
    analyses_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(webapp, "save_folder_path", str(analyses_dir))
    return analyses_dir


def test_chain_runner_inheritance_hierarchy() -> None:
    """Verify BaseK8sClient -> K8sClusterUtils -> K8sFlowRunnerUtils -> K8sChainRunnerUtils -> ProjectCompass."""
    assert issubclass(K8sChainRunnerUtils, K8sFlowRunnerUtils)
    assert issubclass(K8sChainRunnerUtils, K8sClusterUtils)
    assert issubclass(K8sChainRunnerUtils, BaseK8sClient)
    assert issubclass(ProjectCompass, K8sChainRunnerUtils)


def test_two_step_chain_executes_sequentially_and_succeeds(
    app: Any,
    client: Any,
    isolated_analyses_dir: Path,
) -> None:
    """Verify a 2-step chain runs both flows in sequence and records both Execution IDs."""
    webapp = app.config["WEBAPP"]
    app.config["K8S_SYNC_WATCHER"] = True

    webapp.save_flow(name="StepOne", code='print("step 1 complete")')
    webapp.save_flow(name="StepTwo", code='print("step 2 complete")')

    chain_info = webapp.save_chain(
        name="TwoStepChain",
        flow_names=["StepOne", "StepTwo"],
        description="Linear 2-step chain",
    )
    assert chain_info["flow_names"] == ["StepOne", "StepTwo"]
    assert chain_info["flow_names_arrow"] == "StepOne -> StepTwo"

    def fake_post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
        return payload

    def fake_get(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if path.endswith("/pods"):
            return {
                "items": [
                    {
                        "metadata": {"name": "pc-chain-pod"},
                        "spec": {"nodeName": "worker-1"},
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
        patch.object(webapp, "_k8s_post", side_effect=fake_post),
        patch.object(webapp, "_k8s_get", side_effect=fake_get),
        patch.object(webapp, "_k8s_get_text", return_value="step ok\n"),
        patch.object(webapp, "_k8s_delete", return_value={}),
    ):
        resp = client.post(
            "/chains/TwoStepChain/run",
            json={"parameters": {"batch_id": "101"}, "wait": True},
        )
        assert resp.status_code == 200
        payload = resp.get_json()
        assert payload["status"] == "success"
        assert payload["current_step"] == 2
        exec_ids = payload["execution_ids"]
        assert len(exec_ids) == 2

        ex1 = Execution.query.get(exec_ids[0])
        ex2 = Execution.query.get(exec_ids[1])
        assert ex1 is not None and ex1.analysis_name == "StepOne" and ex1.status == "success"
        assert ex2 is not None and ex2.analysis_name == "StepTwo" and ex2.status == "success"
        assert ex1.id < ex2.id

        detail_html = client.get(f"/chains/runs/{payload['chain_run_id']}")
        assert detail_html.status_code == 200
        assert b"StepOne" in detail_html.data
        assert b"StepTwo" in detail_html.data


def test_chain_stops_immediately_when_middle_step_fails(
    app: Any,
    isolated_analyses_dir: Path,
) -> None:
    """Verify if step 2 of a 3-step chain fails, step 3 is never launched and chain status is failed."""
    webapp = app.config["WEBAPP"]
    webapp.save_flow(name="FlowA", code='print("A")')
    webapp.save_flow(name="FlowB_Fail", code='raise RuntimeError("step B boom")')
    webapp.save_flow(name="FlowC_ShouldNotRun", code='print("C")')

    webapp.save_chain(
        name="ThreeStepFailChain",
        flow_names="FlowA -> FlowB_Fail -> FlowC_ShouldNotRun",
    )

    call_count = {"jobs": 0}

    def fake_post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
        if path.endswith("/jobs"):
            call_count["jobs"] += 1
        return payload

    def fake_get(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        # First job succeeds, second job fails
        is_second_job = call_count["jobs"] >= 2
        if path.endswith("/pods"):
            if is_second_job:
                return {
                    "items": [
                        {
                            "metadata": {"name": "pod-fail"},
                            "spec": {"nodeName": "worker-1"},
                            "status": {
                                "phase": "Failed",
                                "containerStatuses": [
                                    {
                                        "state": {
                                            "terminated": {
                                                "exitCode": 1,
                                                "reason": "Error",
                                                "message": "step B boom",
                                            }
                                        }
                                    }
                                ],
                            },
                        }
                    ]
                }
            return {
                "items": [
                    {
                        "metadata": {"name": "pod-ok"},
                        "spec": {"nodeName": "worker-1"},
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
            if is_second_job:
                return {"status": {"succeeded": 0, "failed": 1}}
            return {"status": {"succeeded": 1, "failed": 0}}
        return {}

    with (
        patch.object(webapp, "_k8s_post", side_effect=fake_post),
        patch.object(webapp, "_k8s_get", side_effect=fake_get),
        patch.object(webapp, "_k8s_get_text", return_value="log output\n"),
        patch.object(webapp, "_k8s_delete", return_value={}),
    ):
        chain_exe = webapp.launch_chain_run(
            chain_name="ThreeStepFailChain",
            app=app,
            wait_for_completion=True,
        )
        assert chain_exe.status == "failed"
        assert "FlowB_Fail" in (chain_exe.error_message or "")
        exec_ids = json.loads(chain_exe.execution_ids_json or "[]")
        assert len(exec_ids) == 2
        assert call_count["jobs"] == 2
        assert Execution.query.filter_by(analysis_name="FlowC_ShouldNotRun").count() == 0


def test_chains_ui_crud_and_scheduled_chain_execution(
    app: Any,
    client: Any,
    isolated_analyses_dir: Path,
) -> None:
    """Verify /chains UI CRUD routes and scheduled chain execution through execute_scheduled_flow."""
    from blueprints.catalog import execute_scheduled_flow

    webapp = app.config["WEBAPP"]
    app.config["K8S_SYNC_WATCHER"] = True

    webapp.save_flow(name="IngestFlow", code='print("ingest")')
    webapp.save_flow(name="TransformFlow", code='print("transform")')

    # 1. Save chain via POST /chains/save
    save_resp = client.post(
        "/chains/save",
        data={
            "name": "ETLPipeline",
            "description": "Ingest then transform",
            "flow_names_text": "IngestFlow, TransformFlow",
        },
        follow_redirects=True,
    )
    assert save_resp.status_code == 200
    assert b"ETLPipeline" in save_resp.data
    assert b"IngestFlow -&gt; TransformFlow" in save_resp.data

    # 2. Schedule the chain via POST /schedules/create
    sched_resp = client.post(
        "/schedules/create",
        data={
            "job_id": "sched_chain_etl",
            "chain_name": "ETLPipeline",
            "schedule_type": "interval",
            "interval_minutes": "60",
            "enabled": "1",
        },
        follow_redirects=True,
    )
    assert sched_resp.status_code == 200
    assert b"Chain: ETLPipeline" in sched_resp.data

    # 3. Verify execute_scheduled_flow runs the chain with trigger_type='scheduled'
    with (
        patch.object(webapp, "_k8s_post", side_effect=lambda p, m: m),
        patch.object(
            webapp,
            "_k8s_get",
            return_value={
                "items": [
                    {
                        "metadata": {"name": "pod-sched"},
                        "spec": {"nodeName": "worker-1"},
                        "status": {
                            "phase": "Succeeded",
                            "containerStatuses": [
                                {"state": {"terminated": {"exitCode": 0, "reason": "Completed"}}}
                            ],
                        },
                    }
                ],
                "status": {"succeeded": 1, "failed": 0},
            },
        ),
        patch.object(webapp, "_k8s_get_text", return_value="ok\n"),
        patch.object(webapp, "_k8s_delete", return_value={}),
    ):
        chain_exe = execute_scheduled_flow(chain_name="ETLPipeline", app=app)
        assert isinstance(chain_exe, ChainExecution)
        assert chain_exe.status == "success"
        assert chain_exe.trigger_type == "scheduled"
        assert len(json.loads(chain_exe.execution_ids_json)) == 2

    # 4. Delete chain via POST /chains/ETLPipeline/delete
    del_resp = client.post("/chains/ETLPipeline/delete", follow_redirects=True)
    assert del_resp.status_code == 200
    assert webapp.read_chain("ETLPipeline") is None


def test_compile_pipeline_to_flow_chain_and_sequential_connector_execution(
    app: Any,
    isolated_analyses_dir: Path,
) -> None:
    """Verify compile_pipeline_to_flow_chain compiles connector steps with custom images into a FlowChain."""
    from utils.app_settings import ConnectorParameterSpec, ConnectorSettings

    webapp = app.config["WEBAPP"]
    trino_connector = ConnectorSettings(
        name="trino_etl",
        description="Execute Trino ETL query",
        image="custom-trino-runner:latest",
        builtin=False,
        parameters=(
            ConnectorParameterSpec(name="query", param_type="text", required=True),
            ConnectorParameterSpec(name="connection", param_type="select", source="connections"),
        ),
    )
    python_connector = ConnectorSettings(
        name="python_script",
        description="Execute custom Python script",
        image="python:3.12-slim",
        builtin=True,
        parameters=(ConnectorParameterSpec(name="code", param_type="code", required=True),),
    )

    compiled = webapp.compile_pipeline_to_flow_chain(
        name="ConnectorETLChain",
        steps=[
            {
                "type": "trino_etl",
                "config": {"query": "SELECT id, score FROM metrics", "connection": "analytics_db"},
            },
            {
                "type": "python_script",
                "config": {"code": 'print("post-processing metrics")'},
            },
        ],
        connectors=[trino_connector, python_connector],
        description="Two-step connector ETL chain",
        owner="alice",
        product="Data",
    )

    assert compiled["chain_name"] == "ConnectorETLChain"
    assert compiled["step_flows"] == [
        "ConnectorETLChain__step_1_trino_etl",
        "ConnectorETLChain__step_2_python_script",
    ]

    step1_flow = webapp.read_flow("ConnectorETLChain__step_1_trino_etl")
    step2_flow = webapp.read_flow("ConnectorETLChain__step_2_python_script")
    assert step1_flow is not None and step1_flow["image"] == "custom-trino-runner:latest"
    assert step2_flow is not None and step2_flow["image"] == "python:3.12-slim"

    submitted_jobs: list[dict[str, Any]] = []

    def fake_post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
        if path.endswith("/jobs"):
            submitted_jobs.append(payload)
        return payload

    def fake_get(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if path.endswith("/pods"):
            return {
                "items": [
                    {
                        "metadata": {"name": "pc-connector-pod"},
                        "spec": {"nodeName": "worker-1"},
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
        patch.object(webapp, "_k8s_post", side_effect=fake_post),
        patch.object(webapp, "_k8s_get", side_effect=fake_get),
        patch.object(webapp, "_k8s_get_text", return_value="connector step ok\n"),
        patch.object(webapp, "_k8s_delete", return_value={}),
    ):
        chain_exe = webapp.launch_chain_run(
            chain_name="ConnectorETLChain",
            app=app,
            wait_for_completion=True,
        )
        assert chain_exe.status == "success"
        assert len(submitted_jobs) == 2

        container_1 = submitted_jobs[0]["spec"]["template"]["spec"]["containers"][0]
        container_2 = submitted_jobs[1]["spec"]["template"]["spec"]["containers"][0]
        assert container_1["image"] == "custom-trino-runner:latest"
        assert container_2["image"] == "python:3.12-slim"

        env_map_1 = {item["name"]: item["value"] for item in container_1["env"]}
        assert env_map_1["PC_PARAM_QUERY"] == "SELECT id, score FROM metrics"
        assert env_map_1["PC_PARAM_CONNECTION"] == "analytics_db"


def test_three_step_chain_provisions_once_and_releases_after_completion(
    app: Any,
    isolated_analyses_dir: Path,
) -> None:
    """Keep one provisioned worker available across all steps and clean up once at chain end."""
    from dataclasses import replace
    from unittest.mock import MagicMock

    from utils.worker_provider import WorkerProvider

    webapp = app.config["WEBAPP"]
    original_settings = app.config["PC_SETTINGS"].for_templates()
    webapp.apply_settings(replace(
        original_settings,
        workers=replace(original_settings.workers, auto_provision=True, auto_cleanup=True),
    ))
    provider = MagicMock(spec=WorkerProvider)
    provider.auto_cleanup = True
    webapp.worker_provider = provider

    step_names = ["ThreeStepOne", "ThreeStepTwo", "ThreeStepThree"]
    for step_name in step_names:
        webapp.save_flow(name=step_name, code=f'print("{step_name}")')
    webapp.save_chain(name="ThreeStepChain", flow_names=step_names)

    ready = False
    posted_jobs: list[dict[str, Any]] = []

    def ensure_workers(count: int = 1, **kwargs: Any) -> list[str]:
        nonlocal ready
        ready = True
        return ["worker-node-1"]

    provider.ensure_workers.side_effect = ensure_workers

    def fake_get(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if path == "/api/v1/nodes":
            if not ready:
                return {"items": []}
            return {"items": [{
                "metadata": {
                    "name": "worker-node-1",
                    "labels": {"node-role.kubernetes.io/worker": "true"},
                },
                "status": {"conditions": [{"type": "Ready", "status": "True"}]},
            }]}
        if path.endswith("/pods"):
            return {"items": [{
                "metadata": {"name": "three-step-pod"},
                "spec": {"nodeName": "worker-node-1"},
                "status": {
                    "phase": "Succeeded",
                    "containerStatuses": [
                        {"state": {"terminated": {"exitCode": 0, "reason": "Completed"}}}
                    ],
                },
            }]}
        if "/jobs/" in path:
            return {"status": {"succeeded": 1, "failed": 0}}
        return {}

    def fake_post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
        if path.endswith("/jobs"):
            posted_jobs.append(payload)
        return payload

    try:
        with (
            patch.object(webapp, "_k8s_post", side_effect=fake_post),
            patch.object(webapp, "_k8s_get", side_effect=fake_get),
            patch.object(webapp, "_k8s_get_text", return_value="step complete\n"),
            patch.object(webapp, "_k8s_delete", return_value={}),
        ):
            chain_execution = webapp.launch_chain_run(
                chain_name="ThreeStepChain",
                app=app,
                wait_for_completion=True,
            )

        assert chain_execution.status == "success"
        assert len(posted_jobs) == 3
        provider.ensure_workers.assert_called_once_with(1, require_ready=True)
        provider.release_workers.assert_called_once_with()
    finally:
        webapp.apply_settings(original_settings)

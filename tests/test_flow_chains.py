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

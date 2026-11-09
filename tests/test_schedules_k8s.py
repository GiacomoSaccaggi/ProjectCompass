"""
░████████╗███████╗░██████╗████████╗░░░░░░░██████╗░█████╗░██╗░░██╗███████╗██████╗░
░╚══██╔══╝██╔════╝██╔════╝╚══██╔══╝░░░░░░██╔════╝██╔══██╗██║░░██║██╔════╝██╔══██╗
░░░░██║░░░█████╗░░╚█████╗░░░░██║░░░█████╗╚█████╗░██║░░╚═╝███████║█████╗░░██║░░██║
░░░░██║░░░██╔══╝░░░╚═══██╗░░░██║░░░╚════╝░╚═══██╗██║░░██╗██╔══██║██╔══╝░░██║░░██║
░░░░██║░░░███████╗██████╔╝░░░██║░░░░░░░░░██████╔╝╚█████╔╝██║░░██║███████╗██████╔╝
░░░░╚═╝░░░╚═��════╝╚═════╝░░░░╚═╝░░░░░░░░░╚═════╝░░╚════╝░╚═╝░░╚═╝╚══════╝╚═════╝░
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from app import acquire_scheduler_lock, create_app
from config import Config
from models import Execution


@pytest.fixture
def isolated_analyses_dir(app: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point webapp.save_folder_path to a temporary Analyses directory for tests."""
    webapp = app.config["WEBAPP"]
    analyses_dir = tmp_path / "Analyses"
    analyses_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(webapp, "save_folder_path", str(analyses_dir))
    return analyses_dir


def test_scheduler_file_lock_leader_election(tmp_path: Path) -> None:
    """Verify fcntl.flock allows only one Gunicorn worker to become the active scheduler leader."""
    lock_file = str(tmp_path / "scheduler.lock")

    leader_handle = acquire_scheduler_lock(lock_file)
    assert leader_handle is not None

    try:
        # While leader_handle holds the lock, a second attempt must return None
        follower_handle = acquire_scheduler_lock(lock_file)
        assert follower_handle is None

        class FollowerConfig(Config):
            TESTING = True
            SECRET_KEY = "test-secret"
            WTF_CSRF_ENABLED = False
            SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
            SCHEDULER_LOCK_FILE = lock_file

        follower_app = create_app(FollowerConfig)
        assert follower_app.config["SCHEDULER_IS_LEADER"] is False
    finally:
        leader_handle.close()

    # Once leader releases the lock, a new process can acquire it
    reacquired = acquire_scheduler_lock(lock_file)
    assert reacquired is not None
    reacquired.close()


def test_schedule_create_pause_resume_and_k8s_execution(
    app: Any,
    client: Any,
    isolated_analyses_dir: Path,
) -> None:
    """Verify cron/interval schedule creation, pause/resume toggle, and unified K8s Job execution."""
    webapp = app.config["WEBAPP"]
    scheduler = app.config["SCHEDULER"]
    app.config["K8S_SYNC_WATCHER"] = True

    webapp.save_flow(
        name="ScheduledHello",
        code='print("scheduled hello world")',
        description="Scheduled flow",
        parameters={"env": "prod"},
    )

    # 1. Create a cron schedule via POST /schedules/create
    resp_create = client.post(
        "/schedules/create",
        data={
            "job_id": "sched_hello_1",
            "flow_name": "ScheduledHello",
            "schedule_type": "cron",
            "cron_expr": "*/15 * * * *",
            "parameters": '{"env": "staging"}',
            "enabled": "1",
        },
        follow_redirects=True,
    )
    assert resp_create.status_code == 200
    assert b"ScheduledHello" in resp_create.data
    assert b"Active" in resp_create.data

    job = scheduler.get_job("sched_hello_1")
    assert job is not None
    assert job.next_run_time is not None

    # 2. Pause schedule via POST /schedules/sched_hello_1/toggle
    toggle_pause = client.post(
        "/schedules/sched_hello_1/toggle",
        headers={"Accept": "application/json"},
    )
    assert toggle_pause.status_code == 200
    assert toggle_pause.get_json()["state"] == "paused"
    assert scheduler.get_job("sched_hello_1").next_run_time is None

    sched_page_paused = client.get("/schedules/")
    assert b"Paused" in sched_page_paused.data

    # 3. Resume schedule via POST /schedules/sched_hello_1/toggle
    toggle_resume = client.post(
        "/schedules/sched_hello_1/toggle",
        headers={"Accept": "application/json"},
    )
    assert toggle_resume.status_code == 200
    assert toggle_resume.get_json()["state"] == "active"
    assert scheduler.get_job("sched_hello_1").next_run_time is not None

    # 4. Create an interval schedule and trigger execution through unified K8s Job pipeline
    client.post(
        "/schedules/create",
        data={
            "job_id": "sched_hello_interval",
            "flow_name": "ScheduledHello",
            "schedule_type": "interval",
            "interval_minutes": "30",
            "parameters": '{"batch": 5}',
            "enabled": "1",
        },
    )

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
                        "metadata": {"name": "pc-flow-sched-pod"},
                        "spec": {"nodeName": "worker-node-2"},
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
        patch.object(webapp, "_k8s_post", side_effect=fake_post),
        patch.object(webapp, "_k8s_get", side_effect=fake_get),
        patch.object(webapp, "_k8s_get_text", return_value="scheduled hello world\n"),
        patch.object(webapp, "_k8s_delete", return_value={}),
    ):
        run_now_resp = client.get("/run_schedule_now/?id=sched_hello_interval", follow_redirects=True)
        assert run_now_resp.status_code == 200

    assert len(submitted_jobs) == 1
    assert submitted_jobs[0]["spec"]["backoffLimit"] == 0

    with app.app_context():
        exe = Execution.query.filter_by(analysis_name="ScheduledHello").first()
        assert exe is not None
        assert exe.trigger_type == "scheduled"
        assert exe.status == "success"
        assert exe.node_name == "worker-node-2"
        assert "scheduled hello world" in (exe.log_text or "")


def test_execute_scheduled_flow_handles_missing_flow_and_delegates_cleanly(
    app: Any,
    isolated_analyses_dir: Path,
) -> None:
    """Verify execute_scheduled_flow calls launch_flow_run with trigger_type='scheduled' and handles missing flows."""
    from blueprints.catalog import execute_scheduled_flow

    webapp = app.config["WEBAPP"]
    webapp.save_flow(
        name="ValidSchedFlow",
        code='print("ok")',
        parameters={"k": "v"},
    )

    with patch.object(webapp, "launch_flow_run", return_value="mock-exe") as mock_launch:
        result = execute_scheduled_flow(
            name="ValidSchedFlow",
            parameters={"k": "override"},
            pip_requirements=["httpx"],
            image="python:3.11-slim",
            app=app,
        )
        assert result == "mock-exe"
        mock_launch.assert_called_once()
        call_kwargs = mock_launch.call_args.kwargs
        assert call_kwargs["flow_name"] == "ValidSchedFlow"
        assert call_kwargs["parameters"] == {"k": "override"}
        assert call_kwargs["pip_requirements"] == ["httpx"]
        assert call_kwargs["image"] == "python:3.11-slim"
        assert call_kwargs["trigger_type"] == "scheduled"

    # Calling with a non-existent flow must log an error and return None without raising
    missing_result = execute_scheduled_flow(
        name="NonExistentFlowXYZ",
        parameters={},
        app=app,
    )
    assert missing_result is None

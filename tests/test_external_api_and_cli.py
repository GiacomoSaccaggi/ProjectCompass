"""
████████╗███████╗░██████╗████████╗░░░░░░░█████╗░██████╗░██╗░░░░░░░█████╗░██╗░░░░░██╗
╚══██╔══╝██╔════╝██╔════╝╚══██╔══╝░░░░░░██╔══██╗██╔══██╗██║░░░░░░██╔══██╗██║░░░░░██║
░░░██║░░░█████╗░░╚█████╗░░░░██║░░░█████╗███████║██████╔╝██║█████╗██║░░╚═╝██║░░░░░██║
░░░██║░░░██╔══╝░░░╚═══██╗░░░██║░░░╚════╝██╔══██║██╔═══╝░██║╚════╝██║░░██╗██║░░░░░██║
░░░██║░░░███████╗██████╔╝░░░██║░░░░░░░░░██║░░██║██║░░░░░██║░░░░░░╚█████╔╝███████╗██║
░░░╚═╝░░░╚══════╝╚═════╝░░░░╚═╝░░░░░░░░░╚═╝░░╚═╝╚═╝░░░░░╚═╝░░░░░░░╚════╝░╚══════╝╚═╝
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import httpx
import pytest
from werkzeug.security import generate_password_hash

from models import User, db
from scripts.compass_cli import CompassCliEntrypoint
from utils.cli_utils import BaseCompassCliClient, CompassCliError, CompassCliRunner


def _basic_auth_header(username: str, password: str) -> dict[str, str]:
    """Build an HTTP Basic Authorization header."""
    encoded = base64.b64encode(f"{username}:{password}".encode()).decode("ascii")
    return {
        "Authorization": f"Basic {encoded}",
        "Accept": "application/json",
    }


@pytest.fixture
def isolated_analyses_dir(app: Any, tmp_path: Path) -> Path:
    """Point the webapp's Analyses directory to an isolated temporary path."""
    webapp = app.config["WEBAPP"]
    orig_dir = webapp.save_folder_path
    temp_analyses = tmp_path / "Analyses"
    temp_analyses.mkdir(parents=True, exist_ok=True)
    webapp.save_folder_path = str(temp_analyses)
    yield temp_analyses
    webapp.save_folder_path = orig_dir


def test_http_basic_auth_and_env_bearer_token(
    app: Any,
    unauth_client: Any,
    isolated_analyses_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify HTTP Basic Auth (DB User & env admin) and API_AUTH_TOKEN Bearer Auth across routes."""
    with app.app_context():
        editor = User(
            username="ext_editor",
            password_hash=generate_password_hash("editor_secret"),
            role="editor",
        )
        viewer = User(
            username="ext_viewer",
            password_hash=generate_password_hash("viewer_secret"),
            role="viewer",
        )
        db.session.add_all([editor, viewer])
        db.session.commit()

    # 1. Unauthenticated JSON request to protected route returns 401 JSON
    unauth_resp = unauth_client.get("/flows", headers={"Accept": "application/json"})
    assert unauth_resp.status_code == 401
    assert "error" in unauth_resp.get_json()

    # 2. Invalid Basic Auth returns 401 JSON
    bad_basic = unauth_client.get(
        "/flows",
        headers=_basic_auth_header("ext_editor", "wrong_password"),
    )
    assert bad_basic.status_code == 401
    assert "Invalid basic credentials" in bad_basic.get_json()["error"]

    # 3. Valid DB User Basic Auth succeeds on /flows/save and /flows
    save_resp = unauth_client.post(
        "/flows/save",
        json={
            "name": "BasicAuthFlow",
            "code": 'print("hello from basic auth")\n',
            "description": "Created via Basic Auth",
            "parameters": {"env": "test"},
            "secret_refs": ["cluster-creds"],
        },
        headers=_basic_auth_header("ext_editor", "editor_secret"),
    )
    assert save_resp.status_code == 200
    saved_data = save_resp.get_json()
    assert saved_data["name"] == "BasicAuthFlow"
    assert saved_data["secret_refs"] == ["cluster-creds"]

    # 4. Viewer via Basic Auth can read GET /flows but gets 403 JSON on POST /flows/save
    viewer_get = unauth_client.get(
        "/flows/BasicAuthFlow",
        headers=_basic_auth_header("ext_viewer", "viewer_secret"),
    )
    assert viewer_get.status_code == 200
    assert viewer_get.get_json()["name"] == "BasicAuthFlow"

    viewer_post = unauth_client.post(
        "/flows/save",
        json={"name": "BlockedFlow", "code": "print(1)"},
        headers=_basic_auth_header("ext_viewer", "viewer_secret"),
    )
    assert viewer_post.status_code == 403
    assert "Forbidden" in viewer_post.get_json()["error"]

    # 5. Mint a Bearer token via POST /api/tokens using HTTP Basic Auth
    tok_resp = unauth_client.post(
        "/api/tokens",
        json={"name": "External Automation Token"},
        headers=_basic_auth_header("ext_editor", "editor_secret"),
    )
    assert tok_resp.status_code == 200
    minted_token = tok_resp.get_json()["token"]
    assert minted_token

    # Use minted Bearer token on /flows
    bearer_resp = unauth_client.get(
        "/flows",
        headers={
            "Authorization": f"Bearer {minted_token}",
            "Accept": "application/json",
        },
    )
    assert bearer_resp.status_code == 200
    assert any(f["name"] == "BasicAuthFlow" for f in bearer_resp.get_json()["flows"])

    # 6. Static environment variable API_AUTH_TOKEN works immediately as Bearer token
    monkeypatch.setenv("API_AUTH_TOKEN", "bootstrap-cluster-token-999")
    static_resp = unauth_client.get(
        "/flows/BasicAuthFlow",
        headers={
            "Authorization": "Bearer bootstrap-cluster-token-999",
            "Accept": "application/json",
        },
    )
    assert static_resp.status_code == 200
    assert static_resp.get_json()["name"] == "BasicAuthFlow"

    # 7. Fallback ADMIN_USERNAME / ADMIN_PASSWORD_HASH works with Basic Auth and POST /api/tokens
    monkeypatch.setenv("ADMIN_USERNAME", "cluster_admin")
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", generate_password_hash("super_admin_pw"))
    admin_tok_resp = unauth_client.post(
        "/api/tokens",
        json={"name": "Admin Bootstrap Token"},
        headers=_basic_auth_header("cluster_admin", "super_admin_pw"),
    )
    assert admin_tok_resp.status_code == 200
    assert "token" in admin_tok_resp.get_json()


def test_json_api_parity_for_flows_analyses_chains_runs_workers_and_schedules(
    app: Any,
    unauth_client: Any,
    isolated_analyses_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify full JSON request/response parity across all operational endpoints."""
    monkeypatch.setenv("API_AUTH_TOKEN", "json-api-token")
    app.config["K8S_SYNC_WATCHER"] = True
    webapp = app.config["WEBAPP"]

    headers = {
        "Authorization": "Bearer json-api-token",
        "Accept": "application/json",
    }

    def fake_k8s_get(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if path == "/api/v1/nodes":
            return {
                "items": [
                    {
                        "metadata": {"name": "k0s-worker-1", "uid": "uid-1"},
                        "status": {
                            "conditions": [{"type": "Ready", "status": "True"}],
                            "addresses": [{"type": "InternalIP", "address": "10.0.0.21"}],
                            "capacity": {"cpu": "4", "memory": "8Gi"},
                            "allocatable": {"cpu": "4", "memory": "8Gi"},
                            "nodeInfo": {"kubeletVersion": "v1.30.2+k0s"},
                        },
                    }
                ]
            }
        if path.endswith("/pods"):
            return {
                "items": [
                    {
                        "metadata": {"name": "pc-flow-pod-1"},
                        "spec": {"nodeName": "k0s-worker-1"},
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
        patch.object(webapp, "_k8s_get", side_effect=fake_k8s_get),
        patch.object(webapp, "_k8s_get_text", return_value="json api output\n"),
        patch.object(webapp, "_fetch_node_metrics", return_value={}),
        patch.object(webapp, "_k8s_post", return_value={"metadata": {"name": "ok"}}),
        patch.object(webapp, "_k8s_delete", return_value={"status": "Success"}),
    ):
        # 1. GET /workers JSON
        workers_resp = unauth_client.get("/workers", headers=headers)
        assert workers_resp.status_code == 200
        workers_json = workers_resp.get_json()
        assert workers_json["ready"] == 1
        assert workers_json["nodes"][0]["name"] == "k0s-worker-1"

        # 2. POST /flows/save & POST /flows/<name>/run JSON
        unauth_client.post(
            "/flows/save",
            json={"name": "ApiFlow1", "code": 'print("step 1")\n'},
            headers=headers,
        )
        run_resp = unauth_client.post(
            "/flows/ApiFlow1/run",
            json={"parameters": {"batch": 42}, "wait": True},
            headers=headers,
        )
        assert run_resp.status_code == 200
        run_data = run_resp.get_json()
        run_id = run_data["run_id"]
        assert run_data["status"] == "success"
        assert "json api output" in run_data["log_text"]

        # 3. POST /api/analyses/<name>/run JSON
        analysis_run_resp = unauth_client.post(
            "/api/analyses/ApiFlow1/run",
            json={"parameters": {"mode": "external"}, "wait": True},
            headers=headers,
        )
        assert analysis_run_resp.status_code == 200
        analysis_run_json = analysis_run_resp.get_json()
        assert analysis_run_json["status"] == "success"
        assert analysis_run_json["analysis_name"] == "ApiFlow1"

        # 4. GET /runs, GET /runs/<id>, POST /runs/<id>/abort JSON
        runs_list_resp = unauth_client.get("/runs?flow_name=ApiFlow1", headers=headers)
        assert runs_list_resp.status_code == 200
        assert len(runs_list_resp.get_json()["runs"]) >= 2

        run_detail_resp = unauth_client.get(f"/runs/{run_id}", headers=headers)
        assert run_detail_resp.status_code == 200
        assert run_detail_resp.get_json()["run_id"] == run_id

        with app.app_context():
            from models import Execution

            running_exe = Execution(
                analysis_name="ApiFlow1",
                status="running",
                job_name="pc-flow-job-active",
            )
            db.session.add(running_exe)
            db.session.commit()
            running_id = running_exe.id

        abort_resp = unauth_client.post(f"/runs/{running_id}/abort", headers=headers)
        assert abort_resp.status_code == 200
        assert abort_resp.get_json()["status"] == "aborted"

        # 5. POST /chains/save, GET /chains, POST /chains/<name>/run, POST /chains/<name>/delete JSON
        chain_save_resp = unauth_client.post(
            "/chains/save",
            json={"name": "ApiChain", "flow_names": ["ApiFlow1"], "description": "JSON chain"},
            headers=headers,
        )
        assert chain_save_resp.status_code == 200
        assert chain_save_resp.get_json()["name"] == "ApiChain"

        chains_list_resp = unauth_client.get("/chains", headers=headers)
        assert chains_list_resp.status_code == 200
        assert any(c["name"] == "ApiChain" for c in chains_list_resp.get_json()["chains"])

        chain_run_resp = unauth_client.post(
            "/chains/ApiChain/run",
            json={"parameters": {"k": "v"}, "wait": True},
            headers=headers,
        )
        assert chain_run_resp.status_code == 200
        assert chain_run_resp.get_json()["status"] == "success"

        # 6. POST /schedules/create, GET /schedules/, POST /schedules/<id>/toggle JSON
        sched_create_resp = unauth_client.post(
            "/schedules/create",
            json={
                "flow_name": "ApiFlow1",
                "schedule_type": "interval",
                "interval_minutes": 15,
                "job_id": "json_sched_1",
            },
            headers=headers,
        )
        assert sched_create_resp.status_code == 200
        assert sched_create_resp.get_json()["job_id"] == "json_sched_1"
        assert sched_create_resp.get_json()["state"] == "active"

        sched_list_resp = unauth_client.get("/schedules/", headers=headers)
        assert sched_list_resp.status_code == 200
        assert any(s["id"] == "json_sched_1" for s in sched_list_resp.get_json()["schedules"])

        sched_toggle_resp = unauth_client.post("/schedules/json_sched_1/toggle", headers=headers)
        assert sched_toggle_resp.status_code == 200
        assert sched_toggle_resp.get_json()["state"] == "paused"

        chain_del_resp = unauth_client.post("/chains/ApiChain/delete", headers=headers)
        assert chain_del_resp.status_code == 200
        assert chain_del_resp.get_json()["deleted"] == "ApiChain"


def test_standalone_compass_cli_runner_with_basic_and_bearer_auth(
    app: Any,
    isolated_analyses_dir: Path,
    tmp_path: Path,
) -> None:
    """Verify the OOP CompassCliRunner and CompassCliEntrypoint over WSGI transport."""
    assert issubclass(CompassCliRunner, BaseCompassCliClient)
    assert issubclass(CompassCliEntrypoint, CompassCliRunner)

    app.config["K8S_SYNC_WATCHER"] = True
    webapp = app.config["WEBAPP"]

    with app.app_context():
        cli_user = User(
            username="cli_operator",
            password_hash=generate_password_hash("cli_pass_123"),
            role="admin",
        )
        db.session.add(cli_user)
        db.session.commit()

    wsgi_transport = httpx.WSGITransport(app=app)
    cli_secret = "cli_pass_123"  # noqa: S105
    cli = CompassCliRunner(
        base_url="http://compass.local",
        username="cli_operator",
        password=cli_secret,
        transport=wsgi_transport,
    )
    assert cli.client_type() == "compass-cli-runner"

    script_file = tmp_path / "my_cli_flow.py"
    script_file.write_text('print("executed from cli file")\n', encoding="utf-8")

    def fake_cli_k8s_get(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if path.endswith("/pods"):
            return {
                "items": [
                    {
                        "metadata": {"name": "pc-cli-pod-1"},
                        "spec": {"nodeName": "worker-node-a"},
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
        return {"items": []}

    with (
        patch.object(webapp, "_k8s_get", side_effect=fake_cli_k8s_get),
        patch.object(webapp, "_k8s_get_text", return_value="executed from cli file\n"),
        patch.object(webapp, "_fetch_node_metrics", return_value={}),
        patch.object(webapp, "_k8s_post", return_value={"metadata": {"name": "ok"}}),
        patch.object(webapp, "_k8s_delete", return_value={"status": "Success"}),
    ):
        # 1. Push flow from local file via CLI argv
        code, out = cli.execute_cli(
            [
                "flows",
                "push",
                "CliPushedFlow",
                str(script_file),
                "--description",
                "CLI flow",
                "--params",
                '{"limit": 10}',
                "--secret-refs",
                "sec-a,sec-b",
                "--message",
                "v1 from cli",
            ]
        )
        assert code == 0
        pushed = json.loads(out)
        assert pushed["name"] == "CliPushedFlow"
        assert pushed["secret_refs"] == ["sec-a", "sec-b"]

        # 2. Run flow via CLI argv with --wait
        code, run_out = cli.execute_cli(
            ["flows", "run", "CliPushedFlow", "--params", '{"limit": 99}', "--wait"]
        )
        assert code == 0
        run_payload = json.loads(run_out)
        run_id = run_payload["run_id"]
        assert run_payload["status"] == "success"

        # 3. Fetch logs via CLI (`runs logs <run_id>` and `--follow`)
        code, logs_out = cli.execute_cli(["runs", "logs", str(run_id)])
        assert code == 0
        assert "executed from cli file" in logs_out

        code, sse_logs_out = cli.execute_cli(["runs", "logs", str(run_id), "--follow"])
        assert code == 0
        assert "executed from cli file" in sse_logs_out

        # 4. Run via `analyses run` subcommand
        code, ana_out = cli.execute_cli(["analyses", "run", "CliPushedFlow", "--wait"])
        assert code == 0
        assert json.loads(ana_out)["status"] == "success"

        # 5. Create and run a chain via CLI
        code, ch_save_out = cli.execute_cli(
            ["chains", "save", "CliChain", "CliPushedFlow", "--description", "Single step CLI chain"]
        )
        assert code == 0
        assert json.loads(ch_save_out)["name"] == "CliChain"

        code, ch_run_out = cli.execute_cli(["chains", "run", "CliChain", "--wait"])
        assert code == 0
        assert json.loads(ch_run_out)["status"] == "success"

        # 6. Create, list, and toggle schedule via CLI
        code, sch_out = cli.execute_cli(
            [
                "schedules",
                "create",
                "--flow",
                "CliPushedFlow",
                "--type",
                "cron",
                "--cron",
                "0 6 * * *",
                "--job-id",
                "cli_daily_job",
            ]
        )
        assert code == 0
        assert json.loads(sch_out)["job_id"] == "cli_daily_job"

        code, toggle_out = cli.execute_cli(["schedules", "toggle", "cli_daily_job"])
        assert code == 0
        assert json.loads(toggle_out)["state"] == "paused"

        # 7. Mint a Bearer token via CLI and use it with a token-authenticated runner
        code, tok_out = cli.execute_cli(["tokens", "create", "--name", "CLI Minted"])
        assert code == 0
        new_token = json.loads(tok_out)["token"]

        token_cli = CompassCliEntrypoint(
            base_url="http://compass.local",
            token=new_token,
            transport=wsgi_transport,
        )
        exit_code = token_cli.run_from_sys_argv(["workers", "list"])
        assert exit_code == 0

        # 8. Verify error handling on non-existent flow
        with pytest.raises(CompassCliError):
            token_cli.get_flow("NonExistentFlow999")

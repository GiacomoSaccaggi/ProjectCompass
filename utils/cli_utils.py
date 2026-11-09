"""
░█████╗░██╗░░░░░██╗░░░░░░██╗░░░██╗████████╗██╗██╗░░░░░░██████╗
██╔══██╗██║░░░░░██║░░░░░░██║░░░██║╚══██╔══╝██║██║░░░░░██╔════╝
██║░░╚═╝██║░░░░░██║█████╗██║░░░██║░░░██║░░░██║██║░░░░░╚█████╗░
██║░░██╗██║░░░░░██║╚════╝██║░░░██║░░░██║░░░██║██║░░░░░░╚═══██╗
╚█████╔╝███████╗██║░░░░░░╚██████╔╝░░░██║░░░██║███████╗██████╔╝
░╚════╝░╚══════╝╚═╝░░░░░░░╚═════╝░░░░╚═╝░░░╚═╝╚══════╝╚═════╝░
"""

from __future__ import annotations

import argparse
import base64
import json
import os
from abc import ABC, abstractmethod
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx


class CompassCliError(RuntimeError):
    """Raised when the ProjectCompass HTTP API returns an error or is unreachable."""


class BaseCompassCliClient(ABC):
    """Abstract parent class for external HTTP communication with ProjectCompass.

    Encapsulates endpoint URL normalization, HTTP Basic Authentication
    (`username:password`), and Bearer Token Authentication (`API_AUTH_TOKEN`
    or `ApiToken`) so child CLI runners can invoke REST endpoints without
    managing low-level transport or header assembly.
    """

    def __init__(
        self,
        base_url: str | None = None,
        username: str | None = None,
        password: str | None = None,
        token: str | None = None,
        timeout: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        """Initialize connection credentials and transport configuration."""
        resolved_url = (
            base_url
            or os.environ.get("COMPASS_URL")
            or "http://localhost:8080"
        ).strip()
        self._base_url: str = resolved_url.rstrip("/")
        self._username: str = (
            username
            if username is not None
            else os.environ.get("COMPASS_USER", "")
        ).strip()
        self._password: str = (
            password
            if password is not None
            else os.environ.get("COMPASS_PASSWORD", "")
        )
        self._token: str = (
            token
            if token is not None
            else os.environ.get("COMPASS_TOKEN", os.environ.get("API_AUTH_TOKEN", ""))
        ).strip()
        self._timeout: float = timeout
        self._transport: httpx.BaseTransport | None = transport

    @abstractmethod
    def client_type(self) -> str:
        """Return the concrete CLI client type identifier."""

    def _build_headers(self, extra_headers: dict[str, str] | None = None) -> dict[str, str]:
        """Construct HTTP headers with Accept: application/json and Basic/Bearer auth."""
        headers: dict[str, str] = {
            "Accept": "application/json",
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        elif self._username:
            raw_creds = f"{self._username}:{self._password}".encode()
            encoded = base64.b64encode(raw_creds).decode("ascii")
            headers["Authorization"] = f"Basic {encoded}"
        if extra_headers:
            headers.update(extra_headers)
        return headers

    def _request(
        self,
        method: str,
        path: str,
        json_body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Perform an authenticated JSON HTTP request against ProjectCompass."""
        url = f"{self._base_url}/{path.lstrip('/')}"
        headers = self._build_headers(
            {"Content-Type": "application/json"} if json_body is not None else None
        )
        try:
            with httpx.Client(timeout=self._timeout, transport=self._transport) as client:
                response = client.request(
                    method=method.upper(),
                    url=url,
                    headers=headers,
                    json=json_body,
                    params=params,
                )
        except httpx.HTTPError as exc:
            raise CompassCliError(f"Connection to ProjectCompass at '{url}' failed: {exc}") from exc

        if response.status_code >= 400:
            detail = response.text.strip()
            try:
                err_json = response.json()
                if isinstance(err_json, dict) and err_json.get("error"):
                    detail = str(err_json["error"])
            except ValueError:
                pass
            raise CompassCliError(
                f"HTTP {response.status_code} on {method.upper()} {path}: {detail}"
            )

        try:
            parsed = response.json()
            return parsed if isinstance(parsed, dict) else {"data": parsed}
        except ValueError as exc:
            raise CompassCliError(
                f"Expected JSON response from {method.upper()} {path}, got: {response.text[:200]}"
            ) from exc

    def _stream_sse_lines(self, path: str) -> Iterator[str]:
        """Stream Server-Sent Event log lines from an SSE endpoint."""
        url = f"{self._base_url}/{path.lstrip('/')}"
        headers = self._build_headers({"Accept": "text/event-stream"})
        try:
            with (
                httpx.Client(timeout=self._timeout, transport=self._transport) as client,
                client.stream("GET", url, headers=headers) as response,
            ):
                if response.status_code >= 400:
                    body = response.read().decode("utf-8", errors="replace").strip()
                    raise CompassCliError(f"HTTP {response.status_code} on GET {path}: {body}")
                for raw_line in response.iter_lines():
                    if raw_line.startswith("data: "):
                        yield raw_line[6:]
        except httpx.HTTPError as exc:
            raise CompassCliError(f"SSE stream error on '{url}': {exc}") from exc


class CompassCliRunner(BaseCompassCliClient):
    """Concrete CLI runner for managing Workers, Flows, Runs, Analyses, and Schedules."""

    def client_type(self) -> str:
        """Identify this concrete runner implementation."""
        return "compass-cli-runner"

    @staticmethod
    def _parse_json_or_kv(raw: str | dict[str, Any] | None) -> dict[str, Any]:
        """Parse a JSON string or KEY=VALUE lines into a dictionary."""
        if raw is None:
            return {}
        if isinstance(raw, dict):
            return dict(raw)
        text = str(raw).strip()
        if not text:
            return {}
        try:
            loaded = json.loads(text)
            if isinstance(loaded, dict):
                return loaded
        except ValueError:
            pass
        result: dict[str, Any] = {}
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            k, v = stripped.split("=", 1)
            result[k.strip()] = v.strip()
        return result

    @staticmethod
    def _parse_csv_list(raw: str | list[str] | None) -> list[str]:
        """Parse a comma-separated string or list into a clean list of strings."""
        if raw is None:
            return []
        if isinstance(raw, list):
            return [str(x).strip() for x in raw if str(x).strip()]
        return [part.strip() for part in str(raw).replace("\n", ",").split(",") if part.strip()]

    def create_token(self, name: str = "CLI Token") -> dict[str, Any]:
        """Mint a new Bearer API token using current Basic or session credentials."""
        return self._request("POST", "/api/tokens", json_body={"name": name})

    def list_workers(self) -> dict[str, Any]:
        """Fetch cluster worker nodes summary (`Ready`, `NotReady`, `Removed`)."""
        return self._request("GET", "/workers")

    def list_flows(self) -> dict[str, Any]:
        """List all Python flows stored in ProjectCompass."""
        return self._request("GET", "/flows")

    def get_flow(self, name: str) -> dict[str, Any]:
        """Retrieve a specific flow's code, configuration, and version history."""
        return self._request("GET", f"/flows/{name}")

    def push_flow(
        self,
        name: str,
        code_or_file: str,
        description: str = "",
        parameters: dict[str, Any] | str | None = None,
        pip_requirements: list[str] | str | None = None,
        env_vars: dict[str, str] | str | None = None,
        secret_refs: list[str] | str | None = None,
        image: str = "",
        version_message: str = "",
    ) -> dict[str, Any]:
        """Create or update a flow from a local Python file path or inline script string."""
        candidate_path = Path(code_or_file)
        if candidate_path.is_file():
            code = candidate_path.read_text(encoding="utf-8")
        else:
            code = code_or_file

        body: dict[str, Any] = {
            "name": name,
            "code": code,
            "description": description,
            "parameters": self._parse_json_or_kv(parameters),
            "pip_requirements": self._parse_csv_list(pip_requirements),
            "env_vars": self._parse_json_or_kv(env_vars),
            "secret_refs": self._parse_csv_list(secret_refs),
            "image": image,
            "version_message": version_message,
        }
        return self._request("POST", "/flows/save", json_body=body)

    def run_flow(
        self,
        name: str,
        parameters: dict[str, Any] | str | None = None,
        pip_requirements: list[str] | str | None = None,
        env_vars: dict[str, str] | str | None = None,
        secret_refs: list[str] | str | None = None,
        image: str | None = None,
        wait: bool = False,
    ) -> dict[str, Any]:
        """Trigger a flow execution as an isolated Kubernetes Job."""
        body: dict[str, Any] = {
            "parameters": self._parse_json_or_kv(parameters),
            "wait": bool(wait),
        }
        if pip_requirements is not None:
            body["pip_requirements"] = self._parse_csv_list(pip_requirements)
        if env_vars is not None:
            body["env_vars"] = self._parse_json_or_kv(env_vars)
        if secret_refs is not None:
            body["secret_refs"] = self._parse_csv_list(secret_refs)
        if image:
            body["image"] = image
        return self._request("POST", f"/flows/{name}/run", json_body=body)

    def run_analysis(
        self,
        name: str,
        parameters: dict[str, Any] | str | None = None,
        wait: bool = False,
    ) -> dict[str, Any]:
        """Trigger an analysis or flow via `/api/analyses/<name>/run`."""
        body: dict[str, Any] = {
            "parameters": self._parse_json_or_kv(parameters),
            "wait": bool(wait),
        }
        return self._request("POST", f"/api/analyses/{name}/run", json_body=body)

    def list_runs(self, flow_name: str | None = None, limit: int = 25) -> dict[str, Any]:
        """List recent execution runs."""
        params: dict[str, Any] = {"limit": limit}
        if flow_name:
            params["flow_name"] = flow_name
        return self._request("GET", "/runs", params=params)

    def get_run(self, run_id: int) -> dict[str, Any]:
        """Fetch execution status, metadata, and persisted logs for `run_id`."""
        return self._request("GET", f"/runs/{int(run_id)}")

    def get_run_logs(self, run_id: int, follow: bool = False) -> str:
        """Retrieve stdout/stderr logs for `run_id`, optionally streaming via SSE."""
        if follow:
            lines = list(self._stream_sse_lines(f"/runs/{int(run_id)}/stream"))
            return "\n".join(lines)
        details = self.get_run(run_id)
        return str(details.get("log_text") or "")

    def abort_run(self, run_id: int) -> dict[str, Any]:
        """Abort an in-progress flow run."""
        return self._request("POST", f"/runs/{int(run_id)}/abort")

    def list_schedules(self) -> dict[str, Any]:
        """List all configured cron and interval schedules."""
        return self._request("GET", "/schedules/")

    def create_schedule(
        self,
        flow_name: str | None = None,
        schedule_type: str = "cron",
        cron_expr: str = "0 * * * *",
        interval_seconds: int = 0,
        interval_minutes: int = 0,
        parameters: dict[str, Any] | str | None = None,
        job_id: str | None = None,
        enabled: bool = True,
    ) -> dict[str, Any]:
        """Create a cron or interval schedule for a flow."""
        body: dict[str, Any] = {
            "flow_name": flow_name or "",
            "schedule_type": schedule_type,
            "cron_expr": cron_expr,
            "interval_seconds": interval_seconds,
            "interval_minutes": interval_minutes,
            "parameters": self._parse_json_or_kv(parameters),
            "enabled": enabled,
        }
        if job_id:
            body["job_id"] = job_id
        return self._request("POST", "/schedules/create", json_body=body)

    def toggle_schedule(self, job_id: str) -> dict[str, Any]:
        """Pause an active schedule or resume a paused schedule."""
        return self._request("POST", f"/schedules/{job_id}/toggle")

    @staticmethod
    def build_arg_parser() -> argparse.ArgumentParser:
        """Build the argument parser for the standalone ProjectCompass CLI."""
        parser = argparse.ArgumentParser(
            prog="compass_cli",
            description="ProjectCompass external CLI for k0s Workers, Flows, Runs, and Schedules.",
        )
        parser.add_argument("--url", default=None, help="ProjectCompass base URL (or COMPASS_URL)")
        parser.add_argument("--user", default=None, help="HTTP Basic Auth username (or COMPASS_USER)")
        parser.add_argument("--password", default=None, help="HTTP Basic Auth password (or COMPASS_PASSWORD)")
        parser.add_argument("--token", default=None, help="Bearer token (or COMPASS_TOKEN / API_AUTH_TOKEN)")

        subparsers = parser.add_subparsers(dest="resource", required=True)

        # workers
        workers_p = subparsers.add_parser("workers", help="Inspect k0s worker nodes")
        workers_sub = workers_p.add_subparsers(dest="action", required=True)
        workers_sub.add_parser("list", help="List worker nodes and cluster status")

        # flows
        flows_p = subparsers.add_parser("flows", help="Manage and execute Python flows")
        flows_sub = flows_p.add_subparsers(dest="action", required=True)
        flows_sub.add_parser("list", help="List all flows")

        flows_get = flows_sub.add_parser("get", help="Get flow details and code")
        flows_get.add_argument("name", help="Flow name")

        flows_push = flows_sub.add_parser("push", help="Create or update a flow")
        flows_push.add_argument("name", help="Flow name")
        flows_push.add_argument("source", help="Path to .py file or inline Python code")
        flows_push.add_argument("--description", default="", help="Flow description")
        flows_push.add_argument("--params", default="{}", help="Default parameters (JSON or KEY=VALUE)")
        flows_push.add_argument("--pip", default="", help="Comma-separated pip packages")
        flows_push.add_argument("--secret-refs", default="", help="Comma-separated K8s Secret names")
        flows_push.add_argument("--image", default="", help="Container image override")
        flows_push.add_argument("--message", default="", help="Version commit message")

        flows_run = flows_sub.add_parser("run", help="Launch a flow as a Kubernetes Job")
        flows_run.add_argument("name", help="Flow name")
        flows_run.add_argument("--params", default="{}", help="Run parameters (JSON or KEY=VALUE)")
        flows_run.add_argument("--pip", default=None, help="Comma-separated pip packages override")
        flows_run.add_argument("--secret-refs", default=None, help="Comma-separated K8s Secret names override")
        flows_run.add_argument("--image", default=None, help="Container image override")
        flows_run.add_argument("--wait", action="store_true", help="Wait for Job completion")

        # analyses
        analyses_p = subparsers.add_parser("analyses", help="Trigger catalog analyses")
        analyses_sub = analyses_p.add_subparsers(dest="action", required=True)
        analyses_run = analyses_sub.add_parser("run", help="Run an analysis by name")
        analyses_run.add_argument("name", help="Analysis name")
        analyses_run.add_argument("--params", default="{}", help="Run parameters (JSON)")
        analyses_run.add_argument("--wait", action="store_true", help="Wait for completion")

        # runs
        runs_p = subparsers.add_parser("runs", help="Inspect and control flow runs")
        runs_sub = runs_p.add_subparsers(dest="action", required=True)
        runs_list = runs_sub.add_parser("list", help="List recent runs")
        runs_list.add_argument("--flow", default=None, help="Filter by flow name")
        runs_list.add_argument("--limit", type=int, default=25, help="Max runs to return")

        runs_get = runs_sub.add_parser("get", help="Get run metadata and logs")
        runs_get.add_argument("run_id", type=int, help="Execution run_id")

        runs_logs = runs_sub.add_parser("logs", help="Print or stream run stdout/stderr logs")
        runs_logs.add_argument("run_id", type=int, help="Execution run_id")
        runs_logs.add_argument("--follow", action="store_true", help="Stream via SSE until completion")

        runs_abort = runs_sub.add_parser("abort", help="Abort a running Job")
        runs_abort.add_argument("run_id", type=int, help="Execution run_id")

        # schedules
        sched_p = subparsers.add_parser("schedules", help="Manage cron and interval schedules")
        sched_sub = sched_p.add_subparsers(dest="action", required=True)
        sched_sub.add_parser("list", help="List schedules")

        sched_create = sched_sub.add_parser("create", help="Create a schedule for a flow")
        sched_create.add_argument("--flow", default=None, help="Flow name to schedule")
        sched_create.add_argument("--type", default="cron", choices=["cron", "interval"], help="Trigger type")
        sched_create.add_argument("--cron", default="0 * * * *", help="5-field crontab expression")
        sched_create.add_argument("--seconds", type=int, default=0, help="Interval seconds")
        sched_create.add_argument("--minutes", type=int, default=0, help="Interval minutes")
        sched_create.add_argument("--params", default="{}", help="JSON parameters")
        sched_create.add_argument("--job-id", default=None, help="Optional explicit schedule ID")
        sched_create.add_argument("--paused", action="store_true", help="Create schedule in paused state")

        sched_toggle = sched_sub.add_parser("toggle", help="Pause or resume a schedule")
        sched_toggle.add_argument("job_id", help="Schedule job_id")

        # tokens
        tok_p = subparsers.add_parser("tokens", help="Mint API Bearer tokens")
        tok_sub = tok_p.add_subparsers(dest="action", required=True)
        tok_create = tok_sub.add_parser("create", help="Create a new API token")
        tok_create.add_argument("--name", default="CLI Token", help="Token label")

        return parser

    def execute_cli(self, argv: list[str] | None = None) -> tuple[int, str]:
        """Parse CLI arguments, execute the matching API call, and return `(exit_code, output)`."""
        parser = self.build_arg_parser()
        args = parser.parse_args(argv)

        if args.url:
            self._base_url = str(args.url).rstrip("/")
        if args.user is not None:
            self._username = str(args.user).strip()
        if args.password is not None:
            self._password = str(args.password)
        if args.token is not None:
            self._token = str(args.token).strip()

        try:
            if args.resource == "workers" and args.action == "list":
                res = self.list_workers()
            elif args.resource == "flows":
                if args.action == "list":
                    res = self.list_flows()
                elif args.action == "get":
                    res = self.get_flow(args.name)
                elif args.action == "push":
                    res = self.push_flow(
                        name=args.name,
                        code_or_file=args.source,
                        description=args.description,
                        parameters=args.params,
                        pip_requirements=args.pip,
                        secret_refs=args.secret_refs,
                        image=args.image,
                        version_message=args.message,
                    )
                elif args.action == "run":
                    res = self.run_flow(
                        name=args.name,
                        parameters=args.params,
                        pip_requirements=args.pip,
                        secret_refs=args.secret_refs,
                        image=args.image,
                        wait=args.wait,
                    )
                else:
                    raise CompassCliError(f"Unsupported flows action: {args.action}")
            elif args.resource == "analyses" and args.action == "run":
                res = self.run_analysis(name=args.name, parameters=args.params, wait=args.wait)
            elif args.resource == "runs":
                if args.action == "list":
                    res = self.list_runs(flow_name=args.flow, limit=args.limit)
                elif args.action == "get":
                    res = self.get_run(args.run_id)
                elif args.action == "logs":
                    logs_text = self.get_run_logs(args.run_id, follow=args.follow)
                    return 0, logs_text
                elif args.action == "abort":
                    res = self.abort_run(args.run_id)
                else:
                    raise CompassCliError(f"Unsupported runs action: {args.action}")
            elif args.resource == "schedules":
                if args.action == "list":
                    res = self.list_schedules()
                elif args.action == "create":
                    res = self.create_schedule(
                        flow_name=args.flow,
                        schedule_type=args.type,
                        cron_expr=args.cron,
                        interval_seconds=args.seconds,
                        interval_minutes=args.minutes,
                        parameters=args.params,
                        job_id=args.job_id,
                        enabled=not args.paused,
                    )
                elif args.action == "toggle":
                    res = self.toggle_schedule(args.job_id)
                else:
                    raise CompassCliError(f"Unsupported schedules action: {args.action}")
            elif args.resource == "tokens" and args.action == "create":
                res = self.create_token(name=args.name)
            else:
                raise CompassCliError(f"Unknown command: {args.resource} {getattr(args, 'action', '')}")
        except CompassCliError as exc:
            return 1, json.dumps({"error": str(exc)}, indent=2)

        return 0, json.dumps(res, indent=2)

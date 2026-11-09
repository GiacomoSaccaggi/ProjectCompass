"""
░██╗░░██╗░█████╗░░██████╗░░░░░░██████╗░██████╗░
░██║░██╔╝██╔══██╗██╔════╝░░░░░░██╔══██╗██╔══██╗
░█████═╝░╚█████╔╝╚█████╗░█████╗██████╦╝██████╔╝
░██╔═██╗░██╔══██╗░╚═══██╗╚════╝██╔══██╗██╔═══╝░
░██║░╚██╗╚█████╔╝██████╔╝░░░░░░██████╦╝██║░░░░░
░╚═╝░░╚═╝░╚════╝░╚═════╝░░░░░░░╚═════╝░╚═╝░░░░░
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Iterator
from typing import Any

from flask import (
    Blueprint,
    Response,
    current_app,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from models import Execution, db, log_action

k8s_bp = Blueprint("k8s", __name__)


def _wants_json() -> bool:
    """Return True if the request expects a JSON response."""
    return bool(
        request.is_json
        or "application/json" in request.headers.get("Accept", "")
        or request.args.get("format") == "json"
    )


def _check_write_permission() -> Response | tuple[Response, int] | None:
    """Return a 403 Response if the current authenticated user has a read-only viewer role."""
    if session.get("role") == "viewer":
        msg = "Forbidden: viewer role cannot create, modify, or execute flows."
        if _wants_json():
            return jsonify({"error": msg}), 403
        return Response(msg, status=403)
    return None


def _serialize_flow(flow: dict[str, Any]) -> dict[str, Any]:
    """Serialize a flow dictionary (including version history datetimes) into JSON-safe types."""
    serialized = dict(flow)
    raw_versions = serialized.get("versions") or []
    clean_versions: list[dict[str, Any]] = []
    for ver in raw_versions:
        ver_copy = dict(ver)
        dt = ver_copy.get("created_at")
        if hasattr(dt, "isoformat"):
            ver_copy["created_at"] = dt.isoformat()
        clean_versions.append(ver_copy)
    serialized["versions"] = clean_versions
    return serialized


def _serialize_execution(exe: Execution, include_logs: bool = False) -> dict[str, Any]:
    """Serialize an Execution ORM record into a JSON-safe dictionary."""
    inputs_meta: dict[str, Any] = {}
    if exe.inputs_json:
        try:
            parsed = json.loads(exe.inputs_json)
            if isinstance(parsed, dict):
                inputs_meta = parsed
        except ValueError:
            inputs_meta = {}
    payload: dict[str, Any] = {
        "run_id": exe.id,
        "id": exe.id,
        "flow_name": exe.analysis_name,
        "analysis_name": exe.analysis_name,
        "job_name": exe.job_name,
        "namespace": exe.namespace,
        "node_name": exe.node_name,
        "status": exe.status,
        "exit_code": exe.exit_code,
        "error_message": exe.error_message,
        "trigger_type": exe.trigger_type or "manual",
        "started_at": exe.started_at.isoformat() if exe.started_at else None,
        "finished_at": exe.finished_at.isoformat() if exe.finished_at else None,
        "inputs": inputs_meta,
        "detail_url": f"/runs/{exe.id}",
        "stream_url": f"/runs/{exe.id}/stream",
    }
    if include_logs:
        payload["log_text"] = exe.log_text or ""
    return payload


def _serialize_cluster_summary(summary: dict[str, Any]) -> dict[str, Any]:
    """Serialize get_cluster_summary() output into a JSON-safe dictionary."""
    nodes_out: list[dict[str, Any]] = []
    for node in summary.get("nodes") or []:
        nodes_out.append(
            {
                "name": node.name,
                "uid": node.uid,
                "status": node.status,
                "roles": node.roles,
                "internal_ip": node.internal_ip,
                "address": node.address,
                "cpu_capacity": node.cpu_capacity,
                "memory_capacity": node.memory_capacity,
                "cpu_allocatable": node.cpu_allocatable,
                "memory_allocatable": node.memory_allocatable,
                "cpu_usage": node.cpu_usage,
                "memory_usage": node.memory_usage,
                "kubelet_version": node.kubelet_version,
                "first_seen_at": node.first_seen_at.isoformat() if node.first_seen_at else None,
                "last_seen_at": node.last_seen_at.isoformat() if node.last_seen_at else None,
                "removed_at": node.removed_at.isoformat() if node.removed_at else None,
            }
        )
    updated_at = summary.get("updated_at")
    return {
        "nodes": nodes_out,
        "total_active": summary.get("total_active", 0),
        "ready": summary.get("ready", 0),
        "not_ready": summary.get("not_ready", 0),
        "removed": summary.get("removed", 0),
        "connected": bool(summary.get("connected")),
        "error": summary.get("error"),
        "updated_at": updated_at.isoformat() if hasattr(updated_at, "isoformat") else str(updated_at or ""),
    }


@k8s_bp.route("/workers", methods=["GET"])
def workers_page() -> Response | str:
    """Render the read-only k0s Workers page with HTMX polling or return JSON summary."""
    webapp = current_app.config["WEBAPP"]
    summary = webapp.get_cluster_summary()
    if _wants_json():
        return jsonify(_serialize_cluster_summary(summary))

    html_part = webapp.substitute_html(
        port=webapp.constants.get("port", 5000),
        project_folder=webapp.project_folder,
    )
    return render_template(
        "workers.html",
        head=html_part["head"],
        top_container=html_part["top_container"],
        sidebar_menu=html_part["sidebar_menu"],
        summary=summary,
    )


@k8s_bp.route("/workers/table", methods=["GET"])
def workers_table_partial() -> str:
    """Return the HTMX partial table of k0s worker nodes."""
    webapp = current_app.config["WEBAPP"]
    summary = webapp.get_cluster_summary()
    return render_template("components/workers_table.html", summary=summary)


def _render_flows_view(
    selected_name: str | None = None,
    message: str | None = None,
    error: str | None = None,
    inspected_version: dict[str, Any] | None = None,
) -> str:
    """Render the Flows editor and list page."""
    webapp = current_app.config["WEBAPP"]
    html_part = webapp.substitute_html(
        port=webapp.constants.get("port", 5000),
        project_folder=webapp.project_folder,
    )
    flows = webapp.list_flows()
    selected_flow: dict[str, Any] | None = None
    if selected_name:
        selected_flow = webapp.read_flow(selected_name)
    elif flows and not request.args.get("new"):
        selected_flow = flows[0]

    recent_runs = Execution.query.order_by(Execution.started_at.desc()).limit(8).all()
    default_image = current_app.config.get("K8S_DEFAULT_IMAGE", os.environ.get("K8S_DEFAULT_IMAGE", "python:3.11-slim"))

    return render_template(
        "flows.html",
        head=html_part["head"],
        top_container=html_part["top_container"],
        sidebar_menu=html_part["sidebar_menu"],
        flows=flows,
        selected_flow=selected_flow,
        inspected_version=inspected_version,
        recent_runs=recent_runs,
        default_image=default_image,
        message=message,
        error=error,
    )


@k8s_bp.route("/flows", methods=["GET"])
def flows_page() -> Response | str:
    """Redirect to the unified analysis catalog or return JSON list of flows."""
    if _wants_json():
        webapp = current_app.config["WEBAPP"]
        flows = [_serialize_flow(f) for f in webapp.list_flows()]
        return jsonify({"flows": flows})
    return redirect("/analysis")


@k8s_bp.route("/flows/<name>", methods=["GET"])
def flow_detail_page(name: str) -> Response | tuple[Response, int] | str:
    """Display a specific Flow inside the Flows editor or return JSON flow details."""
    webapp = current_app.config["WEBAPP"]
    flow = webapp.read_flow(name)
    if flow is None:
        if _wants_json():
            return jsonify({"error": f"Flow '{name}' not found."}), 404
        return _render_flows_view(error=f"Flow '{name}' not found.")
    if _wants_json():
        return jsonify(_serialize_flow(flow))
    return _render_flows_view(selected_name=name, message=request.args.get("msg"))


@k8s_bp.route("/flows/<name>", methods=["DELETE"])
def flow_delete_route(name: str) -> Response | tuple[Response, int]:
    """Delete a Flow and all its version history."""
    denied = _check_write_permission()
    if denied is not None:
        return denied

    webapp = current_app.config["WEBAPP"]
    if not webapp.delete_flow(name):
        return jsonify({"error": f"Flow '{name}' not found."}), 404

    log_action("delete_flow", "flow", name)
    return jsonify({"deleted": True, "name": name})


@k8s_bp.route("/flows/new", methods=["GET", "POST"])
@k8s_bp.route("/flows/save", methods=["POST"])
def flow_create_route() -> Response | tuple[Response, int] | str:
    """Create a new Flow (or update via /flows/save) or display the blank new Flow editor."""
    if request.method == "GET":
        return _render_flows_view(selected_name=None)

    denied = _check_write_permission()
    if denied is not None:
        return denied

    webapp = current_app.config["WEBAPP"]
    payload = request.get_json(silent=True) if request.is_json else None
    flow_name = str((payload.get("name") if payload else request.form.get("name")) or "").strip()
    code = (
        payload.get("code")
        if payload and "code" in payload
        else (request.form.get("code") or 'print("hello world")\n')
    )
    description = str((payload.get("description") if payload else request.form.get("description")) or "").strip()
    parameters = (
        payload.get("parameters")
        if payload and "parameters" in payload
        else (request.form.get("parameters") or "{}")
    )
    pip_requirements = (
        payload.get("pip_requirements")
        if payload and "pip_requirements" in payload
        else (request.form.get("pip_requirements") or "")
    )
    env_vars = (
        payload.get("env_vars")
        if payload and "env_vars" in payload
        else (request.form.get("env_vars") or "")
    )
    secret_refs = (
        payload.get("secret_refs")
        if payload and "secret_refs" in payload
        else (request.form.get("secret_refs") or "")
    )
    image = str((payload.get("image") if payload else request.form.get("image")) or "").strip()
    version_message = str(
        (payload.get("version_message") if payload else request.form.get("version_message")) or ""
    ).strip()
    owner = session.get("username") or "flow-author"

    try:
        saved = webapp.save_flow(
            name=flow_name,
            code=code,
            description=description,
            parameters=parameters,
            pip_requirements=pip_requirements,
            env_vars=env_vars,
            secret_refs=secret_refs,
            image=image,
            owner=owner,
            user_id=session.get("user_id"),
            version_message=version_message,
        )
        log_action("save_flow", "flow", saved["name"])
    except ValueError as exc:
        if _wants_json():
            return jsonify({"error": str(exc)}), 400
        return _render_flows_view(error=str(exc))

    if _wants_json():
        return jsonify(_serialize_flow(saved))

    return redirect(url_for("k8s.flow_detail_page", name=saved["name"], msg="Flow saved."))


@k8s_bp.route("/flows/<name>/save", methods=["POST"])
def flow_save_route(name: str) -> Response | tuple[Response, int] | str:
    """Save edits to an existing or renamed Flow."""
    denied = _check_write_permission()
    if denied is not None:
        return denied

    webapp = current_app.config["WEBAPP"]
    payload = request.get_json(silent=True) if request.is_json else None
    target_name = str((payload.get("name") if payload else request.form.get("name")) or name).strip()
    code = (payload.get("code") if payload and "code" in payload else (request.form.get("code") or ""))
    description = str((payload.get("description") if payload else request.form.get("description")) or "").strip()
    parameters = (
        payload.get("parameters")
        if payload and "parameters" in payload
        else (request.form.get("parameters") or "{}")
    )
    pip_requirements = (
        payload.get("pip_requirements")
        if payload and "pip_requirements" in payload
        else (request.form.get("pip_requirements") or "")
    )
    env_vars = (
        payload.get("env_vars")
        if payload and "env_vars" in payload
        else (request.form.get("env_vars") or "")
    )
    secret_refs = (
        payload.get("secret_refs")
        if payload and "secret_refs" in payload
        else (request.form.get("secret_refs") or "")
    )
    image = str((payload.get("image") if payload else request.form.get("image")) or "").strip()
    version_message = str(
        (payload.get("version_message") if payload else request.form.get("version_message")) or ""
    ).strip()
    owner = session.get("username") or "flow-author"

    try:
        saved = webapp.save_flow(
            name=target_name,
            code=code,
            description=description,
            parameters=parameters,
            pip_requirements=pip_requirements,
            env_vars=env_vars,
            secret_refs=secret_refs,
            image=image,
            owner=owner,
            user_id=session.get("user_id"),
            version_message=version_message,
        )
        log_action("save_flow", "flow", saved["name"])
    except ValueError as exc:
        if _wants_json():
            return jsonify({"error": str(exc)}), 400
        return _render_flows_view(selected_name=name, error=str(exc))

    if _wants_json():
        return jsonify(_serialize_flow(saved))

    return redirect(url_for("k8s.flow_detail_page", name=saved["name"], msg="Flow saved."))


@k8s_bp.route("/flows/<name>/versions/<int:version_num>", methods=["GET"])
def flow_version_view_route(name: str, version_num: int) -> Response | str:
    """Inspect a historical version snapshot for a Flow."""
    webapp = current_app.config["WEBAPP"]
    flow = webapp.read_flow(name)
    if flow is None:
        return Response(f"Flow '{name}' not found.", status=404)

    versions = webapp.read_flow_versions(name)
    target = next((v for v in versions if v["version_num"] == version_num), None)
    if target is None:
        return Response(f"Version v{version_num} for flow '{name}' not found.", status=404)

    if request.is_json or "application/json" in request.headers.get("Accept", ""):
        return jsonify(
            {
                "flow_name": target["flow_name"],
                "version_num": target["version_num"],
                "code": target["code"],
                "config": target["config"],
                "username": target["username"],
                "message": target["message"],
                "created_at": target["created_at"].isoformat() if target["created_at"] else None,
            }
        )

    return _render_flows_view(selected_name=name, inspected_version=target)


@k8s_bp.route("/flows/<name>/versions/<int:version_num>/restore", methods=["POST"])
def flow_version_restore_route(name: str, version_num: int) -> Response | str:
    """Non-destructively restore a Flow to a specified version snapshot."""
    denied = _check_write_permission()
    if denied is not None:
        return denied

    webapp = current_app.config["WEBAPP"]
    try:
        restored = webapp.restore_flow_version(
            name=name,
            version_num=version_num,
            user_id=session.get("user_id"),
        )
    except ValueError as exc:
        return Response(str(exc), status=404)

    log_action(
        "restore_flow_version",
        "flow",
        name,
        details={"restored_from": version_num, "new_version": restored.get("version_num")},
    )
    if request.is_json or "application/json" in request.headers.get("Accept", ""):
        return jsonify(
            {
                "flow_name": restored["name"],
                "restored_from": version_num,
                "version_num": restored.get("version_num"),
                "code": restored["code"],
            }
        )

    return redirect(
        url_for(
            "k8s.flow_detail_page",
            name=name,
            msg=f"Restored from version v{version_num} (now at v{restored.get('version_num')}).",
        )
    )


@k8s_bp.route("/flows/<name>/run", methods=["POST"])
def flow_run_route(name: str) -> Response | tuple[Response, int] | str:
    """Launch an isolated Kubernetes batch/v1 Job for the specified Flow and return/redirect to its run_id."""
    denied = _check_write_permission()
    if denied is not None:
        return denied

    webapp = current_app.config["WEBAPP"]
    flow = webapp.read_flow(name)
    if flow is None:
        if _wants_json():
            return jsonify({"error": f"Flow '{name}' not found."}), 404
        return Response(f"Flow '{name}' not found.", status=404)

    payload = request.get_json(silent=True) if request.is_json else None
    parameters = (payload.get("parameters") if payload else request.form.get("parameters"))
    pip_requirements = (payload.get("pip_requirements") if payload else request.form.get("pip_requirements"))
    env_vars = (payload.get("env_vars") if payload else request.form.get("env_vars"))
    secret_refs = (payload.get("secret_refs") if payload else request.form.get("secret_refs"))
    image = (payload.get("image") if payload else request.form.get("image"))
    wait_sync = bool(
        (payload and payload.get("wait"))
        or request.args.get("wait") == "1"
        or current_app.config.get("K8S_SYNC_WATCHER", False)
    )

    exe = webapp.launch_flow_run(
        flow_name=name,
        parameters=parameters,
        pip_requirements=pip_requirements,
        env_vars=env_vars,
        secret_refs=secret_refs,
        image=image,
        user_id=session.get("user_id"),
        trigger_type="manual",
        app=current_app._get_current_object(),  # type: ignore[attr-defined]
        wait_for_watcher=wait_sync,
    )
    log_action("run_flow", "flow", name, details={"run_id": exe.id, "job_name": exe.job_name})

    if _wants_json():
        return jsonify(_serialize_execution(exe, include_logs=True))

    return redirect(url_for("k8s.run_detail_page", run_id=exe.id))


@k8s_bp.route("/runs", methods=["GET"])
def runs_list_route() -> Response | str:
    """List recent flow and analysis executions in JSON or redirect to the executions view."""
    limit = int(request.args.get("limit") or 50)
    flow_filter = (request.args.get("flow_name") or "").strip()
    query = Execution.query
    if flow_filter:
        query = query.filter_by(analysis_name=flow_filter)
    executions = query.order_by(Execution.started_at.desc()).limit(limit).all()

    if _wants_json():
        return jsonify({"runs": [_serialize_execution(exe) for exe in executions]})

    return redirect("/executions")


@k8s_bp.route("/runs/<int:run_id>", methods=["GET"])
def run_detail_page(run_id: int) -> Response | tuple[Response, int] | str:
    """Display the Run detail and live/historical stdout/stderr log viewer for a specific run_id."""
    exe = db.session.get(Execution, run_id)
    if exe is None:
        if _wants_json():
            return jsonify({"error": f"Run #{run_id} not found."}), 404
        return Response(f"Run #{run_id} not found.", status=404)

    if _wants_json():
        return jsonify(_serialize_execution(exe, include_logs=True))

    webapp = current_app.config["WEBAPP"]
    html_part = webapp.substitute_html(
        port=webapp.constants.get("port", 5000),
        project_folder=webapp.project_folder,
    )
    inputs_meta: dict[str, Any] = {}
    if exe.inputs_json:
        try:
            parsed = json.loads(exe.inputs_json)
            if isinstance(parsed, dict):
                inputs_meta = parsed
        except ValueError:
            inputs_meta = {}

    return render_template(
        "run_detail.html",
        head=html_part["head"],
        top_container=html_part["top_container"],
        sidebar_menu=html_part["sidebar_menu"],
        execution=exe,
        inputs_meta=inputs_meta,
    )


@k8s_bp.route("/runs/<int:run_id>/stream", methods=["GET"])
def run_stream_route(run_id: int) -> Response:
    """Stream live or historical logs for run_id via SSE without re-triggering execution."""
    initial_exe = db.session.get(Execution, run_id)
    if initial_exe is None:
        return Response(f"Run #{run_id} not found.", status=404)

    app_obj = current_app._get_current_object()  # type: ignore[attr-defined]
    max_polls = int(current_app.config.get("K8S_SSE_MAX_POLLS", 600))
    poll_interval = float(current_app.config.get("K8S_SSE_POLL_INTERVAL", 0.25))

    def generate() -> Iterator[str]:
        from flask import has_app_context

        offset = 0
        for _ in range(max_polls):
            if has_app_context():
                db.session.expire_all()
                current_exe = db.session.get(Execution, run_id)
                full_text = (current_exe.log_text or "") if current_exe else ""
                status_val = current_exe.status if current_exe else None
            else:
                with app_obj.app_context():
                    db.session.expire_all()
                    current_exe = db.session.get(Execution, run_id)
                    full_text = (current_exe.log_text or "") if current_exe else ""
                    status_val = current_exe.status if current_exe else None

            if status_val is None:
                yield "data: [Error: Run record not found]\n\n"
                return

            if len(full_text) > offset:
                new_chunk = full_text[offset:]
                offset = len(full_text)
                for line in new_chunk.splitlines():
                    yield f"data: {line}\n\n"

            if status_val in ("success", "failed", "aborted"):
                yield f"data: [Status: {status_val}]\n\n"
                yield f"event: done\ndata: {status_val}\n\n"
                return

            time.sleep(poll_interval)

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@k8s_bp.route("/runs/<int:run_id>/abort", methods=["POST"])
def run_abort_route(run_id: int) -> Response | tuple[Response, int]:
    """Abort an in-progress Kubernetes Job run."""
    denied = _check_write_permission()
    if denied is not None:
        return denied

    webapp = current_app.config["WEBAPP"]
    exe = webapp.abort_flow_run(run_id)
    if exe is None:
        if _wants_json():
            return jsonify({"error": f"Run #{run_id} not found."}), 404
        return Response(f"Run #{run_id} not found.", status=404)

    log_action("abort_run", "execution", str(run_id))
    if _wants_json():
        return jsonify(_serialize_execution(exe, include_logs=True))
    return redirect(url_for("k8s.run_detail_page", run_id=run_id))


@k8s_bp.route("/schedules/create", methods=["POST"])
def schedule_create_route() -> Response | tuple[Response, int]:
    """Create a cron or interval schedule for a Flow backed by APScheduler and K8s Jobs."""
    denied = _check_write_permission()
    if denied is not None:
        return denied

    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.interval import IntervalTrigger

    from blueprints.catalog import execute_scheduled_flow

    webapp = current_app.config["WEBAPP"]
    scheduler = current_app.config["SCHEDULER"]
    payload = request.get_json(silent=True) if request.is_json else None

    flow_name = str(
        (
            (payload.get("flow_name") or payload.get("analysis_name"))
            if payload
            else (request.form.get("flow_name") or request.form.get("analysis_name"))
        )
        or ""
    ).strip()

    if not flow_name or webapp.read_flow(flow_name) is None:
        if _wants_json():
            return jsonify({"error": f"Flow '{flow_name}' not found."}), 404
        return Response(f"Flow '{flow_name}' not found.", status=404)

    schedule_type = str(
        (payload.get("schedule_type") if payload else request.form.get("schedule_type")) or "cron"
    ).strip().lower()
    raw_params = (
        payload.get("parameters")
        if payload and "parameters" in payload
        else (request.form.get("parameters") or "{}")
    )
    params = webapp.parse_flow_parameters(raw_params)
    pip_reqs = (payload.get("pip_requirements") if payload else request.form.get("pip_requirements")) or None
    image = str((payload.get("image") if payload else request.form.get("image")) or "").strip() or None

    if schedule_type == "interval":
        seconds = int((payload.get("interval_seconds") if payload else request.form.get("interval_seconds")) or 0)
        minutes = int((payload.get("interval_minutes") if payload else request.form.get("interval_minutes")) or 0)
        if seconds > 0:
            trigger = IntervalTrigger(seconds=seconds)
        else:
            trigger = IntervalTrigger(minutes=max(1, minutes or 60))
    else:
        cron_expr = str(
            (
                (payload.get("cron_expr") or payload.get("schedule_cron"))
                if payload
                else (request.form.get("cron_expr") or request.form.get("schedule_cron"))
            )
            or "0 * * * *"
        ).strip()
        try:
            trigger = CronTrigger.from_crontab(cron_expr)
        except ValueError as exc:
            if _wants_json():
                return jsonify({"error": f"Invalid cron expression '{cron_expr}': {exc}"}), 400
            return Response(f"Invalid cron expression '{cron_expr}': {exc}", status=400)

    raw_job_id = payload.get("job_id") if payload else request.form.get("job_id")
    job_id = str(raw_job_id or f"flow_{flow_name}_{int(time.time())}").strip()
    scheduler.add_job(
        id=job_id,
        func=execute_scheduled_flow,
        trigger=trigger,
        kwargs={
            "name": flow_name,
            "parameters": params,
            "pip_requirements": pip_reqs,
            "image": image,
        },
        name=f"{flow_name} ({schedule_type})",
        coalesce=True,
        max_instances=1,
        misfire_grace_time=60,
        replace_existing=True,
    )

    enabled_flag = (
        payload.get("enabled", True)
        if payload and "enabled" in payload
        else request.form.get("enabled", "1")
    )
    is_paused = str(enabled_flag).lower() in ("0", "false", "off")
    if is_paused:
        scheduler.pause_job(job_id)

    log_action(
        "create_schedule",
        "schedule",
        job_id,
        details={"flow": flow_name, "type": schedule_type},
    )
    if _wants_json():
        return jsonify(
            {
                "job_id": job_id,
                "name": f"{flow_name} ({schedule_type})",
                "schedule_type": schedule_type,
                "flow_name": flow_name,
                "state": "paused" if is_paused else "active",
            }
        )
    return redirect("/schedules/")


@k8s_bp.route("/schedules/<job_id>/toggle", methods=["POST"])
def schedule_toggle_route(job_id: str) -> Response | tuple[Response, int]:
    """Pause an active schedule or resume a paused schedule."""
    denied = _check_write_permission()
    if denied is not None:
        return denied

    scheduler = current_app.config["SCHEDULER"]
    job = scheduler.get_job(job_id)
    if job is None:
        if _wants_json():
            return jsonify({"error": f"Schedule '{job_id}' not found."}), 404
        return Response(f"Schedule '{job_id}' not found.", status=404)

    if job.next_run_time is not None:
        scheduler.pause_job(job_id)
        new_state = "paused"
    else:
        scheduler.resume_job(job_id)
        new_state = "active"

    log_action("toggle_schedule", "schedule", job_id, details={"state": new_state})
    if _wants_json():
        return jsonify({"job_id": job_id, "state": new_state})

    return redirect("/schedules/")

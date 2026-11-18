"""
░████████╗███████╗░██████╗████████╗░░░░░░███████╗██╗░░░░░░█████╗░░██╗░░░░░░░██╗░██████╗
░╚══██╔══╝██╔════╝██╔════╝╚══██╔══╝░░░░░░██╔════╝██║░░░░░██╔══██╗░██║░░██╗░░██║██╔════╝
░░░░██║░░░█████╗░░╚█████╗░░░░██║░░░█████╗█████╗░░██║░░░░░██║░░██║░╚██╗████╗██╔╝╚█████╗░
░░░░██║░░░██╔══╝░░░╚═══██╗░░░██║░░░╚════╝██╔══╝░░██║░░░░░██║░░██║░░████╔═████║░░╚═══██╗
░░░░██║░░░███████╗██████╔╝░░░██║░░░░░░░░░██║░░░░░███████╗╚█████╔╝░░╚██╔╝░╚██╔╝░██████╔╝
░░░░╚═╝░░░╚══════╝╚═════╝░░░░╚═╝░░░░░░░░░╚═╝░░░░░╚══════╝░╚════╝░░░░╚═╝░░░╚═╝░░╚═════╝░
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest
import yaml


@pytest.fixture
def isolated_analyses_dir(app: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point webapp.save_folder_path to a temporary Analyses directory for clean tests."""
    webapp = app.config["WEBAPP"]
    analyses_dir = tmp_path / "Analyses"
    analyses_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(webapp, "save_folder_path", str(analyses_dir))
    return analyses_dir


def test_save_and_read_hello_world_flow(app: Any, isolated_analyses_dir: Path) -> None:
    """Verify saving a generic print('hello world') flow inside Analyses/<name>/."""
    webapp = app.config["WEBAPP"]
    flow = webapp.save_flow(
        name="HelloFlow",
        code='print("hello world")',
        description="Minimal hello world flow",
        parameters={"greeting": "hello", "count": 1},
        pip_requirements=["requests==2.31.0", "httpx"],
        env_vars={"API_SECRET_TOKEN": "super-secret-value", "API_TOKEN": "tok-123"},
        image="python:3.11-slim",
        owner="alice",
    )

    assert flow["name"] == "HelloFlow"
    assert 'print("hello world")' in flow["code"]
    assert flow["parameters"] == {"greeting": "hello", "count": 1}
    assert flow["pip_requirements"] == ["requests==2.31.0", "httpx"]
    assert sorted(flow["env_keys"]) == ["API_SECRET_TOKEN", "API_TOKEN"]
    assert flow["image"] == "python:3.11-slim"

    flow_dir = isolated_analyses_dir / "HelloFlow"
    assert (flow_dir / "flow.py").is_file()
    assert (flow_dir / "flow_config.yaml").is_file()
    assert (flow_dir / "metadata.yaml").is_file()
    assert (flow_dir / "compass_flow.yaml").is_file()

    # Verify secret values are NOT persisted in plaintext in flow_config.yaml
    raw_cfg_text = (flow_dir / "flow_config.yaml").read_text(encoding="utf-8")
    assert "super-secret-value" not in raw_cfg_text
    assert "tok-123" not in raw_cfg_text
    cfg_data = yaml.safe_load(raw_cfg_text)
    assert cfg_data["env_keys"] == ["API_SECRET_TOKEN", "API_TOKEN"]

    # Verify backwards-compatibility with read_single_analysis
    single = webapp.read_single_analysis(str(isolated_analyses_dir), "HelloFlow")
    assert single["title"] == "HelloFlow"
    assert single["structured_analysis"] == "y"


def test_flows_ui_routes_and_rbac(
    app: Any,
    client: Any,
    unauth_client: Any,
    isolated_analyses_dir: Path,
) -> None:
    """Verify /flows, /flows/new, /flows/<name>, /flows/<name>/save routes and RBAC roles."""
    # 1. Create flow via POST /flows/new
    resp = client.post(
        "/flows/new",
        data={
            "name": "CloudTask",
            "code": 'import os\nprint("hello world")\n',
            "description": "Cloud automation script",
            "parameters": '{"region": "eu-west-1"}',
            "pip_requirements": "httpx\npyyaml",
            "env_vars": "CLOUD_KEY=secret999",
            "image": "python:3.12-slim",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    html = resp.data.decode("utf-8")
    assert "CloudTask" in html
    assert 'print("hello world")' in html
    assert "python:3.12-slim" in html
    assert os.path.isfile(isolated_analyses_dir / "CloudTask" / "flow.py")

    # 2. Update flow via POST /flows/CloudTask/save
    resp_save = client.post(
        "/flows/CloudTask/save",
        data={
            "name": "CloudTask",
            "code": 'print("updated hello world")\n',
            "description": "Updated description",
            "parameters": "region=us-east-1",
            "pip_requirements": "requests",
            "env_vars": "",
            "image": "python:3.11-slim",
        },
        follow_redirects=True,
    )
    assert resp_save.status_code == 200
    assert b"updated hello world" in resp_save.data

    # 3. Viewer role can view /flows and /flows/CloudTask but cannot create or save
    with client.session_transaction() as sess:
        sess["role"] = "viewer"

    view_resp = client.get("/flows/CloudTask")
    assert view_resp.status_code == 200
    assert b"CloudTask" in view_resp.data

    forbidden_new = client.post("/flows/new", data={"name": "BlockedFlow", "code": "print(1)"})
    assert forbidden_new.status_code == 403

    forbidden_save = client.post("/flows/CloudTask/save", data={"name": "CloudTask", "code": "print(2)"})
    assert forbidden_save.status_code == 403

    # 4. Unauthenticated user cannot view flows editor
    unauth_resp = unauth_client.get("/flows")
    assert b"Python Flows on k0s" not in unauth_resp.data


def test_flow_versioning_and_non_destructive_restore(
    app: Any,
    client: Any,
    isolated_analyses_dir: Path,
) -> None:
    """Verify saving a flow 3 times creates 3 FlowVersion rows and restoring v1 creates v4."""
    from models import FlowVersion

    webapp = app.config["WEBAPP"]

    # Save flow 3 times with distinct code and parameters
    webapp.save_flow(
        name="VersionedFlow",
        code='print("version 1")',
        parameters={"step": 1},
        secret_refs=["sec-v1"],
        version_message="Initial version",
    )
    webapp.save_flow(
        name="VersionedFlow",
        code='print("version 2")',
        parameters={"step": 2},
        secret_refs=["sec-v2"],
        version_message="Second iteration",
    )
    webapp.save_flow(
        name="VersionedFlow",
        code='print("version 3")',
        parameters={"step": 3},
        secret_refs=["sec-v3"],
        version_message="Third iteration",
    )

    versions = webapp.read_flow_versions("VersionedFlow")
    assert len(versions) == 3
    assert [v["version_num"] for v in versions] == [3, 2, 1]
    assert 'print("version 1")' in versions[2]["code"]
    assert 'print("version 3")' in versions[0]["code"]
    assert FlowVersion.query.filter_by(flow_name="VersionedFlow").count() == 3

    # Inspect version 1 via GET /flows/VersionedFlow/versions/1
    import html as html_lib

    view_v1 = client.get("/flows/VersionedFlow/versions/1")
    assert view_v1.status_code == 200
    assert 'print("version 1")' in html_lib.unescape(view_v1.data.decode("utf-8"))
    assert b"Inspecting Snapshot" in view_v1.data

    view_v1_json = client.get(
        "/flows/VersionedFlow/versions/1",
        headers={"Accept": "application/json"},
    )
    assert view_v1_json.status_code == 200
    assert 'print("version 1")' in view_v1_json.get_json()["code"]

    # Restore version 1 via POST /flows/VersionedFlow/versions/1/restore
    restore_resp = client.post(
        "/flows/VersionedFlow/versions/1/restore",
        follow_redirects=True,
    )
    assert restore_resp.status_code == 200
    assert b"Restored from version v1 (now at v4)" in restore_resp.data

    current_flow = webapp.read_flow("VersionedFlow")
    assert current_flow is not None
    assert 'print("version 1")' in current_flow["code"]
    assert current_flow["parameters"] == {"step": 1}
    assert current_flow["secret_refs"] == ["sec-v1"]
    assert current_flow["version_num"] == 4

    all_versions = webapp.read_flow_versions("VersionedFlow")
    assert len(all_versions) == 4
    assert [v["version_num"] for v in all_versions] == [4, 3, 2, 1]
    assert "Restored from version 1" in all_versions[0]["message"]


def test_save_flow_extracts_targz_and_zip_bundles_and_preserves_on_code_only_update(
    app: Any,
    isolated_analyses_dir: Path,
) -> None:
    """Verify .tar.gz and .zip bundles extract into analysis/, exclude noise, and survive code-only saves."""
    import base64
    import io
    import stat
    import tarfile
    import zipfile

    webapp = app.config["WEBAPP"]

    # Build a .tar.gz bundle with './' prefixes and excluded directories/files
    tar_buf = io.BytesIO()
    with tarfile.open(fileobj=tar_buf, mode="w:gz") as tf:
        entries = {
            "./tagline/__init__.py": b'PACKAGE_NAME = "tagline"\n',
            "./tagline/logic.py": b"def compute() -> int:\n    return 42\n",
            "./run.py": b'if __name__ == "__main__":\n    print("runner")\n',
            "./.git/config": b"[core]\n",
            "./.venv/pyvenv.cfg": b"home = /usr/bin\n",
            "./tagline/__pycache__/logic.cpython-312.pyc": b"\x00\x01\x02",
            "./node_modules/pkg/index.js": b"module.exports = {};\n",
            "./.DS_Store": b"mac-junk",
        }
        for arcname, payload in entries.items():
            info = tarfile.TarInfo(name=arcname)
            info.size = len(payload)
            tf.addfile(info, io.BytesIO(payload))

    bundle_b64 = base64.b64encode(tar_buf.getvalue()).decode("ascii")
    webapp.save_flow(
        name="MultiModuleFlow",
        code='from tagline.logic import compute\nprint(compute())\n',
        pip_requirements=["pandas"],
        image="python:3.11-slim",
        analysis_bundle_b64=bundle_b64,
    )

    flow_dir = isolated_analyses_dir / "MultiModuleFlow"
    analysis_subdir = flow_dir / "analysis"
    assert (analysis_subdir / "tagline" / "__init__.py").is_file()
    assert (analysis_subdir / "tagline" / "logic.py").is_file()
    assert (analysis_subdir / "run.py").is_file()
    assert not (analysis_subdir / ".git").exists()
    assert not (analysis_subdir / ".venv").exists()
    assert not (analysis_subdir / "tagline" / "__pycache__").exists()
    assert not (analysis_subdir / "node_modules").exists()
    assert not (analysis_subdir / ".DS_Store").exists()

    ep_path = flow_dir / "scripts" / "pc_entrypoint.sh"
    assert ep_path.is_file()
    assert bool(os.stat(ep_path).st_mode & stat.S_IXUSR)

    dockerfile_text = (flow_dir / "Dockerfile").read_text(encoding="utf-8")
    assert dockerfile_text.startswith("# Auto-generated by ProjectCompass\n")
    assert "COPY analysis/ /app/\n" in dockerfile_text
    assert "COPY . /app/\n" in dockerfile_text
    assert "COPY scripts/pc_entrypoint.sh /app/scripts/pc_entrypoint.sh\n" in dockerfile_text
    assert 'ENV PYTHONPATH="/app:/app/analysis"\n' in dockerfile_text
    assert 'ENTRYPOINT ["/bin/sh", "/app/scripts/pc_entrypoint.sh", "python", "flow.py"]\n' in dockerfile_text
    # Ensure COPY analysis/ /app/ comes BEFORE COPY . /app/ so Compass root files win
    assert dockerfile_text.index("COPY analysis/ /app/") < dockerfile_text.index("COPY . /app/")

    # Code-only update without bundle preserves existing analysis/ tree
    webapp.save_flow(
        name="MultiModuleFlow",
        code='from tagline.logic import compute\nprint("updated", compute())\n',
        pip_requirements=["pandas", "httpx"],
    )
    assert (analysis_subdir / "tagline" / "logic.py").is_file()
    assert (analysis_subdir / "run.py").is_file()
    assert 'print("updated", compute())' in (flow_dir / "flow.py").read_text(encoding="utf-8")

    # Replacing via a .zip bundle refreshes analysis/ cleanly
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("new_pkg/__init__.py", "VERSION = 2\n")
        zf.writestr(".pytest_cache/README.md", "ignored\n")
    zip_b64 = base64.b64encode(zip_buf.getvalue()).decode("ascii")

    webapp.save_flow(
        name="MultiModuleFlow",
        code="import new_pkg\nprint(new_pkg.VERSION)\n",
        analysis_bundle_b64=zip_b64,
    )
    assert (analysis_subdir / "new_pkg" / "__init__.py").is_file()
    assert not (analysis_subdir / "tagline").exists()
    assert not (analysis_subdir / ".pytest_cache").exists()


def test_save_flow_upgrades_legacy_dockerfile_but_preserves_custom_dockerfile(
    app: Any,
    isolated_analyses_dir: Path,
) -> None:
    """Verify legacy 5-line Compass Dockerfiles are upgraded while custom Dockerfiles remain untouched."""
    webapp = app.config["WEBAPP"]

    # 1. Pre-create a flow with the legacy 5-line auto-generated Dockerfile
    legacy_dir = isolated_analyses_dir / "LegacyDockerFlow"
    legacy_dir.mkdir(parents=True, exist_ok=True)
    legacy_dockerfile = (
        "FROM python:3.11-slim\n"
        "WORKDIR /app\n"
        "COPY . .\n"
        "RUN if [ -s requirements.txt ]; then pip install --no-cache-dir -r requirements.txt; fi\n"
        'ENTRYPOINT ["/bin/sh", "scripts/pc_entrypoint.sh", "python", "flow.py"]\n'
    )
    (legacy_dir / "Dockerfile").write_text(legacy_dockerfile, encoding="utf-8")

    webapp.save_flow(
        name="LegacyDockerFlow",
        code='print("upgraded")\n',
        image="python:3.12-slim",
        analysis_files={"tagline/helper.py": "X = 1\n"},
    )
    upgraded_text = (legacy_dir / "Dockerfile").read_text(encoding="utf-8")
    assert upgraded_text.startswith("# Auto-generated by ProjectCompass\n")
    assert "FROM python:3.12-slim\n" in upgraded_text
    assert "COPY analysis/ /app/\n" in upgraded_text
    assert 'ENTRYPOINT ["/bin/sh", "/app/scripts/pc_entrypoint.sh", "python", "flow.py"]\n' in upgraded_text
    assert (legacy_dir / "analysis" / "tagline" / "helper.py").is_file()

    # 2. Pre-create a flow with a custom Dockerfile (e.g. demo style)
    custom_dir = isolated_analyses_dir / "CustomDockerFlow"
    custom_dir.mkdir(parents=True, exist_ok=True)
    custom_dockerfile = (
        "FROM python:3.12-slim\n"
        "WORKDIR /app\n"
        "COPY . .\n"
        "COPY scripts/pc_entrypoint.sh /usr/local/bin/pc_entrypoint.sh\n"
        "RUN chmod +x /usr/local/bin/pc_entrypoint.sh\n"
        'ENTRYPOINT ["pc_entrypoint.sh", "python", "flow.py"]\n'
    )
    (custom_dir / "Dockerfile").write_text(custom_dockerfile, encoding="utf-8")

    webapp.save_flow(
        name="CustomDockerFlow",
        code='print("custom kept")\n',
    )
    assert (custom_dir / "Dockerfile").read_text(encoding="utf-8") == custom_dockerfile

"""
░████████╗███████╗░██████╗████████╗░░░░░░██████╗░███████╗██████╗░░██████╗██╗░██████╗████████╗
░╚══██╔══╝██╔════╝██╔════╝╚══██╔══╝░░░░░░██╔══██╗██╔════╝██╔══██╗██╔════╝██║██╔════╝╚══██╔══╝
░░░░██║░░░█████╗░░╚█████╗░░░░██║░░░█████╗██████╔╝█████╗░░██████╔╝╚█████╗░██║╚█████╗░░░░██║░░░
░░░░██║░░░██╔══╝░░░╚═══██╗░░░██║░░░╚════╝██╔═══╝░██╔══╝░░██╔══██╗░╚═══██╗██║░╚═══██╗░░░██║░░░
░░░░██║░░░███████╗██████╔╝░░░██║░░░░░░░░░██║░░░░░███████╗██║░░██║██████╔╝██║██████╔╝░░░██║░░░
░░░░╚═╝░░░╚══════╝╚═════╝░░░░╚═╝░░░░░░░░░╚═╝░░░░░╚══════╝╚═╝░░╚═╝╚═════╝░╚═╝╚═════╝░░░░╚═╝░░░
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from app import create_app
from config import Config
from models import Execution, FlowVersion, db


def test_data_dir_pvc_isolation_for_analyses_and_sqlite(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify setting DATA_DIR isolates Analyses/, Saved_data/, Saved_queries/, tmp/, and SQLite DB."""
    pvc_dir = tmp_path / "pvc_mount"
    monkeypatch.setenv("DATA_DIR", str(pvc_dir))

    class PvcTestConfig(Config):
        TESTING = True
        SECRET_KEY = "test-pvc-secret"
        WTF_CSRF_ENABLED = False
        DATA_DIR = str(pvc_dir)
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{pvc_dir / 'projectcompass.db'}"
        SCHEDULER_LOCK_FILE = str(pvc_dir / "tmp" / "scheduler.lock")

    pvc_app = create_app(PvcTestConfig)
    webapp = pvc_app.config["WEBAPP"]

    assert Path(pvc_app.config["DATA_DIR"]) == pvc_dir
    assert Path(webapp.save_folder_path) == pvc_dir / "Analyses"
    assert Path(webapp.save_data_path) == pvc_dir / "Saved_data"
    assert Path(webapp.save_queries_path) == pvc_dir / "Saved_queries"
    assert (pvc_dir / "Analyses").is_dir()
    assert (pvc_dir / "Saved_data").is_dir()
    assert (pvc_dir / "Saved_queries").is_dir()
    assert (pvc_dir / "tmp").is_dir()
    assert (pvc_dir / "rag_data").is_dir()

    with pvc_app.app_context():
        saved = webapp.save_flow(
            name="PersistentFlow",
            code='print("persisted on pvc")',
            description="Stored on PVC DATA_DIR",
        )
        assert saved["name"] == "PersistentFlow"
        assert (pvc_dir / "Analyses" / "PersistentFlow" / "flow.py").is_file()
        assert (pvc_dir / "projectcompass.db").is_file()
        assert FlowVersion.query.filter_by(flow_name="PersistentFlow").count() == 1

        exe = Execution(analysis_name="PersistentFlow", status="success", log_text="ok\n")
        db.session.add(exe)
        db.session.commit()
        assert Execution.query.filter_by(analysis_name="PersistentFlow").count() == 1


def test_k8s_manifests_and_kustomization_validity() -> None:
    """Validate all YAML manifests in k8s/ and verify RBAC covers required Kubernetes API resources."""
    repo_root = Path(__file__).resolve().parent.parent
    k8s_dir = repo_root / "k8s"
    assert k8s_dir.is_dir()

    kustomization_path = k8s_dir / "kustomization.yaml"
    assert kustomization_path.is_file()
    kustomization = yaml.safe_load(kustomization_path.read_text(encoding="utf-8"))
    resources = kustomization.get("resources") or []
    expected_files = [
        "namespace.yaml",
        "rbac.yaml",
        "pvc.yaml",
        "configmap.yaml",
        "deployment.yaml",
        "service.yaml",
    ]
    for fname in expected_files:
        assert fname in resources
        assert (k8s_dir / fname).is_file()

    # Validate Deployment mounts PVC at /app/data and configures /health probes
    deployment = yaml.safe_load((k8s_dir / "deployment.yaml").read_text(encoding="utf-8"))
    assert deployment["kind"] == "Deployment"
    pod_spec = deployment["spec"]["template"]["spec"]
    assert pod_spec["serviceAccountName"] == "projectcompass-console"
    container = pod_spec["containers"][0]
    assert any(vm["mountPath"] == "/app/data" for vm in container["volumeMounts"])
    assert container["livenessProbe"]["httpGet"]["path"] == "/health"
    assert container["readinessProbe"]["httpGet"]["path"] == "/health"

    # Validate ConfigMap defines generic k8s and resource limit keys
    configmap = yaml.safe_load((k8s_dir / "configmap.yaml").read_text(encoding="utf-8"))
    cm_data = configmap["data"]
    for required_key in (
        "DATA_DIR",
        "K8S_NAMESPACE",
        "K8S_DEFAULT_IMAGE",
        "K8S_DEFAULT_CPU_REQUEST",
        "K8S_DEFAULT_CPU_LIMIT",
        "K8S_DEFAULT_MEMORY_REQUEST",
        "K8S_DEFAULT_MEMORY_LIMIT",
        "K8S_SECRET_REFS",
    ):
        assert required_key in cm_data

    # Validate RBAC covers nodes, metrics.k8s.io, jobs, pods, pods/log, configmaps, and secrets
    rbac_docs = list(yaml.safe_load_all((k8s_dir / "rbac.yaml").read_text(encoding="utf-8")))
    kinds = {doc["kind"] for doc in rbac_docs if isinstance(doc, dict)}
    assert {"ServiceAccount", "ClusterRole", "ClusterRoleBinding", "Role", "RoleBinding"}.issubset(kinds)

    all_resources: set[str] = set()
    for doc in rbac_docs:
        if isinstance(doc, dict) and doc.get("kind") in ("ClusterRole", "Role"):
            for rule in doc.get("rules") or []:
                for res in rule.get("resources") or []:
                    all_resources.add(str(res))

    assert {"nodes", "jobs", "pods", "pods/log", "configmaps", "secrets"}.issubset(all_resources)


def test_git_sync_utils_mocked_subprocess(
    app: Any,
    tmp_path: Path,
) -> None:
    """Verify GitSyncUtils parent-child inheritance, token injection/sanitization, and subprocess calls."""
    from unittest.mock import MagicMock, patch

    from basefun import ProjectCompass
    from utils.analysis_utils import AnalysisUtils
    from utils.git_utils import GitSyncUtils

    assert issubclass(AnalysisUtils, GitSyncUtils)
    assert issubclass(ProjectCompass, GitSyncUtils)

    webapp = app.config["WEBAPP"]
    assert (
        webapp._inject_git_token("https://git.example.com/org/repo.git", "secret-tok-123")
        == "https://oauth2:secret-tok-123@git.example.com/org/repo.git"
    )
    assert (
        webapp._sanitize_git_text(
            "fatal: https://oauth2:secret-tok-123@git.example.com/org/repo.git failed",
            "secret-tok-123",
        )
        == "fatal: https://oauth2:***@git.example.com/org/repo.git failed"
    )

    target_dir = tmp_path / "mock_git_analyses"
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / ".git").mkdir()

    recorded_cmds: list[list[str]] = []

    def fake_run(cmd: list[str], **kwargs: Any) -> Any:
        recorded_cmds.append(cmd)
        res = MagicMock()
        res.returncode = 0
        res.stdout = "ok"
        res.stderr = ""
        return res

    with patch("utils.git_utils.subprocess.run", side_effect=fake_run):
        assert webapp.git_pull(target_dir=str(target_dir), branch="main") is True
        assert webapp.git_commit_and_push(
            target_dir=str(target_dir),
            message="Commit test flow",
            branch="main",
        ) is True

    assert ["git", "pull", "--no-rebase", "origin", "main"] in recorded_cmds
    assert ["git", "add", "-A"] in recorded_cmds
    assert ["git", "commit", "-m", "Commit test flow"] in recorded_cmds
    assert ["git", "push", "-u", "origin", "HEAD:main"] in recorded_cmds


def test_git_sync_end_to_end_with_local_bare_repository(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Initialize a bare Git repository in tmp_path, enable USE_GIT_SYNC, save a flow, and verify push."""
    import subprocess

    bare_repo = tmp_path / "remote_analyses.git"
    bare_repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "--bare", str(bare_repo)], check=True, capture_output=True)

    pvc_dir = tmp_path / "pvc_git_data"
    monkeypatch.setenv("DATA_DIR", str(pvc_dir))
    monkeypatch.setenv("USE_GIT_SYNC", "True")
    monkeypatch.setenv("GIT_REPO_URL", str(bare_repo))
    monkeypatch.setenv("GIT_BRANCH", "main")
    monkeypatch.setenv("GIT_SYNC_ON_SAVE", "True")

    class GitSyncTestConfig(Config):
        TESTING = True
        SECRET_KEY = "test-git-secret"
        WTF_CSRF_ENABLED = False
        DATA_DIR = str(pvc_dir)
        SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
        USE_GIT_SYNC = True
        GIT_REPO_URL = str(bare_repo)
        GIT_BRANCH = "main"
        GIT_SYNC_ON_SAVE = True

    git_app = create_app(GitSyncTestConfig)
    webapp = git_app.config["WEBAPP"]

    with git_app.app_context():
        webapp.save_flow(
            name="GitSyncedFlow",
            code='print("synced to bare git repo")',
            description="Auto-pushed flow",
            version_message="Initial git sync commit",
        )

    # Clone the bare repo into a verification directory and confirm GitSyncedFlow/flow.py was pushed
    verify_clone = tmp_path / "verify_clone"
    subprocess.run(
        ["git", "clone", "--branch", "main", str(bare_repo), str(verify_clone)],
        check=True,
        capture_output=True,
    )
    pushed_flow_py = verify_clone / "GitSyncedFlow" / "flow.py"
    assert pushed_flow_py.is_file()
    assert 'print("synced to bare git repo")' in pushed_flow_py.read_text(encoding="utf-8")

"""
░████████╗███████╗░██████╗████████╗░░░░░░██╗░░██╗░█████╗░░██████╗
░╚══██╔══╝██╔════╝██╔════╝╚══██╔══╝░░░░░░██║░██╔╝██╔══██╗██╔════╝
░░░░██║░░░█████╗░░╚█████╗░░░░██║░░░█████╗█████═╝░╚█████╔╝╚█████╗░
░░░░██║░░░██╔══╝░░░╚═══██╗░░░██║░░░╚════╝██╔═██╗░██╔══██╗░╚═══██╗
░░░░██║░░░███████╗██████╔╝░░░██║░░░░░░░░░██║░╚██╗╚█████╔╝██████╔╝
░░░░╚═╝░░░╚══════╝╚═════╝░░░░╚═╝░░░░░░░░░╚═╝░░╚═╝░╚════╝░╚═════╝░
"""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import patch

import pytest

from basefun import ProjectCompass
from models import K8sWorkerNode
from utils.k8s_utils import BaseK8sClient, K8sApiError, K8sClusterUtils


def _make_k8s_node(
    name: str,
    ip: str,
    ready: str = "True",
    cpu: str = "4",
    mem: str = "8388608Ki",
    role_label: str = "worker",
) -> dict[str, Any]:
    """Construct a realistic Kubernetes /api/v1/nodes item for testing."""
    return {
        "metadata": {
            "name": name,
            "uid": f"uid-{name}",
            "labels": {
                f"node-role.kubernetes.io/{role_label}": "true",
            },
        },
        "status": {
            "conditions": [
                {"type": "MemoryPressure", "status": "False"},
                {"type": "Ready", "status": ready},
            ],
            "addresses": [
                {"type": "InternalIP", "address": ip},
                {"type": "Hostname", "address": name},
            ],
            "capacity": {"cpu": cpu, "memory": mem},
            "allocatable": {"cpu": cpu, "memory": mem},
            "nodeInfo": {"kubeletVersion": "v1.30.2+k0s"},
        },
    }


def test_k8s_inheritance_hierarchy() -> None:
    """Verify strict parent-child OOP inheritance chain into ProjectCompass."""
    assert issubclass(K8sClusterUtils, BaseK8sClient)
    assert issubclass(ProjectCompass, K8sClusterUtils)


def test_workers_discovery_ready_notready_and_removed(app: Any, client: Any) -> None:
    """Verify node discovery, Ready -> NotReady transition, and Removed tracking."""
    webapp = app.config["WEBAPP"]

    initial_nodes = {
        "items": [
            _make_k8s_node("k0s-master-1", "10.0.0.10", ready="True", cpu="4", role_label="control-plane"),
            _make_k8s_node("worker-aws-1", "10.0.1.21", ready="True", cpu="8"),
            _make_k8s_node("worker-local-pc", "192.168.1.50", ready="True", cpu="16"),
        ]
    }
    metrics_payload = {
        "items": [
            {
                "metadata": {"name": "worker-aws-1"},
                "usage": {"cpu": "1250m", "memory": "2048Mi"},
            }
        ]
    }

    def fake_get_step1(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if path == "/api/v1/nodes":
            return initial_nodes
        if path == "/apis/metrics.k8s.io/v1beta1/nodes":
            return metrics_payload
        return {}

    with patch.object(webapp, "_k8s_get", side_effect=fake_get_step1):
        resp = client.get("/workers")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert "k0s-master-1" in html
        assert "worker-aws-1" in html
        assert "10.0.1.21" in html
        assert "worker-local-pc" in html
        assert "192.168.1.50" in html
        assert "8.0 GiB" in html
        assert "1250m used" in html

    # Step 2: worker-local-pc becomes unreachable (Ready=False -> NotReady, NOT Removed)
    not_ready_nodes = {
        "items": [
            _make_k8s_node("k0s-master-1", "10.0.0.10", ready="True", cpu="4", role_label="control-plane"),
            _make_k8s_node("worker-aws-1", "10.0.1.21", ready="True", cpu="8"),
            _make_k8s_node("worker-local-pc", "192.168.1.50", ready="False", cpu="16"),
        ]
    }

    with patch.object(webapp, "_k8s_get", return_value=not_ready_nodes):
        resp_table = client.get("/workers/table")
        assert resp_table.status_code == 200
        with app.app_context():
            pc_node = K8sWorkerNode.query.filter_by(name="worker-local-pc").first()
            assert pc_node is not None
            assert pc_node.status == "NotReady"
            assert pc_node.removed_at is None

    # Step 3: worker-local-pc is deleted from cluster -> marked Removed with removed_at timestamp
    after_delete_nodes = {
        "items": [
            _make_k8s_node("k0s-master-1", "10.0.0.10", ready="True", cpu="4", role_label="control-plane"),
            _make_k8s_node("worker-aws-1", "10.0.1.21", ready="True", cpu="8"),
        ]
    }

    with patch.object(webapp, "_k8s_get", return_value=after_delete_nodes):
        resp_after = client.get("/workers/table")
        assert resp_after.status_code == 200
        html_after = resp_after.data.decode("utf-8")
        assert "Removed" in html_after
        with app.app_context():
            pc_node = K8sWorkerNode.query.filter_by(name="worker-local-pc").first()
            aws_node = K8sWorkerNode.query.filter_by(name="worker-aws-1").first()
            assert pc_node is not None
            assert pc_node.status == "Removed"
            assert pc_node.removed_at is not None
            assert aws_node is not None
            assert aws_node.status == "Ready"


def test_workers_graceful_when_k8s_unreachable(app: Any, client: Any) -> None:
    """Verify /workers displays a warning banner instead of HTTP 500 when K8s API fails."""
    webapp = app.config["WEBAPP"]
    with patch.object(webapp, "_k8s_get", side_effect=K8sApiError("Connection refused")):
        resp = client.get("/workers")
        assert resp.status_code == 200
        assert b"Unable to reach live k0s API" in resp.data


def test_workers_strictly_read_only(client: Any, unauth_client: Any) -> None:
    """Verify Workers routes are strictly read-only and require authentication."""
    for method in (client.post, client.put, client.delete, client.patch):
        resp = method("/workers")
        assert resp.status_code == 405
        resp_table = method("/workers/table")
        assert resp_table.status_code == 405

    unauth_resp = unauth_client.get("/workers")
    assert unauth_resp.status_code == 200
    assert b"k0s Cluster Workers (Read-Only)" not in unauth_resp.data


@pytest.mark.k0s
@pytest.mark.skipif(
    os.environ.get("K0S_LIVE_TEST") != "1",
    reason="Live k0s test skipped unless K0S_LIVE_TEST=1 is set.",
)
def test_live_k0s_cluster_nodes_and_hello_world(app: Any) -> None:
    """Optional live verification against a real k0s cluster (never modifies external hosts)."""
    webapp = app.config["WEBAPP"]
    nodes, err = webapp.sync_worker_nodes()
    assert err is None, f"Expected live k0s API connection to succeed, got: {err}"
    assert len(nodes) >= 1
    assert any(n.status == "Ready" for n in nodes)

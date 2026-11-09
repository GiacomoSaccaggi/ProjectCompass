"""Tests for K8s flow execution hierarchy (chain tests removed)."""

from __future__ import annotations

from basefun import ProjectCompass
from utils.k8s_utils import BaseK8sClient, K8sClusterUtils, K8sFlowRunnerUtils


def test_flow_runner_inheritance_hierarchy() -> None:
    """Verify BaseK8sClient -> K8sClusterUtils -> K8sFlowRunnerUtils -> ProjectCompass."""
    assert issubclass(K8sFlowRunnerUtils, K8sClusterUtils)
    assert issubclass(K8sFlowRunnerUtils, BaseK8sClient)
    assert issubclass(ProjectCompass, K8sFlowRunnerUtils)

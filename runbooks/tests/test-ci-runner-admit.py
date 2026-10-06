#!/usr/bin/env python3
"""Regression checks for ARC pods sharing the CI thermal gate."""
import importlib.util
import io
import json
import os
import pathlib
import unittest
from unittest.mock import patch


ROOT = pathlib.Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("ci_admit", ROOT / "scripts/ninth-banner-admit.py")
admit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(admit)


def pod(name, namespace, lane, node=None, gated=False):
    return {
        "metadata": {
            "name": name,
            "namespace": namespace,
            "creationTimestamp": "2026-10-06T12:00:00Z",
            "labels": {"ci.cberg.home/lane": lane},
        },
        "spec": {
            "nodeName": node,
            "containers": [{"resources": {"requests": {"cpu": "1", "memory": "1Gi"}}}],
            "schedulingGates": [{"name": admit.GATE}] if gated else [],
        },
        "status": {"phase": "Pending" if gated else "Running"},
    }


class ThermalGateNamespaces(unittest.TestCase):
    def test_snapshot_counts_runner_and_build_pods_from_both_namespaces(self):
        data = {
            "ci-runner": [pod("test", "ci-runner", "cpu", "k8s-nuc14-01")],
            "arc-build": [pod("build", "arc-build", "browser", "k8s-nuc14-01")],
        }

        def get_pods(*args, **kwargs):
            return json.dumps({"items": data[args[args.index("-n") + 1]]})

        with patch.object(admit, "kubectl", side_effect=get_pods):
            count, _, queue, requests = admit.snapshot()
        self.assertEqual(count["k8s-nuc14-01"], {"browser": 1, "cpu": 1})
        self.assertEqual(queue, [])
        self.assertEqual(requests["k8s-nuc14-01"]["cpu"], 2)

    def test_release_patches_the_pods_own_namespace(self):
        candidate = pod("build", "arc-build", "browser", gated=True)
        candidate["metadata"]["resourceVersion"] = "42"
        with patch.object(admit, "kubectl") as call:
            admit.release(candidate, "k8s-nuc14-03")
        self.assertEqual(call.call_args.args[2:4], ("-n", "arc-build"))

    def test_in_cluster_get_uses_only_the_namespaced_pod_api(self):
        with patch.dict(os.environ, {"KUBERNETES_SERVICE_HOST": "kubernetes.default.svc"}), \
             patch.object(admit, "cluster_request", return_value=b'{"items":[]}') as request:
            out = admit.kubectl("get", "pods", "-n", "arc-build", "-l", "app=runner", "-o", "json")
        self.assertEqual(json.loads(out), {"items": []})
        self.assertEqual(request.call_args.args[0],
                         "/api/v1/namespaces/arc-build/pods?labelSelector=app%3Drunner")

    def test_restartable_dind_init_container_counts_with_runner_cpu(self):
        build = pod("build", "arc-build", "browser", "k8s-nuc14-01")
        build["spec"]["initContainers"] = [
            {"name": "copy", "resources": {"requests": {"cpu": "100m"}}},
            {"name": "dind", "restartPolicy": "Always",
             "resources": {"requests": {"cpu": "1", "memory": "1Gi"}}},
        ]
        self.assertEqual(admit.pod_requests(build)["cpu"], 2)


if __name__ == "__main__":
    unittest.main()

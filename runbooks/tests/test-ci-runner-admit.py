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
            count, _, queue, requests, idle = admit.snapshot()
        self.assertEqual(count["k8s-nuc14-01"], {"browser": 1, "cpu": 1})
        self.assertEqual(idle, {})
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


def runner(name, namespace, lane, node, started="2026-10-06T12:00:00Z"):
    p = pod(name, namespace, lane, node)
    p["metadata"]["ownerReferences"] = [{"kind": "EphemeralRunner", "name": name}]
    p["metadata"]["annotations"] = {admit.RELEASED_AT: started}
    return p


def er(name, job=None):
    return {"metadata": {"name": name}, "status": {"jobId": job} if job else {}}


class WarmIdleRunners(unittest.TestCase):
    NOW = admit.ts("2026-10-06T13:00:00Z")

    def snap(self, pods, runners):
        def get(*args, **kwargs):
            ns = args[args.index("-n") + 1]
            if args[1] == "ephemeralrunners":
                if runners is None:
                    raise RuntimeError("forbidden")
                return json.dumps({"items": runners.get(ns, [])})
            return json.dumps({"items": [p for p in pods if p["metadata"]["namespace"] == ns]})
        with patch.object(admit, "kubectl", side_effect=get):
            return admit.snapshot(self.NOW)

    def test_idle_runner_keeps_budget_but_frees_its_lane_slot(self):
        pods = [runner("cpu-a", "ci-runner", "cpu", "k8s-nuc14-03"),
                runner("build-a", "arc-build", "browser", "k8s-nuc14-03")]
        count, _, _, req, idle = self.snap(pods, {"ci-runner": [er("cpu-a")], "arc-build": [er("build-a")]})
        self.assertEqual(count["k8s-nuc14-03"], {"browser": 0, "cpu": 0})
        self.assertEqual(idle, {"k8s-nuc14-03": 2})
        self.assertEqual(req["k8s-nuc14-03"]["cpu"], 2)

    def test_busy_runner_counts_in_full(self):
        pods = [runner("cpu-a", "ci-runner", "cpu", "k8s-nuc14-01")]
        count, _, _, _, idle = self.snap(pods, {"ci-runner": [er("cpu-a", job="j1")]})
        self.assertEqual(count["k8s-nuc14-01"]["cpu"], 1)
        self.assertEqual(idle, {})

    def test_runner_inside_settle_window_counts_in_full(self):
        pods = [runner("cpu-a", "ci-runner", "cpu", "k8s-nuc14-01", started="2026-10-06T12:58:00Z")]
        count, _, _, _, idle = self.snap(pods, {"ci-runner": [er("cpu-a")]})
        self.assertEqual(count["k8s-nuc14-01"]["cpu"], 1)
        self.assertEqual(idle, {})

    def test_unreadable_job_state_fails_closed(self):
        pods = [runner("cpu-a", "ci-runner", "cpu", "k8s-nuc14-01")]
        count, _, _, _, idle = self.snap(pods, None)
        self.assertEqual(count["k8s-nuc14-01"]["cpu"], 1)
        self.assertEqual(idle, {})

    def test_idle_runner_still_selects_the_second_pod_temperature_tier(self):
        temps = {"k8s-nuc14-01": (80.0, 85.0)}   # >= 78 second-pod limit, < 88 first-pod limit
        free = {"k8s-nuc14-01": {"cpu": 8.0, "memory": 64 * 2**30, "gpu": 1.0}}
        args = ("k8s-nuc14-01", "browser", {"cpu": 2.0, "memory": 2**30, "gpu": 1.0}, temps,
                {"k8s-nuc14-01": {"browser": 0, "cpu": 0}}, {}, self.NOW, free,
                {"k8s-nuc14-01": {"cpu": 1.6, "memory": 0.0, "gpu": 0.0}}, {})
        self.assertEqual(admit.closed_reason(*args), "")
        self.assertIn("2nd-pod limit", admit.closed_reason(*args, {"k8s-nuc14-01": 1}))

    def test_in_cluster_ephemeralrunner_list_uses_the_namespaced_crd_api(self):
        with patch.dict(os.environ, {"KUBERNETES_SERVICE_HOST": "kubernetes.default.svc"}), \
             patch.object(admit, "cluster_request", return_value=b'{"items":[]}') as request:
            admit.kubectl("get", "ephemeralrunners", "-n", "arc-build", "-o", "json")
        self.assertEqual(request.call_args.args[0],
                         "/apis/actions.github.com/v1alpha1/namespaces/arc-build/ephemeralrunners")


if __name__ == "__main__":
    unittest.main()

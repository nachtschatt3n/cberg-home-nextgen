#!/usr/bin/env python3
"""backup-restore-proof — prove a Longhorn backup actually RESTORES (G2).

"Verified" backups are Schroedinger's until restored: checksum-clean backup
files prove nothing about whether postgres will start on them. This probe is
the runtime `backup_gate` for AUTO-BACKUP-GATED plans and the automated form
of the quarterly restore drill (docs/sops/control-liveness.md):

  1. newest Completed Longhorn Backup CR for --volume (EXACT name match —
     `postgresql-data` is a retired volume's leftover record; the live one is
     `postgresql-data-5g`; substring matching would happily prove the wrong,
     nine-month-old backup restores)
  2. restore it into a SCRATCH Longhorn volume (1 replica, unique name)
  3. attach via scratch PV/PVC to a scratch postgres pod (same image + PGDATA
     as the live deployment) and wait for pg_isready
  4. smoke: count databases and rows in a real table
  5. tear everything down, PASS/FAIL on exit code

SAFETY: the source volume is never touched — Longhorn restores from the
backupstore into a NEW volume. Every scratch object carries the
restore-proof=true label and a unique run suffix; the probe REFUSES to start
if leftovers from a previous run exist (fail loud, never pile up). Teardown
runs in `finally`. Blast radius of any failure: the scratch copies only.

Usage:
  runbooks/backup-restore-proof.py                        # defaults: postgresql-data-5g
  runbooks/backup-restore-proof.py --volume superset-postgresql-data \\
      --image pgvector/pgvector:0.8.6-pg16 --keep   # keep scratch for inspection

Exit: 0 restore PROVEN · 1 FAILED · 2 preconditions (leftovers / no backup).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone

RUN = datetime.now(timezone.utc).strftime("%m%d%H%M")


def sh(args, timeout=60, input_=None):
    p = subprocess.run(args, capture_output=True, text=True,
                       timeout=timeout, input=input_)
    return p.returncode, p.stdout.strip(), p.stderr.strip()


def kubectl_json(args, timeout=60):
    rc, out, err = sh(["kubectl", *args, "-o", "json"], timeout)
    if rc != 0:
        raise RuntimeError(f"kubectl {' '.join(args)}: {err[:200]}")
    return json.loads(out)


def newest_backup(volume: str):
    d = kubectl_json(["-n", "storage", "get", "backups.longhorn.io"])
    cands = [b for b in d["items"]
             if b.get("status", {}).get("volumeName") == volume
             and b.get("status", {}).get("state") == "Completed"]
    if not cands:
        return None
    return max(cands, key=lambda b: b["status"].get("snapshotCreatedAt", ""))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--volume", default="postgresql-data-5g")
    ap.add_argument("--image", default="pgvector/pgvector:0.8.6-pg16")
    ap.add_argument("--pgdata", default="/var/lib/postgresql/data/pgdata")
    ap.add_argument("--namespace", default="databases")
    ap.add_argument("--smoke-table", default=None,
                    help="db.table to count (default: just count databases)")
    ap.add_argument("--timeout-restore", type=int, default=900)
    ap.add_argument("--timeout-start", type=int, default=300)
    ap.add_argument("--keep", action="store_true",
                    help="keep the scratch objects for inspection (manual cleanup!)")
    a = ap.parse_args()

    scratch = f"restoreproof-{RUN}"
    ns = a.namespace

    # refuse to run over leftovers
    d = kubectl_json(["-n", "storage", "get", "volumes.longhorn.io",
                      "-l", "restore-proof=true"])
    if d["items"]:
        print(f"PRECONDITION: leftover restore-proof volume(s) exist "
              f"({[v['metadata']['name'] for v in d['items']]}) — clean up first",
              file=sys.stderr)
        return 2

    bk = newest_backup(a.volume)
    if not bk:
        print(f"PRECONDITION: no Completed backup for volume {a.volume!r} "
              f"(exact match) — nothing to prove", file=sys.stderr)
        return 2
    url = bk["status"].get("url")
    when = bk["status"].get("snapshotCreatedAt")
    print(f"proving: {bk['metadata']['name']} of {a.volume} ({when})")

    created = []   # (kind, ns_or_None, name) in creation order
    try:
        # 1. scratch volume from backup
        vol = {
            "apiVersion": "longhorn.io/v1beta2", "kind": "Volume",
            "metadata": {"name": scratch, "namespace": "storage",
                         "labels": {"restore-proof": "true"}},
            "spec": {"fromBackup": url, "numberOfReplicas": 1,
                     "frontend": "blockdev"},
        }
        rc, _, err = sh(["kubectl", "apply", "-f", "-"], 60, json.dumps(vol))
        if rc != 0:
            raise RuntimeError(f"volume create: {err[:200]}")
        created.append(("volumes.longhorn.io", "storage", scratch))

        print("waiting for restore ...", end="", flush=True)
        deadline = time.time() + a.timeout_restore
        while time.time() < deadline:
            v = kubectl_json(["-n", "storage", "get", "volumes.longhorn.io", scratch])
            st = v.get("status", {})
            if st.get("state") == "detached" and not st.get("restoreRequired", True):
                print(" restored")
                break
            if st.get("robustness") == "faulted":
                raise RuntimeError("scratch volume FAULTED during restore")
            time.sleep(10)
            print(".", end="", flush=True)
        else:
            raise RuntimeError("restore did not complete in time")

        # 2. PV + PVC + pod
        pv = {"apiVersion": "v1", "kind": "PersistentVolume",
              "metadata": {"name": scratch, "labels": {"restore-proof": "true"}},
              "spec": {"capacity": {"storage": "5Gi"},
                       "accessModes": ["ReadWriteOnce"],
                       "persistentVolumeReclaimPolicy": "Retain",
                       "storageClassName": "longhorn-static",
                       "csi": {"driver": "driver.longhorn.io",
                               "volumeHandle": scratch, "fsType": "ext4"}}}
        pvc = {"apiVersion": "v1", "kind": "PersistentVolumeClaim",
               "metadata": {"name": scratch, "namespace": ns,
                            "labels": {"restore-proof": "true"}},
               "spec": {"accessModes": ["ReadWriteOnce"],
                        "storageClassName": "longhorn-static",
                        "volumeName": scratch,
                        "resources": {"requests": {"storage": "5Gi"}}}}
        pod = {"apiVersion": "v1", "kind": "Pod",
               "metadata": {"name": scratch, "namespace": ns,
                            "labels": {"restore-proof": "true"}},
               "spec": {"restartPolicy": "Never",
                        "containers": [{
                            "name": "pg", "image": a.image,
                            "env": [{"name": "PGDATA", "value": a.pgdata},
                                    {"name": "POSTGRES_PASSWORD",
                                     "value": "unused-data-dir-exists"}],
                            "volumeMounts": [{"name": "data",
                                              "mountPath": "/var/lib/postgresql/data"}],
                            "resources": {"requests": {"cpu": "100m", "memory": "256Mi"},
                                          "limits": {"memory": "1Gi"}}}],
                        "volumes": [{"name": "data",
                                     "persistentVolumeClaim": {"claimName": scratch}}]}}
        for obj, kind, kns in ((pv, "pv", None), (pvc, "pvc", ns), (pod, "pod", ns)):
            rc, _, err = sh(["kubectl", "apply", "-f", "-"], 60, json.dumps(obj))
            if rc != 0:
                raise RuntimeError(f"{kind} create: {err[:200]}")
            created.append((kind, kns, scratch))

        print("waiting for postgres ...", end="", flush=True)
        deadline = time.time() + a.timeout_start
        up = False
        while time.time() < deadline:
            rc, out, _ = sh(["kubectl", "-n", ns, "exec", scratch, "--",
                             "pg_isready", "-U", "postgres"], 30)
            if rc == 0 and "accepting connections" in out:
                up = True
                print(" up")
                break
            time.sleep(10)
            print(".", end="", flush=True)
        if not up:
            rc, out, _ = sh(["kubectl", "-n", ns, "logs", scratch, "--tail=15"], 30)
            raise RuntimeError(f"postgres never became ready. tail: {out[-400:]}")

        # 3. smoke — local socket, peer auth as the in-container postgres user
        rc, out, err = sh(["kubectl", "-n", ns, "exec", scratch, "--",
                           "psql", "-U", "postgres", "-tA",
                           "-c", "SELECT count(*) FROM pg_database"], 30)
        if rc != 0 or not out.strip().isdigit() or int(out) < 3:
            raise RuntimeError(f"database-count smoke failed: rc={rc} out={out!r} {err[:150]}")
        ndb = int(out)
        extra = ""
        if a.smoke_table:
            db, table = a.smoke_table.split(".", 1)
            rc, out, err = sh(["kubectl", "-n", ns, "exec", scratch, "--",
                               "psql", "-U", "postgres", "-d", db, "-tA",
                               "-c", f"SELECT count(*) FROM {table}"], 30)
            if rc != 0 or not out.strip().isdigit():
                raise RuntimeError(f"table smoke failed: {err[:200]}")
            extra = f", {a.smoke_table}={out} rows"
        print(f"RESTORE PROVEN: backup {bk['metadata']['name']} ({when}) boots "
              f"postgres with {ndb} databases{extra}")
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"\nRESTORE PROOF FAILED: {e}", file=sys.stderr)
        return 1
    finally:
        if a.keep:
            print(f"--keep: scratch objects '{scratch}' left for inspection "
                  f"(label restore-proof=true; delete pod,pvc,pv then the "
                  f"Longhorn volume)")
        else:
            for kind, kns, name in reversed(created):
                nsargs = ["-n", kns] if kns else []
                sh(["kubectl", *nsargs, "delete", kind, name,
                    "--ignore-not-found", "--timeout=120s"], 150)
            print("scratch objects removed")


if __name__ == "__main__":
    sys.exit(main())

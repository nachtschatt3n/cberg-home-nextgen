#!/usr/bin/env python3
"""longhorn-bulk-restore — restore many/all Longhorn volumes from the backup target.

Total-loss / damaged-cluster tool. Point a (new) Longhorn at the restored
backupstore (see docs/sops/longhorn.md "Total-loss Longhorn restore"), let it
sync BackupVolume/Backup CRs, then run this to recreate every volume under its
ORIGINAL name (the house rule is volume == PV == PVC name, so the normal Flux
apply of pv.yaml/pvc then binds to the restored data with no manifest change).

Safe by default:
  * DRY-RUN unless --apply is given; the plan table is printed either way.
  * Read-only against everything except `Volume` CRs it creates (and, with
    --create-pv, PVs). It never deletes anything unless --force is given, and
    --force only ever deletes a DETACHED Longhorn Volume whose exact name it is
    about to restore onto, and only with --yes.
  * Refuses to touch an existing volume of the same name.
  * Backups whose newest completed backup is older than --max-age-days are
    treated as retired volumes (STALE) and skipped unless --include-stale.

Usage (always through mise so the repo kubeconfig is used):
  mise exec -- runbooks/longhorn-bulk-restore.py                    # dry-run plan, all volumes
  mise exec -- runbooks/longhorn-bulk-restore.py --only 'grafana-*' --apply
  mise exec -- runbooks/longhorn-bulk-restore.py --name-prefix restoretest- \\
      --only grafana-config --apply --create-pv                     # scratch restore
  mise exec -- runbooks/longhorn-bulk-restore.py --apply --parallel 2 --exclude 'prometheus-*'

Longhorn's own `restore-concurrent-limit` setting (live: 1) still serialises
restores cluster-side; --parallel only controls how many Volume CRs this tool
keeps in flight.

Exit code: 0 all requested volumes restored (or dry-run), 1 any failure.
"""
import argparse
import fnmatch
import json
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

NS = "storage"
LH = "longhorn.io/v1beta2"
RESTORE_LABEL = "bulk-restore"
PRINT_LOCK = threading.Lock()


def log(msg):
    with PRINT_LOCK:
        print(msg, flush=True)


def sh(args, timeout=60, input_=None):
    p = subprocess.run(args, input=input_, capture_output=True, text=True, timeout=timeout)
    return p.returncode, p.stdout, p.stderr


def kjson(args, timeout=120):
    rc, out, err = sh(["kubectl", *args, "-o", "json"], timeout)
    if rc != 0:
        raise RuntimeError(f"kubectl {' '.join(args)}: {err.strip()[:300]}")
    return json.loads(out)


def kapply(obj):
    rc, _, err = sh(["kubectl", "apply", "-f", "-"], 60, json.dumps(obj))
    if rc != 0:
        raise RuntimeError(f"apply {obj['kind']}/{obj['metadata']['name']}: {err.strip()[:300]}")


def parse_ts(s):
    try:
        return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def gib(n):
    return round(int(n or 0) / 2**30, 1)


def quantity(nbytes):
    nbytes = int(nbytes)
    if nbytes % 2**30 == 0:
        return f"{nbytes // 2**30}Gi"
    return str(nbytes)


# ---------------------------------------------------------------- discovery
def discover(a):
    """Return (plan_rows, gaps). One row per backup volume with a usable backup."""
    bvs = kjson(["-n", NS, "get", "backupvolumes.longhorn.io"])["items"]
    backups = kjson(["-n", NS, "get", "backups.longhorn.io"])["items"]
    live = {v["metadata"]["name"] for v in kjson(["-n", NS, "get", "volumes.longhorn.io"])["items"]}

    by_vol = {}
    for b in backups:
        st = b.get("status", {})
        if st.get("state") == "Completed" and st.get("url"):
            by_vol.setdefault(st.get("volumeName"), []).append(b)

    # Ages are measured against the NEWEST backup in the store, not the wall clock:
    # after a total loss the restore may happen weeks later and every volume would
    # otherwise look "stale". Retired volumes are the ones that stopped being backed
    # up while the rest of the store kept moving.
    stamps = [parse_ts(b["status"].get("snapshotCreatedAt")) for bl in by_vol.values() for b in bl]
    ref = max([t for t in stamps if t], default=datetime.now(timezone.utc))
    now = datetime.now(timezone.utc)
    rows = []
    for bv in bvs:
        vname = bv["spec"].get("volumeName") or bv["metadata"].get("labels", {}).get("backup-volume")
        st = bv.get("status", {})
        cands = by_vol.get(vname, [])
        cands.sort(key=lambda b: b["status"].get("snapshotCreatedAt") or "")
        # prefer the backup volume's own lastBackupName when it is Completed
        pick = None
        for b in cands:
            if b["metadata"]["name"] == st.get("lastBackupName"):
                pick = b
        if pick is None and cands:
            pick = cands[-1]
        row = {"volume": vname, "backupvolume": bv["metadata"]["name"], "backup": None,
               "age_days": None, "size": int(st.get("size") or 0), "stored": int(st.get("dataStored") or 0),
               "sc": st.get("storageClassName", ""), "labels": st.get("labels", {}),
               "status": "PLAN", "why": ""}
        if pick is None:
            row.update(status="NOBACKUP", why="no Completed Backup CR")
            rows.append(row)
            continue
        ps = pick["status"]
        row["backup"] = pick["metadata"]["name"]
        row["url"] = ps["url"]
        row["size"] = int(ps.get("volumeSize") or row["size"] or 0)
        ts = parse_ts(ps.get("snapshotCreatedAt"))
        if ts:
            row["age_days"] = (ref - ts).days
        k8s = {}
        try:
            k8s = json.loads(row["labels"].get("KubernetesStatus", "{}"))
        except ValueError:
            pass
        row["k8s"] = k8s
        row["mode"] = row["labels"].get("longhorn.io/volume-access-mode") or \
            (pick.get("spec", {}).get("labels") or {}).get("longhorn.io/volume-access-mode", "rwo")
        row["target"] = f"{a.name_prefix}{vname}"
        if not fnmatch_any(vname, a.only, True) or fnmatch_any(vname, a.exclude, False):
            row.update(status="FILTERED", why="--only/--exclude")
        elif row["age_days"] is not None and row["age_days"] > a.max_age_days and not a.include_stale:
            row.update(status="STALE", why=f"newest backup {row['age_days']}d old (> {a.max_age_days}d); retired?")
        elif row["target"] in live:
            row.update(status="EXISTS", why="volume already present" + (" (--force)" if a.force else ""))
        rows.append(row)

    # live volumes with no usable backup at all, or stale backups
    gaps = []
    names = {r["volume"]: r for r in rows}
    for v in sorted(live):
        if a.name_prefix and v.startswith(a.name_prefix):
            continue  # scratch restores from a previous run
        r = names.get(v)
        if r is None:
            gaps.append((v, "NO BackupVolume in the backup target"))
        elif r["backup"] is None:
            gaps.append((v, "BackupVolume exists but no Completed backup"))
        elif r["age_days"] is not None and r["age_days"] > 2:
            gaps.append((v, f"newest backup is {r['age_days']}d older than the store's newest"))
    return rows, gaps


def fnmatch_any(name, patterns, default):
    if not patterns:
        return default
    return any(fnmatch.fnmatch(name, p) for p in patterns)


# ---------------------------------------------------------------- restore
def volume_manifest(r, a):
    mode = r.get("mode", "rwo")
    locality = "disabled" if r["sc"] == "longhorn" else "best-effort"
    return {
        "apiVersion": LH, "kind": "Volume",
        "metadata": {"name": r["target"], "namespace": NS,
                     "labels": {RESTORE_LABEL: "true"}},
        "spec": {"fromBackup": r["url"], "size": str(r["size"]),
                 "numberOfReplicas": a.replicas, "accessMode": mode,
                 "frontend": "blockdev", "dataLocality": locality,
                 "staleReplicaTimeout": 30},
    }


def pv_manifest(r, a):
    dynamic = r["sc"] == "longhorn" or r["volume"].startswith("pvc-")
    attrs = {"numberOfReplicas": str(a.replicas), "staleReplicaTimeout": "30"}
    spec = {
        "capacity": {"storage": quantity(r["size"])},
        "volumeMode": "Filesystem",
        "accessModes": ["ReadWriteMany" if r.get("mode") == "rwx" else "ReadWriteOnce"],
        "persistentVolumeReclaimPolicy": "Retain",  # never Delete on a restored volume
        "storageClassName": "longhorn" if dynamic else "longhorn-static",
        "csi": {"driver": "driver.longhorn.io", "fsType": "ext4",
                "volumeAttributes": attrs, "volumeHandle": r["target"]},
    }
    k8s = r.get("k8s") or {}
    ns = a.target_namespace or k8s.get("namespace")
    # Dynamic PVs have no pv.yaml in git, so pre-bind them to their claim. Static
    # ones stay unbound: Flux applies the PVC with spec.volumeName == PV name.
    if dynamic and ns and k8s.get("pvcName") and not a.name_prefix:
        spec["claimRef"] = {"apiVersion": "v1", "kind": "PersistentVolumeClaim",
                            "namespace": ns, "name": k8s["pvcName"]}
    return {"apiVersion": "v1", "kind": "PersistentVolume",
            "metadata": {"name": r["target"], "labels": {RESTORE_LABEL: "true"}}, "spec": spec}


def restore_one(r, a):
    """Create + wait. Returns (status, seconds, detail)."""
    t0 = time.time()
    name = r["target"]
    try:
        if a.force:
            existing = sh(["kubectl", "-n", NS, "get", "volumes.longhorn.io", name, "-o", "json"])
            if existing[0] == 0:
                state = json.loads(existing[1]).get("status", {}).get("state")
                if state != "detached":
                    return "FAILED", 0, f"--force refused: existing volume is {state}, not detached"
                if not a.yes:
                    return "FAILED", 0, "--force needs --yes"
                log(f"[{name}] --force: deleting existing DETACHED volume")
                rc, _, err = sh(["kubectl", "-n", NS, "delete", "volumes.longhorn.io", name, "--wait=true",
                                 "--timeout=120s"], 150)
                if rc != 0:
                    return "FAILED", 0, f"delete existing: {err.strip()[:200]}"
        kapply(volume_manifest(r, a))
        log(f"[{name}] created from backup {r['backup']} ({gib(r['size'])} GiB provisioned, "
            f"{gib(r['stored'])} GiB stored); waiting")
        deadline = t0 + a.timeout
        last = 0
        while time.time() < deadline:
            v = kjson(["-n", NS, "get", "volumes.longhorn.io", name])
            st = v.get("status", {})
            if st.get("robustness") == "faulted":
                return "FAILED", time.time() - t0, "volume FAULTED during restore"
            if st.get("state") == "detached" and st.get("restoreInitiated") \
                    and not st.get("restoreRequired", True) \
                    and not st.get("isStandby", False) and st.get("robustness") in ("healthy", "unknown", None, ""):
                break
            if time.time() - last >= a.progress_interval:
                last = time.time()
                log(f"[{name}] {int(last - t0)}s state={st.get('state')} robustness={st.get('robustness')} "
                    f"restoreRequired={st.get('restoreRequired')}")
            time.sleep(5)
        else:
            return "FAILED", time.time() - t0, f"timeout after {a.timeout}s (volume left in place)"
        if a.create_pv:
            kapply(pv_manifest(r, a))
        return "RESTORED", time.time() - t0, ""
    except Exception as e:  # noqa: BLE001 - report every failure in the table
        return "FAILED", time.time() - t0, str(e)[:200]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="actually create volumes (default: dry-run)")
    ap.add_argument("--only", action="append", help="glob on ORIGINAL volume name (repeatable)")
    ap.add_argument("--exclude", action="append", help="glob on ORIGINAL volume name (repeatable)")
    ap.add_argument("--parallel", type=int, default=2, help="Volume CRs in flight (default 2; etcd is sensitive)")
    ap.add_argument("--name-prefix", default="", help="restore as <prefix><name> (scratch restores, e.g. restoretest-)")
    ap.add_argument("--target-namespace", help="claimRef namespace for dynamic PVs created by --create-pv")
    ap.add_argument("--create-pv", action="store_true", help="also create the PV (volumeHandle == name)")
    ap.add_argument("--replicas", type=int, default=2, help="numberOfReplicas (house class default 2)")
    ap.add_argument("--timeout", type=int, default=1800, help="per-volume restore timeout seconds")
    ap.add_argument("--progress-interval", type=int, default=30)
    ap.add_argument("--max-age-days", type=int, default=30,
                    help="newest backup older than this => STALE (retired volume), skipped")
    ap.add_argument("--include-stale", action="store_true")
    ap.add_argument("--force", action="store_true",
                    help="delete an existing DETACHED same-name volume first (needs --yes). DESTRUCTIVE")
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args()

    if a.force and not a.name_prefix:
        log("NOTE: --force without --name-prefix would delete a PRODUCTION-named volume. "
            "Refusing; use it only with a scratch --name-prefix (or delete by hand per the SOP).")
        return 2

    rows, gaps = discover(a)
    rows.sort(key=lambda r: (r["status"] != "PLAN", r["volume"]))
    log(f"{'VOLUME':<48}{'GiB':>6}{'STORED':>8}{'AGE':>5}  {'STATUS':<9} NOTE")
    for r in rows:
        if r["status"] == "FILTERED":
            continue
        log(f"{r['volume']:<48}{gib(r['size']):>6}{gib(r['stored']):>8}"
            f"{(str(r['age_days']) + 'd') if r['age_days'] is not None else '-':>5}  {r['status']:<9} {r['why']}")
    todo = [r for r in rows if r["status"] == "PLAN" or (r["status"] == "EXISTS" and a.force)]
    log(f"\n{len(todo)} to restore, "
        f"{sum(1 for r in rows if r['status'] == 'EXISTS' and not a.force)} exist (refused), "
        f"{sum(1 for r in rows if r['status'] == 'STALE')} stale, "
        f"{sum(1 for r in rows if r['status'] == 'FILTERED')} filtered, "
        f"{sum(1 for r in rows if r['status'] == 'NOBACKUP')} without usable backup; "
        f"restore volume total {gib(sum(r['size'] for r in todo))} GiB provisioned / "
        f"{gib(sum(r['stored'] for r in todo))} GiB stored")
    if gaps:
        log("\nBACKUP GAPS among live volumes:")
        for v, why in gaps:
            log(f"  {v}: {why}")
    if not a.apply:
        log("\nDRY-RUN: nothing created. Re-run with --apply to restore.")
        return 0
    if not todo:
        log("nothing to do")
        return 0

    results = {}
    with ThreadPoolExecutor(max_workers=max(1, a.parallel)) as ex:
        futs = {ex.submit(restore_one, r, a): r for r in todo}
        for f, r in futs.items():
            results[r["target"]] = f.result()

    log("\nSUMMARY")
    log(f"{'VOLUME':<56}{'RESULT':<10}{'SECONDS':>8}  DETAIL")
    bad = 0
    for r in todo:
        res, secs, detail = results[r["target"]]
        bad += res != "RESTORED"
        log(f"{r['target']:<56}{res:<10}{int(secs):>8}  {detail}")
    log(f"\n{len(todo) - bad} restored, {bad} failed")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

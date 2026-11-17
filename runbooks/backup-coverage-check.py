#!/usr/bin/env python3
"""backup-coverage-check - compare what SHOULD be backed up with what IS.

Three audits, all derived from the live cluster (never from a hard-coded list):

  1. Longhorn  every Volume has a Completed Backup newer than the policy
               threshold (via runbooks/longhorn-backup-age.py's resolver, which
               copes with unsynced Backup CRs) and carries the recurring-job
               group that schedules backups.
  2. CIFS      every SMB PersistentVolume's data path is inside the off-site
               include list (offsite-backup-sources, decrypted IN MEMORY, never
               printed) or its StorageClass is on the exclusion list with a reason.
  3. Databases every SQL datastore workload has a db-dump-<workload> CronJob in
               its namespace, or is on the exclusion list with a reason.

Policy (exclusions + reasons): runbooks/backup-coverage-policy.yaml.

Tri-state, per docs/sops/audit-script-correctness.md: a probe that could not
measure is reported as NOT MEASURED (own finding), never as a pass. Every audit
checks its denominator and the matcher is proven by a built-in negative control
(a synthetic path that must NOT be covered) so a silent zero cannot read green.

Findings go to the sweep board (section "infra", producer "backup-assurance")
when SWEEP_PG_DSN is set; otherwise the result is printed only.

Usage:
    python3 runbooks/backup-coverage-check.py                 # print + write findings
    python3 runbooks/backup-coverage-check.py --no-write
    python3 runbooks/backup-coverage-check.py --policy /path/empty.yaml --no-write   # negative test
Exit: 0 clean, 1 findings, 2 could not measure.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()
REPO_ROOT = SCRIPT_DIR.parent
SOURCES_SECRET = REPO_ROOT / "kubernetes/apps/backup/offsite-backup/secrets/secret-sources.sops.yaml"
DEFAULT_POLICY = SCRIPT_DIR / "backup-coverage-policy.yaml"

SQL_FAMILY = ("postgres", "pgvector", "vectorchord", "vchord", "mariadb", "mysql", "percona")
OTHER_DATASTORES = ("influxdb", "memgraph-mage", "mongo", "timescale", "clickhouse")


def _activate_mise() -> None:
    if os.environ.get("_MISE_ACTIVATED"):
        return
    if not (REPO_ROOT / ".mise.toml").is_file():
        return
    mise = next((os.path.join(p, "mise") for p in os.environ.get("PATH", "").split(os.pathsep)
                 if os.path.isfile(os.path.join(p, "mise"))), None)
    if not mise:
        return
    os.environ["_MISE_ACTIVATED"] = "1"
    os.execvp(mise, [mise, "-C", str(REPO_ROOT), "exec", "--", sys.executable, *sys.argv])


class NotMeasured(Exception):
    pass


def kubectl_json(*args: str) -> dict:
    p = subprocess.run(["kubectl", *args, "-o", "json"], capture_output=True, text=True, timeout=120)
    if p.returncode != 0:
        raise NotMeasured(f"kubectl {' '.join(args)}: {p.stderr.strip()[:160]}")
    return json.loads(p.stdout)


def load_yaml(path: Path) -> dict:
    import yaml
    with open(path) as fh:
        return yaml.safe_load(fh) or {}


def decrypt_sources() -> dict:
    p = subprocess.run(["sops", "-d", "--output-type", "json", str(SOURCES_SECRET)],
                       capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        raise NotMeasured("sops could not decrypt the off-site sources secret")
    d = json.loads(p.stdout)
    return d.get("stringData") or d.get("data") or {}


# ---------------------------------------------------------------- CIFS ----------

def norm(path: str) -> str:
    parts = [x for x in path.replace("\\", "/").split("/") if x not in ("", ".")]
    if ".." in parts:
        raise NotMeasured("path with .. in a source definition")
    return "/".join(parts).lower()


def include_paths(src: dict) -> set[str]:
    """Absolute share-relative include paths (share/sub/rel), normalised."""
    out: set[str] = set()
    for tier_key in ("FILES_CORE", "FILES_APPS"):
        for line in (src.get(tier_key) or "").splitlines():
            line = line.strip()
            if not line.startswith("/src/"):
                continue
            rest = line[len("/src/"):]
            n, _, rel = rest.partition("/")
            base = src.get(f"OFFSITE_SRC_{n}")
            if not base:
                raise NotMeasured(f"include list references mount {n} with no source definition")
            out.add(norm(f"{base}/{rel}"))
    return out


def pv_path(pv: dict) -> str | None:
    csi = pv["spec"].get("csi") or {}
    if csi.get("driver") != "smb.csi.k8s.io":
        return None
    va = csi.get("volumeAttributes") or {}
    source = va.get("source", "")
    # //host/share -> share
    share = source.lstrip("/").partition("/")[2]
    sub = va.get("subDir") or va.get("subdir") or ""
    return norm(f"{share}/{sub}")


def covered(path: str, includes: set[str]) -> str:
    """'full' (path inside an include), 'partial' (an include inside path), or 'no'."""
    for inc in includes:
        if path == inc or path.startswith(inc + "/"):
            return "full"
    for inc in includes:
        if inc.startswith(path + "/") or path == "":
            return "partial"
    return "no"


def audit_cifs(policy: dict) -> tuple[list[dict], list[str]]:
    findings: list[dict] = []
    notes: list[str] = []
    includes = include_paths(decrypt_sources())
    if not includes:
        raise NotMeasured("off-site include list is empty")
    # NEGATIVE CONTROL: a path that cannot be in any include list must not match.
    if covered("zz-control-nonexistent-share/zz", includes) != "no":
        raise NotMeasured("coverage matcher control failed: a bogus path reads as covered")
    pvs = kubectl_json("get", "pv")["items"]
    smb = [(pv, pv_path(pv)) for pv in pvs]
    smb = [(pv, p) for pv, p in smb if p is not None and pv["spec"].get("storageClassName") != "offsite-backup-src"]
    if not smb:
        raise NotMeasured("zero SMB PersistentVolumes found: refusing to judge on an empty denominator")
    excl = {e["storageclass"]: e.get("reason", "") for e in (policy.get("cifs") or {}).get("excluded") or []}
    seen_classes: set[str] = set()
    uncovered: dict[str, list[str]] = {}
    partial: set[str] = set()
    for pv, p in smb:
        sc = pv["spec"].get("storageClassName", "?")
        seen_classes.add(sc)
        c = covered(p, includes)
        if c == "partial":
            partial.add(sc)
        # Partial coverage (an include INSIDE the PV's tree, e.g. curated
        # sub-folders of a bulk media share) does not make the PV's data
        # covered: it still needs a documented exclusion.
        if c != "full" and sc not in excl:
            uncovered.setdefault(sc, []).append(pv["metadata"]["name"])
        if c == "full" and sc in excl:
            findings.append({
                "sev": "warning", "sub": "cifs",
                "title": f"Backup coverage: `{sc}` is listed as excluded but its path IS in the off-site include list",
                "action": "Remove the stale entry from runbooks/backup-coverage-policy.yaml (cifs.excluded).",
            })
    for sc, names in sorted(uncovered.items()):
        findings.append({
            "sev": "warning", "sub": "cifs",
            "title": f"Backup coverage: SMB StorageClass `{sc}` is not in the off-site include list and not on the exclusion list",
            "action": (f"{len(names)} PV(s) of class {sc} hold data that is neither backed up off-site nor a documented "
                       "exclusion. Either add the path to the off-site include list (offsite-backup-sources, SOPS) or add "
                       "the class to runbooks/backup-coverage-policy.yaml cifs.excluded with a reason."),
        })
    for sc in sorted(set(excl) - seen_classes):
        findings.append({
            "sev": "warning", "sub": "cifs",
            "title": f"Backup coverage: exclusion for `{sc}` matches no PersistentVolume (stale entry)",
            "action": "Remove it from runbooks/backup-coverage-policy.yaml cifs.excluded.",
        })
    notes.append(f"cifs: {len(smb)} PVs in {len(seen_classes)} classes, {len(includes)} include paths, "
                 f"{len(excl)} excluded classes, {len(partial)} class(es) partially covered")
    return findings, notes


# ------------------------------------------------------------- Longhorn ---------

def _load_age_module():
    spec = importlib.util.spec_from_file_location("lh_age", SCRIPT_DIR / "longhorn-backup-age.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def audit_longhorn(policy: dict) -> tuple[list[dict], list[str]]:
    findings: list[dict] = []
    lh = _load_age_module()
    conf = policy.get("longhorn") or {}
    max_att = float(conf.get("max_age_hours_attached", 26))
    max_det = float(conf.get("max_age_hours_detached", 192))
    excl = {e["volume"]: e.get("reason", "") for e in conf.get("excluded") or []}
    vols = kubectl_json("-n", "storage", "get", "volumes.longhorn.io")["items"]
    backups = kubectl_json("-n", "storage", "get", "backups.longhorn.io")["items"]
    bvs = kubectl_json("-n", "storage", "get", "backupvolumes.longhorn.io")["items"]
    if not vols:
        raise NotMeasured("zero Longhorn volumes listed")
    if not backups:
        raise NotMeasured("zero Backup CRs listed: refusing to judge on an empty denominator")
    now = datetime.now(timezone.utc)
    seen: set[str] = set()
    bad = fresh = 0
    for v in vols:
        name = v["metadata"]["name"]
        seen.add(name)
        if name in excl:
            continue
        labels = v["metadata"].get("labels") or {}
        in_group = any(k.startswith("recurring-job-group.longhorn.io/") or k.startswith("recurring-job.longhorn.io/")
                       for k in labels)
        # Volume object may also be scheduled by a StorageClass/default group; the
        # age check below is the ground truth, the label check catches unscheduled ones.
        r = lh.resolve(name, v, backups, bvs, now)
        detached = (v.get("status") or {}).get("state") == "detached"
        limit = max_det if detached else max_att
        age = r["age_h"]
        if age is None:
            bad += 1
            findings.append({"sev": "critical", "sub": "longhorn",
                             "title": f"Backup coverage: Longhorn volume `{name}` has NO confirmed backup",
                             "action": "Check the recurring-job group of the volume; add it to the default group or list it in runbooks/backup-coverage-policy.yaml longhorn.excluded with a reason."})
        elif age >= limit:
            bad += 1
            findings.append({"sev": "warning", "sub": "longhorn",
                             "title": f"Backup coverage: Longhorn volume `{name}` newest backup is older than {limit:.0f}h ({'detached' if detached else 'attached'})",
                             "action": f"Newest confirmed backup {age:.1f}h old. If the volume is orphaned, retire it; otherwise investigate the recurring job.",
                             })
        else:
            fresh += 1
        if not in_group:
            findings.append({"sev": "warning", "sub": "longhorn",
                             "title": f"Backup coverage: Longhorn volume `{name}` has no recurring-job label",
                             "action": "Without a recurring-job (group) label the nightly backup does not schedule it."})
    for name in sorted(set(excl) - seen):
        findings.append({"sev": "warning", "sub": "longhorn",
                         "title": f"Backup coverage: Longhorn exclusion `{name}` matches no volume (stale entry)",
                         "action": "Remove it from runbooks/backup-coverage-policy.yaml longhorn.excluded."})
    return findings, [f"longhorn: {len(vols)} volumes, {fresh} fresh, {bad} stale/none, {len(excl)} excluded"]


# ------------------------------------------------------------ databases ---------

def audit_databases(policy: dict) -> tuple[list[dict], list[str]]:
    findings: list[dict] = []
    cronjobs = kubectl_json("get", "cronjob", "-A")["items"]
    dumps = {(c["metadata"]["namespace"], c["metadata"]["name"]) for c in cronjobs
             if c["metadata"]["name"].startswith("db-dump-")}
    workloads = kubectl_json("get", "statefulset,deployment", "-A")["items"]
    excl = {e["workload"]: e.get("reason", "") for e in (policy.get("databases") or {}).get("excluded") or []}
    sql, other = [], []
    for w in workloads:
        ns, name = w["metadata"]["namespace"], w["metadata"]["name"]
        if name.startswith("db-dump-"):
            continue
        # Main containers only: init/sidecar containers (wait-for-db, clients)
        # do not make a workload a datastore.
        main_images = [c["image"].lower() for c in w["spec"]["template"]["spec"].get("containers", [])]
        # Only the FIRST container decides: a client sidecar is not a datastore.
        img = main_images[0] if main_images else ""
        base = img.rsplit("/", 1)[-1]
        if any(f in base for f in SQL_FAMILY) and "exporter" not in base and "pgadmin" not in base:
            sql.append((ns, name))
        elif any(f in base for f in OTHER_DATASTORES):
            other.append((ns, name))
    if not sql:
        raise NotMeasured("zero SQL datastore workloads detected: the image matcher is blind, refusing to report clean")
    if not dumps:
        raise NotMeasured("zero db-dump CronJobs found")
    missing = 0
    for ns, name in sorted(sql + other):
        key = f"{ns}/{name}"
        if key in excl:
            continue
        if (ns, f"db-dump-{name}") in dumps:
            continue
        # Datastore without a dump CronJob.
        if (ns, name) in other:
            reason = "non-SQL datastore: add a policy exclusion (with reason) or a backup job"
        else:
            reason = "no db-dump CronJob in its namespace"
        missing += 1
        findings.append({"sev": "warning", "sub": "databases",
                         "title": f"Backup coverage: datastore `{key}` has no db-dump CronJob and no exclusion",
                         "action": f"{reason}. Add db-dump-{name} under kubernetes/apps/backup/db-dumps/ (docs/sops/backup.md, Adding an instance) "
                                   "or list it in runbooks/backup-coverage-policy.yaml databases.excluded with a reason."})
    known = {f"{n}/{m}" for n, m in sql + other}
    for key in sorted(set(excl) - known):
        findings.append({"sev": "warning", "sub": "databases",
                         "title": f"Backup coverage: database exclusion `{key}` matches no workload (stale entry)",
                         "action": "Remove it from runbooks/backup-coverage-policy.yaml databases.excluded."})
    # Reverse direction: a dump CronJob whose instance no longer exists.
    live = {(n, f"db-dump-{m}") for n, m in sql}
    for ns, cj in sorted(dumps - live):
        findings.append({"sev": "warning", "sub": "databases",
                         "title": f"Backup coverage: CronJob `{ns}/{cj}` dumps an instance that no longer exists",
                         "action": "Remove the CronJob (and retire its NAS directory), or the instance detector missed it."})
    return findings, [f"databases: {len(sql)} SQL + {len(other)} other datastores, {len(dumps)} db-dump CronJobs, {missing} missing"]


# ------------------------------------------------------------ fire drills --------

def audit_drills(policy: dict) -> tuple[list[dict], list[str]]:
    """Fire-drill ledger: last full drill and credential-row verification dates."""
    from datetime import date
    ledger_path = SCRIPT_DIR / "backup-fire-drill-ledger.yaml"
    if not ledger_path.is_file():
        raise NotMeasured("runbooks/backup-fire-drill-ledger.yaml is missing")
    led = load_yaml(ledger_path)
    if "credential_rows" not in led or "last_full_drill" not in led:
        raise NotMeasured("ledger lacks last_full_drill / credential_rows keys")
    today = date.today()
    findings: list[dict] = []

    def age(d) -> int | None:
        if d is None:
            return None
        if isinstance(d, str):
            d = date.fromisoformat(d)
        return (today - d).days

    max_drill = int(led.get("max_drill_age_days", 100))
    a = age(led["last_full_drill"])
    if a is None:
        findings.append({"sev": "warning", "sub": "fire-drill",
                         "title": "Backup fire drill: no full drill has ever been recorded",
                         "action": "Run the quarterly drill (docs/sops/total-loss-recovery.md section 15.2) and record it in runbooks/backup-fire-drill-ledger.yaml."})
    elif a > max_drill:
        findings.append({"sev": "warning", "sub": "fire-drill",
                         "title": f"Backup fire drill: last full drill is older than {max_drill} days",
                         "action": f"Last full drill {a} days ago. Run section 15.2 of docs/sops/total-loss-recovery.md and update the ledger."})
    max_ver = int(led.get("max_verification_age_days", 365))
    stale = [r for r, d in sorted(led["credential_rows"].items())
             if (age(d) is None) or age(d) > max_ver]
    if stale:
        findings.append({"sev": "warning", "sub": "fire-drill",
                         "title": "Backup fire drill: credential-inventory rows are unverified or older than 365 days",
                         "action": f"Section 3.1 row(s) {', '.join(str(r) for r in stale)} have no verification date within {max_ver} days. "
                                   "Confirm them at the quarterly drill and write the date into runbooks/backup-fire-drill-ledger.yaml."})
    return findings, [f"fire-drill: last full drill {led['last_full_drill'] or 'never'}, "
                      f"{len(led['credential_rows'])} tracked credential rows, {len(stale)} unverified/stale"]


# ---------------------------------------------------------------- main ----------

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--policy", default=str(DEFAULT_POLICY))
    ap.add_argument("--no-write", action="store_true")
    ap.add_argument("--postgres-dsn", default=os.environ.get("SWEEP_PG_DSN"))
    a = ap.parse_args(argv)
    policy = load_yaml(Path(a.policy))
    all_findings: list[dict] = []
    not_measured: list[str] = []
    for label, fn in (("longhorn", audit_longhorn), ("cifs", audit_cifs), ("databases", audit_databases), ("drills", audit_drills)):
        try:
            f, notes = fn(policy)
            all_findings += f
            for n in notes:
                print(f"  {n}")
        except NotMeasured as e:
            not_measured.append(f"{label}: {e}")
            print(f"  {label}: NOT MEASURED ({e})")
        except Exception as e:  # noqa: BLE001 - any crash is not-measured, never a pass
            not_measured.append(f"{label}: {type(e).__name__}: {e}")
            print(f"  {label}: NOT MEASURED ({type(e).__name__}: {e})")
    for f in all_findings:
        print(f"  [{f['sev']}] {f['title']}")
    write = not a.no_write and a.postgres_dsn
    if write:
        sys.path.insert(0, str(SCRIPT_DIR))
        from lib.findings_writer import FindingsWriter, cycle_id_from_env, trigger_from_env, git_head
        fw = FindingsWriter(dsn=a.postgres_dsn, section="infra", producer="backup-assurance",
                            cycle_id=cycle_id_from_env(), trigger=trigger_from_env(), git_head=git_head())
        try:
            for f in all_findings:
                fw.emit(f["sev"], f["title"], action=f["action"], subsection=f["sub"])
            for nm in not_measured:
                label = nm.split(":", 1)[0]
                fw.emit("warning", f"Backup coverage check could not measure `{label}` (undetermined, not a pass)",
                        action=nm, subsection="not-measured")
            if not_measured:
                fw.mark_incomplete("backup-coverage-check: " + "; ".join(not_measured)[:300])
        finally:
            fw.close(verdict="red" if not_measured else ("yellow" if all_findings else "green"))
    elif not a.no_write:
        print("  (no SWEEP_PG_DSN: findings printed only)")
    print(f"result: {len(all_findings)} finding(s), {len(not_measured)} not measured")
    if not_measured:
        return 2
    return 1 if all_findings else 0


if __name__ == "__main__":
    _activate_mise()
    sys.exit(main())

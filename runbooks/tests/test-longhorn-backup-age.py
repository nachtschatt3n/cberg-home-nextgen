#!/usr/bin/env python3
"""Regression: backup-age gates must see a Completed backup whose Backup CR
status never synced (F-a915dd47).

On 2026-09-26 the nightly RecurringJob's Backup CR for authentik-pg-data was
`Completed` but had `status.volumeName=''` / `backupCreatedAt=''` /
`lastSyncedAt=null`. Every gate filtering Backup CRs on `status.volumeName` fell
back to the previous night's backup (26h+) and one pre-check aborted a window
on a volume that HAD been backed up that morning. Reproduced live again
2026-09-28 on prometheus-tsdb (old filter: 26.6h; this helper: 2.6h).

Also guarded: the fallback must be CROSS-CHECKED. A Volume.status.lastBackup
that neither the BackupVolume nor any Completed Backup CR corroborates is
reported but never counted, so the fix cannot become a new false PASS.

Run: python3 runbooks/tests/test-longhorn-backup-age.py
"""
import datetime as dt
import importlib.util
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("lba", ROOT / "runbooks/longhorn-backup-age.py")
lba = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lba)

NOW = dt.datetime(2026, 9, 28, 6, 0, tzinfo=dt.timezone.utc)


def ago(h):
    return (NOW - dt.timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M:%SZ")


def cr(name, vol, h, synced=True, state="Completed"):
    st = {"state": state, "snapshotCreatedAt": ago(h) if synced else ""}
    if synced:
        st.update(volumeName=vol, backupCreatedAt=ago(h))
    else:
        st.update(volumeName="", backupCreatedAt="", lastSyncedAt=None)
    return {"metadata": {"name": name, "labels": {"backup-volume": vol},
                         "creationTimestamp": ago(h)}, "status": st}


def vol(name, last=None, h=None):
    st = {"state": "attached"}
    if last:
        st.update(lastBackup=last, lastBackupAt=ago(h))
    return {"metadata": {"name": name}, "status": st}


def bv(volname, last, h):
    return {"metadata": {"name": f"{volname}-abc", "labels": {"backup-volume": volname}},
            "spec": {"volumeName": volname},
            "status": {"lastBackupName": last, "lastBackupAt": ago(h)}}


fails = []


def check(label, cond):
    print(("ok   " if cond else "FAIL ") + label)
    if not cond:
        fails.append(label)


# 1. THE INCIDENT: today's CR unsynced, yesterday's synced. Must read today.
backups = [cr("b-old", "authentik-pg-data", 26.9), cr("b-new", "authentik-pg-data", 2.9, synced=False)]
r = lba.resolve("authentik-pg-data", vol("authentik-pg-data", "b-new", 2.9), backups,
                [bv("authentik-pg-data", "b-new", 2.9)], NOW)
check("unsynced nightly CR is seen (age < 26h)", r["age_h"] is not None and r["age_h"] < 26)
check("unsynced nightly CR -> FRESH", lba.verdict(r, 26) == "FRESH")
check("resolved backup is today's", r["backup"] == "b-new")

# 1b. Control: the OLD status.volumeName filter on the same fixture reads 26.9h.
old = [b for b in backups if b["status"].get("volumeName") == "authentik-pg-data"]
check("control: old status.volumeName filter misses it", len(old) == 1 and old[0]["metadata"]["name"] == "b-old")

# 2. Label ALSO missing (worst case) -> Volume.lastBackup cross-checked by BackupVolume.
b2 = cr("b-new", "x", 3, synced=False)
b2["metadata"]["labels"] = {}
r = lba.resolve("x", vol("x", "b-new", 3), [cr("b-old", "x", 27), b2], [bv("x", "b-new", 3)], NOW)
check("no label: volume+bv fallback -> FRESH", lba.verdict(r, 26) == "FRESH" and r["source"] in ("volume+bv", "backupvolume"))

# 3. Uncorroborated Volume.lastBackup must NOT pass the gate.
r = lba.resolve("y", vol("y", "b-ghost", 1), [cr("b-old", "y", 30)], [bv("y", "b-old", 30)], NOW)
check("uncorroborated lastBackup is not counted -> STALE", lba.verdict(r, 26) == "STALE")
check("uncorroborated lastBackup is REPORTED", any("b-ghost" in u for u in r["unconfirmed"]))

# 4. Non-Completed CRs never count.
r = lba.resolve("z", vol("z"), [cr("b-err", "z", 1, state="Error"), cr("b-ok", "z", 40)], [], NOW)
check("Error CR ignored -> STALE at 40h", lba.verdict(r, 26) == "STALE" and r["backup"] == "b-ok")

# 5. No evidence at all -> NONE (not FRESH, not a crash).
r = lba.resolve("n", vol("n"), [cr("b", "other", 1)], [], NOW)
check("no evidence -> NONE", lba.verdict(r, 26) == "NONE")

# 6. A synced CR for ANOTHER volume carrying a stale/mismatched label must not leak.
leak = cr("b-leak", "other", 1)
leak["metadata"]["labels"]["backup-volume"] = "w"
r = lba.resolve("w", vol("w"), [leak, cr("b-w", "w", 30)], [], NOW)
check("synced CR of another volume is not borrowed via label", r["backup"] == "b-w")

# 7. lastBackupAt lag (the OTHER direction): Volume says yesterday, CR says today.
r = lba.resolve("l", vol("l", "b-y", 27), [cr("b-y", "l", 27), cr("b-t", "l", 3)], [bv("l", "b-y", 27)], NOW)
check("lastBackupAt lag: freshest confirmed CR wins", r["backup"] == "b-t" and lba.verdict(r, 26) == "FRESH")

# 8. Source guards: plans with a status.volumeName FRESHNESS gate must use the helper.
src = (ROOT / "runbooks/longhorn-backup-age.py").read_text()
check("helper fails closed on empty Backup CR list", "empty denominator" in src)
# Freshness gates that key Backup CRs on status.volumeName: the jsonpath
# range/awk form and the inline-python form. (Existence-only premises using
# `?(@.status.volumeName==...)` are allowed: an older synced CR proves existence.)
FRESHNESS_BY_STATUS_VOLUMENAME = re.compile(
    r"\{\.status\.volumeName\}\{\" \"\}|get\(['\"]volumeName['\"]\)\s*==")
for p in sorted((ROOT / "runbooks/maintenance/plans").glob("*.md")):
    t = p.read_text()
    if re.search(r"^status:\s*(executed|superseded|abandoned|declined)", t, re.M):
        continue
    check(f"{p.name}: no inline status.volumeName freshness gate",
          not FRESHNESS_BY_STATUS_VOLUMENAME.search(t))

if fails:
    print(f"\n{len(fails)} FAILED")
    raise SystemExit(1)
print("\nall passed")

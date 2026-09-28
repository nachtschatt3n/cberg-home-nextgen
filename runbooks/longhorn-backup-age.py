#!/usr/bin/env python3
"""Shared backup-age gate: how old is the newest CONFIRMED backup of a Longhorn volume?

Use this in every plan premise / pre-check / backup_gate instead of an inline
`jsonpath='{.items[?(@.status.volumeName=="<vol>")]...}'` filter.

Why (F-a915dd47, 2026-09-26): the nightly RecurringJob's Backup CRs can stay
`state: Completed` with an UNSYNCED status -- `status.volumeName`,
`status.backupCreatedAt` empty and `status.lastSyncedAt` null -- for hours. A
gate that filters Backup CRs on `status.volumeName` then silently falls back to
the PREVIOUS night's backup and reads ~26h: one plan premise false-negatived and
one pre-check ABORTED a window on a volume that had in fact been backed up that
morning. The opposite lag also exists: `Volume.status.lastBackupAt` can keep the
previous timestamp for a cycle (docs/sops/backup.md "lastBackupAt Can Lag"). So
no single field is trustworthy; this helper takes the freshest CONFIRMED signal:

  1. backup-cr        Completed Backup CR whose status.volumeName == volume
  2. backup-cr-label  Completed Backup CR matched by its `backup-volume` LABEL
                      (the label is set at creation, before status sync -- this
                      is what catches the unsynced nightly CR)
  3. volume+bv        Volume.status.lastBackup/lastBackupAt, ACCEPTED ONLY when
                      cross-checked: the BackupVolume for the volume names the
                      same backup as lastBackupName, or a Completed Backup CR
                      of that name exists
  4. backupvolume     BackupVolume.status.lastBackupName/lastBackupAt when that
                      named backup exists as a Completed Backup CR

An UNCONFIRMED Volume.lastBackup (no BackupVolume agreement, no CR) is reported
but never counted -- a gate must not pass on a claim nothing corroborates.

Usage:
  runbooks/longhorn-backup-age.py VOLUME [VOLUME ...] [--max-hours 26] [--json]

Output, one line per volume:
  <volume> <age>h FRESH|STALE|NONE via <source> backup=<name> at=<ts>
Exit: 0 all FRESH, 1 any STALE/NONE, 2 kubectl/lookup error (fails CLOSED).
Premise form:  run: python3 runbooks/longhorn-backup-age.py <vol> --max-hours 26
               expect_contains: " FRESH "
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys

NS = "storage"


def _parse(ts: str | None) -> dt.datetime | None:
    if not ts:
        return None
    try:
        t = dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)


def _backup_ts(b: dict) -> dt.datetime | None:
    s = b.get("status") or {}
    return (_parse(s.get("snapshotCreatedAt")) or _parse(s.get("backupCreatedAt"))
            or _parse((b.get("metadata") or {}).get("creationTimestamp")))


def _bv_volume(bv: dict) -> str | None:
    return ((bv.get("spec") or {}).get("volumeName")
            or ((bv.get("metadata") or {}).get("labels") or {}).get("backup-volume")
            or (bv.get("status") or {}).get("volumeName"))


def resolve(volume: str, vol_obj: dict | None, backups: list, backupvolumes: list,
            now: dt.datetime) -> dict:
    """Return the freshest confirmed backup evidence for `volume`.

    Keys: volume, age_h (float|None), source, backup, at, unconfirmed (list of
    notes about evidence seen but NOT counted)."""
    completed = {}
    cands = []  # (ts, source, name)
    for b in backups:
        md, st = b.get("metadata") or {}, b.get("status") or {}
        if st.get("state") != "Completed":
            continue
        name = md.get("name", "")
        completed[name] = b
        ts = _backup_ts(b)
        if ts is None:
            continue
        if st.get("volumeName") == volume:
            cands.append((ts, "backup-cr", name))
        elif not st.get("volumeName") and (md.get("labels") or {}).get("backup-volume") == volume:
            cands.append((ts, "backup-cr-label", name))

    bvs = [bv for bv in backupvolumes if _bv_volume(bv) == volume]
    bv_names = {(bv.get("status") or {}).get("lastBackupName") for bv in bvs} - {None, ""}
    unconfirmed = []

    vst = (vol_obj or {}).get("status") or {}
    lb, lba = vst.get("lastBackup"), _parse(vst.get("lastBackupAt"))
    if lb and lba:
        if lb in bv_names or lb in completed:
            cands.append((lba, "volume+bv", lb))
        else:
            unconfirmed.append(f"Volume.lastBackup={lb} not corroborated by BackupVolume/Backup CR")

    for bv in bvs:
        bst = bv.get("status") or {}
        n, t = bst.get("lastBackupName"), _parse(bst.get("lastBackupAt"))
        if n and t:
            if n in completed:
                cands.append((t, "backupvolume", n))
            else:
                unconfirmed.append(f"BackupVolume.lastBackupName={n} has no Completed Backup CR")

    if not cands:
        return {"volume": volume, "age_h": None, "source": None, "backup": None,
                "at": None, "unconfirmed": unconfirmed}
    ts, src, name = max(cands, key=lambda c: c[0])
    return {"volume": volume, "age_h": (now - ts).total_seconds() / 3600.0,
            "source": src, "backup": name,
            "at": ts.strftime("%Y-%m-%dT%H:%M:%SZ"), "unconfirmed": unconfirmed}


def verdict(r: dict, max_hours: float) -> str:
    if r["age_h"] is None:
        return "NONE"
    return "FRESH" if r["age_h"] < max_hours else "STALE"


def fmt(r: dict, max_hours: float) -> str:
    v = verdict(r, max_hours)
    if v == "NONE":
        line = f"{r['volume']} -h NONE via - backup=- at=-"
    else:
        line = (f"{r['volume']} {r['age_h']:.1f}h {v} via {r['source']} "
                f"backup={r['backup']} at={r['at']}")
    for u in r["unconfirmed"]:
        line += f"\n  note: {u} (not counted)"
    return line


def _kubectl_items(kind: str) -> list:
    p = subprocess.run(["kubectl", "-n", NS, "get", kind, "-o", "json"],
                       capture_output=True, text=True, timeout=90)
    if p.returncode != 0:
        raise RuntimeError(f"kubectl get {kind}: {p.stderr.strip()[:200]}")
    return json.loads(p.stdout).get("items", [])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("volumes", nargs="+", help="Longhorn Volume name(s)")
    ap.add_argument("--max-hours", type=float, default=26.0)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    try:
        vols = {v["metadata"]["name"]: v for v in _kubectl_items("volumes.longhorn.io")}
        backups = _kubectl_items("backups.longhorn.io")
        bvs = _kubectl_items("backupvolumes.longhorn.io")
    except Exception as e:  # fail CLOSED and loud
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    if not backups:
        print("ERROR: zero Backup CRs listed -- refusing to judge on an empty denominator",
              file=sys.stderr)
        return 2
    now = dt.datetime.now(dt.timezone.utc)
    rc = 0
    out = []
    for name in a.volumes:
        if name not in vols:
            print(f"ERROR: no Longhorn volume named {name!r}", file=sys.stderr)
            rc = 2
            continue
        r = resolve(name, vols[name], backups, bvs, now)
        r["verdict"] = verdict(r, a.max_hours)
        if r["verdict"] != "FRESH" and rc == 0:
            rc = 1
        out.append(r)
    if a.json:
        print(json.dumps(out, indent=2))
    else:
        for r in out:
            print(fmt(r, a.max_hours))
    return rc


if __name__ == "__main__":
    sys.exit(main())

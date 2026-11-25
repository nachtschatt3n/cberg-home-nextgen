#!/usr/bin/env python3
"""ha-integration-gate — did every Home Assistant integration survive the bump?

The Step 0 health gate reads POD health. A Home Assistant release can change or
remove an integration while the pod stays Ready (an integration that fails to
set up leaves 1/1 Running). This gate reads what actually matters: per
integration, the config-entry state and the availability of its entities,
captured BEFORE the change and compared AFTER it.

  ha-integration-gate.py snapshot --out FILE
  ha-integration-gate.py compare  --snapshot FILE [--settle SECONDS] [--no-reload] [--json]

READ-ONLY EXCEPT ONE ACTION: `compare` reloads a config entry that was `loaded`
in the snapshot and is not now, ONCE per entry, via
POST /api/config/config_entries/entry/<id>/reload (non-restarting). Never a core
restart. `--no-reload` makes compare strictly read-only.

WHAT COUNTS AS A REGRESSION (any one => exit 1, with a table)
  * a config entry `loaded` in the snapshot is not `loaded` now (after the one
    reload attempt);
  * an entity that was AVAILABLE in the snapshot is `unavailable` now;
  * an entity present and AVAILABLE in the snapshot no longer exists (feature
    loss: a removed entity is worse than an unavailable one).
TOLERATED (reported, never failing):
  * entities already `unavailable` BEFORE the change (orphaned registry rows,
    dead devices): they are in the snapshot's unavailable set, so they never
    count as new;
  * entities of BLE tracker integrations (policy BLE_DOMAINS) that are
    unavailable but whose config entry is `loaded`: trackers legitimately wait
    for the next advert after a restart;
  * entities that are new now.

FAIL CLOSED: no credentials, unreachable API, a snapshot with zero config
entries or zero entities (an empty denominator proves nothing), a live read with
zero entries, an unparseable template reply => exit 2 (precondition), never 0.

Credentials: HASS_URL + HASS_TOKEN from the environment, else from
/Users/mu/code/hactl/.env (the file health-check.sh sources). The token is never
printed, logged or put in an exception message.

Exit: 0 PASS · 1 REGRESSION · 2 precondition / unreadable.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HACTL_ENV = Path("/Users/mu/code/hactl/.env")
SNAPSHOT_VERSION = 1
BLE_DOMAINS = {"bluetooth", "ibeacon", "private_ble_device", "bluetooth_le_tracker",
               "ble_monitor", "bermuda"}
BAD_ENTRY_STATES = {"setup_error", "setup_retry", "migration_error", "failed_unload",
                    "not_loaded"}


class GateError(Exception):
    """Precondition failure (exit 2). Messages never contain the token."""


# ── credentials + client ─────────────────────────────────────────────────────
def load_credentials(env=None, env_file: Path = HACTL_ENV):
    env = os.environ if env is None else env
    url, tok = env.get("HASS_URL"), env.get("HASS_TOKEN")
    if (not url or not tok) and env_file.is_file():
        vals = {}
        for line in env_file.read_text(errors="ignore").splitlines():
            m = re.match(r"^\s*(?:export\s+)?([A-Z_]+)=(.*)$", line)
            if m:
                vals[m.group(1)] = m.group(2).strip().strip("'\"")
        url = url or vals.get("HASS_URL")
        tok = tok or vals.get("HASS_TOKEN")
    if not url or not tok:
        raise GateError("HASS_URL/HASS_TOKEN not available (env or hactl .env) — cannot read HA")
    return url.rstrip("/"), tok


class HA:
    def __init__(self, url, token, timeout=30):
        self.url, self._token, self.timeout = url, token, timeout

    def _req(self, method, path, body=None, raw=False):
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(
            self.url + path, data=data, method=method,
            headers={"Authorization": "Bearer " + self._token, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                txt = r.read().decode()
        except urllib.error.HTTPError as e:
            raise GateError(f"HA {method} {path} -> HTTP {e.code}") from None
        except Exception as e:   # never include the request (carries the token)
            raise GateError(f"HA {method} {path} unreachable ({type(e).__name__})") from None
        return txt if raw else (json.loads(txt) if txt.strip() else None)

    def get(self, path):
        return self._req("GET", path)

    def post(self, path, body=None):
        return self._req("POST", path, body)

    def template(self, tpl):
        return self._req("POST", "/api/template", {"template": tpl}, raw=True)


# ── reading ──────────────────────────────────────────────────────────────────
_TPL = """{% set ns = namespace(o={}) %}{% for d in domains %}{% set ids = integration_entities(d) %}\
{% set bad = ids | select('is_state','unavailable') | list %}\
{% set ns.o = dict(ns.o, **{d: {'e': ids | list, 'u': bad}}) %}{% endfor %}{{ ns.o | tojson }}"""


def read_state(ha: HA):
    """{'entries': {entry_id: {domain,title,state}}, 'domains': {domain: {'e': [...], 'u': [...]}}}"""
    entries = ha.get("/api/config/config_entries/entry")
    if not isinstance(entries, list):
        raise GateError("config entries reply is not a list")
    ent = {}
    for e in entries:
        if e.get("disabled_by"):
            continue
        ent[e["entry_id"]] = {"domain": e["domain"], "title": e.get("title", ""), "state": e.get("state")}
    domains = sorted({v["domain"] for v in ent.values()})
    tpl = "{% set domains = " + json.dumps(domains) + " %}" + _TPL
    raw = ha.template(tpl)
    try:
        dom = json.loads(raw)
    except Exception:
        raise GateError("entity template reply not JSON (template API unreadable)") from None
    if not isinstance(dom, dict):
        raise GateError("entity template reply has the wrong shape")
    return {"entries": ent, "domains": dom}


def snapshot(ha: HA):
    st = read_state(ha)
    n_ent = sum(len(v["e"]) for v in st["domains"].values())
    if not st["entries"] or n_ent == 0:
        raise GateError(f"refusing an empty snapshot ({len(st['entries'])} entries, {n_ent} entities): "
                        f"an empty denominator proves nothing")
    return {"version": SNAPSHOT_VERSION, "taken_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            **st}


# ── comparison (pure) ────────────────────────────────────────────────────────
def compare_states(before: dict, now: dict):
    """(regressions, tolerated). Each regression is (kind, integration, subject, detail)."""
    reg, tol = [], []
    for eid, b in before["entries"].items():
        if b["state"] != "loaded":
            continue                       # was not healthy before: not ours to blame
        n = now["entries"].get(eid)
        if n is None:
            reg.append(("entry-gone", b["domain"], b["title"], "config entry no longer exists"))
        elif n["state"] != "loaded":
            reg.append(("entry-state", b["domain"], b["title"], f"loaded -> {n['state']}"))
    now_loaded_domains = {v["domain"] for v in now["entries"].values() if v["state"] == "loaded"}
    for dom, b in before["domains"].items():
        n = now["domains"].get(dom, {"e": [], "u": []})
        was_bad = set(b["u"])
        was_ok = set(b["e"]) - was_bad
        now_all, now_bad = set(n["e"]), set(n["u"])
        for ent in sorted(was_ok - now_all):
            reg.append(("entity-gone", dom, ent, "available before, no longer exists (feature loss)"))
        for ent in sorted((was_ok & now_all) & now_bad):
            if dom in BLE_DOMAINS and dom in now_loaded_domains:
                tol.append(("ble-awaiting-advert", dom, ent, "unavailable; BLE tracker, entry loaded"))
            else:
                reg.append(("entity-unavailable", dom, ent, "available before, unavailable now"))
        for ent in sorted(was_bad & now_bad):
            tol.append(("already-unavailable", dom, ent, "unavailable BEFORE the change"))
    return reg, tol


def _table(rows, title):
    if not rows:
        return f"{title}: none"
    w = max(len(r[1]) for r in rows)
    out = [f"{title}: {len(rows)}", f"  {'KIND':<20} {'INTEGRATION':<{w}}  SUBJECT / DETAIL"]
    for k, d, s, det in rows[:80]:
        out.append(f"  {k:<20} {d:<{w}}  {s} — {det}")
    if len(rows) > 80:
        out.append(f"  ... {len(rows) - 80} more")
    return "\n".join(out)


def compare(ha: HA, before: dict, settle=120, reload=True, interval=10, sleep=time.sleep,
            now_fn=time.monotonic):
    """Poll until clean or `settle` seconds pass; reload failed entries ONCE.
    Returns (exit_code, report dict)."""
    if before.get("version") != SNAPSHOT_VERSION:
        raise GateError("snapshot version mismatch")
    if not before.get("entries") or not any(v["e"] for v in before.get("domains", {}).values()):
        raise GateError("snapshot is empty — refusing to compare against nothing")
    deadline = now_fn() + settle
    reloaded: dict = {}
    last_err, now = None, None
    while True:
        try:
            now = read_state(ha)
            last_err = None
        except GateError as e:                      # HA restarting: keep polling
            last_err = str(e)
        if now is not None and last_err is None:
            if not now["entries"]:
                raise GateError("live read returned zero config entries — refusing to pass")
            reg, tol = compare_states(before, now)
            bad_entries = [r for r in reg if r[0] in ("entry-state", "entry-gone")]
            if not reg:
                break
            if reload and bad_entries and now_fn() < deadline + interval:
                ids = [eid for eid, b in before["entries"].items()
                       if b["state"] == "loaded" and eid in now["entries"]
                       and now["entries"][eid]["state"] != "loaded" and eid not in reloaded]
                for eid in ids:
                    try:
                        ha.post(f"/api/config/config_entries/entry/{eid}/reload")
                        reloaded[eid] = "reload requested"
                    except GateError as e:
                        reloaded[eid] = str(e)
                if ids:
                    sleep(min(interval, max(0, deadline - now_fn())) or 1)
                    continue
            if now_fn() >= deadline:
                break
        elif now_fn() >= deadline:
            raise GateError(f"HA API unreadable for {settle}s after the change: {last_err}")
        sleep(interval)
    report = {"regressions": reg, "tolerated_count": len(tol),
              "tolerated": tol[:40], "reloaded": reloaded,
              "entries_now": len(now["entries"]),
              "entities_now": sum(len(v["e"]) for v in now["domains"].values())}
    return (1 if reg else 0), report


# ── cli ──────────────────────────────────────────────────────────────────────
def main(argv=None, ha=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("snapshot")
    s.add_argument("--out", required=True)
    c = sub.add_parser("compare")
    c.add_argument("--snapshot", required=True)
    c.add_argument("--settle", type=int, default=120)
    c.add_argument("--no-reload", action="store_true")
    c.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    try:
        if ha is None:
            url, tok = load_credentials()
            ha = HA(url, tok)
        if args.cmd == "snapshot":
            snap = snapshot(ha)
            Path(args.out).write_text(json.dumps(snap))
            os.chmod(args.out, 0o600)
            print(f"snapshot: {len(snap['entries'])} config entries, "
                  f"{sum(len(v['e']) for v in snap['domains'].values())} entities, "
                  f"{sum(len(v['u']) for v in snap['domains'].values())} already unavailable -> {args.out}")
            return 0
        p = Path(args.snapshot)
        if not p.is_file():
            raise GateError(f"snapshot file missing: {p}")
        before = json.loads(p.read_text())
        rc, rep = compare(ha, before, settle=args.settle, reload=not args.no_reload)
    except GateError as e:
        print(f"HA-INTEGRATION-GATE: PRECONDITION FAILED — {e}", file=sys.stderr)
        return 2
    except (OSError, ValueError) as e:
        print(f"HA-INTEGRATION-GATE: PRECONDITION FAILED — {type(e).__name__}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(rep, default=list))
    print(_table(rep["regressions"], "REGRESSIONS"))
    print(f"tolerated (pre-existing unavailable / BLE awaiting advert): {rep['tolerated_count']}")
    if rep["reloaded"]:
        print(f"config entries reloaded once: {len(rep['reloaded'])}")
    print(f"HA-INTEGRATION-GATE: {'PASS' if rc == 0 else 'FAIL'} "
          f"({rep['entries_now']} entries, {rep['entities_now']} entities read)")
    return rc


if __name__ == "__main__":
    sys.exit(main())

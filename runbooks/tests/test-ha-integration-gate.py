"""ha-integration-gate: must PASS on a clean bump and FAIL (exit 1 / 2) on every
regression class, with the tolerance classes honoured. Hermetic: a fake HA.

Run: python3 runbooks/tests/test-ha-integration-gate.py
"""
from __future__ import annotations
import copy, importlib.util, io, json, os, sys, tempfile
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("hag", REPO / "runbooks/lib/ha-integration-gate.py")
hag = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hag)

FAILS = []
def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  {str(detail)[:300]}"))
    if not ok: FAILS.append(name)

SECRET = "SUPER-SECRET-TOKEN-VALUE-123"

def state(entries, domains):
    return {"entries": entries, "domains": domains}

BASE = state(
    {"e1": {"domain": "hue", "title": "Hue", "state": "loaded"},
     "e2": {"domain": "bluetooth", "title": "BT", "state": "loaded"},
     "e3": {"domain": "zha", "title": "ZHA", "state": "not_loaded"}},
    {"hue": {"e": ["light.a", "light.b", "light.dead"], "u": ["light.dead"]},
     "bluetooth": {"e": ["device_tracker.phone"], "u": []},
     "zha": {"e": [], "u": []}})
BASE["version"] = hag.SNAPSHOT_VERSION

class FakeHA(hag.HA):
    """Serves successive states; a reload flips an entry to loaded when `reload_fixes`."""
    def __init__(self, states, reload_fixes=False, fail_reads=0):
        self.states = states; self.i = 0; self.reload_fixes = reload_fixes
        self.reloads = []; self.fail_reads = fail_reads; self._token = SECRET; self.url = "http://x"
    def cur(self):
        return self.states[min(self.i, len(self.states) - 1)]
    def get(self, path):
        if self.fail_reads > 0:
            self.fail_reads -= 1
            raise hag.GateError("HA GET unreachable (URLError)")
        st = self.cur(); self.i += 1
        return [{"entry_id": k, "domain": v["domain"], "title": v["title"], "state": v["state"], "disabled_by": None}
                for k, v in st["entries"].items()]
    def template(self, tpl):
        return json.dumps(self.cur()["domains"])
    def post(self, path, body=None):
        self.reloads.append(path)
        if self.reload_fixes:
            for s in self.states:
                for v in s["entries"].values():
                    if v["state"] in hag.BAD_ENTRY_STATES:
                        v["state"] = "loaded"

def run(now_states, **kw):
    ha = FakeHA([copy.deepcopy(s) for s in now_states], reload_fixes=kw.pop("reload_fixes", False),
                fail_reads=kw.pop("fail_reads", 0))
    t = [0.0]
    def clock(): return t[0]
    def sleep(s): t[0] += max(s, 1)
    try:
        rc, rep = hag.compare(ha, copy.deepcopy(BASE), sleep=sleep, now_fn=clock, **kw)
    except hag.GateError as e:
        return 2, str(e), ha
    return rc, rep, ha

kw = dict(settle=30, interval=5)
rc, rep, ha = run([BASE], **kw)
check("identical state => PASS, nothing reloaded", rc == 0 and not ha.reloads, rep)
check("pre-existing unavailable entity is tolerated (not a regression)",
      rc == 0 and rep["tolerated_count"] >= 1, rep)

bad = copy.deepcopy(BASE); bad["entries"]["e1"]["state"] = "setup_error"
rc, rep, ha = run([bad], reload=False, **kw)
check("entry loaded -> setup_error => FAIL (exit 1)", rc == 1 and rep["regressions"][0][0] == "entry-state", rep)
check("--no-reload never POSTs", ha.reloads == [])
rc, rep, ha = run([bad], reload=True, **kw)
check("unfixed entry is reloaded EXACTLY once, then FAIL", rc == 1 and len(ha.reloads) == 1, (rc, ha.reloads))
rc, rep, ha = run([bad, bad], reload=True, reload_fixes=True, **kw)
check("entry fixed by the one reload => PASS", rc == 0 and len(ha.reloads) == 1, (rc, rep, ha.reloads))
check("reload endpoint is the non-restarting entry reload",
      ha.reloads and ha.reloads[0] == "/api/config/config_entries/entry/e1/reload", ha.reloads)

new_un = copy.deepcopy(BASE); new_un["domains"]["hue"]["u"] = ["light.dead", "light.a"]
rc, rep, _ = run([new_un], **kw)
check("a NEW unavailable entity => FAIL", rc == 1 and rep["regressions"][0][:3] == ("entity-unavailable", "hue", "light.a"), rep)

gone = copy.deepcopy(BASE); gone["domains"]["hue"]["e"] = ["light.a", "light.dead"]
rc, rep, _ = run([gone], **kw)
check("an available entity that DISAPPEARED => FAIL (feature loss)", rc == 1 and rep["regressions"][0][0] == "entity-gone", rep)

ble = copy.deepcopy(BASE); ble["domains"]["bluetooth"]["u"] = ["device_tracker.phone"]
rc, rep, _ = run([ble], **kw)
check("BLE tracker awaiting advert (entry loaded) is tolerated", rc == 0, rep)
ble2 = copy.deepcopy(ble); ble2["entries"]["e2"]["state"] = "setup_error"
rc, rep, _ = run([ble2], reload=False, **kw)
check("...but not when the BLE entry itself failed", rc == 1, rep)

added = copy.deepcopy(BASE); added["domains"]["hue"]["e"].append("light.new")
rc, rep, _ = run([added], **kw)
check("a NEW entity is fine", rc == 0, rep)

# the gate recovers from a restart window, and gives up honestly
rc, rep, _ = run([BASE], fail_reads=2, **kw)
check("API down for 2 reads during the restart, then clean => PASS", rc == 0, rep)
rc, rep, _ = run([BASE], fail_reads=99, **kw)
check("API never comes back => exit 2 (precondition), NOT pass", rc == 2, rep)
pending = copy.deepcopy(BASE); pending["entries"]["e1"]["state"] = "setup_in_progress"
good = copy.deepcopy(BASE)
rc, rep, _ = run([pending, good], reload=False, **kw)
check("a transient state that settles inside the window => PASS", rc == 0, rep)

# empty denominators
empty = state({}, {}); empty["version"] = hag.SNAPSHOT_VERSION
try:
    hag.compare(FakeHA([BASE]), empty); check("empty snapshot refused", False)
except hag.GateError:
    check("empty snapshot is refused (empty denominator)", True)
try:
    hag.snapshot(FakeHA([state({"x": {"domain": "d", "title": "", "state": "loaded"}}, {"d": {"e": [], "u": []}})]))
    check("snapshot with zero entities refused", False)
except hag.GateError:
    check("snapshot with zero entities is refused", True)
try:
    hag.compare(FakeHA([state({}, {})]), copy.deepcopy(BASE), settle=0, interval=1,
                sleep=lambda s: None, now_fn=lambda: 0)
    check("zero live entries refused", False)
except hag.GateError:
    check("a live read with ZERO config entries never passes", True)

# credentials: missing => exit 2, token never printed
buf_o, buf_e = io.StringIO(), io.StringIO()
with tempfile.TemporaryDirectory() as d:
    sfile = Path(d) / "s.json"; sfile.write_text(json.dumps(BASE))
    old = {k: os.environ.pop(k, None) for k in ("HASS_URL", "HASS_TOKEN")}
    orig = hag.HACTL_ENV
    hag.HACTL_ENV = Path(d) / "nope.env"
    try:
        with redirect_stdout(buf_o), redirect_stderr(buf_e):
            try:
                url, tok = hag.load_credentials(env={}, env_file=Path(d) / "nope.env")
                rc = 0
            except hag.GateError:
                rc = 2
        check("no credentials => precondition failure", rc == 2)
        envf = Path(d) / "h.env"; envf.write_text(f"HASS_URL=http://ha.local:8123\nexport HASS_TOKEN='{SECRET}'\n")
        u, t = hag.load_credentials(env={}, env_file=envf)
        check("credentials read from the hactl-style .env", u == "http://ha.local:8123" and t == SECRET)
        # main(): compare against a snapshot via the CLI path, token must not leak
        ha = FakeHA([bad], fail_reads=0)
        with redirect_stdout(buf_o), redirect_stderr(buf_e):
            rc = hag.main(["compare", "--snapshot", str(sfile), "--settle", "0", "--no-reload"], ha=ha)
        out = buf_o.getvalue() + buf_e.getvalue()
        check("CLI: regression exits 1 and prints a table", rc == 1 and "REGRESSIONS: 1" in out and "FAIL" in out, out)
        check("the token is never printed", SECRET not in out)
        with redirect_stdout(buf_o), redirect_stderr(buf_e):
            rc = hag.main(["compare", "--snapshot", str(Path(d) / "missing.json")], ha=FakeHA([BASE]))
        check("CLI: missing snapshot => exit 2", rc == 2)
        out_f = Path(d) / "out.json"
        with redirect_stdout(buf_o), redirect_stderr(buf_e):
            rc = hag.main(["snapshot", "--out", str(out_f)], ha=FakeHA([BASE]))
        check("CLI: snapshot writes a 0600 file", rc == 0 and (out_f.stat().st_mode & 0o777) == 0o600)
        with redirect_stdout(buf_o), redirect_stderr(buf_e):
            rc = hag.main(["compare", "--snapshot", str(out_f), "--settle", "0", "--no-reload"], ha=FakeHA([BASE]))
        check("CLI: snapshot then compare against the same state => exit 0", rc == 0)
    finally:
        hag.HACTL_ENV = orig
        for k, v in old.items():
            if v is not None: os.environ[k] = v

print("\nFAILED: %d" % len(FAILS) if FAILS else "\nALL PASS")
sys.exit(1 if FAILS else 0)

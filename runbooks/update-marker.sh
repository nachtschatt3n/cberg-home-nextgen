#!/usr/bin/env bash
# Active-update markers: tell the alert-triage-agent that alerts from an app/ns
# are EXPECTED for a window (so it silences their noise instead of paging you).
# State lives in runbooks/state/active-updates.json (auto-pruned of expired entries).
#
#   update-marker.sh add   <app> <namespace> <hours> [note]   # start a window
#   update-marker.sh clear <app>                              # end early
#   update-marker.sh list                                     # show active (pruned)
#   update-marker.sh check <app|-> <namespace>                # exit 0 if matched, 1 if not
#
# `check` matches when a non-expired marker has the same namespace AND
# (app == "-"/"*"/empty  OR  app substring-matches the passed app). Used by the agent.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STATE="$HERE/state/active-updates.json"
PYBIN="$([ -x "$HERE/../.venv/bin/python3" ] && echo "$HERE/../.venv/bin/python3" || echo python3)"
mkdir -p "$HERE/state"
[ -f "$STATE" ] || echo '{"active":[]}' > "$STATE"

cmd="${1:-list}"; shift || true
"$PYBIN" - "$STATE" "$cmd" "$@" <<'PY'
import json, sys
from datetime import datetime, timezone, timedelta
state, cmd, *rest = sys.argv[1:]
now = datetime.now(timezone.utc)
def load():
    try: d = json.load(open(state))
    except Exception: d = {}
    act = d.get("active", [])
    # prune expired
    keep = []
    for e in act:
        try: exp = datetime.fromisoformat(e["until"].replace("Z","+00:00"))
        except Exception: continue
        if exp > now: keep.append(e)
    return {"active": keep}
def save(d): json.dump(d, open(state,"w"), indent=2); open(state,"a").write("\n")

d = load()
if cmd == "add":
    app, ns, hours = rest[0], rest[1], float(rest[2]); note = rest[3] if len(rest)>3 else ""
    until = (now + timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
    d["active"] = [e for e in d["active"] if not (e["app"]==app and e["namespace"]==ns)]
    d["active"].append({"app":app,"namespace":ns,"until":until,"note":note,
                        "started":now.strftime("%Y-%m-%dT%H:%M:%SZ")})
    save(d); print(f"marked: {app}/{ns} expected until {until}" + (f" ({note})" if note else ""))
elif cmd == "clear":
    app = rest[0]; before=len(d["active"])
    d["active"] = [e for e in d["active"] if e["app"]!=app]
    save(d); print(f"cleared {before-len(d['active'])} marker(s) for {app}")
elif cmd == "list":
    save(d)  # persist the prune
    if not d["active"]: print("no active update markers")
    for e in d["active"]: print(f"  {e['app']}/{e['namespace']}  until {e['until']}  {e.get('note','')}")
elif cmd == "check":
    save(d)
    app = (rest[0] if rest else "").strip(); ns = rest[1] if len(rest)>1 else ""
    for e in d["active"]:
        if e["namespace"] != ns: continue
        ea = e["app"]
        if ea in ("-","*","") or app=="" or ea in app or app in ea:
            print(f"MATCH: {e['app']}/{e['namespace']} until {e['until']} {e.get('note','')}")
            sys.exit(0)
    print("no match"); sys.exit(1)
else:
    print(f"unknown command: {cmd}", file=sys.stderr); sys.exit(2)
PY

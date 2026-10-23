---
plan_id: wazuh-100404-ci-build-tuning
component: wazuh                      # Wazuh manager ruleset: ConfigMap security/unifi-decoder, key unifi_rules.xml
                                      # (the Falco 100400-100404 family lives HERE, not in wazuh-local-rules)
pr: null                              # no Renovate PR; sweep PLAN-lane finding (cycle 288980ff, rule 4e)
kind: infra
current: "100404 children 100413/100414/100415 INERT (defined before their parent); CI builds alert at level 12"
target: "100414/100415 moved after 100404, 100413 deleted, new 100416/100417 demote dind/BuildKit CI build execs to level 3"
update_type: n/a
risk: low                             # config-only rules edit + one manager pod roll. The failure that matters (a rule
                                      # that does not load) is DETECTED by §4.1 within minutes and reverted by git.
                                      # Matched scope measured offline: 22/22 target events, 0 of the other 114,383
                                      # retained 100404 events (May-Oct 2026 archive on the manager).
est_duration_min: 25                  # §2 5 + §3 5 + Flux pickup + STS roll ~5 + §4 replay/log gates 5 + slack 5
needs_reboot: false
exclusive: false
touches:
  namespaces: [security]
  resources:                          # every object re-verified to EXIST live 2026-10-23 (kubectl get)
    - configmap/security/unifi-decoder              # key unifi_rules.xml EDITED (falco group only)
    - statefulset/security/wazuh-manager-master     # annotation checksum/unifi-decoder bumped -> pod rolls
    - pod/security/wazuh-manager-master-0           # restarted once (analysisd reads rules only at start)
    - kustomization/flux-system/wazuh               # Flux Kustomization that applies both (no manual reconcile)
    - kubernetes/apps/security/wazuh/app/unifi-decoder-configmap.yaml
    - kubernetes/apps/security/wazuh/app/wazuh-manager-statefulset.yaml
  shared:
    - wazuh-siem                      # the manager restart pauses rule evaluation for ALL agents (~2-3 min; agents
                                      # buffer and resend). Every Falco/UniFi/Envoy SIEM rule is re-loaded.
    - monitoring                      # §4 reads Prometheus alerts (WazuhManagerPodNotReady / WazuhPodCrashLooping)
depends_on: []
conflicts_with:
  - talos-linux-1.14.4                # node roll restarts the manager, agents and Falco - confounds every §4 gate
                                      # (talos-linux-1.14.2 is superseded by it; the old kube-prometheus-stack-91.9.0
                                      # entry was dropped 2026-10-23: no kube-prometheus-stack plan is open - if one is
                                      # filed, re-add it, because §4 CONTROL reads Prometheus alert state)
  - falco-9.2.1                       # Falco chart roll in ns security (HelmRelease falco): restarts the Falco daemonset
                                      # whose events feed 100404 and confounds the §4.3 soak; same ns, same SIEM path
  - flux-oci-chart-sources            # touches ns security (falco chart source); a falco re-roll mid-replay confounds
  - flux-reconciler-impersonation     # rewrites how kustomize-controller applies ns security (this plan's apply+revert path)
capability_change: false              # detection TUNING: two narrowly-scoped child rules demote two benign build
                                      # shapes 12 -> 3 (still indexed), plus re-ordering two existing suppressions
                                      # so they do what their commits said. No new feature, route, permission, API
                                      # or exposure. (Operator may still prefer attended - see §6.)
rollback_class: git-revert            # no state: rules are read at analysisd start; revert + roll restores exactly
security_ref: F-2804f72b              # the level>=12 critical this answers; detail stays in the DB
finding_refs:
  - F-2804f72b                        # 22 level>=12 Wazuh alerts / 24h (PLAN lane, critical)
  - F-1ce8300f                        # the proposed remedy (tune 100404 for buildkit/dind CI builds)
review: ready-for-go@2026-10-23      # delta plan-reviewer 2026-10-23: ready-for-go
premises:
  # Read-only, single pipelines. Values re-measured 2026-10-23 (manager moved 4.14.8 -> 4.14.9 on 2026-10-16, efc54547;
  # the ruleset bytes and the roll checksum did NOT move).
  - id: live-rules-match-git-baseline
    why: >-
      §3's edit script anchors on exact text of the CURRENT unifi_rules.xml. The live ConfigMap key must be the
      same bytes as git HEAD. Premises may not run shasum, so this is the byte length (22049 live == git on
      2026-10-07); §2.2 additionally compares the sha256 prefix 485d64f10fce on both sides.
    run: kubectl get cm unifi-decoder -n security -o jsonpath='{.data.unifi_rules\.xml}' | wc -c | tr -d ' '
    expect_exact: "22049"
  - id: three-children-still-reference-100404
    why: "The inert-children defect this plan repairs must still be present (100413/100414/100415 -> 100404)."
    run: kubectl get cm unifi-decoder -n security -o jsonpath='{.data.unifi_rules\.xml}' | grep -c 'if_sid.100404..if_sid'
    expect_exact: "3"
  - id: manager-ready-on-baseline-checksum
    why: "§3 bumps checksum/unifi-decoder from this value; the manager must be Ready on it so a revert lands on known-good."
    run: kubectl get sts wazuh-manager-master -n security -o jsonpath='{.spec.template.metadata.annotations.checksum/unifi-decoder} {.status.readyReplicas}/{.status.replicas} {.spec.template.spec.containers[0].image}'
    expect_exact: 742b4950c2ee 1/1 wazuh/wazuh-manager:4.14.9
status: vetted
window: "nightly:2026-11-03"   # stamped 2026-10-23 on delta review
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/falco.md
  - docs/sops/monitoring.md
  - docs/sops/verification-contents-not-shape.md
  - docs/sops/vulnerability-disclosure.md
generated: "2026-10-07"
refreshed: "2026-10-23"             # baseline re-measured on manager 4.14.9; conflicts_with refreshed
---

# Wazuh 100404: demote ARC dind/BuildKit CI build execs, and repair the inert 100404 children

## 1. Summary & why held

**Driver.** Sweep finding `F-2804f72b` (PLAN lane, critical: "22 high-severity Wazuh alerts (level>=12) in last
24h"); remedy recorded as `F-1ce8300f`. Detail lives on the DB records — `runbooks/policy-cli.py finding show
F-2804f72b`. Publishable summary: every one of the 22 is Wazuh rule **100404** (Falco "Drop and execute new binary
in container", priority Critical -> level 12) on k8s-nuc14-01 / k8s-nuc14-03 between 16:13 and 23:27Z on
2026-10-06, and every one is a **CI image build** inside the ARC dind/BuildKit runners
(`arc-build/ninth-banner-build-k8s`, `ci-runner/ninth-banner-k8s`; warm runners introduced 2026-10-06 per
`docs/sops/ci-runner.md` changelog — which is why the shape first appears that day). Two shapes only, measured
from `/var/ossec/logs/alerts/2026/Oct/ossec-alerts-06.json.gz` on the manager:

| Shape | n | Distinguishing output fields |
|---|---|---|
| BuildKit QEMU/binfmt probe | 8 | `proc_exepath=/tmp/qemu-check<N>/check parent=buildkitd proc_sname=docker-init` |
| esbuild platform binary in a `RUN` step | 14 | `proc_exepath=/app/node_modules/esbuild/bin/esbuild ... container_id=buildkit/<id> proc_sname=docker-init` |

All 22 have `k8smeta_pod_name=<NA> k8smeta_ns_name=<NA> container_image_repository=<NA>`.

**Why the obvious remedy does not work as briefed.** The brief (and `F-1ce8300f`) says "lower the level only for
build containers in the CI runner namespaces". **The namespace is not observable**: these processes run in
containers started by the runner's *inner* dockerd/buildkitd, which the CRI never sees, so Falco reports every
k8s field as `<NA>`. Namespace scoping is impossible at either layer — which also rules out the Falco-side
exception pattern of `docs/sops/falco.md` §4 (it requires ns + pod + container + image). The scope used instead
is the strongest one available in the event itself, ANDed:

1. `proc_sname=docker-init` — the session leader is Docker's `--init` shim. Only the dind daemons start
   containers with it here; in the whole retained 100404 archive (114,405 events at authoring, May-Oct 2026) it appears in
   exactly these 22. Re-measured 2026-10-23: the retained October archives hold 121,529 `100404` events, of which
   144 carry `proc_sname=docker-init` - all in the SAME two shapes (128 esbuild, 16 qemu-check), no third shape.
2. all-`<NA>` k8s metadata (pod, ns, image) — i.e. NOT a kubelet-managed container.
3. an **exact exepath per build tool** (plus `parent=buildkitd` for the probe, `container_id=buildkit/` for the
   esbuild step) — so any OTHER binary dropped and executed inside a dind build container still alerts at 12.

Matched rules are **demoted to level 3, not 0**: the event stays in `wazuh-alerts` for audit and leaves only the
level>=12 bucket (and the 7-11 bucket that `security-check.py` s13 also counts). Offline match test of the final
pcre2 against the full archive at authoring: **22/22 target events, 0 of the other 114,383**; on 2026-10-23 the
two-shape census above (144 of 121,529, nothing else with `docker-init`) is unchanged in kind.

**Folded-in defect (confirmed live, not suspected).** The reviewer's suspicion is correct and wider than 100413:
**all three existing children of 100404 — 100413 (paperclip), 100414 (Nextcloud Collabora AppImage), 100415
(ESPHome toolchain) — are defined ABOVE 100404 in `unifi_rules.xml` and are inert.** analysisd resolves `<if_sid>`
only against already-loaded rules. Evidence, manager container log at the last start (**re-measured 2026-10-23 on the 4.14.9 pod, started
2026-10-16 01:43Z after the 4.14.8 -> 4.14.9 direct-bump**; the defect survived the upgrade because the ruleset
bytes did not change). Each child produces TWO lines now - the 7617 lookup failure and a 7619 "ignored" line:

```
WARNING: (7617): Signature ID '100404' was not found and will be ignored in the 'if_sid' option of rule '100413'.
WARNING: (7619): Empty 'if_sid' value. Rule '100413' will be ignored.
(same pair for rule '100414' and rule '100415')
```

and behaviourally: ESPHome toolchain events kept landing on 100404 / level 12 on 2026-08-26/27 (16k+ events) after
100415 was added on 2026-08-14 (`defae78f`), and a live `wazuh-logtest` replay of an archived ESPHome event today
returns `100404 / 12` (§4.2 "before" run). The same mistake was made and fixed once before for 100610
(`03568905`, comment at `unifi_rules.xml` ~line 341) — the lesson never reached the Falco block.

Repair, decided per rule:
- **100414, 100415: moved below 100404** (they become live). Effect is small: the Falco HelmRelease already
  excludes both shapes upstream (`kubernetes/apps/security/falco/app/helmrelease.yaml` lines ~228/231), so these
  are belt-and-braces, exactly as their authors intended.
- **100413: DELETED, not moved.** It is a blanket suppression of every 100404 in any `paperclip-*` ubuntu container.
  `F-6dc08159` explicitly forbids a Falco/Wazuh suppression for that container (the current paperclip hits are
  self-inflicted by the `paperclip-26.04` premise check and must stay visible — fix is in that plan, not here).
  Moving 100413 would have silently activated the forbidden suppression. Deleting it is behaviour-neutral (it
  never loaded); the apt/dpkg bootstrap noise it was written for is already excluded at the Falco layer
  (helmrelease line ~152).

**Why held / why a plan.** No version bump; the finding routed to PLAN by the default triage rule. It is a window
action (git edit + one manager roll), not an operator decision: no exposure is accepted, the demoted events remain
indexed, and every non-CI container keeps level 12 (proved by §4.2 controls). The one judgement call — whether a
detection-tuning change may run unattended — is raised in §6, not hidden.

## 2. Pre-checks

Run from the repo root, zsh. All read-only. STOP on any mismatch.

```bash
cd /Users/mu/code/cberg-home-nextgen
# 2.1 premises (live CM == git baseline, defect still present, manager Ready on baseline checksum)
.venv/bin/python3 runbooks/plan-premises.py wazuh-100404-ci-build-tuning
#   PASS = all three premises PASS. A byte-length (22049) mismatch means the ruleset changed since 2026-10-07: re-plan.

# 2.2 git file == live CM (the edit is applied to git; it must start from what is running)
python3 -c "import yaml,hashlib;print(hashlib.sha256(yaml.safe_load(open('kubernetes/apps/security/wazuh/app/unifi-decoder-configmap.yaml'))['data']['unifi_rules.xml'].encode()).hexdigest()[:12])"
#   expect: 485d64f10fce

# 2.3 Flux Kustomization healthy, manager pod Ready, no Wazuh alert already firing
flux get ks wazuh -n flux-system
kubectl -n security get pod wazuh-manager-master-0 -o jsonpath='{.status.phase} {.status.containerStatuses[0].ready}'; echo
#   expect: Running true
kubectl -n monitoring port-forward svc/kube-prometheus-stack-prometheus 9090:9090 >/dev/null 2>&1 & PF=$!; sleep 3
curl -s 'http://localhost:9090/api/v1/alerts' | python3 -c "import sys,json;a=[x['labels']['alertname'] for x in json.load(sys.stdin)['data']['alerts'] if x['labels']['alertname'].startswith('Wazuh') and x['state']=='firing'];print('FIRING',a)"
kill $PF 2>/dev/null
#   expect: FIRING []   (a pre-existing Wazuh alert would make §4.1 unreadable - stop and triage first)

# 2.4 IDs 100416/100417 unused in every rule source (repo AND the running manager's ruleset)
grep -rn -E 'id="10041[67]"' kubernetes/ ; echo "repo-hits=$?"        # expect repo-hits=1 (none)
kubectl -n security exec wazuh-manager-master-0 -- sh -c 'grep -rl -E "id=\"10041[67]\"" /var/ossec/etc/rules /var/ossec/ruleset/rules; echo done'
#   expect: only "done"

# 2.5 Write the replay harness and record the BEFORE baseline (must PASS in mode "before")
mkdir -p /tmp/w404
cat > /tmp/w404/replay.py <<'EOF'
#!/usr/bin/env python3
"""Replay 100404 fixtures through the LIVE manager's wazuh-logtest.
Prints one line per fixture: NAME rule=<id> level=<n> EXPECT=<...> PASS|FAIL.
Exit 1 on any FAIL or any fixture that could not be built/parsed (fail closed)."""
import json, re, subprocess, sys
NS, POD = "security", "wazuh-manager-master-0"
MODE = sys.argv[1] if len(sys.argv) > 1 else "after"   # before | after
def sh(cmd):
    return subprocess.run(["kubectl", "-n", NS, "exec", "-i", POD, "--", "sh", "-c", cmd],
                          capture_output=True, text=True, check=True).stdout
def first(path, needle):
    out = sh(f"zcat {path} | grep '\"id\":\"100404\"' | grep -F -m1 -- '{needle}'")
    if not out.strip(): sys.exit(f"FIXTURE-MISSING {path} {needle}")
    return json.loads(out.splitlines()[0])["full_log"]
OCT6 = "/var/ossec/logs/alerts/2026/Oct/ossec-alerts-06.json.gz"
qemu    = first(OCT6, "proc_exepath=/tmp/qemu-check")
esbuild = first(OCT6, "proc_exepath=/app/node_modules/esbuild/bin/esbuild")
esphome = first("/var/ossec/logs/alerts/2026/Aug/ossec-alerts-13.json.gz", "proc_exepath=/root/.cache/esphome/")
paperclip = first("/var/ossec/logs/alerts/2026/Oct/ossec-alerts-01.json.gz", "proc_exepath=/tmp/t ")
def sub(s, a, b):
    if a not in s: sys.exit(f"SUBST-MISS {a!r}")
    return s.replace(a, b)
# Synthetic negatives derived from the real CI events (only the 'output' string matters to the rules)
dind_other = sub(sub(qemu, "proc_exepath=/tmp/qemu-check", "proc_exepath=/tmp/x-dropper"), "parent=buildkitd", "parent=sh")
k8s_qemu = sub(sub(qemu, "k8smeta_pod_name=<NA> k8smeta_ns_name=<NA>", "k8smeta_pod_name=web-0 k8smeta_ns_name=default"),
               "container_image_repository=<NA>", "container_image_repository=docker.io/library/alpine")
k8s_esbuild = sub(sub(esbuild, "container_id=buildkit/", "container_id=deadbeef"),
                  "k8smeta_pod_name=<NA> k8smeta_ns_name=<NA>", "k8smeta_pod_name=web-0 k8smeta_ns_name=default")
after = MODE == "after"
cases = [  # name, log, expected rule id, expected level
  ("ci-qemu-check",   qemu,      "100416" if after else "100404", "3"  if after else "12"),
  ("ci-esbuild",      esbuild,   "100417" if after else "100404", "3"  if after else "12"),
  ("esphome-100415",  esphome,   "100415" if after else "100404", "0"  if after else "12"),
  ("CTRL-paperclip",  paperclip, "100404", "12"),
  ("CTRL-dind-other", dind_other,"100404", "12"),
  ("CTRL-k8s-qemu",   k8s_qemu,  "100404", "12"),
  ("CTRL-k8s-esbuild",k8s_esbuild,"100404","12"),
]
bad = 0
for name, log, rid, lvl in cases:
    out = subprocess.run(["kubectl","-n",NS,"exec","-i",POD,"--","/var/ossec/bin/wazuh-logtest"],
                         input=log+"\n", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True).stdout
    ph3 = out.split("**Phase 3: Completed filtering (rules).", 1)
    if len(ph3) != 2:
        print(f"{name:18} NO-PHASE3 (logtest produced no rule match) FAIL"); bad += 1; continue
    gid = re.search(r"\tid: '(\d+)'", ph3[1]); glv = re.search(r"\tlevel: '(\d+)'", ph3[1])
    got = (gid and gid.group(1), glv and glv.group(1))
    ok = got == (rid, lvl)
    bad += not ok
    print(f"{name:18} rule={got[0]} level={got[1]} EXPECT={rid}/{lvl} {'PASS' if ok else 'FAIL'}")
print(f"RESULT mode={MODE} fail={bad}")
sys.exit(1 if bad else 0)
EOF
python3 /tmp/w404/replay.py before; echo "exit=$?"
#   expect: 7x PASS (all rule=100404 level=12), "RESULT mode=before fail=0", exit=0
#   Measured 2026-10-07 AND re-measured 2026-10-23 on manager 4.14.9 (archive fixtures still present): exactly that. Running "after" mode at this point MUST fail (measured: 3 FAIL -
#   ci-qemu-check, ci-esbuild, esphome-100415 all still 100404/12) - that is the proof §4.2 can fail.
python3 /tmp/w404/replay.py after; echo "exit=$? (expect exit=1 here, BEFORE the change)"
```

## 3. Steps

GitOps only. No `kubectl edit/apply`, no manual `flux reconcile` (the webhook applies; `docs/sops/application-update.md`).

**3.1 Write the edit script** (exact-anchor; aborts on any miss — dry-tested 2026-10-07 on a scratch copy):

```bash
cat > /tmp/w404/edit.py <<'PYEOF'
#!/usr/bin/env python3
"""Reorder/repair the Falco 100404 children in unifi_rules.xml. Exact-anchor edit; aborts on any miss."""
import sys, re
P = sys.argv[1]
t = open(P).read()
def cut(start_marker, end_marker):
    """Cut from the line holding start_marker through the line ending end_marker (inclusive)."""
    global t
    i = t.index(start_marker); i = t.rindex("\n", 0, i) + 1
    j = t.index(end_marker, i) + len(end_marker); j = t.index("\n", j) + 1
    blk = t[i:j]; t = t[:i] + t[j:]; return blk
assert t.count('<rule id="100413"') == 1 and t.count('<rule id="100414"') == 1 and t.count('<rule id="100415"') == 1
assert '<rule id="100416"' not in t and '<rule id="100417"' not in t
# 1) delete the paperclip blanket suppression (comment + rule) — inert today, and F-6dc08159 forbids activating it
cut("Suppress Falco \"Drop and execute new binary in container\" when\n           triggered by the paperclip", '<group>falco,homelab,suppress,</group>\n      </rule>')
# 2) lift the Nextcloud + ESPHome children (comment + rule) out of their pre-parent position
b414 = cut("Suppress Falco \"Drop and execute new binary in container\" when\n           triggered by the Nextcloud Collabora", '<group>falco,homelab,suppress,</group>\n      </rule>')
b415 = cut("Suppress Falco \"Drop and execute new binary in container\" for the\n           ESPHome firmware build", '<group>falco,homelab,suppress,</group>\n      </rule>')
assert '<rule id="100414"' in b414 and '<rule id="100415"' in b415 and '100413' not in t
new = '''      <!-- ── Children of 100404 MUST be defined AFTER 100404 (below). ──────────
           analysisd resolves <if_sid> only against rules ALREADY loaded; a child
           placed above its parent is dropped with "WARNING (7617): Signature ID
           '100404' was not found and will be ignored in the 'if_sid' option" and
           is INERT. 100413/100414/100415 sat above 100404 from their creation
           until 2026-10 and never fired (ESPHome bursts kept alerting at level 12
           on 2026-08-26/27). 100413 (paperclip blanket) was deleted rather than
           moved: F-6dc08159 forbids a blanket suppression of that container.
           ───────────────────────────────────────────────────────────────────── -->
'''
ci = '''      <!-- CI image builds on the ARC dind/BuildKit runners (arc-build,
           ci-runner; warm runners since 2026-10-06). Containers started by the
           runner's inner dockerd/buildkitd are INVISIBLE to the CRI, so Falco
           reports k8smeta_pod_name/ns/image as <NA> and namespace scoping is
           impossible; scope instead on (a) proc_sname=docker-init (session
           leader is the Docker init shim (docker-init) — only the dind daemons run it here),
           (b) all-<NA> k8s metadata, and (c) an EXACT exepath per build tool.
           DEMOTED to level 3, not 0: the event stays in wazuh-alerts for audit,
           it just leaves the level>=12 critical bucket. Any OTHER binary dropped
           and executed inside a dind build container still alerts at 12.
           Evidence: F-1ce8300f / F-2804f72b (22 hits 2026-10-06, all these two
           shapes; 0 matches in the other 114k retained 100404 events). -->
      <rule id="100416" level="3">
        <if_sid>100404</if_sid>
        <field name="output" type="pcre2">proc_sname=docker-init .*proc_exepath=/tmp/qemu-check\\d+/check parent=buildkitd .*k8smeta_pod_name=\\WNA\\W k8smeta_ns_name=\\WNA\\W .*container_image_repository=\\WNA\\W</field>
        <description>Falco (CI build, demoted): buildkitd QEMU/binfmt probe /tmp/qemu-check*/check in a dind container</description>
        <group>falco,homelab,ci_build,</group>
      </rule>
      <rule id="100417" level="3">
        <if_sid>100404</if_sid>
        <field name="output" type="pcre2">proc_sname=docker-init .*proc_exepath=/app/node_modules/(?:esbuild|@esbuild/linux-[a-z0-9]+)/bin/esbuild .*k8smeta_pod_name=\\WNA\\W k8smeta_ns_name=\\WNA\\W container_id=buildkit/\\w+ .*container_image_repository=\\WNA\\W</field>
        <description>Falco (CI build, demoted): esbuild platform binary run inside a BuildKit RUN step</description>
        <group>falco,homelab,ci_build,</group>
      </rule>
'''
anchor = '''        <description>Falco $(priority): $(rule)</description>
        <group>falco,homelab,attack,</group>
      </rule>
'''
assert t.count(anchor) == 1, "100404 anchor not unique"
t = t.replace(anchor, anchor + new + b414 + b415 + ci)
open(P, "w").write(t)
print("OK edited", P)
PYEOF
```

Notes on the rule text (each was a real trap): `<NA>` is matched as `\WNA\W` so no literal `<` appears inside an XML
element; no `--` inside the new XML comments; `output` is a dynamic JSON field (only `url`/`srcip`/... are static —
memory `project_wazuh_local_rule_authoring`), so `<field name="output" type="pcre2">` is correct, as in 100410-100415.

**3.2 Apply to the repo file, then the ordering gate (must PASS; it FAILS on today's file — measured):**

```bash
cd /Users/mu/code/cberg-home-nextgen
F=kubernetes/apps/security/wazuh/app/unifi-decoder-configmap.yaml
python3 /tmp/w404/edit.py "$F"            # expect: OK edited ...
cat > /tmp/w404/order_check.py <<'EOF'
import sys,yaml,re
x=yaml.safe_load(open(sys.argv[1]))['data']['unifi_rules.xml']
ids=re.findall(r'<rule id="(\d+)"',x); pos={i:n for n,i in enumerate(ids)}
bad=0
for rid,body in re.findall(r'<rule id="(\d+)"[^>]*>(.*?)</rule>',x,re.S):
    for p in re.findall(r'<if_sid>(\d+)</if_sid>',body):
        if p in pos and pos[p]>pos[rid]: print('CHILD-BEFORE-PARENT',rid,'parent',p); bad+=1
print('ORDER', 'FAIL' if bad else 'PASS', bad); sys.exit(1 if bad else 0)
EOF
python3 /tmp/w404/order_check.py "$F"     # expect: ORDER PASS 0   (on the pre-edit file it prints 3x CHILD-BEFORE-PARENT, ORDER FAIL 3)
python3 -c "import yaml,re;x=yaml.safe_load(open('$F'))['data']['unifi_rules.xml'];print([i for i in re.findall(r'<rule id=\"(1004\d\d)\"',x)])"
#   expect: ['100400', '100410', '100411', '100412', '100401', '100402', '100403', '100404', '100414', '100415', '100416', '100417']
git diff --stat -- "$F"                   # expect: 1 file changed, ~40 insertions, ~35 deletions
```

**3.3 Bump the roll trigger** (analysisd reads rules only at process start; the mount is a whole-dir ConfigMap
volume, so the file updates in place but nothing reloads it). The annotation is the first 12 hex of the file's
sha256 (verified: `742b4950c2ee` == sha of the current file). BSD-sed dry-tested on a scratch copy:

```bash
NEW=$(shasum -a 256 kubernetes/apps/security/wazuh/app/unifi-decoder-configmap.yaml | cut -c1-12); echo "$NEW"
sed -i '' -E "s|^([[:space:]]*checksum/unifi-decoder: )\"[0-9a-f]{12}\"|\1\"${NEW}\"|" kubernetes/apps/security/wazuh/app/wazuh-manager-statefulset.yaml
git diff kubernetes/apps/security/wazuh/app/wazuh-manager-statefulset.yaml
#   expect exactly one line: -        checksum/unifi-decoder: "742b4950c2ee"
#                            +        checksum/unifi-decoder: "<NEW>"
#   (scratch dry-run of the 2026-10-07 edit produced "cf5ce44ba559"; yours will match only if the edit is byte-identical)
```

**3.4 Validate + commit (shared worktree rules) + push:**

```bash
kubeconform -summary -ignore-missing-schemas kubernetes/apps/security/wazuh/app/
cat > /tmp/w404/msg.txt <<'EOF'
fix(wazuh): demote ARC dind/BuildKit CI build execs; repair inert 100404 children

- 100416/100417 (level 3): BuildKit qemu-check probe and esbuild-in-RUN-step,
  scoped to proc_sname=docker-init + all-<NA> k8s metadata + exact exepath.
  Every other 100404 (incl. any other binary in a dind container) stays 12.
- 100414/100415 moved below 100404: they were defined before their parent and
  dropped at load (WARNING 7617) since creation.
- 100413 deleted (inert; F-6dc08159 forbids activating a paperclip blanket).
- checksum/unifi-decoder bumped to roll the manager.

Plan: wazuh-100404-ci-build-tuning. Findings: F-2804f72b, F-1ce8300f.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
EOF
git commit --only kubernetes/apps/security/wazuh/app/unifi-decoder-configmap.yaml \
  kubernetes/apps/security/wazuh/app/wazuh-manager-statefulset.yaml -F /tmp/w404/msg.txt
git log -1 --format=%s     # MUST read "fix(wazuh): demote ARC dind/BuildKit CI build execs; ..." - amend before push if not
git show --stat HEAD       # exactly the 2 files above
git push
```

## 4. Verification

**4.1 The new ruleset LOADED (the failure that matters: a rule that does not load).** Wait for the roll:

```bash
for i in $(seq 1 30); do
  A=$(kubectl -n security get sts wazuh-manager-master -o jsonpath='{.spec.template.metadata.annotations.checksum/unifi-decoder} {.status.updatedReplicas}/{.status.readyReplicas}')
  echo "$A"; [ "$A" = "$NEW 1/1" ] && break; sleep 20; done
kubectl -n security get pod wazuh-manager-master-0 -o jsonpath='{.status.startTime} {.status.containerStatuses[0].ready}'; echo
#   PASS: annotation == $NEW, 1/1, pod startTime AFTER the push, ready true. (Ready alone is not proof - the
#   manager has gone Ready with analysisd dead before; 4.1b/4.2 are the contents gates.)

# 4.1b load-time log of THIS pod start: no if_sid warning for any local 1004xx rule, no rule-load error
kubectl -n security logs wazuh-manager-master-0 | grep -iE "rule '1004[0-9]{2}'|Error loading the rules|Failure to read rule|CRITICAL|7612" ; echo "grep-exit=$?"
#   PASS: no lines, grep-exit=1.
#   What FAILURE prints (re-measured on the CURRENT 4.14.9 pod's start log 2026-10-23, grep-exit=0): six lines -
#   "WARNING: (7617): Signature ID '100404' was not found ... of rule '10041[345]'" plus a matching
#   "WARNING: (7619): Empty 'if_sid' value. Rule '10041[345]' will be ignored." for each. A bad pcre2 prints
#   "Failure to read rule" + "CRITICAL: Error loading the rules" and analysisd exits.
#   Case-insensitive on purpose (upstream mixes WARNING/Warning).
```

CONTROL: alertname WazuhManagerPodNotReady — must be NOT firing 10 min after the roll (a rule-load CRITICAL
kills analysisd and the manager goes not-ready).
CONTROL: alertname WazuhPodCrashLooping — must be NOT firing for `wazuh-manager-master-0` after the roll.

```bash
kubectl -n monitoring port-forward svc/kube-prometheus-stack-prometheus 9090:9090 >/dev/null 2>&1 & PF=$!; sleep 3
curl -s 'http://localhost:9090/api/v1/rules?type=alert' | python3 -c "
import sys,json
r=[x for g in json.load(sys.stdin)['data']['groups'] for x in g['rules'] if x['name'] in ('WazuhManagerPodNotReady','WazuhPodCrashLooping')]
assert len(r)==2, f'CONTROL rules not loaded in Prometheus: {[x[\"name\"] for x in r]}'
for x in r: print(x['name'], x['state'])"
kill $PF 2>/dev/null
#   PASS: both printed, both "inactive". The assert fails closed if either rule is not loaded (an absent rule reads
#   as "not firing" otherwise - memory project_prometheusrule_silent_ignore).
```

**4.2 CONTENTS ASSERTION: the right events moved and nothing else did** — measured by replaying 7 fixtures
(4 real archived events + 3 synthetic negatives derived from them) through the LIVE manager's `wazuh-logtest`,
compared to the §2.5 baseline (all 7 at `100404/12`):

```bash
python3 /tmp/w404/replay.py after; echo "exit=$?"
#   PASS (exit=0, "RESULT mode=after fail=0"):
#     ci-qemu-check      rule=100416 level=3   <- (a) dind/BuildKit probe drops below 12
#     ci-esbuild         rule=100417 level=3   <- (a) esbuild in a BuildKit RUN step drops below 12
#     esphome-100415     rule=100415 level=0   <- ordering repair: the previously inert child now fires
#     CTRL-paperclip     rule=100404 level=12  <- (b) real non-CI container (ai/paperclip tools) stays 12 (F-6dc08159)
#     CTRL-dind-other    rule=100404 level=12  <- (b) ANY other binary inside a dind container stays 12
#     CTRL-k8s-qemu      rule=100404 level=12  <- (b) same exepath in a kubelet-managed pod stays 12
#     CTRL-k8s-esbuild   rule=100404 level=12  <- (b) esbuild in a normal pod/container stays 12
#   This gate CAN fail and has: run against today's ruleset it prints 3 FAIL (the three upper rows at 100404/12),
#   exit=1 (measured 2026-10-07). Fail-closed paths: a missing archived fixture -> FIXTURE-MISSING, a logtest
#   output with no rule phase -> NO-PHASE3 FAIL (this caught a stderr-vs-stdout bug while authoring).
```

**4.3 Soak (not a window gate — needs a real CI build after the roll).** After the next ARC image build:

```bash
kubectl -n security exec wazuh-manager-master-0 -- sh -c 'echo demoted=$(grep -cE "\"id\":\"10041[67]\"" /var/ossec/logs/alerts/alerts.json) crit_dind=$(grep "\"id\":\"100404\"" /var/ossec/logs/alerts/alerts.json | grep -c "proc_sname=docker-init")'
#   expected after a build: demoted>0 (FLOOR - proves the rules match live traffic, not only fixtures), crit_dind=0.
#   demoted=0 with no build since the roll is INCONCLUSIVE, not a pass. crit_dind>0 means a NEW build tool shape:
#   triage it as a real event first; only after that consider a further exact-exepath child (never broaden these two).
```

Finding close-out: `F-2804f72b` is script-produced and re-evaluates from s13 each sweep. The 24h count decays as
the 2026-10-06 events age out (suppression is forward-only); it reaches 0 only if nothing else is at >=12 — the
paperclip premise-check hits (`F-6dc08159`, owned by `paperclip-26.04`) will keep it non-zero on sweep nights
until that plan's premise is fixed. `F-1ce8300f` is agent-authored and never auto-closes:
`runbooks/policy-cli.py finding close F-1ce8300f --commit <sha>` after 4.2 passes.

## 5. Rollback

Trigger: any §4.1/4.1b/4.2 FAIL, or `WazuhManagerPodNotReady` firing.

```bash
cd /Users/mu/code/cberg-home-nextgen
SHA=$(git log -1 --format=%H --grep='demote ARC dind/BuildKit CI build execs')
git revert --no-edit "$SHA"        # restores BOTH files: rules text AND checksum 742b4950c2ee -> rolls the manager again
git log -1 --format=%s             # confirm it is the revert, then:
git push
# confirm back on baseline (same premises as §2.1):
.venv/bin/python3 runbooks/plan-premises.py wazuh-100404-ci-build-tuning     # all PASS again (sha 485d64f10fce, checksum 742b4950c2ee, 1/1)
python3 /tmp/w404/replay.py before; echo "exit=$?"                            # exit=0 - all 7 back at 100404/12
```

No forward-only state: rules are re-read at analysisd start, the alert indices are untouched, and demoted level-3
alerts written in the meantime stay indexed (nothing is lost — that is why the demotion is 3, not 0). If analysisd
is crash-looping on a bad rule, the revert is still the fix (Flux applies the ConfigMap regardless of pod health);
do NOT `kubectl edit` the ConfigMap — Flux would revert it, and the git history must carry the fix.

## 6. Interference notes

- **Manager restart = ~2-3 min SIEM gap for every source** (UniFi syslog, Envoy access logs, Falco, FIM). Agents
  buffer and resend; UniFi remote syslog over UDP does not — a few UniFi lines in the restart window can be lost.
  Acceptable for nightly; avoid running it while an incident is being investigated in Wazuh.
- **conflicts_with:** `talos-linux-1.14.4` (node roll restarts manager, agents and Falco; 1.14.2 is superseded),
  `falco-9.2.1` (Falco chart roll in ns `security`; confounds the §4.3 soak), `flux-oci-chart-sources`
  (moves the Falco chart source in ns `security`), `flux-reconciler-impersonation` (changes how ns `security` is
  applied; currently `blocked`). No `kube-prometheus-stack` plan is open as of 2026-10-23; if one is filed, add it
  (§4.1 CONTROL reads Prometheus). **Reciprocity is NOT yet declared on those plans** — this planner may write only its own file;
  the vetting pass should add `wazuh-100404-ci-build-tuning` to their `conflicts_with`.
- **paperclip-26.04** is deliberately NOT a conflict: CTRL-paperclip replays an ARCHIVED event, so a live paperclip
  premise check the same night does not confound §4.2. Its live hits will (correctly) still read level 12.
- **CI builds during the window are harmless** (they only add events); a build after the roll is in fact what the
  §4.3 floor needs.
- **Unattended eligibility (operator judgement, surfaced not hidden):** declared facts are risk low /
  capability_change false / git-revert, which makes this AUTO-NIGHT/SD-10-eligible once reviewed. It is a
  detection-REDUCING change, even if narrow and level-3-preserving. If the operator wants every SIEM tuning
  attended, that belongs in `runbooks/autonomy-policy.yaml` as a rule, not in this plan's facts.
- **Repo corrections found while planning** (not applied here):
  1. `docs/sops/falco.md` has no warning that k8s metadata is `<NA>` for dind/BuildKit-spawned containers, so its
     "match ns + pod + container + image" rule cannot be followed for CI builds — worth a short subsection.
  2. Neither `docs/sops/falco.md` nor `docs/sops/monitoring.md` records the child-after-parent rule; it exists only
     as a comment near 100610. Three rules violated it unnoticed for months. A load-log check for `(7617)` on local
     IDs in the sweep's s13 would catch the next one.
  3. `checksum/envoy-decoder` in the StatefulSet (`6f62f6342128`) does not match the current
     `envoy-decoder-configmap.yaml` sha prefix (`7120fd9ace46`): its last edit (`1c0d9817`, 2026-09-11) did not
     bump the annotation. Harmless TODAY only because the manager restarted later (2026-09-27) for another reason;
     the next envoy-rule edit made the same way would not roll. Separate correction; not touched here.

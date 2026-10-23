---
plan_id: otbr-0.4.0
component: otbr
pr: null                              # RE-SCOPED 2026-10-23 (independent review). The v0.3.0 -> v0.4.0 bump
                                      # already LANDED as Renovate PR #357, commit 668f56c9 (2026-10-16 03:34
                                      # CEST), WITHOUT the four env pins the first version of this plan required.
                                      # This plan is now the FIX-FORWARD: add the pins. No Renovate PR exists.
kind: image
current: "v0.4.0"                     # LIVE 2026-10-23: pod otbr-b68c767c8-4z4sz (7d15h, R=0, k8s-nuc14-03)
                                      # imageID ghcr.io/ownbee/hass-otbr-docker@sha256:790f21835c86e0d9b9071f21b042ca77ef0ff70e714e8454903982a00df83cfb
target: "v0.4.0"                      # SAME image. Only four env vars change (see section 1). Ships no new binary.
update_type: config                   # env pins on an already-deployed tag
risk: medium                          # Not from the diff (4 env lines) but from the surface: one Recreate roll of
                                      # a privileged hostNetwork Thread Border Router that rewrites the NODE's
                                      # iptables, and it re-runs the settings-migration script (section 1.3).
                                      # The mesh survives the ~2 min restart (two other Border Routers).
est_duration_min: 25                  # 8 pre-checks/baseline + 3 commit/push + 4 Recreate roll + 8 gates + 2 buffer
needs_reboot: false
touches:
  namespaces: [home-automation]
  resources:
    - helmrelease/otbr                # 4 env vars added -- the ONLY git change
    - deployment/otbr                 # one Recreate roll (strategy verified live: Recreate)
    - pvc/otbr-data                   # NOT edited. /data/thread holds the persisted Thread dataset; the
                                      #   migration script runs against it on EVERY start (section 1.3)
    - service/otbr                    # not edited
    - httproute/otbr                  # not edited
  shared:
    - thread-mesh                     # our BR leaves/rejoins the Thread network for ~2 min
    - host-netfilter/k8s-nuc14-03     # privileged hostNetwork pod rewrites the NODE's iptables/ip6tables
                                      #   (ingress filter chain, NAT64 MASQUERADE + mangle mark) on start/stop
    - lan-exposure/k8s-nuc14-03:8080  # OTBR_WEB=1 starts otbr-web on the node IP, port 8080, all interfaces,
                                      #   LAN-only, NOT routed through the Gateway (as under v0.3.0)
    - home-assistant/otbr-integration # HA config entry otbr -> http://192.168.55.13:8081 (node IP)
    - monitoring                      # gate 4.8 reads kube-state-metrics through Prometheus
depends_on: []
conflicts_with:                       # pruned 2026-10-23: dropped kube-prometheus-stack-92.2.0 (no such plan)
                                      # and home-assistant-2026.10.1 (superseded -> 2026.10.2)
  - talos-linux-1.14.2                # node roll reboots k8s-nuc14-03 (our pinned node) and flushes host netfilter
  - talos-linux-1.14.4                # same
  - home-assistant-2026.10.2          # HA restart flaps the otbr/thread integrations and the HA pod is the
                                      #   instrument for gate 4.5 (_meshcop browse) -- serialize
  - cilium-1.20.3                     # Cilium owns FORWARD/nat chains on the same node; this pod adds its own
  - flux-oci-chart-sources            # rewrites this HR's chart source (bjw-s app-template)
  - helm-drift-detection              # adds spec.driftDetection to every HR incl. helmrelease/otbr
  - flux-reconciler-impersonation     # changes the identity helm-controller applies home-automation/ with
  - flux-distribution-2.9.6           # upgrades the Flux controllers that apply this HR and revert it
  - talos-power-tuning-ab             # node-level change on the same node set (power caps); keep attribution clean
  - multus-macvlan-foundation         # cni-adjacent work in home-automation that names otbr (stays hostNetwork)
exclusive: false
security_ref: null                    # not security-driven by a version. NOTE for the operator: the open ingress
                                      # filter is a posture regression on this host; the register records for this
                                      # image stay on F-d2d378c8 / F-894245ce (detail on the records only).
capability_change: false              # restores the v0.3.0 behaviour (measured 2026-10-14): ingress filter, NAT64,
                                      # web UI, hardware flow control. Nothing new is enabled relative to what ran
                                      # before 2026-10-16.
rollback_class: git-revert            # section 5.1: revert the pin commit. Nothing forward-only beyond the
                                      # settings file, which has an explicit procedure (section 5.2)
autonomy_override: human-gated        # operator 2026-10-23: human-gated. It restarts the Thread BR and changes
                                      # host firewall behaviour; a GO is required even though the diff is 4 lines
finding_refs: [F-f6b592f2]            # filed 2026-10-23 for the missed pins (detail on the record)
review: ready-for-go@2026-10-23
status: vetted
window: null                          # LEFT NULL until the operator GO
premises:
  - id: live-image-is-v0.4.0
    why: >-
      The plan is a fix-forward ON TOP of v0.4.0. If the image moved (v0.4.1, or a revert of
      #357) the analysis of the inverted defaults must be redone.
    run: kubectl get pod -n home-automation -l app.kubernetes.io/name=otbr -o jsonpath='{.items[*].status.containerStatuses[*].imageID}'
    expect_contains: "sha256:790f21835c86e0d9b9071f21b042ca77ef0ff70e714e8454903982a00df83cfb"
  - id: pins-still-absent
    why: >-
      The edit adds FIREWALL/NAT64/FLOW_CONTROL/OTBR_WEB. If any is already set the edit would
      duplicate a key -- re-plan.
    run: kubectl get deploy -n home-automation otbr -o jsonpath='{.spec.template.spec.containers[0].env[*].name}'
    expect_matches: '^(?!.*\b(FIREWALL|NAT64|FLOW_CONTROL|OTBR_WEB)\b).*NETWORK_DEVICE.*$'
  - id: rcp-is-wired-unit
    why: >-
      The deployment comment says scale to 0 if NETWORK_DEVICE moves to a WiFi unit; then this is the wrong job.
    run: kubectl get deploy -n home-automation otbr -o jsonpath='{.spec.template.spec.containers[0].env[?(@.name=="NETWORK_DEVICE")].value}'
    expect_exact: "192.168.33.238:6638"
  - id: hr-ready
    why: A reconcile already failing would make gate 4.1 unattributable.
    run: kubectl get helmrelease -n home-automation otbr -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: "True"
  - id: otbr-available
    why: The baseline in section 2 is read from the running pod.
    run: kubectl get deploy -n home-automation otbr -o jsonpath='{.status.availableReplicas}'
    expect_exact: "1"
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/home-assistant-updates.md
  - docs/sops/longhorn.md
  - docs/sops/backup.md
  - docs/sops/verification-contents-not-shape.md
generated: "2026-10-14"
revised: "2026-10-23"
---

# otbr v0.4.0 -- fix-forward: restore the four inverted env pins

## 1. Summary & why held

**What happened.** The first version of this plan (2026-10-14) bundled the v0.3.0 -> v0.4.0 bump with
four env pins. Renovate PR #357 (`668f56c9`, 2026-10-16 03:34 CEST) landed the bump **alone**, so
`ghcr.io/ownbee/hass-otbr-docker:v0.4.0` has run for 7 days without the pins. The independent review
(2026-10-23) found the plan obsolete and the regression live. This plan replaces it: same image, add the
four env vars on `helmrelease/otbr` (app-template 5.3.0, ns `home-automation`; privileged, hostNetwork,
single replica pinned to `k8s-nuc14-03`, Recreate strategy, spinel-over-TCP to the SLZB-06P7 RCP at
`192.168.33.238:6638`).

**Why v0.4.0 behaves differently without them.** v0.4.0 inverted four "unset = ON" tests into
"must be `1`". Verified in the RUNNING container's scripts (`/etc/s6-overlay/...`, 2026-10-23), not only in
the release diff:

| Var | v0.4.0 test (live script) | LIVE effect today (unset) | v0.3.0 behaviour to restore |
|---|---|---|---|
| `FIREWALL` | `otbr-agent/run:84` `[ x"${FIREWALL}" = x"1" ]`, else branch appends only `-j ACCEPT` | `ip6tables -S OTBR_FORWARD_INGRESS` = `-N` + `-A ... -j ACCEPT` only: **0** unicast-DROP rules, 0 `match-set` rules (ingress filter OPEN) | 2 unicast-DROP + 2 `match-set` rules |
| `NAT64` | `otbr-agent/run:100` and `otbr-agent-configure.sh:9` test `= "1"` | `ot-ctl nat64 state` = `PrefixManager: Disabled / Translator: Disabled`; `dns server upstream` = `Disabled`; **0** `mark 0x1001` MASQUERADE rules | PrefixManager `Idle`, 1 MASQUERADE rule, upstream DNS enabled |
| `OTBR_WEB` | `scripts/enable-check.sh:49` starts otbr-web only `if [ -n "${OTBR_WEB}" ]` | `s6-svstat /run/service/otbr-web` = `down (not started yet)`; `http://192.168.55.13:8080/` -> connection refused (curl `000`) | otbr-web up, :8080 -> 200 |
| `FLOW_CONTROL` | `otbr-agent/run` `= "1"` else `&uart-init-deassert` | agent URL `spinel+hdlc+uart:///tmp/ttyOTBR?uart-baudrate=115200&uart-init-deassert` | `...&uart-flow-control` (what v0.3.0 ran, measured 2026-10-14) |

Everything else is healthy today: `state` = `router`, 2 router neighbours, ba-id
`a46bcba497701adf204feb4fecd663a9`, ext PAN `1391992999084adf`, network `MyHome900239170`, REST 8081 answers
(`"router"`), 0 restarts. So the Thread mesh is up but the host is running without the ingress filter and
without NAT64 (Thread devices have no IPv4 path), and the web UI is gone.

**Upstream defaults (primary source, not a SOP).** `ownbee/hass-otbr-docker` v0.4.0 (compare
`v0.3.0...v0.4.0`) and the scripts above: all four vars must be set to `1` to get the v0.3.0 behaviour.
`OTBR_WEB` is only tested for non-empty at container start (`enable-check.sh`, a cont-init step), so it must
be present in the pod env, not set later. Note `otbr-web/run` itself defaults `${OTBR_WEB:-1}`, which is why
reading only that file would suggest the web UI is on by default; it is not started at all.

**Why held / human-gated.** Operator decision 2026-10-23: human-gated. The change restarts the Thread BR and
alters host firewall behaviour on a shared node. Exposure note for the GO: `OTBR_WEB=1` re-opens
`node-IP:8080` on the LAN (the UI is not behind the Gateway), exactly as before 2026-10-16. If the operator
prefers the UI stays off, drop that one pin and delete gate 4.4 -- a separate decision, not made here.
**OPERATOR DECISION AT THE GO: OTBR_WEB=1 exposes the otbr web UI on node-ip:8080 to the LAN** (not behind the Gateway or Authentik). Confirm or drop that pin.

### 1.1 Observed on the live pod (for the window agent)

- `/data/thread` now holds `0_124b002d12c333.data` (248 B) **and** `0_0-tmp.data` (32 B, created at the
  2026-10-16 start). The old plan expected one file. `0_0-tmp.data` is a v0.4.0 migration artefact, not
  a second identity (eui64 = `00124b002d12c333`). Do not delete it; record before/after (gate 4.3).
- The pod logs were empty when read on 2026-10-23, so the "migration took the skip path" evidence from the
  first plan could not be re-measured; gate 4.3 relies on dataset/ba-id equality instead.

### 1.2 Settings migration (re-runs on this roll)

`migrate_otbr_settings.py` runs before otbr-agent on every start. On 2026-10-16 it left `0_124b002d12c333.data`
intact (dataset/ba-id equal after the first v0.4.0 start). The same path should repeat; gate 4.3 compares
against a baseline captured immediately before. Dataset recovery is in section 5.2.

## 2. Pre-checks

Run from the repo root on the Mac mini (zsh). Baseline files hold the Thread network key: keep them in a
mode-700 dir outside the repo and delete after the soak (5.3).

```bash
# 2.1 premises (fail closed)
.venv/bin/python3 runbooks/plan-premises.py otbr-0.4.0

# 2.2 nightly backup of the settings volume is fresh (< 26h); floor for 5.2
kubectl get volume -n storage pvc-da17b5c6-0d8c-42cf-9a25-bc444ac9a71d -o jsonpath='{.status.lastBackup} {.status.lastBackupAt}{"\n"}'
# 2026-10-23: backup-eb896a3fec244900 2026-10-23T14:24:07Z

# 2.3 baseline (secret material -> local only)
B=/tmp/otbr-0.4.0; mkdir -p $B && chmod 700 $B
kubectl -n home-automation exec deploy/otbr -- sh -c 'ls -la /data/thread' | tee $B/ls-before.txt
kubectl -n home-automation exec deploy/otbr -- cat /data/thread/0_124b002d12c333.data > $B/0_124b002d12c333.data
kubectl -n home-automation exec deploy/otbr -- sha256sum /data/thread/0_124b002d12c333.data
shasum -a 256 $B/0_124b002d12c333.data           # PASS: identical hash (the file can change by a few bytes at runtime; re-read if not)
kubectl -n home-automation exec deploy/otbr -- ot-ctl dataset active -x | head -1 > $B/dataset.hex
chmod 600 $B/*; shasum -a 256 $B/dataset.hex | cut -c1-64 > $B/dataset.sha
kubectl -n home-automation exec deploy/otbr -- sh -c 'ot-ctl ba id; ot-ctl extpanid; ot-ctl networkname; ot-ctl state; ot-ctl neighbor table' | tee $B/thread-before.txt
# expected 2026-10-23: ba id a46bcba4..., extpanid 1391992999084adf, state router, 2 'R' neighbours

# 2.4 record the REGRESSION baseline (every number below must CHANGE in section 4)
kubectl -n home-automation exec deploy/otbr -- sh -c 'echo ingress_drop=$(ip6tables -S OTBR_FORWARD_INGRESS | grep -c "pkt-type unicast -j DROP"); echo masq=$(iptables -t nat -S POSTROUTING | grep -c "mark 0x1001"); ot-ctl nat64 state' | tee $B/regression-before.txt
curl -s -m5 -o /dev/null -w 'web8080=%{http_code}\n' http://192.168.55.13:8080/ | tee -a $B/regression-before.txt
# 2026-10-23: ingress_drop=0  masq=0  PrefixManager: Disabled / Translator: Disabled  web8080=000
# GATE: if ingress_drop is already 2 the regression was fixed by someone else -> STOP, plan is moot.
# (This is not a premise: the premise sandbox refuses `kubectl exec`.)

# 2.5 no other change in flight in home-automation, no Talos/Cilium work
flux get helmreleases -n home-automation | awk 'NR==1 || $5 != "True"'     # header only
```

2.6 Run the `_meshcop` browse from gate 4.5 and record the baseline (3 Border Routers on 2026-10-14).

## 3. Steps (GitOps)

The edit script was dry-tested 2026-10-23 on a scratch copy of the HelmRelease (macOS, python only, no sed).
Diff was exactly `60a61,73` (13 added lines after the `OTBR_REST_PORT` entry); a second run aborts with
`AssertionError: pins already present`; the YAML parses with the env list
`TZ, NETWORK_DEVICE, DEVICE, BAUDRATE, BACKBONE_IF, OTBR_REST_PORT, FIREWALL, NAT64, FLOW_CONTROL, OTBR_WEB`.

```bash
cd /Users/mu/code/cberg-home-nextgen
cat > /tmp/otbr-edit.py <<'PYEOF'
import sys, pathlib
p = pathlib.Path(sys.argv[1]); s = p.read_text()
anchor = '              - name: OTBR_REST_PORT\n                value: "8081"\n'
assert s.count(anchor) == 1, "OTBR_REST_PORT anchor not found exactly once"
assert 'name: FIREWALL' not in s, "pins already present"
add = (
 "              # v0.4.0 INVERTED these defaults (unset now means OFF; v0.3.0 treated\n"
 "              # unset as ON). Pinned to the v0.3.0 behaviour measured 2026-10-14;\n"
 "              # without them v0.4.0 runs with the ingress filter open, NAT64 off,\n"
 "              # the web UI down and hardware flow control off.\n"
 "              # See plan otbr-0.4.0.\n"
 "              - name: FIREWALL\n                value: \"1\"\n"
 "              - name: NAT64\n                value: \"1\"\n"
 "              - name: FLOW_CONTROL\n                value: \"1\"\n"
 "              - name: OTBR_WEB\n                value: \"1\"\n"
)
p.write_text(s.replace(anchor, anchor + add)); print("edited", p)
PYEOF
python3 /tmp/otbr-edit.py kubernetes/apps/home-automation/otbr/app/helmrelease.yaml
git diff --stat kubernetes/apps/home-automation/otbr/app/helmrelease.yaml    # 1 file, 13 insertions, 0 deletions
printf 'fix(otbr): pin FIREWALL/NAT64/FLOW_CONTROL/OTBR_WEB=1 for v0.4.0 (plan otbr-0.4.0)\n\nv0.4.0 inverted these defaults; #357 landed without the pins, leaving the\ningress filter open, NAT64 off and the web UI down. Restores v0.3.0 behaviour.\n\nCo-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>\n' > /tmp/otbr-msg.txt
git commit --only kubernetes/apps/home-automation/otbr/app/helmrelease.yaml -F /tmp/otbr-msg.txt
git log -1 --format=%s        # MUST be the subject above (shared worktree); amend before push if not
git show --stat HEAD          # exactly 1 file
git push
PIN_SHA=$(git rev-parse HEAD); echo "$PIN_SHA"
```

Flux picks it up from the webhook; no manual reconcile. The Deployment is `Recreate`: expect about 1-2 min
with no BR (socat waits for the RCP, the migration script runs, otbr-agent attaches). The HR has
`upgrade.remediation: rollback, retries 3`; if the pod is not Ready within the timeout helm-controller
rolls back to the previous release (the pin-less v0.4.0). That counts as a FAILED window item: go to 5.

## 4. Verification

Wait for the new pod: `kubectl -n home-automation get pod -l app.kubernetes.io/name=otbr -o wide` must show
one pod < 10 min old on `k8s-nuc14-03`, with a DIFFERENT name than `otbr-b68c767c8-4z4sz`.

**4.1 Rollout landed (floor).** HR `Ready=True`; pod imageID still contains `sha256:790f2183...` (image
unchanged); env on the LIVE pod:
`kubectl get pod -n home-automation -l app.kubernetes.io/name=otbr -o jsonpath='{.items[0].spec.containers[0].env[*].name}'`
contains all four names. FAILS AS: an old pod name or startTime older than the push (rollout-status
old-generation trap), or CrashLoop.

**4.2 CONTENTS: ingress filter and NAT64 are really back on the node** (each number changes from the 2.4
baseline; a pin that did not reach the script leaves the old value):

```bash
kubectl -n home-automation exec deploy/otbr -- sh -c 'echo ingress_drop=$(ip6tables -S OTBR_FORWARD_INGRESS | grep -c "pkt-type unicast -j DROP"); echo ingress_set=$(ip6tables -S OTBR_FORWARD_INGRESS | grep -c match-set); echo masq=$(iptables -t nat -S POSTROUTING | grep -c "mark 0x1001"); echo nat64_disabled=$(ot-ctl nat64 state | grep -ci disabled); echo upstream=$(ot-ctl dns server upstream | head -1); echo flowctl=$(for f in /proc/[0-9]*/cmdline; do tr "\000" " " < $f; echo; done | grep -a "^/usr/sbin/otbr-agent" | grep -c "uart-flow-control"); echo deassert=$(for f in /proc/[0-9]*/cmdline; do tr "\000" " " < $f; echo; done | grep -a "^/usr/sbin/otbr-agent" | grep -c uart-init-deassert)'
```

PASS: `ingress_drop=2`, `ingress_set=2`, `masq=1` (not 2+: leftover duplicates would mean teardown failed),
`nat64_disabled=0`, `upstream=Enabled`, `flowctl=1`, `deassert=0`.
FAILS AS (all measured on the live pod before the fix, 2026-10-23): `ingress_drop=0`, `ingress_set=0`,
`masq=0`, `nat64_disabled=2`, `upstream=Disabled`, `flowctl=0`, `deassert=1`. `grep -ci` is
case-insensitive; an empty `nat64 state` prints `0` too, so also require the two lines to be present:
`ot-ctl nat64 state | grep -c "^PrefixManager\|^Translator"` = 2.

**4.3 CONTENTS: Thread identity survived** (compare to the 2.3 baseline):

```bash
B=/tmp/otbr-0.4.0
kubectl -n home-automation exec deploy/otbr -- ot-ctl dataset active -x | head -1 | shasum -a 256 | cut -c1-64 | diff - $B/dataset.sha && echo DATASET_SAME
kubectl -n home-automation exec deploy/otbr -- sh -c 'ot-ctl ba id; ot-ctl extpanid; ot-ctl networkname; ot-ctl state; ot-ctl neighbor table; ls -la /data/thread'
```

PASS: `DATASET_SAME`; ba id `a46bcba497701adf204feb4fecd663a9` (case-insensitive); ext PAN
`1391992999084adf`; name `MyHome900239170`; state `router` or `leader` (retry up to 3 min: `child`/`detached`
are transient); >= 2 `R` neighbours; `/data/thread` contains `0_124b002d12c333.data` and no `*.backup-*`
file (`0_0-tmp.data` may remain). FAILS AS: changed hash/ba id (migration rewrote identity -> 5.2), `detached`
or 0 neighbours after 3 min, a `.backup-` file.

**4.4 Web UI.** `curl -s -m5 -o /dev/null -w '%{http_code}\n' http://192.168.55.13:8080/` must be `200`
(baseline `000`: refused). FAILS AS: `000` = `OTBR_WEB` did not reach the container env.

**4.5 mDNS advertisement unchanged from before the roll.** Run the same `_meshcop._udp` browse as in 2.6 from
the HA pod (`kubectl -n home-automation exec deploy/home-assistant -c app -- python3 ...zeroconf browse...`);
PASS: same instance count as 2.6 (3 expected) and one instance with server `k8s-nuc14-03-otbr.local.`
(case-insensitive match on `k8s-nuc14-03`); all carry `nn` `MyHome900239170`. FAILS AS: count drops to 2.

**4.6 REST surface HA reads.** `curl -s -m5 http://192.168.55.13:8081/node/state` -> `"router"` (or
`"leader"`); `/node/ba-id` -> `"a46bcba497701adf204feb4fecd663a9"` (HA's otbr config entry is bound to this id).

**4.7 Radio link.** `ot-ctl rcp version` contains `SLZB-06P7`; no `Init() at spinel_driver` failure in
`kubectl logs deploy/otbr | grep -i "spinel_driver\|failed permanently"` (case-insensitive; empty = PASS).
The flow-control pin is the only one that changes the RCP URL: if the agent restarts or `state` flaps after
`uart-flow-control` is active, revert per 5.1 (the previous state was stable with `uart-init-deassert`).

**4.8 Stability over a 10 min soak after Ready.**

```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 19090:9090 >/dev/null 2>&1 & PF=$!; sleep 3
curl -s http://localhost:19090/api/v1/query --data-urlencode 'query=kube_deployment_status_replicas_available{namespace="home-automation",deployment="otbr"}'
curl -s http://localhost:19090/api/v1/query --data-urlencode 'query=sum(increase(kube_pod_container_status_restarts_total{namespace="home-automation",pod=~"otbr-.*"}[10m]))'
kill $PF 2>/dev/null
```

CONTROL: first query must read `1` (EMPTY = FAIL, not a pass); second must read `0` for the NEW pod
(restarts of the old pod inside the 10 min window can make it > 0 right after the roll; use pod name of
the new pod in `pod=` if so). Then re-run 4.2 and 4.3 once at the end of the soak.

## 5. Rollback

### 5.1 Standard (any gate fails, dataset intact)

```bash
cd /Users/mu/code/cberg-home-nextgen
git revert --no-edit <PIN_SHA>
git log -1 --format=%s; git show --stat HEAD     # 1 file, revert subject is yours
git push
```

This returns to the CURRENT state (v0.4.0 without pins: Thread up, ingress filter open, NAT64 and web UI
off). Confirm: new pod, 4.3 identity gate passes, `ingress_drop=0` again. To go further back to v0.3.0,
additionally `git revert 668f56c9` (the #357 squash) in a second commit; then `ot-ctl version` shows
`thread-reference-20230706`. Known artefact: v0.3.0's teardown does not know the v0.4.0
`OTBR_FORWARD_NAT64` chain, so it can leave a harmless leftover chain until the node reboots. Do not
hand-edit node iptables.

### 5.2 Dataset lost or changed (gate 4.3 failed)

The Thread network itself lives on the Apple and IKEA Border Routers, so a lost dataset here detaches only
our BR. Restore in order:
1. **From HA:** Settings -> Devices & Services -> Thread -> our OTBR -> use the preferred network (same ext
   PAN). PUTs the dataset via the 8081 REST API.
2. **From the captured TLV** (operator-present, via cberg-agent):
   `kubectl -n home-automation exec deploy/otbr -- ot-ctl dataset set active "$(cat /tmp/otbr-0.4.0/dataset.hex)"`
   then `ot-ctl ifconfig up; ot-ctl thread start`; re-run 4.3.
3. **Border-agent id changed, dataset same:** copy the captured file back
   (`kubectl exec -i deploy/otbr -- sh -c 'cat > /data/thread/0_124b002d12c333.data' < /tmp/otbr-0.4.0/0_124b002d12c333.data`),
   confirm `sha256sum` equals the baseline, restart the pod once via cberg-agent.
4. **Floor:** restore volume `pvc-da17b5c6-0d8c-42cf-9a25-bc444ac9a71d` from the nightly Longhorn backup
   (2.2), per `docs/sops/backup.md`; operator-present.

### 5.3 Cleanup (success or rollback)

`rm -rf /tmp/otbr-0.4.0 /tmp/otbr-edit.py /tmp/otbr-msg.txt` after the soak. The baseline dir holds the
Thread network key.

## 6. Interference notes

- **Node-scoped, privileged, hostNetwork.** The pod rewrites `k8s-nuc14-03`'s iptables on start and stop. Do
  not co-run with anything that rolls that node or touches host networking (Talos, Cilium,
  `multus-macvlan-foundation`). `matter-server` (hostNetwork, same node) shares 5353 and is not restarted.
- **HA.** Do not share a slot with `home-assistant-2026.10.2`: its restart flaps the otbr/thread integrations
  and gate 4.5 uses the HA pod as its instrument.
- **Same HR, other writers.** `flux-oci-chart-sources`, `helm-drift-detection`, `flux-reconciler-impersonation`
  touch `helmrelease/otbr` or its applier: separate windows so a failure is attributable. Reciprocal
  `conflicts_with` entries are not yet on those plans (this revision may only write this file).
- **Prometheus.** Gate 4.8 reads kube-state-metrics; no `kube-prometheus-stack` plan is open (2026-10-23). If
  one is added for the same night, serialize it.
- **Human-gated, no reboot.** About 2 min BR-only outage, 0 HA Matter nodes affected (HA's matter-server held
  0 nodes on 2026-10-14). A nightly slot with a prior GO is fine.
- **Repo correction owed.** The first version of this plan and PR #357 treated the bump and the pins as one
  change, but Renovate merges only the tag. Any component whose upstream inverts defaults needs a deny
  rule (or a compensating pin merged FIRST) so the auto-update lane cannot land the bump alone.

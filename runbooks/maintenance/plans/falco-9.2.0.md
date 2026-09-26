---
plan_id: falco-9.2.0
component: falco
pr: null                              # no Renovate PR. Reached the PLAN lane via coverage.py's
                                      # direct-bump path: "G3 could not verify the release notes —
                                      # an unverified bump needs an assessed window" (nightly
                                      # window 2026-09-25, Step 0.5). This plan IS that assessment.
kind: chart
current: "9.1.0"                      # live: hr/falco 9.1.0, helm rev v28, image falco:0.44.1,
                                      # falcoctl:0.13.0, metacollector pin 0.1.3 (measured
                                      # 2026-09-25 01:54Z)
target: "9.2.0"                       # appVersion 0.45.0 (Falco released 2026-09-21T12:23Z,
                                      # "Latest", not a pre-release); chart pulled + rendered
update_type: minor
risk: medium                          # Engine minor with a declared BREAKING change in rule
                                      # condition evaluation (engine 0.62.0 -> 0.63.0, §1.2) on
                                      # the node-level security sensor, plus two chart-template
                                      # changes to the host mounts (§1.3). Our custom rules were
                                      # read against the breaking change and are not in its
                                      # scope, and the failure mode is bounded (one node blind at
                                      # a time, auto-rollback) — hence not high. But a 4-day-old
                                      # engine release on the cluster's only syscall detector is
                                      # not low either.
est_duration_min: 40                  # pre-change positive control 5, edit+push 3, rollout
                                      # ~10 (maxUnavailable 1, 3 nodes, falcoctl init pulls
                                      # rules+plugins per pod), verification 12, buffer 10
needs_reboot: false                   # modern_ebpf is CO-RE and ships inside the falco binary;
                                      # no kmod, no driver-loader init container, no node reboot
touches:
  namespaces: [security]
  resources:
    - helmrelease/falco
    - daemonset/falco
    - deployment/falco-k8s-metacollector
    - configmap/falco
    - configmap/falco-falcoctl
    - configmap/falco-rules
    - "docker.io/falcosecurity/falco"
    - "docker.io/falcosecurity/falcoctl"
    - "docker.io/falcosecurity/k8s-metacollector"
  shared:
    - wazuh-falco-feed                # falco.log on the host is the ONLY source of syscall
                                      # alerts for Wazuh (rule tree 100400-100415). While a
                                      # node's falco pod is replaced, that node is unmonitored.
    - containerd-socket               # chart 9.2.0 now bind-mounts the host DIRECTORIES
                                      # /run/containerd and /var/run (was: the socket files)
                                      # into the privileged falco container (§1.3)
depends_on: []
conflicts_with:
  - flux-oci-chart-sources            # moves falco's chart source to OCI
  - helm-drift-detection              # adds a spec field to hr/falco
  - talos-1.14.1                      # A node roll changes the KERNEL that modern_ebpf attaches
                                      # to and restarts every falco pod three times. Running both
                                      # in one window makes a detection gap unattributable
                                      # (engine vs kernel) and invalidates the §2 kernel premise.
                                      # Serialize: either order, separate windows.
  - kube-prometheus-stack-91.4.1      # §4 CONTROL lines read kube-state-metrics through THIS
                                      # Prometheus; a same-night Prometheus restart reads as
                                      # "no data" (rule 4, plan-authoring rules 2026-09-15).
exclusive: false
security_ref: F-01f4a388              # the metacollector image finding that step 3.2 answers;
                                      # detail stays on the DB record
capability_change: false              # no user-visible behaviour; detection semantics shift only
                                      # for byte-level string matching our rules do not use (§1.2)
rollback_class: git-revert            # stateless: every falco volume is emptyDir/hostPath/
                                      # ConfigMap; no schema, no PVC, nothing forward-only
finding_refs: [F-8ee4be16, F-01f4a388]
                                      # F-8ee4be16 = version finding "falco: chart 9.1.0 -> 9.2.0";
                                      # F-01f4a388 = metacollector image finding (answered by the
                                      # 0.1.3 -> 0.1.4 pin bump in step 3.2)
status: vetted   # 2026-09-26 plan-reviewer needs-fix -> A-H applied (detect.sh script file, wazuh >=3 hits all 100402, k8smeta RPC noise filtered in 4.1, shared-index-safe revert, 9m rollout waits); order: last in the serial set, after kps sign-off
window: "now:2026-09-26"   # ON-DEMAND NOW run 2026-09-26 (run-now.py stamp; was None)
premises:
  - id: chart-still-9.1.0
    why: >-
      `current:` claims chart 9.1.0. If the HelmRelease already moved (a later
      direct-bump, a manual edit), every baseline and the rollback target in this
      plan are wrong. Prints the actual version on failure.
    run: kubectl get -n security hr falco -o jsonpath='{.spec.chart.spec.version}'
    expect_exact: "9.1.0"
  - id: engine-still-0.44.1
    why: >-
      The breaking-change analysis in §1.2 is 0.44.1 -> 0.45.0. A different live
      engine means the delta was not assessed.
    run: kubectl get -n security ds falco -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: "docker.io/falcosecurity/falco:0.44.1"
  - id: sensor-healthy-before-we-touch-it
    why: >-
      Never roll the node sensor while it is already degraded — a pre-existing
      not-ready pod would be misattributed to the bump and burn the window on a
      needless revert. Measured 3/3 on 2026-09-25.
    run: kubectl get -n security ds falco -o jsonpath='{.status.numberReady}/{.status.desiredNumberScheduled}'
    expect_exact: "3/3"
  - id: no-falco-restarts-baseline
    why: >-
      §4.2 asserts zero restarts after the roll. That gate is only meaningful if the
      baseline is also zero (six containers = falco + falcoctl-artifact-follow on
      3 nodes). Measured "0 0 0 0 0 0" on 2026-09-25.
    run: kubectl get -n security pods -l app.kubernetes.io/name=falco -o jsonpath='{.items[*].status.containerStatuses[*].restartCount}'
    expect_matches: '^(0 ){5}0$'
  - id: driver-is-modern-ebpf
    why: >-
      needs_reboot:false and the "no driver-loader" reasoning in §1.4 hold only for
      the CO-RE modern_ebpf driver. A switch to kmod/ebpf would add a
      driver-loader init container and a kernel-module build.
    run: >-
      kubectl get -n security cm falco -o jsonpath='{.data.falco\.yaml}' | grep -c 'kind: modern_ebpf'
    expect_exact: "1"
  - id: kernel-unchanged-since-assessment
    why: >-
      The modern_ebpf attach and the §2.3 positive control were assessed on Talos
      kernel 6.18.48 on all three nodes. If a Talos roll landed first, re-run §2.3
      and re-check the driver compatibility before proceeding (see conflicts_with).
    run: kubectl get nodes -o jsonpath='{.items[*].status.nodeInfo.kernelVersion}'
    expect_exact: "6.18.48-talos 6.18.48-talos 6.18.48-talos"
  - id: trigger-target-present
    why: >-
      The §4 synthetic detection runs `cat /etc/shadow` inside the falco-log-rotate
      busybox pod on each node. If that DaemonSet is not 3/3, a node has no trigger
      target and its detection gate cannot be exercised.
    run: kubectl get -n security ds falco-log-rotate -o jsonpath='{.status.numberReady}'
    expect_exact: "3"
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/falco.md                # rule-override mechanism + §6 verification tests
  - docs/sops/verification-contents-not-shape.md
generated: "2026-09-25"
---

# falco chart 9.1.0 -> 9.2.0 (Falco engine 0.44.1 -> 0.45.0)

## 1. Summary & why held

### 1.1 What changes

Measured by `helm pull` of both charts and `helm template` of each with the live
`spec.values` (yq-extracted from `helmrelease.yaml`), then `diff`:

| Artifact | 9.1.0 (live) | 9.2.0 |
|---|---|---|
| falco image | `falco:0.44.1` | `falco:0.45.0` |
| falcoctl (init + follow sidecar) | `falcoctl:0.13.0` | `falcoctl:0.14.2` |
| container plugin (falcoctl install ref) | `0.7.1` | `0.7.4` |
| k8smeta plugin | `0.4.1` | `0.4.2` |
| k8s-metacollector subchart | `0.1.10` (appVersion 0.1.1) | `0.3.2` (appVersion 0.1.4) |
| rules artifact followed | `falco-rules:5` | `falco-rules:5` (unchanged) |
| rendered `falco.yaml` (configmap) | — | **unchanged** except labels |

The metacollector subchart's rendered Deployment/Service/RBAC differ only in the
`helm.sh/chart` / `app.kubernetes.io/version` labels; the selector is unchanged,
so no immutable-selector delete/recreate is needed.

**Pin interaction:** our values pin `k8s-metacollector.image.tag: "0.1.3"`. Under
9.2.0 the subchart's own default is `0.1.4`, so leaving the pin would make it a
*downgrade* relative to the chart. Step 3.2 moves the pin to `0.1.4`
(upstream v0.1.4 release notes: dependency and toolchain bumps only, no
behaviour change). This also answers F-01f4a388 — see the DB record, not this file.
The falcoctl move to 0.14.2 is also the newer tag referenced by F-2dcb2380
(accepted under AR-077; cited, not claimed).

### 1.2 Why it is not auto-safe — the upstream breaking change

Falco 0.45.0 release notes (github.com/falcosecurity/falco/releases/tag/0.45.0),
"Breaking Changes":

> feat(userspace)!: evaluate rule conditions on raw field bytes (invalid and
> non-printable UTF-8 sequences are now matchable with string operators, single
> bytes with the new `\xHH` escape sequence), let `regex` operate on sanitized
> input, and escape non-printable characters / replace invalid UTF-8 sequences at
> output encoding time; `FALCO_ENGINE_VERSION` bumped from `0.62.0` to `0.63.0`;
> rules that matched the replacement character with non-regex operators must be
> reviewed [#3942]

**Assessment against our rules** (`spec.values.customRules`): both override files
(`apt-dpkg-noise.yaml`, `k8s-api-noise.yaml`) use only `=`, `in`, `startswith`
against plain-ASCII literals (process names, container names, image
repositories, paths). None uses `regex`, none matches U+FFFD or non-printable
bytes. The change is therefore out of scope for our overrides. The upstream
ruleset is followed from `falco-rules:5` by falcoctl regardless of chart version
(it already refreshed on 2026-09-08 per the follow sidecar log), and 0.45.0
itself was cut against rules 5.2.0 (#3973) — the same major we follow.

Also relevant from the same notes:
- `container_engines` key now logs a schema warning — **we do not set it**
  (`grep -n container_engines` on the 9.2.0 render: no hit).
- `--validate` now suggests `--dry-run` for config files. We do not run it; noted
  because an exit-code-based validate gate would be the wrong instrument anyway.

The residual risk is the one that cannot be read off the notes: a 4-day-old
engine release (published 2026-09-21) whose override-append path could reject
our ruleset. Falco **crash-loops on a rule it cannot load** (`docs/sops/falco.md`
§2), which is why §4.1 reads every pod's log for `[error]` and §4.3 proves an
event is actually detected rather than trusting Ready.

### 1.3 Chart-template changes that alter what lands on the node

1. **Socket mounts become directory mounts** (upstream #3978, "so Falco keeps
   working after a container runtime restart"). Rendered diff, falco container:
   `/host/run/containerd/containerd.sock` -> `/host/run/containerd`, and likewise
   for the other five engine paths, including `/var/run/docker.sock` -> host
   **`/var/run`** mounted at `/host/var/run` (no `readOnly`). The hostPath volumes
   carry no `type`, same as today. Measured in the live pod: the non-existent
   engine paths (`podman.sock`, `crio`, `k3s`, `host-containerd`) were already
   auto-created on the host as empty directories by the 9.1.0 file mounts, so the
   new directory hostPaths all exist. Net effect: the privileged falco container
   now sees the host's whole `/var/run`. It is already `privileged: true` with
   `/host/proc` (AR-026), so this widens nothing that privilege did not already
   grant — but the window agent should know the host view changed.
2. **`/etc/falco/config.d` is always an emptyDir** (upstream #3984) — prevents the
   image's own container-plugin snippet from double-loading the plugin. With
   `driverLoader` disabled (modern_ebpf) this volume did not exist before; it is
   new and harmless.
3. **falcoctl config volume** is now conditional on install/follow being enabled
   — both are enabled here, so it still renders (verified in the diff).
4. The DaemonSet gains an optional `revisionHistoryLimit` (unset here, no render
   change).

### 1.4 Driver / Talos

Release badge: libs 0.26.0, driver `11.0.0+driver`. We run `driver.kind:
modern_ebpf` (CO-RE, compiled into the falco binary, no kernel module, no
driver-loader init container — the 9.2.0 render has none). Nodes run Talos
v1.13.10, kernel 6.18.48-talos, well above the modern_ebpf floor. No reboot, no
Talos change.

## 2. Pre-checks

Run from the repo root on the Mac mini (zsh).

2.1 Premises (fail-closed, read-only):

```bash
.venv/bin/python3 runbooks/plan-premises.py falco-9.2.0
```

PASS = all seven premises pass. Any failure: stop, do not edit.

2.2 No in-flight reconcile, HR clean:

```bash
flux -n security get hr falco
kubectl -n security get ds falco falco-log-rotate wazuh-agent
```

PASS = `falco  9.1.0  False  True  Helm upgrade succeeded ... falco@9.1.0`; all
three DaemonSets 3/3.

2.3 **Positive control on 9.1.0 — prove the §4.3 detection gate can PASS before
the change** (and record its timestamp so the sweep does not treat the synthetic
events as an incident). The trigger is a `cat /etc/shadow` in the busybox
`rotate` container of each node's `falco-log-rotate` pod: stock rule
`Read sensitive file untrusted` (priority Warning -> Wazuh rule 100402, level 6).
`cat` is not in any Wazuh suppression (100410 matches `wazuh-*`, 100412 matches
`pg_isready`) nor in our Falco overrides. `/etc/shadow` exists in that image
(`-rw------- root`, measured).

Save the checker once (it is also used in §4.3):

```bash
mkdir -p /tmp/falco-9.2.0 && cat > /tmp/falco-9.2.0/check.py <<'EOF'
import sys, json, os
t0 = os.environ["T0"]; want_rule = os.environ.get("RULE", "Read sensitive file untrusted")
want_ctr = os.environ.get("CTR", "rotate"); node = os.environ.get("NODE", "?")
hits = 0; enriched = 0
for line in sys.stdin:
    try: e = json.loads(line)
    except ValueError: continue
    if e.get("rule") != want_rule or e.get("time", "") < t0: continue
    f = e.get("output_fields", {})
    if f.get("container.name") != want_ctr: continue
    hits += 1
    if f.get("k8s.ns.name") and f.get("k8s.pod.name") and f.get("container.image.repository"):
        enriched += 1
print(f"{node}: hits={hits} enriched={enriched} -> " + ("PASS" if hits > 0 and enriched == hits else "FAIL"))
EOF
cat > /tmp/falco-9.2.0/wz.py <<'EOF'
import sys, json, os
t0 = os.environ["T0"]; want_rule = os.environ.get("RULE", "Read sensitive file untrusted")
want_ctr = os.environ.get("CTR", "rotate")
hits = 0; ids = set()
for line in sys.stdin:
    try: e = json.loads(line)
    except ValueError: continue
    d = e.get("data") or {}
    if d.get("rule") != want_rule or e.get("timestamp", "") < t0: continue
    f = d.get("output_fields") or {}
    if (f.get("container") or {}).get("name") != want_ctr: continue
    hits += 1; ids.add(e["rule"]["id"])
print(f"wazuh: hits={hits} rule_ids={sorted(ids)} -> " + ("PASS" if hits >= 3 and ids == {"100402"} else "FAIL"))
EOF
```

Then save the trigger + read as a SCRIPT FILE (reused verbatim in §4.3 and §5;
not a shell function — the window agent's Bash calls share no shell state):

```bash
cat > /tmp/falco-9.2.0/detect.sh <<'EOF'
#!/bin/bash
set -u
T0=$(date -u +%Y-%m-%dT%H:%M:%S)
echo "T0=$T0 (record in the window log: synthetic falco trigger)"
echo "$T0" >> /tmp/falco-9.2.0/t0.log
for node in k8s-nuc14-01 k8s-nuc14-02 k8s-nuc14-03; do
  R=$(kubectl -n security get pods -l app.kubernetes.io/name=falco-log-rotate --field-selector spec.nodeName=$node -o jsonpath='{.items[0].metadata.name}')
  kubectl -n security exec "$R" -c rotate -- cat /etc/shadow >/dev/null
done
sleep 20
for node in k8s-nuc14-01 k8s-nuc14-02 k8s-nuc14-03; do
  F=$(kubectl -n security get pods -l app.kubernetes.io/name=falco --field-selector spec.nodeName=$node -o jsonpath='{.items[0].metadata.name}')
  kubectl -n security exec "$F" -c falco -- grep -F '"rule":"Read sensitive file untrusted"' /var/run/falco/falco.log \
    | T0=$T0 NODE=$node python3 /tmp/falco-9.2.0/check.py
done
sleep 30
kubectl -n security exec wazuh-manager-master-0 -- grep -F 'falco.log' /var/ossec/logs/alerts/alerts.json \
  | T0=$T0 python3 /tmp/falco-9.2.0/wz.py
EOF
bash /tmp/falco-9.2.0/detect.sh
```

PASS = three `k8s-nuc14-0N: hits>=1 enriched==hits -> PASS` lines and
`wazuh: hits>=3 rule_ids=['100402'] -> PASS`. If this FAILS on 9.1.0, the gate is
broken, not falco — stop and fix the gate before bumping anything (a gate that
cannot pass today cannot tell you anything tomorrow).

How the gate fails (measured 2026-09-25 while authoring, against real
`falco.log` on k8s-nuc14-02): the reader printed `hits=1355 enriched=1355 ->
PASS` for `CTR=postgresql` over natural traffic; `-> FAIL` with `CTR=rotate`
(no event for that container yet) and `-> FAIL` with a future `T0`. The Wazuh
reader printed `PASS` for a real container/rule pair from today's
`alerts.json` and `FAIL` for `CTR=rotate`. So an empty log, a dead sensor, a
missing enrichment (container plugin not reaching containerd — exactly what the
§1.3 mount change could break), or a broken file->Wazuh hand-off each print FAIL.

2.4 Critical-tier baseline for §4.4 (advisory): take the count twice, 10 minutes
apart, on k8s-nuc14-02 and record the delta.

```bash
F=$(kubectl -n security get pods -l app.kubernetes.io/name=falco --field-selector spec.nodeName=k8s-nuc14-02 -o jsonpath='{.items[0].metadata.name}')
kubectl -n security exec "$F" -c falco -- grep -c '"priority":"Critical"' /var/run/falco/falco.log
```

## 3. Steps

3.1 Edit the chart version and the metacollector pin (BSD sed; dry-tested on a
scratch copy on macOS 2026-09-25 — resulting diff pasted below):

```bash
cd /Users/mu/code/cberg-home-nextgen
sed -i '' \
  -e 's/^      version: 9\.1\.0$/      version: 9.2.0/' \
  -e 's/^        tag: "0\.1\.3"$/        tag: "0.1.4"/' \
  kubernetes/apps/security/falco/app/helmrelease.yaml
git diff kubernetes/apps/security/falco/app/helmrelease.yaml
```

Expected diff (exactly two changed lines):

```
-      version: 9.1.0
+      version: 9.2.0
-        tag: "0.1.3"
+        tag: "0.1.4"
```

3.2 Render-verify the pin before committing (the pin comment in the helmrelease
warns that a pin at the wrong path no-ops silently while the HR reports Ready):

```bash
helm repo add falcosecurity https://falcosecurity.github.io/charts >/dev/null 2>&1; helm repo update falcosecurity >/dev/null
yq '.spec.values' kubernetes/apps/security/falco/app/helmrelease.yaml > /tmp/falco-9.2.0/values.yaml
helm template falco falcosecurity/falco --version 9.2.0 -n security -f /tmp/falco-9.2.0/values.yaml | grep -n 'image:'
```

PASS = exactly these four images: `falco:0.45.0`, `falcoctl:0.14.2` (twice),
`k8s-metacollector:0.1.4`. Any other metacollector tag: the pin path is wrong,
stop.

3.3 Commit and push (shared worktree rules):

```bash
git commit --only kubernetes/apps/security/falco/app/helmrelease.yaml \
  -m "feat(falco): chart 9.1.0 -> 9.2.0 (falco 0.45.0), metacollector pin 0.1.3 -> 0.1.4" \
  -m "Plan: runbooks/maintenance/plans/falco-9.2.0.md"
git log -1 --format=%s        # must be the subject above; amend before push if not
git show --stat HEAD          # exactly one file
git push
```

No manual `flux reconcile` — the webhook drives it (SOP). Flux upgrades the
release with `timeout: 15m`; the DaemonSet rolls one node at a time
(`maxUnavailable: 1, maxSurge: 0`, measured).

3.4 Watch the roll, and **cut it short on the first bad pod** (see §5 — do not
let Flux's remediation loop run):

```bash
kubectl -n security rollout status ds/falco --timeout=9m   # agent Bash caps a call at 10 min; if it times out while pods still progress, run it once more
kubectl -n security get pods -l app.kubernetes.io/name=falco -o wide
```

If the first replaced pod is not `2/2 Running` within 5 minutes, go straight to
§5.

## 4. Verification

4.1 **Ruleset loaded cleanly on the new engine, every node** (the crash-loop
failure mode from `docs/sops/falco.md`):

```bash
for p in $(kubectl -n security get pods -l app.kubernetes.io/name=falco -o name); do
  echo "== $p"; kubectl -n security logs "$p" -c falco --tail=300 | grep -iE '\[error\]|schema validation|could not load|LOAD_ERR' | grep -vcF '[k8smeta] error during the RPC call'
done
```

PASS = `0` on all three pods. Case-insensitive on purpose (upstream mixes
`[error]` / `Error` / `LOAD_ERR_*`). k8smeta `error during the RPC call` lines are excluded on purpose: every falco
pod logs them when the metacollector pod is replaced (4/7/4 lines on the live
9.1.0 pods, 2026-09-26), and this upgrade replaces the metacollector while the
DaemonSet is still rolling, so an unfiltered count FAILs a healthy roll.
Filtered, the live 9.1.0 pods read `0 0 0`; the identical chain reads `1` on a
replayed `LOAD_ERR_COMPILE_CONDITION` line, so a rules-load failure still FAILs.
Persistent k8smeta loss is caught by §4.3's `enriched == hits`, not here. A rule the engine rejects prints an error
and the container restarts — caught here and in 4.2.

4.2 Shape floor — HR on the new revision, DS fully rolled, no restarts:

```bash
flux -n security get hr falco
kubectl -n security get ds falco -o jsonpath='{.status.numberReady}/{.status.desiredNumberScheduled} updated={.status.updatedNumberScheduled}{"\n"}'
kubectl -n security get ds falco -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'
kubectl -n security get deploy falco-k8s-metacollector -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'
kubectl -n security get pods -l app.kubernetes.io/name=falco -o jsonpath='{.items[*].status.containerStatuses[*].restartCount}{"\n"}'
```

PASS = HR Ready with `falco@9.2.0`; `3/3 updated=3`;
`docker.io/falcosecurity/falco:0.45.0`;
`docker.io/falcosecurity/k8s-metacollector:0.1.4`; `0 0 0 0 0 0`.

4.3 **CONTENTS ASSERTION: every node's falco actually DETECTS a syscall event,
enriches it with container + Kubernetes metadata, writes it to the host sink,
and Wazuh ingests it** — measured by `/tmp/falco-9.2.0/detect.sh` (§2.3) run after the roll,
compared to the §2.3 baseline on 9.1.0.

```bash
bash /tmp/falco-9.2.0/detect.sh
```

PASS = identical shape to the §2.3 baseline: three per-node `PASS` lines with
`enriched == hits`, and `wazuh: ... rule_ids=['100402'] -> PASS`.

What each FAIL means:
- `hits=0` on a node — the engine is up but not detecting (driver attach failed,
  rule not loaded, or file output broken). This is the failure Ready cannot see.
- `hits>0 enriched<hits` — the container plugin lost containerd (the §1.3
  socket->directory mount change) or k8smeta lost the metacollector. Events
  would arrive in Wazuh with empty container/pod fields, which silently breaks
  every scoped exclusion in our overrides and the Wazuh 1004xx suppressions.
- falco side PASS, wazuh FAIL — the host-file hand-off to the wazuh-agent broke
  (the `/var/run/falco` hostPath mount is unchanged by the chart, so this would
  be unexpected; check the agent before blaming falco).

4.4 Existing-overrides still in force (an override-append regression would
surface as the scoped noise returning): the Critical tier should not jump.

```bash
F=$(kubectl -n security get pods -l app.kubernetes.io/name=falco --field-selector spec.nodeName=k8s-nuc14-02 -o jsonpath='{.items[0].metadata.name}')
kubectl -n security exec "$F" -c falco -- grep -c '"priority":"Critical"' /var/run/falco/falco.log
```

Read after >=10 minutes on the new pod (fresh pods start with the shared host
file, so compare the delta over that window against the same 10-minute delta
taken in §2 on 9.1.0). A multi-fold jump means an appended exclusion stopped
matching — revert (§5) and investigate with `docs/sops/falco.md` §8. This is
advisory, not a hard gate: Critical volume is workload-driven.

CONTROL: metric kube_daemonset_status_number_ready — `{namespace="security",daemonset="falco"}` must read 3 after the roll (measured 3 on 2026-09-25; not-ready pods drop it).
CONTROL: metric kube_daemonset_status_updated_number_scheduled — `{namespace="security",daemonset="falco"}` must read 3 (a stalled roll stays below 3).
CONTROL: metric kube_pod_container_status_restarts_total — `{namespace="security",container="falco"}` must not increase across the window (baseline 0 on all three series).

The primary instrument is not Prometheus: falco's own ServiceMonitor is off
(`serviceMonitor.create: false`), so there is no falco metric to read. The
detection gate is `falco.log` + Wazuh `alerts.json`, read directly in 4.3.

## 5. Rollback

Falco holds no persistent state (emptyDir / ConfigMap / hostPath only), so a
revert fully restores it.

**Do not wait for Flux's remediation loop.** `upgrade.remediation: {strategy:
rollback, retries: 3}` with `timeout: 15m` means a crash-looping 0.45.0 is
retried up to three more times after the first rollback — up to about an hour
of one node at a time running unmonitored. On the first failed gate, revert in
git instead:

```bash
cd /Users/mu/code/cberg-home-nextgen
git log -1 --format=%H --grep='^feat(falco): chart 9\.1\.0 -> 9\.2\.0' -- kubernetes/apps/security/falco/app/helmrelease.yaml > /tmp/falco-9.2.0/commit.sha
cat /tmp/falco-9.2.0/commit.sha        # exactly one SHA; empty = STOP
git revert --no-commit "$(cat /tmp/falco-9.2.0/commit.sha)"   # plain `git revert` refuses while the shared index holds foreign staged files
git commit --only kubernetes/apps/security/falco/app/helmrelease.yaml \
  -m 'Revert "feat(falco): chart 9.1.0 -> 9.2.0 (falco 0.45.0), metacollector pin 0.1.3 -> 0.1.4"' \
  -m "Plan: runbooks/maintenance/plans/falco-9.2.0.md §5"
git log -1 --format=%s                 # "Revert \"feat(falco): chart 9.1.0 -> 9.2.0 ...\""
git show --stat HEAD                   # only helmrelease.yaml
git push                               # rejected? git pull --rebase, then push
```

Confirm the cluster is back:

```bash
flux -n security get hr falco          # Ready, falco@9.1.0
kubectl -n security rollout status ds/falco --timeout=9m   # agent Bash caps a call at 10 min; if it times out while pods still progress, run it once more
kubectl -n security get ds falco -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'   # falco:0.44.1
kubectl -n security get deploy falco-k8s-metacollector -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'   # k8s-metacollector:0.1.3
bash /tmp/falco-9.2.0/detect.sh        # must PASS on all three nodes + wazuh, as in §2.3
```

If Flux's own remediation already rolled back to rev v28 before the revert
lands, the revert is still required: otherwise the next reconcile retries 9.2.0.
`helm -n security history falco` shows the rollback revisions for the window log.

Note on the host directories: 9.1.0 file-mounts `/run/containerd/containerd.sock`
etc. again after rollback; the paths all exist on the hosts (measured), so the
downgrade mounts succeed.

## 6. Interference notes

- **Detection gap is per node, sequential.** During the roll exactly one node is
  without syscall monitoring at a time (~1-3 min each). Nothing else in the window
  should be relying on Falco/Wazuh alerts during those minutes.
- **Synthetic SIEM events.** §2.3 and §4.3 each produce three level-6 Wazuh
  alerts (rule 100402, `Read sensitive file untrusted`, container `rotate`,
  process `cat`, file `/etc/shadow`). Record both `T0` values in the window log
  so a sweep or the security-agent does not triage them as an intrusion. Do not
  add a suppression for them — they are the test.
- **talos-1.14.1** (conflicts_with): a kernel change under modern_ebpf plus three
  node reboots must not share this window — the §4.3 gate could not attribute a
  failure.
- **kube-prometheus-stack-91.4.1** (conflicts_with): §4 CONTROL lines read
  kube-state-metrics through that Prometheus.
- **Wazuh 4.14.7 -> 4.14.8 (cb4fe2ff) and agent client_buffer change (44584b1b)
  landed 2026-09-25 evening, AFTER the §2.3 reader demonstration.** Live
  alerts.json on 2026-09-26 still shows nested `data.output_fields.container.name`
  and Warning -> 100402, but §2.3's pre-change run is the re-demonstration and is
  mandatory: a Wazuh-leg FAIL there stops the plan before any edit.
- **wazuh-agent / wazuh-manager** are not touched, but §4.3 reads the manager's
  `alerts.json`. Any same-window change to the Wazuh ruleset (the
  `unifi-decoder` ConfigMap holds rules 100400-100415) would confound the Wazuh
  leg of the gate; none is open at authoring time (`wazuh-2xx-edge-coverage`
  touches `network`/`kube-system` only).
- **falco-log-rotate** truncates `falco.log` at 64 MiB. A truncation between
  trigger and read would drop the synthetic line; if a single node reads
  `hits=0` while the others PASS, re-run `bash /tmp/falco-9.2.0/detect.sh` once before declaring
  failure (check `wc -c /var/run/falco/falco.log` for a reset).
- **Helm comments** in `helmrelease.yaml` still say "verified by helm template
  against falco 9.1.0 ... with pin -> 0.1.3" and "Falco 0.44.0's built-in
  exclusions". They are historical notes, not config; §3.2 is the fresh
  verification. The executor may update them in the same commit, but it is not
  required.

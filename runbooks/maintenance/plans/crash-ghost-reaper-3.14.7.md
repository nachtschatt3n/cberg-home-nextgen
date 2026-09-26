---
plan_id: crash-ghost-reaper-3.14.7
component: crash-ghost-reaper
pr: null                              # no Renovate PR: this is an inline CronJob image with no
                                      # Renovate manager hit; coverage.py (no-PR direct-bump lane)
                                      # routed it to needs_plan on 2026-09-25 with reason
                                      # "G3 could not verify the release notes".
kind: image
current: "3.12-alpine"                # FLOATING tag. Live CronJob spec re-verified 2026-09-25 01:55Z.
                                      # Running pods resolve it to python@sha256:236173eb… (the node's
                                      # cached copy under imagePullPolicy IfNotPresent), while Docker
                                      # Hub's 3.12-alpine now points at sha256:4c47124a… — so the float
                                      # is already stale per node. Pinning is a side benefit.
target: "3.14.7-alpine"               # Docker Hub: pushed 2026-09-21T17:08:45Z, index digest
                                      # sha256:9e9fde4d32eedce0b661d9ab91e826b62dddf28e928c230ec55f1866cac66b01
                                      # (== 3.14.7-alpine3.24).
update_type: minor                    # CPython 3.12 -> 3.14: two feature releases. Semver-minor, but
                                      # 3.13 changed an ssl default this script depends on (§1.2).
risk: low                             # stdlib-only script; the one real hazard (3.13 VERIFY_X509_STRICT
                                      # against the Talos apiserver cert) was MEASURED passing on all
                                      # three apiservers with 3.13.14 and 3.14.6 (§1.3). Stateless
                                      # CronJob, git-revert rollback, next run 15 min later.
est_duration_min: 30                  # commit+push 3, Flux apply <=5, wait for next */15 run <=15,
                                      # verify 3, Prometheus metric settle ~2
needs_reboot: false
touches:
  namespaces: [kube-system]
  resources:
    - cronjob/crash-ghost-reaper
    - kustomization/crash-ghost-reaper   # Flux Kustomization, ns kube-system
    - "docker.io/library/python:3.14.7-alpine"
  shared: []                          # The reaper is a leaf: nothing depends on it, and it holds no
                                      # state. It READS the apiserver (one pod LIST per 15 min) and
                                      # can DELETE pods cluster-wide, but only node-loss ghosts
                                      # (signature unchanged by this plan — the ConfigMap is not
                                      # edited). A failure mode here is "reaper stops running",
                                      # which perturbs nothing shared until the next ungraceful
                                      # node reboot. See §6.
depends_on: []
conflicts_with:
  - kube-prometheus-stack-91.4.1      # §4 gate B reads kube-state-metrics series from THIS Prometheus;
                                      # a same-night Prometheus restart reads as "no data" and would
                                      # look like a reaper regression. Declared one-sided; the
                                      # scheduler honours conflicts_with symmetrically.
exclusive: false
security_ref: null
capability_change: false              # same script, same RBAC, same schedule; only the interpreter moves
rollback_class: git-revert            # no data, no migration, no forward-only step
finding_refs: [F-cdcbe7ea]            # version finding "crash-ghost-reaper: image docker.io/library/python
                                      # 3.12-alpine → 3.14.7-alpine (minor)". The sibling finding
                                      # F-c9568174 (elasticsearch-obs-recovery, same image bump) is NOT
                                      # answered by this plan — different script, different surface.
status: vetted   # 2026-09-26 plan-reviewer ready-for-go (0 blocking); Gate B made enforcing, SOP edit made concrete
window: "now:2026-09-26"   # ON-DEMAND NOW run 2026-09-26 (run-now.py stamp; was None)
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/crash-ghost-reaper.md
  - docs/sops/inline-image-tag-coverage.md
generated: "2026-09-25"
premises:
  - id: live-image-is-still-3.12-alpine
    why: >-
      current is the floating 3.12-alpine tag on the CronJob pod template. If
      someone already moved it, the diff in §3 does not apply and the rollback
      baseline is wrong.
    run: "kubectl get cronjob -n kube-system crash-ghost-reaper -o jsonpath='{.spec.jobTemplate.spec.template.spec.containers[0].image}'"
    expect_exact: docker.io/library/python:3.12-alpine
  - id: script-is-still-stdlib-only
    why: >-
      The compatibility assessment in §1.3 is for exactly this import set
      (json, os, ssl, sys, urllib.error, urllib.request, datetime). A new
      third-party import would not exist in the bare python image at all, and
      a new stdlib module would need re-checking against 3.13/3.14 removals.
    run: "kubectl get cm -n kube-system crash-ghost-reaper -o jsonpath='{.data.reap\\.py}' | grep -e '^[[:space:]]*import ' -e '^[[:space:]]*from ' | sed 's/^[[:space:]]*//' | sort | tr '\\n' '#'"
    expect_exact: "from datetime import datetime, timezone#import json#import os#import ssl#import sys#import urllib.error#import urllib.request#"
  - id: cronjob-not-suspended
    why: >-
      §4 waits for the next scheduled run. A suspended CronJob never produces
      a new-image pod and the gate would time out rather than prove anything.
    run: "kubectl get cronjob -n kube-system crash-ghost-reaper -o jsonpath='{.spec.suspend}'"
    expect_exact: "false"
---

# crash-ghost-reaper: python 3.12-alpine -> 3.14.7-alpine

## 1. Summary & why held

### 1.1 What changes

One line in `kubernetes/apps/kube-system/crash-ghost-reaper/app/cronjob.yaml`:
the CronJob container image moves from the floating
`docker.io/library/python:3.12-alpine` to the pinned
`docker.io/library/python:3.14.7-alpine` (Alpine 3.24 base). The script
(`reap.py`, in the ConfigMap), RBAC, schedule, env and securityContext are
untouched.

### 1.2 Why it was held

coverage.py's G3 gate could not fetch release notes for `library/python`
(Docker Official Image, no GitHub release feed), and an unverified bump needs
an assessed window. That gate is working as designed. The hold is **mostly a
false positive for this script**, with one real hazard worth measuring:

The CPython 3.13 "What's New" (ssl section) says:

> The `create_default_context()` API now includes `VERIFY_X509_PARTIAL_CHAIN`
> and `VERIFY_X509_STRICT` in its default flags.
> Note: `VERIFY_X509_STRICT` may reject pre-RFC 5280 or malformed certificates
> that the underlying OpenSSL implementation might otherwise accept.
> (gh-112389)

`reap.py` builds its TLS context with exactly
`ssl.create_default_context(cafile=f"{SA}/ca.crt")` and talks to the
kube-apiserver via the in-cluster service IP. If the Talos-issued apiserver
cert failed RFC 5280 strict checks (the usual failure is a leaf with no
Authority Key Identifier), every run would die with
`URLError(... CERTIFICATE_VERIFY_FAILED ...)` and the reaper would silently
stop protecting the cluster until the next power loss proved it.

The 3.14 "What's New" lists nothing affecting `ssl.create_default_context`,
`urllib.request`, `json` (only exception notes and a CLI), `datetime` (a new
`strptime` on date/time) or `open()` for the regular files this script reads.
3.13's PEP 594 removals (`cgi`, `telnetlib`, …) touch no module the script imports.

### 1.3 What was measured (2026-09-25, read-only)

- **Cert shape:** the cluster CA (`kube-root-ca.crt`) has `Basic Constraints:
  critical CA:TRUE`, `Key Usage: critical`, and a Subject Key Identifier. The
  apiserver leaf has an `Authority Key Identifier` matching that SKI, and SAN
  `IP Address:10.96.0.1` (the in-cluster endpoint the script uses).
- **Real reader, all three apiservers:** `reap.py` extracted from the live
  ConfigMap, with only the SA directory repointed at the live CA, run under
  Python 3.12.13 (`VERIFY_X509_STRICT` off), 3.13.14 and 3.14.6 (both
  strict=True), against 192.168.55.10 (VIP) and .11/.12/.13 on :6443. All
  completed the TLS handshake and got an HTTP 401 (dummy token), which is
  proof the handshake passed: a TLS failure raises an uncaught `URLError`
  instead, because `api()` catches only `HTTPError`.
- **Negative control:** the same run with the system CA bundle in place of
  the cluster CA failed with `CERTIFICATE_VERIFY_FAILED`. The handshake test
  can fail.
- **Detection logic parity:** `ghost_reason()` run over the live pod list
  (330 pods) plus three synthetic pods (a `ContainerStatusUnknown` ghost, a
  `NodeLost` ghost, a ghost younger than GRACE_MINUTES) on 3.12.13, 3.13.14
  and 3.14.6. All three versions printed the same thing: 0 live hits, both
  synthetic ghosts flagged, the young one held.

Residual gap: the Mac interpreters link a different OpenSSL build than
Alpine's. `VERIFY_X509_STRICT` is the same OpenSSL flag either way, but only
the in-cluster run in §4 is authoritative. That is why §4 gate A is a hard gate.

## 2. Pre-checks

```bash
cd /Users/mu/code/cberg-home-nextgen
# P1 premises (image, stdlib-only imports, not suspended)
.venv/bin/python3 runbooks/plan-premises.py crash-ghost-reaper-3.14.7

# P2 Flux Kustomization healthy, and the last run on the OLD image succeeded (baseline)
kubectl get kustomization -n kube-system crash-ghost-reaper \
  -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}{"\n"}'     # expect True
WANT=docker.io/library/python:3.12-alpine bash -c "$(sed -n '/^```verify-gate/,/^```$/p' runbooks/maintenance/plans/crash-ghost-reaper-3.14.7.md | sed '1d;$d')"
# expect: "... done — 0 pod(s) reaped" then PASS  (baseline: the gate passes on the old image)

# P3 no ghost is currently waiting to be reaped (so a broken new image cannot
#    strand a real one during the window)
kubectl get pods -A --no-headers | awk '$4=="Unknown" || $4=="ContainerStatusUnknown"'   # expect empty

# P4 target tag still resolves
curl -s https://hub.docker.com/v2/repositories/library/python/tags/3.14.7-alpine \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['digest'])"
# expect sha256:9e9fde4d32eedce0b661d9ab91e826b62dddf28e928c230ec55f1866cac66b01
```

If P3 lists a pod, stop: let the old reaper handle it (next */15 run), then restart the pre-checks.

## 3. Steps

1. Edit the image line. Dry-tested on a scratch copy (BSD sed, macOS):

   ```bash
   cd /Users/mu/code/cberg-home-nextgen
   sed -i '' 's#image: docker.io/library/python:3.12-alpine$#image: docker.io/library/python:3.14.7-alpine#' \
     kubernetes/apps/kube-system/crash-ghost-reaper/app/cronjob.yaml
   git diff --stat kubernetes/apps/kube-system/crash-ghost-reaper/app/cronjob.yaml   # 1 file, 1+/1-
   ```
   Expected diff (verified):
   ```
   <               image: docker.io/library/python:3.12-alpine
   >               image: docker.io/library/python:3.14.7-alpine
   ```

2. Also bump the SOP's overview line so the doc stays true (optional but same commit):
   `docs/sops/crash-ghost-reaper.md` §2, `python:3.12-alpine` → `python:3.14.7-alpine`: SOP line 28, plain text edit `python:3.12-alpine, non-root` → `python:3.14.7-alpine, non-root`; confirm `git diff docs/sops/crash-ghost-reaper.md` = 1+/1-.

3. Commit and push (shared worktree, so use `--only`):
   ```bash
   git commit --only kubernetes/apps/kube-system/crash-ghost-reaper/app/cronjob.yaml docs/sops/crash-ghost-reaper.md \
     -m "chore(crash-ghost-reaper): python 3.12-alpine -> 3.14.7-alpine (plan crash-ghost-reaper-3.14.7)"
   git log -1 --format=%s     # must be THIS subject
   git show --stat HEAD       # exactly the files above
   git push
   ```

4. Let the Flux webhook reconcile the change. Do not trigger a manual reconcile.
   Confirm the spec moved:
   ```bash
   kubectl get cronjob -n kube-system crash-ghost-reaper \
     -o jsonpath='{.spec.jobTemplate.spec.template.spec.containers[0].image}{"\n"}'
   # expect docker.io/library/python:3.14.7-alpine
   ```

5. Wait for the next scheduled run, at most 15 minutes. Optional: to shorten
   the wait, run the SOP §4 ad-hoc job (`kubectl create job -n kube-system
   ghost-reaper-adhoc --from=cronjob/crash-ghost-reaper`), which the
   component SOP sanctions. The window agent delegates it to cberg-agent and
   deletes the job afterwards. The gate below picks up either pod.

## 4. Verification

**Gate A (hard): the new interpreter completed a full authenticated list.**
Run until PASS, or 20 min after step 4:

```verify-gate
export WANT="${WANT:-docker.io/library/python:3.14.7-alpine}"
kubectl get pods -n kube-system -o json | python3 -c '
import sys, json, os, subprocess, re
want = os.environ["WANT"]
pods = [p for p in json.load(sys.stdin)["items"]
        if p["metadata"]["name"].startswith("crash-ghost-reaper-") or p["metadata"]["name"].startswith("ghost-reaper-adhoc")]
pods = [p for p in pods if p["spec"]["containers"][0]["image"] == want]
if not pods:
    print("FAIL: no reaper pod on", want, "yet"); sys.exit(1)
p = max(pods, key=lambda x: x["metadata"]["creationTimestamp"])
name = p["metadata"]["name"]; st = p["status"]
cs = (st.get("containerStatuses") or [{}])[0]
term = cs.get("state", {}).get("terminated", {})
log = subprocess.run(["kubectl","logs","-n","kube-system",name], capture_output=True, text=True).stdout
done = re.search(r"done . [0-9]+ pod\(s\) reaped", log)
bad = re.search(r"(?i)traceback|cannot list pods|ssl|certificate", log)
print(name, "phase=%s exit=%s imageID=%s" % (st.get("phase"), term.get("exitCode"), cs.get("imageID")))
print("LOG:", log.strip().splitlines()[-1] if log.strip() else "<empty>")
ok = st.get("phase") == "Succeeded" and term.get("exitCode") == 0 and done and not bad
print("PASS" if ok else "FAIL"); sys.exit(0 if ok else 1)
'
```

CONTENTS ASSERTION: the reaper run on the new image LISTED every pod in the cluster and walked the whole list. Measured by the `done — N pod(s) reaped` line, compared with the pre-change baseline (P2, same line on 3.12). In `reap.py` that line is printed only after `GET /api/v1/pods` returned 200 and the loop over `items` finished (`main()`). The failures it guards against print something different, and the gate FAILs on each:
- strict-TLS rejection: uncaught `URLError ... CERTIFICATE_VERIFY_FAILED`, a traceback, pod `Failed`, no `done` line;
- RBAC/token breakage: `cannot list pods: {...401/403...}`, exit 1;
- interpreter/rootfs breakage (e.g. read-only root refusing a write): traceback, `Failed`.
Dry-run on 2026-09-25: with `WANT=…3.12-alpine` it printed `PASS` (under bash and zsh); with the default target and no new pod yet it printed `FAIL: no reaper pod …` and exit 1. The gate can fail.

Also confirm the running pod is the NEW image and not a stale generation. `imageID` in the gate output must start `docker.io/library/python@sha256:9e9fde4d` (the 3.14.7-alpine index digest), not `…@sha256:236173eb` (the old 3.12 pull).

**Gate B (control): kube-state-metrics records the success.**

CONTROL: metric kube_cronjob_status_last_successful_time — `{cronjob="crash-ghost-reaper"}` must advance to a time after the push in step 3 (it read 1790300705 at 2026-09-25 01:54Z).
CONTROL: metric kube_job_status_failed — `{namespace="kube-system",job_name=~"crash-ghost-reaper.*"}` must be 0 for every job created after the push.

```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 19090:9090 >/dev/null 2>&1 & PF=$!; sleep 3
PUSH_TS=$(git log -1 --format=%ct <sha-of-step-3>)
WIN=$(( ($(date +%s) - PUSH_TS) / 60 + 1 ))
curl -s --data-urlencode 'query=kube_cronjob_status_last_successful_time{cronjob="crash-ghost-reaper"}' http://localhost:19090/api/v1/query \
 | PUSH_TS=$PUSH_TS python3 -c "import sys,json,os;r=json.load(sys.stdin)['data']['result'];v=float(r[0]['value'][1]) if r else 0;ok=v>int(os.environ['PUSH_TS']);print('last_successful',int(v),'push',os.environ['PUSH_TS'],'PASS' if ok else 'FAIL');sys.exit(0 if ok else 1)"
curl -s --data-urlencode "query=max by (job_name)(max_over_time(kube_job_status_failed{namespace=\"kube-system\",job_name=~\"crash-ghost-reaper.*|ghost-reaper-adhoc.*\"}[${WIN}m]))" http://localhost:19090/api/v1/query \
 | python3 -c "import sys,json;r=json.load(sys.stdin)['data']['result'];bad=[(x['metric']['job_name'],x['value'][1]) for x in r if float(x['value'][1])>0];print(len(r),'series; failed:',bad,'FAIL' if (not r or bad) else 'PASS');sys.exit(1 if (not r or bad) else 0)"
kill $PF 2>/dev/null
```
Both series were measured present on 2026-09-25/26; an empty result FAILs (instrument missing). Known-bad replay 2026-09-26: the failed-job query over [30d] returned crash-ghost-reaper-29838030 = 1 (2026-09-24 20:30Z) and exited 1; the timestamp check against PUSH_TS=now exited 1.
A single failed run after the bump: read its log before calling it a 3.14 regression (a 3.12 run failed 2026-09-24 20:30Z alongside elasticsearch-obs-recovery, cause unknown).

**Gate C (logic parity, already measured):** §1.3 ran detection parity on
3.14.6 against the live pod list with positive controls. Nothing in the
cluster can exercise the delete path without creating a real ghost, so do
NOT try to create one. The first real ungraceful reboot is the delete-path
test, same as on 3.12.

## 5. Rollback

Stateless. The CronJob recreates its Job pod from the spec on every run, so
no data or forward-only step is involved.

```bash
cd /Users/mu/code/cberg-home-nextgen
git revert --no-edit <sha-of-step-3>      # restores docker.io/library/python:3.12-alpine
git log -1 --format=%s && git show --stat HEAD
git push
kubectl get cronjob -n kube-system crash-ghost-reaper \
  -o jsonpath='{.spec.jobTemplate.spec.template.spec.containers[0].image}{"\n"}'   # expect 3.12-alpine
# then re-run the Gate A block with WANT=docker.io/library/python:3.12-alpine -> PASS on the next run
```

If a real ghost appears while the new image is failing, and before the revert
lands, use the manual equivalent from the SOP §5:
`kubectl delete pod -n <ns> <ghost> --grace-period=0 --force`. This needs
operator go.

If strict TLS is the confirmed cause (gate A log shows
`CERTIFICATE_VERIFY_FAILED`), do NOT fix it by adding
`ctx.verify_flags &= ~ssl.VERIFY_X509_STRICT` in-window. Revert, and
open a finding about the apiserver cert shape instead: §1.3 measured it as
compliant, so a strict failure means that measurement or the cert changed.

## 6. Interference notes

- **Blast radius of a failure:** none immediate. A broken reaper only stops
  reaping, and ghosts come only from ungraceful node loss. Do not schedule
  this into a window that also plans an *ungraceful* node action. Talos
  upgrades are graceful drains and do not create ghosts, so no
  `conflicts_with` entry is needed for them.
- **conflicts_with kube-prometheus-stack-91.4.1:** Gate B reads its Prometheus.
- **Sibling, not bundled:** `elasticsearch-obs-recovery` (ns monitoring) runs
  the same `python:3.12-alpine` float and has its own finding `F-c9568174`.
  Its script, its TLS peers (Elasticsearch, not the apiserver) and its
  failure mode differ, so it needs its own assessment. This plan
  deliberately does not touch it.
- **Repo corrections found while planning (not fixed here):**
  1. `docs/sops/crash-ghost-reaper.md` §5 Example A and §9 select pods with
     `-l app.kubernetes.io/name=crash-ghost-reaper`. The Job pods do NOT
     carry that label, because Flux `commonMetadata` labels only the
     top-level objects. The selector returns "No resources found" (measured
     2026-09-25). Pods carry only `job-name` / `batch.kubernetes.io/job-name`.
  2. SOP §6 Test 1 still matches only `terminated.reason == "Unknown"`, but
     since 2026-07-22 the script also matches `ContainerStatusUnknown`. The
     verification test is narrower than the thing it verifies.

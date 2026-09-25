---
plan_id: paperclip-chart-5.2.1
component: paperclip                  # version-check component key (HelmRelease ai/paperclip)
pr: null                              # no Renovate PR open for app-template 5.2.1 (gh pr list, 2026-09-25)
kind: chart
current: "app-template 5.1.0"
target: "app-template 5.2.1"
update_type: minor
risk: low                             # rendered diff for paperclip's LIVE values = the helm.sh/chart label only;
                                      # pod template byte-identical -> no pod roll (see §1)
est_duration_min: 15
needs_reboot: false
touches:
  namespaces: [ai]
  resources:
    - helmrelease/paperclip           # chart.spec.version 5.1.0 -> 5.2.1 (the only edit)
    - deployment/paperclip            # metadata label only; spec/pod template unchanged
    - service/paperclip               # metadata label only
    - pvc/paperclip-data              # metadata label only (Longhorn RWO, not resized, not re-bound)
    - serviceaccount/paperclip        # metadata label only
    - httproute/paperclip             # metadata label only (envoy-internal, LAN-only)
  shared: []                          # no gateway/envoy, cert-manager, cilium, coredns, shared DB or
                                      # longhorn engine change: the HTTPRoute's spec is identical in the
                                      # render, only its metadata label moves. The chart version is
                                      # per-HelmRelease, so the other ~79 app-template consumers are NOT
                                      # re-rendered by this change.
depends_on: []
conflicts_with:
  - paperclip-base-images             # same HelmRelease file, same pod: its debian leg restarts
                                      # deployment/paperclip; keep the two apart so a regression is
                                      # attributable (that plan's §6 already asks for this in prose)
  - kube-prometheus-stack-91.4.1      # §4 reads Prometheus (ALERTS + kube-state-metrics) — the
                                      # window's instrument is shared infra
exclusive: false
security_ref: null
capability_change: false              # template library bump; no behaviour change for paperclip
rollback_class: git-revert
finding_refs: [F-44278983]
status: draft
window: null
sops_refs:
  - docs/sops/application-update.md
generated: "2026-09-25"
---

# paperclip: bjw-s app-template chart 5.1.0 → 5.2.1

## 1) Summary & why held

`kubernetes/apps/ai/paperclip/app/helmrelease.yaml` pins `chart: app-template`
`version: 5.1.0` (HelmRepository `flux-system/bjw-s`,
`oci://ghcr.io/bjw-s-labs/helm`). Target **5.2.1**.

**Why held:** the auto-update policy rule `*app-template*` (`max: patch`,
`runbooks/auto-update-policy.yaml`) sends every app-template MINOR to the PLAN
lane with a rendered old-vs-new diff, because a chart minor is where bjw-s
changes rendered defaults. Sweep finding **F-44278983** (`version`, `monitor`).

**Target exists and is stable** (GitHub releases, `bjw-s-labs/helm-charts`,
checked 2026-09-25): `app-template-5.2.0` published 2026-09-17T15:49Z,
`app-template-5.2.1` 2026-09-17T18:58Z, both `prerelease=false`; nothing newer
than 5.2.1 is published. Eight days in the wild. (The `Source:` link in
`runbooks/version-check-current.md` points at `bjw-s-labs/app-template`, which
is the wrong repo. The releases live in `bjw-s-labs/helm-charts`.)

**Upstream evidence.** `app-template-5.2.x` only bumps the `common` library.
From the `common-5.2.0` changelog:

> Added support for ExternalSecret / CiliumNetworkPolicy /
> CiliumClusterwideNetworkPolicy resources · Added initial support for
> ListenerSet resources · **Added default selectors to
> topologySpreadConstraints to the same controller** · Added native support for
> `projected` persistence items · **Added global support for templating string
> fields** · Fixed NetworkPolicy extraSelectorLabels precedence over generated
> selector labels

`common-5.2.1`: "Fixed template rendering issues". There is no breaking-change
notice and no new upgrade guide. The linked guide is the existing 4→5 one.

Two items could affect paperclip:

- **Global templating of string fields.** paperclip's values hold a roughly
  300-line shell script (the `mise-install` initContainer and the `app`
  command). If 5.2 ran `tpl` over a string containing `{{`, it would break.
  Measured: the values contain no `{{` (only shell `${…}` / Flux-escaped
  `$${…}`), and the render below is identical.
- **Default topologySpreadConstraints selectors.** paperclip sets no
  `topologySpreadConstraints`, so the render has none on either version.

**Measured rendered diff (the gate the deny rule asks for).** I rendered
`helm template` from the LIVE HelmRelease values (`kubectl get hr -o
jsonpath='{.spec.values}'`, which are post-Flux-substitution) against 5.1.0 and
5.2.1. Both produce 545 lines and 5 objects (ServiceAccount, PVC, Service,
Deployment, HTTPRoute). The **entire** diff is five lines, all
`helm.sh/chart: app-template-5.1.0 → app-template-5.2.1` in object
`metadata.labels`. The Deployment's pod-template labels, selector, `strategy:
Recreate`, containers, initContainers, probes and volumes are byte-identical.
Consequences:

- **No pod roll.** A metadata-label change does not bump the Deployment
  `generation` or its pod-template-hash. The running pod (and its long, stateful
  `mise-install` init) is not touched.
- **No immutable-selector trap** (`application-update.md` §9, "spec.selector:
  field is immutable"). Selectors are unchanged.

**Verdict: the hold is a policy-correct false positive for this consumer.**
`risk: low`. It still goes through a window because the rule exists to force a
look. This plan re-runs the diff gate at execution time, so a republished chart
or a values change since 2026-09-25 is caught before the edit.

**Scope note, which the window agent should read.** The same 5.1.0 → 5.2.1
bump is open on about 80 app-template consumers, each with its own `monitor`
finding (e.g. F-11bb688f, F-6d39efbe, F-e1936864, …). This plan covers
**paperclip only**. It is a clean first canary: its values are the most
script-heavy in the fleet, which is where string templating would bite. The
fleet move deserves ONE plan with the diff looped across all consumers, not 80
copies of this one (see report).

## 2) Pre-checks

```bash
cd /Users/mu/code/cberg-home-nextgen

# a) HR healthy, still on 5.1.0 (if already 5.2.1 -> stop, the work is done; retire this plan)
kubectl get helmrelease -n ai paperclip \
  -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} {.status.history[0].chartVersion}{"\n"}'
# expect: True 5.1.0

# b) record the pod identity the §4 no-roll assertion compares against
kubectl get pods -n ai -l app.kubernetes.io/name=paperclip \
  -o custom-columns='NAME:.metadata.name,UID:.metadata.uid,HASH:.metadata.labels.pod-template-hash,RESTARTS:.status.containerStatuses[*].restartCount'
kubectl get deploy -n ai paperclip -o jsonpath='{.metadata.generation}{"\n"}'
# 2026-09-25 baseline: paperclip-58bccc9b55-tn9sb  uid 3ebccc18-…  hash 58bccc9b55  restarts 0,0  generation 8
# -> WRITE DOWN today's values; they are the baseline, not these.

# c) app content baseline — /api/health (NOT /health: that path is the SPA and returns 200 + HTML for anything)
kubectl port-forward -n ai svc/paperclip 38100:3100 >/dev/null 2>&1 & PF=$!; sleep 3
curl -s http://127.0.0.1:38100/api/health; echo
kill $PF 2>/dev/null
# expect JSON containing "status":"ok" and "bootstrapStatus":"ready"

# d) RENDERED-DIFF GATE — re-run at execution time; this is the policy rule's required evidence.
#    Values contain the real domain: keep them in a scratch dir and delete afterwards; never commit.
T=$(mktemp -d)
kubectl get helmrelease -n ai paperclip -o jsonpath='{.spec.values}' > "$T/v.json"
for v in 5.1.0 5.2.1; do
  helm template paperclip oci://ghcr.io/bjw-s-labs/helm/app-template --version $v -n ai -f "$T/v.json" > "$T/r-$v.yaml" || echo "RENDER_FAIL $v"
done
diff "$T/r-5.1.0.yaml" "$T/r-5.2.1.yaml" | grep -E '^[<>]' \
  | grep -vE 'helm\.sh/chart: app-template-5\.(1\.0|2\.1)$' | wc -l | tr -d ' '
# PASS: 0. Any other number = the render changed something beyond the chart label -> STOP,
#   inspect `diff` by hand and re-plan (risk is no longer low).
# Can it fail? Yes — dry-tested 2026-09-25 on macOS: real diff -> 0; negative control
#   (sed port 3100->3101 in the 5.2.1 render) -> 8. A RENDER_FAIL line also fails the gate.
rm -rf "$T"

# e) no other paperclip change in flight
git log --oneline -5 -- kubernetes/apps/ai/paperclip/
grep -nE '^(status|window):' runbooks/maintenance/plans/paperclip-base-images.md   # must not be in this same window
```

## 3) Steps

1. Edit the chart version. There is exactly one `version: 5.1.0` line in the
   file. Dry-tested with BSD sed on a scratch copy; the resulting diff is
   `11c11 <       version: 5.1.0 --- >       version: 5.2.1`:
   ```bash
   cd /Users/mu/code/cberg-home-nextgen
   sed -i '' 's/^      version: 5\.1\.0$/      version: 5.2.1/' kubernetes/apps/ai/paperclip/app/helmrelease.yaml
   git diff kubernetes/apps/ai/paperclip/app/helmrelease.yaml   # exactly one -/+ pair, line 11
   ```
2. Commit only that file, verify it, then push:
   ```bash
   git commit --only kubernetes/apps/ai/paperclip/app/helmrelease.yaml \
     -m "chore(paperclip): app-template chart 5.1.0 -> 5.2.1 (plan paperclip-chart-5.2.1, F-44278983)"
   git show --stat HEAD          # exactly one file
   git log -1 --format=%s        # must be the subject above (shared-worktree message-swap check)
   git push
   ```
3. Let the Flux webhook reconcile. The Kustomization and HR `interval` are
   30m, so if the webhook does not deliver within 5 minutes,
   `flux reconcile kustomization paperclip -n ai --with-source` is acceptable.
   The SOP's "commit + push, let Flux reconcile" path is the default.
4. After verification passes, close the finding in the same turn:
   `runbooks/policy-cli.py finding close F-44278983 --commit <sha>`. Also
   delete this plan file in the landing commit or a follow-up.

## 4) Verification

Floor:
```bash
kubectl get helmrelease -n ai paperclip \
  -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} {.status.history[0].chartVersion} {.status.history[0].status}{"\n"}'
# PASS: "True 5.2.1 deployed"   FAIL looks like: "True 5.1.0 …" (not reconciled yet / webhook missed),
#   or "False 5.2.1 failed" (helm upgrade error — read `kubectl describe hr -n ai paperclip`)
```

**CONTENTS ASSERTION 1 (the change landed):** the live Deployment carries
the new chart label. Measured by
`kubectl get deploy -n ai paperclip -o jsonpath='{.metadata.labels.helm\.sh/chart}{"\n"}'`
and compared to `app-template-5.2.1`. It fails by printing
`app-template-5.1.0` if helm never applied the release. HR `Ready=True` alone
can be the OLD revision's condition.

**CONTENTS ASSERTION 2 (nothing else changed; the no-roll premise holds):**
the pod is the same pod. Measured by
```bash
kubectl get pods -n ai -l app.kubernetes.io/name=paperclip \
  -o custom-columns='NAME:.metadata.name,UID:.metadata.uid,HASH:.metadata.labels.pod-template-hash,RESTARTS:.status.containerStatuses[*].restartCount'
kubectl get deploy -n ai paperclip -o jsonpath='{.metadata.generation}{"\n"}'
```
Compare against the §2b baseline. PASS means the same UID, same
pod-template-hash, same restart counts and same generation. It fails with a new
pod name/UID/hash, or generation +1, if the chart changed the pod spec. That
contradicts the §2d render. It is not necessarily an outage, but it means the
render gate was wrong. Then run the full `application-update.md` health checks,
watch `mise-install` to `Completed`, and report the discrepancy.

**CONTENTS ASSERTION 3 (the app still serves real state):** `/api/health`
returns `"status":"ok"` and `"bootstrapStatus":"ready"`. Compare it to the §2c
baseline:
```bash
kubectl port-forward -n ai svc/paperclip 38100:3100 >/dev/null 2>&1 & PF=$!; sleep 3
curl -s http://127.0.0.1:38100/api/health | grep -ciE '"status":"ok".*"bootstrapStatus":"ready"'
kill $PF 2>/dev/null
# PASS: 1. FAIL: 0 (non-ok JSON, empty body from a dead forward, or HTML).
# Do NOT substitute /health — measured 2026-09-25 it serves the SPA index.html with 200 regardless.
```

**Prometheus gate:**
```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 39090:9090 >/dev/null 2>&1 & PF=$!; sleep 3
curl -s http://127.0.0.1:39090/api/v1/query \
  --data-urlencode 'query=kube_deployment_status_replicas_available{namespace="ai",deployment="paperclip"}' \
  | python3 -c "import sys,json;r=json.load(sys.stdin)['data']['result'];print(r[0]['value'][1] if r else 'EMPTY')"
curl -s http://127.0.0.1:39090/api/v1/query \
  --data-urlencode 'query=ALERTS{alertname=~"PaperclipPodNotReady|PaperclipPodCrashLooping|PaperclipPodRestarted",alertstate="firing"}' \
  | python3 -c "import sys,json;print(len(json.load(sys.stdin)['data']['result']))"
kill $PF 2>/dev/null
```
CONTROL: metric kube_deployment_status_replicas_available — PASS reads `1`.
It fails as `0` (pod not available) or `EMPTY`. EMPTY means the scrape or
forward is broken, so the ALERTS reading below is not trustworthy either. That
is why this non-empty reading is paired with it. Measured 2026-09-25: `1`.

CONTROL: alertname PaperclipPodNotReady — must be not firing. The ALERTS count
above reads `0`. Rules were confirmed loaded via `/api/v1/rules` on 2026-09-25.

CONTROL: alertname PaperclipPodCrashLooping — must be not firing (same query).

CONTROL: alertname PaperclipPodRestarted — must be not firing (same query). It
guards against an unexpected container restart triggered by the upgrade.

## 5) Rollback

Only git-tracked, reversible state changes. No migration, no data, no pod
restart:

```bash
cd /Users/mu/code/cberg-home-nextgen
git revert --no-edit <sha of the step-2 commit>
git show --stat HEAD && git log -1 --format=%s     # one file, subject "Revert ..."
git push
# confirm the cluster is back:
kubectl get helmrelease -n ai paperclip \
  -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} {.status.history[0].chartVersion}{"\n"}'   # True 5.1.0
kubectl get deploy -n ai paperclip -o jsonpath='{.metadata.labels.helm\.sh/chart}{"\n"}'                  # app-template-5.1.0
```
Then re-run the §4 CONTENTS ASSERTION 3 and the Prometheus gate.

`maxHistory: 1` means `helm rollback` cannot reach 5.1.0. The git revert is the
path (`application-update.md` §11). If the HR is stuck after a failed upgrade
(`upgrade.remediation.retries: 1` exhausted), use
`flux reconcile helmrelease -n ai paperclip --force` after the revert is
pushed. This is `application-update.md` §9's remedy. For `pending-upgrade`, use
`helm rollback paperclip <last-deployed-rev> -n ai --wait=false` per the same
table, then reconcile. Leave the finding open and add a note with the failure
mode.

## 6) Interference notes

- **No shared infra.** The chart version is per-HelmRelease: only
  `ai/paperclip` re-renders. The other ~79 app-template consumers, the Envoy
  Gateways, `paperclip-postgresql` (a separate plain Deployment, already on
  18.6 since the executed `paperclip-postgresql-18.6`) and the
  `paperclip-backup-cleanup` CronJob are untouched.
- **`paperclip-base-images` (draft; its ubuntu `tools` leg is DO NOT EXECUTE
  under AR-101).** Both plans edit `kubernetes/apps/ai/paperclip/app/helmrelease.yaml`.
  Its debian leg deliberately clears the toolroot and restarts the pod. Listed
  in `conflicts_with`, so neither plan's verification can misattribute the
  other's pod event. There is no `depends_on` in either direction: neither
  change needs the other first. Note that `paperclip-base-images` does not yet
  list this plan back (reciprocity is not checked by `--validate`). That is a
  repo correction for its owner.
- **`kube-prometheus-stack-91.4.1`**: §4 reads Prometheus, so a same-night kps
  bump would take away the instrument. Listed in `conflicts_with`. That plan
  should list this one back.
- **`flux-reconciler-impersonation`** is `exclusive: true`, and the scheduler
  already keeps its slot empty. **`flux-oci-chart-sources`** migrates HTTP chart
  sources to `chartRef`. `bjw-s` is already an OCI HelmRepository, but if that
  plan's scope ever grows to app-template releases, it rewrites the same
  `spec.chart` block. Re-check at vetting if both are in one window.
- Low risk, no pod roll, `git-revert` rollback, no capability change. It still
  must not be folded into the unattended Step-0 safe-update batch: the deny
  rule's `max: patch` exists so that each app-template minor is looked at
  before it moves.

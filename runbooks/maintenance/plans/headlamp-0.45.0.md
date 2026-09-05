---
plan_id: headlamp-0.45.0
component: headlamp
pr: null                          # no open Renovate PR found for this bump as of
                                  # 2026-09-05 (gh pr list / search: none); the
                                  # auto-updater HELD it on the 0.x minor-is-breaking
                                  # policy rule before a PR needed to exist for that
                                  # gate to fire. Execute via the direct-bump steps
                                  # below, or by merging the Renovate PR if one
                                  # opens first (same verification either way).
kind: chart
current: "0.44.0"
target: "0.45.0"
update_type: security             # numerically a minor chart bump, but the value
                                  # driver is security: it moves the app image off
                                  # the tag flagged in F-f97717d3 (see Summary)
risk: low
est_duration_min: 15
needs_reboot: false
touches:
  namespaces: [monitoring]
  resources:
    - helmrelease/headlamp
    - deployment/headlamp
    - "ghcr.io/headlamp-k8s/headlamp (image tag v0.44.0 -> v0.45.0, default-tag follows chart appVersion)"
  shared: []                      # headlamp depends on cert-manager + metrics-server
                                  # (ks.yaml dependsOn) but this bump restarts
                                  # neither; headlamp itself is not shared infra —
                                  # nothing else in the cluster depends on it
depends_on: []
conflicts_with: []
security_ref: F-f97717d3          # CVE detail stays in the DB record; see Summary
                                  # for what's citable here
capability_change: false          # same admin-UI capability surface; RBAC/auth
                                  # wiring verified unchanged (see Summary)
rollback_class: git-revert        # single-replica Deployment, no PVC/state to
                                  # migrate; a version revert is a clean revert
finding_refs: [F-f97717d3]
status: draft
window: null
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/headlamp-token.md
  - docs/sops/authentik.md
generated: "2026-09-05"
---

## 1) Summary & why held

Chart bump `headlamp` 0.44.0 → 0.45.0 (`kubernetes/apps/monitoring/headlamp/app/helmrelease.yaml`,
`spec.chart.spec.version`). The auto-updater's policy holds any 0.x release
where the **minor** digit moves, on the general SemVer-0.x rule that the minor
digit is the breaking one at major 0 (`docs/sops/auto-update.md`). That rule is
a blanket heuristic, not evidence about this specific release — investigation
below shows the hold is a **false positive** for this bump specifically:

- **Verified chart 0.45.0 exists** in the upstream index
  (`https://kubernetes-sigs.github.io/headlamp/index.yaml`): `version: 0.45.0`,
  `appVersion: 0.45.0`, published 2026-08-20. This chart tracks `version ==
  appVersion` 1:1 (confirmed in `Chart.yaml` for both 0.44.0 and 0.45.0), so the
  chart bump and the app-version bump are the same event.
- **Full upstream diff pulled** (`git compare headlamp-helm-0.44.0...headlamp-helm-0.45.0`,
  kubernetes-sigs/headlamp) and filtered to `charts/headlamp/**`. The only
  non-test files touched are `Chart.yaml` (version bump only),
  `templates/deployment.yaml` (+3 lines), `values.yaml` (+2 lines),
  `values.schema.json` (+21 lines) and `README.md` (+1 line). The entire
  functional change is one new **opt-in** field,
  `config.clusterInventory.namespaces` (default `[]`, an experimental/alpha
  Cluster Inventory feature we do not enable) which appends a CLI arg only
  when a value is set. Our HelmRelease doesn't touch `clusterInventory` at all,
  so this bump is a functional no-op for us on the chart side.
- **RBAC/auth wiring is untouched.** `templates/serviceaccount.yaml` and
  `templates/clusterrolebinding.yaml` do not appear in the 0.44.0→0.45.0 diff
  at all — byte-identical both sides. Live-cluster check confirms current
  wiring: `serviceaccount/headlamp` (created by our own
  `kubernetes/apps/monitoring/headlamp/app/rbac.yaml`, since our values set
  `serviceAccount.create: false` / `name: headlamp`) and
  `clusterrolebinding/headlamp-admin` → `ClusterRole/cluster-admin` (chart-managed,
  `clusterRoleBinding.create: true` default, unchanged both versions) both
  already exist and will not be recreated or altered by this bump. Web auth
  (Authentik forward-auth on the ingress) is a separate manifest
  (`authentik-outpost-ingress.yaml`) this bump does not touch. **Net: this
  cluster-admin-holding app's authz surface does not change.**
- **This DOES matter for security, and raises this plan's priority**: our
  HelmRelease does not set `image.tag`, so the chart's default
  (`{{ .Values.image.tag | default (printf "v%s" .Chart.AppVersion) }}`) drives
  the running image tag directly off the chart version. Bumping the chart from
  0.44.0 → 0.45.0 therefore moves the main container from
  `ghcr.io/headlamp-k8s/headlamp:v0.44.0` to `:v0.45.0` — i.e. it is exactly
  the remediation `security_ref: F-f97717d3` already recommends ("newer
  upstream tag available, bump the image"). Per repo policy, CVE IDs and
  per-image vulnerability counts stay in the `sweep_findings` DB record
  (`runbooks/policy-cli.py finding show F-f97717d3`) — not here. What's
  citable here: upstream's own v0.45.0 release notes state the release
  "close[s] command-consent and dependency vulnerabilities" as part of its
  security section, consistent with the tag no longer being the one the
  finding flagged. **Confirm the fix in Verification (§4) by re-scanning the
  new tag** — don't take the release notes' word for it.
- **Blast radius is genuinely small**: `replicaCount: 1`, no PVC (headlamp is
  stateless — reads the cluster live), and nothing else in the cluster depends
  on headlamp (it's a leaf admin-UI consumer of cert-manager/metrics-server via
  `ks.yaml dependsOn`, not shared infra itself). No other app shares its
  namespace-scoped resources.

**Verdict:** `risk: low`. This is a case where the blanket 0.x-minor-is-breaking
hold rule fired on a release that changes nothing breaking, while
independently being the correct fix for an open CRITICAL security finding.
Recommend prioritizing this into the next available window (including the
unattended `nightly` window — see Interference notes, §6) rather than waiting
for the attended slot the low/security combination would otherwise queue behind.

## 2) Pre-checks

```bash
# HelmRelease currently healthy at 0.44.0 (confirms clean starting state)
kubectl get helmrelease -n monitoring headlamp \
  -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} {.status.history[0].chartVersion}{"\n"}'
# expect: True 0.44.0

# Single pod, running, no recent restarts
kubectl get pods -n monitoring -l app.kubernetes.io/name=headlamp

# RBAC baseline — record before, to diff after
kubectl get sa headlamp -n monitoring -o yaml > /tmp/headlamp-sa-before.yaml
kubectl get clusterrolebinding headlamp-admin -o yaml > /tmp/headlamp-crb-before.yaml

# Confirm chart 0.45.0 is actually published (repeat close to execution time)
curl -s https://kubernetes-sigs.github.io/headlamp/index.yaml | \
  python3 -c "import sys,yaml; d=yaml.safe_load(sys.stdin); print([e['version'] for e in d['entries']['headlamp'] if e['version']=='0.45.0'])"
# expect: ['0.45.0']

# Flux HelmRepository for headlamp is reconciling cleanly
flux get sources helm -n flux-system headlamp
```

No alert silence or update-marker needed for this one — per SOP §1 risk tiers
this is a **minor**, self-contained, single-replica, no-migration bump: the
"Minor" tier (verify target exists, then proceed as low, watch the rollout)
applies, not the attended/silence tier.

## 3) Steps

1. Edit the chart version:
   ```bash
   # kubernetes/apps/monitoring/headlamp/app/helmrelease.yaml
   #   spec.chart.spec.version: 0.44.0 -> 0.45.0
   ```
   No other value changes are required (§1 — the only new field,
   `config.clusterInventory.namespaces`, is opt-in and we don't set
   `config.clusterInventory` at all).

2. Commit and push (GitOps only — no direct cluster mutation):
   ```bash
   git add kubernetes/apps/monitoring/headlamp/app/helmrelease.yaml
   git commit --only kubernetes/apps/monitoring/headlamp/app/helmrelease.yaml -m "$(cat <<'EOF'
   feat(headlamp): bump chart 0.44.0 -> 0.45.0 (clears F-f97717d3 image tag)

   Chart/appVersion track 1:1 upstream; default image tag follows chart
   version, so this moves the running image off the tag flagged in
   F-f97717d3. Chart diff is a no-op for us (one opt-in clusterInventory
   field we don't use); RBAC/auth wiring unchanged (verified against
   upstream template diff + live cluster).
   EOF
   )"
   git push
   ```

3. Let Flux reconcile (`ks.yaml` interval 30m, or force if the window wants it
   sooner):
   ```bash
   flux reconcile source helm -n flux-system headlamp
   flux reconcile helmrelease -n monitoring headlamp --with-source
   ```

4. Watch the rollout (single-replica Deployment, default `RollingUpdate` is
   fine here — no Longhorn RWO volume for headlamp to multi-attach-deadlock
   on, per `docs/sops/longhorn-rwo-multi-attach.md`'s applicability test):
   ```bash
   kubectl get pods -n monitoring -l app.kubernetes.io/name=headlamp -w
   ```

## 4) Verification

```bash
# HelmRelease reconciled to 0.45.0 and Ready
kubectl get helmrelease -n monitoring headlamp \
  -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} {.status.history[0].chartVersion}{"\n"}'
# expect: True 0.45.0

# Pod healthy, 0 restarts after settle
kubectl get pods -n monitoring -l app.kubernetes.io/name=headlamp

# CONTENTS ASSERTION: the running image is actually v0.45.0, by imageID not
# just tag string (tag alone can lag a stale pull) — this is the property the
# whole security case rests on, so assert it directly:
kubectl get pod -n monitoring -l app.kubernetes.io/name=headlamp \
  -o jsonpath='{.items[0].spec.containers[?(@.name=="headlamp")].image}{"\n"}{.items[0].status.containerStatuses[?(@.name=="headlamp")].imageID}{"\n"}'
# expect: .../headlamp:v0.45.0 and an imageID digest that differs from the
# pre-upgrade v0.44.0 digest

# CONTENTS ASSERTION: RBAC unchanged (auth surface didn't silently drift)
diff <(kubectl get sa headlamp -n monitoring -o yaml) /tmp/headlamp-sa-before.yaml
diff <(kubectl get clusterrolebinding headlamp-admin -o yaml) /tmp/headlamp-crb-before.yaml
# expect: no meaningful diff (resourceVersion/managedFields churn only)

# App actually usable, not just Ready: hit it through the real path
# (Authentik forward-auth + ingress), not a bare port-forward
curl -sk -o /dev/null -w '%{http_code}\n' "https://headlamp.${SECRET_DOMAIN}/"
# expect: 302 (redirect to Authentik outpost) — proves ingress + auth-url
# annotation still resolve, i.e. auth wiring survived the bump end to end

# CONTENTS ASSERTION for the security driver: re-scan the NEW tag and confirm
# the CVEs in F-f97717d3 no longer appear (do this, don't just trust the
# release notes prose quoted in §1)
trivy image --quiet --scanners vuln --severity CRITICAL --ignore-unfixed \
  ghcr.io/headlamp-k8s/headlamp:v0.45.0
# expect: what F-f97717d3 records is no longer present on the new tag.
# Record the result in the finding, don't inline CVE detail in this file:
#   runbooks/policy-cli.py finding show F-f97717d3   (then resolve if clear)
```

## 5) Rollback

Single-replica, stateless (no PVC) — a straight git revert is sufficient, no
data/migration concerns:

```bash
git revert --no-edit <bump-commit-sha>
git push
flux reconcile helmrelease -n monitoring headlamp --with-source
kubectl get helmrelease -n monitoring headlamp \
  -o jsonpath='{.status.history[0].chartVersion}{"\n"}'
# expect: 0.44.0
kubectl get pods -n monitoring -l app.kubernetes.io/name=headlamp
```

If the pod is crash-looping and Flux's own remediation hasn't already rolled
it back (`upgrade.remediation.retries: 3` is the current default in this
HelmRelease), the revert above still applies — `maxHistory: 2` is enough to
hold both the pre- and post-bump revisions, so a plain `helm rollback` would
also reach 0.44.0 if needed, but the git revert is the GitOps-correct path and
should be preferred.

## 6) Interference notes

- **No shared infra perturbed.** Headlamp is a leaf consumer
  (`dependsOn: cert-manager, metrics-server` in `ks.yaml`) — this bump
  restarts only its own single pod. Nothing else in the cluster reads from or
  depends on headlamp.
- **No namespace contention expected**, but `monitoring` hosts many other
  apps (Prometheus stack, Grafana, etc.) — this plan touches only
  `helmrelease/headlamp` and its own Deployment, no shared `monitoring`-scope
  resource (no ConfigMap/Secret/NetworkPolicy shared with siblings).
- **Good candidate for the unattended `nightly` window**: low risk, no
  reboot, no migration, single replica, git-revert rollback, and a
  security-relevant fix that shouldn't sit queued behind attended-only slots.
  If the autonomy policy still routes `update_type: security` +
  `capability_change: false` + `rollback_class: git-revert` to attended by
  default, that's a fine, conservative first run — but there's no
  interference reason to hold it for Saturday/Sunday specifically.
- **`security_ref`/`finding_refs` both point at F-f97717d3** — once this
  executes and Verification's Trivy re-scan confirms the CRITICAL(s) are
  gone, resolve the finding via `runbooks/policy-cli.py finding` so the
  plan-or-page pass doesn't treat it as unplanned, and retire this plan file
  in the same commit that lands the bump (per this directory's README).

---
plan_id: app-template-5.3.0
component: app-template               # bjw-s app-template chart, every consumer (HelmRepository flux-system/bjw-s)
pr: 254                               # Renovate "update app-template to v5.3.0" -- DO NOT MERGE (see §1: its Flate Render Gate fails on openclaw)
kind: chart
current: "app-template 5.1.0 (66 HelmReleases) and 5.2.1 (1, ai/paperclip)"
target: "app-template 5.3.0"
update_type: minor
risk: medium                          # rendered diff is label-only for all 67 live consumers (measured 2026-10-12), but it is 67 helm
                                      # upgrades, and one consumer (openclaw) needs a values edit to render at all. Medium = honest
                                      # capacity weight; staged in 4 waves so a surprise is localised.
est_duration_min: 60                  # canary 12 + wave 1 15 + wave 2 15 + openclaw 8 + pre-checks/close-out 10; fits nightly budget 70
needs_reboot: false
touches:
  namespaces: [ai, backup, databases, default, download, home-automation, media, monitoring,
               my-software-development, my-software-production, my-software-showcase, network, office]
  resources:
    - "helmrelease/* on app-template (67 live: 66 on 5.1.0 + paperclip on 5.2.1), in 4 waves: W0 canary (ai/paperclip, default/echo-server), W1 (38 live, namespaces not in W2), W2 (26 live: home-automation, network, databases, backup), W3 ai/openclaw"
    - "15 x kubernetes/apps/**/helmrelease.yaml of apps DECOMMISSIONED 2026-10-04 (ks.yaml commented out, not deployed) plus the my-software-development/_template scaffold -- file edit only, nothing reconciles; bumped in W1/W2"
    - "68 workloads (66 Deployment + 2 StatefulSet iobroker/penpot-db; CronJob pallet-price-monitor covered by the render gate only): metadata label helm.sh/chart only, no pod-template change"
    - "every chart-owned Service/PVC/ServiceAccount/HTTPRoute/ConfigMap of those releases: metadata label only"
  shared:
    - gateway/envoy                   # 95 HTTPRoutes live (31+ owned by these releases) get a metadata-label change (spec identical) -> Envoy Gateway re-translates
    - public-edge                     # network/cloudflared is a consumer (label-only, no pod roll)
    - mqtt                            # home-automation/mosquitto is a consumer (label-only, no pod roll)
    - monitoring                      # §4 reads Prometheus (flux_resource_info, kube-state-metrics) -- the instrument
depends_on: []
conflicts_with:
  - app-template-5.2.1                # SUPERSEDED by this plan (same files, older target) -- must never share a window; see §1
  - flux-reconciler-impersonation     # exclusive; rewires helm-controller identity for the SAME HelmReleases
  - helm-drift-detection              # adds spec.driftDetection to the same HRs (same helm-controller)
  - flux-oci-chart-sources            # rewrites HelmRelease chart sources (spec.chart block)
  - flux-fleet-0.60.0                 # rolls deployment/flux-operator, the exporter of flux_resource_info that §4 reads
  - flux-distribution-2.9.6           # rolls Flux controllers: an HR reconcile racing a controller roll is unattributable
  - kube-prometheus-stack-92.2.0      # §4 reads Prometheus (shared instrument)
  - iobroker-12.0.0                   # edits + ROLLS home-automation/iobroker (W2 StatefulSet) -> GEN_CHANGED
  - chart-patches-coredns-reloader-blackbox  # Reloader/CoreDNS roll reads as GEN_CHANGED / POD_REPLACED in §4
  - coredns-1.48.2
  - edot-collector-0.162.0
  - envoy-proxy-config-distroless-v1.39.2
  - envoy-proxy-config-distroless-v1.39.3
  - external-dns-1.23.0
  - nextcloud-fleet-35.0.1
  - nextcloud-mcp-0.198.0             # edits office/nextcloud-mcp helmrelease.yaml (W1 file)
  - nextcloud-mcp-0.199.1
  - nocodb-2026.09.1
  - paperclip-26.04                   # edits ai/paperclip (canary file)
  - paperclip-backup-cleanup-busybox-pin  # edits ai/paperclip (canary file); added 2026-10-12
  - cli-tool-pins                     # edits ai/paperclip (canary file); added 2026-10-12
  - next-ai-draw-io-0.5.0             # edits ai/next-ai-draw-io (W1 file)
  - pgvector-fleet-0.8.7
  - python-fleet-3.14.8
  - reloader-2.2.18
  - sure-0.7.5
  - absenty-drop-npm-runtime          # edits absenty helmrelease.yaml (W1 file)
  - float-tag-pinning                 # edits media/makemkv helmrelease.yaml (W1 file)
  - penpot-cache-9.2                  # edits office/penpot-cache helmrelease.yaml (W1 file)
  - penpot-chart-1.10.0
  - redis-fleet-8.10.2                # edits + ROLLS 4 redis HRs that are fleet members
  - teslamate-4.3                     # edits home-automation/teslamate (W2 file) and ROLLS it
  - vaultwarden-1.37.4                # edits office/vaultwarden (W1 file)
exclusive: false
security_ref: null                    # no sweep finding mentions app-template as a security driver (policy-cli finding list --all --grep app-template, 2026-10-12); the per-consumer version findings below are the ownership claim
capability_change: false              # template-library bump; rendered objects byte-identical except the chart label (measured)
rollback_class: git-revert
finding_refs: [F-081877c1, F-08398bf3, F-0a5ad294, F-0d31e9d4, F-0d5c12a7, F-1111d5a4, F-11bb688f, F-14b6086c,
               F-159c75df, F-1784f5f2, F-18253c26, F-18599748, F-1ae6e89b, F-1efe0176, F-21d49540, F-295f5347,
               F-2983fb7e, F-2cf44161, F-2e5722d1, F-2eb36da8, F-315cfb68, F-393364bf, F-3a6463db, F-3b1428b1,
               F-3b7743cb, F-434c3acd, F-49469b03, F-4eb289a4, F-4f280046, F-51747edd, F-51bc0073, F-527444a0,
               F-58d3ce5b, F-6164d45d, F-65436d0a, F-68589ebb, F-6d39efbe, F-6dcba5d4, F-70caee92, F-74ec3d58,
               F-775e8438, F-796945e3, F-8016b6d3, F-84b976b0, F-88618ed2, F-8a178201, F-8abf3da3, F-8ad78669,
               F-8b9d5d30, F-8d9677a0, F-8e34fea8, F-908550f6, F-922d30b2, F-943e4773, F-94bbd7ee, F-a20805e9,
               F-ad2c78a0, F-afc9bd6a, F-b5e13899, F-b9646099, F-c0bca7f3, F-c5d55409, F-c676683f, F-ca7b2d59,
               F-cdab7cec, F-cf5d675b, F-d0b1c69d, F-d7e34f0d, F-d9cdd507, F-dd055cec, F-dda0af9f, F-dfd6adca,
               F-e1846243, F-e1936864, F-e4bffed7, F-e7135a91, F-ecd3db25, F-f6dabba5,
               F-76741a97, F-9d6fd381,   # carried verbatim from app-template-5.2.1 (the per-consumer version findings)
               F-0f056051]               # ops-retro finding that asked for exactly this invariant-premise re-plan
premises:
  # INVARIANT premises (F-0f056051): none of these hard-codes the fleet size, so a consumer added/decommissioned
  # between drafting and the window does not defer the plan. The render gate in §2d is what covers the fleet.
  - id: no-consumer-on-an-unplanned-version
    why: >-
      Every app-template HelmRelease must sit on 5.1.0, 5.2.1 or 5.3.0 (the plan's three known states, so a
      re-run after a partial execution still passes). Any other version means the plan's wave sed and rollback
      target are wrong for that consumer.
    run: >-
      kubectl get helmrelease -A -o jsonpath='{range .items[*]}{.spec.chart.spec.chart}={.spec.chart.spec.version}{"\n"}{end}'
      | grep '^app-template=' | cut -d= -f2 | sort -u | grep -v -e '^5.1.0$' -e '^5.2.1$' -e '^5.3.0$' | wc -l
    expect_exact: "0"
  - id: every-consumer-deployed-and-ready
    why: >-
      Do not stack the bump on a failing or half-applied release; the git-revert rollback target must be the
      revision actually deployed. Counts rows that are NOT deployed+Ready (0 is the only passing value; the
      pre-pipe grep also guarantees the jsonpath produced app-template rows at all via the next premise).
    run: >-
      kubectl get helmrelease -A -o jsonpath='{range .items[*]}{.spec.chart.spec.chart}={.status.history[0].chartVersion}={.status.history[0].status}={.status.conditions[?(@.type=="Ready")].status}{"\n"}{end}'
      | grep '^app-template=' | grep -v '=deployed=True$' | wc -l
    expect_exact: "0"
  - id: fleet-is-nonempty
    why: >-
      Guards the two premises above against an empty read (kubectl returning nothing makes every "count of
      bad rows" read 0). At least 60 consumers must be visible (67 on 2026-10-12).
    run: >-
      kubectl get helmrelease -A -o jsonpath='{range .items[*]}{.spec.chart.spec.chart}{"\n"}{end}'
      | grep -c '^app-template$'
    expect_matches: "^(6[0-9]|[7-9][0-9]|1[0-9][0-9])$"
  - id: repo-pins-only-known-versions
    why: >-
      The wave seds assume every `chart: app-template` file is followed by `version: 5.1.0` or 5.2.1 (or already
      5.3.0). Any other pin (a new consumer on a newer/older line) is unrendered by the §2d gate.
    run: >-
      grep -rh -A1 'chart: app-template' kubernetes/apps
      | grep '^      version:' | grep -v -e ' 5.1.0$' -e ' 5.2.1$' -e ' 5.3.0$' | wc -l
    expect_exact: "0"
  - id: target-chart-5.3.0-published
    why: "The target must still resolve from the OCI source the bjw-s HelmRepository uses; a yanked tag fails every upgrade."
    run: helm show chart oci://ghcr.io/bjw-s-labs/helm/app-template --version 5.3.0
    expect_contains: "version: 5.3.0"
  - id: openclaw-placeholders-present
    why: >-
      W3 escapes exactly two single-quoted whisper placeholders. If they moved/renamed, the W3 sed is wrong ->
      re-run the §2d openclaw gate. Passes both before (unescaped) and after (escaped) W3: it counts LINES
      containing either placeholder name.
    run: grep -c -e 'OutputDir}}' -e 'MediaPath}}' kubernetes/apps/ai/openclaw/app/helmrelease.yaml
    expect_exact: "2"
  - id: echo-server-single-intentional-template
    why: >-
      echo-server's `{{ .Release.Name }}` hostname is the one INTENTIONAL template in the fleet; it must stay
      the only `{{` there (it is NOT escaped).
    run: grep -c '{{' kubernetes/apps/default/echo-server/app/helmrelease.yaml
    expect_exact: "1"
  - id: no-consumer-renders-a-networkpolicy-today
    why: >-
      Baseline for the NetworkPolicy question (see §1). No app-template release currently renders a
      NetworkPolicy; if one does, §4's "none labelled 5.3.0" gate has a non-zero baseline and must be re-read.
    run: >-
      kubectl get networkpolicy,ciliumnetworkpolicy -A -l helm.sh/chart=app-template-5.1.0 --no-headers | wc -l
    expect_exact: "0"
status: vetted             # 2026-10-12 plan-reviewer: ready-for-go (premises 8/8, fleet render gate 67/67 label-only, negative controls GATE_FAIL); human-gated, attended window after Step 0
review: ready-for-go@2026-10-12   # plan-reviewer-agent, sweep a6518c23
window: null
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/auto-update.md
  - docs/sops/verification-contents-not-shape.md
  - docs/sops/storage-safety.md
generated: "2026-10-12"
---

# app-template fleet: bjw-s app-template chart 5.1.0 / 5.2.1 → 5.3.0 (67 live consumers)

## 1) Summary & why held

**Relationship to `app-template-5.2.1`: SUPERSEDED, not duplicated.** 5.3.0 was published 2026-10-10 and
Renovate retargeted PR #254 to it; 5.2.1 (published 2026-09-17) is no longer the newest line, deferred
`awaiting-go` in three nightlies, and carries exact-count premises that F-0f056051 asked to replace. This plan
reuses its batch machinery (`runbooks/app-template-render-diff.py`, the openclaw escape, the echo-server rule),
re-measures everything for 5.3.0, adds a canary wave and a two-wave split of the bulk, and carries its
`finding_refs`. **Parent action (I did not edit other files):** set `app-template-5.2.1` to
`status: superseded` (keep the file one commit for reciprocal refs), and repoint reciprocal `conflicts_with:
app-template-5.2.1` entries to `app-template-5.3.0`. This plan lists `app-template-5.2.1` in `conflicts_with`
so the scheduler cannot put both in a window.

**Why held:** `runbooks/auto-update-policy.yaml` rule `*app-template*` (`max: patch`) sends every minor to the
PLAN lane with a rendered diff. PR #254 shows why: its `Flate Render Gate` and `Flux Local Diff (helmrelease)`
CI checks FAIL (68 files, includes `ai/openclaw` unescaped), consistent with the openclaw render break below.
**Do not merge #254**; execute this plan's commits instead, then close #254 as superseded.

**Upstream evidence (common library 5.2.0 -> 5.3.0; app-template 5.2.x/5.3.0 only bump `common`).**
- `common-5.2.0`: "Added global support for templating string fields", "default selectors to
  topologySpreadConstraints", ExternalSecret / CiliumNetworkPolicy / ListenerSet / projected volumes.
  `common-5.2.1`: "Fixed template rendering issues".
- `common-5.3.0` Added: controller `extraSelectorLabels` + shared controller selector-labels helper; COMMAND
  probes; templateable annotation/label keys; controller references in (Cilium)NetworkPolicy rules; **configurable
  recursive string template evaluation with path exclusions** (`global.templateEvaluation.passes` default 1,
  `excludePaths`); Changed: "Use controller selector labels consistently for pod labels and generated pod
  selectors"; Fixed: "Render clusterIP in LoadBalancer and NodePort Services", "Fixed resource label / annotation
  merge order". No breaking-change notice.
- The three 5.3.0 items that COULD move a pod template or a Service (selector-label consistency, label merge
  order, clusterIP rendering) are exactly what the fleet render gate checks; measured below: none of the 67
  consumers' live values hits them.
- `global.templateEvaluation.excludePaths` is a cleaner alternative to the openclaw escape, but is NOT tested
  here; the proven escape is kept.

**NetworkPolicy question (explicit, because of the 2026-10-12 otel-operator deadlock): app-template 5.2/5.3
renders NO NetworkPolicy or CiliumNetworkPolicy by default.** `networkpolicies: {}` is the chart default
(common `values.yaml` line 2437, 5.3.0 chart pulled and read), NetworkPolicy objects only render when a
consumer sets `networkpolicies.*`, and `grep -rn 'networkpolicies:' kubernetes/apps` finds only
`storage/longhorn` (a different chart). The fleet render gate reports `LABEL_ONLY` for all 67 (an added
NetworkPolicy would read `ADD`), and §4 asserts live that none carries `helm.sh/chart=app-template-5.3.0`.
Contrast with the chart that deadlocked: that was an upstream chart default; this is opt-in.
Also note a **pre-existing red** to carry as baseline: `monitoring/otel-operator` HelmRelease is
`Ready=False` (rollback of opentelemetry-kube-stack 0.24.3) and `kube_deployment_spec_replicas !=
available` reads 1 (`monitoring/otel-operator-opentelemetry-operator`); `FluxResourceNotReady` fires for it.
It is NOT an app-template consumer; §4's gates are scoped to `source_name="bjw-s"` / exclude it.

**Method (script, reusable): `runbooks/app-template-render-diff.py`** renders each consumer's LIVE values
(`helm get values`) with the old and new chart, diffs the objects with the `helm.sh/chart` label stripped, and
classifies. Two self-checks: FIDELITY (old render must equal `helm get manifest`; held for all 67) and negative
controls. **Measured 2026-10-12, kube v1.36.0, `--from 5.1.0 --to 5.3.0 --escape ai/openclaw`:**
`TOTALS LABEL_ONLY=67  FLAGS ESCAPED=1 LIVE=5.2.1=1 TPL=2`, `GATE_PASS`. Controls run on 5.3.0 the same day:

| control | expected | measured |
|---|---|---|
| openclaw WITHOUT escape | fail | `RENDER_FAIL  function "OutputDir" not defined`, `GATE_FAIL` |
| echo-server WITH escape (must NOT be escaped) | fail | `OTHER HTTPRoute/echo-server:.spec.hostnames[0]`, `GATE_FAIL` |
| 5.3.0 chart copy mutated (`hostname:` injected into `lib/pod/_spec.tpl`) | fail | `POD_TEMPLATE Deployment/echo-server:.spec.template.spec.hostname`, `GATE_FAIL` |

| Class | Count | Consumers | Wave |
|---|---|---|---|
| LABEL_ONLY, `LIVE=5.2.1` | 1 | `ai/paperclip` (5.2.1 -> 5.3.0) | W0 canary |
| LABEL_ONLY, `TPL` | 1 | `default/echo-server` (intentional `{{ .Release.Name }}` hostname; render-identical, do NOT escape) | W0 canary |
| LABEL_ONLY, no flag | 38 live | every live consumer outside the W2 namespaces | W1 |
| LABEL_ONLY, no flag | 26 live | `home-automation` (19), `network/cloudflared`, `databases` (4), `backup` (2) | W2 |
| not deployed (repo-values render identical) | 16 files | 15 decommissioned 2026-10-04 + `_template` (14+_template in W1, 1 in W2) | W1/W2 file edits only |
| RENDER_FAIL, `TPL` -> LABEL_ONLY with escape | 1 | `ai/openclaw` (whisper `'{{OutputDir}}'`, `'{{MediaPath}}'` placeholders) | W3 |
| POD_TEMPLATE / OTHER / TSC / SELECTOR / ADD / DEL / FIDELITY | **0** | none | - |

**Consequence: no restarters.** A label-only helm upgrade bumps no workload `metadata.generation` and no pod
template hash. No pod rolls, including RWO-Longhorn singletons and the stateful ones (iobroker, penpot-db,
home-assistant, zigbee2mqtt, mosquitto).

**Verdict:** the hold is correct (it catches a real render break: openclaw); the rest are label-only false
positives. `risk: medium`, `capability_change: false`, `rollback_class: git-revert`, no reboot. It derives
HUMAN-GATED because `touches.shared: gateway/envoy` hits `SHARED_INFRA_FLOOR` in `runbooks/maintenance-plan.py`
(95 HTTPRoutes get a metadata-label change); run it in an attended window (sat/sun-attended), after Step 0.

## 2) Pre-checks

```bash
cd /Users/mu/code/cberg-home-nextgen
B=/private/tmp/claude-501/app-template-5.3.0; mkdir -p "$B"

# a) premises (invariant, no fleet-size constant)
.venv/bin/python3 runbooks/plan-premises.py app-template-5.3.0
# PASS: every premise passed. Any failure -> STOP and re-plan (do not "fix" the expected number).

# b) nothing else in flight. BASELINE RED IS EXPECTED: monitoring/otel-operator is Ready=False (measured 2026-10-12).
flux get helmreleases -A | awk 'NR==1 || $5 != "True"'
# PASS: only the header + monitoring/otel-operator (or nothing, if it was fixed). ANY other not-Ready HR, and
#   in particular any app-template consumer -> STOP.
git status --short -- kubernetes/apps | head     # foreign dirty files belong to other sessions; `git commit --only` below ignores them

# c) BASELINE snapshots -- take AFTER Step 0 (safe-update apply) has settled, never before it
.venv/bin/python3 runbooks/app-template-render-diff.py --snapshot-workloads "$B/wl-before.json"
# PASS: "SNAPSHOT workloads=68" (measured 2026-10-12: 68 = 67 on 5.1.0 incl. 2 StatefulSet + paperclip on 5.2.1; 68 -> use the printed number as the denominator if Step 0 changed it, and recompute the §4 table).  workloads=0 or exit 1 -> STOP.
kubectl get httproute -n default echo-server -o jsonpath='{.spec.hostnames[0]}' > "$B/echo-host-before.txt"
grep -c '^echo-server\.' "$B/echo-host-before.txt"                              # PASS: 1
DIG='import sys,json,hashlib;d=json.load(sys.stdin)["items"];print(len(d),hashlib.sha256(json.dumps(sorted([(i["metadata"]["namespace"],i["metadata"]["name"],i["spec"]) for i in d],key=lambda x:(x[0],x[1])),sort_keys=True).encode()).hexdigest()[:16])'
kubectl get httproute -A -o json | python3 -c "$DIG" | tee "$B/routes-before.txt"   # measured 2026-10-12: "95 6bfc0d109fdcb331"
kubectl get svc -A -o json       | python3 -c "$DIG" | tee "$B/svc-before.txt"      # measured 2026-10-12: "215 4df01245065fc4bb"
#   PASS: both print "<n> <16 hex>" with n > 0 (an empty read prints "0 <hash of []>" -> STOP).
kubectl get networkpolicy,ciliumnetworkpolicy -A --no-headers -o custom-columns=NS:.metadata.namespace,N:.metadata.name | sort > "$B/np-before.txt"; wc -l < "$B/np-before.txt"   # PASS: > 0 (non-empty control: mariadb, flux-operator-web, ... exist)

# d) RENDER GATE -- re-run at execution time over LIVE values (never reuse a pulled chart dir)
rm -rf "$B/render"
#  d1) whole fleet, openclaw with its planned escape
.venv/bin/python3 runbooks/app-template-render-diff.py --from 5.1.0 --to 5.3.0 --out "$B/render" \
  --escape ai/openclaw --expect LABEL_ONLY --allow-flag TPL --allow-flag ESCAPED --allow-flag LIVE=5.2.1 \
  | tee "$B/render-fleet.txt" | tail -2
# PASS: "TOTALS LABEL_ONLY=<N> FLAGS ESCAPED=1 LIVE=5.2.1=1 TPL=2" then "GATE_PASS" (N=67 measured 2026-10-12; N may differ if the fleet changed -- it is the CLASS and FLAGS that must match).
#   Any other class/flag (POD_TEMPLATE, OTHER, RENDER_FAIL, FIDELITY, TSC, SELECTOR, ADD, DEL) -> STOP, re-plan.
#  d2) per-wave strict gates from the live HR list
kubectl get helmrelease -A -o jsonpath='{range .items[*]}{.metadata.namespace}/{.metadata.name}={.spec.chart.spec.chart}{"\n"}{end}' \
  | grep '=app-template$' | sed 's/=app-template$//' | sort > "$B/all.hr"
grep -E '^(ai/paperclip|default/echo-server)$' "$B/all.hr" > "$B/w0.hr"
grep -vE '^(ai/paperclip|default/echo-server|ai/openclaw)$' "$B/all.hr" | grep -E  '^(home-automation|network|databases|backup)/' > "$B/w2.hr"
grep -vE '^(ai/paperclip|default/echo-server|ai/openclaw)$' "$B/all.hr" | grep -vE '^(home-automation|network|databases|backup)/' > "$B/w1.hr"
wc -l < "$B/w0.hr"; wc -l < "$B/w1.hr"; wc -l < "$B/w2.hr"       # measured 2026-10-12: 2 / 38 / 26 (sum with openclaw = all.hr = 67)
.venv/bin/python3 runbooks/app-template-render-diff.py --from 5.1.0 --to 5.3.0 --out "$B/render" --only-file "$B/w0.hr" --expect LABEL_ONLY --allow-flag TPL --allow-flag LIVE=5.2.1 | tail -1   # PASS: GATE_PASS
.venv/bin/python3 runbooks/app-template-render-diff.py --from 5.1.0 --to 5.3.0 --out "$B/render" --only-file "$B/w1.hr" --expect LABEL_ONLY | tail -1                                         # PASS: GATE_PASS
.venv/bin/python3 runbooks/app-template-render-diff.py --from 5.1.0 --to 5.3.0 --out "$B/render" --only-file "$B/w2.hr" --expect LABEL_ONLY | tail -1                                         # PASS: GATE_PASS
.venv/bin/python3 runbooks/app-template-render-diff.py --from 5.1.0 --to 5.3.0 --out "$B/render" --only ai/openclaw --escape ai/openclaw --expect LABEL_ONLY --allow-flag TPL --allow-flag ESCAPED | tail -1   # PASS: GATE_PASS
```

Can these fail? Yes, all three negative controls in §1 were run 2026-10-12 and read `GATE_FAIL`. A consumer whose
values start rendering differently (e.g. a values edit landed by another plan) drops out of `LABEL_ONLY` and fails
its wave gate: STOP that wave, the others may still run if their own gate passed.

## 3) Steps

Four waves, one commit each, each followed by its own §4 gate before the next starts. Commit with `--only` and
verify the subject every time (shared worktree; another session currently has `openclaw/app/skills-configmap.sops.yaml`
dirty -- it must NOT ride along). File lists are built from the repo, not typed.

The sed was dry-tested 2026-10-12 on a scratch copy of `kubernetes/` with BSD sed; results below.

```bash
cd /Users/mu/code/cberg-home-nextgen
B=/private/tmp/claude-501/app-template-5.3.0
BUMP='/^      chart: app-template$/{n;s/^      version: 5\.(1\.0|2\.1)$/      version: 5.3.0/;}'
grep -rl 'chart: app-template' kubernetes/apps | grep -v -e '/ai/openclaw/' -e '/default/echo-server/' -e '/ai/paperclip/' | sort > "$B/bulk.files"
grep -E  '^kubernetes/apps/(home-automation|network|databases|backup)/' "$B/bulk.files" > "$B/w2.files"
grep -vE '^kubernetes/apps/(home-automation|network|databases|backup)/' "$B/bulk.files" > "$B/w1.files"
printf '%s\n' kubernetes/apps/ai/paperclip/app/helmrelease.yaml kubernetes/apps/default/echo-server/app/helmrelease.yaml > "$B/w0.files"
wc -l < "$B/w0.files"; wc -l < "$B/w1.files"; wc -l < "$B/w2.files"     # dry-tested: 2 / 53 / 27 (53 = 38 live + 14 decommissioned + _template; 27 = 26 live + 1 decommissioned)
```

**W0 -- canary: ai/paperclip (5.2.1 -> 5.3.0) + default/echo-server (5.1.0 -> 5.3.0).** Two HRs, no stateful
data in the hot path; echo-server also exercises the one intentional `tpl` hostname and an HTTPRoute on the gateway.
```bash
while IFS= read -r f; do sed -i '' -E "$BUMP" "$f"; done < "$B/w0.files"
xargs git diff --stat -- < "$B/w0.files" | tail -1                         # PASS: "2 files changed, 2 insertions(+), 2 deletions(-)"
xargs git diff -- < "$B/w0.files" | grep -E '^[-+] ' | sort | uniq -c      # PASS (dry-tested): "1 -      version: 5.1.0", "1 -      version: 5.2.1", "2 +      version: 5.3.0"
#   any other -/+ line = a foreign hunk in a canary file -> STOP (--only would commit it)
printf '%s\n\n%s\n' "chore(app-template): chart -> 5.3.0, wave 0 canary (paperclip, echo-server)" \
  "Plan app-template-5.3.0. Rendered diff = helm.sh/chart label only (runbooks/app-template-render-diff.py)." > "$B/msg-0.txt"
xargs git commit --only -F "$B/msg-0.txt" -- < "$B/w0.files"
git show --stat HEAD | tail -1; git log -1 --format=%s                     # PASS: 2 files changed; subject = the line above verbatim (swap check)
git push
```
Run the §4 gate for W0 (row W0). **Bake: re-run the §4 readings once more 5 minutes after the first PASS**; the
canary must be green twice before W1. Any FAIL -> §5, do not continue.

**W1 -- bulk, non-critical namespaces (38 live + 14 inert + _template = 53 files).**
```bash
while IFS= read -r f; do sed -i '' -E "$BUMP" "$f"; done < "$B/w1.files"
xargs git diff --stat -- < "$B/w1.files" | tail -1                         # PASS: "53 files changed, 53 insertions(+), 53 deletions(-)"
xargs git diff -- < "$B/w1.files" | grep -E '^[-+] ' | sort | uniq -c      # PASS: exactly "53 -      version: 5.1.0" and "53 +      version: 5.3.0"
printf '%s\n\n%s\n' "chore(app-template): chart 5.1.0 -> 5.3.0, wave 1 (38 label-only consumers + 14 decommissioned + _template)" \
  "Plan app-template-5.3.0. Rendered diff = helm.sh/chart label only (runbooks/app-template-render-diff.py)." > "$B/msg-1.txt"
xargs git commit --only -F "$B/msg-1.txt" -- < "$B/w1.files"
git show --stat HEAD | tail -1; git log -1 --format=%s; git push          # PASS: 53 files changed; subject verbatim
```

**W2 -- household-critical namespaces (home-automation, network/cloudflared, databases, backup; 26 live + 1 inert = 27 files).**
Only after W1's §4 gate passed.
```bash
while IFS= read -r f; do sed -i '' -E "$BUMP" "$f"; done < "$B/w2.files"
xargs git diff --stat -- < "$B/w2.files" | tail -1                         # PASS: "27 files changed, 27 insertions(+), 27 deletions(-)"
xargs git diff -- < "$B/w2.files" | grep -E '^[-+] ' | sort | uniq -c      # PASS: exactly "27 -      version: 5.1.0" and "27 +      version: 5.3.0"
printf '%s\n\n%s\n' "chore(app-template): chart 5.1.0 -> 5.3.0, wave 2 (26 household-critical label-only consumers + 1 decommissioned)" \
  "Plan app-template-5.3.0. Rendered diff = helm.sh/chart label only (runbooks/app-template-render-diff.py)." > "$B/msg-2.txt"
xargs git commit --only -F "$B/msg-2.txt" -- < "$B/w2.files"
git show --stat HEAD | tail -1; git log -1 --format=%s; git push          # PASS: 27 files changed; subject verbatim
```
After this, `grep -rh -A1 'chart: app-template' kubernetes/apps | grep -c '^      version: 5.1.0$'` must read **1** (openclaw).

**W3 -- openclaw: chart bump + placeholder escape, ONE commit (after W2's gate).**
Dry-tested 2026-10-12 on a scratch copy (BSD sed; the placeholders were still `'{{OutputDir}}'` / `'{{MediaPath}}'`).
```bash
F=kubernetes/apps/ai/openclaw/app/helmrelease.yaml
sed -i '' -E -e '/^      chart: app-template$/{n;s/^      version: 5\.1\.0$/      version: 5.3.0/;}' \
  -e "s/'\{\{OutputDir\}\}'/'{{ \"{{\" }}OutputDir}}'/" \
  -e "s/'\{\{MediaPath\}\}'/'{{ \"{{\" }}MediaPath}}'/" "$F"
git diff "$F" | grep -E '^[-+] '
# PASS: exactly six lines: -/+ version 5.1.0 -> 5.3.0, and the two placeholder lines
#   '{{OutputDir}}' -> '{{ "{{" }}OutputDir}}'  and  '{{MediaPath}}' -> '{{ "{{" }}MediaPath}}'
grep -c '{{ "{{" }}' "$F"                                                   # PASS: 2
printf '%s\n' "fix(openclaw): app-template -> 5.3.0 + escape whisper {{placeholders}} for global string templating (plan app-template-5.3.0)" > "$B/msg-3.txt"
git commit --only "$F" -F "$B/msg-3.txt" && git show --stat HEAD | tail -1 && git log -1 --format=%s && git push
```
NEVER split W3 into two commits: a version-only commit leaves the HR `Ready=False` on `function "OutputDir" not
defined` (helm fails before apply; cluster untouched); an escape-only commit restarts openclaw with literal
`{{ "{{" }}` in its whisper args (the escape is only evaluated by >= 5.2).

If after 10 minutes a wave's §4 HR count has not moved at all, run `flux reconcile source git flux-system` once
(fetch only). Never force-reconcile HelmReleases.

**Close-out (after W3 verifies):** `runbooks/policy-cli.py finding close F-… --commit <sha>` for each id in
`finding_refs` (W0 sha for paperclip/echo-server findings, W3 sha for openclaw's, W1/W2 for the rest), same turn.
Close PR #254 with a comment pointing at the four commits (`gh pr close 254 -c ...`); never merge it. Retire this
plan file in a follow-up commit. Keep `$B` out of the repo; delete `$B/render` (contains real hostnames) at the end.

## 4) Verification (run after EACH wave; the numbers are per wave)

Measured baseline 2026-10-12: 67 HR (66 on 5.1.0, 1 on 5.2.1); 68 workloads (67 on 5.1.0, 1 on 5.2.1); 66 Deployments
(`kube_deployment_labels` 65 on 5.1.0 + 1 on 5.2.1; the 2 StatefulSets are not exported by ksm). Recompute from the
printed §2c numbers if Step 0 moved the fleet.

| after | HR on 5.3.0 / 5.1.0 | workload chart labels (`--expect-labels`) | `kube_deployment_labels{...="app-template-5.3.0"}` |
|---|---|---|---|
| W0 | 2 / 65 | `app-template-5.1.0=66 app-template-5.3.0=2` | 2 |
| W1 | 40 / 27 | `app-template-5.1.0=28 app-template-5.3.0=40` | 39 |
| W2 | 66 / 1 | `app-template-5.1.0=1 app-template-5.3.0=67` | 65 |
| W3 | 67 / 0 | `app-template-5.3.0=68` | 66 |

Poll until converged, at most 20 minutes, re-reading the number each time (not a passive sleep):
```bash
kubectl get helmrelease -A -o jsonpath='{range .items[*]}{.spec.chart.spec.chart}={.status.history[0].chartVersion}={.status.history[0].status}={.status.conditions[?(@.type=="Ready")].status}{"\n"}{end}' \
  | grep '^app-template=' | sort | uniq -c
# PASS (after W0): "2 app-template=5.3.0=deployed=True" and "65 app-template=5.1.0=deployed=True", nothing else.
# FAIL looks like: "=5.3.0=failed=False" (helm upgrade error -> `kubectl describe hr -n <ns> <name>` + §5), a
#   "=5.1.0=...=False" row, or a residual 5.1.0 count above the table after 20 min (not reconciled).
```

CONTENTS ASSERTION 1 (the change landed per workload AND nothing re-rolled): every workload carries the new chart
label and `metadata.generation` + pod UIDs are unchanged, measured against the §2c baseline:
```bash
.venv/bin/python3 runbooks/app-template-render-diff.py --compare-workloads "$B/wl-before.json" \
  --expect-labels 'app-template-5.1.0=66 app-template-5.3.0=2'      # row W0; use the row of the wave just applied
```
PASS prints the `CHART_LABELS` line then `SAME_GEN workloads=68 ...`. FAIL prints `LABELS_MISMATCH want ... got ...`
(chart not applied or applied to the wrong set), `GEN_CHANGED <ns>/<kind>/<name> n -> n+1` (the chart changed a pod
template, contradicting the render gate), `GONE`/`NEW`, or `COMPARE_FAIL empty baseline`, exit 1.
`POD_REPLACED_SAME_GEN` is informational (eviction/crash/node, not the chart). Why this is the real gate: HR
`Ready=True` can be the OLD revision's condition; the label reading cannot.

CONTENTS ASSERTION 2 (the rendered traffic objects are byte-equivalent, not just present): HTTPRoute and Service
**spec** digests equal the §2c baseline, which catches the 5.3.0 items that touch Service rendering (clusterIP
fix) and route label/selector handling:
```bash
kubectl get httproute -A -o json | python3 -c "$DIG" | diff - "$B/routes-before.txt" && echo ROUTES_SAME || echo ROUTES_CHANGED
kubectl get svc -A -o json       | python3 -c "$DIG" | diff - "$B/svc-before.txt"    && echo SVC_SAME    || echo SVC_CHANGED
```
PASS: `ROUTES_SAME` and `SVC_SAME`. FAIL: `*_CHANGED` plus the diff line (a route/service spec moved; name it with
`kubectl get ... -o json` and go to §5). A different change landing in the same window (another plan's route/service
edit) also trips it, which is why `conflicts_with` is wide; investigate before blaming the chart.

CONTENTS ASSERTION 3 (NetworkPolicy: the 2026-10-12 incident shape): no NetworkPolicy/CiliumNetworkPolicy came
from this chart, and the pre-existing set is unchanged:
```bash
kubectl get networkpolicy,ciliumnetworkpolicy -A -l helm.sh/chart=app-template-5.3.0 --no-headers | wc -l     # PASS: 0
kubectl get svc -A -l helm.sh/chart=app-template-5.3.0 --no-headers | wc -l                                    # CONTROL, PASS: > 0 after W0 (the label selector matches rendered objects; 0 here voids the line above)
kubectl get networkpolicy,ciliumnetworkpolicy -A --no-headers -o custom-columns=NS:.metadata.namespace,N:.metadata.name | sort | diff - "$B/np-before.txt" && echo NP_SAME || echo NP_CHANGED
```
FAIL: a non-zero first count (a consumer rendered a policy; `kubectl get ... -o yaml` it and STOP, do not wait for
the deadlock) or `NP_CHANGED`.

CONTENTS ASSERTION 4 (echo-server's intentional template, after W0): hostname byte-identical:
`kubectl get httproute -n default echo-server -o jsonpath='{.spec.hostnames[0]}' | diff - "$B/echo-host-before.txt" && echo HOST_SAME || echo HOST_CHANGED`
PASS `HOST_SAME`; FAIL `HOST_CHANGED` (5.3.0 double-evaluated or a literal `{{ .Release.Name }}...` leaked).

CONTENTS ASSERTION 5 (after W3, openclaw's whisper args are the literal placeholders):
```bash
kubectl get deploy -n ai openclaw -o jsonpath='{.spec.template.spec.containers[?(@.name=="app")].command[2]}' > "$B/oc-cmd.txt"
grep -cF "'{{OutputDir}}'" "$B/oc-cmd.txt"      # PASS: 1
grep -cF "'{{MediaPath}}'" "$B/oc-cmd.txt"      # PASS: 1
grep -cF '{{ "{{" }}' "$B/oc-cmd.txt"           # PASS: 0 (1+ = the escape reached the pod literally)
```
This also reads unchanged if the chart never applied; only `SAME_GEN` + `app-template-5.3.0=68` proves the new chart
rendered these bytes.

Prometheus gate (per wave):
```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 39090:9090 >/dev/null 2>&1 & PF=$!; sleep 3
q() { curl -s http://127.0.0.1:39090/api/v1/query --data-urlencode "query=$1" \
      | python3 -c "import sys,json;r=json.load(sys.stdin)['data']['result'];print(' '.join(f\"{x['metric'].get('revision','')}={x['value'][1]}\" for x in r) or 'EMPTY')"; }
q 'count by(revision)(flux_resource_info{kind="HelmRelease",source_name="bjw-s",ready="True"})'
q 'count(flux_resource_info{kind="HelmRelease",source_name="bjw-s",ready!="True"}) or vector(0)'
q 'count(kube_deployment_spec_replicas)'
q 'count(kube_deployment_spec_replicas{deployment!="otel-operator-opentelemetry-operator"} != kube_deployment_status_replicas_available{deployment!="otel-operator-opentelemetry-operator"}) or vector(0)'
q 'count(kube_deployment_labels{label_helm_sh_chart="app-template-5.3.0"})'
q 'count(ALERTS{alertname="FluxResourceNotReady",alertstate="firing",name!="otel-operator"}) or vector(0)'
kill $PF 2>/dev/null
```
CONTROL: metric flux_resource_info -- first query. PASS after W0 reads `5.1.0=65 5.3.0=2` (W1 `5.1.0=27 5.3.0=40`, W2
`5.1.0=1 5.3.0=66`, W3 `5.3.0=67`). Fails as a residual 5.1.0 count, or as `EMPTY` (flux-operator scrape broken, so
every later reading is void). Measured 2026-10-12 before the change: `5.1.0=66 5.2.1=1` (the `revision` label is the
chart version). Second query PASS `=0` (no bjw-s HR not Ready; measured 0).

CONTROL: metric kube_deployment_spec_replicas -- third query is the non-empty control (PASS a number, 168-ish; `EMPTY`
means ksm scrape or the forward is broken and the fourth reading is void). Fourth query PASS `=0`: **measured baseline
without the exclusion is 1** (the otel-operator deployment, a pre-existing red unrelated to this plan; the filter removes it).
A positive number names a Deployment short of replicas (`... != ...` without the aggregate); if it is a consumer, go to §5.

CONTROL: metric kube_deployment_labels -- fifth query, the table's last column. Fails as a lower count (consumer not
re-rendered) or a higher one (foreign roll). Measured baseline 2026-10-12: `app-template-5.2.1` = 1, `5.1.0` = 65.

CONTROL: alertname FluxResourceNotReady -- must not be firing for any consumer 15 minutes after each wave. It is real
and CAN match: measured 2026-10-12 it fires for `monitoring/otel-operator` (hence the `name!=` exclusion; with the
exclusion the baseline reads 0). Because of `for: 15m` the positive readings above are the primary gate and this is
the backstop.

Apps: after W2 spot-check household-critical consumers (home-assistant, zigbee2mqtt, mosquitto, vaultwarden,
cloudflared): `Running`, same pod names as `$B/wl-before.json` (SAME_GEN already implies it; read it).

## 5) Rollback

All git-tracked, no migration, no data, no pod roll. Each wave reverts on its own:
```bash
cd /Users/mu/code/cberg-home-nextgen
B=/private/tmp/claude-501/app-template-5.3.0
git revert --no-edit <sha of the failing wave's commit>      # W3: the WHOLE commit -- bump AND escape together
git show --stat HEAD | tail -1; git log -1 --format=%s       # W0: 2 files, W1: 53, W2: 27, W3: 1; subject "Revert ..."
git push
# confirm the cluster is back (expect the "before" row of the §4 table for the reverted wave):
kubectl get helmrelease -A -o jsonpath='{range .items[*]}{.spec.chart.spec.chart}={.status.history[0].chartVersion}={.status.conditions[?(@.type=="Ready")].status}{"\n"}{end}' | grep '^app-template=' | sort | uniq -c
.venv/bin/python3 runbooks/app-template-render-diff.py --compare-workloads "$B/wl-before.json"   # SAME_GEN; CHART_LABELS back to the reverted state
```
- Reverting a wave is the exact mirror of the forward move (label-only helm upgrades); no pod rolls either way.
  NOTE for W0: `git revert` restores each file's previous pin, so paperclip returns to **5.2.1** (not 5.1.0) and
  echo-server to 5.1.0; verify paperclip's label reads `app-template-5.2.1` afterwards.
- Many consumers carry `maxHistory: 1`, so `helm rollback` cannot reach the old chart; git revert is the path
  (`application-update.md` §11). If an HR sticks after a failed upgrade with exhausted remediation retries:
  `flux reconcile helmrelease -n <ns> <name> --force` after the revert is pushed; for `pending-upgrade`,
  `helm rollback <rel> <last-deployed-rev> -n <ns> --wait=false` then reconcile. Per consumer, never fleet-wide.
- W3 render failure (`function "OutputDir" not defined`): the escape did not land with the bump; the cluster is
  unchanged (helm fails before apply). Revert the commit and re-check the W3 diff.
- Leave the findings open on any rollback and note the failure mode on them.

## 6) Interference notes

- **Blast radius is fleet-wide by design; the render gate plus the wave split is what makes it acceptable.** Flux
  re-renders every consumer of a wave in one reconcile at helm-controller's default concurrency. The canary isolates
  the tpl path (echo-server) and the newest-pinned release (paperclip); W1 before W2 means the household-critical
  namespaces (home-automation, cloudflared, DBs, icloud backup) go only after ~40 releases have proven the chart live.
- **Step 0 runs first** (safe-update apply) in whatever window takes this. If Step 0 auto-reverts, stop before W0:
  the §2c baseline would include its pod rolls. Take `--snapshot-workloads` after Step 0 settles, never before.
- **`conflicts_with`** covers: the controller-identity / drift / chart-source plans (`flux-reconciler-impersonation`,
  `helm-drift-detection`, `flux-oci-chart-sources`, `flux-distribution-2.9.6`, `flux-fleet-0.60.0`), the Prometheus
  instrument owner (`kube-prometheus-stack-92.2.0`), every plan that edits or ROLLS a fleet member's files (nextcloud,
  nocodb, paperclip x3, next-ai-draw-io, vaultwarden, absenty, makemkv, penpot x2, redis, teslamate, iobroker, sure,
  pgvector, python-fleet), Reloader/CoreDNS/edot/envoy/external-dns rolls that read as `GEN_CHANGED`/`POD_REPLACED`,
  and the superseded `app-template-5.2.1`. If one of them lands first it does not break this plan (§2d re-renders live
  values), but it must not share the night. Scheduling hints as of 2026-10-12: nightly 10-13..10-16, sat 10-17 (coredns),
  sun 10-18 (nextcloud-fleet) are already occupied by listed conflicts; the window agent assigns the slot.
- **Reciprocity is a parent task**: `--validate` checks refs resolve, not reciprocity. Each plan above that is
  `draft`/`vetted` should list `app-template-5.3.0` (most currently list `app-template-5.2.1`).
- **HTTPRoutes (gateway/envoy):** 95 live routes; the fleet's change only `metadata.labels`. Envoy Gateway re-translates
  but listeners/hostnames/backends are byte-identical (§4 assertion 2 proves it).
- **PVCs** get a label change only: no resize/rebind/volumeHandle touch. `storage/longhorn` is deliberately not in
  `touches.shared`.
- **Pre-existing red**: `monitoring/otel-operator` HelmRelease failing (not this plan's); §2b/§4 account for it. If it
  is fixed before the window, drop the `otel-operator` exclusions only after re-measuring they read 0 unfiltered.
- **Upstream moved on?** If 5.3.1+ ships before the window, `target` is stale: re-run §2d with `--to <new>` and refresh
  in place (README "When the held target MOVES"); do not bump blind.

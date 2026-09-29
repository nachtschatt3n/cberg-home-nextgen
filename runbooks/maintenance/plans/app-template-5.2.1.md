---
plan_id: app-template-5.2.1
component: app-template               # bjw-s app-template chart, every consumer (HelmRepository flux-system/bjw-s)
pr: null                              # no Renovate PR open for app-template 5.2.1 (gh pr list --search app-template, 2026-09-27)
kind: chart
current: "app-template 5.1.0"
target: "app-template 5.2.1"
update_type: minor
risk: medium                          # rendered diff is label-only for all 79 (see §1 table), but it is 79 helm
                                      # upgrades in one night, and one consumer (openclaw) needs a values edit
                                      # to render at all. Medium = honest capacity weight; not `high`.
est_duration_min: 55
needs_reboot: false
touches:
  namespaces: [ai, backup, databases, default, download, home-automation, media, monitoring,
               my-software-development, my-software-production, my-software-showcase, network, office]
  resources:
    - "78 x helmrelease/* on app-template 5.1.0 (Batch A: every consumer except openclaw + echo-server; list = §3 A.1 file set)"
    - "kubernetes/apps/my-software-development/_template/app/helmrelease.yaml (scaffold, not deployed; bumped in Batch A)"
    - helmrelease/echo-server           # Batch B (default)
    - helmrelease/openclaw              # Batch C (ai): chart bump + two-placeholder escape, ONE commit
    - "81 workloads = 79 Deployment incl. paperclip + 2 StatefulSet iobroker/penpot-db (covered by --compare-workloads); plus 1 CronJob pallet-price-monitor (render gate only): metadata label helm.sh/chart only"
    - "every chart-owned Service/PVC/ServiceAccount/HTTPRoute/ConfigMap of those releases: metadata label only"
  shared:
    - gateway/envoy                   # ~45 HTTPRoutes get a metadata-label change (spec identical) -> Envoy Gateway
                                      # re-translates; no route/listener change. Both envoy-internal and envoy-external.
    - public-edge                     # network/cloudflared is a consumer (label-only, no pod roll)
    - mqtt                            # home-automation/mosquitto is a consumer (label-only, no pod roll)
    - monitoring                      # §4 reads Prometheus (flux_resource_info, kube-state-metrics) — the instrument
depends_on: []
conflicts_with:
  - flux-reconciler-impersonation     # exclusive; rewires helm-controller/kustomize-controller identity for the
                                      # SAME 79 HelmReleases — a same-night failure could not be attributed
  - helm-drift-detection              # adds spec.driftDetection to all 124 HRs incl. these 79 (same objects, same helm-controller)
  - flux-oci-chart-sources            # rewrites HelmRelease chart sources (up to 32 -> chartRef); same spec.chart block
  - nextcloud-mcp-0.187.1             # edits kubernetes/apps/ai/openclaw/app/helmrelease.yaml (Batch C's file)
  - absenty-drop-npm-runtime          # edits my-software-production/absenty helmrelease.yaml (Batch A file)
  - float-tag-pinning                 # edits media/makemkv helmrelease.yaml (Batch A file)
  - penpot-cache-9.2                  # edits office/penpot-cache helmrelease.yaml (Batch A file)
  - redis-fleet-8.10.2                # edits 4 Batch A HR files (redis, tube-archivist-redis, immich-redis,
                                      # sure-redis) and ROLLS them -> §4 would read GEN_CHANGED
  - makemkv-v26.09.2                  # edits media/makemkv helmrelease.yaml (Batch A file); lists us already
  # traccar-6.16.0 REMOVED 2026-09-29: executed green in nightly:2026-09-29 (3a943035), plan retired (1a40b257);
  # traccar helmrelease.yaml now pins image 6.16.0@sha256 (chart still 5.1.0) -- Batch A's chart sed is unaffected
  - chart-patches-coredns-reloader-blackbox  # a Reloader/CoreDNS roll during §4 reads as GEN_CHANGED; lists us already
  - penpot-chart-1.10.0               # works against penpot-db + penpot-cache (Batch A members); lists us already
  - mariadb-chart-27.3.0              # rolls databases/mariadb-0 under phpmyadmin + all 15 showcase HRs (our Batch members); same-night confounds both §4s (review 2026-09-28)
exclusive: false
security_ref: null
capability_change: false              # template-library bump; rendered objects byte-identical except the chart label
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
               F-e1846243, F-e1936864, F-e4bffed7, F-e7135a91, F-ecd3db25, F-f6dabba5]
premises:
  - id: fleet-still-on-5.1.0
    why: >-
      `current:` claims 79 app-template HelmReleases on 5.1.0 (plus paperclip,
      already 5.2.1). A different count means a consumer was added, removed or
      bumped since the 2026-09-27 render — the §1 table no longer covers the fleet.
    run: kubectl get helmrelease -A -o jsonpath='{range .items[*]}{.spec.chart.spec.chart}={.spec.chart.spec.version}{"\n"}{end}' | grep -c '^app-template=5.1.0$'
    expect_exact: "79"
  - id: fleet-deployed-and-ready-on-5.1.0
    why: >-
      Do not stack the bump on a failing or half-applied release; the git-revert
      rollback target must be the revision actually deployed on every consumer.
    run: kubectl get helmrelease -A -o jsonpath='{range .items[*]}{.spec.chart.spec.chart}={.status.history[0].chartVersion}={.status.history[0].status}={.status.conditions[?(@.type=="Ready")].status}{"\n"}{end}' | grep -c '^app-template=5.1.0=deployed=True$'
    expect_exact: "79"
  - id: target-chart-5.2.1-published
    why: "The target must still resolve from the OCI source the bjw-s HelmRepository uses; a yanked tag fails 79 upgrades."
    run: helm show chart oci://ghcr.io/bjw-s-labs/helm/app-template --version 5.2.1 | grep -E '^version:'
    expect_exact: "version: 5.2.1"
  - id: repo-pins-80-files
    why: >-
      §3's edits assume every app-template file has `chart: app-template`
      immediately followed by `      version: 5.1.0` (79 live + the _template
      scaffold). Run from the repo root.
    run: >-
      grep -rh -A1 'chart: app-template' kubernetes/apps | grep -c '^      version: 5.1.0$'
    expect_exact: "80"
  - id: openclaw-placeholders-unescaped
    why: >-
      Batch C escapes exactly two single-quoted placeholders. If they moved, were
      renamed, or a third `{{` appeared, the Batch C sed is wrong — re-run the
      §2 render gate and re-plan Batch C.
    run: grep -c '{{' kubernetes/apps/ai/openclaw/app/helmrelease.yaml
    expect_exact: "2"
  - id: echo-server-intentional-template
    why: >-
      echo-server's `{{ .Release.Name }}` hostname is the one INTENTIONAL
      template in the fleet (5.1.0 already tpl'd route hostnames); Batch B must
      NOT escape it. Guard that it is still the only `{{` there.
    run: grep -c '{{' kubernetes/apps/default/echo-server/app/helmrelease.yaml
    expect_exact: "1"
status: vetted   # 2026-09-27 plan-reviewer: needs-fix (4 blocking) -> all applied -> re-check ready-for-go. NO operator GO recorded.
review: ready-for-go@2026-09-27
window: "nightly:2026-10-02"   # SCHEDULED 2026-09-28 by maintenance-window-agent (operator: "schedule everything that needs to be scheduled"); SD-11 candidate; GO-free only once SD-11 lands, else needs a GO
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/auto-update.md
  - docs/sops/verification-contents-not-shape.md
generated: "2026-09-27"
---

# app-template fleet: bjw-s app-template chart 5.1.0 → 5.2.1 (79 consumers)

## 1) Summary & why held

79 HelmReleases pin `chart: app-template` `version: 5.1.0` (HelmRepository
`flux-system/bjw-s`, `oci://ghcr.io/bjw-s-labs/helm`); an 80th file is the
`my-software-development/_template` scaffold (not deployed). Target **5.2.1**.
paperclip already moved on 2026-09-26 (`paperclip-chart-5.2.1`, executed:
label-only, same pod) and is the canary for this plan.

**Why held:** `runbooks/auto-update-policy.yaml` rule `*app-template*`
(`max: patch`) sends every app-template MINOR to the PLAN lane "with a rendered
diff (helm template, old chart vs new, across all consumers) before it moves".
This plan is that diff. It answers the 78 per-consumer `version` findings
(`<name>: chart 5.1.0 → 5.2.1 (minor)`, listed in `finding_refs`). absenty and
andreamosteller each exist in two namespaces and share one finding.

**Upstream evidence.** app-template 5.2.x only bumps the `common` library.
`common-5.2.0` added "global support for templating string fields" and
"default selectors to topologySpreadConstraints to the same controller" (plus
ExternalSecret/CiliumNetworkPolicy/ListenerSet/projected-volume support).
`common-5.2.1` is "Fixed template rendering issues". There is no
breaking-change notice. The string-templating change is **in the code, not
just the notes**. In `charts/common/templates/loader/_generate.tpl` (5.2.1),
every render now starts with
`bjw-s.common.values.evaluateTemplate` over the whole `.Values` tree, and
`values/_init.tpl` runs `tpl` on **every string that contains `{{`**. The only
exemption is `externalSecrets.*.target.template.data`. There is no values
opt-out.

**Method (script, reusable): `runbooks/app-template-render-diff.py`.** For each
consumer it takes the values helm actually holds (`helm get values`, which
includes esphome's `valuesFrom` and the postBuild substitution), renders them
with 5.1.0 and 5.2.1 (both charts pulled locally, cluster kube-version and
api-resources passed as capabilities), and diffs the rendered objects with the
`helm.sh/chart` label stripped. It then classifies each consumer and raises
review flags. Two self-checks make the classification trustworthy:

- **FIDELITY.** The 5.1.0 render must equal `helm get manifest` of the live
  release. The first run failed this on 45 HTTPRoutes (`apiVersion`: without the
  `group/version/Kind` capability strings, `classes/_route.tpl` picks
  `v1alpha2`). The script now passes those strings, and fidelity holds for all
  79. So "no diff" means "no diff against what is deployed", not "no diff
  between two wrong renders".
- **Negative controls (2026-09-27, mutated 5.2.1 chart copy).** Injecting
  `topologySpreadConstraints` into `lib/pod/_spec.tpl` gives `POD_TEMPLATE` +
  `TSC` + `GATE_FAIL`. Injecting `publishNotReadyAddresses` into the Service
  class gives `OTHER` + `GATE_FAIL`. openclaw without the escape gives
  `RENDER_FAIL` + `GATE_FAIL`. `--compare-workloads` with a bumped generation
  gives `COMPARE_FAIL`, and with an empty baseline `COMPARE_FAIL empty baseline`.

**Summary table (run 2026-09-27, all 80 app-template releases, kube v1.36.0):**

| Class | Count | Consumers | Batch |
|---|---|---|---|
| LABEL_ONLY, no flag | 77 | every consumer except the three below | **A**: one commit, attended window (derives HUMAN-GATED, see Verdict) |
| LABEL_ONLY, `TPL` | 1 | `default/echo-server` | **B**: individual (reviewed below) |
| RENDER_FAIL, `TPL` | 1 | `ai/openclaw` | **C**: individual; needs a values edit in the SAME commit |
| LABEL_ONLY, `LIVE=5.2.1` | 1 | `ai/paperclip` | done 2026-09-26; Batch A's sed is a no-op on it |
| POD_TEMPLATE (restart) | **0** | — | none |
| OTHER / CRON_TEMPLATE | **0** | — | none |
| `TSC` (topologySpreadConstraints) | **0** | no consumer sets them, so the new default selectors never render | none |
| `SELECTOR` / `ADD` / `DEL` | **0** | — | none |
| `FIDELITY` mismatch | **0** | — | — |

Consequence: **there are no restarters.** The "group restarters by
namespace/risk" batch is empty. A label-only helm upgrade does not bump any
workload's `metadata.generation` or its pod-template hash. No pod rolls
anywhere, including the four RWO-Longhorn singletons and the stateful ones
(iobroker, penpot-db, home-assistant, zigbee2mqtt, mosquitto). The paperclip
canary measured generation `8 → 8`, same pod UID.

**The two individual reviews:**

- **echo-server (TPL, render-identical).** Its only `{{` is
  `route.app.hostnames: ["{{ .Release.Name }}.${SECRET_DOMAIN}"]`. That is an
  intentional template, and 5.1.0 already ran `tpl` on route hostnames
  (`classes/_route.tpl` line 62: `- {{ tpl . $rootContext | quote }}`). 5.2.1
  evaluates it once centrally and gets the same hostname. The render diff is
  label-only. It must **not** be escaped: the escaped render reads `OTHER`
  (`HTTPRoute/echo-server:.spec.hostnames[0]`), measured. Verdict: bump
  unchanged. It gets its own batch only because it carries the flag.
- **openclaw (RENDER_FAIL).** The JS config script in
  `controllers.openclaw.containers.app.command[2]` contains openclaw's own
  whisper placeholders `'{{OutputDir}}'` and `'{{MediaPath}}'`
  (`helmrelease.yaml` lines 1295/1297). 5.2.1 `tpl`s them and fails with
  `function "OutputDir" not defined`. The fix is to write them as Go-template
  escapes, `'{{ "{{" }}OutputDir}}'` and `'{{ "{{" }}MediaPath}}'`, which 5.2.1
  renders back to the literal placeholder. Measured: escaped values on 5.2.1
  equal the original values on 5.1.0 apart from the 4 chart labels, so openclaw
  becomes **label-only, no restart**. **The escape and the chart bump must be
  ONE commit.** On 5.1.0 the escape is NOT evaluated: the escaped values on
  5.1.0 change the command (2 lines), which would restart openclaw with broken
  whisper args. The reverse also holds: 5.2.1 without the escape fails the
  helm render. That failure is before any apply, so the cluster is untouched,
  but the HR goes `Ready=False`.

**Verdict:** the hold was correct, because it caught a real render break
(openclaw). The other 78 are label-only false positives. `risk: medium`
(blast-radius weight), `capability_change: false`, `rollback_class:
git-revert`, no reboot. **It derives HUMAN-GATED**
(`maintenance-plan.py --json`), because `touches.shared: gateway/envoy` hits
`SHARED_INFRA_FLOOR` in `runbooks/maintenance-plan.py`. That is correct: about
47 HTTPRoutes get re-translated by Envoy Gateway. So all three batches run in
an attended window. The label-only render proof would otherwise make Batch A
an unattended nightly candidate, but declaring the gateway truthfully rules
that out. Whether a metadata-only route change should count against the floor
is an operator decision, not a planner's.

## 2) Pre-checks

```bash
cd /Users/mu/code/cberg-home-nextgen
B=/private/tmp/claude-501/app-template-5.2.1; mkdir -p "$B"

# a) premises (fleet count 79, all deployed+Ready on 5.1.0, target published, 80 repo pins, openclaw 2 / echo 1 `{{`)
.venv/bin/python3 runbooks/plan-premises.py app-template-5.2.1
# PASS: every premise passed. Any failure -> STOP (fleet changed since the 2026-09-27 render; re-run d) and re-plan).

# b) nothing else in flight: no other plan from conflicts_with in this window, Flux quiet
flux get helmreleases -A | awk 'NR==1 || $5 != "True"'          # expect only the header line (column 5 = READY)
git log --oneline -3 -- kubernetes/apps/ai/openclaw/app/helmrelease.yaml

# c) BASELINE: workload generations + pod UIDs (the no-roll comparand) and echo-server hostname
.venv/bin/python3 runbooks/app-template-render-diff.py --snapshot-workloads "$B/wl-before.json"
# PASS: "SNAPSHOT workloads=81 -> …". Measured 2026-09-27: 81 (80 on app-template-5.1.0 + paperclip on 5.2.1).
#   An exit 1 / workloads=0 -> STOP (kubectl failed; §4 would compare against nothing).
kubectl get httproute -n default echo-server -o jsonpath='{.spec.hostnames[0]}' > "$B/echo-host-before.txt"
grep -c '^echo-server\.' "$B/echo-host-before.txt"                   # PASS: 1

# d) RENDER GATE — re-run at execution time over the LIVE values (they may have changed since 2026-09-27).
#    Values/renders contain real hostnames: they stay under $B/render, deleted at the end of the window.
rm -rf "$B/render"        # never reuse a pulled (or negative-control-mutated) chart dir: the script trusts it
#    d1) whole fleet, openclaw rendered with its planned escape — the summary table of §1, re-measured:
.venv/bin/python3 runbooks/app-template-render-diff.py --from 5.1.0 --to 5.2.1 --out "$B/render" \
  --escape ai/openclaw --expect LABEL_ONLY --allow-flag TPL --allow-flag ESCAPED --allow-flag LIVE=5.2.1 \
  | tee "$B/render-fleet.txt" | tail -2
# PASS: "TOTALS LABEL_ONLY=80   FLAGS ESCAPED=1 LIVE=5.2.1=1 TPL=2" then "GATE_PASS" (measured 2026-09-27)
#   (= every consumer rendered, is LABEL_ONLY, and its 5.1.0 render equals the live manifest; a
#   failed `helm get manifest` flags FIDELITY and fails closed).
#   Any other class/flag (POD_TEMPLATE, OTHER, RENDER_FAIL, FIDELITY, TSC, SELECTOR, ADD, DEL) -> STOP, re-plan.
#    d2) per-batch STRICT gates (each must print GATE_PASS) — Batch A's consumer list from the live HRs:
kubectl get helmrelease -A -o jsonpath='{range .items[*]}{.metadata.namespace}/{.metadata.name}={.spec.chart.spec.chart}{"\n"}{end}' \
  | grep '=app-template$' | sed 's/=app-template$//' | grep -v -e '^ai/openclaw$' -e '^default/echo-server$' -e '^ai/paperclip$' \
  | sort > "$B/batchA.hr"; wc -l < "$B/batchA.hr"                     # PASS: 77
.venv/bin/python3 runbooks/app-template-render-diff.py --from 5.1.0 --to 5.2.1 --out "$B/render" \
  --only-file "$B/batchA.hr" --expect LABEL_ONLY | tail -2            # PASS: TOTALS LABEL_ONLY=77 … GATE_PASS
.venv/bin/python3 runbooks/app-template-render-diff.py --from 5.1.0 --to 5.2.1 --out "$B/render" \
  --only default/echo-server --expect LABEL_ONLY --allow-flag TPL | tail -1     # PASS: GATE_PASS
.venv/bin/python3 runbooks/app-template-render-diff.py --from 5.1.0 --to 5.2.1 --out "$B/render" \
  --only ai/openclaw --escape ai/openclaw --expect LABEL_ONLY --allow-flag TPL --allow-flag ESCAPED | tail -1   # PASS: GATE_PASS
```

Can these fail? Yes, each was run 2026-09-27. openclaw without `--escape`
reads `RENDER_FAIL` / `GATE_FAIL`. echo-server with `--escape` reads `OTHER` /
`GATE_FAIL`. The mutated-chart controls in §1 read `POD_TEMPLATE`/`OTHER`. A
consumer that starts rendering differently (for example a values change landed
by `absenty-drop-npm-runtime`) drops out of `LABEL_ONLY` and fails its batch
gate. Any batch gate that is not `GATE_PASS` means **STOP that batch**. The
others may still run if their own gate passed.

## 3) Steps

Each batch is ONE commit, followed by its own §4 gate before the next batch
starts. Commit with `--only` and verify the subject every time, because the
worktree is shared.

**Batch A — 77 label-only consumers + the `_template` scaffold (one commit).**

A.1 Edit. Dry-tested 2026-09-27 on a scratch copy of `kubernetes/` with BSD
sed. The result was 78 files changed, each diff exactly
`<       version: 5.1.0` / `>       version: 5.2.1`. paperclip was a no-op, and
openclaw and echo-server were untouched (`grep -A1` afterwards: `2 × 5.1.0`,
`79 × 5.2.1`).
```bash
cd /Users/mu/code/cberg-home-nextgen
B=/private/tmp/claude-501/app-template-5.2.1
grep -rl 'chart: app-template' kubernetes/apps | grep -v -e '/ai/openclaw/' -e '/default/echo-server/' > "$B/batchA.files"
while IFS= read -r f; do
  sed -i '' '/^      chart: app-template$/{n;s/^      version: 5\.1\.0$/      version: 5.2.1/;}' "$f"
done < "$B/batchA.files"
xargs git diff --stat -- < "$B/batchA.files" | tail -1                    # PASS: "78 files changed, 78 insertions(+), 78 deletions(-)"
xargs git diff -- < "$B/batchA.files" | grep -E '^[-+] ' | sort | uniq -c   # PASS: exactly "78 -      version: 5.1.0" and "78 +      version: 5.2.1"
#   any extra -/+ line = a foreign hunk inside a batch file (another session) -> STOP: `--only` would commit it
grep -rh -A1 'chart: app-template' kubernetes/apps | grep -c '^      version: 5.1.0$'   # PASS: 2 (openclaw, echo-server)
```
A.2 Commit only those files. Use a unique message file, and verify the files
and the subject before pushing:
```bash
xargs git diff --name-only -- < "$B/batchA.files" > "$B/batchA.changed"; wc -l < "$B/batchA.changed"   # PASS: 78
printf '%s\n\n%s\n' "chore(app-template): chart 5.1.0 -> 5.2.1, batch A (77 label-only consumers + _template)" \
  "Plan app-template-5.2.1. Rendered diff = helm.sh/chart label only (runbooks/app-template-render-diff.py)." > "$B/msg-A.txt"
xargs git commit --only -F "$B/msg-A.txt" -- < "$B/batchA.files"   # paths via xargs, never a zsh scalar; 80 short paths = one invocation
git show --stat HEAD | tail -1          # PASS: 78 files changed
git log -1 --format=%s                  # PASS: the subject above, verbatim (shared-worktree message-swap check)
git push
```
A.3 Let the Flux webhook reconcile. If after 10 minutes the §4 A-count has not
moved at all, run `flux reconcile source git flux-system` once. That only
fetches the source. Do not force-reconcile HelmReleases.

**Batch B — echo-server (after Batch A's §4 gate passed).**
```bash
F=kubernetes/apps/default/echo-server/app/helmrelease.yaml
sed -i '' '/^      chart: app-template$/{n;s/^      version: 5\.1\.0$/      version: 5.2.1/;}' "$F"
git diff "$F" | grep -E '^[-+] '        # PASS: exactly "-      version: 5.1.0" / "+      version: 5.2.1" (dry-tested: line 12)
printf '%s\n' "chore(echo-server): app-template chart 5.1.0 -> 5.2.1, batch B (plan app-template-5.2.1)" > "$B/msg-B.txt"
git commit --only "$F" -F "$B/msg-B.txt" && git show --stat HEAD | tail -1 && git log -1 --format=%s && git push
```

**Batch C — openclaw: chart bump + placeholder escape, ONE commit (after B's gate).**
```bash
F=kubernetes/apps/ai/openclaw/app/helmrelease.yaml
sed -i '' -e '/^      chart: app-template$/{n;s/^      version: 5\.1\.0$/      version: 5.2.1/;}' \
  -e "s/'{{OutputDir}}'/'{{ \"{{\" }}OutputDir}}'/" \
  -e "s/'{{MediaPath}}'/'{{ \"{{\" }}MediaPath}}'/" "$F"
git diff "$F" | grep -E '^[-+] '
# PASS (dry-tested 2026-09-27, lines 11/1295/1297), exactly these six lines:
#   -      version: 5.1.0                              +      version: 5.2.1
#   -                        '--output_dir', '{{OutputDir}}',     +  … '{{ "{{" }}OutputDir}}',
#   -                        '{{MediaPath}}',                     +  … '{{ "{{" }}MediaPath}}',
grep -c '{{ "{{" }}' "$F"               # PASS: 2
printf '%s\n' "fix(openclaw): app-template 5.1.0 -> 5.2.1 + escape whisper {{placeholders}} for 5.2 string templating (plan app-template-5.2.1)" > "$B/msg-C.txt"
git commit --only "$F" -F "$B/msg-C.txt" && git show --stat HEAD | tail -1 && git log -1 --format=%s && git push
```
NEVER split Batch C into two commits (see §1). A version-only commit leaves
the HR `Ready=False` on a render error. An escape-only commit restarts
openclaw with the literal `{{ "{{" }}` text in its whisper args.

**Close-out (after C verifies):** close each finding in `finding_refs` with
`runbooks/policy-cli.py finding close F-… --commit <sha of the batch that
covered it>` in the same turn. openclaw's and echo-server's findings take the
B/C shas, and everything else takes A's. Then retire this plan file in a
follow-up commit.

## 4) Verification (run after EACH batch; expected numbers per batch)

| after | HR app-template on 5.2.1 & deployed & Ready | on 5.1.0 | workload chart labels (from `--compare-workloads`) |
|---|---|---|---|
| A | 78 | 2 | `app-template-5.1.0=2 app-template-5.2.1=79` |
| B | 79 | 1 | `app-template-5.1.0=1 app-template-5.2.1=80` |
| C | 80 | 0 | `app-template-5.2.1=81` |

Floor. Poll until converged, for at most 20 minutes. This is not a passive
sleep: re-read and act on the number each time.
```bash
kubectl get helmrelease -A -o jsonpath='{range .items[*]}{.spec.chart.spec.chart}={.status.history[0].chartVersion}={.status.history[0].status}={.status.conditions[?(@.type=="Ready")].status}{"\n"}{end}' \
  | grep '^app-template=' | sort | uniq -c
# PASS (after A): "78 app-template=5.2.1=deployed=True" and "2 app-template=5.1.0=deployed=True", nothing else.
# FAIL looks like: "=5.2.1=failed=False" (helm upgrade error -> `kubectl describe hr` + §5), or a
#   "=5.1.0=…=False" row, or a residual 5.1.0 count above the table after 20 min (not reconciled).
```

**CONTENTS ASSERTION 1 (the change landed, per workload, and nothing re-rolled):**
the live workloads carry the new chart label, and every workload's
`metadata.generation` is unchanged. This is measured by
```bash
.venv/bin/python3 runbooks/app-template-render-diff.py --compare-workloads "$B/wl-before.json" \
  --expect-labels 'app-template-5.1.0=2 app-template-5.2.1=79'
# after B: --expect-labels 'app-template-5.1.0=1 app-template-5.2.1=80'   after C: --expect-labels 'app-template-5.2.1=81'
```
and compared to the §2c baseline and the per-batch label counts in the table
above. A wrong count prints `LABELS_MISMATCH want … got …` and `COMPARE_FAIL`
(measured 2026-09-27 against the pre-change state). PASS prints the table's `CHART_LABELS` line
followed by `SAME_GEN workloads=81 …`. It fails with `GEN_CHANGED <ns>/<kind>/<name> n -> n+1`
(the chart changed a pod template, contradicting the render gate), or with
`GONE`/`NEW`, and exits 1. A missing or empty baseline prints `COMPARE_FAIL
empty baseline`. `POD_REPLACED_SAME_GEN` lines are informational: a pod
replaced while its generation stayed put was not caused by the chart
(eviction, crash, node). Inspect it, but it is not this plan's failure. The
gate can fail: a mutated baseline with one generation +1 read
`GEN_CHANGED … COMPARE_FAIL`, rc 1, measured 2026-09-27. HR `Ready=True` alone
can be the OLD revision's condition, and this label reading cannot.

**CONTENTS ASSERTION 2 (Batch B, echo-server's intentional template still resolves):**
the live HTTPRoute hostname is byte-identical to the pre-change one:
```bash
kubectl get httproute -n default echo-server -o jsonpath='{.spec.hostnames[0]}' | diff - "$B/echo-host-before.txt" && echo HOST_SAME || echo HOST_CHANGED
```
PASS prints `HOST_SAME`. It fails as `HOST_CHANGED` if 5.2 double-evaluated
the template or it got escaped. A literal `{{ .Release.Name }}…` hostname
would be one example.

**CONTENTS ASSERTION 3 (Batch C, openclaw's whisper args are the literal placeholders):**
```bash
kubectl get deploy -n ai openclaw -o jsonpath='{.spec.template.spec.containers[?(@.name=="app")].command[2]}' > "$B/oc-cmd.txt"
grep -cF "'{{OutputDir}}'" "$B/oc-cmd.txt"      # PASS: 1   (measured before the change: 1)
grep -cF "'{{MediaPath}}'" "$B/oc-cmd.txt"      # PASS: 1
grep -cF '{{ "{{" }}' "$B/oc-cmd.txt"           # PASS: 0   (measured before: 0). 1+ = escape reached the pod literally
```
This also reads unchanged if the chart never applied. Only the `SAME_GEN`
reading together with `app-template-5.2.1=81` proves that the new chart
rendered these exact bytes.

**Prometheus gate (per batch):**
```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 39090:9090 >/dev/null 2>&1 & PF=$!; sleep 3
q() { curl -s http://127.0.0.1:39090/api/v1/query --data-urlencode "query=$1" \
      | python3 -c "import sys,json;r=json.load(sys.stdin)['data']['result'];print(' '.join(f\"{x['metric'].get('revision','')}={x['value'][1]}\" for x in r) or 'EMPTY')"; }
q 'count by(revision)(flux_resource_info{kind="HelmRelease",source_name="bjw-s",ready="True"})'
q 'count(flux_resource_info{kind="HelmRelease",source_name="bjw-s",ready!="True"}) or vector(0)'
q 'count(kube_deployment_spec_replicas)'
q 'count(kube_deployment_spec_replicas != kube_deployment_status_replicas_available) or vector(0)'
q 'count(kube_deployment_labels{label_helm_sh_chart="app-template-5.2.1"})'
kill $PF 2>/dev/null
```
CONTROL: metric flux_resource_info — first query. PASS after A reads
`5.1.0=2 5.2.1=78`, after C `5.2.1=80`. It fails as a residual 5.1.0 count,
or as `EMPTY` (flux-operator scrape broken, so the next reading is not
trustworthy either). Measured 2026-09-27: `5.1.0=79 5.2.1=1`. The `revision`
label is the chart version (paperclip reads `revision=5.2.1`,
`reason=UpgradeSucceeded`). Second query PASS: `=0` (no bjw-s HR not-Ready).

CONTROL: metric kube_deployment_spec_replicas — third query is the non-empty
control. PASS reads a number (183 measured 2026-09-27). `EMPTY` means the
kube-state-metrics scrape or the forward is broken, and the fourth reading is
void. Fourth query PASS: `=0`, measured 2026-09-27 `0`. A positive number
means a Deployment is short of available replicas. Name it with
`kube_deployment_spec_replicas != kube_deployment_status_replicas_available`,
and if it is a consumer, go to §5.

CONTROL: metric kube_deployment_labels — fifth query. PASS reads 77 after A
(all app-template Deployments except openclaw and echo-server), 78 after B and
79 after C. There are 79 app-template Deployments in total. The two
StatefulSets are covered by `--compare-workloads` and the CronJob only by the
§2d render gate, because ksm does not export their chart
label (`kube_statefulset_labels{label_helm_sh_chart=~…}` reads EMPTY,
measured). Measured before the change: 1, paperclip.

CONTROL: alertname FluxResourceNotReady — it must not be firing for any
`kind="HelmRelease"` row of these releases 15 minutes after each batch. It is
real and can match: `count_over_time(ALERTS{alertname="FluxResourceNotReady"}[30d])`
is non-empty (it fired for a Kustomization in the last 30 days). Because of
its `for: 15m`, the positive readings above are the primary gate and this is
the 15-minute backstop.

Apps: per `application-update.md` §9, spot-check the household-critical
consumers after Batch A. home-assistant, zigbee2mqtt, mosquitto, vaultwarden
and cloudflared must show `Running` and the same pod names as in
`$B/wl-before.json`. `SAME_GEN` already implies this, but read it.

## 5) Rollback

Everything is git-tracked, with no migration, no data and no pod roll. Each
batch reverts on its own:

```bash
cd /Users/mu/code/cberg-home-nextgen
B=/private/tmp/claude-501/app-template-5.2.1       # the §2c baseline lives here
git revert --no-edit <sha of the failing batch's commit>     # Batch C: the WHOLE commit — bump AND escape together
git show --stat HEAD | tail -1 && git log -1 --format=%s     # A: 78 files; B/C: 1 file; subject "Revert …"
git push
# confirm the cluster is back (for a Batch A revert expect the "before" row of the §4 table: 1× 5.2.1 (paperclip), rest 5.1.0):
kubectl get helmrelease -A -o jsonpath='{range .items[*]}{.spec.chart.spec.chart}={.status.history[0].chartVersion}={.status.conditions[?(@.type=="Ready")].status}{"\n"}{end}' | grep '^app-template=' | sort | uniq -c
.venv/bin/python3 runbooks/app-template-render-diff.py --compare-workloads "$B/wl-before.json"   # SAME_GEN; CHART_LABELS back to the reverted state
```
- Reverting Batch A is itself 77 label-only helm upgrades, the exact mirror of
  the forward move (the render proves symmetry). There are no pod rolls in
  either direction.
- Many consumers carry `maxHistory: 1`, so `helm rollback` cannot reach 5.1.0.
  git revert is the path (`application-update.md` §11). If an HR sticks after
  a failed upgrade with exhausted remediation retries, run
  `flux reconcile helmrelease -n <ns> <name> --force` after the revert is
  pushed. For `pending-upgrade`, run `helm rollback <rel> <last-deployed-rev>
  -n <ns> --wait=false` and then reconcile. Do this per consumer, never
  fleet-wide.
- Batch C render failure: if the HR shows `Ready=False` with
  `function "OutputDir" not defined`, the escape did not land with the bump.
  The cluster is unchanged because helm fails before apply. Revert the commit
  and re-check §3 C's diff.
- Leave the findings open on any rollback, and note the failure mode on them.

## 6) Interference notes

- **Blast radius is fleet-wide by design, and the render gate is what makes
  that acceptable.** Flux re-renders all 77 Batch A releases in one reconcile,
  and helm-controller runs them at its default concurrency (no `--concurrent`
  arg on `deployment/helm-controller`). Batches B and C are separated so the
  one real behaviour change (openclaw's escape) and the one intentional
  template (echo-server) are attributable.
- **Step 0 runs first** (safe-update apply) in whatever window takes this. If
  Step 0 auto-reverts, stop before Batch A: the §2c baseline would include
  Step 0's pod rolls. Take a fresh `--snapshot-workloads` after Step 0
  settles, never before it.
- **`conflicts_with`**: `flux-reconciler-impersonation` (exclusive; same
  HelmReleases, controller identity), `helm-drift-detection` (spec change on
  the same 79 HRs), and `flux-oci-chart-sources` (rewrites `spec.chart`) all
  change how helm-controller treats these very objects. Also listed are four
  plans that edit a file in this batch set (`nextcloud-mcp-0.187.1` → openclaw,
  `absenty-drop-npm-runtime` → absenty, `float-tag-pinning` → makemkv,
  `penpot-cache-9.2` → penpot-cache, `redis-fleet-8.10.2` → 4 redis HRs that it
  also rolls, `makemkv-v26.09.2`, `traccar-6.16.0`, `penpot-chart-1.10.0`), and
  `chart-patches-coredns-reloader-blackbox`, whose Reloader/CoreDNS roll would
  read as `GEN_CHANGED` in §4. If any of those lands first, it does not
  break this plan, because §2d re-renders live values at execution time, but
  it must not share the night. No `kube-prometheus-stack` plan is open
  (`kube-prometheus-stack-91.4.1` executed). A new one must list this plan,
  because §4 reads Prometheus. None of these plans lists this one back yet
  (`--validate` does not check reciprocity), which is a follow-up for their
  owners.
- **HTTPRoutes (gateway/envoy):** about 45 routes change only
  `metadata.labels`. Envoy Gateway re-translates, but listeners, hostnames,
  backends and filters are byte-identical, and there is no route-status flap
  in the paperclip canary. Both gateways are declared because consumers sit on
  both.
- **PVCs** get a label change only: no resize, no rebind, and no
  `volumeHandle` touch. `storage`/`longhorn` is deliberately NOT in
  `touches.shared`.
- **penpot-db / penpot-cache findings** (F-434c3acd, F-afc9bd6a) show as
  `accepted` under AR-038/AR-039. Those ARs were written for the old bitnami
  chart majors (see the report). Both consumers are ordinary label-only Batch A
  members here.
- **Upstream moved on?** If a 5.2.2+ ships before the window, this plan's
  `target` is stale. Re-run §2d with `--to <new>` and refresh the plan in place
  (README "When the held target MOVES"). Do not bump blind.

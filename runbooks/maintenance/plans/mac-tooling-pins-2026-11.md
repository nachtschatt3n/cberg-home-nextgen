---
plan_id: mac-tooling-pins-2026-11
component: mac-toolchain              # local .mise.toml pins (Mac mini + the flate pin shared with CI). NOT a cluster workload.
pr: 296                               # primary; the set is #297 helmfile, #296 helm, #503 flate group. DEFERRED, not merged here, #471 flux2 CLI and #247 talosctl CLI.
kind: config
current: "helm 3.22.1, helmfile 0.171.0, flate 0.6.5 (+ action ref v0.6.5)"
target: "helm 4.3.2, helmfile 1.8.4, flate 0.7.0 (+ action ref v0.7.0)"
update_type: major
risk: medium                          # helmfile and helm are low (measured parity below); flate 0.7.0 is what makes it medium, it breaks the CI render gate that every kubernetes/** PR and the auto-updater G4 lane depend on until the workflow is migrated
est_duration_min: 120                 # pre-checks 25, helmfile 15, helm 20, flate prep+verify 45, slack 15
needs_reboot: false
touches:
  namespaces: []                      # nothing in the cluster changes; every cluster call below is a read
  resources:
    - .mise.toml                                          # 3 pin lines (helm, helmfile, flate)
    - .github/workflows/flux-local.yaml                   # flate action ref + gate command (flate step only)
    - README.md                                           # version lines 620-623
    - runbooks/auto-update-policy.yaml                    # optional explicit flate hold (step 1.2)
    - runbooks/tests/test-flate-gate-mitigations.py       # only if the gate command shape changes
  shared:
    - mac-toolchain                   # every sweep, ops-console session, window agent and runbook script runs these binaries via mise
    - flate-render-gate               # CI check "Flate Render Gate" + auto-update G4 lane
depends_on: []
conflicts_with:
  - kube-prometheus-stack-93.3.0      # soft (plan-reviewer 2026-11-14): it lists this plan back; its chart diffs are helm-rendered, and the engine changes at the helm merge
  - longhorn-1.13.0                   # soft: sun-attended:2026-11-15; do not merge #296 the same day as a window that verifies by a helm-rendered diff
  - talos-linux-1.14.5                # exclusive Sunday slot; it also edits .mise.toml (talosctl pin, its step 3.12) and must not interleave with a toolchain swap
exclusive: false
security_ref: null
capability_change: false              # same behaviour for every consumer after the flate gate migration; helm 4 differences are render-order and null-default handling in LOCAL template output only
rollback_class: git-revert            # old binaries stay installed in ~/.local/share/mise/installs; revert + mise install is instant
finding_refs: []                      # policy-cli finding list --grep helm and --grep flate (2026-11-09): no finding for these pins
review: null
premises:
  - id: pins-still-current
    why: "Steps sed the three exact current pin lines. If someone moved one, re-plan (run from the repo root)."
    run: "grep -c -e '\"aqua:helm/helm\" = \"3.22.1\"' -e '\"aqua:helmfile/helmfile\" = \"0.171.0\"' -e '\"github:home-operations/flate\" = \"0.6.5\"' .mise.toml"
    expect_exact: "3"
  - id: helm-controller-independent
    why: "The claim that cluster HelmReleases are rendered by Flux helm-controller and not by the local helm binary stands on this image tag (helm-controller v1.x embeds its own Helm SDK)."
    run: kubectl get deploy helm-controller -n flux-system -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_contains: "fluxcd/helm-controller:v1."
  - id: flux-distribution-still-2.9.6
    why: "#471 stays deferred only while the cluster distribution is v2.9.6; if it moved, the flux2 CLI pin becomes eligible and this plan is stale."
    run: "grep -c 'version: v2.9.6' kubernetes/apps/flux-system/flux-operator/instance/helm-values.yaml"
    expect_exact: "1"
  - id: gate-still-uses-removed-flag
    why: "The 0.7.0 breakage evidence is that the gate command carries --allow-missing-secrets exactly once; if it was already migrated, section 3 phase 3 shrinks."
    run: "grep -c -e '--allow-missing-secrets' .github/workflows/flux-local.yaml"
    expect_exact: "1"
  - id: nodes-still-talos-1.14.1
    why: "#247 (now 1.14.1 -> 1.14.6) stays deferred until the talos plan has rolled the nodes (that plan is still named 1.14.5 and needs retargeting)."
    run: kubectl get nodes -o jsonpath='{.items[*].status.nodeInfo.osImage}'
    expect_contains: "Talos (v1.14.1)"
status: draft
window: null
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/auto-update.md
  - docs/sops/flux-upgrade.md
generated: "2026-11-09"
---

# mac-tooling-pins-2026-11

An attended Mac runbook, not a cluster maintenance window. Nothing in the cluster changes. It can run in
any attended slot or as an on-demand NOW run; the only scheduling constraint is not to share a day with the
Talos 1.14.5 roll (conflicts_with), because both edit `.mise.toml`.

## 1. Summary & why held

Five open Renovate PRs touch `.mise.toml` pins. Verdict per PR (A = safe to merge at the end of the run once its
checks pass; B = blocked, with what must change first):

| PR | Change | Verdict | Why |
|---|---|---|---|
| #297 | helmfile 0.171.0 -> 1.8.4 (MAJOR) | **A** | Measured byte-identical to the old stack (see 1.2), even paired with the CURRENT helm 3.22.1. Merge FIRST, alone. |
| #296 | helm 3.22.1 -> 4.3.2 (MAJOR) | **A, after #297** | Every consumer verb we use is identical or differs only in explained ways (1.3). Needs helmfile >= 1.2.0 (the release that added Helm 4 support), so it merges second. |
| #503 | flate group 0.6.5 -> 0.7.0 (binary pin + CI action ref) | **B** | 0.7.0 removes `--allow-missing-secrets`; the unchanged gate command exits 1 on `unknown flag`. Needs a workflow migration to `--supply` first (1.1, phase 3). The PR itself is ungated (1.1). |
| #471 | flux2 CLI 2.9.6 -> 2.10.0 | **DEFERRED (B)** | Policy: the CLI never moves ahead of the cluster distribution (`distribution.version: v2.9.6`, `docs/sops/flux-upgrade.md`; policy rule `aqua:fluxcd/flux2`, F-39ab2c30). It follows a flux-fleet upgrade. Premise `flux-distribution-still-2.9.6`. |
| #247 | talosctl CLI 1.14.1 -> 1.14.6 | **DEFERRED (B)** | Owned by `talos-linux-1.14.5` step 3.12 (NOTE: #247 is now 1.14.1 -> 1.14.6 since 2026-11-13; that talos plan must be retargeted to 1.14.6 before the CLI pin moves) (moves LAST, after the nodes roll; sun-attended 2026-11-22). Nodes are still v1.14.1 (premise `nodes-still-talos-1.14.1`). Do not merge here. |

Recommended order: **(1) #297 helmfile, (2) #296 helm, (3) #503 flate after its prep commit.** Reasoning: helmfile
1.8.4 works with helm 3 AND helm 4, so it separates the two majors and gives a clean rollback boundary each.
flate is last because it is the only one that can break something other than the Mac (the CI gate), and it has
real prep work. If the operator wants flate "first" it is still last-to-merge in practice: its prep commit
(phase 3) can land first, but #503 cannot merge until the prep is green.

### 1.0 Who consumes each tool (git grep, 2026-11-09)

- **helm (local binary)**: `runbooks/check-all-versions.py` (`helm search repo -o json`, `helm repo add/remove`,
  `helm show chart oci://...`, parses stdout for `version:`), `runbooks/app-template-render-diff.py`
  (`helm pull`, `helm template --kube-version`, `helm get values -o json`, `helm get manifest`), `revendor.sh` for
  the Envoy Gateway CRDs (`kubernetes/apps/network/envoy-gateway/crds/revendor.sh`), the plan-reviewer and
  upgrade-planner agents' `helm template` chart diffs, and operator `helm list/get`. No `helm install/upgrade/
  registry login` anywhere in runbooks, docs or CI. No GitHub workflow uses mise or helm (the only helm mention
  in `.github/workflows/` is a comment).
- **helmfile**: ONLY `kubernetes/bootstrap/apps/helmfile.yaml` (cilium, coredns, cert-manager, flux-operator,
  flux-instance), driven by `.taskfiles/bootstrap/Taskfile.yaml` task `apps`
  (`helmfile ... apply --skip-diff-on-install --suppress-diff`), plus `runbooks/doc-check.py` which only READS the
  file as text. This is the cluster-rebuild path; it is not exercised on a running cluster.
- **flate**: `.github/workflows/flux-local.yaml` job `flate` (check "Flate Render Gate"), whose result feeds
  `runbooks/auto-update.py` (G4) and Renovate PR gating; `runbooks/tests/test-flate-gate-mitigations.py` asserts the
  workflow shape. It is NOT in `.githooks/pre-commit` and not in the Taskfile. The `.mise.toml` pin exists for
  local reproduction only.
- **Flux helm-controller is independent of all of this.** Live: `deploy/helm-controller` runs
  `ghcr.io/fluxcd/helm-controller:v1.6.5`, which embeds its own Helm SDK; 118 HelmReleases render and apply
  through it. The local helm binary never renders or applies a cluster release. The one coupling is READ-only:
  `helm get values/manifest/list` read the Helm release Secrets helm-controller writes, and Helm 4.3.2 reads them
  identically (1.3).

### 1.1 flate 0.6.5 -> 0.7.0 (why #503 is B)

Release notes for 0.7.0 list 12 BREAKING CHANGES (CHANGELOG at the v0.7.0 tag), including "cli: trim flags to inputs
flate cannot read from Git (#1376)", "cli: supply Secrets and ConfigMaps flate cannot read (#1367)" and "secrets: treat
SOPS-encrypted values as unreadable (#1435)". Measured against a clean `git archive` of HEAD with the exact CI command
(local `--concurrency 8`; the default 56 produced 90 spurious TLS-handshake-timeout failures on this Mac for BOTH versions,
CI is unaffected):

| Run | Result |
|---|---|
| 0.6.5, CI command | `321 passed, 1 failed` (the allowlisted `HelmRelease ai/oc8`) = matches `EXPECTED_FAILURES` |
| 0.7.0, CI command unchanged | `flate error: unknown flag: --allow-missing-secrets`, exit 1, no summary line. The workflow's own no-summary guard turns this into a red job, so it fails LOUD, but it fails every PR touching `kubernetes/**` and freezes the auto-update G4 lane (the F-00235e5c shape). |
| 0.7.0, flag simply dropped | `289 passed, 6 failed`: oc8, mariadb, homepage, esphome, unpoller (`valuesFrom Secret ... not found`) and k8s-gateway (`Delegated domain ('domain') is mandatory`, because the SOPS `cluster-secrets` SECRET_DOMAIN is now unreadable). |
| 0.7.0 + a dummy `--supply` file for those 6 | `292 passed, 3 failed`: oc8 (`secrets.secretKek is required`, a second required key), unpoller (my dummy value was wrong), k8s-gateway (the supply did not reach SECRET_DOMAIN; needs the real substituteFrom name). Converges, but needs iteration: this is the prep work, not a finished fix. |

Object totals also moved (322 vs 295): supplied objects are no longer counted. Any threshold in tooling that reads the
total must be re-baselined.

Gate-integrity facts for the operator:
- #503 changes only `.mise.toml` and `.github/workflows/flux-local.yaml`; the workflow's `paths:` filter is
  `kubernetes/apps/**` and `kubernetes/flux/**`, so **no gate ran on the PR** (only `Labeler`). It would show green and
  merge, and the NEXT kubernetes PR would be the first to hit the dead flag.
- The auto-updater holds #503 today only by accident: gate `parse`, "title not in `update <dep> ( x -> y )` shape"
  (the group title). If Renovate ever retitles it, nothing else stops a merge. Phase 1 adds an explicit hold.

### 1.2 helmfile 0.171.0 -> 1.8.4 (#297)

`helmfile -f kubernetes/bootstrap/apps/helmfile.yaml template` (isolated `HELM_*` dirs, real charts from the network):
helmfile 0.171.0 + helm 3.22.1 versus helmfile 1.8.4 + helm 3.22.1: **0 differing lines** after dropping blank lines and
`# Source:` comments. helmfile v1.0 breaking changes that could have applied (v1 state-file syntax needing `.gotmpl` for
templated files, removed subcommands/flags) do not: our file templates only a values PATH via `requiredEnv`, which
1.8.4 accepts unchanged (the run above is the proof). `helmfile lint` under 1.8.4 + helm 4.3.2: `1 chart(s) linted,
0 chart(s) failed`. helmfile 1.2.0 release note: "add Helm 4 support while maintaining Helm 3 compatibility" (#2262);
1.8.4 maps `force` to `--force-replace` when it detects Helm 4 (`pkg/state/state.go` at v1.8.4, line 4366, re-verified 2026-11-14).
Side effects: 1.8.4 keeps a shared chart cache at `~/Library/Caches/helmfile` (outside the repo); it prints
"Skipping refresh ... shared cache" lines. `helmDefaults.force: true` plus `wait: true` in our file is only exercised by
`apply`, which cannot be tested without a cluster rebuild (residual risk, 1.4).

### 1.3 helm 3.22.1 -> 4.3.2 (#296), what changed and what we measured

Upstream (helm.sh changelog, v4.0.0 release notes): `--atomic` -> `--rollback-on-failure` (deprecated `--atomic` kept
on install), `--force` -> `--force-replace`, server-side apply is the default for install/upgrade
(`--server-side` default true, `--force-conflicts`), `--wait` takes a strategy (`watcher` default), plugins redesigned
(`--verify` on by default; unsigned plugin install needs `--verify=false`), post-renderers became plugins, removed
`--create-pods`, `repo add --no-update`, `helm version --client`, `status --show-desc`; `helm list` shows all by
default; implicit lint of the cwd removed; template output adds a newline after doc separators; content cache.
None of the removed flags appear in our scripts (grep). Measured with the real binaries, same charts/values/kube-version:

| Check | helm 3.22.1 vs 4.3.2 |
|---|---|
| `helm list -A -o json` (live) | 118 vs 118 releases (2026-11-14; was 117), read from helm-controller's release Secrets |
| `helm get values home-assistant -n home-automation -o json` | byte-identical (`cmp`) |
| `helm get manifest home-assistant -n home-automation` | byte-identical |
| `helm search repo grafana/grafana -o json` | identical |
| `helm show chart oci://ghcr.io/bjw-s-labs/helm/app-template --version 5.3.0` | identical stdout (`Pulled:`/`Digest:` go to stderr in both, so check-all-versions.py's `version:` parse is unaffected) |
| `helm repo add/remove` | works |
| `app-template-render-diff.py --from 5.3.0 --to 5.3.0` over all 66 consumers | **identical logs**, `LABEL_ONLY=66`, flags `FIDELITY=1 TPL=2`, `GATE_FAIL ai/openclaw` under BOTH versions (a pre-existing fidelity flag, not caused by helm 4) |
| `helm template` grafana 14.0.1, our values | 0 differing non-blank lines |
| `helm template` app-template 5.3.0 (home-assistant values) | 1 line: a leading `---` |
| `helm template` kube-prometheus-stack 92.11.1, our values (NOT re-measured on 4.3.2: the live chart has since moved, so this row is dated 2026-11-09 and is a spot check, not a gate) | 109 vs 109 documents, **equal as sets**; only ORDER differs (helm 4 installs the MutatingWebhookConfiguration earlier) |
| bootstrap helmfile `template` (cert-manager) | ServiceMonitor document moves position; content equal |
| `helm template` **cilium 1.20.4**, our values | **REAL CONTENT DIFF (finding F1)** |
| `helm plugin install .../helm-diff` | needs `--verify=false` on Helm 4 (then installs 3.15.15 and `helmfile diff` runs, rc 0) |

**F1: Helm 4 drops chart-default `null` values from the computed values, so `hasKey` templates change.** Cilium's
values.yaml has `verbose: ~`, `nodePort.addresses: ~`; its templates use `{{- if hasKey .Values.debug "verbose" }}`.
Helm 3 renders `debug-verbose: ""`, `policy-cidr-match-mode: ""`, `nodeport-addresses: ""` and the agent arg
`--k8s-api-server-urls=`; Helm 4 omits all four, which changes the ConfigMap checksum annotation
(`64828a20...` -> `29272518...`) on the agent and operator. Effect: ONLY a local helm 4 render or a future
helmfile bootstrap `apply` is affected; the live cluster runs helm-controller (Helm 3 SDK) and does not change.
Consequence to remember: a rendered diff of a chart that uses `hasKey` on a null default (cilium, possibly others) made
with helm 4 will not match the live manifest rendered by helm-controller. Fidelity checks in
`app-template-render-diff.py` (app-template has no such pattern) are unaffected. A cilium bootstrap re-run after this
change would roll cilium once on the checksum change; harmless but expected.

### 1.5 Re-measurement on the re-targeted PRs (2026-11-14: helm 4.3.2, helmfile 1.8.4)

Renovate re-targeted #296 (4.3.1 -> 4.3.2) and #297 (1.8.3 -> 1.8.4) on 2026-11-13. Re-measured with the downloaded upstream
binaries in a scratch directory (no mise install, repo pin untouched, isolated `HELM_*` dirs):
- helmfile 1.8.4 + helm 3.22.1 bootstrap `template` vs helmfile 0.171.0 + helm 3.22.1: **0 differing lines** (18802 raw lines each, 18517 normalised, rc 0 both).
- `helmfile lint` under 1.8.4 + helm 4.3.2: `1 chart(s) linted, 0 chart(s) failed`. `force` -> `--force-replace` on Helm 4 re-verified at v1.8.4 `pkg/state/state.go` line 4366.
- helm 4.3.2 vs 3.22.1: `helm get values/manifest home-assistant` byte-identical (2934 B / 194 lines), `helm list -A` 118 vs 118 releases.
- `app-template-render-diff.py --from 5.3.0 --to 5.3.0`: identical under both, `TOTALS LABEL_ONLY=66   FLAGS FIDELITY=1 TPL=2`, `GATE_FAIL ai/openclaw` under both (consumers now 66).
- F1 reproduced on 4.3.2: the same four lines drop (`debug-verbose`, `policy-cidr-match-mode`, `nodeport-addresses`, `--k8s-api-server-urls=`), the same two cilium checksum annotations change (`64828a20...` -> `29272518...`), ServiceMonitor document moves position (4 ServiceMonitor documents both sides).
- Release notes of 1.8.4 (17 items: dependency bumps, `--state-values-set` fixes, release-dependency `condition`/default-version, chartification skip) and helm 4.3.2 (docs + registry transport fix) show nothing in the surface we use; not a substitute for the measurements above.
- NOT re-measured: the kube-prometheus-stack/grafana template rows of 1.3 (dated 2026-11-09), and the absolute run-all count on the new versions (see G2).

### 1.4 Residual risks (not testable read-only)

- `helmfile apply` under helm 4 (`force: true` -> `--force-replace` with SSA default): upstream code handles the
  mapping; the live interaction is only provable during an actual bootstrap. Mitigation: before the next cluster rebuild
  run `helmfile diff` and one `apply --dry-run`-class check, see section 2 pre-check 9.
- `helm-diff` is not installed on this Mac today (`helm plugin list` is empty), so `task bootstrap:apps` already
  needs it. Not caused by this change; documented here because the install form changes on Helm 4 (`--verify=false`).
- The 210-suite `runbooks/tests/run-all.sh` has little helm coverage; its parity (below) proves "nothing else broke",
  not "helm 4 correct". The consumer-level table above is the real evidence.

## 2. Pre-checks

Run from the repo root on the Mac, cluster read-only. All commands exist (verified 2026-11-09).

1. Clean tree for the files this plan edits: `git status --short .mise.toml .github/workflows/flux-local.yaml README.md runbooks/auto-update-policy.yaml` prints nothing.
2. Premises: `.venv/bin/python3 runbooks/plan-premises.py mac-tooling-pins-2026-11 --require-premises` prints PASS.
3. Not the Talos day: `.venv/bin/python3 runbooks/maintenance-plan.py --open | grep -i talos-linux-1.14.5` and confirm its window is not today and the nodes are not mid-roll (`kubectl get nodes` all Ready, one Talos version).
4. No competing PRs on the same lines: `gh pr list --state open --limit 100 --json number,title,files --jq '.[]|select(any(.files[]; .path==".mise.toml"))|"#\(.number) \(.title)"'` lists the PRs touching `.mise.toml`: expect #296/#297/#471/#503/#247 plus unrelated pin PRs (measured 2026-11-14: also #529 cloudflared, #271 python); merge conflicts in `.mise.toml` are the usual failure, so merge the others first or rebase. (The old `--search "mise.toml in:path"` form does not search file paths and returned an unrelated PR.)
5. Install the new binaries WITHOUT touching the repo pin: `cd /tmp && mise install aqua:helm/helm@4.3.2 aqua:helmfile/helmfile@1.8.4 github:home-operations/flate@0.7.0` (old versions stay installed).
6. Baseline of the old stack for later diffing (scratch dir `$W=$(mktemp -d)`): bootstrap template, `mkdir $W/{old,new}`; with `HELM_CACHE_HOME HELM_CONFIG_HOME HELM_DATA_HOME` pointed into `$W/old` and `KUBERNETES_DIR=$PWD/kubernetes`, run `mise x aqua:helm/helm@3.22.1 aqua:helmfile/helmfile@0.171.0 -- helmfile -f kubernetes/bootstrap/apps/helmfile.yaml template > $W/old/t.yaml`.
7. Baseline of the render fleet: `.venv/bin/python3 runbooks/app-template-render-diff.py --from 5.3.0 --to 5.3.0 --out $W/atrd-old -j 4 | tail -3` expecting `TOTALS LABEL_ONLY=66   FLAGS FIDELITY=1 TPL=2` (record the exact tail; re-measure the count, the fleet changes).
8. Baseline of the test suite on the old stack: `bash runbooks/tests/run-all.sh -q` ends `210 audit test suites passed` (re-counted 2026-11-14: 210, was 209; record it). Run it in a scratch `rsync` copy of the repo if other sessions are active in the worktree.
9. Before the next cluster rebuild (NOT now, record only): install helm-diff on the new stack, `helm plugin install https://github.com/databus23/helm-diff --verify=false`, then `helmfile ... diff` must run rc 0.
10. flate baseline with the CI command and `--concurrency 8` against a `git archive HEAD` copy that has a `git init` (0.7.0 needs a git root): expect `321 passed` / `1 failed` / `HelmRelease ai/oc8` (numbers drift with the fleet; the failing set must equal `EXPECTED_FAILURES`).

## 3. Steps

Commit style is squash; use `git commit --only <paths>` and verify `git log -1 --format=%s` before pushing
(shared worktree). Do not use `git add -A`.

### Phase 1: hold flate explicitly (before anything else)

1.1 Confirm #503 is held and why: `.venv/bin/python3 runbooks/auto-update.py --json | python3 -c "import sys,json; print([h for h in json.load(sys.stdin)['held'] if h['number']==503])"` shows `gate: parse`.
1.2 Add an explicit deny rule so a retitle cannot slip it through (edit `runbooks/auto-update-policy.yaml`, new rule above the generic ones):
`match: "github:home-operations/flate"`, reason: "0.7.0 removed --allow-missing-secrets; the CI gate command must be migrated to --supply first (plan mac-tooling-pins-2026-11). Remove this rule in the commit that lands the migration." Re-run 1.1 and confirm the verdict is now `gate: policy`.

### Phase 2: #297 helmfile 1.8.4, then #296 helm 4.3.2

2.1 Merge #297 only: `gh pr merge 297 --squash`, then `git pull --ff-only`.
2.2 `mise install` (reads the new `.mise.toml`), then `mise x -- helmfile --version` prints `helmfile version 1.8.4` and `mise x -- helm version --short` still prints `v3.22.1`.
2.3 Gate (section 4, G1). Stop here and revert if it fails.
2.4 Merge #296: `gh pr merge 296 --squash`, `git pull --ff-only`, `mise install`, `mise x -- helm version --short` prints `v4.3.2`.
2.5 Update the version text in README.md lines 620-623 (`helm 3.22.1` -> `helm 4.3.2`, `helmfile 0.171.0` -> `helmfile 1.8.4`) in a docs commit. Dry-tested BSD sed on a scratch copy of `.mise.toml` gives, for the equivalent pin edit: `-"aqua:helm/helm" = "3.22.1"` / `+"aqua:helm/helm" = "4.3.2"`; for README use:
`sed -i '' -e 's|\*\*helm 3\.22\.1\*\*|**helm 4.3.2**|' -e 's|\*\*helmfile 0\.171\.0\*\*|**helmfile 1.8.4**|' README.md` and check with `git diff --stat README.md` showing 2 changed lines.
2.6 Gate (section 4, G2).
2.7 Add to `docs/sops/application-update.md` or the plan-reviewer notes one line: "helm 4 drops null chart defaults, so a local render of a hasKey-on-null chart (cilium) differs from the live manifest (F1)". The reviewer agents read helm output.

### Phase 3: flate 0.7.0 prep, then #503 (BLOCKED until this is green)

3.1 Create the supply file in the repo (dummy, non-secret values only) OUTSIDE the render path, at `.github/flate-supply.yaml`. Start from the six dummy Secrets used in the 1.1 experiment (cluster-secrets SECRET_DOMAIN; oc8-values incl. `secrets.jwtSecret` and `secrets.secretKek`; homepage-values; esphome-values; unpoller-credentials with a real-shaped `upConfig` value; mariadb with the four keys) and iterate until the only failing release is `HelmRelease ai/oc8`'s allowlisted state or it renders. Every value is a placeholder; never copy a real value.
3.2 In `.github/workflows/flux-local.yaml`: delete `--allow-missing-secrets`, add `--supply .github/flate-supply.yaml`, bump `home-operations/flate/action@v0.6.5` -> `@v0.7.0` (exact sed, dry-tested on a scratch copy: `sed -i '' -e 's|home-operations/flate/action@v0\.6\.5|home-operations/flate/action@v0.7.0|' .github/workflows/flux-local.yaml` yields `-        uses: home-operations/flate/action@v0.6.5` / `+        uses: home-operations/flate/action@v0.7.0`), refresh the two comments that quote `@v0.6.5`, and re-derive `EXPECTED_FAILURES` from the 0.7.0 run.
3.3 Add `.github/flate-supply.yaml` to the workflow `paths:` filter AND add `.mise.toml` and `.github/workflows/flux-local.yaml` to it, so a change to the gate itself runs the gate (today it does not; see 1.1).
3.4 `.venv/bin/python3 runbooks/tests/test-flate-gate-mitigations.py` must pass; update its assertions for the new command shape if (and only if) they pin the removed flag.
3.5 Push the prep as a PR (not main), watch `Flate Render Gate` go green on it, then rebase/merge #503 (`.mise.toml` pin + the same action ref the prep already bumped; resolve the duplicate hunk), remove the phase 1.2 deny rule in the same merge, and run the gate G3.

### Phase 4: leave deferred

4.1 #471 and #247 stay open and untouched. Add no rule for #247 (already covered by the `aqua:siderolabs/talos` rule); confirm both still show `gate: policy` in `auto-update.py --json`.

## 4. Verification

Every gate below can fail; the failure signature it guards against is stated.

**G1 (after helmfile 1.8.4, helm still 3.22.1)**
- CONTENTS ASSERTION: the rendered bootstrap manifests are unchanged by helmfile 1.8.4 — measured by repeating pre-check 6 with `mise x aqua:helm/helm@3.22.1 aqua:helmfile/helmfile@1.8.4`, normalising both outputs with `grep -v '^[[:space:]]*$' | grep -v '^# Source'`, and `diff old new | wc -l` must print `0` (measured 0 on 2026-11-09; a changed chart or values path would print a positive count, an empty output file would print a large diff, so it cannot pass on emptiness; also assert the new file has >15000 lines).
- `mise x -- helmfile -f kubernetes/bootstrap/apps/helmfile.yaml lint` ends `1 chart(s) linted, 0 chart(s) failed` (case-insensitive grep for `failed` with a non-zero count must NOT match `0 chart(s) failed`; read the digits).
- CONTROL: none of these gates read Prometheus, so no kube-prometheus-stack bump conflicts with this plan; the instruments are the commands themselves.

**G2 (after helm 4.3.2)**
- CONTENTS ASSERTION: live release data reads identically — measured by `helm get values home-assistant -n home-automation -o json` and `helm get manifest ...` under 3.22.1 and 4.3.2, `cmp` exits 0 for both and the files are non-empty (values 2934 bytes, manifest 194 lines on 2026-11-09; an empty read on both sides would pass `cmp`, so assert `wc -c` > 1000).
- CONTENTS ASSERTION: the app-template fleet render is unchanged — measured by repeating pre-check 7 with helm 4 first on PATH; the `TOTALS` line must equal the pre-check 7 line exactly and the consumer count must equal `consumers=66`-style baseline; a helm 4 render difference would show as `POD_TEMPLATE`/`OTHER` or a larger FIDELITY count.
- F1 recorded: `helm template cilium ... ` under 4.3.2 omits exactly four lines (`debug-verbose`, `policy-cidr-match-mode`, `nodeport-addresses`, `--k8s-api-server-urls=`). This is the EXPECTED diff; anything beyond those four plus the two checksum lines and blank/order noise is a regression.
- `helm search repo`, `helm show chart oci://ghcr.io/bjw-s-labs/helm/app-template --version 5.3.0 2>/dev/null | grep -c '^version:'` prints `1` (a `Pulled:` line on stdout would not change that count but would break YAML parsing, so also assert the first stdout line is not `Pulled`).
- `.venv/bin/python3 runbooks/check-all-versions.py` completes and its degraded list contains no `helm` entries that were not present in the pre-change baseline run.
- `bash runbooks/tests/run-all.sh -q` ends `210 audit test suites passed` (same count as pre-check 8). Measured parity on 2026-11-14 on helm 4.3.2 + helmfile 1.8.4: old stack 204 passed / 6 failed, new stack 204 passed / 6 failed, the SAME six suites (coverage-plan-also-covers, doc-check-retired-phrases, pii-needle-not-inert, precommit-age-key-pattern, s3-env-var-name-rhs, s3-secret-named-file-scope), in a scratch rsync copy WITHOUT `.git`, so those six are copy artifacts and the absolute 210/210 was NOT proven on the new versions (only old==new parity). Re-run in a real checkout before merge (see section 1.5).

**G3 (after flate 0.7.0)**
- CONTENTS ASSERTION: the gate still renders the whole fleet — measured by the exact new CI command on a `git archive` + `git init` copy, summary line must show `passed` > 280 and `failed` equal to the new allowlist size; a gate that renders nothing prints `0 passed`, and the workflow's `[0-9]+ passed` guard exits 1.
- On the prep PR, `gh pr checks <n> --json name,state` lists `Flate Render Gate` as `SUCCESS`; a PR touching only the gate files must now trigger it (3.3), otherwise this check shows no run and the step has not been satisfied.
- Negative control: on a scratch branch, break one HelmRelease chart version and confirm `Flate Render Gate` goes RED (a gate that cannot fail proves nothing).
- `auto-update.py --json` shows no new `held` reason of the form "check missing/stale" for open PRs after the merge.

## 5. Rollback

All three tools are local pins; the old binaries remain installed under `~/.local/share/mise/installs/`.

- Per PR: `git revert <merge-sha> && git push`, then `mise install`, then confirm `mise x -- helm version --short` / `helmfile --version` / `flate --version` show the old versions (3.22.1 / 0.171.0 / 0.6.5). Cluster: nothing to restore.
- flate: revert BOTH the `.mise.toml` pin and the workflow edits (`git revert` of the prep merge and of #503) so the action ref and pin stay in lockstep (the `.mise.toml` comment requires it); then confirm the next kubernetes PR's `Flate Render Gate` returns to `321 passed / 1 failed` shape. If the gate is red on `main` PRs in the meantime, the auto-update G4 lane is frozen: revert first, debug second.
- Remove the phase 1.2 deny rule only after a successful flate landing; keep it when rolling back flate.
- helm-diff plugin installed during checks lives in an isolated `HELM_DATA_HOME`; nothing to uninstall.
- Post-rollback check: `bash runbooks/tests/run-all.sh -q` ends with the pre-check 8 count.

## 6. Interference notes

- `conflicts_with: talos-linux-1.14.5` (exclusive Sunday slot, also edits `.mise.toml`). Its reciprocal entry was added 2026-11-14 (plan-reviewer blocker 3). `kube-prometheus-stack-93.3.0` already lists this plan; the reverse refs for it and `longhorn-1.13.0` are soft and not added to those plans. `--validate` checks only that refs resolve.
- No other open plan touches helm/helmfile/flate pins. `cli-tool-pins` is `superseded` (it listed helm and helmfile as out-of-scope majors; this plan is the "narrow successor" for those two).
- Every plan whose verification runs `helm template`/`app-template-render-diff.py` (app-template bumps, plan-reviewer chart diffs) changes engine at the helm merge. Do not run this plan the same evening as a window whose plans verify through a helm-rendered diff; the helm 4 ordering and null-default differences (F1) would confuse a baseline taken on helm 3.
- While phase 3 is in flight the repo has an open gate-migration PR: do not merge Renovate PRs touching `kubernetes/**` until `Flate Render Gate` is green on `main` again, or the G4 lane reads a stale red/absent gate.
- Findings to carry back (repo corrections, not applied here): (1) `.github/workflows/flux-local.yaml` `paths:` omits the gate's own files; (2) `helm-diff` is a hidden prerequisite of `task bootstrap:apps` and is undocumented; (3) the auto-updater holds the flate group only by a title-parse accident.

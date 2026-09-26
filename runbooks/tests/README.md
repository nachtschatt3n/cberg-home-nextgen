# Sweep tooling tests

Plain-Python tests for the audit scripts. There is no CI stage, but
`.githooks/pre-commit` DOES run `runbooks/tests/run-all.sh` when a commit stages
audit tooling — so a staged change to a covered script gates on these. That glob
is `runbooks/tests/test-*.py` plus `test-*.sh`; it does **not** reach
`runbooks/lib/test_*.py`, which nothing runs automatically. Run the tests in the
same commit as the code they cover regardless — the hook only fires on paths it
recognises as audit tooling.

Each file is dual-mode: run it directly for a readable PASS/FAIL list, or under
pytest.

```bash
# one file
python3 runbooks/tests/test-ar-suppression-guard.py

# everything here and in runbooks/lib/
python3 -m pytest runbooks/tests runbooks/lib -q

# no-pytest fallback
for t in runbooks/tests/test-*.py runbooks/lib/test_*.py; do
    echo "== $t"; python3 "$t" || echo "FAILED: $t"
done
```

All of them are hermetic: fakes and fixtures only, no cluster, no database, no
network — with TWO deliberate exceptions, both reading the repo's own tracked
files rather than any live system. `test-helmrelease-chartref-shape.py` parses
the real `kubernetes/` manifests, because a chart-source parser validated only
on synthetic input is not validated (`docs/sops/audit-script-correctness.md`);
it reads versions OUT of those manifests instead of hardcoding them, so a
routine chart bump cannot turn this fail-closed gate into a blocked commit.
`test-cred-suppressor-scoping.py` also
scans every tracked file with the pre-commit password guard, because the
operational cost of that detector IS how many files it would block, and a number
measured once in a terminal rots. If it fails, a tracked file would now block
commits: fix the file or the detector's scoping — do NOT delete the assertion. Anything that needs the live register is a `--dry-run` script, not a
test — see `runbooks/refingerprint-findings.py`.

## `runbooks/tests/`

| File | Covers | Run it when you touch |
|---|---|---|
| `test-ar-suppression-guard.py` | The two classes of finding exempt from AR substring suppression: audit-integrity (`risk_nature` / `audit_*` subsection) and self-reference (`metadata.ar_id`). Also asserts the operator-facing exemption count is real. | `_apply_ar_suppression` in `sweep-run.py`; anything about AR matching |
| `test-autoclose-component-scope.py` | The PER-COMPONENT coverage veto: `component_key` / `finding_matches_component` / `partition_by_uncovered`, one uncovered leaf still letting the section close the rest, a non-attributable failure still vetoing section-wide, the `MAX_SCOPED_COMPONENTS` / `MAX_UNCOVERED_FRACTION` revert, and the 429-only retry backoff | `mark_uncovered` / `DegradationLog.apply` in `findings_writer.py`; the `component=` call sites in `check-all-versions.py`; the backstop in `sweep-run.py` |
| `test-coverage-lane-safety.py` | The AUTO-lane safety rules in `coverage.py` — pre-release/beta channels, 0.x release-line moves, chart↔image lockstep, image-matched REBUILD, and the truncated-tag dedupe | `assign_lane` / `channel_hold` / `_apply_lockstep` / `is_self_built` in `runbooks/coverage.py` |
| `test-coverage-plan-match.py` | `coverage.py` ↔ maintenance-plan matching | `runbooks/coverage.py`, plan discovery |
| `test-helmrelease-chartref-shape.py` | Both HelmRelease chart-source shapes — inline `spec.chart.spec` AND `spec.chartRef` → OCIRepository/HelmChart. Pins that a digest-pinned OCI ref resolves to the TAG (the digest is an immutability pin, not a version), that the classic shape is untouched, and that an unreadable shape lands in the loud `unresolved` bucket instead of returning empty strings | `parse_helmrelease` / `load_chart_sources` / `check_chart_freshness` / `get_latest_chart_version` in `check-all-versions.py`; `_chart_source_for` in `coverage.py` |
| `test-osv-coverage.py` | OSV ecosystem mapping and the coverage-gap accounting | OSV lookups in `security-check.py` |
| `test-pick-latest-semver-tag.py` | `_pick_latest_semver_tag` — variant filtering, cross-variant proposals, downgrade rejection | tag selection in `check-all-versions.py` |
| `test-s3-env-var-name-rhs.py` | `_ENV_VAR_NAME_RHS` — the s3 filter separating an environment-variable NAME on the right-hand side from real credential material. Asserts both directions: the F-8a52ddd9 docstring stays suppressed, value-shaped secrets still fire. | the s3 credential-keyword pipeline in `security-check.py` |
| `test-tag-oracle-veto-discriminator.py` | `_is_structurally_slow` — whether a defeated tag listing is a registry's inherent pace (no veto) or a blip (veto). Pinned to measured s/page for docker.elastic.co vs GHCR. | the OCI tag-listing budget / timeout / exception branches in `check-all-versions.py` |
| `test-trivy-cache-coverage.py` | Trivy cache hit/miss accounting vs the running-image inventory | the s4 scan-target policy or cache logic |
| `test-trivy-tally.py` | Two classes. `KernelHeaderExclusionTest` — per-image Trivy tally arithmetic and the header-package exclusion. `GoPseudoVersionTest` — `classify_pseudo_version`, i.e. FIX-STATUS determination when the installed version is a Go pseudo-version: each of the three routes in both directions, the tag guards (bare integer, CalVer, pre-release), the branch-aware fix bar, the owner+name main-module match, and that an undetermined-only image never reports clean | `tally_trivy_report`, `classify_pseudo_version`, `_TRIVY_TALLY_VERSION` or the fix/no-fix/undetermined classification in `security-check.py` |
| `test-cred-suppressor-scoping.py` | Both credential detectors' suppressor SCOPING: shape rules judged against the VALUE only, scaffolding words against the CONTEXT only (the line minus its values), never the whole file. Carries the witness that survived 4.7 months, with the pre-fix logic transcribed so the witness is proven to be a real regression witness. Also asserts the awk guard trips on zero tracked files. | `_hist_cred_hit_suppressed` in `security-check.py`; `.githooks/lib/password-guard.awk`; the s3 grep chain |
| `test-disclosure-residual-claims.py` | The residual-claim tier of the commit-message disclosure hook — phrasing that describes what still awaits an upstream release, distinct from the count and advisory-ID tiers | `.githooks/lib/disclosure_patterns.py` or the residual-claim wording set |
| `test-outpost-ingress-suppression.py` | The Authentik outpost audit. Load-bearing assertion: it reads the LIVE outpost list, never a repo grep — a repo grep enumerates the outposts we *declared*, which is how the managed `authentik Embedded Outpost` sat on `[]` invisibly through every previous audit. Also pins: `managed` outposts are never exempt, non-Kubernetes service connections are out of scope (no Ingress to publish), and neither a failed probe nor an empty list may read as clean | `s12_authentik_outposts` in `security-check.py` |
| `test-window-run-running-row.py` | window-run-record.py running/finalize target selection, stuck detection, CLI compatibility | touching window-run-record.py or maintenance-plan.py liveness |
| `test-scheduler-premises-gate.py` | window-scheduler.py fail-closed premises gate (premises_verdict, injected checker) | touching window-scheduler.py or plan-premises.py output |
| `test-run-now.py` | runbooks/run-now.py on-demand NOW-run preflight: every status/needs_reboot/ceiling/depends_on refusal, approvals-exec failure = NO approval (unless `--operator-go`), window-scoped approvals, fail-closed premises, deterministic serial order with conflict-pair `settle_before` and per-step `depends_on_in_run`, plans already stamped `now:<today>` refused without `--operator-go --resume`, durable `running_row_notes` consent string, frontmatter-only all-or-nothing `stamp` (incl. against every real plan file) | touching run-now.py, the `on_demand:` block, or plan frontmatter shape |
| `test-openclaw-run-now-skill.py` | The OpenClaw side of the NOW trigger, imported from the COMMITTED SOPS-encrypted `openclaw-skills` ConfigMap (decrypted to a private temp dir): `maintenance-window run-now` marker + busy-console refusal + no /clear, retired window ids refused, `run-now` refuses while ANY open `now` window_runs row exists, whatever its run_date (exit 10, fake psql over a fake table; the reviewer's yesterday-only open row, no run_date predicate, refusal names run_date + started_at; unreadable ledger/row exit 7), `run/retry --window now` refused, `home-operation run --issue` EXACT-key only (wrong-issue substring repro exits 3, records nothing) + approval + `now:<today>` window + all-or-nothing failures + failed-dispatch undo (re-scoped window restored, new approval withdrawn, a prior defer restored exactly) + `--no-push` writes nothing + tick expiry. Exception to "hermetic": needs sops + the age key — without them it prints a loud SKIP and returns 0 | touching `home-operation.py` / `maintenance-window.py` in `skills-configmap.sops.yaml` |
| `test-openclaw-console-delivery.py` | The ops-console DELIVERY path in `maintenance-window.py` + `operation.py` (from the COMMITTED `openclaw-skills` ConfigMap): `classify_pane` against fixture panes (idle/draft/placeholder, spinner, `Waiting for N background agents`, question menu, permission prompt, `/resume` list, exhausted-idle/-draft/-busy/-unclear) and byte-identical in both skills; `run` refuses exit 8 with nothing typed on busy/menu; cron poll for the Step 0 running row (12 none within budget, 11 unreadable, pre-existing row ignored, say-so no poll); exhausted-idle auto-`/clear` exactly once then deliver, every other exhausted state / manual / run-now exit 4; `classify` read-only; no `${` (Flux postBuild). Needs sops + the age key — loud SKIP otherwise `retry` of a LOST occurrence (no window_runs row) into busy/menu exits 8 and exhausted-unclearable exits 4 with LOST wording, nothing typed; a row present is an exit-0 no-op (2026-09-26). | touching `classify_pane`, delivery or poll logic in `maintenance-window.py` / `operation.py` in `skills-configmap.sops.yaml` |
| `test-window-liveness-now-covers-nightly.py` | `maintenance-plan.py:nightly_covered_by_on_demand()`: a completed, non-aborted `now`/ad-hoc `window_runs` row covers that Europe/Berlin day's `nightly`; running / aborted / other-date rows do not; sat/sun never covered; end-to-end through `window_liveness_report()` (the `--liveness-metrics` / Pushgateway path). | touching window liveness in `maintenance-plan.py` or the `window_runs` schema |
| `test-window-crons-retry.py` | window-crons.py retry cron expression derivation and --check parity | touching window-crons.py or maintenance-windows.yaml |
| `test-s3-placeholder-value-shape.py` | The scaffolding-PHRASE shape rule in `_hist_cred_hit_suppressed` (F-54cbd530): a multi-word, digit-free, anchor-bearing template phrase goes quiet; every neighbour with a digit, a case break, a missing anchor, or a bare word keeps firing. Fixtures assembled at runtime. STRAW: the module's own rule set minus the two new branches fires on all five 2026-09-10 rows | `_placeholder_scaffold_value`, `_bare_placeholder_with_env_reference`, `_PLACEHOLDER_ANCHORS`, or the final `return all(...)` of `_hist_cred_hit_suppressed` in `security-check.py` |
| `test-s3-secret-named-file-content.py` | The CONTENT detector for secret-named files (F-fd37ba9c): every committed version of the path is read and judged value-scoped, in a throwaway git repo built at runtime; material → the content title (VULN), references → the name-only title (LOW); PEM blocks count; env-var NAMES are confirmed through the injected oracle; a failed git read is None, never []. STRAW: the filename grep rates the material and reference files identically | `secret_named_file_content_hits` or the secret-named-file loop in `s3_git_history` |
| `test-flux-source-hygiene.py` | Flux source hygiene (F-e805174a): scheme, consumers, GitHub namespace ownership, branch-tracking GitRepositories — run over the REAL repo manifests through `flux_objects_from_repo` (population-guarded) and over a fixture holding every defect, each proven removable. Pins the three controls (resolver via the root source, oracle via octocat/fluxcd, non-empty inventory) refusing to emit verdicts, and the section wiring incl. live-vs-git drift | `flux_source_hygiene`, `flux_objects_from_repo`, `flux_consumer_ref`, `github_owner_of`, `_s10_flux_source_hygiene` in `security-check.py` |
| `test-wazuh-agent-flooding.py` | The per-agent event-queue overflow slice in s13 (F-9952c59e): no volume floor, an ENUMERATING query (term on `rule.groups` + terms agg on `agent.name`), NOT MEASURED on failure, never a bare zero. STRAW: the group-level triage on a quiet day (3 events) reports nothing | `flag_wazuh_flooding_agents` or slice 3c of `s13_wazuh_siem` in `security-check.py` |
| `test-slo-declared-burn-windows.py` | slo-check evaluates the windows the catalog DECLARES (F-7f596ea3): `burn_window_labels`, `_evaluate_prom` querying every declared long+short window, `fast_burns` comparing the DECLARED per-SLO threshold, `compute()` filling the 1h/6h columns by label, `defects()` over every window. STRAW: the transcribed hardcoded 1h/6h evaluator never sees the 3d breach | `_evaluate_prom` / `fast_burns` in `slo-check.py`; `compute` / `defects` / `SloSnapshot.burn_rates` in `lib/slo/calc.py` |
| `test-render-board-ran-discriminator.py` | How the board decides a section REPORTED (F-bfb9ec80): rows → writer completion record → SLO snapshots in the cycle window → reconcile declaration → gap, with the INCOMPLETE veto as a suffix; `collect()` parses the notes and bounds the snapshot window by the next cycle's start. STRAW: the rows-or-declared rule renders the 2026-09-17 doc and slo sections as gaps | `section_evidence` / `section_line` / `collect()` in `render-board.py` |
| `test-findings-writer-completed-record.py` | `FindingsWriter._persist_completed` (F-bfb9ec80): written once, last, on every complete close — merged onto the shared row, withheld for a dry run and for a zero-emit run the circuit breaker REFUSED, recorded alongside an INCOMPLETE veto. STRAW: the rows-only rule says a clean close never reported | `close()` / `_persist_completed` in `lib/findings_writer.py` |

## `runbooks/lib/`

Colocated with the module they cover, per the `lib/` convention.

| File | Covers |
|---|---|
| `test_findings_writer_autoclose.py` | The auto-close safety gates — `section_complete`, orchestrated-run, the incomplete veto, the zero-emit breaker — plus section scoping, the run-start bound, and the uncovered-component scope (gate 3b; narrow contract in `tests/test-autoclose-component-scope.py`) |
| `test_findings_writer_fingerprint.py` | Finding **identity**: AR tags must not affect it, `_KIND_MARKERS` must still separate the three answers an image's findings can give — "there is a fix", "there is no fix", and "undetermined" — rewording must not fork, version digits must |
| `test_risk_model.py` | Every cell of the exposure × exploited × nature matrix, the nature table, and the s4 marker overrides |
| `test_notify_routing.py` | Tier → channel routing decisions |

## Conventions

- **Fixtures must be publish-safe.** These files are committed to a public repo,
  so never pair a real deployed image tag with a vulnerability count — use a
  synthetic repository and an AR id outside the allocated range. See
  `docs/sops/vulnerability-disclosure.md`; the pre-commit hook checks commit
  messages, not fixtures, so this one is on you.
- **Assert the decision, not the SQL.** Where the logic lives in SQL, re-implement
  the predicate over fakes *and* assert the emitted statement still contains the
  clauses the re-implementation assumes — otherwise deleting a guard from the SQL
  silently passes.
- Name new files `test-<topic>.py` here, `test_<module>.py` in `lib/`, and add a
  row above.

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
network — with ONE deliberate exception. `test-cred-suppressor-scoping.py` also
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

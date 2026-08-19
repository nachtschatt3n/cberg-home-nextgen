# Sweep tooling tests

Plain-Python tests for the audit scripts. **Nothing runs these automatically** —
there is no CI stage and no pre-commit hook for them, so they are only worth
anything if you run them in the same commit as a change to the code they cover.

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
network. Anything that needs the live register is a `--dry-run` script, not a
test — see `runbooks/refingerprint-findings.py`.

## `runbooks/tests/`

| File | Covers | Run it when you touch |
|---|---|---|
| `test-ar-suppression-guard.py` | The two classes of finding exempt from AR substring suppression: audit-integrity (`risk_nature` / `audit_*` subsection) and self-reference (`metadata.ar_id`). Also asserts the operator-facing exemption count is real. | `_apply_ar_suppression` in `sweep-run.py`; anything about AR matching |
| `test-autoclose-component-scope.py` | The PER-COMPONENT coverage veto: `component_key` / `finding_matches_component` / `partition_by_uncovered`, one uncovered leaf still letting the section close the rest, a non-attributable failure still vetoing section-wide, the `MAX_SCOPED_COMPONENTS` / `MAX_UNCOVERED_FRACTION` revert, and the 429-only retry backoff | `mark_uncovered` / `DegradationLog.apply` in `findings_writer.py`; the `component=` call sites in `check-all-versions.py`; the backstop in `sweep-run.py` |
| `test-coverage-lane-safety.py` | The AUTO-lane safety rules in `coverage.py` — pre-release/beta channels, 0.x release-line moves, chart↔image lockstep, image-matched REBUILD, and the truncated-tag dedupe | `assign_lane` / `channel_hold` / `_apply_lockstep` / `is_self_built` in `runbooks/coverage.py` |
| `test-coverage-plan-match.py` | `coverage.py` ↔ maintenance-plan matching | `runbooks/coverage.py`, plan discovery |
| `test-osv-coverage.py` | OSV ecosystem mapping and the coverage-gap accounting | OSV lookups in `security-check.py` |
| `test-pick-latest-semver-tag.py` | `_pick_latest_semver_tag` — variant filtering, cross-variant proposals, downgrade rejection | tag selection in `check-all-versions.py` |
| `test-s3-env-var-name-rhs.py` | `_ENV_VAR_NAME_RHS` — the s3 filter separating an environment-variable NAME on the right-hand side from real credential material. Asserts both directions: the F-8a52ddd9 docstring stays suppressed, value-shaped secrets still fire. | the s3 credential-keyword pipeline in `security-check.py` |
| `test-tag-oracle-veto-discriminator.py` | `_is_structurally_slow` — whether a defeated tag listing is a registry's inherent pace (no veto) or a blip (veto). Pinned to measured s/page for docker.elastic.co vs GHCR. | the OCI tag-listing budget / timeout / exception branches in `check-all-versions.py` |
| `test-trivy-cache-coverage.py` | Trivy cache hit/miss accounting vs the running-image inventory | the s4 scan-target policy or cache logic |
| `test-trivy-tally.py` | Two classes. `KernelHeaderExclusionTest` — per-image Trivy tally arithmetic and the header-package exclusion. `GoPseudoVersionTest` — `classify_pseudo_version`, i.e. FIX-STATUS determination when the installed version is a Go pseudo-version: each of the three routes in both directions, the tag guards (bare integer, CalVer, pre-release), the branch-aware fix bar, the owner+name main-module match, and that an undetermined-only image never reports clean | `tally_trivy_report`, `classify_pseudo_version`, `_TRIVY_TALLY_VERSION` or the fix/no-fix/undetermined classification in `security-check.py` |
| `test-disclosure-residual-claims.py` | The residual-claim tier of the commit-message disclosure hook — phrasing that describes what still awaits an upstream release, distinct from the count and advisory-ID tiers | `.githooks/lib/disclosure_patterns.py` or the residual-claim wording set |

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

# SOP: Sweep Findings Lifecycle — emit, fingerprint, auto-close, and the incomplete-run veto

> Description: Defines how an audit finding is born, re-identified across cycles, and automatically resolved — and the four independent safety gates that stop a partial, ad-hoc, or failed run from silently marking real problems "fixed".
> Version: `2026.08.18`
> Last Updated: `2026-08-18`
> Owner: `homelab-sre`

---

## 1) Description

The sweep does not just report; it maintains a **stateful finding register** in
the `sweep_history` Postgres. Every audit script writes findings there, and a
finding that a section **stops emitting** is automatically resolved. That single
sentence carries all the risk in this system, because auto-close is a conclusion
drawn from **ABSENCE** — and absence has two causes:

1. the problem was fixed (correct to close), or
2. the check could not run (catastrophic to close).

This SOP is the contract that keeps those apart. It exists because the rules
previously lived only in a module docstring, three commit messages, and a skill
file — and we hit three separate production failure modes in one day (§7).

- Scope: `runbooks/lib/findings_writer.py`, `runbooks/sweep-run.py`, and the
  audit scripts `runbooks/{security,check-all-versions,doc,health}-check.py`
- Prerequisites: `SWEEP_PG_DSN` (set automatically by `runbooks/sweep-run.py`),
  repo-pinned tooling via `mise exec --`
- Out of scope: AR suppression semantics (`docs/sops/policy-cli.md` — but note
  suppression must never touch *identity*, §4.1 step 2, nor silence an
  audit-integrity finding), the
  vulnerability-disclosure boundary (`docs/sops/vulnerability-disclosure.md`),
  and the maintenance-window pipeline (`docs/sops/maintenance-windows.md`)

---

## 2) Overview

| Setting | Value |
|---------|-------|
| Namespace | `databases` (sweep-history Postgres) |
| Source of truth (code) | `runbooks/lib/findings_writer.py` |
| Schema | `kubernetes/apps/databases/sweep-history/app/schema-configmap.yaml` |
| Orchestrator | `runbooks/sweep-run.py` |
| Tables | `sweep_cycles`, `sweep_findings` |
| Board | `https://sweep.<DOMAIN>/` |
| Valid sections | `health, security, version, doc, media, smarthome, slo, infra, carry` |
| Auto-close owner | `FindingsWriter.close()` (primary, all four gates) + `sweep-run.py` (backstop, gate 3 only — §4.8) |

**The four gates.** Auto-close **via `FindingsWriter.close()`** only fires
when ALL of these hold. The orchestrator's backstop pass is a *separate*
implementation and honours only gate 3 — see §4.8.

| # | Gate | Trips when | Where |
|---|------|-----------|-------|
| 1 | `section_complete` | no verdict was computed (crash path / `__exit__`) | `close()` |
| 2 | Orchestrated-run | the run minted its own cycle id (ad-hoc) | `close()` |
| 3 | **Incomplete veto** | the section called `mark_incomplete()` | `close()` |
| 4 | Zero-emit breaker | run emitted 0 findings but has rows to close | `close()` |

Plus two always-on scoping invariants that are not gates but bounds:
**section scoping** (never touches another section's rows) and the
**run-start bound** (never resolves a row last seen at/after this run's start).

---

## 3) Blueprints

Source of truth is code, not YAML. The declarative surface is the writer's
public API — treat these five calls as the contract:

```python
from runbooks.lib.findings_writer import (
    FindingsWriter, DegradationLog, cycle_id_from_env, trigger_from_env, git_head,
)

DEGRADED = DegradationLog("security", printer=warn)   # module-level recorder

# ...deep inside a section function, on a graceful-degradation path:
except Exception as e:
    DEGRADED.record("s6_attack_patterns", "Elasticsearch", repr(e))
    return OK, findings, body        # section still completes and reports

# ...at the end of main():
with FindingsWriter(dsn=dsn, section="security",
                    cycle_id=cycle_id_from_env(),
                    trigger=trigger_from_env(), git_head=git_head()) as writer:
    _emit_findings(writer, results, scored)
    DEGRADED.apply(writer)           # -> writer.mark_incomplete(...) if degraded
    writer.close(verdict=verdict)
```

Environment escape hatches (all read in `close()`):

| Var | Effect |
|-----|--------|
| `SWEEP_AUTOCLOSE=0` | kill switch — never auto-close |
| `SWEEP_AUTOCLOSE=1` | opt an **ad-hoc** run in (overrides gate 2 only) |
| `SWEEP_AUTOCLOSE_DRYRUN=1` | print what WOULD close, write nothing |
| `SWEEP_AUTOCLOSE_FORCE=1` | override the zero-emit breaker (gate 4 only) |

There is **no** env override for gate 3. A degraded run cannot be talked into
auto-closing; fix the dependency and re-run.

---

## 4) Operational Instructions

### 4.1 Lifecycle of one finding

1. **Emit.** A section calls `writer.emit(severity, title, subsection=…,
   evidence_path=…, metadata=…)`. Severity accepts the emoji constants
   (`🔴🟡🟢🛡️`) or the strings `critical|warning|clean|accepted|monitor|deferred`.
2. **Fingerprint.** `fingerprint(section, subsection, title)` produces the
   stable identity. It is **not** a hash of the rendered prose:
   - `[AR-0NN]` tags are **stripped first**, on both paths below.
   - If the title contains backticked spans, identity = those spans **verbatim**
     (version digits included — `postgres:17.10` and `postgres:17.11` are
     genuinely different findings) + a **kind token** from `_KIND_MARKERS`.
   - Otherwise it falls back to the normalized title, with timestamps, UUIDs,
     IPv4s, MACs, SHAs and bare digits substituted out.
   - Rationale: rewording a message must not fork a new row for an unchanged
     problem (a 2026-08 reword split 20 image findings into 39 rows).

   > **Identity is what a finding is ABOUT, never how it is presented.**
   > Until 2026-08-18 the second component was the sorted set of `[AR-0NN]`
   > tags, which put a *suppression decision* inside the *identity*: adding,
   > removing or re-wording an accepted risk forked a new row for an unchanged
   > problem and left the old one to be auto-closed as "fixed". Seen live —
   > F-094be167 was born 08-16, forked to F-e14cda04 on 08-17 when AR-063
   > started matching, and re-appeared on 08-18 when AR-063's wording lapsed.
   > One problem, three rows, nothing changed in the world. This is the
   > absence-means-fixed failure §4.3 exists to prevent, reached through a
   > *policy edit* rather than a broken check — so none of the four gates see
   > it coming.
   >
   > The tags were doing one real job — separating an image's "there is a fix"
   > line from its "there is no fix" line, which genuinely IS identity. That is
   > now explicit in `_KIND_MARKERS` (verbatim marker match, the same discipline
   > as `risk_model.S4_POLICY_MARKERS`). Measured over all 296 open rows: the
   > new function reproduces the old discrimination exactly (296 → 296 distinct
   > fingerprints) with zero sensitivity to AR tagging. Dropping the tags
   > *without* the kind token would have merged 52 pairs.
   >
   > **Editing `_KIND_MARKERS` changes identity.** Run
   > `runbooks/refingerprint-findings.py` (dry-run first) after any change to
   > it or to `_stable_anchor`, or every affected finding forks once more on
   > the next sweep. Tests: `runbooks/lib/test_findings_writer_fingerprint.py`.

3. **Upsert.** Same fingerprint → same `finding_id`, `last_seen` bumped, row
   stays open. New fingerprint → new row.

   > `finding_id` is `F-<first 8 hex of fingerprint>`, so it is **not** globally
   > unique — a resolved finding that legitimately recurs re-derives its old id,
   > and the table really does hold repeated ids across history. A partial
   > UNIQUE index (`uq_findings_open_finding_id`) enforces it among **open**
   > rows only. **Any consumer that looks a finding up by id must qualify on
   > `resolved_at IS NULL`** or it can silently return a years-old closed row.
   >
   > Because identity changes rename rows, `metadata.prior_finding_ids` records
   > every id a row has previously answered to. Committed `security_ref:`
   > lines, plan front-matter and published dashboard links are frozen forever,
   > so **every by-id consumer must carry the fallback**. All three do:
   > `policy-cli._finding_row` (which also prefers a LIVE row over a resolved
   > stub, because `finding detail` writes to the row it returns),
   > `render-board.planned_findings()` (without it a renamed finding stops
   > being recognised as planned and resurfaces as un-planned board noise —
   > this really happened to one plan ref on 2026-08-18), and the dashboard's
   > `/findings/<F-id>` route. A fourth consumer must add it too.
   >
   > **`resolved_at` and `status` must move together.** The writer and every
   > fingerprint query test `resolved_at IS NULL`; `render-board.py` and the
   > dashboard filter on `status != 'resolved'`. Setting one alone produces a
   > row that auto-close treats as closed while the board renders it as a live
   > action item — and which sits outside `uq_findings_open_finding_id`, so a
   > later sweep can open a SECOND row with the same id. Two separate resolve
   > paths got this wrong on 2026-08-18, so `ck_findings_resolved_status`
   > (init Job v5) now makes it impossible rather than merely documented.
4. **Cycle row is LAZY.** `sweep_cycles` is inserted on the **first** `emit()`,
   never at construction — a writer that emits nothing leaves no row. This is
   what killed the "5 empty cycle rows per run" orphan problem (N-20).
5. **Auto-close.** `close(verdict=…)` resolves every open row of **this
   section** whose fingerprint this run did **not** re-emit — subject to the
   four gates. Closed rows get `resolved_at=now()`, `status='resolved'`,
   `resolved_commit=<git HEAD>`.
6. **Report.** Closures print per-row, and AR-tagged/accepted closures print in
   their own block — an operator-accepted risk disappearing must never be
   silent.

### 4.1b Changing the identity function

Editing `_KIND_MARKERS` or `_stable_anchor` renames findings. The steps are
order-dependent and the ordering is not guessable, so follow it exactly:

1. **Measure before designing.** Recompute the candidate fingerprint over all
   open rows and count how many groups would MERGE. A merge means two distinct
   findings collapse into one row and one of them stops being reported — the
   naive "just drop the AR tags" variant merged 52 pairs.
2. `python3 runbooks/refingerprint-findings.py` — dry run. Confirm
   `MERGING groups: 0` and no warnings.
3. `python3 runbooks/refingerprint-findings.py --apply`. Takes a
   transaction-scoped advisory lock, so it is safe against a concurrent sweep.
4. Re-run the dry run: it must now report `identity changes to write: 0`.
5. **Only then** bump the sweep-history init Job suffix if the change also needs
   DDL. The script connects as `sweep_writer`, which does **not** own the table,
   so `CREATE INDEX` / `ALTER TABLE` must ship via the Job
   (`docs/sops/immutable-job-image-bumps.md`). Running the Job first can fail
   its index build on duplicate open ids.
6. Verify: `SELECT finding_id, count(*) FROM sweep_findings WHERE resolved_at
   IS NULL GROUP BY 1 HAVING count(*) > 1` → no rows.

Skipping step 3 is the expensive mistake: every affected finding forks once
more on the next sweep, and the abandoned rows auto-close as "fixed".

### 4.1a Never emit a PASS confirmation as a finding

A finding is a *problem*. Emitting "SOP X is compliant" as a finding puts a
green fact into a table whose whole purpose is tracking open work — and
`render-board.py` keys the operator's action list on `status='new'`, not on
severity, so 44 "compliant" rows once landed on the board as MEDIUM action
items (cycle `b2410887`). Report a pass in the markdown body or as a count;
never as a row in `sweep_findings`.

---

### 4.2 Section scoping

A `FindingsWriter` is constructed **per section**, and every auto-close
statement carries `AND section = %s`. A section can only ever resolve its own
rows. This is also why the incomplete veto is section-scoped: one degraded
dependency suppresses auto-close for the **whole** section, not for a
subsection. That is deliberate — auto-close operates at section granularity, so
a finer veto would be unenforceable. Over-suppressing costs one stale row until
the next clean run; under-suppressing loses a real finding.

### 4.3 The incomplete-run veto (gate 3)

Audit scripts **degrade gracefully by design**: if Elasticsearch is unreachable
the run must still complete and report the twelve sections that did work. That
design is correct for reporting and lethal for auto-close — the degraded
section emits nothing, and absence reads as "fixed".

Every graceful-degradation path must therefore call, directly or via
`DegradationLog.record()`:

```python
writer.mark_incomplete("<scope>: <dependency> unavailable (<detail>)")
```

`mark_incomplete()` **accumulates** (deduped, first-occurrence order), so a run
that trips four dependencies reports four reasons rather than one arbitrary
survivor.

**Conditions that trip the veto** (as wired 2026-08-18):

| Script | Section | Tripped by |
|--------|---------|-----------|
| `health-check.py` | `health` | no issues file this run; stale issues file (mtime < run start); `health-check.sh` exit code outside `{0,1}` |
| `security-check.py` | `security` | **Shared primitives** (cover every call site): `run()`/`run_cmd()` exception path — timeout, missing binary, OSError; `kubectl_json()` returning None (a live apiserver returns an empty `items` list, so None is always a coverage gap); `run_unifictl()` empty/login-failed after all retries; `_exec_search()` failing all 3 attempts. **Named sites**: Elasticsearch pod/credential lookup (s5, s6, s6a); Wazuh indexer credentials and `agent_control -l` enumeration (s13); UniFi `stat alarm` / `stat rogueap` / `client list` / `wlan list` empty or unparsable (s11); NVD API 2.0 failure (s11 — `[]` otherwise prints a green "no open CVEs"); OSV.dev lookup failures (s4); `trivy` not on PATH (s4 — skips the entire running-image scan); `version-check-current.md` absent (s4 — skips OSV *and* Trivy); empty running-image inventory (s4); a running image still unscannable after retry — including a private one whenever the run HOLDS registry credentials — and any scannable running image that got no scan attempt at all (s4; the one exclusion is a private image on a credential-less run: see the worked example below); exposure-index build failure and an unloaded CISA KEV feed (risk scoring) |
| `check-all-versions.py` | `version` | registry unreachable/timeout; **HTTP 429 registry rate-limit**; OCI tag-listing truncation; Helm `index.yaml` fetch failure (recorded once per repo — it negative-caches); OCI `helm show chart` / `helm search repo` failure; the bjw-s chart resolver (its negative cache fans out across most of the repo); unparseable `HelmRepository` / `HelmRelease` (the latter drops a whole app from the run); `gh auth` failure and Renovate PR fetch failure (currently renders identically to "there genuinely are none"); NVD, npm, talosctl per-node + talconfig fallback, PiKVM, UniFi. Gated by `_is_transient()` + `_is_real_downgrade()` — see the transitions rule below |
| `doc-check.py` | `doc` | **Shared primitives**: `run()` exception path and `rc != 0` with empty stdout (scoped call sites only — an unscoped grep returning nothing is a legitimate clean result); `run_cmd()` exception path; `read_file()` on PermissionError / IsADirectoryError / decode error (unreadable is never a legitimate clean result), and on FileNotFoundError only where a call site passes an explicit scope. **Named sites**: `kubectl version` / node list / ingress / `sops-age` secret unavailable; `talosctl version` unavailable; `unifictl` VLAN + WLAN JSON unparsable or rc≠0; helmfile / homepage / renovate / ollama / blueprint / SOP / Taskfile / `.gitignore` / `.sops.yaml` / `CLAUDE.md` unreadable; `age-keygen` missing (silently downgrades a wrong-key CRITICAL to a green line); a regex that no longer matches a reworded doc |

> **Not all degradation is silence — some of it is an affirmative green.**
> Several paths do not merely stop emitting; they print a PASS manufactured
> from the failed dependency: an unreadable (or still-encrypted) Authentik
> blueprint yields an empty string, the violation regex matches nothing, and
> the run asserts "N blueprint(s) use UUIDs". An NVD outage returns `[]` and
> the run prints "no open CVEs found". Under auto-close that is an
> affirmative "fixed" claim, not an absence — which is why the veto is wired
> at the dependency, not inferred from the emitted-finding count.
>
> **Veto on TRANSITIONS, not on steady states.** This is the rule that makes
> the veto useful rather than a permanent off-switch. Auto-close can only harm
> you when a finding *existed* and the check that produced it *stopped
> working* — absence then reads as "fixed". A dependency that has been broken
> since the check was written never produced a finding, so there is nothing to
> wrongly resolve, and vetoing on it disables auto-close forever while
> protecting nothing.
>
> Both wiring passes hit this hard. `check-all-versions.py` recorded **67
> degradations on a fully healthy run** before narrowing: HTTP 401s from
> private registries we never authenticate to, charts sourced from
> `OCIRepository` CRs the loader does not collect, downstream symptoms whose
> causes were already recorded, and version-format artifacts (`1.16` vs
> `1.16.0`, digest-pinned tags). Only 4 were genuine 429s.
> `security-check.py` hit the same class: its OSV.dev scan sends
> `ecosystem: "Helm"`, which OSV rejects with HTTP 400 on every request.
>
> So each script classifies before recording: `_is_transient()` (408/425/429/
> 5xx and socket-level errors) in `security-check.py`, `_is_transient()` plus
> `_is_real_downgrade()` in `check-all-versions.py`. Steady-state breakage is
> reported as a **finding** instead — which is auto-close-safe and is how it
> gets fixed. *(The two scripts classify 403 differently on purpose: a registry
> 403 is usually throttling, an API 403 is usually permanent auth.)*
>
> **When you add a degrade path, ask: could this condition be different on the
> next run?** If no, emit a finding; do not veto.
>
> **Worked example — the Trivy running-image scan (s4).** Its uncovered images
> split three ways, and only one of them vetoes. (1) Images excluded by the
> scan-target policy (Bitnami, Wazuh internals): permanent by construction,
> reported in the coverage line, no veto and no finding. (2) Images in our own
> private registry **on a run that holds no registry credentials**: the scan
> fails identically every time — steady state, reported as a standing FINDING,
> no veto (there are ~30 of them, so vetoing here would switch auto-close off
> for the whole security section permanently). (3) Anything else that failed
> after retry, or any scannable image that got no scan attempt this run: could
> succeed tomorrow, had findings yesterday — **veto**. The cached failure list
> is retried on the next run for class 3 and not for class 2, so a transient
> blip cannot keep the veto armed for the full cache TTL.
>
> **The discriminator in (2) is the ENVIRONMENT, not the registry** — and
> getting that wrong is how a steady-state exclusion becomes the very
> false-negative it was meant to avoid. `runbooks/sweep-run.py` passes a
> `gh auth token` through as `TRIVY_USERNAME`/`TRIVY_PASSWORD`, so under the
> orchestrated sweep those private images ARE scanned and DO carry real
> findings. Classifying them "steady state" unconditionally would mean an
> expired or under-scoped token fails all ~30 at once, records no degradation,
> and lets auto-close resolve every one of their open findings on a run that
> never looked at them. `_is_permanently_unscannable()` therefore requires
> BOTH the private prefix AND the absence of credentials; with credentials
> present the failure is class 3 and vetoes. When you write a steady-state
> exclusion, state the condition that makes it permanent and assert THAT in
> code — never infer permanence from the identity of the thing that failed.
>
> **Degradation crosses module boundaries.** `security-check.py`'s s4 decides
> "is this CVE fixable by a newer tag?" by dynamically loading
> `check-all-versions.py` and querying it — a second `DegradationLog` owner. A
> throttled registry therefore degrades the *security* verdict while recording
> the reason in the *version* log. `main()` drains the oracle's log into the
> security one before `apply()`. If you add another cross-module oracle, drain
> it too, or its degradation is invisible to the section that depends on it.
>
> **The rate-limit case is the sharpest.** A Docker Hub anonymous pull that
> returns 429 under concurrency yields the *same* Python value as "no newer tag
> exists". On 2026-08-18 that produced ~40 bogus "up to date" answers that only
> a serial re-check caught. A rate-limited lookup is **incomplete**, never
> "no update available" — otherwise it auto-closes real version findings.

### 4.4 The orchestrated-vs-ad-hoc gate (gate 2)

`sweep-run.py` and the daily-operation fan-out hand every specialist one shared
`SWEEP_CYCLE_ID`. A check script an operator runs by hand does **not** receive
one and mints its own UUID; `self._orchestrated` is False and auto-close is
skipped with an explanatory line. Reason: an ad-hoc run may be scoped,
exploratory, or pointed at a subset — a smaller result set would wrongly read
as "fixed". Opt in with `SWEEP_AUTOCLOSE=1` when you *know* the run was full.

### 4.5 The zero-emit circuit breaker (gate 4)

If a run emitted **zero** findings but has open rows that would close, `close()`
refuses, prints what it would have closed, and continues. A section that
produced nothing has almost certainly failed rather than gone clean. It is a
**backstop, not a substitute** for `mark_incomplete()` — it only catches a
*total* wipeout, so partial degradation must still be declared explicitly. A
genuinely newly-clean section costs one forced re-run with
`SWEEP_AUTOCLOSE_FORCE=1`.

### 4.6 The run-start bound

At construction the writer reads the **DB's** clock (`SELECT now()`, not the
local host — clock skew between the Mac and the cluster must not widen the
window) and stores it. Auto-close adds `AND last_seen < <run_start>`, so a
concurrent or out-of-band run of the same section cannot resolve rows the other
run just wrote.

### 4.8 The backstop is a SEPARATE implementation — know what it does not check

`sweep-run.py:_auto_close_stale_findings()` is not the writer. It is its own
SQL, scoped only by `section = ANY(...)` and `cycle_id != <this cycle>`, and it
runs after every step. It therefore does **not** apply:

| Gate | Writer | Backstop |
|------|--------|----------|
| 1 `section_complete` / verdict | yes | **no** |
| 2 orchestrated-vs-ad-hoc | yes | n/a (it *is* the orchestrator) |
| 3 incomplete veto | yes | **yes — via `sweep_cycles.notes.incomplete`** |
| 4 zero-emit breaker | yes | **no** |
| run-start `last_seen` bound | yes | **no** |

Gate 3 crosses the process boundary because the writer *persists* it:
`_persist_incomplete()` writes `{section: reason}` into
`sweep_cycles.notes.incomplete` (under `SELECT … FOR UPDATE`, since several
specialists finish concurrently), and the backstop reads it back and drops
those sections, naming each. **If the backstop cannot read the veto it aborts
without closing anything** — fail-closed, because the alternative is resolving
findings from a section we cannot prove was healthy.

This was not always true. Until 2026-08-18 the backstop honoured nothing: a
degraded section printed `auto-close SKIPPED … INCOMPLETE` and the orchestrator
closed exactly those rows seconds later, in the same sweep. The veto was
inoperative in the only mode where auto-close is armed at all. If you add a
gate to the writer, decide explicitly whether the backstop needs it too.

---

### 4.7 What `--ran` means

`sweep-run.py --reconcile-only --ran doc,version,security,health,slo` is the
**backstop** auto-close path, used by the fan-out to finalize the shared cycle.
`--ran` declares which sections **actually ran**, and it is authoritative
because **the schema has no per-section run record**: a section that ran and
found nothing writes no rows and is indistinguishable from a section that never
ran. Without `--ran`, the scope is *inferred* from rows written under this
cycle id — which silently drops any clean section.

The declared set is persisted to `sweep_cycles.notes` as `{"ran": [...]}`, which
is what lets the board render "ran clean" instead of a false "DID NOT REPORT".

Sections in the candidate list that did not report are skipped with an explicit
log line — no report is not a resolution.

---

## 5) Examples

### Example A: normal orchestrated sweep (auto-close active)

```bash
cd /Users/mu/code/cberg-home-nextgen && mise exec -- python3 runbooks/sweep-run.py all
```

Each specialist inherits `SWEEP_CYCLE_ID`; each section's `close(verdict=…)`
auto-closes its own stale rows; the final `--reconcile-only` pass recomputes the
verdict.

### Example B: preview closures without writing

```bash
cd /Users/mu/code/cberg-home-nextgen && \
  SWEEP_AUTOCLOSE_DRYRUN=1 mise exec -- python3 runbooks/security-check.py
```

### Example C: ad-hoc run you know was complete

```bash
cd /Users/mu/code/cberg-home-nextgen && \
  SWEEP_AUTOCLOSE=1 mise exec -- python3 runbooks/doc-check.py
```

### Example D: reconcile a specific cycle (the ONLY safe form)

```bash
cd /Users/mu/code/cberg-home-nextgen && mise exec -- python3 runbooks/sweep-run.py \
  --reconcile-only --cycle-id "$SWEEP_CYCLE_ID" --ran doc,version,security,health,slo
```

Never omit `--cycle-id` here — see §7.2.

---

## 6) Verification Tests

### Test 1: the veto fires and is visible

```bash
cd /Users/mu/code/cberg-home-nextgen && \
  mise exec -- python3 runbooks/lib/test_findings_writer_autoclose.py
```

Expected:
- All tests pass, including the degraded-dependency cases.
- Output contains `auto-close SKIPPED for section <x>: run declared INCOMPLETE`.

If failed:
- Check `close()` still evaluates `self._incomplete_reason` **before** the
  `section_complete` branch — order matters for the log message.

### Test 2: a healthy run still auto-closes

```bash
cd /Users/mu/code/cberg-home-nextgen && \
  mise exec -- python3 runbooks/lib/test_findings_writer_autoclose.py \
  | grep -E "healthy_run_still_autocloses|veto_is_persisted"
```

Expected:
- `PASS test_healthy_run_still_autocloses` — a clean run DOES close.
- `PASS test_veto_is_persisted_so_the_orchestrator_can_honour_it` — the veto
  reaches the backstop.

If failed:
- Confirm the fixture marks the run orchestrated (gate 2) and emits ≥1 finding
  (gate 4) — either alone suppresses the close.

### Test 3: a degraded live run completes and reports

```bash
cd /Users/mu/code/cberg-home-nextgen && \
  mise exec -- python3 runbooks/tests/test-osv-coverage.py
```

(There is no env var that fakes an unreachable Elasticsearch — an earlier
revision of this SOP invented `SWEEP_ES_HOST`/`SWEEP_ES_PORT`, which no script
reads. Drive the degrade paths through the tests instead.)

Expected:
- `test_zero_successful_queries_cannot_report_clean` passes — a dependency
  that rejects everything can never yield a clean verdict.
- `test_cloudflare_and_5xx_range_are_transient` passes — a transient failure
  arms the veto.
- For a real degraded run: it finishes, report written, `exit=0` or `1` (never
  a traceback), with `⚠ DEGRADED` lines and a closing `auto-close SKIPPED`.

If failed:
- A degrade path is raising instead of recording — that is a bug in the
  section, not in the writer.

---

## 7) Troubleshooting

| Symptom | Likely Cause | First Fix |
|---------|--------------|-----------|
| Findings stayed open after the fix shipped | Auto-close never ran — section was ad-hoc (gate 2) or degraded (gate 3) | Read the `auto-close SKIPPED` line; it names the gate |
| A whole section's findings resolved at once | A dependency was down and its degrade path is **not** wired to `mark_incomplete()` | Re-open the rows, wire the path, add a test |
| `auto-close REFUSED … emitted 0 findings` | Zero-emit breaker (gate 4) | Verify the section really is clean, then `SWEEP_AUTOCLOSE_FORCE=1` |
| Board shows a section as "DID NOT REPORT" but it ran clean | `--ran` not passed to `--reconcile-only` | Re-run reconcile with the explicit `--ran` list |
| `--reconcile-only` exits with a `SystemExit` about `--cycle-id` | Working as designed (§7.2) | Supply the real cycle id |
| Findings duplicated after a message reword | Title has no backticked anchor, so identity fell back to prose | Put the object identifier in backticks |

```bash
# What is currently open, by section
cd /Users/mu/code/cberg-home-nextgen && mise exec -- python3 - <<'PY'
import os, psycopg
with psycopg.connect(os.environ["SWEEP_PG_DSN"]) as c, c.cursor() as cur:
    cur.execute("SELECT section, count(*) FROM sweep_findings "
                "WHERE resolved_at IS NULL GROUP BY section ORDER BY 1")
    for r in cur.fetchall(): print(r)
PY
```

### 7.1 Failure mode: auto-close never ran

Auto-close originally lived **only** in the orchestrator's separately-sequenced
reconcile step. On 2026-08-18 the version section completed at 13:52 having
stopped emitting 78 obsolete `chart 3.7.3 → 5.1.0` criticals — but the only
reconcile passes that day ran at 13:33 and 13:37, i.e. **before** it finished. A
human hand-resolved 82 rows. Fix: auto-close moved **into the writer**, which is
the only component that always knows the section, the exact fingerprint set just
emitted, and whether the run completed. The orchestrator pass remains as a
backstop.

### 7.2 Failure mode: `--reconcile-only` without `--cycle-id`

Without `--cycle-id` (and without `SWEEP_CYCLE_ID` in the env), `sweep-run.py`
mints a **fresh** UUID. The backstop auto-close then evaluates
`cycle_id != <fresh-uuid>`, which is true for **every** row — so it would
resolve every open finding in every `--ran` section, including ones a specialist
had re-confirmed minutes earlier. This is not hypothetical: an un-scoped
reconcile minted a stray cycle on 2026-08-18 at 13:56. `--reconcile-only` now
**refuses to start** without an explicit cycle id.

### 7.3 Failure mode: out-of-band writes blind the `cycle_id` key

The backstop's scope was once hardcoded to six sections including `media` — but
`sweep-run.py` has **no media step**; the media-manager agent writes findings
out-of-band, under no cycle id the reconcile knows about. Every
`--reconcile-only` run therefore auto-closed every open media finding, including
four the agent had just re-confirmed. Any section that writes outside the
orchestrated cycle is invisible to a `cycle_id`-keyed close. Fix: scope is now
derived from what actually reported this cycle, or declared explicitly with
`--ran` — and a section that did not report is skipped, loudly.

---

## 8) Diagnose Examples

### Diagnose Example 1: "a finding vanished and I don't think it was fixed"

```bash
cd /Users/mu/code/cberg-home-nextgen && mise exec -- python3 - <<'PY'
import os, psycopg
with psycopg.connect(os.environ["SWEEP_PG_DSN"]) as c, c.cursor() as cur:
    cur.execute("SELECT finding_id, section, severity, resolved_at, resolved_commit, "
                "left(title,90) FROM sweep_findings "
                "WHERE resolved_at > now() - interval '2 days' ORDER BY resolved_at DESC")
    for r in cur.fetchall(): print(r)
PY
```

Expected:
- A cluster of same-`section` rows resolved at the identical timestamp is the
  signature of an unguarded degrade path, not of real fixes.

If unclear:
- Pull that run's stdout and grep for `auto-close` and `DEGRADED`.

### Diagnose Example 2: "did the veto actually arm?"

```bash
cd /Users/mu/code/cberg-home-nextgen && \
  mise exec -- python3 runbooks/security-check.py 2>&1 | grep -E "DEGRADED|auto-close"
```

Expected:
- Either `auto-close SKIPPED … declared INCOMPLETE (<reasons>)`, or no
  `DEGRADED` lines at all and a normal close.

If unclear:
- Re-run with `SWEEP_AUTOCLOSE_DRYRUN=1` to see the candidate set without
  writing.

---

## 9) Health Check

```bash
# 1) Unit contract still holds
cd /Users/mu/code/cberg-home-nextgen && cd /Users/mu/code/cberg-home-nextgen && mise exec -- python3 runbooks/lib/test_findings_writer_autoclose.py
cd /Users/mu/code/cberg-home-nextgen && mise exec -- python3 runbooks/tests/test-osv-coverage.py
cd /Users/mu/code/cberg-home-nextgen && mise exec -- python3 runbooks/tests/test-trivy-cache-coverage.py

# 2) No section has been fully wiped in the last day
cd /Users/mu/code/cberg-home-nextgen && mise exec -- python3 - <<'PY'
import os, psycopg
with psycopg.connect(os.environ["SWEEP_PG_DSN"]) as c, c.cursor() as cur:
    cur.execute("SELECT section, count(*) FROM sweep_findings "
                "WHERE resolved_at > now() - interval '1 day' GROUP BY section")
    print(cur.fetchall())
PY
```

Expected:
- Tests green.
- No section shows a mass-resolution burst that does not correspond to a known
  remediation commit.

---

## 10) Security Check

```bash
# The veto must have NO env override — a degraded security run must never auto-close
cd /Users/mu/code/cberg-home-nextgen && \
  grep -n "_incomplete_reason" runbooks/lib/findings_writer.py

# Every degrade path in the security audit records a reason
cd /Users/mu/code/cberg-home-nextgen && \
  grep -cE "(DEGRADED|degraded)\\.record" runbooks/security-check.py
# check-all-versions.py records via `self.degraded.record` off a module-level
# _DEGRADED, so a literal "DEGRADED.record" grep under-counts it (2 vs ~35).
```

Expected:
- `_incomplete_reason` is consulted in `close()` and is **not** gated behind any
  `SWEEP_*` env var.
- The `DEGRADED.record` count matches the number of degrade paths documented in
  §4.3 for that script.
- No CVE IDs, per-image vulnerability counts, or unfixed-exposure detail appear
  in any committed artifact — those belong on the `sweep_findings` row in
  Postgres with a `security_ref: F-xxxxxxxx` pointer
  (`docs/sops/vulnerability-disclosure.md`).

---

## 11) Rollback Plan

The wiring is additive and GitOps-safe (repo scripts only, no cluster mutation).

```bash
cd /Users/mu/code/cberg-home-nextgen
git revert <sha>            # never reset --hard, never force-push
git push
```

Immediate mitigation without a revert — disable auto-close entirely for the next
run:

```bash
SWEEP_AUTOCLOSE=0 mise exec -- python3 runbooks/sweep-run.py all
```

To re-open findings that were wrongly auto-closed:

```sql
-- inspect first; run inside a transaction and verify the count before COMMIT
-- `status` MUST move with `resolved_at` — ck_findings_resolved_status enforces
-- it, and the two columns feed different consumers (see §4.1 step 3). The live
-- vocabulary is new | unchanged | resolved; 'open' is NOT a value this table
-- uses and nothing downstream understands it.
UPDATE sweep_findings
   SET resolved_at = NULL, status = 'new', resolved_commit = NULL
 WHERE section = '<section>'
   AND resolved_at BETWEEN '<start>' AND '<end>';
```

---

## 12) References

- `runbooks/lib/findings_writer.py` — writer, gates, `DegradationLog`
- `runbooks/lib/test_findings_writer_autoclose.py` — the executable contract
- `runbooks/tests/test-osv-coverage.py` — OSV coverage + transient-classifier contract
- `runbooks/tests/test-trivy-cache-coverage.py` — Trivy cache top-up coverage, tally-version invalidation, and the steady-state-vs-transient split above
- `runbooks/sweep-run.py` — orchestrator, `--ran`, `--reconcile-only`
- `runbooks/{security,doc,health}-check.py`, `runbooks/check-all-versions.py`
- `docs/sops/audit-script-correctness.md`
- `docs/sops/vulnerability-disclosure.md`
- `docs/sops/policy-cli.md` — AR suppression semantics, incl. the two classes
  of finding that are **exempt** from it (audit-integrity and self-reference)
- `runbooks/refingerprint-findings.py` — one-shot migration for any change to
  the identity function
- `runbooks/lib/test_findings_writer_fingerprint.py`,
  `runbooks/lib/test_findings_writer_autoclose.py`,
  `runbooks/tests/test-ar-suppression-guard.py`
- `runbooks/health-check.md`, `runbooks/version-check.md`, `runbooks/doc-check.md`

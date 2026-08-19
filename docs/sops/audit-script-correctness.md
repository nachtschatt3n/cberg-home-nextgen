# SOP: Audit-script correctness — never score a non-result as a result

> Description: Rules for writing and reviewing the sweep's audit scripts
> (`health-check.sh`, `security-check.py`, `doc-check.py`, `slo-check.py`,
> `sweep-run.py`, the media `audit.py`), so a check that could not measure
> something never reports it as passing — or as confirmed.
> Version: `2026.08.19`
> Last Updated: `2026-08-19`
> Owner: `operator + daily-operation agents`

---

## 1) Description

Between 2026-07-30 and 2026-08-18, **sixteen** defects across five audit scripts
shared one root cause: an unmeasured, failed or absent probe was reported as a
definite outcome. Four of them were introduced *while fixing the others*.

The failure is not a coding slip — it is a modelling error. Audit code naturally
has three outcomes (pass / fail / could-not-measure) but is usually written with
two, so the third silently collapses into whichever branch the code falls through
to. When it collapses into *pass*, real problems are hidden. When it collapses
into *fail*, operators chase things that do not exist and stop trusting the sweep.

This SOP exists because that rule lived only in commit messages.

## 2) Overview

> **Sibling failure class — change verification.** This SOP governs the sweep's
> **audit code**: a check that could not measure must not report a result. Its
> twin governs **change plans**: a check that measures the wrong noun. There the
> defect is asserting the SHAPE of a thing (exists / Ready / 200) instead of its
> CONTENTS, so every green signal is true while the thing is empty — three
> instances on 2026-08-18/19. Rules and per-class assertions:
> **[`docs/sops/verification-contents-not-shape.md`](verification-contents-not-shape.md)**.
> One sentence covers both: *a health signal that cannot distinguish "working"
> from "empty" is not a health signal.*

**The rule: every audit function returns a tri-state. Never two.**

```
pass            — measured, and the property holds
fail            — measured, and the property does not hold
not-measured    — could not measure (error, timeout, missing source, empty input,
                  auth failure, unparsable output, subset enumeration)
```

`not-measured` is **never** rendered with the wording of `pass` or `fail`. It
gets its own wording and, for security checks, surfaces (fail-safe) — but says
plainly that it is undetermined.

**Second rule (added 2026-08-15): the counter you assert on must be
PROPORTIONAL TO THE HARM.**

This is a distinct failure family from the tri-state one — the check *did*
measure something real, it just measured the wrong quantity. If the source
**batches** N events into one record, counting records measures flush
frequency, not loss. `health-check.sh` counted `validation errors` log lines
from the edot collector; the exporter packs ~18 drop reasons into each line, so
when Envoy Gateway phase 0 added 6720 dropped metric points/h the line counter
did not move (~362/h, as before) and the check reported healthy.

Before setting a threshold, derive the **expected per-unit rate** and set the
threshold from it — here: one un-converted histogram family on one 30s-scraped
target = ~120 dropped points/h, so the threshold is 100/h and the first new
family trips it. A counter that cannot move when the harm grows is not a
signal.

### The instances (each one a test case for new code)

| Script | What went wrong | Collapsed into |
|---|---|---|
| `security-check.py` | trivy scan failure treated as "clean" (`1bf8c4fe`) | pass |
| `doc-check.py` | fuzzy match: any word >4 chars counted as documented | pass |
| `doc-check.py` | denominator enumerated only HelmRelease apps, so raw-manifest apps could never be flagged | pass |
| media `audit.py` | two documented thresholds never computed at all | pass |
| media `audit.py` | `layout_pct` = nested/total, not the compliance flag | pass |
| `health-check.sh` | `grep -c … \|\| echo "0"` → `"0\n0"`, aborting the `-gt` test | pass (guard never ran) |
| `security-check.py` | image dedup on raw string, same image counted twice | double-fail |
| `security-check.py` | `None` (undeterminable) newer-tag lookup worded as "newer upstream tag available" | fail |
| `security-check.py` | a Trivy cache HIT short-circuited the running-image scan entirely, so the CACHE's image set silently defined coverage instead of the RUNNING set: images started after the cache was written were never scanned while the cached numbers were reported as current. Name the denominator — coverage is a property of what is running, never of what the memo happens to hold (2026-08-18, `cfebb329`, F-8cdf8719) | pass (stale numbers reported as current) |
| `security-check.py` | same cache, second mechanism: a tally-logic fix (kernel-header exclusion, `abb12fda`) could not take effect until the 24h TTL expired, because the cache written before it kept serving pre-fix arithmetic. A cached RESULT must be invalidated by the version of the LOGIC that produced it, not only by age — `_TRIVY_TALLY_VERSION` (2026-08-18, `cfebb329`) | pass (fixed logic, stale output) |
| `sweep-run.py` | auto-close resolved findings for sections that never ran | pass (false resolution) |
| `health-check.sh` | counted batched `validation errors` LINES; ~18 drops per line, so the counter sat flat at ~362/h while loss grew 8x to 6720 points/h (`1482de6a`) | pass |
| `health-check.sh` | §34 + fatal/OOM ES queries: `match` on the `body.text` KEYWORD is exact-equality, so "error logs 24h: 0" while `wildcard *error*` found 63,559 — hid two DNS outages; `severity_text` clause was dead too (`a54e88d8`) | pass |
| `health-check.sh` | the fix commit for the row above claimed BOTH queries repaired; the fatal/OOM edit hit an anchor mismatch and silently never landed on disk — verify disk state after editing, never trust the commit message (`e1777211`) | pass (phantom fix) |
| `health-check.sh` | ES stalled-port-forward class: `773b76e6` fixed a leaked port-forward holding :9201 so the ES bind failed silently; same class recurred 2026-08-17 as an orphan alert-bridge process holding :8787/:8788 while launchd crash-looped `EADDRINUSE` — a stale process holding a port makes the NEW instance the silent failure | pass (stale process answers) |
| `health-check.sh` | FATAL/OOM wildcard `*fatal*` matched the NFS mount OPTION `fatal_neterrors=none` in mount-table output from the Talos cleanup pod — 2 of 6 "critical" hits were a filesystem flag, not a log level (fixed: must_not `*fatal_neterrors=*`) | fail (option name ≠ log level) |
| `health-check.sh` | same FATAL/OOM check, structural version of the row above: threshold was `>0 ⇒ CRITICAL` over a match set dominated by recurring restart noise, so the assertion **could never clear**. Re-measured at 215 hits / 24h: 100 Rails empty-message FATAL headers, 50 clean-shutdown SIGTERM, 36 restart-tied "too many clients already", 16 hits on the GIF FILENAME `icon_fatalerror.gif`, 9 probe-misconfig, 1 real. ~93% false positive. Split into three assertions with honest titles and tiered floors (2026-08-18, F-d97cfe78) | pass (permanent false CRITICAL) |
| `health-check.sh` | same check again: titled "FATAL/OOM" while reporting a CRITICAL **OOM** condition with `out of memory` = 0 and both authoritative controls (`events reason=OOMKilled`, pod `lastState`) at 0. A composite title lets one component's noise speak for the other's silence — name an assertion after exactly what it measures | pass (title asserted more than the query) |
| `health-check.sh` | 17 Flux assertions and ZERO for the image-automation family, so an `ImageUpdateAutomation` that ran on schedule for 218d without ever pushing a commit was invisible — `lastPushCommit: null` while `lastAutomationRunTime` advanced. Coverage gaps are audit-logic bugs too: the check that does not exist cannot fail loudly (2026-08-18) | fail (unmonitored silent failure) |
| `health-check.sh` | the FIX for the row above shipped with the same defect it removed: it escalated on `lastPushCommit == null` ALONE, but an automation whose policy tag already matches what is deployed has never had a change to make and reports null forever — a permanent MAJOR that can never clear. Discriminator must be null **AND** a pending update (policy tag not deployed). Caught within the hour by the sweep agents (2026-08-18, `9127dff2`) | pass (the anti-pattern reproduced inside its own fix) |
| `health-check.sh` | §34's fatal check was the HEAD of a single `if/elif` chain that the total-error-count branches hung off, so a non-zero fatal count short-circuited the chain and `High error count in logs` could NEVER fire — and fatal was always non-zero. Splitting the assertion un-masked a second, unrelated assertion that had been dark for as long as the first was broken. One assertion heading an `elif` chain silently owns every branch below it | double-fail (one broken check masking another) |
| `health-check.sh` | `git pull --rebase` landing mid-run rewrote the script WHILE bash was reading it; bash reads by byte offset, so it resumed mid-token and aborted with a syntax error pointing at a line that is perfectly valid (`bash -n` passes on the same file). Any sweep overlapping a pull can die this way. Run audits from an immutable copy or a git worktree, never from the live tree | fail (abort mid-audit, misleading error) |
| `health-check.sh` | ES/kubectl query failures printed `0`, so an unreachable Elasticsearch or a stalled port-forward scored as THREE clean green assertions instead of one loud failure. Fixed with an `ERR` sentinel that raises a MAJOR "assertions did not run" and skips the verdicts (2026-08-18) | pass (silent green on a dead probe) |
| `health-check.sh` | "Kustomizations not reconciled" emitted from TWO call sites (§5 + summary) for ONE condition → duplicate finding rows F-359d4bdf/F-a2726bda; a summary section must log-only, never re-add issues | double-fail |
| `sweep-run.py` | auto-close lived ONLY in the orchestrator's reconcile, so a section finishing at 13:52 kept 78 obsolete findings open when the day's reconciles ran at 13:33/13:37 — 82 rows hand-resolved | fail (false persistence) |
| `health-check.sh` | THIRD instance of the structurally-unclearable class (after the two FATAL/OOM rows above): "High error count in logs" escalated at `> 10,000` against a MEASURED 7-day baseline of 113,571-133,922 hits/day — 43,882-44,517/day even with the loudest namespace entirely excluded. It could not have gone green on any day in the retained window, before or after the storm that surfaced it. Its own code comment said the count was "display-only ... the per-namespace breakdown is what makes it useful", and the code then called `add_major_issue` on the total anyway. Fixed per-namespace-relative (floors 40k/100k/500k + a concentration rule), so one chatty app can no longer own the cluster verdict, with the cluster-wide total kept as a broad-runaway backstop only (2026-08-18) | pass (permanent unclearable MAJOR; comment and code disagreed) |
| `health-check.sh` | window mismatch between a query and its corroborating control: §34's OOM CRITICAL required 24h Elasticsearch `OOM_TEXT` **and** `OOM_COUNT`, which reads kubectl Events with a ~1h etcd TTL. `OOM_LASTSTATE` did not close the gap either — it is unbounded in time but only covers pods that still EXIST, so a real OOM three hours ago whose pod has since been replaced left no surviving evidence in either control and could only ever reach MINOR. Added `OOM_LASTSTATE_24H` from `lastState.terminated.finishedAt`, which is window-aligned with the ES query. Corroboration is only corroboration when both sides measure the same window (2026-08-18) | pass (real OOM capped at MINOR) |
| `health-check.sh` | non-audit-logic cousin worth recording next to the row above: the thing being measured produced the noise. A CakePHP `/health` ROUTE as the readiness/liveness/startup target made the kubelet boot the framework ~480x/hour, emitting ~370 deprecation notices per boot — 4.35M lines/24h, 58% of all cluster log ingest, 98.8% of the error metric, from probes alone. They scored as errors only because the substring "Error" sits inside the method name `CakeLog::handleError`, exactly the `icon_fatalerror.gif` collision three orders of magnitude larger. A health probe must be cheap and silent: point it at a static endpoint, not a framework route (2026-08-18, `05f07143`, docs/sops/log-volume-runaway.md) | fail (the probe was the incident) |
| `sweep-run.py` | `--reconcile-only` without `--cycle-id` minted a FRESH uuid, making `cycle_id != <fresh>` true for every row — would have resolved every open finding in the `--ran` scope (cycle f11badb9, 2026-08-18 13:56) | pass (mass false resolution) |

## 3) Blueprints

```python
# Tri-state, explicit. None means "could not measure" — never False.
def check_thing() -> bool | None:
    try:
        data = probe()
    except Exception:
        return None            # NOT False
    if not data:
        return None            # empty input is not a pass
    return property_holds(data)

verdict = check_thing()
if verdict is None:
    f.add(WARNING, "thing: could NOT determine (probe failed) — verify manually")
elif verdict:
    f.add(OK, "thing: holds")
else:
    f.add(CRITICAL, "thing: does not hold")
```

```bash
# Shell: grep -c already prints 0 and exits 1 on no match.
# WRONG — appends a second zero, breaking every later numeric test:
COUNT=$(... | grep -c PATTERN || echo "0")
# RIGHT:
COUNT=$(... | grep -c PATTERN || true)
COUNT=$(printf '%s' "${COUNT:-0}" | tr -d '\n')
```

## 4) Operational Instructions

When writing or reviewing an audit check:

1. **Name the denominator.** Write down the set being checked. If the enumeration
   covers a subset (only HelmReleases, only tagged images, only the first 25
   rows), the check may not report "0 problems" — it must report "0 problems
   *among N of M*", and the gap must be visible.
2. **Make `not-measured` reachable and distinct.** Every probe that can fail
   (network, registry auth, kubectl, jq/parse, empty file) needs its own branch.
3. **Never let a fallback fabricate data.** `|| echo 0`, `or vector(0)`,
   `.get(x, 0)`, `2>/dev/null` without a status check — each converts "no answer"
   into an answer.
4. **Compute the metric the threshold names.** If the SOP says "episode NFO
   coverage ≥80%", the code must compute episode NFO coverage — not season layout,
   not a proxy.
5. **Canonicalise before dedup/compare.** Registry prefixes
   (`docker.io/library/`), variant suffixes (`-openvino`, `-alpine`), and tag
   shapes must be normalised, or the same object is counted twice or compared
   across lines.
6. **Absence is not resolution.** Auto-close / auto-resolve may only act on
   sections that demonstrably ran. Prefer an explicit declaration from the caller
   over inferring it from written rows — a section that ran clean may write
   nothing.

   Full contract: **[`docs/sops/sweep-findings-lifecycle.md`](sweep-findings-lifecycle.md)**.

Since 2026-08-18 auto-close lives primarily in the **writer**:
   `FindingsWriter.close(verdict=...)` resolves the open findings of its OWN
   section that the run did not re-emit, keyed on fingerprint. The gate is
   `section_complete`, inferred from `verdict is not None` — so `__exit__`'s bare
   `close()` on the exception path, and partial writer users like
   `auto-update.py`, conclude nothing. A section that ran but knows its coverage
   degraded (scanner errored, port-forward died, API rate-limited) **must** call
   `mark_incomplete(reason)`; a coverage gap is not a fix. When the gap is
   attributable to exactly ONE component — an API rate-limit on a single image
   is the common case — call `mark_uncovered(component_key(...), reason)`
   instead: it holds that component's findings open while the rest of the
   section still closes. Never INFER attribution; only the call site knows
   whether its failure sits at the leaf or above it.
   `sweep-run.py --reconcile-only --ran <sections>` remains as a backstop.
   Kill switches: `SWEEP_AUTOCLOSE=0`, `SWEEP_AUTOCLOSE_DRYRUN=1`.
   **Auto-close is section-scoped and fires only on an ORCHESTRATED run**
   (`SWEEP_CYCLE_ID` set in the env — i.e. launched by `sweep-run.py` or the
   daily-operation fan-out). An ad-hoc standalone run of a check script does
   NOT auto-close unless you opt in with `SWEEP_AUTOCLOSE=1`.
7. **Fail-safe direction is security-dependent.** Security checks surface on
   `not-measured`; cosmetic checks may stay quiet — but both must say which it is.

## 5) Examples

### Example A: registry lookup cannot resolve a tag

```python
latest = get_latest_image_tag(repo, tag)
if not latest:
    return None    # undeterminable → caller surfaces with "could NOT determine"
```
Wording matters: `"could NOT determine whether a newer upstream tag exists;
verify upstream before planning a bump"` — not `"newer upstream tag available"`.

### Example B: a check that enumerates a subset

```python
apps = find_apps()              # HelmRelease + raw-manifest (ks.yaml)
print(f"Total apps found (HelmRelease + raw-manifest): {len(apps)}")
```
The label states the denominator, so "0 undocumented" cannot be misread as
"0 undocumented apps in the cluster".

## 6) Verification Tests

### Test 1: the check can actually fail
Run the new check against a known-bad fixture and confirm it reports `fail`.
**A check that has never failed once is unverified.** This is mandatory before a
new check ships.
```bash
# e.g. temporarily point the check at a bad value / empty dir / wrong tag
# and confirm a finding is emitted
```

### Test 2: the check reports `not-measured` when the probe dies
```bash
# break the probe deliberately (unset creds, bad host, empty input)
# expect: "could NOT determine" wording — NOT a pass, NOT a silent 0
```

### Test 3: zero is handled
```bash
X=$(echo "no match" | grep -c PATTERN || true); X=$(printf '%s' "${X:-0}" | tr -d '\n')
[ "${X:-0}" -gt 10 ] && echo "gt" || echo "guard evaluated"   # must NOT abort
```

### Test 4: real-inventory false-positive sweep
For any classifier that can *suppress* a finding, run it over the full live
inventory and eyeball every match.
```bash
# example: the floating-tag classifier over all running images
# 183 images scanned, 7 matched, all genuinely floating, 0 pinned tags caught
```

## 7) Troubleshooting

| Symptom | Likely cause |
|---|---|
| Section reports "0 problems" but you can see one | denominator excludes it (rule 1) |
| `integer expression expected` in a shell guard | `grep -c … \|\| echo 0` (rule 3) |
| Same item appears as two findings | missing canonicalisation (rule 5) |
| Finding auto-resolves and reappears next cycle | auto-close acting on a section that did not run (rule 6) |
| A resolved finding stays open across cycles | the section auto-closes only on a completed run — check for "auto-close SKIPPED … no verdict" / "declared INCOMPLETE" in its output (rule 6) |
| Operators stop believing a section | `not-measured` worded as `fail` (rule 7) |

```bash
# Quick debugging commands
python3 -c "import ast;ast.parse(open('runbooks/security-check.py').read())"
bash -n runbooks/health-check.sh
python3 runbooks/doc-check.py 2>/dev/null | grep -E '🔴|🟡'
```

## 8) Diagnose Examples

Embedded scripts parse individually but break at the import boundary — how the
media audit broke on 2026-08-14 (`EPISODE_NAME_RE` added to `common.py`, never
added to `audit.py`'s explicit import list):

```bash
# assert every capitalised name a script uses from common is actually imported
python3 - <<'EOF'
import yaml, re
d=yaml.safe_load(open('kubernetes/apps/media/library-tools/app/scripts-configmap.yaml'))
a,c = d['data']['audit.py'], d['data']['common.py']
imported=set(re.search(r'from common import \(([^)]*)\)', a, re.S).group(1).replace(',',' ').split())
defined={m.group(1) for m in re.finditer(r'^([A-Z_][A-Z0-9_]*)\s*=', c, re.M)}
used=set(re.findall(r'\b([A-Z_][A-Z0-9_]{2,})\b', a))
print("used from common but not imported:", sorted((used & defined) - imported))
EOF
```

## 9) Health Check

```bash
# every audit script still parses, and doc-check's own assertions pass
python3 -c "import ast;[ast.parse(open(f).read()) for f in ['runbooks/security-check.py','runbooks/sweep-run.py','runbooks/doc-check.py','runbooks/slo-check.py']]"
bash -n runbooks/health-check.sh
python3 runbooks/doc-check.py 2>/dev/null | tail -20
```

## 10) Security Check

- A suppression/acceptance rule must **narrow on the specific evidence**, never on
  a container name or namespace alone — that blinds the whole workload (see the
  Falco 100415 ESPHome rule, scoped on image AND exepath).
- Accepted-risk descriptions are substring-matched against finding text by
  `Findings.suppress_accepted()`. Descriptions must be **short matchers**, not
  prose, or the AR silently suppresses nothing (AR-057, 2026-08-14). Put the
  reasoning in `justification`.
- Do not AR-suppress a false positive. Fix the audit logic; the AR register is
  for risks that are real and accepted.
- **An AR must never suppress a finding about the audit itself.** Findings whose
  `risk_nature` is audit-integrity (`policy-drift`, `audit-coverage-gap`,
  `audit-integrity`, `meta`) or whose `subsection` starts `audit_`/`audit-`, and
  any finding whose `metadata.ar_id` names the AR being applied, are exempt from
  substring suppression. A finding reporting *"AR-063 no longer suppresses its
  target"* was tagged `[AR-063] accepted` on 2026-08-18 because it quoted the
  AR's own description — the detector was switched off by the thing it detects.
  Guards live in `_apply_ar_suppression` (`runbooks/sweep-run.py`);
  `Findings.suppress_accepted` does **not** carry them yet — tracked on
  `F-21ceb683`, and note that `subsection`/`risk_nature` are attached *after*
  that function runs, so it needs an explicit `meta` flag rather than a copy of
  the SQL predicate.
- **Never put a suppression decision inside a finding's identity.** AR tags are
  presentation; `fingerprint()` strips them. See
  `docs/sops/sweep-findings-lifecycle.md` §4.1 step 2.
- Preview EVERY new AR description with `runbooks/policy-cli.py risk match
  --description '<candidate>'` before writing it. The description is a substring
  of a finding *title*, so a description written as prose matches nothing and
  suppresses nothing while reporting success — and `risk lint` will not catch
  that (its probe only fires when a shorter PREFIX matches). `risk lint` is a
  periodic regression check, not a pre-write validator.
- `risk add` and `risk edit` both refuse a description embedding `x.y.z` or a
  volatile count (`--allow-drift`); `risk add` additionally refuses one that
  matches nothing (`--allow-nomatch`) or far too much (`--allow-broad`).
- Run `runbooks/policy-cli.py risk lint` to find descriptions that have already
  drifted, and `risk edit AR-NNN --description '<drift-stable>'` to fix one in
  place.

## 11) Rollback Plan

Audit scripts are read-only, so a bad change costs signal quality, not cluster
state. Revert the commit and re-run the section:

```bash
git revert --no-edit <sha> && git push
python3 runbooks/sweep-run.py <section> --no-write     # smoke test, no DB write
```

If a bad classifier already auto-closed findings, reopen them (set
`resolved_at = NULL, status = 'open'`) — findings are data, and a wrong
resolution is a data error, not just a display bug.

# SOP: Control Liveness — every control proves it can fire

> Description: The convention every automation in this repo must follow — a one-time commissioning proof plus a standing staleness assertion — and the ledger that enforces it.
> Version: `2026.08.26`
> Last Updated: `2026-08-26`
> Owner: `cluster-ops`

---

## 1) Description

Half of this system's historical failures were **controls that could not fire
and looked healthy**: a restart CronJob that had never run *and could not have
started* (wrong schedule + no shell in the image), alert selectors matching
deleted PVCs, a storage-safety STOP gate whose condition no live object could
satisfy, four maintenance windows with no driving cron, test fixtures whose
comments satisfied the assertions. The common shape: **a mechanism whose
absence is silent**. Presence in a manifest review proves nothing — the
frigate mitigation looked correct in every review while being incapable of
running.

- Scope: every automation this operation depends on — crons (OpenClaw and
  k8s), alert rules, auto-remediations, scheduled agents, sweeps
- Prerequisites: none (the enforcement is a pure-git doc-check section)
- Out of scope: application-level features; one-shot migrations

---

## 2) Overview

Two obligations, both mandatory when a new control ships:

1. **Commissioning proof** — demonstrate ONCE that the control actually fires,
   *before trusting it*: force the first CronJob run, inject the failing state
   and watch the alert fire, run the checker against the known-broken
   pre-state. Record the proof in the commit message. A green check that has
   never been red is indistinguishable from a broken one.
2. **Standing staleness assertion** — something that fires when the control
   has NOT done its job on cadence. Assert the **effect**, not the mechanism
   (`ContainerRestartMitigationStale` asserts the container got *younger*, so
   one expression covers cron deleted / RBAC revoked / image broken /
   schedule wrong / run skipped). Include an `absent()` arm where the metric
   does not exist until first success.

The ledger `runbooks/controls.yaml` lists every control and names its
assertion. **The `assertion:` field is an exact substring needle grepped in
the `in:` file** — the same contract as accepted-risk descriptions: prose
matches nothing and silently watches nothing. `in:` must be plaintext in git
(a needle can never match inside a SOPS-encrypted file). doc-check section 10
verifies every needle resolves; a ledger row pointing at a renamed or deleted
assertion is a critical finding.

---

## 3) Blueprints

N/A — the artifacts are `runbooks/controls.yaml` and doc-check section 10
(`s10_control_ledger` in `runbooks/doc-check.py`).

---

## 4) Operational Instructions

**Adding a control:**
1. Build the control AND its staleness assertion in the same change.
2. Commission it: force it to fire once; put the evidence in the commit message.
3. Add the ledger entry: `id`, `kind`, `what`, `cadence`, `watched_by:
   {assertion: <exact needle>, in: <plaintext repo path>, note: <prose>}`.
4. Keep the ledger under ~15 entries. Past that, prune mechanisms — a growing
   ledger is a symptom, not a achievement.

**Removing a control:** delete the ledger row in the same commit, or s10
fails on the dangling needle — which is the point.

---

## 5) Examples

The canonical exemplar is the frigate restart mitigation
(`docs/sops/frigate-memory-leak.md`): the mitigation CronJob, the
`ContainerRestartMitigationStale` effect-assertion with its `absent()` arm,
and a commissioning run that exposed the mitigation had NEVER been able to
start. The windows system is the same pattern at system scale:
`window-crons.py --check` (executor exists) + `window_runs` liveness (executor
ran) + `SweepPipelineDead` (the whole pipeline's dead-man's switch, watched
from inside the cluster so it does not share the Mac's fate).

---

## 6) Verification Tests

```bash
# the ledger itself
python3 - <<'PY'
import importlib.util
spec = importlib.util.spec_from_file_location("dc", "runbooks/doc-check.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
sev, f, _ = m.s10_control_ledger(); print(sev, f.summary_cell())
PY
# EXPECT: 🟢 clean
```

---

## 7) Troubleshooting

| Symptom | Meaning | Action |
|---|---|---|
| s10 critical: needle not found | watcher renamed/removed | restore the assertion or update the row — never delete the row to silence it |
| s10 critical: watcher file missing | assertion's home deleted | same |
| control fires constantly | staleness threshold vs real cadence mismatch | fix the cadence claim, not the alert |

---

## 8) Diagnose Examples

```bash
python3 runbooks/window-crons.py --check          # executor parity, live
python3 runbooks/maintenance-plan.py | grep -A4 "NEVER RAN"   # occurrence liveness
curl -s http://127.0.0.1:8788/                    # bridge watchdog age
```

---

## 9) Health Check

`bash runbooks/tests/run-all.sh -q` green, doc-check sections 9+10 green, and
zero firing `SweepPipelineDead` / `ContainerRestartMitigationStale`.

---

## 10) Security Check

The ledger is metadata only — no secrets, no vulnerability detail, no
endpoints beyond what the repo already documents. Needles must not quote
unfixed vulnerability specifics (`docs/sops/vulnerability-disclosure.md`).

---

## 11) Rollback Plan

Deleting `runbooks/controls.yaml` disables enforcement loudly (s10 goes
critical on the missing ledger — absence is a finding, not a pass). Individual
rows roll back by git revert.

---

## 12) References

- `runbooks/controls.yaml` · `runbooks/doc-check.py` (s10)
- `docs/sops/frigate-memory-leak.md` — the exemplar
- `docs/sops/audit-script-correctness.md` — the doctrinal home of the
  silent-wrong-answer catalogue
- `docs/troubleshooting/ops-continuity-plan.md` — the effort this closes

## Restore Drill Log

Quarterly scratch-restore of one Longhorn backup AND one postgres dump, with
smoke queries — "verified" backups are Schrödinger's until restored. G2 will
automate this as the `backup_gate` probe for AUTO-BACKUP-GATED plans; until
then it is operator-manual and this table is the record. **Next due:
2026-11-26.**

| Date | What was restored | Outcome |
|---|---|---|
| 2026-08-26 | `postgresql-data-5g` backup of same morning (03:01), via `runbooks/backup-restore-proof.py` | **PROVEN** — postgres booted, 6 databases, smoke count on a live table returned rows; scratch fully torn down |

---

## Version History

| Version | Date | Change |
|---|---|---|
| `2026.08.26` | 2026-08-26 | Created (P3.2): convention + ledger + doc-check s10 enforcement. |

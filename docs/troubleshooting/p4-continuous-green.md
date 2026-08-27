# P4 — Autonomy to Continuous Green

> Status: **P4.0 done** (this commit) · P4.1–P4.5 pending. Delete this file
> when P4.5 closes and the exit criterion has held.
> Started: 2026-08-28 · Successor to `ops-continuity-plan.md` (P0–P3).
> Operator-approved plan (2026-08-27/28 review session), validated against
> ITIL change classes, Google-SRE ownership/error-budget practice, and
> progressive-delivery norms.

## Goal and exit criterion

**Continuous green**: the sweep board verdict is green on every sweep for 30
consecutive days, where green is redefined (P4.2) as *zero unowned work* —
zero open criticals, every open warning in a lane and inside its SLA, zero
CRACKs at any severity, triage available. Operator touchpoints reduce to:
go/no-go on **user-visible changes**, go/no-go on **interrupting work**,
weekly digest review. Everything else executes, verifies, and reverts itself.

Operator decisions baked in (2026-08-27 Q&A):
- Human gate = **user-visible behavior changes + availability interruptions**
  (>N min of user-facing downtime outside a window; brief in-window restarts
  need no approval). Data-shape and security-surface changes may auto-execute
  once safeguards pass — but the storage-safety `subdir: /` hard stop stays
  unconditionally.
- **Node reboots automate eventually**, after a proven track record of clean
  attended runs (Kured/Talos-style serialized reboots are industry standard).
- **Unpatchable CVEs → auto-created accepted-risks with expiry** (time-boxed,
  auto-renew while unpatched, lapse the moment a patch appears so the finding
  resurfaces). "No downstream fixes" stays.

## Ordering rationale

Truth repair first — agents execute from these documents; a file claiming a
live gate is "REPORT-ONLY" invites wrong reasoning. Ownership plumbing before
the verdict punishes its absence. Verdict flip only after back-test.
Autonomy widening last, supervised by everything before it.

## P4.0 — Truth repair ✅ (this commit)

| # | item | done |
|---|---|---|
| 1 | "REPORT-ONLY / lands with P2.1b" claims killed in `maintenance-plan.py` (report header, JSON comment, section comment) + `autonomy-policy.yaml` STATUS block → "ENFORCED since P2.1b (a39d8766); kill switch = empty the classes" | ✅ |
| 2 | `maintenance-windows.yaml` retired-`auto_execute` comment; SOP pre-rename window names + retired `max_unattended_risk` reference; stale sample output refreshed | ✅ |
| 3 | `media-manager.md` storage STOP conjunction corrected to the unconditional rule (`subdir == "/"` → STOP regardless of reclaimPolicy); needle test added (test-storage-safety-table.py test 7) asserting all three carrier docs keep it | ✅ |
| 4 | One plan-status vocabulary: `approved` dropped from `VALID_STATUSES` (loaded by nothing — silent-inert status); README documents the FULL set; parity tests added (test-plan-frontmatter-invariants.py) | ✅ |
| 5 | `ops-continuity-plan.md` header un-lagged; successor pointer added | ✅ |
| 6 | Sweep-skill note: `media` is the one section with no sweep-run step; `--ran media` only on agent-reported completion (until P4.4.5) | ✅ |

## P4.1 — Ownership plumbing (script what prompts promise)

Principle: every ingest that today lives as instruction text becomes a script
the prompt merely invokes (the `window-crons.py --check` migration, again).
Reuse `runbooks/lib/notify.py` — no new transport.

1. **`runbooks/openclaw-sync.py`** — one idempotent reconciler, run every
   sweep + window close-out, three subjects, all glue over existing `--json`
   outputs: awaiting-go plans (`maintenance-plan.py --json`), DECIDE-lane
   findings (`finding-triage.py --json`), REBUILD-lane components
   (`coverage.py --json`, 14d SLA). Replaces the prompt-instructed
   `kubectl exec` blocks in daily-operation rules 4d/4e. OpenClaw pod
   unreachable → `ingest_or_notify` Telegram fallback + loud non-zero exit.
   Test: `test-openclaw-sync-payload.py` (`--dry-run` prints JSON, execs
   nothing); commission against a scaled-down pod.
2. **`runbooks/alert-record.py`** — alert-triage-agent invokes on every
   SURFACE: finding via `findings_writer.py` (section `alert`, fingerprint =
   alert identity → re-fires dedupe) + home-operation issue; `--resolved`
   closes both. SURFACE'd alerts inherit lanes/SLAs/ownership from existing
   machinery. Plus `AlertBridgeNoListener` PrometheusRule + controls.yaml
   entry so `ws_clients: 0` stops being a mere warning.
3. **awaiting-go terminal escalation** — home-operation `tick`: after 3
   unanswered escalations (~72h) record a `deferred` decision-of-record
   (silence can only defer, never approve), rebase plan to next same-mode
   window; 3 consecutive defers → "decision debt" in the weekly briefing.
4. **Restore-drill cadence machine-asserted** — `backup-restore-proof.py`
   writes `runbooks/state/restore-drills.json` on success; `--assert-cadence`
   (every sweep) emits a warning finding when quarterly is overdue; repoint
   the controls.yaml needle.
5. **PVC SPOF watchers** — OpenClaw issue store + briefing patch join the
   backup-gate roster; two controls.yaml entries (hits the 15-entry cap —
   prune before any 16th).
6. **Specialist-recommendation contract** — a state-change recommendation
   MUST be emitted as a finding; "a recommendation that exists only in report
   prose does not exist" (sweep skill + specialist docs).

## P4.2 — Warning ownership + verdict v2

Decision: extend triage lanes to warnings (`warning_plan_sla_days: 14`,
criticals keep 4) — NOT a numeric warning budget (baseless number, hides
warnings in headroom, invites reclassification; lanes reuse proven critical
machinery and per-item SLAs are a time-denominated budget).
- DECIDE-accept for a warning materializes as a **time-boxed AR** via
  `policy-cli.py risk add --expires-days` (shared with P4.3) — a tolerated
  warning leaves the board legitimately, with an expiry.
- Overdue-warning paging only past 2× SLA (alert-fatigue guard).
- `render-board.py` verdict v2: **green** = triage ran + zero criticals +
  zero CRACKs + all warnings laned & in-SLA (prints `GREEN — N warnings
  owned, oldest due …`); **yellow** = owned criticals in flight OR warning
  unlaned/overdue ≤2× SLA; **red** = existing conditions + warning CRACK +
  warning past 2× SLA.
- **Back-test before flip**: verdict v2 read-only over 30 days of
  sweep_history + two live sweeps side-by-side, tune SLA, then flip (one
  function, one-commit revert).

## P4.3 — Auto-AR lifecycle for unpatchable CVEs

State in existing `accepted_risks.metadata` JSONB
(`{auto: true, origin: "cve-nofix", expires_at, renew_count, image,
cve_snapshot}`) — no schema migration.
- **Create**: `security-check.py` at the AR-029 tag point — per-image auto-AR
  row, needle = backtick-quoted `image:tag` + "already on the newest upstream
  tag" (must pass `risk lint`).
- **Renew** (+90d): only when the sweep re-derives "still no fix" —
  evidence-driven, not a timer.
- **Lapse**: the moment fix-availability flips → `status='lapsed',
  enabled=false`; finding re-emits CRITICAL and flows to lanes (usually
  COVERED by the update pipeline — the point).
- **Escalate**: `renew_count >= 4` (~1yr) → DECIDE finding ("replace,
  variant-switch, or formally accept").
- **Digest**: board section "ACCEPTED (auto)" — count, nearest expiry,
  lapsed-since-last-sweep; `policy-cli.py risk list --auto`.
- Safeguards: auto-writer touches ONLY `metadata.auto=true` rows (operator
  ARs untouchable, pinned by test); every failure direction resurfaces
  findings as criticals (noise, never silence). Rollout: two sweeps
  `--dry-run` first. Test: `test-auto-ar-lifecycle.py`.

## P4.4 — Hardening the auto path

1. **kubeconform in CI** — add to `.github/workflows/flux-local.yaml` over
   rendered output, in the required check; auto-merge "CI green" then means
   rendering AND schema. Commission with a deliberately invalid field.
2. **Snapshot-freshness gate (G6)** in `auto-update.py` —
   `version-check-current.md` older than 36h → AUTO demoted to HELD for that
   run (fail-closed); nightly Step 0 refreshes the snapshot first.
   Test: backdate mtime, assert HELD.
3. **Revert-streak circuit breaker** — two consecutive `revert` outcomes in
   `window_runs` → AUTO lane refused until an attended window completes
   green, page once. Failing automation stops itself.
4. **Finish or delete half-built** — implement `add_prometheus_rule`
   (additive PrometheusRule in a dedicated auto-rules file, CI-validated);
   DELETE `sensitive_namespaces` from auto-update-policy.yaml (read by
   nothing); add the missing `age_waive` regression test (the one gate where
   a bug widens autonomy).
5. **Media becomes a first-class sweep step** in `sweep-run.py`, retiring
   the caller-declared `--ran` for it.

## P4.5 — Autonomy widening, on track record (last, by design)

1. **Split the capability fact**: `capability_change` →
   `user_visible_change` (checkable enumeration: UI looks/behaves
   differently; feature add/remove/rename; auth-flow change; breaking API)
   + `interruption_minutes` (worst-case user-facing unavailability). Auto
   classes require `user_visible_change: false` AND `interruption_minutes <=`
   per-window `in_window_interruption_ok_min` (nightly 10, attended 30).
   Validator maps the legacy key with a deprecation warning; backfill live
   plans in the same commit.
2. **`talos-reboot` execution class with earn-out**: requires
   `user_visible_change: false`, `needs_reboot: true`,
   `category: talos-reboot`; **sun-attended only** (pinned in policy);
   serialized node-by-node with per-node gates (Node Ready → Longhorn volumes
   healthy → pods rescheduled → health-check pass); any failure stops
   remaining nodes + pages + `outcome=partial` (streak resets). Track record:
   additive `plan_categories TEXT[]` on `window_runs` + `--categories` on
   `window-run-record.py`; unattended eligibility = ≥3 consecutive green
   attended runs containing the category; first unattended run gets a
   day-before heads-up (courtesy, not gate). Never moves to nightly in P4.
3. **Track-record visibility**: `maintenance-plan.py` report prints
   per-category progress (`talos-reboot: 1/3 clean attended`).

## Deliberately NOT built (scale-appropriate refusals)

Flagger/canary + service mesh (single-replica services — health-gate+revert
is the honest equivalent); Kured (window/track-record model covers it);
staging cluster (CI + cooldown + auto-revert is the proportionate pre-prod);
OPA/Gatekeeper admission (git-reviewed policies + validators already enforce
at the only real entry point); commercial paging (OpenClaw+Telegram + the
P4.1.3 terminal rung); issue-store rewrite off PVC (backup-gate + watchers
instead); controls.yaml past ~15 entries (prune first, per its contract).

## Verification discipline

- Every new script gets a test in `runbooks/tests/` before first live run;
  every new watcher/control is **commissioned by watching it fail first**
  (scaled-down OpenClaw pod, backdated state file, invalid manifest, seeded
  revert rows, synthetic alert).
- Phase gates: verdict v2 flips only after 30-day back-test + two
  side-by-side sweeps; AR auto-writer live after two clean `--dry-run`
  sweeps; fact split proven in one attended window before nightly relies on
  it; talos-reboot unattended only after 3 consecutive clean attended sun
  windows.
- Exit test: 30 consecutive green verdicts with operator touches limited to
  user-visible/interruption go/no-gos + weekly digest.

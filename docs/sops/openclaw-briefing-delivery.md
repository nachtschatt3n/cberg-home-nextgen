# SOP: OpenClaw morning-briefing delivery triage

> Description: How to localise a failed or stale morning voice briefing to a
> single pipeline stage, using the artifacts each stage leaves behind — and how to
> read the health-check's ">26h" warning without mistaking a recovered
> single-day miss for an ongoing outage.
> Version: `2026.08.14`
> Last Updated: `2026-08-14`
> Owner: `operator + openclaw-agent`

---

## 1) Description

The morning briefing runs as an OpenClaw cron (~08:45 Europe/Berlin) in the
`ai/openclaw` pod. When it fails, the usual signals all look green — the cron
reports `lastRunStatus=ok`, local TTS reports `model_loaded=true`, and the Codex
dispatch canary replies — because **each of those tests a different stage than the
one that broke**. The sweep then reports only "last voice sent Nh ago", which says
that something failed but not what.

This SOP exists because that state was carried as an open finding across three
sweeps (2026-08-12 → 08-14) with no triage path.

## 2) Overview

The pipeline is four stages, and **each successful stage leaves a dated artifact**
in `~/clawd/.tmp/morning-briefing/` plus a line in
`~/clawd/state/morning-briefing/briefing.log`. The last artifact present tells you
exactly which stage failed — this is the whole diagnostic.

| # | Stage | Log line | Artifact |
|---|---|---|---|
| 1 | collect context | `collected context …` | `context-YYYY-MM-DD.json` |
| 2 | generate briefing (LLM) | `created briefing …` | `briefing-YYYY-MM-DD.txt` |
| 2b | append open-issues recap | `appended operation-issues recap (N open)` | (in the .txt) |
| 3 | render voice text | `voice preflight ok … chars=N` | `voice-YYYY-MM-DD.txt` |
| 4 | deliver voice | `voice sent from …` | — (delivery is the side effect) |

**Read it as: the highest-numbered artifact that exists is the last stage that
worked.** A missing `briefing-*.txt` next to a present `context-*.json` means
stage 2 died — nothing downstream ever ran, so TTS and delivery are irrelevant.

### Worked example — the 2026-08-13 miss

```
08-12T08:47:33  collected → created → voice preflight ok → voice sent     ✅
08-13T08:45:11  collected context                        ← and nothing more  ❌
08-14T08:47:43  collected → created → voice preflight ok → voice sent     ✅
```
On disk: `context-2026-08-13.json` (56805 bytes) present, **no**
`briefing-2026-08-13.txt`, **no** `voice-2026-08-13.txt`. Stage 2 failed. It
self-recovered the next day with no intervention → a transient generation/dispatch
failure, not a broken pipeline.

### Reading the health-check warning correctly

`runbooks/health-check.sh` warns when the newest `voice sent` line is older than
**26h**. One missed day therefore produces a warning for roughly a day *after
recovery too* — at 04:02 on 08-14 the last voice was 08-12T08:47, i.e. ~43h, and
the finding was accurate; the 08:47 run that same morning then cleared it.

**So: a single stale reading is not an incident.** Check whether the NEXT
scheduled run succeeded before escalating. Escalate when two consecutive days miss,
or when the same stage fails repeatedly.

## 3) Blueprints

N/A — the briefing is an OpenClaw cron plus a skill, not a Kubernetes manifest.
The cron is looked up **by name** (`~ 'Daily Morning Briefing'`), never by id: the
id changes whenever the cron is recreated, and the 2026.6.6 upgrade dropped the
cron entirely once, which a hardcoded-id check would have missed silently.

## 4) Operational Instructions

```bash
OC=$(kubectl get pods -n ai --no-headers | grep '^openclaw-' | awk '{print $1}')

# 1) Which stage failed? (the whole diagnostic)
kubectl exec -n ai "$OC" -c app -- bash -lc \
  'ls -la ~/clawd/.tmp/morning-briefing/ | tail -12'
kubectl exec -n ai "$OC" -c app -- bash -lc \
  'tail -25 ~/clawd/state/morning-briefing/briefing.log'

# 2) Does the cron still exist, and what did it last report?
kubectl exec -n ai "$OC" -c app -- bash -lc 'openclaw cron list --json' \
  | python3 -c "import sys,json;d=json.load(sys.stdin);[print(c) for c in (d if isinstance(d,list) else d.get('crons',[])) if 'riefing' in str(c.get('name',''))]"
```

Then act on the stage that failed:

- **Stage 1 (no `context-*.json`)** — context collection. Check the sources it
  reads (cluster/HA/sweep DB reachability) and the pod's own health.
- **Stage 2 (no `briefing-*.txt`)** — the LLM generation step. The usual cause is
  a provider/dispatch failure: look for `FailoverError`, `couldn't generate a
  response`, `provider is not one of`, `Missing bearer` in the pod log, and check
  the Codex OAuth chain (see `project_openclaw_codex_oauth_drift`: the provider
  dies silently when the refresh chain stops rolling; recovery is
  `codex login --device-auth` then delete the pod). **A single failure here
  self-heals next run — do not intervene on the first occurrence.**
- **Stage 3 (no `voice-*.txt` / no `voice preflight ok`)** — voice rendering. Check
  local TTS (`model_loaded`) and the character count; an empty or oversized
  briefing can fail preflight.
- **Stage 4 (`voice preflight ok` but no `voice sent`)** — delivery only. This is
  the case where cron/TTS/canary all look green. Check the delivery target
  (Telegram/peer binding) and credentials, not the generator.

## 5) Examples

### Example A: transient generation failure (the common case)
`context-*.json` present, `briefing-*.txt` absent, next day succeeded.
**Action: none.** Record it; escalate only if it repeats.

### Example B: green cron, green TTS, no voice
`voice preflight ok` present but no `voice sent`, repeated across days.
**Action:** stage 4 — delivery. The cron, the model and the canary are all
irrelevant here; do not chase them.

## 6) Verification Tests

### Test 1: a full cycle completes
```bash
kubectl exec -n ai "$OC" -c app -- bash -lc \
  'tail -5 ~/clawd/state/morning-briefing/briefing.log'
# expect all four lines for today's date, ending in "voice sent"
```

### Test 2: today's artifacts all exist
```bash
D=$(date +%F)
kubectl exec -n ai "$OC" -c app -- bash -lc \
  "ls ~/clawd/.tmp/morning-briefing/{context,briefing,voice}-$D.* 2>&1"
# expect all three; a missing one names the failed stage
```

### Test 3: the staleness gate agrees
```bash
grep -A6 'last briefing voice sent' runbooks/health-check.sh
# threshold is 26h; confirm the newest "voice sent" is inside it
```

## 7) Troubleshooting

| Symptom | Stage | Likely cause |
|---|---|---|
| No `context-*.json` | 1 | source unreachable / pod unhealthy |
| `context` but no `briefing` | 2 | LLM/provider dispatch — check Codex OAuth drift |
| `briefing` but no `voice preflight ok` | 3 | TTS or preflight (char count, empty text) |
| `voice preflight ok` but no `voice sent` | 4 | delivery target/credentials |
| Cron absent entirely | — | dropped by an upgrade (happened on 2026.6.6) — re-add by name |
| Warning persists after a good run | — | expected: the 26h window still contains the miss |

```bash
# Quick debugging commands
kubectl logs -n ai "$OC" -c app --since=24h | grep -iE 'briefing|failover|bearer|provider is not one of' | tail -20
```

## 8) Diagnose Examples

```bash
# Localise the failure in one command: last artifact per day for the last 5 days
kubectl exec -n ai "$OC" -c app -- bash -lc '
for d in $(seq 0 4); do
  D=$(date -d "-$d day" +%F 2>/dev/null || date -v-${d}d +%F)
  printf "%s: " "$D"
  for s in context briefing voice; do
    ls ~/clawd/.tmp/morning-briefing/$s-$D.* >/dev/null 2>&1 && printf "%s " "$s" || printf "-%s " "$s"
  done; echo
done'
# a line reading "context -briefing -voice" is a stage-2 failure for that day
```

## 9) Health Check

```bash
# the sweep's own assertions for this surface
grep -n -A6 'Morning Briefing cron lastRunStatus' runbooks/health-check.sh
grep -n -A10 'last briefing voice sent' runbooks/health-check.sh
```
Green means: cron present and `lastRunStatus=ok`, dispatch canary replied, local
TTS `model_loaded=true`, and newest `voice sent` < 26h.

## 10) Security Check

- The briefing reads cluster, Home Assistant and sweep-DB state and speaks it
  aloud. Treat `context-*.json` as sensitive: it aggregates household and
  infrastructure state in one file. Do not copy it out of the pod or paste it
  into commits, issues or reports.
- Never print provider tokens while triaging stage 2. Check the token's *age and
  presence*, not its value.
- Delivery targets are per-peer bindings; do not re-point a briefing at a
  different chat/peer to "test" it — that leaks household context to another
  recipient.

## 11) Rollback Plan

Nothing to roll back for a transient miss — the next scheduled run supersedes it.

- If the cron was re-added or edited and misbehaves, remove and re-add it by name
  (`openclaw cron list` → `openclaw cron rm <id>` → `openclaw cron add …`).
- If a provider/auth change is the cause, revert that change; for the Codex OAuth
  path, re-auth (`codex login --device-auth`) and delete the openclaw pod so it
  restarts with a fresh chain.
- Do **not** hand-craft a `voice sent` line into `briefing.log` to silence the
  warning: the log is the evidence the health check reads, and faking it hides the
  next real failure.

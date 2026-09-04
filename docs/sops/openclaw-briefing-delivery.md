# SOP: OpenClaw morning-briefing delivery triage

> Description: How to localise a failed or stale morning voice briefing to a
> single pipeline stage, using the artifacts each stage leaves behind — and how to
> read the health-check's ">26h" warning without mistaking a recovered
> single-day miss for an ongoing outage. Covers the two stages that leave the
> *weakest* evidence: the cron's model dispatch (stage 0) and the detached TTS
> child (stage 4b).
> Version: `2026.08.18`
> Last Updated: `2026-08-18`
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
| 0 | cron agent turn dispatch | *(none in briefing.log)* | `cron_run_logs` row in `~/.openclaw/state/openclaw.sqlite` |
| 1 | collect context | `collected context …` | `context-YYYY-MM-DD.json` |
| 2 | generate briefing (LLM) | `created briefing …` | `briefing-YYYY-MM-DD.txt` |
| 2b | append open-issues recap | `appended operation-issues recap (N open)` | (in the .txt) |
| 3 | render voice text | `voice preflight ok … chars=N` | `voice-YYYY-MM-DD.txt` |
| 4a | launch `say` | `voice sent from …` | — **only proves `say` exited 0** |
| 4b | synthesize + deliver (detached) | `say: voice note synthesized via local-tts` | `~/clawd/.tmp/say/say-<pid>.log` |

**Read it as: the highest-numbered artifact that exists is the last stage that
worked.** A missing `briefing-*.txt` next to a present `context-*.json` means
stage 2 died — nothing downstream ever ran, so TTS and delivery are irrelevant.

**Stage 0 leaves nothing in `briefing.log`.** If the agent turn never reaches the
shell, `morning_briefing.py` does not run at all and the log simply has *no lines
for that date* — indistinguishable at a glance from "the pod was down". Read
`cron_run_logs` (§4 step 0) to tell those apart; it records the model and provider
that actually served the turn.

**Stage 4a is not delivery.** Since the chunk-and-detach rework (2026-08-18) `say`
**forks** for any text longer than `LOCAL_CHUNK_CHARS` (1200) and returns
`{"status":"queued","detached":true}` immediately. `morning_briefing.py` sees exit
0 and logs `voice sent from …` while synthesis has not started yet. The detached
child writes to `~/clawd/.tmp/say/say-<pid>.log` and **discards the Telegram API
response**, so a successful log reads only:

```
say: voice note synthesized via local-tts
```

That line is written *before* the upload. A delivery exception appends
`say(detached): delivery failed: …`; its **absence** plus a completed file is the
practical success signal. For hard proof see §6 Test 4.

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

### Named failure mode: a cron model pin bypasses the fallback chain

**This is the failure mode with the worst evidence-to-impact ratio in the whole
pipeline, because every other signal stays green.**

The agent's global chain (`agents.defaults.model` in `openclaw.json`) is:

```
openai/gpt-5.6-terra  →  ollama/gemma4:26b-mlx  →  ollama/gemma4:e2b-mlx
```

A cron job may carry a **per-job model override** (`payload.model`). When it does,
that model is used *instead of* the chain — the fallbacks are not consulted. So
the moment the pinned provider is unavailable (Codex weekly quota, OAuth drift,
provider outage) the agent turn dies with

```
GatewayClientRequestError: FailoverError: You've reached your Codex subscription
usage limit. Next reset in 2 days, Aug 20 at 4:03 AM UTC.
```

and **stage 1 never starts** — no `context-*.json`, no log lines, nothing to
triage downstream.

**Why it hides:** the sweep's dispatch canary runs *without* a model override, so
it takes the fallback and replies happily. TTS reports `model_loaded=true`. The
cron shows `lastRunStatus=ok`. Only `cron_run_logs.model` / `payload_model` expose
it.

**How to spot it in one query:**

```bash
kubectl exec -n ai "$OC" -c app -- bash -lc 'python3 - <<EOF
import sqlite3
db=sqlite3.connect("file:/home/node/.openclaw/state/openclaw.sqlite?mode=ro",uri=True)
for r in db.execute("select job_id,name,payload_model from cron_jobs where payload_model is not null"):
    print(r)
EOF'
# expect: no rows. Any row is a job that cannot fail over.
```

**The fix is `--clear-model`, not a different pin.** Repointing the pin at
`ollama/gemma4:26b-mlx` merely moves the single point of failure and needs a manual
flip back when quota returns. Clearing it restores normal cron model precedence,
so the job self-heals on the next reset *and* survives the next outage:

```bash
kubectl exec -n ai "$OC" -c app -- \
  openclaw cron edit <job-id> --clear-model
```

**Accept the latency change.** On the fallback the turn runs on `gemma4:26b-mlx`,
which is roughly 2–3× slower than `gpt-5.6-terra` (measured 2026-08-18: 489 s vs
163–253 s for the same job). That is still well inside the job's
`timeoutSeconds: 1200`, but a job with a tighter timeout would start failing on
fallback only — check the margin before clearing a pin elsewhere.

### TTS topology (changed 2026-08-18)

- **ElevenLabs is gone.** Removed by operator decision: metered, effectively
  unused (318 of 59k chars), and its budget guard silently killed a whole
  briefing. There is now **one** provider.
- **Self-hosted Qwen3-TTS** on the Mac mini, `OPENCLAW_TTS_FALLBACK_URL`
  (`…:8000/v1`, `POST /audio/speech`). The env var keeps its historical
  "fallback" name; it is the primary and only path. If it is unreachable the
  error propagates loudly — there is no silent second provider.
- **The 4000-char ElevenLabs budget guard is retired.** It was the cause of the
  2026-08-18 morning failure (`say: refused — text length 4366 > 4000 chars`).
  It is replaced by a pure runaway guard at **12000** chars
  (`OPENCLAW_TTS_LOCAL_MAX_CHARS`), which a briefing capped at
  `MAX_VOICE_CHARS` = **6200** (`BRIEFING_MAX_VOICE_CHARS`) cannot reach.
  **Do not reintroduce a TTS-side length guard below the briefing cap** — length
  is bounded at the source, in `morning_briefing.py`.
- **Chunk and stitch.** The model truncates above ~1500 chars, so text is split
  at sentence boundaries into ≤1200-char chunks, synthesized serially (~58 s
  each) and concatenated with `ffmpeg`. `ffmpeg` is therefore a hard dependency
  of stage 4b.
- **Voice and seed are pinned** (`OPENCLAW_TTS_VOICE`, `OPENCLAW_TTS_SEED`,
  `OPENCLAW_TTS_TEMPERATURE`). Qwen3-TTS here is a VoiceDesign model: unpinned,
  every chunk generated a *different* voice and an unlucky chunk padded dead air.
  A dead-air guard re-synthesises any chunk whose chars/sec collapses below
  `DEADAIR_RATIO` of the batch median. **Keep these pinned.**

## 3) Blueprints

N/A — the briefing is an OpenClaw cron plus a skill, not a Kubernetes manifest.
The cron is looked up **by name** (`~ 'Daily Morning Briefing'`), never by id: the
id changes whenever the cron is recreated, and the 2026.6.6 upgrade dropped the
cron entirely once, which a hardcoded-id check would have missed silently.

**Where the cron lives:** `~/.openclaw/state/openclaw.sqlite`, table `cron_jobs`.
`/home/node` is the `openclaw-data` PVC, and the init script in `helmrelease.yaml`
contains **no** cron seeding — so cron edits are PVC state, survive a pod roll,
and are *not* recoverable from git. Same GitOps exception class as
`~/clawd/scripts/morning_briefing.py`: a PVC rebuild loses both.

## 4) Operational Instructions

```bash
OC=$(kubectl get pods -n ai --no-headers | grep '^openclaw-' | awk '{print $1}')

# 0) Did the agent turn even run, and on which model? (stage 0)
kubectl exec -n ai "$OC" -c app -- bash -lc 'python3 - <<EOF
import sqlite3, datetime
db=sqlite3.connect("file:/home/node/.openclaw/state/openclaw.sqlite?mode=ro",uri=True)
db.row_factory=sqlite3.Row
q="select * from cron_run_logs where name like \"%Briefing%\" order by run_at_ms desc limit 5"
for r in db.execute(q):
    d=dict(r)
    print(datetime.datetime.fromtimestamp(int(d["run_at_ms"])/1000, datetime.timezone.utc).isoformat(),
          d.get("status"), d.get("model"), d.get("provider"), str(d.get("summary"))[:70])
EOF'
# model/provider is the ground truth for "did it fall back?".
# A row whose summary carries a FailoverError and whose model is the pinned
# one == the model-pin failure mode (see section 2).

# 1) Which stage failed? (the whole diagnostic)
kubectl exec -n ai "$OC" -c app -- bash -lc \
  'ls -la ~/clawd/.tmp/morning-briefing/ | tail -12'
kubectl exec -n ai "$OC" -c app -- bash -lc \
  'tail -25 ~/clawd/state/morning-briefing/briefing.log'

# 2) Does the cron still exist, and what did it last report?
kubectl exec -n ai "$OC" -c app -- bash -lc 'openclaw cron list --json' \
  | python3 -c "import sys,json;d=json.load(sys.stdin);[print(c) for c in (d if isinstance(d,list) else d.get('crons',[])) if 'riefing' in str(c.get('name',''))]"

# 3) Did the DETACHED TTS child finish? (stage 4b — `voice sent` does not say)
kubectl exec -n ai "$OC" -c app -- bash -lc \
  'ls -lt ~/clawd/.tmp/say/ | head -5; echo ---; cat "$(ls -t ~/clawd/.tmp/say/*.log | head -1)"'
# good: a single line "say: voice note synthesized via local-tts"
# bad:  "say(detached): delivery failed: …", or no log file at all for that run
```

Then act on the stage that failed:

- **Stage 0 (no lines at all in `briefing.log` for that date)** — the agent turn
  never reached the shell. Check `cron_run_logs` for the model/provider and a
  `FailoverError`, then check `payload_model` for a pin (see the named failure
  mode in §2). Distinguish from "pod was down" with `kubectl get pod -n ai` age.
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
- **Stage 4a (`voice preflight ok` but no `voice sent`)** — `say` itself refused
  or crashed. `briefing.log` carries the reason inline
  (`say failed exit=N stderr=…`). Exit 3 is the runaway-length guard; exit 2 is a
  missing `OPENCLAW_TTS_FALLBACK_URL` or Telegram bot token.
- **Stage 4b (`voice sent` present but nothing arrived in Telegram)** — the
  detached child. This is the case where cron/TTS/canary/`briefing.log` *all* look
  green. Read `~/clawd/.tmp/say/say-<pid>.log`: no file means the fork died before
  logging; `delivery failed` names the upload error; a lone `synthesized` line
  with no upload error means the send itself was accepted. Check `ffmpeg`
  presence and local-TTS reachability before suspecting Telegram.

## 5) Examples

### Example A: transient generation failure (the common case)
`context-*.json` present, `briefing-*.txt` absent, next day succeeded.
**Action: none.** Record it; escalate only if it repeats.

### Example B: green cron, green TTS, no voice
`voice preflight ok` present but no `voice sent`, repeated across days.
**Action:** stage 4 — delivery. The cron, the model and the canary are all
irrelevant here; do not chase them.

### Example C: the 2026-08-18 double failure (both new failure modes at once)

Two unrelated defects stacked on the same day, and the second one was invisible
until the first was fixed.

```
08-18T08:47:24  collected → created → voice preflight ok chars=4366
08-18T08:47:24  say failed exit=3 stderr=say: refused — text length 4366 > 4000
                chars (ElevenLabs character budget guard)          ← stage 4a
08-18T08:47:41  news links sent          (the text half still went out)
```

Stage 4a: the retired-provider guard rejected a briefing that was *within* the
briefing's own 6200-char cap. Note `cron_run_logs` still recorded
`status=ok` for that run — the *agent turn* succeeded, only the script exited 3.

With the guard removed, the *next* morning would still have failed, one stage
earlier and for an unrelated reason: the cron carried
`payload.model = "openai/gpt-5.6-terra"` and the Codex weekly quota had
exhausted with a reset at Aug 20 04:03 UTC — after the 08-19 08:45 run. A canary
against the pinned model returned `FailoverError`; the same canary with no
override answered normally over `ollama/gemma4:26b`. **Action:** `--clear-model`,
then a real off-schedule `openclaw cron run` to prove all six stages, because
every dry-run stops before stage 4.

**Lesson:** fixing the stage that failed *last night* does not mean tomorrow's run
works. After any briefing repair, re-run the cron for real — a `--dry-run` exits
at stage 3 (it prints the voice text and returns 0 without calling `say`), so it
can never distinguish a healthy stage 4 from a broken one.

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

### Test 4: end-to-end proof (the only test that covers stages 0 and 4b)

`--dry-run` returns at stage 3. To prove the whole chain, run the cron for real:

```bash
JOB=$(kubectl exec -n ai "$OC" -c app -- bash -lc 'openclaw cron list --json' \
  | python3 -c "import sys,json;d=json.load(sys.stdin);print([c['id'] for c in (d if isinstance(d,list) else d.get('crons',[])) if 'riefing' in str(c.get('name',''))][0])")
kubectl exec -n ai "$OC" -c app -- openclaw cron run "$JOB"
```

Then collect all four pieces of evidence — **all four, not the first that looks
green**:

1. `cron_run_logs` newest row: `status=ok` and the `model`/`provider` you expect
   (on a cleared pin during a Codex outage: `gemma4:26b` / `ollama`).
2. `briefing.log`: the full ladder for today ending in `voice sent from …`.
3. `~/clawd/.tmp/say/say-<pid>.log`: `say: voice note synthesized via local-tts`
   and **no** `delivery failed` line.
4. A Telegram acknowledgement carrying a non-zero audio size. The detached child
   discards the API response, so read it back from Telegram — forward the message
   to the same chat and delete the copy:

```bash
kubectl exec -n ai "$OC" -c app -- bash -lc 'python3 - <<EOF
import json, urllib.request
tok = json.load(open("/home/node/.openclaw/openclaw.json"))["channels"]["telegram"]["botToken"]
CHAT = <chat-id>          # the briefing target; do NOT point this elsewhere
def api(m, **kw):
    r = urllib.request.Request("https://api.telegram.org/bot%s/%s" % (tok, m),
        data=json.dumps(kw).encode(), headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(r, timeout=30).read())
res = api("forwardMessage", chat_id=CHAT, from_chat_id=CHAT, message_id=<id>)
print(json.dumps(res["result"].get("voice"), indent=1))
api("deleteMessage", chat_id=CHAT, message_id=res["result"]["message_id"])
EOF'
```

A healthy briefing looks like `{"duration": 252, "mime_type": "audio/ogg",
"file_size": 950951}` — i.e. minutes of audio and ~1 MB. A few-KB / 2-second
voice note is a truncated synthesis, not a success.

**Note the ordering quirk:** because stage 4b is detached, the *news-links text*
message is delivered ~2 minutes **before** the voice note. Voice arriving last is
normal, not a partial failure.

## 7) Troubleshooting

| Symptom | Stage | Likely cause |
|---|---|---|
| **No lines at all for that date** | 0 | agent turn never dispatched — **check `payload_model` for a pin**, then Codex quota/OAuth |
| `FailoverError … usage limit` on the pinned model, canary green | 0 | per-job model override bypassing the fallback chain — `--clear-model` |
| No `context-*.json` | 1 | source unreachable / pod unhealthy |
| `context` but no `briefing` | 2 | LLM/provider dispatch — check Codex OAuth drift |
| `briefing` but no `voice preflight ok` | 3 | preflight (char count > `MAX_VOICE_CHARS`, empty text) |
| `say failed exit=3 … refused — text length` | 4a | runaway guard (12000). If the number in the message is 4000, an old ElevenLabs-era `say` is staged — the init container did not re-seed |
| `say failed exit=2` | 4a | `OPENCLAW_TTS_FALLBACK_URL` unset or Telegram bot token missing |
| `voice sent` but nothing in Telegram | 4b | detached child — read `~/clawd/.tmp/say/say-<pid>.log`; check `ffmpeg` and local-TTS reachability |
| Voice arrives after the news-links text | — | expected: stage 4b is detached and runs ~1 min/1200 chars |
| Voice changes speaker mid-briefing, or a silent stretch | 4b | seed/voice not pinned, or dead-air chunk — see the TTS topology notes in §2 |
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

**Known blind spots in that green — do not read it as "the briefing works":**

- `lastRunStatus=ok` tracks the *agent turn*, not the script: the 2026-08-18
  `exit code 3` failure recorded `ok`.
- The dispatch canary runs with **no model override**, so it exercises the
  fallback chain and stays green while a *pinned* cron cannot dispatch at all.
  Assert separately that no cron carries a `payload_model` (§2 query).
- `voice sent` is stage 4a. It does not observe the detached child, so it stays
  green when synthesis or upload fails. Only `~/clawd/.tmp/say/say-*.log` and a
  Telegram acknowledgement cover stage 4b.

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
- If a `--clear-model` needs undoing, re-pin with
  `openclaw cron edit <id> --model <model>` — but prefer fixing the provider. A
  pin is a deliberate loss of failover and should be justified in the job
  description, not left implicit.
- Cron state lives on the `openclaw-data` PVC and is not in git. Before editing a
  job, capture the current definition so the edit is reversible:
  `openclaw cron get <id> > /tmp/job-<id>.json` (keep it in the pod; it contains
  the chat id and household context — do not copy it into the repo).
- Do **not** hand-craft a `voice sent` line into `briefing.log` to silence the
  warning: the log is the evidence the health check reads, and faking it hides the
  next real failure.

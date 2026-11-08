# SOP: OpenClaw seeded runtime config (web search, memory embeddings, codex plugin strip)

> Description: The three boot-time config guards that keep OpenClaw's tools
> working on a login-only (ChatGPT/Codex OAuth) setup, why each exists, how to
> prove each one is live, and how to restore it. Also records the provider-disable
> block and the harmless `plugins.entries.*` "not installed" warnings.
> Version: `2026.11.08`
> Last Updated: `2026-11-08`
> Owner: `operator + openclaw-agent`

---

## 1) Description

OpenClaw (`ai/openclaw`, bjw-s app-template HelmRelease) re-installs its npm
packages on every pod boot and its config lives on the PVC. A fresh or drifted
config silently loses three behaviours that the household depends on, because
each one defaults to something that needs an API key or capability the ChatGPT
login does not have. The init script in
`kubernetes/apps/ai/openclaw/app/helmrelease.yaml` re-applies them on every boot.

- Scope: `ai/openclaw` config seeding (`openclaw.json`, `~/.codex/config.toml`).
- Prerequisites: `kubectl` (mise), repo access, GitOps push rights.
- Out of scope: model/provider selection and the OAuth lifecycle
  (`docs/sops/ai-integration.md`), briefing triage
  (`docs/sops/openclaw-briefing-delivery.md`), cron/sweep recovery
  (`docs/sops/operation-sweep-cron.md`).

## 2) Overview

| Guard | Symptom when missing | Setting | Commit |
|---|---|---|---|
| web_search provider | `web_search` answers "disabled or no provider is available" on every call; price/watch crons cannot search | `tools.web.search.provider = duckduckgo` | `8f51d787` (2026-11-01) |
| memory embeddings | memory index goes stale for days; embeddings call returns 401 `invalid_authentication` | `agents.defaults.memorySearch = {provider: ollama, model: nomic-embed-text:latest, remote.baseUrl: http://ollama-toolfix.ai.svc.cluster.local}` | `4696f187` (2026-10-31) |
| codex connector strip | the agent offers a "Google Calendar"/GitHub tool, tries it instead of the `gcal` CLI and tells the family the calendar is down | `[plugins."...@openai-curated"]` stanzas deleted from `~/.codex/config.toml` | `d5a21e69` (2026-10-31) |

Why each default is wrong here:

1. **web_search.** Providers that need no API key are never auto-selected; the
   provider must be named. DuckDuckGo needs no key.
2. **Embeddings.** The default `openai` embeddings provider sends the Codex
   ChatGPT-login token to `api.openai.com/v1/embeddings`. That token has no API
   scopes, so the endpoint answers 401. It only worked for a few hours after a
   re-login, which made the index go stale between re-logins. The local Ollama
   `nomic-embed-text` model needs no key and costs nothing.
3. **Codex plugins.** The codex app-server enables `google-calendar` and `github`
   from the `@openai-curated` marketplace by itself. They are never connected in
   this household (calendar = the `gcal` CLI via bash), so they are removed with
   an idempotent `sed` on every boot.

## 3) Blueprints

- Source of truth: `kubernetes/apps/ai/openclaw/app/helmrelease.yaml`, init
  script (config seeding block for web search and memory, shell block for the
  codex `config.toml` strip). Search for the comments `WEB SEARCH`,
  `MEMORY EMBEDDINGS` and `openai-curated`.
- Seeds are spread-merged into the PVC's `openclaw.json`, so a value an operator
  changes live is overwritten on the next boot. Change git, not the pod.
- The Ollama host is the shared Mac mini (`192.168.30.111:11434`), reached
  through the in-cluster `ollama-toolfix` Service; `nomic-embed-text:latest` must
  be present on it.

## 4) Operational Instructions

Changing any guard:

1. Edit the init script in `helmrelease.yaml` (check `git log -3 -- <file>`
   first: other sessions edit it).
2. Validate by rendering (`helm template` of the app-template values, not just
   kubeconform) and commit with `git commit --only <paths>`.
3. Before the pod rolls, check no OpenClaw cron is due within ~15 minutes and no
   `say` voice job is in flight (a roll kills a detached voice job).
4. Push; Flux reconciles; verify with section 6.

Provider-disable block (same init script, `disabledProviders`): it keeps 40+
unused LLM provider plugins disabled so a fresh PVC does not regress to a ~45 s
boot with a ~30 s event-loop stall (which kills the Discord WebSocket and the
Telegram poller mid-handshake). Do not remove it wholesale.

## 5) Examples

### Example A: web_search is "disabled"

`openclaw agent` replies that web search has no provider. Check the seed
(section 6, Test 1); if the value is missing, the guard was dropped from the
init script or the pod booted from an older revision.

### Example B: memory index stale after a clean re-login

Embeddings started failing again with 401. Confirm `memorySearch.provider` is
`ollama`, not `openai`, and that `ollama-toolfix` answers.

## 6) Verification Tests

Run from the repo root (`OC=$(kubectl -n ai get pod -l app.kubernetes.io/instance=openclaw -o jsonpath='{.items[0].metadata.name}')`).

### Test 1: openclaw.json guards

```bash
kubectl -n ai exec "$OC" -c app -- python3 -c "
import json;d=json.load(open('/home/node/.openclaw/openclaw.json'))
print(d['tools']['web']['search']); print(d['agents']['defaults']['memorySearch'])"
# expect {'provider': 'duckduckgo'} and provider ollama / nomic-embed-text:latest
```

### Test 2: codex connectors are gone

```bash
kubectl -n ai exec "$OC" -c app -- grep -c openai-curated /home/node/.codex/config.toml
# expect 0
```

### Test 3: live turn

```bash
kubectl -n ai exec "$OC" -c app -- openclaw agent -m "Reply with exactly this token: CANARY7F3" --session-id hc --timeout 90
# expect CANARY7F3 (the model line must be the configured primary)
```

## 7) Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `web_search` "disabled or no provider" | provider not named | restore `tools.web.search.provider` seed |
| embeddings 401 `invalid_authentication` | memorySearch back on `openai` | restore the Ollama memorySearch seed |
| memory index empty / Ollama unreachable | `nomic-embed-text` missing on the Mac mini, or `ollama-toolfix` down | pull the model via ollama-agent; check the Service |
| agent claims "calendar is down" while using a connector | `@openai-curated` stanzas returned in `config.toml` | the boot `sed` did not run or codex re-created them; roll the pod after fixing the script |
| 18 `plugins.entries.<id>: plugin not installed` lines on every `openclaw` command | the provider-disable block lists providers that are external plugins in this OpenClaw version (arcee, cerebras, chutes, cloudflare-ai-gateway, deepinfra, deepseek, fireworks, groq, ... zai) and are not installed | cosmetic. Those plugins cannot load, so the disable entry is redundant for them. Clean it up together with an OpenClaw version bump, by pruning those ids from `disabledProviders` AND deleting the stale keys from the live `plugins.entries` (spread-merge keeps old keys). Verify with `openclaw doctor` before and after. Also expect one `plugins.entries.discord: duplicate plugin id` line (config-selected plugin overrides the global one; intended) |
| Only `main` reaches openai; the other agents answer from the local fallback (`fallbackUsed=True`, "No route-compatible authentication source is configured for openai") | OpenClaw >= 2026.11 keeps one openai OAuth profile PER AGENT (no read-through from `main`) | the boot sequence imports `~/.codex/auth.json` into every agent (`models auth login` then `models auth activate`, then unsets the `openai/gpt-6-astra@profile` pin that activate writes); needs the gateway stopped and a valid codex login. Manual: `openclaw models auth login --provider openai --device-code --agent <id>` under a TTY (`script -qfc`), then activate and `openclaw config unset agents.entries.<id>.model` |
| `doctor --fix` exits 1 "Plugin migration source config changed or could not be read" | a configured provider moved out of the host package (web search `duckduckgo` is `@openclaw/duckduckgo-plugin` in 2026.11) so doctor cannot read the legacy-shaped config | install the plugin before doctor (init does) and re-run; the boot runs doctor up to 4 passes and parks a refused Codex sidecar in `~/.openclaw/doctor-held` |
| doctor refuses "temp workspace ancestor /tmp has group/world-writable mode 2777" | fsGroup makes the `/tmp` emptyDir 2777 and `/home/node` 2775 | init runs `chmod 1777 /tmp; chmod 755 /home/node` as root every boot |
| `codex` reported "not a bundled or verified official installation" (`provenance-invalid`) | plugin installed by raw `npm install` into the managed store | `openclaw plugins install @openclaw/codex@<ver> --force --accept-capabilities` (needs a valid config); the boot skips plugins already `trusted-official` because re-running it for discord fails ("no authoritative package-owner metadata"); discord runs from the global install with trust `record-missing`, which is expected |
| `tools.media.models` grows a duplicate whisper entry per boot | a guard still writing the legacy `tools.media.audio.models` shape | the guard writes `tools.media.models` (one entry, `env OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 whisper ...`) and leaves `audio.models` unset |
| "Skipping invalid skill ... description is required" | workspace `SKILL.md` without frontmatter `description:` | the boot adds a minimal frontmatter block from the first heading (idempotent) |
| `cron list` shows 9 more jobs than before | 2026.11 declares one `heartbeat:<agent>` job per agent (every 1h); the original 32 jobs are unchanged | expected count is 41 after the 2026.11.1 roll |
| HelmRelease `Failed ... stalled resources: Deployment Failed` while the pod is still booting | the Deployment progress deadline (10 min) is shorter than the first-boot migration; `upgrade.remediation.retries: 0` means no rollback | wait for the pod to become Ready, then `flux reconcile hr openclaw -n ai --force` |

## 8) Diagnose Examples

### Diagnose Example 1: "the agent says web search is unavailable"

```bash
kubectl -n ai exec "$OC" -c app -- openclaw agent -m "search the web for the weather in Berlin" --session-id hc --timeout 90
kubectl -n ai logs "$OC" -c app --since=1h | grep -i "web_search\|no provider"
```

Provider present in Test 1 but still failing means DuckDuckGo itself is
rate-limiting or unreachable from the pod; check egress before touching config.

### Diagnose Example 2: stale memory

```bash
kubectl -n ai exec "$OC" -c app -- openclaw memory status
```

A provider other than `ollama`, or an embeddings error, points at Test 1.

## 9) Health Check

`runbooks/health-check.sh` (OpenClaw block) covers dispatch, plugin skew, the
briefing cron and voice. The three guards above have no dedicated signal; run
section 6 after every change to the init script and after every pod rebuild that
also bumps `openclaw`.

## 10) Security Check

- Never print `~/.codex/auth.json` or any token while triaging; check age only.
- The embeddings path deliberately uses no credential. Do not "fix" a 401 by
  adding an API key to the config.
- Do not paste private hostnames or chat ids into commits or this document.

## 11) Rollback Plan

Revert the guard's commit (`git revert <sha>`), push, and let Flux roll the pod
(subject to the no-roll-during-crons rule). Reverting a guard restores the
broken default behaviour described in section 2.

## 12) References

- `kubernetes/apps/ai/openclaw/app/helmrelease.yaml`
- `docs/sops/ai-integration.md`, `docs/sops/openclaw-briefing-delivery.md`,
  `docs/sops/operation-sweep-cron.md`
- Commits `8f51d787`, `4696f187`, `d5a21e69`

## Version History

- `2026.11.08`: OpenClaw 2026.11.1 on node 24.22.2 (plan `openclaw-2026.11.1`): per-agent openai auth import, plugin install/trust, doctor loop, whisper `tools.media.models`, skills frontmatter repair, `ANTHROPIC_API_KEY` env (provider detection only), troubleshooting rows above.
- `2026.11.07`: created (closes the SOP-gap findings for web search, codex
  plugin strip and memory embeddings); records the cosmetic provider-entry
  warnings.

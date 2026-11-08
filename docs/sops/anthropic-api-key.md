# SOP: Anthropic API key — two copies, rotate both

> Description: The shared Anthropic API key lives as two SOPS-encrypted Secrets, one per namespace, because Kubernetes Secrets are namespaced and this cluster has no replicator. This SOP records where the copies are, who consumes them, and how to rotate or revoke the key without leaving a stale copy or a stale pod behind.
> Version: `2026.11.07`
> Last Updated: `2026-11-07`
> Owner: `Platform`

---

## 1) Description

One Anthropic API key (operator-owned, console.anthropic.com) is meant to be
shared by Open WebUI, OpenClaw and the web-development apps. A Secret cannot be
read across namespaces, so there are **two copies of the same value**. The
operator chose to keep it that way on 2026-11-07 (the alternative, one value in
`cluster-secrets` with placeholder Secrets, was offered and declined). That
choice has one cost: **a rotation must touch both copies and then restart every
consumer**, otherwise one namespace keeps serving the old key.

- Scope: `Secret/anthropic-api-key` in namespaces `ai` and `my-software-development`.
- Prerequisites: SOPS age key (`age.key` at the repo root), `sops` (a mise tool, often not on PATH in a plain terminal: the script finds it), `kubectl`, the pre-commit hooks.
- Out of scope: the roll mechanics for any Secret (`docs/sops/secret-rotation.md`), rotating the SOPS age key (`docs/sops/sops-encryption.md`).
- Never paste the key into chat, a commit message, a plan file or a shell command line. The script reads it with hidden input.

---

## 2) Overview

| Setting | Value |
|---------|-------|
| Secret name / key | `anthropic-api-key` / `ANTHROPIC_API_KEY` |
| Copy 1 | `kubernetes/apps/ai/openclaw/app/anthropic-api-key.sops.yaml` (namespace `ai`; usable by OpenClaw and Open WebUI) |
| Copy 2 | `kubernetes/apps/my-software-development/opencode-andreamosteller/app/anthropic-api-key.sops.yaml` (namespace `my-software-development`) |
| Created | `d04a9059f` (2026-11-07) |
| Tooling | `runbooks/rotate-anthropic-key.sh` (`--create` first time, no flag to rotate) |
| Reloader | restart is needed after a rotation (see section 4 step 3) |

### Consumers (keep this table current)

A copy that nothing references is dead weight, and a consumer that is not listed
is invisible to the next rotation. Update the table in the same commit that
wires a consumer.

| Namespace | Workload | How it reads the key | Status |
|-----------|----------|----------------------|--------|
| `ai` | OpenClaw | `ANTHROPIC_API_KEY` env from `secretKeyRef` (app container) + Reloader `secret.reloader.stakater.com/reload` lists `anthropic-api-key`; provider detection only, primary stays openai, no anthropic model in fallbacks | wired and live since the 2026.11.1 roll on 2026-11-08 (commit `610534c0b`); in-pod env hash equals the Secret hash; `openclaw models status` detects `anthropic`, `anthropic-openai` and `claude-cli` via env | wired |
| `ai` | Open WebUI | not wired yet (needs an Anthropic connection configured) | pending |
| `my-software-development` | `opencode-andreamosteller` | not wired yet; its own `opencode-andreamosteller-secrets` still carries an EMPTY `ANTHROPIC_API_KEY` | pending |
| `home-automation` | `pellet-price-monitor` | its own `secret.sops.yaml` carries an EMPTY `ANTHROPIC_API_KEY`; not shared | not using the shared copy |

An EMPTY `ANTHROPIC_API_KEY` in another Secret is a third place the key could
end up. If someone fills one in by hand, point it at `anthropic-api-key`
(`secretKeyRef`) instead, or add it as a row above and to the rotation.

---

## 3) Blueprints

- `kubernetes/apps/ai/openclaw/app/kustomization.yaml` lists copy 1.
- `kubernetes/apps/my-software-development/opencode-andreamosteller/app/kustomization.yaml` lists copy 2.

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: anthropic-api-key
stringData:
  ANTHROPIC_API_KEY: ENC[...]   # SOPS-encrypted; namespace comes from the Kustomization
```

---

## 4) Operational Instructions

### Rotate the key (the routine case)

1. **Mint the new key** in the Anthropic console. Keep the old one active until step 5.
2. **Write both copies** in your own terminal (hidden input):
   ```bash
   runbooks/rotate-anthropic-key.sh
   ```
   It writes both files, encrypts each next to its target, checks that each
   contains `ENC[` and not the key, and removes any temp file on failure.
3. **Commit both files together** (they must never diverge):
   ```bash
   git commit --only \
     kubernetes/apps/ai/openclaw/app/anthropic-api-key.sops.yaml \
     kubernetes/apps/my-software-development/opencode-andreamosteller/app/anthropic-api-key.sops.yaml \
     -F <msg-file>
   git push
   ```
   Source the DSN helper in a separate shell call, not the same one as `git commit`
   (`docs/sops/pre-commit-secret-scan.md`).
4. **Restart every consumer in the table above.** A rewritten Secret does not
   reach a running pod (`docs/sops/secret-rotation.md`). Check each workload for a
   Reloader annotation; if it has none, `kubectl rollout restart` it AFTER Flux has
   applied the new Secret (verify with Test 1 first). Do not restart OpenClaw during a
   due cron or a `say` in flight.
5. **Verify** (section 6), then **revoke the old key** in the Anthropic console.

### First-time create or wiring a new consumer

- Create: `runbooks/rotate-anthropic-key.sh --create`.
- New namespace: add a third copy file, add it to that app's `kustomization.yaml`, add its path to `FILES` in the script, and add a row to the consumer table. Do not hand-copy secrets between namespaces.
- Wire a consumer with `secretKeyRef` on `anthropic-api-key` / `ANTHROPIC_API_KEY`, then add it to the table.

### Revoke in an emergency (key leaked)

Revoke the key in the Anthropic console FIRST, then do the rotation above. A
revoked key makes every consumer fail loudly, which is the safe direction.

---

## 5) Examples

### Example A: routine rotation

```bash
runbooks/rotate-anthropic-key.sh
git diff --stat   # exactly the two files
```

### Example B: only one namespace was updated by mistake

Both files must carry the same value. Re-run the script, which rewrites both.
There is no supported way to edit one copy alone.

---

## 6) Verification Tests

### Test 1: both live Secrets changed and match each other

```bash
for ns in ai my-software-development; do
  kubectl -n $ns get secret anthropic-api-key -o jsonpath='{.metadata.creationTimestamp} {.metadata.resourceVersion}{"\n"}'
done
# compare a hash, never print the key:
for ns in ai my-software-development; do
  kubectl -n $ns get secret anthropic-api-key -o jsonpath='{.data.ANTHROPIC_API_KEY}' | shasum -a 256 | cut -c1-12
done
```

Expected:
- the two hashes are identical, and differ from the pre-rotation hash.

If failed:
- one Kustomization has not reconciled: `flux get kustomizations -A | grep -E "openclaw|opencode"`.

### Test 2: each consumer restarted after the Secret changed

Follow `docs/sops/secret-rotation.md` Test 2 and 3 for every row of the consumer
table (pod start time later than the Secret's change; in-pod value hash equals the
live Secret hash).

### Test 3: the new key works

Make one request through a consumer (or `curl` the Anthropic models endpoint with the key from a
trusted terminal). Expected: HTTP 200, not 401.

---

## 7) Troubleshooting

| Symptom | Likely Cause | First Fix |
|---------|--------------|-----------|
| `sops: command not found` in the script | `sops` is a mise tool not on PATH in a plain terminal | The script finds it under `~/.local/share/mise/installs`; run `mise install` if that fails. Earlier (2026-11-07) a version without the fallback left a plaintext file behind; the script now deletes any unencrypted file it wrote |
| 401 from one app after a rotation | That consumer was not restarted, or reads its own empty `ANTHROPIC_API_KEY` | Restart it; check the consumer table |
| One namespace works, the other 401s | Only one copy was updated or one Kustomization has not reconciled | Test 1 |
| Pre-commit hook rejects a commit | A decoded cluster Secret matches the diff | `docs/sops/pre-commit-secret-scan.md` |

---

## 8) Diagnose Examples

### Diagnose Example 1: which pods hold the old key?

```bash
# Secret change time vs pod start time (see docs/sops/secret-rotation.md Diagnose Example 1)
kubectl -n ai get pods -o custom-columns=NAME:.metadata.name,START:.status.startTime
kubectl -n ai get secret anthropic-api-key -o jsonpath='{.metadata.managedFields[*].time}{"\n"}'
```

Expected:
- every consumer started after the newest Secret write time.

If unclear:
- compare the in-pod env hash with the Secret hash (`secret-rotation.md` Test 3).

---

## 9) Health Check

```bash
for ns in ai my-software-development; do kubectl -n $ns get secret anthropic-api-key --no-headers; done
```

Expected:
- both exist, `Opaque`, 1 key.

Rotate on a schedule you choose (Anthropic keys do not expire by themselves) and after any suspected leak.

---

## 10) Security Check

```bash
git grep -n "sk-ant" -- . ':!docs/sops/anthropic-api-key.md' | head
grep -c 'ENC\[' kubernetes/apps/ai/openclaw/app/anthropic-api-key.sops.yaml kubernetes/apps/my-software-development/opencode-andreamosteller/app/anthropic-api-key.sops.yaml
```

Expected:
- no `sk-ant` hits in the repo; each file has `ENC[` values and a `sops:` block.
- the key never appears in chat, plans, findings or commit messages.

---

## 11) Rollback Plan

Re-run the script with the previous key (it is only valid until you revoke it in
step 5 of the rotation), commit both files, restart the consumers. If the old key
is already revoked, mint another one: there is no restore of a revoked key.

---

## 12) References

- `docs/sops/secret-rotation.md` (roll every consumer after a Secret change)
- `docs/sops/sops-encryption.md`, `docs/sops/pre-commit-secret-scan.md`
- `runbooks/rotate-anthropic-key.sh`
- Origin: commit `d04a9059f` (2026-11-07)

---

## Version History

- `2026.11.07`: Initial SOP. Two copies chosen on purpose (operator decision); rotation script added.

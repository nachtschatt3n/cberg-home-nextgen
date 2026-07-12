# SOP: Pre-Commit Secret Scan Hook

> Description: How the repo-tracked pre-commit hook (`.githooks/pre-commit`) blocks secret leaks into this public repository — its three scan layers, cluster-secret literal matching, known false-positive classes, failure modes, and safe bypass procedure.
> Version: `2026.07.12`
> Last Updated: `2026-07-12`
> Owner: `cberg-home operators`

---

## 1) Description

Every `git commit` in this repository runs a three-layer secret scan against
the **staged** content (index, via `git show ":$file"` — not the worktree).
The repo is public, so a single leaked credential, token, or private domain
is an incident. The hook blocks the commit (`exit 1`) if any layer fires.

- Scope: all staged text files in `cberg-home-nextgen` (binary files are
  skipped via `file ... | grep text`)
- Prerequisites: `git config core.hooksPath` set to `.githooks` (done once
  per clone); `kubectl` reachable for Layer 1 (optional — see failure modes)
- Out of scope: server-side scanning, history rewriting, secret rotation
  (see `docs/sops/sops-encryption.md` for encryption workflow)

---

## 2) Overview

| Setting | Value |
|---------|-------|
| Active hook | `.githooks/pre-commit` (repo-tracked) |
| Activation | `git config core.hooksPath .githooks` |
| Stale copy | `.git/hooks/pre-commit` — legacy pre-layered version, **inactive** (core.hooksPath overrides it); ignore/delete |
| Layer 1 | Substring match of staged content against decoded cluster Secret values (~175 literals) |
| Layer 1 cache | `${TMPDIR:-/tmp}/cberg-precommit-literals.cache`, TTL 600 s |
| Layer 2 | `kubernetes/**/*.sops.yaml` + `talos/**/*.sops.yaml` must carry a top-level `sops:` block |
| Layer 3 | Regex credential detectors (API keys, AWS, JWT, GitHub tokens, private keys, DB DSNs, passwords) |
| kubectl unreachable | **Fails open for Layer 1 only** (warning printed; Layers 2+3 still enforced) |
| Bypass | `git commit --no-verify` — emergency only, see Security Check |

### Layer 1 — cluster Secret literal scan

The hook pulls **every** Kubernetes Secret (`kubectl get secrets -A -o json`),
decodes the values, and `grep -F -f <literals>` substring-matches them
against each staged file. First match blocks the commit with
`Cluster-Secret value literal found in file (rotate if real)`.

kubectl is resolved in order: `PATH` → `~/.local/share/mise/shims/kubectl`
→ `mise exec -- kubectl`.

Filtering before a decoded value becomes a scan literal (all verified in the
embedded Python in `.githooks/pre-commit`):

- Skipped Secret **types**: `service-account-token`, `tls`,
  `dockerconfigjson`, `dockercfg`, `bootstrap.kubernetes.io/token`,
  `helm.sh/release.v1`
- Skipped **key names** (public identifiers, not credentials): `TIMEZONE`/`TZ`,
  `ca.crt`, `username`, `repository`/`repo`, `org`/`organization`, `image`,
  `OPENAI_URI_BASE`/`OPENAI_BASE`/`OLLAMA_BASE`/`OLLAMA_BASE_URL`,
  `TELEGRAM_ALLOWED_USERS`, `SECRET_ICLOUD_USERNAME`, `NEXTCLOUD_USERNAME`
- Skipped **value shapes**: length <8 or >256, multi-line, private-key/cert
  blocks, pure-lowercase dictionary words (≤15 chars), lowercase space-phrases
  (OIDC scopes like `"openid email profile"`), DNS-1123 k8s names ≤30 chars
  (`superset-postgresql`), bare IPv4/IPv6 literals, OCI image tags
  (`nginx:1.25-alpine`), in-cluster service DNS (`*.svc[.cluster.local][:port]`)

**FQDN false-positive gotcha:** the `SVC_DNS` skip only covers `.svc`
in-cluster names. A Secret value that is an **external FQDN** (e.g.
`host.<private-domain>`) stays in the literal list and substring-matches any
doc or manifest mentioning that hostname. **Prefer short hostnames over
FQDNs** in committed docs/manifests to dodge this. (For our private domain
the block is correct behavior — the domain must never be committed.)

Deliberate trade-off: a weak all-lowercase / hyphenated / space-separated
password stored in a Secret would be filtered out and slip past Layer 1.
Real secrets are generated strong (digits, case, symbols) per repo policy.

### Layer 2 — unencrypted `.sops.yaml`

Any staged file under `kubernetes/` or `talos/` whose name matches
`*.sops.yaml` is blocked unless its staged content contains a line starting
with `sops:`. This catches "decrypted in place and forgot to re-encrypt".

### Layer 3 — pattern detectors

Regexes run against staged content: API-key assignments (`api_key` + ≥20
alnum), AWS `AKIA[0-9A-Z]{16}`, `bearer`/`token` + ≥20 chars, `BEGIN ...
PRIVATE KEY`, DB DSNs with inline credentials (`postgresql`/`mysql`/
`mongodb` scheme + `user:pass@` — spelled out here in parts, since the
verbatim form would trip the detector in this very file), GitHub
`gh[pousr]_...` tokens, three-part `eyJ...` JWTs, generic
`secret|credential|auth` + ≥32 base64ish chars, and `password|passwd` +
≥8 non-space chars.

The password detector has a false-positive guard: it is suppressed when the
file also matches `example|sample|placeholder|your-password|CHANGEME|${...}|
<UPPER_TOKEN>|ENC[`. The **`ENC[` exemption** (commit `60293d0e`) exists
because SOPS ciphertext after a `password:` key (e.g.
`admin_password: ENC[AES256_GCM,...]`) is encrypted by definition — Layer 2
already verified the `sops:` block — and is not a plaintext leak.

---

## 3) Blueprints

- Source of truth file(s): `.githooks/pre-commit` (single self-contained bash
  script with embedded Python for Layer 1 literal extraction)
- Related manifests/templates: `.sops.yaml` (encryption creation rules that
  Layer 2 path-matching mirrors)
- Required IDs/constants: cache path
  `${TMPDIR:-/tmp}/cberg-precommit-literals.cache`, TTL `600` s; literal
  length window `8..256`

```bash
# Activation blueprint (once per clone)
git config core.hooksPath .githooks
```

---

## 4) Operational Instructions

Normal flow — the hook is automatic:

1. Stage your changes (`git add <specific files>`).
2. `git commit ...` — the hook prints `🔍 Scanning staged files for secrets...`
   then either `✅ No secrets detected` or `COMMIT BLOCKED` with a per-file
   violation list.
3. On a block, fix the staged content (SOPS-encrypt, replace the literal
   with an env-var/Secret reference, or shorten an FQDN to a hostname),
   re-stage, commit again.
4. Only bypass with `--no-verify` after the Security Check below.

Editing the hook itself:

1. Modify `.githooks/pre-commit` (it is repo-tracked — commit the change).
2. New Layer 1 skip rules go into the embedded Python (`SKIP_TYPES`,
   `SKIP_KEY_NAMES`, or a new anchored regex) with a comment explaining the
   false-positive class and the trade-off — follow the existing pattern.
3. Fix false positives at the audit-logic root cause; never blanket-bypass.

```bash
git add .githooks/pre-commit
git commit -m "fix(pre-commit): <what and why>"
git push
```

---

## 5) Examples

### Example A: blocked commit — cluster-secret literal (FQDN collision)

```bash
git commit -m "docs: add service URL"
# ✗ docs/applications.md
#   - Cluster-Secret value literal found in file (rotate if real)
```

Fix: the doc mentioned `myapp.<private-domain>` which exists verbatim in a
cluster Secret. Replace with the short hostname `myapp` (or `<DOMAIN>`
placeholder), re-stage, commit.

### Example B: stale literal cache after rotating a secret

```bash
# Just rotated a credential but the hook still matches the old value,
# or doesn't yet know the new one:
rm -f "${TMPDIR:-/tmp}/cberg-precommit-literals.cache"
git commit ...   # hook re-pulls fresh literals from the cluster
```

---

## 6) Verification Tests

### Test 1: hook is active and wired via core.hooksPath

```bash
git config core.hooksPath && test -x .githooks/pre-commit && echo OK
```

Expected:
- Prints `.githooks` then `OK`

If failed:
- Run `git config core.hooksPath .githooks`; `chmod +x .githooks/pre-commit`

### Test 2: hook blocks a planted credential (Layer 3)

```bash
# Assemble the AWS-key plant at runtime (a literal one here would block
# committing this SOP itself):
printf 'aws_key = %s%s\n' 'AKIA' 'ABCDEFGHIJKLMNOP' > hook-test.txt
git add hook-test.txt
git commit -m "test" ; echo "exit=$?"
git reset HEAD hook-test.txt && rm -f hook-test.txt
```

Expected:
- `COMMIT BLOCKED` with `AWS access key`, `exit=1`

If failed:
- Hook not executing — re-check Test 1; confirm the file was staged (hook
  scans the index, not the worktree)

### Test 3: Layer 1 literals load from the cluster

```bash
rm -f "${TMPDIR:-/tmp}/cberg-precommit-literals.cache"
touch hook-test2.txt && git add hook-test2.txt && git commit -m "test"
# observe: "· loaded N secret literals from cluster" (N ≈ 175)
git reset --soft HEAD~1 && git reset HEAD hook-test2.txt && rm -f hook-test2.txt
```

Expected:
- `loaded <N> secret literals from cluster` line, N in the low hundreds

If failed:
- `⚠ kubectl unreachable` means Layer 1 was skipped — check kubeconfig/VPN

---

## 7) Troubleshooting

| Symptom | Likely Cause | First Fix |
|---------|--------------|-----------|
| `Cluster-Secret value literal found` on an innocent doc | FQDN/identifier stored in some cluster Secret substring-matches your text | Use short hostname or placeholder; if the value is genuinely public, add its key to `SKIP_KEY_NAMES` or an anchored shape regex in the hook |
| `⚠ kubectl unreachable — skipping Layer 1` | No cluster access (VPN down, kubeconfig missing, off-LAN) | Restore access and re-commit; Layer 1 **fails open**, so treat the commit as unscanned against cluster literals |
| `Password pattern` on a SOPS file | Missing `ENC[` guard match — value after `password:` is plaintext | Encrypt the file with SOPS; if it is ciphertext and still flagged, the file lost its `sops:` block |
| `Unencrypted .sops.yaml file` | File decrypted in place and staged before re-encrypting | `sops -e -i <file>` in the repo path, re-stage |
| Hook doesn't run at all | `core.hooksPath` unset in a fresh clone (only stale `.git/hooks/pre-commit` present) | `git config core.hooksPath .githooks` |
| Old rotated secret still blocks | 10-min literal cache | `rm -f "${TMPDIR:-/tmp}/cberg-precommit-literals.cache"` |

```bash
# What exactly is the hook scanning? (index content, not worktree)
git diff --cached --name-only --diff-filter=ACM
git show ":path/to/file" | head
```

---

## 8) Diagnose Examples

### Diagnose Example 1: which cluster literal matched my file?

```bash
# Rebuild the literal list the hook uses, then find the exact match:
CACHE="${TMPDIR:-/tmp}/cberg-precommit-literals.cache"
git show ":docs/applications.md" | grep -F -f "$CACHE" | head -3
```

Expected:
- The offending line(s) print — the matching substring is a decoded value of
  some cluster Secret. **Do not paste the literal list itself anywhere.**

If unclear:
- Cache may be stale/empty; run a commit attempt first so the hook
  repopulates it, or loop: for each staged line, `grep -cF "<line>" "$CACHE"`

### Diagnose Example 2: Layer 1 silently inactive

```bash
kubectl get ns kube-system   # same probe the hook uses
ls -la "${TMPDIR:-/tmp}/cberg-precommit-literals.cache"
```

Expected:
- kubectl probe succeeds → Layer 1 will load fresh literals; a recent cache
  mtime (<10 min) means the hook used the cached list

If unclear:
- Check kubectl resolution order used by the hook: `command -v kubectl`,
  then `~/.local/share/mise/shims/kubectl`, then `mise exec -- kubectl`

---

## 9) Health Check

```bash
git config core.hooksPath                      # → .githooks
test -x .githooks/pre-commit && echo hook-ok   # executable
kubectl get ns kube-system >/dev/null && echo layer1-ok
```

Expected:
- All three checks pass; commits print the `loaded/cached ... secret
  literals` line (Layer 1 active) and end with `✅` or a block

---

## 10) Security Check

**Bypass policy (`git commit --no-verify`):** this repo is **public** — a
bypassed commit that leaks a credential or the private domain is published
to GitHub immediately and must be treated as compromised (rotate, don't just
revert; history rewriting does not un-leak). Before any `--no-verify`:

```bash
# 1. Eyeball every staged hunk yourself:
git diff --cached
# 2. Confirm the block is a known false-positive class (FQDN collision,
#    identifier overlap) — not a real secret.
# 3. Prefer fixing the content or the hook's skip rules over bypassing.
```

Expected:
- No plaintext secrets, tokens, or the private domain in staged content
- `--no-verify` used only for verified false positives, ideally never —
  fix false positives at the root cause in the hook instead
- Remember Layer 1 fails open off-LAN: an offline commit was **not** checked
  against cluster secrets; re-verify before push if it touched configs

---

## 11) Rollback Plan

```bash
# Roll back a bad hook change (hook is repo-tracked):
git log --oneline -- .githooks/pre-commit
git checkout <good-sha> -- .githooks/pre-commit
git commit -m "revert(pre-commit): restore working hook"

# Emergency: disable the hook entirely (LAST resort, re-enable ASAP):
git config --unset core.hooksPath      # re-enable: git config core.hooksPath .githooks

# A commit that leaked despite/around the hook:
# → rotate the exposed credential FIRST, then clean history.
```

---

## 12) References

- `.githooks/pre-commit` — the hook itself (extensively commented)
- `docs/sops/sops-encryption.md` — SOPS encrypt/decrypt workflow (Layer 2 context)
- `CLAUDE.md` — Information Security section (public-repo rules)
- Memory note `feedback_precommit_cluster_secret_match` — prefer short
  hostnames over FQDNs to dodge Layer 1 collisions
- Commits: `60293d0e` (ENC[ exemption), `62f4c27c` (OAuth scope phrases),
  `7e217387` (in-cluster service DNS skip)

---

## Version History

- `2026.07.12`: Initial SOP — documents the three-layer scan, Layer 1
  literal filtering and cache, fail-open behavior without kubectl, ENC[
  exemption, FQDN false-positive gotcha, and bypass policy.

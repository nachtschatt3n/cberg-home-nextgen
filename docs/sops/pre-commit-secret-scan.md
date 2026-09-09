# SOP: Pre-Commit Secret Scan Hook

> Description: How the repo-tracked pre-commit hook (`.githooks/pre-commit` plus the Layer 3 password guard `.githooks/lib/password-guard.awk`) blocks secret leaks into this public repository — its three scan layers, hunk-scoped cluster-secret literal matching, per-line/per-value suppressor scoping, known false-positive classes, failure modes, and safe bypass procedure.
> Version: `2026.09.09`
> Last Updated: `2026-09-09`
> Owner: `cberg-home operators`

---

## 1) Description

Every `git commit` in this repository runs a three-layer secret scan against
the **staged** content — never the worktree. Layer 1 reads the staged hunks
(`git diff --cached -U0`, added lines); Layers 2+3 read the full staged file
(`git show ":$file"`).
The repo is public, so a single leaked credential, token, or private domain
is an incident. The hook blocks the commit (`exit 1`) if any layer fires.

- Scope: all staged text files in `cberg-home-nextgen` (binary files are
  skipped via `file ... | grep text`)
- Prerequisites: `task install-hooks` run once per clone (sets
  `core.hooksPath` to `.githooks`); `kubectl` reachable for Layer 1
  (optional — see failure modes)
- Out of scope: server-side scanning, history rewriting, secret rotation
  (see `docs/sops/sops-encryption.md` for encryption workflow)

---

## 2) Overview

| Setting | Value |
|---------|-------|
| Active hook | `.githooks/pre-commit` (repo-tracked) |
| Sibling hook | `.githooks/commit-msg` — the vulnerability-disclosure guard (`docs/sops/vulnerability-disclosure.md`). Shares `core.hooksPath`, so it is installed and disabled by the SAME switch as this one |
| Activation | `task install-hooks` (sets `core.hooksPath .githooks`; installs BOTH hooks) |
| Stale copy | `.git/hooks/pre-commit` — legacy pre-layered version, **inactive** (core.hooksPath overrides it); ignore/delete |
| Layer 1 | Substring match of the **staged hunks** (added lines of `git diff --cached -U0`, per file) against decoded cluster Secret values (~200 literals) |
| Layer 1 cache | `${TMPDIR:-/tmp}/cberg-precommit-literals.cache`, TTL 600 s |
| Layer 2 | `kubernetes/**/*.sops.yaml` + `talos/**/*.sops.yaml` must carry a top-level `sops:` block |
| Layer 3 | Regex credential detectors (API keys, AWS, JWT, GitHub tokens, private keys, DB DSNs) **plus** the per-line password guard `.githooks/lib/password-guard.awk` |
| Guard failure mode | Missing or erroring guard = `MISSING`/`FAILED` violation — **fails closed**, never "clean" |
| kubectl unreachable | **Fails open for Layer 1 only** (warning printed; Layers 2+3 still enforced) |
| Bypass | `git commit --no-verify` — emergency only, see Security Check |

### Layer 1 — cluster Secret literal scan

The hook pulls **every** Kubernetes Secret (`kubectl get secrets -A -o json`),
decodes the values, and `grep -F -f <literals>` substring-matches them
against **the staged hunks of each file** — the added lines of
`git diff --cached -U0 -- <file>` — not the whole file content. First match
blocks the commit with
`Cluster-Secret value literal found in a staged hunk (rotate if real)`.

**Hunk-scoped since `2026.08.18`.** Previously Layer 1 scanned the entire
staged file (`git show ":$file"`), so a long-committed line that happens to
share a substring with some cluster Secret (most commonly a cluster-local
service URL that a Secret also contains) re-tripped the scanner on **every
later edit to that file**, forcing documented `--no-verify` bypasses for
innocent changes. A line you are not adding in this commit cannot leak
anything new, so pre-existing lines are out of scope; detection strength for
**newly added lines is unchanged** (same literal list, same filters, same
`grep -F` substring match). Layers 2 and 3 still scan full staged content.

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
**newly added** doc or manifest line mentioning that hostname (since
`2026.08.18` pre-existing lines no longer re-trip it). **Prefer short hostnames over
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

#### The password guard — `.githooks/lib/password-guard.awk`

The `password|passwd|secret_key|blowfish_secret` detector is **not** a grep. It
lives in its own program, `.githooks/lib/password-guard.awk`, which reads a
file's staged content on stdin and prints `line <N>` for the first line holding
a literal credential. The hook calls it per file and checks its **exit status**:
a non-zero exit is reported as `Password guard FAILED (awk exit N) — unscanned,
not clean`, and a missing guard file as `Password guard MISSING`. Both **fail
closed** — an unreadable guard must never read as a clean file.

**What it evaluates, and against what text.** The guard works **per line**, and
each suppressor is scoped to text that the credential itself does *not* control:

| Scope | What is judged | Examples of suppressors |
|-------|----------------|-------------------------|
| **Per VALUE** | the value only, and only its **syntactic shape** | `${X}` / `$X` / `$(cmd)` interpolation, `{{ helm }}`, `ENC[...]` SOPS ciphertext, `<template-token>`, `__file`/`__env` sentinels, filename-shaped values, `SCREAMING_SNAKE` env-var names |
| **Per CONTEXT** | the line **minus every credential value** — the key token, the comment, surrounding syntax | scaffolding words (`example`, `placeholder`, `change_me`, `your-`), reference mechanisms (`secretKeyRef`, `valueFrom`, `existingSecret`, `process.env`), and search/regex-literal context (`rg`/`grep`, `re.compile`) |
| **Exact allowlist** | the value, compared **whole** | five canonical template strings only (e.g. `replace-me`, `my-strong-password`). Deliberately exact, never substring |

Note what is **absent from the per-VALUE column: dictionary words.** A value is
exempted only for being *syntactically not a literal* — never for containing a
reassuring word. `placeholder_password: <a real secret>` is scaffolding and is
suppressed via the key token; `password: placeholder-XYZZY` is a password that
merely spells one, and it **fires**.

> The value above is **synthetic**. The credential that actually leaked was a
> bare dictionary word, and the property worth teaching is that *a credential
> whose text resembles a placeholder defeats any filter that reads the value* —
> which is precisely why it read as a generic example for 4.7 months. Describe
> that property; do not reprint the value. Documenting a self-suppressing
> credential by quoting it reproduces the leak it explains, and it is a
> second-order instance of rule 3 in `docs/sops/audit-script-correctness.md`.

The **`ENC[` exemption** (commit `60293d0e`) survives this scoping because it is
structural, not lexical: SOPS ciphertext after a `password:` key (e.g.
`admin_password: ENC[AES256_GCM,...]`) is encrypted by definition, and Layer 2
has already verified the `sops:` block.

> **This replaced a defect — do not reconstruct it.** Until 2026-09-08 the guard
> was two whole-**FILE** greps: flag on `(password|passwd)["\s:=]+[^"\s]{8,}`,
> then suppress if the file matched `example|placeholder|CHANGEME|\$\{|ENC\[`.
> Both halves were wrong in the same way — **they judged the line using text the
> line did not control**:
>
> - the suppressor was **file-wide**, so a single `${...}` *anywhere* in a file
>   disarmed the guard for that entire file. 73 of this repo's 112
>   `helmrelease.yaml` files carry a Flux postBuild variable, making the guard
>   inert on roughly 65% of them;
> - the placeholder filter matched the **credential's own value**, so a password
>   whose value was itself a bare scaffolding-style dictionary word satisfied its
>   own exemption and deleted its own finding.
>
> A real admin password self-suppressed on both counts at once and survived
> **4.7 months and 28 commits in this public repository**. Fixes: `f1720e57`,
> `588c353a`, `47a53c8e`, `09498745`. The generalised rule — *a suppressor may
> never be evaluated against text the thing being judged controls* — is rule 3
> of `docs/sops/audit-script-correctness.md`.

**Known residual holes in this layer** (measured 2026-09-08, documented in the
awk header so they get re-attacked rather than forgotten): an angle-template
opener, a filename-shaped value, a stray backtick in a comment line, and a
`SCREAMING_SNAKE` value read as an env-var name. Each is a value shape the
structural rules cannot separate from prose, and **each is still caught by
`security-check.py`'s history scan** — verified, not assumed. Do **not** close
one by widening a word list; that is the defect this file exists to prevent.

---

## 3) Blueprints

- Source of truth file(s): `.githooks/pre-commit` (bash, with embedded Python
  for Layer 1 literal extraction) **and** `.githooks/lib/password-guard.awk`
  (the Layer 3 password detector — the hook is no longer self-contained; the
  two are versioned and rolled back together, see §11)
- Guard regression suite: `runbooks/tests/test-cred-suppressor-scoping.py`
  (also gates commits: staging anything under `.githooks/lib/` runs the full
  `runbooks/tests/run-all.sh` suite, fail-closed)
- Related manifests/templates: `.sops.yaml` (encryption creation rules that
  Layer 2 path-matching mirrors)
- Required IDs/constants: cache path
  `${TMPDIR:-/tmp}/cberg-precommit-literals.cache`, TTL `600` s; literal
  length window `8..256`

```bash
# Activation blueprint (once per clone) — installs pre-commit AND commit-msg
task install-hooks
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

4. Password-detector changes go in `.githooks/lib/password-guard.awk`, never
   back into the hook. Prefer a **structural** rule (a value shape that is not
   a literal) over a dictionary word, and never let a suppressor read the
   value's own text — see §2 and rule 3 of `docs/sops/audit-script-correctness.md`.

```bash
# --only with explicit paths: this checkout is shared by several sessions and
# git's index is shared state (see CLAUDE.md).
git commit --only .githooks/pre-commit .githooks/lib/password-guard.awk \
    -m "fix(pre-commit): <what and why>"
git show --stat HEAD    # every file here must be yours
git push
```

---

## 5) Examples

### Example A: blocked commit — cluster-secret literal (FQDN collision)

```bash
git commit -m "docs: add service URL"
# ✗ docs/applications.md
#   - Cluster-Secret value literal found in a staged hunk (rotate if real)
```

Fix: the **newly added** doc line mentioned `myapp.<private-domain>` which
exists verbatim in a cluster Secret. Replace with the short hostname `myapp` (or `<DOMAIN>`
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

### Test 4: Layer 1 is hunk-scoped (pre-existing lines don't re-trip)

Run in a **throwaway repo** with the hook copied in — never plant real
literals in this repo's history:

```bash
T=$(mktemp -d) && cd "$T" && git init -q .   && cp /Users/mu/code/cberg-home-nextgen/.githooks/pre-commit hook.sh
LIT=$(awk 'NR==5' "${TMPDIR:-/tmp}/cberg-precommit-literals.cache")  # never echo it
printf 'pre-existing: x%sx\n' "$LIT" > doc.md && git add doc.md   && git commit -q --no-verify -m base
echo "innocent new line" >> doc.md && git add doc.md
bash hook.sh; echo "A exit=$? (want 0)"          # pre-existing literal: pass
printf 'leak: %s\n' "$LIT" > leak.md && git add leak.md
bash hook.sh; echo "B exit=$? (want 1)"          # newly added literal: block
cd / && rm -rf "$T"
```

Expected:
- `A exit=0` (innocent edit next to an old literal-bearing line passes)
- `B exit=1` (a newly added line containing a literal is blocked)

If failed:
- Layer 1 regressed to whole-file scanning, or the literal cache is
  empty/stale — check `.githooks/pre-commit` `check_file()` and Test 3

### Test 5: the password guard can actually FAIL (per-line/per-value scoping)

The point of this test is that the guard **fires**, not that it stays quiet. A
detector that matches nothing passes every run while seeing nothing — the exact
state that let a credential sit in this public repo for 4.7 months.

```bash
# Must each print `line N` — these are the two shapes that self-suppressed
# under the pre-2026-09-08 whole-file guard:
# NOTE the `%s` indirection: the plant is assembled at RUNTIME so this SOP
# does not itself carry a credential-shaped line. Writing them literally makes
# this file trip the very guard it documents, which blocks every later commit
# — and the honest fix is this, never adding the doc to an exclusion list.
printf 'password: %s\n' 'placeholder' | awk -f .githooks/lib/password-guard.awk
#   → line 1   (a value that merely SPELLS a scaffolding word)
printf 'email: admin@%s\nfoo: bar\npassword: %s\n' '${SECRET_DOMAIN}' 'Hunter2SevenXY' \
    | awk -f .githooks/lib/password-guard.awk
#   → line 3   (an unrelated ${...} elsewhere in the file no longer disarms it)

# Must each print NOTHING — legitimate suppressions still hold:
printf 'password: %s\n'              '${SUPERSET_PASSWORD}'        | awk -f .githooks/lib/password-guard.awk
printf 'admin_password: %s\n'        'ENC[AES256_GCM,data:xx]'    | awk -f .githooks/lib/password-guard.awk
printf 'placeholder_password: %s\n'  'Hunter2SevenXY'             | awk -f .githooks/lib/password-guard.awk
printf 'passwordSecretRef: %s\n'     'my-app-credentials'         | awk -f .githooks/lib/password-guard.awk

python3 runbooks/tests/test-cred-suppressor-scoping.py
```

Expected:
- the first two print `line 1` and `line 3`; the next four print nothing
- the regression suite passes

If failed:
- **Nothing printed for the first two** → the guard is inert. Do not commit;
  this is the original defect. Check that the per-CONTEXT block reads only the
  key token + comment (`ctx`), never `val`, and that no rule was re-scoped to
  `$0` or to whole-file text.
- **Something printed for the last four** → a structural suppressor was lost;
  fix it in the awk program, not by widening a word list.

### Test 6: the guard fails CLOSED when it is missing or broken

Run in a **throwaway repo** — never plant credentials in this repo's history.

```bash
T=$(mktemp -d) && cd "$T" && git init -q . && mkdir -p hooks/lib
cp /Users/mu/code/cberg-home-nextgen/.githooks/pre-commit hooks/pre-commit
printf 'password: %s\n' 'Hunter2SevenXY' > leak.yaml && git add leak.yaml

bash hooks/pre-commit >/dev/null 2>&1; echo "A exit=$? (want 1)"   # guard ABSENT
cp /Users/mu/code/cberg-home-nextgen/.githooks/lib/password-guard.awk hooks/lib/
bash hooks/pre-commit >/dev/null 2>&1; echo "B exit=$? (want 1)"   # guard PRESENT, real finding
git rm -q --cached leak.yaml && rm leak.yaml
printf 'password: %s\n' '${SUPERSET_PASSWORD}' > ok.yaml && git add ok.yaml
bash hooks/pre-commit >/dev/null 2>&1; echo "C exit=$? (want 0)"   # clean file passes
cd / && rm -rf "$T"
```

Expected (verified 2026-09-09):
- `A exit=1` with `Password guard MISSING (.githooks/lib/password-guard.awk) —
  unscanned, not clean` — a rollback that drops the `.awk` blocks every commit
  rather than silently scanning nothing
- `B exit=1` with `Password pattern (line 1)`
- `C exit=0` — the guard is not simply blocking everything

If failed:
- `A exit=0` is the serious one: the hook fell back to "clean" with no detector.
  Check the `elif [ -f "$PW_GUARD" ]` / `else` branches in `check_file()`.

---

## 7) Troubleshooting

| Symptom | Likely Cause | First Fix |
|---------|--------------|-----------|
| `Cluster-Secret value literal found` on an innocent doc | FQDN/identifier stored in some cluster Secret substring-matches a line you are ADDING (pre-existing lines no longer trip it) | Use short hostname or placeholder; if the value is genuinely public, add its key to `SKIP_KEY_NAMES` or an anchored shape regex in the hook |
| `⚠ kubectl unreachable — skipping Layer 1` | No cluster access (VPN down, kubeconfig missing, off-LAN) | Restore access and re-commit; Layer 1 **fails open**, so treat the commit as unscanned against cluster literals |
| `Password pattern` on a SOPS file | Missing `ENC[` guard match — value after `password:` is plaintext | Encrypt the file with SOPS; if it is ciphertext and still flagged, the file lost its `sops:` block |
| `Password guard MISSING` on every file | `.githooks/lib/password-guard.awk` absent — usually a rollback of `.githooks/pre-commit` alone (§11) | Restore BOTH paths at the same sha; re-run Verification Test 5 |
| `Password guard FAILED (awk exit N)` | The awk program errored — syntax break, or an awk that rejects it | Run `awk -f .githooks/lib/password-guard.awk </dev/null; echo $?`; revert the guard to its last good sha. **Do not** bypass: exit≠0 means the file was never scanned |
| `Password pattern` on a value that is genuinely not a secret | The value's SHAPE is indistinguishable from a literal | Add a **structural** rule (or an exact-match template literal, mirrored into `_TEMPLATE_LITERALS` in `security-check.py`) — never a dictionary word, and never a suppressor that reads the value's own text |
| `Unencrypted .sops.yaml file` | File decrypted in place and staged before re-encrypting | `sops -e -i <file>` in the repo path, re-stage |
| Hook doesn't run at all | `core.hooksPath` unset in a fresh clone (only stale `.git/hooks/pre-commit` present) | `task install-hooks` |
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
# Rebuild the literal list the hook uses, then find the exact match among
# the ADDED lines (what Layer 1 actually scans since 2026.08.18):
CACHE="${TMPDIR:-/tmp}/cberg-precommit-literals.cache"
git diff --cached -U0 -- docs/applications.md \
  | awk '/^@@/{h=1;next} h&&/^\+/{print substr($0,2)}' \
  | grep -F -f "$CACHE" | head -3
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
test -x .githooks/commit-msg  && echo msg-hook-ok  # disclosure guard
kubectl get ns kube-system >/dev/null && echo layer1-ok
```

Expected:
- All four checks pass; commits print the `loaded/cached ... secret
  literals` line (Layer 1 active) and end with `✅` or a block
- `core.hooksPath` is a **shared** switch: if it is unset, the commit-msg
  disclosure guard is off too, silently

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

**The hook is two files, and they must move together.** Since 2026-09-08 the
Layer 3 password detector lives in `.githooks/lib/password-guard.awk`, which
`.githooks/pre-commit` invokes by path. Rolling back `pre-commit` **alone** is
never correct and fails in one of two ways depending on the direction:

- to a sha **before** the guard was extracted → you reinstate the whole-file
  suppression defect described in §2 (the guard goes inert on ~65% of
  helmreleases) while `password-guard.awk` sits unused on disk;
- to a sha **after** the extraction, with the `.awk` file deleted or reverted
  away → every scanned file reports `Password guard MISSING — unscanned, not
  clean` and **all commits block**.

So roll back the pair, and always re-run the guard tests afterwards:

```bash
# Roll back a bad hook change — BOTH paths, same sha (both are repo-tracked):
git log --oneline -- .githooks/pre-commit .githooks/lib/password-guard.awk
git checkout <good-sha> -- .githooks/pre-commit .githooks/lib/password-guard.awk

# Confirm the pair is coherent BEFORE committing: the guard must exist, be
# readable by awk, and still detect a planted credential.
test -f .githooks/lib/password-guard.awk || echo "FAIL: guard missing — commits will block"
printf 'password: %s\n' 'Tr0ub4dor3xample' | awk -f .githooks/lib/password-guard.awk
#   → must print `line 1`. Silence here means the guard is inert: STOP.
python3 runbooks/tests/test-cred-suppressor-scoping.py

git commit --only .githooks/pre-commit .githooks/lib/password-guard.awk \
    -m "revert(pre-commit): restore working hook + password guard"
```

> Rolling back only because the guard is *too noisy* is the wrong lever: fix the
> false positive at its root in the awk program (a new **structural** rule, or a
> new exact-match template literal) rather than reverting to a version that
> could not see. If you add a template literal, `_TEMPLATE_LITERALS` in
> `security-check.py` must be updated to match — `test-cred-suppressor-scoping.py`
> asserts the two sets are identical, because three copies had already drifted.

# Emergency: disable the hook entirely (LAST resort, re-enable ASAP):
#   ⚠ This unsets the hooks path for the WHOLE clone, so it also disables
#   .githooks/commit-msg — the vulnerability-disclosure guard on a PUBLIC
#   repo — with no warning, and leaves it off for every later commit.
#   Prefer a scoped, single-commit `git commit --no-verify` and re-review
#   the message by hand; unset the path only if the hook itself is broken.
git config --unset core.hooksPath      # re-enable: task install-hooks

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
- `.githooks/lib/password-guard.awk` — the Layer 3 password detector; its
  header documents the replaced defect and the known residual holes
- `runbooks/tests/test-cred-suppressor-scoping.py` — guard regression suite
- `docs/sops/audit-script-correctness.md` — rule 3: a suppressor may never be
  evaluated against text the thing being judged controls
- Commits: `60293d0e` (ENC[ exemption), `62f4c27c` (OAuth scope phrases),
  `7e217387` (in-cluster service DNS skip); `036676c5` (hunk-scoped Layer 1, 2026-08-18);
  `f1720e57`, `588c353a`, `47a53c8e`, `09498745` (per-line/per-value guard scoping, 2026-09-08)

---

## Version History

- `2026.07.12`: Initial SOP — documents the three-layer scan, Layer 1
  literal filtering and cache, fail-open behavior without kubectl, ENC[
  exemption, FQDN false-positive gotcha, and bypass policy.
- `2026.08.18`: Layer 1 hunk-scoped — scans only the staged added lines
  (`git diff --cached -U0`) so pre-existing committed lines can't re-trip
  the scanner; Verification Test 4 added; troubleshooting/diagnose recipes
  adjusted to the hunk-scoped flow.
- `2026.08.18`: `core.hooksPath` is a SHARED switch — activation is now
  `task install-hooks` (installs pre-commit AND the commit-msg
  vulnerability-disclosure guard), and the Rollback Plan warns that
  `git config --unset core.hooksPath` silently disables the disclosure
  guard too. Health Check asserts both hooks.
- `2026.09.09`: **§2 no longer documents the whole-file suppression as intended
  design.** The Layer 3 password detector is described as what it now is — the
  per-line, per-value/per-context guard in `.githooks/lib/password-guard.awk` —
  with the replaced defect quarantined in a clearly-labelled historical note,
  the known residual holes listed, and the fail-closed MISSING/FAILED branches
  documented. §11 Rollback rewritten: the hook is **two files**, and restoring
  `.githooks/pre-commit` alone either reinstates the defect or blocks every
  commit on `Password guard MISSING`; the recipe now moves both paths at one
  sha and verifies the pair before committing. §3, §4, §7 and §12 updated to
  match; Verification Tests 5 (the guard can fail) and 6 (it fails closed)
  added.

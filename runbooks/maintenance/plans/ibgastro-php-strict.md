---
plan_id: ibgastro-php-strict
component: ibgastro
pr: https://github.com/nachtschatt3n/ibgastro/pull/1
kind: image
current: "sha-73f8d53d8db8a962079d30f38582479f2cb5bff3 — emits ~380 PHP Strict Standards notices per request"
target: "new sha-<merge-commit> built from master with Configure::write('log', <mask>) in app/config/core.php"
update_type: config                   # one-line change in the app's own config file; no dependency moves
risk: low
est_duration_min: 30
needs_reboot: false
touches:
  namespaces: [my-software-showcase]
  resources:
    - helmrelease/ibgastro
    - "ghcr.io/nachtschatt3n/ibgastro"
  shared: []
depends_on: []
conflicts_with: []
status: draft
window: null
auto_execute: false                   # changes which PHP diagnostics reach the log stream
security_ref: null
sops_refs:
  - docs/sops/log-volume-runaway.md
  - docs/sops/new-deployment-blueprint.md
generated: "2026-08-18"
---

# ibgastro: stop the PHP Strict Standards notices at source

## 1) Summary & why held

`05f07143` fixed the *driver* of the log storm (probe path split: readiness and
startup moved to a static nginx `/healthz`, liveness kept on the deep CakePHP
`/health` route). Measured effect, live: **183,425 lines/hour → 45,600
lines/hour, a 75.1% cut**, exactly as predicted.

The remaining 45,600/hour is the liveness probe still booting the framework 120
times an hour at ~380 notices per boot. That is the *source*, and it is not
fixable from this repo — it needs the image.

**This plan is held for operator go/no-go because the root cause is not what
the investigation brief assumed, and the fix therefore lands somewhere with
more semantic weight than a php.ini line.**

## 2) Root cause (corrected)

The php.ini in the image **already** carries the right value:

```
error_reporting = E_ALL & ~E_DEPRECATED & ~E_STRICT & ~E_NOTICE   # ineffective
```

It is a no-op. CakePHP 1.3 calls `error_reporting()` itself at runtime, after
the ini is read, so the ini can never win:

- `cake/bootstrap.php:28` — unconditional `error_reporting(E_ALL & ~E_DEPRECATED);`
- `cake/libs/configure.php:117-135` — `Configure::write('debug'/'log')`
  recomputes the level and calls `error_reporting()` again.

With `Configure::write('log', true)` and `debug=0`, configure.php takes the
`else` branch and lands on `E_ALL & ~E_DEPRECATED`. **Since PHP 5.4, `E_ALL`
includes `E_STRICT`** — so Strict Standards is back ON for every request.

The multiplier: `cake/libs/cake_log.php:290` registers
`set_error_handler(array('CakeLog','handleError'))` while `handleError()` is
**non-static**. PHP raises that strict notice on *every* handler invocation,
while the handler is already running, so it cannot be swallowed and goes
straight to the error log. `handleError()` even `return`s early for codes
2048/8192 — CakePHP never wanted to log these.

**A pure Dockerfile/php.ini fix is impossible here.** That is why this is a
plan and not a merged PR.

## 3) The change (PR #1, CI green, NOT merged)

Branch `fix/silence-strict-deprecated-log-flood`, commit `c6e60e8`, base
`master`.

`app/config/core.php:88`:

```php
- Configure::write('log', true);
+ Configure::write('log', E_ALL & ~E_STRICT & ~E_DEPRECATED & ~E_NOTICE);
```

This takes the `is_integer($_this->log) && !$_this->debug` branch in
configure.php, which sets `error_reporting()` to exactly that mask. The integer
form is documented in that file's own comment block (lines 52-56).

`Dockerfile` — comment only, recording that the ini value is overridden by the
framework and pointing at core.php.

**Kept on** (load-bearing — do NOT widen this to `error_reporting = 0`):
`E_ERROR`, `E_WARNING`, `E_PARSE`, `E_RECOVERABLE_ERROR`, `E_USER_*`. Real
errors are still raised, still handled by CakeLog, still logged.

**Scope note for the reviewer:** this touches `app/config/`, CakePHP's
configuration file — not a controller, model, view, or framework file. Only
production behaviour changes: with `CAKEPHP_DEBUG=1/2` the integer branch is
not taken and dev behaviour is unchanged.

## 4) Pre-checks

1. Confirm the PR still shows CI green and no new commits on `master`:
   `gh pr checks 1 --repo nachtschatt3n/ibgastro`
2. Note that `master` has **already moved past the deployed pin** — `feb0512`
   ("docs: agent context") built and published after
   `sha-73f8d53d8db8a962079d30f38582479f2cb5bff3`. Merging this PR therefore
   rolls TWO commits into the cluster, not one. Review `feb0512` before the
   window; if it is docs-only as its subject claims, this is not a concern.
3. Record the current line rate for the before/after comparison
   (`docs/sops/log-volume-runaway.md` §8.12).

## 5) Execution

1. Merge PR #1 on `nachtschatt3n/ibgastro` (operator, or `gh pr merge 1 --squash`).
2. Wait for the `build-push.yml` run on `master` to complete. It builds, loads
   locally, runs `scripts/smoke-test.sh` (MySQL 5.7 + seeds + real HTTP auth
   assertions + the `assert_no_external_hosts.sh` egress gate), and only then
   pushes to GHCR.
3. Read the new long-form sha tag from the run:
   `gh run view <id> --repo nachtschatt3n/ibgastro --log | grep 'sha-'`
4. In this repo, bump the pin in
   `kubernetes/apps/my-software-showcase/ibgastro/app/helmrelease.yaml`:
   `tag: sha-<new-40-char-sha>`. **Digest-pinned sha tag only — never `latest`
   or `master`.**
5. `mise exec -- task kubeconform`, commit, push. Flux reconciles via webhook.

## 6) Verification

- Pod rolls, `1/1 Running`, `RESTARTS 0`.
- Liveness still passes on the deep route:
  `kubectl exec -n my-software-showcase <pod> -c app -- wget -qO- http://127.0.0.1/health`
- Line rate on the NEW pod, measured at least 2 minutes after Ready
  (`docs/sops/log-volume-runaway.md` §8.12):
  - before this plan: **45,600/hour**
  - expected after: **~200-500/hour** (see residual below)
- 24h later, the whole-stream error count returns to the measured non-storm
  baseline of ~44,000/day (§8.6). It is a trailing window; do not judge it at
  T+10 minutes.
- The app still serves: sign-in page loads, demo credential prefill works.

## 7) Known residual (accepted, not blocking)

~1-2 lines per request survive, emitted **before** core.php loads:

- `bootstrap.php:38` calls `Configure::getInstance()` statically.
- `object.php` declares both `Object()` and `__construct()` → one "Redefining
  already defined constructor" per compile.

Removing these needs edits inside `cake/` (vendored framework — out of scope).
Enabling OPcache in the image would eliminate the compile-time one and is worth
a separate look on PHP 5.6 regardless. At 120 liveness probes/hour the residual
is a few hundred lines/day, which is noise-floor.

Second-order: if duplicate lines persist after the fix, the php-fpm →
nginx-FastCGI double-log path is live. Either set `catch_workers_output = no`
(nginx then carries them) or confirm `/dev/stderr` is writable by the worker.
Do not chase this before the error-level fix lands — the volume driver is the
level, not the duplication.

## 8) Risk & rollback

**Risk: low.** The change narrows which diagnostic classes are *reported*; it
does not alter control flow, and the classes removed are ones CakePHP's own
error handler discards anyway. Blast radius is one showcase demo app with no
users depending on it and no data at risk.

**Main risk to name honestly:** if the app ever relied on an `E_NOTICE`-level
message to diagnose a fault, that message is now gone. Mitigation: `E_WARNING`
and above are untouched, and `CAKEPHP_DEBUG=1` restores full reporting for
debugging without a rebuild.

**Rollback:** revert the tag bump in this repo —
`git revert <sha> && git push` — which returns the pin to
`sha-73f8d53d8db8a962079d30f38582479f2cb5bff3`. The upstream PR can stay
merged; the cluster pin is the only thing that matters. Never `git reset
--hard` or force-push.

## 9) Interference surface

None. Single namespace, single HelmRelease, no shared infrastructure, no
reboot, no storage or database change, no other plan touches
`my-software-showcase`. Safe to sequence anywhere in a window.

---
plan_id: ibgastro-php-strict
component: ibgastro
pr: null                              # upstream PR lives in a DIFFERENT repo; maintenance-plan.py compares `pr:` against THIS repo's Renovate PR numbers, so a URL is permanently "ORPHAN". URL: github.com/nachtschatt3n/ibgastro/pull/1
kind: image
current: "sha-73f8d53d8db8a962079d30f38582479f2cb5bff3 — emits ~380 PHP Strict Standards notices per request"
target: "new sha-<merge-commit> built from the default branch with an integer error-reporting mask in the app config"
update_type: refactor                 # one-line change in the app's own config file; no dependency moves
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
status: awaiting-go                   # PR open + CI green; blocked only on operator go/no-go
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

> ### THE TRAP
>
> **The image's php.ini already sets the correct `error_reporting`, and it is a
> no-op.** The obvious fix looks right, is already present, and does nothing.
>
> Anyone triaging this will reach for php.ini first, find the value they were
> about to add already sitting there, and conclude the notices must be coming
> from somewhere else. They are not. The ini is simply overruled:
>
> 1. php.ini is read at startup and sets the mask correctly.
> 2. CakePHP 1.3 then calls `error_reporting()` **itself, at runtime**, in two
>    places, and whatever it computes wins.
> 3. What it computes is `E_ALL & ~E_DEPRECATED` — and **`E_ALL` has included
>    `E_STRICT` since PHP 5.4**, so Strict Standards comes straight back on.
>
> The general lesson, which is why this is worth writing down: **a runtime that
> can call `error_reporting()` (or its equivalent) makes every static config
> file advisory.** Verify the EFFECTIVE value at request time, not the value in
> the config file. The same shape appears elsewhere in this cluster — see
> F-a49c67c3, where `RAILS_LOG_TO_STDOUT=1` is set correctly on four apps and is
> equally inert because the image never reads it.


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

> The image repo is **private**. Branch names, commit SHAs and CI script names
> are deliberately omitted here — this repo is public. Read them from the PR.

The single functional line, in the app's CakePHP config
(`app/config/core.php` — a standard, publicly-documented CakePHP path):

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
2. Note the image repo's default branch has **already moved past the deployed
   pin** by one commit (subject suggests docs-only). Merging this PR therefore
   rolls TWO commits into the cluster, not one. Confirm the intervening commit
   is inert before the window.
3. Record the current line rate for the before/after comparison
   (`docs/sops/log-volume-runaway.md` §8.12).

## 5) Execution

1. Merge PR #1 on `nachtschatt3n/ibgastro` (operator, or `gh pr merge 1 --squash`).
2. Wait for the image build workflow on the default branch to complete. It
   builds, loads the image locally, runs the repo's smoke-test suite (real
   database + HTTP auth assertions + an outbound-host gate) and only pushes to
   GHCR if that passes.
3. Read the new long-form sha tag from the workflow run
   (`gh run view <id> --repo <image-repo> --log | grep 'sha-'`).
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
- The app still serves: the sign-in page loads and behaves as before.

### CONTENTS ASSERTION — the FLOOR, not only the ceiling

**A ceiling with no floor is a shape check.** This plan's headline metric is
"log lines should go *down*", and the best possible score on that metric is
**zero lines/hour** — which is also exactly what an app that has stopped
shipping logs entirely produces. That is not hypothetical here: this repo
already has **four Rails apps that are `Running`, have `RAILS_LOG_TO_STDOUT=1`
set correctly, and ship zero log documents** because the image never reads it
(F-a49c67c3, cited in §2 above). Silencing a *diagnostic class* and silencing
the *log pipeline* are indistinguishable from the ceiling alone.
See `docs/sops/verification-contents-not-shape.md`.

**CONTENTS ASSERTION: documents from this container still reach Elasticsearch
after the change — a non-zero floor — and the surviving lines are the right
ones.**

```
# In logs-generic-default, filtered to
#   resource.attributes.k8s.namespace.name = my-software-showcase
#   resource.attributes.k8s.container.name = <ibgastro container>
# over a 1h window that STARTS after the roll:
#
#   a) total documents  > 0        <-- THE FLOOR. Zero = the pipeline died, not a win.
#                                      Expect ~200-500 (access/liveness lines survive).
#   b) documents matching *Strict Standards*  == 0   <-- the ceiling, the intended effect
#   c) at least one ordinary request/access line is present, proving the stream
#      is live rather than merely quiet.
```

```bash
# corroborate at the pod, so a broken ES/edot path cannot be mistaken for success
# (and vice versa — if the pod emits and ES does not receive, that is a DIFFERENT
#  incident and must be raised, not silently absorbed into this plan's success)
mise exec -- kubectl logs -n my-software-showcase deploy/ibgastro --since=10m | wc -l          # > 0
mise exec -- kubectl logs -n my-software-showcase deploy/ibgastro --since=10m \
  | grep -c 'Strict Standards' || echo 0                                                       # 0
```

If (a) is zero: **do not record this plan as successful.** Roll back or
investigate the log path first — a plan that appears to have removed 100% of an
app's logging has removed the wrong thing.

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

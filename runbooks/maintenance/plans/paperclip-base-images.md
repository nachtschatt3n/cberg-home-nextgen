---
plan_id: paperclip-base-images
component: paperclip
pr: null                              # digest-pinned base images; no Renovate PR (float-tag policy)
kind: image
current: "mise-install initContainer: debian trixie-slim@sha256:26f98ccd… (built 2026-03-16, ~Debian 13.4-era) | tools container: ubuntu 24.04@sha256:d78ab76…"
target: "mise-install initContainer: debian 13.6-slim | tools container: ubuntu 26.04 — RECOMMENDED: DO NOT EXECUTE, see §1b"
update_type: major                    # driven by the ubuntu leg; the debian leg is an intra-major (13.4→13.6) refresh, see §1a
risk: medium                          # debian leg: medium (persisted toolchain, ABI risk). ubuntu leg: not executed by default (see below)
est_duration_min: 40
needs_reboot: false
touches:
  namespaces: [ai]
  resources:
    - helmrelease/paperclip
    - pvc/paperclip-data                          # /paperclip — persists mise-install's built toolroot
    - initcontainer/mise-install (debian leg)
    - container/tools (ubuntu leg — sidecar, not on request path)
  shared: []                                       # no ingress/cert-manager/cilium/coredns/shared-DB perturbed;
                                                    # paperclip-postgresql is a SEPARATE Deployment (see conflicts_with)
depends_on: []
conflicts_with: ["paperclip-postgresql-18.6"]      # placeholder name for the parallel postgres 17->18 plan being
                                                    # written independently — confirm the ACTUAL plan_id at vetting
                                                    # time (see §6 Interference notes for why ordering matters)
status: draft
window: null
# auto_execute RETIRED 2026-08-26 (P2.1b) — execution class is derived from
# capability_change/rollback_class per runbooks/autonomy-policy.yaml.
security_ref: F-ae420ae8              # live accepted-risk finding for the ubuntu leg (AR-101); F-afa93406 is its
                                       # resolved predecessor recording the original hold decision. Detail DB-only.
capability_change: false              # no user-visible behaviour change on either leg
rollback_class: git-revert
finding_refs: []                      # not a P2.2 sweep-dispatched finding; direct held-update input
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/vulnerability-disclosure.md
generated: "2026-09-05"
---

# paperclip: two base-image bumps — debian (mise-install) + ubuntu (tools sidecar)

## 1) Summary & why held

Both images live in `kubernetes/apps/ai/paperclip/app/helmrelease.yaml`, in two
unrelated containers of the `paperclip` controller. They were bundled into one
sweep item because they're both digest-pinned base-image bumps on the same
component, but **they are different questions with different answers.**

### 1a) `mise-install` initContainer: `debian:trixie-slim` → `13.6-slim`

**This is NOT a codename→number no-op rename, despite trixie being Debian 13
both before and after.** Verified against the registry, not assumed from the
tag string:

- The **currently pinned** digest
  (`sha256:26f98ccd92fd0a44d6928ce8ff8f4921b4d2f535bfa07555ee5d18f61429cf0c`)
  decodes to an image built `2026-03-16T00:00:00Z` (OCI `created` annotation,
  debuerreotype build). That build date lands two days after **Debian 13.4**
  released (2026-03-14) — i.e. the container running today is effectively a
  13.4-era `trixie-slim` snapshot, not 13.6.
- The **`13.6-slim`** tag today resolves to digest `sha256:d7e12182…`, which is
  **byte-identical** to the current floating `trixie-slim` tag (same digest,
  both `last_updated: 2026-08-25`). Debian 13.6 released 2026-07-11; no 13.7
  exists yet (`13.7-slim` → 404 on Docker Hub as of this check).
- **Conclusion: this is a real intra-major refresh, ~13.4 → 13.6**, carrying
  roughly two Debian point releases (13.5, 13.6) of security-only package
  patches — glibc, gcc, openssl, binutils, coreutils, apt — NOT a distro
  major bump (still Debian 13) and NOT a no-op digest-only republish. The
  auto-updater's "unknown" classification is a **codename-vs-number string
  comparison blind spot** (it cannot semantically diff `trixie-slim` against
  `13.6-slim`), not evidence of anything more dramatic than the above.

**Why this needs care despite being "just" a point-release bump**: this
initContainer builds a **persistent glibc/gcc sysroot toolchain**
(`/paperclip/toolroot` + wrapper scripts at `/paperclip/.local/bin/{gcc,g++,ld,…}`)
on the `paperclip-data` PVC, which the long-lived `app` container later uses
via `--sysroot` to compile native Ruby/Node gems. A glibc/gcc point-patch level
change can shift symbol versions or header layout under that toolchain. This
must be verified by actually compiling something, not just checking the pod
started (§4).

**The bigger risk is operational, not the OS bump itself**: see §3 Step 2 —
the init script's idempotency is keyed on **files already present on the PVC**,
not on the image version, so a naive tag bump silently does nothing.

### 1b) `tools` container: `ubuntu:24.04` → `26.04` — RECOMMENDED: DO NOT EXECUTE

This leg is **not an open question**. It is a live operator decision already
on record:

> **Security driver — detail withheld from this public repo.**
> Tracked as **F-ae420ae8** (`version` / severity `accepted`, re-fires every
> sweep, suppressed by **AR-101**, accepted 2026-08-19). Its predecessor
> **F-afa93406** (same title, `status: resolved`) records the decision: the
> bump was tried once (commit `e9b70b73`), **reverted**, and re-pinned to
> 24.04 deliberately — the 26.04 base image measured a **worse** security
> posture than 24.04 at the time. 24.04 is LTS with standard support to 2029;
> there was no security or lifecycle argument for moving, only "a newer tag
> exists," which the finding record explicitly calls a currency signal, not a
> risk signal. Re-evaluation triggers recorded on the finding: (a) ubuntu
> 26.04's base image measures better, or (b) 24.04 approaches its 2029 EOL.
> Neither has occurred.
>
> - Dashboard: `https://sweep.<DOMAIN>/findings/F-ae420ae8` (and `F-afa93406`)
> - CLI: `runbooks/policy-cli.py finding show F-ae420ae8`
>
> See `docs/sops/vulnerability-disclosure.md`.

Scope note (also on the finding): this is the `tools` **debug/build sidecar**
(`build-essential`, `curl`, `git`, `vim`, `runAsUser: 0`, `exec sleep infinity`
— a manual `kubectl exec` shell, no ingress, not on the app's request path).
It is genuinely low blast-radius *if* it were bumped, which is exactly why the
5-months-later re-ask keeps surfacing: low stakes make it tempting to just
clear the finding. That is precisely the judgement call this plan should not
paper over.

**Per the planning rules: if investigation shows the right answer is an
operator decision rather than a window action, say so instead of writing steps
that execute it anyway.** This plan does not include execution steps for the
ubuntu leg. §3 Step 0 for this leg is a **gate**, not a bump: re-run the same
trivy comparison recorded on F-afa93406 against the *current* `ubuntu:26.04`
digest. Only if that gate now shows 26.04 at parity-or-better than 24.04 does
this become a normal low-risk sidecar bump — and even then, that is a fresh
decision for the operator/window-agent to make explicitly (update AR-101's
justification or lapse it), not something this plan pre-authorizes. **Default
action for the window: SKIP this leg, leave the pin as-is.**

## 2) Pre-checks

Run for both legs before touching anything:

```bash
cd /Users/mu/code/cberg-home-nextgen
mise exec -- flux get helmrelease -n ai paperclip           # Ready=True, no in-flight reconcile
mise exec -- kubectl get pods -n ai -l app.kubernetes.io/name=paperclip
mise exec -- kubectl get pvc -n ai paperclip-data            # Bound, note current usage: `kubectl exec` df -h /paperclip
mise exec -- kubectl get deploy -n ai paperclip-postgresql   # confirm it's on the version this plan's `current:` assumes
                                                              # (paperclip-postgresql-18.6 plan may have already landed —
                                                              # if so, re-check §6 ordering before proceeding)
```

**Debian leg only** — confirm the PVC actually holds a stale toolroot before
planning to clear it (if it doesn't, e.g. first boot after a PVC recreate,
Step 2 in §3 is a no-op and can be skipped):

```bash
mise exec -- kubectl exec -n ai deploy/paperclip -c app -- \
  sh -c 'ls -la /paperclip/.local/bin/gcc /paperclip/toolroot 2>&1 | head -5'
```

**Ubuntu leg gate** (run regardless of whether you intend to act on it — this
is the re-evaluation trigger check, not a plan step):

```bash
# Requires trivy locally. Compare current 24.04 pin vs current 26.04 digest,
# same scanner/DB, back to back — mirrors the method already used on F-afa93406.
trivy image --quiet --scanners vuln --severity CRITICAL,HIGH --ignore-unfixed -f json -o /tmp/ubuntu-2404.json \
  ubuntu:24.04@sha256:d78ab76437b1afc5f01e223d6bf0172763f404bb166441328845adbef44518cb
trivy image --quiet --scanners vuln --severity CRITICAL,HIGH --ignore-unfixed -f json -o /tmp/ubuntu-2604.json \
  ubuntu:26.04
python3 -c "
import json
for f in ('/tmp/ubuntu-2404.json','/tmp/ubuntu-2604.json'):
    d=json.load(open(f)); n=sum(len(r.get('Vulnerabilities') or []) for r in d.get('Results',[]))
    print(f, 'findings:', n)
"
```
If 26.04's count is still materially worse than 24.04's, **stop here** — do
not proceed with the ubuntu leg, and report the gate result (not the counts,
per the disclosure rule) back to AR-101 so its next review has fresh data.

## 3) Steps

### Debian leg (`mise-install`) — execute

1. Edit `kubernetes/apps/ai/paperclip/app/helmrelease.yaml`, `mise-install`
   initContainer image:
   ```yaml
   image:
     repository: debian
     tag: 13.6-slim@sha256:<digest of 13.6-slim AT EXECUTION TIME>  # re-resolve; don't reuse the digest quoted in §1a — it will have moved by the window date
   ```
   Re-resolve the digest at execution time (`curl -s
   "https://hub.docker.com/v2/repositories/library/debian/tags/13.6-slim" | python3 -c
   "import sys,json;print(json.load(sys.stdin)['digest'])"`) and pin the
   multi-arch index digest, not a per-platform manifest digest. Update the
   trailing comment to record the new pin date, replacing the stale
   "2026-08-18" note.

2. **Clear the persisted toolchain cache so the bump actually takes effect.**
   This is the step the idempotent init script cannot do for itself — it only
   rebuilds when these files are *absent*:
   ```bash
   mise exec -- kubectl exec -n ai deploy/paperclip -c app -- \
     rm -rf /paperclip/toolroot /paperclip/toolchain.log \
            /paperclip/.local/bin/gcc /paperclip/.local/bin/cc \
            /paperclip/.local/bin/g++ /paperclip/.local/bin/c++ \
            /paperclip/.local/bin/make /paperclip/.local/bin/ld \
            /paperclip/.local/bin/ld.bfd /paperclip/.local/bin/as \
            /paperclip/.local/bin/ar /paperclip/.local/bin/nm \
            /paperclip/.local/bin/strip /paperclip/.local/bin/objdump
   ```
   Leave `mise`, `zsh`, `oh-my-zsh`, `gh`, `unifictl` in place — their own
   `NEED_APT` gate is unrelated to the base-image ABI question this plan is
   about, and re-installing them adds run time and risk for no verification
   benefit. If a future plan wants those refreshed too, do it as its own step
   with its own verification.

3. Commit and push:
   ```bash
   git add kubernetes/apps/ai/paperclip/app/helmrelease.yaml
   git commit --only kubernetes/apps/ai/paperclip/app/helmrelease.yaml -m "chore(paperclip): debian mise-install trixie-slim -> 13.6-slim (13.4-era -> 13.6, same major)"
   git push
   ```

4. Reconcile and force a pod restart so the initContainer re-runs against the
   cleared cache:
   ```bash
   mise exec -- flux reconcile kustomization paperclip -n ai --with-source
   mise exec -- kubectl rollout restart deployment/paperclip -n ai
   mise exec -- kubectl get pods -n ai -l app.kubernetes.io/name=paperclip -w
   ```

### Ubuntu leg (`tools`) — do not execute by default

No steps. If the §2 gate result changes the operator's call, that is a new
plan (or an explicit re-scope of this one with `security_ref` updated and
AR-101 revisited) — not a silent extension of this plan's approved scope.

## 4) Verification

Floor: `flux get helmrelease -n ai paperclip` → `Ready=True`; `paperclip` pod
`1/1`, 0 unexpected restarts; `mise-install` initContainer `Completed`.

**CONTENTS ASSERTION (debian leg): the toolroot was actually rebuilt against
the new image, and native gem compilation still works end-to-end** — a green
pod proves the OS pulled, not that the toolchain functions:

```bash
# a) prove the rebuild happened against the NEW image, not stale cache
mise exec -- kubectl logs -n ai deploy/paperclip -c mise-install --tail=200 | grep -E 'Building sysroot|gcc wrapper ->|ld wrapper ->|Sysroot ready'
# expect the full build sequence, NOT "Build toolchain already present, skipping"

mise exec -- kubectl exec -n ai deploy/paperclip -c app -- \
  sh -c 'cat /paperclip/toolchain.log 2>/dev/null | tail -20; /paperclip/.local/bin/gcc --version'
# gcc version banner must be present, and toolchain.log must be freshly timestamped (this run, not weeks old)

# b) compile something real through the sysroot wrapper — the actual failure mode
# to catch is "gcc exists but native extension linking is broken against this glibc"
mise exec -- kubectl exec -n ai deploy/paperclip -c app -- \
  sh -c 'export PATH=/paperclip/.local/bin:$PATH; printf "int main(){return 0;}" > /tmp/t.c && gcc -o /tmp/t /tmp/t.c && /tmp/t && echo COMPILE_AND_RUN_OK'
# then exercise the real path if paperclip's runtime supports it, e.g. a gem install
# that needs native compilation (mkmf/extconf.rb) — check paperclip logs after the
# app has had a chance to install/update its own dependencies post-restart:
mise exec -- kubectl logs -n ai deploy/paperclip -c app --tail=100 | grep -iE 'gyp|extconf|native extension|error' || echo "no native-build errors in recent app log"
```

`COMPILE_AND_RUN_OK` with no linker/glibc errors is the actual proof this
bump is safe; a healthy pod alone is a shape check that would pass even if
the rebuilt toolchain silently produces broken binaries.

## 5) Rollback

Debian leg:
```bash
git revert <the debian-bump commit>
git push
mise exec -- flux reconcile kustomization paperclip -n ai --with-source
```
The reverted manifest re-pins the old digest, but **the stale-cache trap cuts
both ways**: if you cleared the toolroot in Step 2 and the revert lands, the
NEXT pod start will rebuild the toolroot fresh from the OLD (13.4-era) debian
image — this is expected and fine, just don't assume "revert = instant
restore," budget the same ~2-3 min rebuild time. Confirm via the same §4
commands (rebuild log shows the OLD digest's package versions, `gcc --version`
succeeds).

Ubuntu leg: not executed, nothing to roll back.

## 6) Interference notes

- **No shared infra perturbed.** No ingress, cert-manager, CNI, CoreDNS, or
  shared-DB touched by either leg. Safe to co-schedule with unrelated plans
  from a shared-infra standpoint.
- **Do not co-schedule with the parallel `paperclip-postgresql` (17→18) plan
  in the same window without sequencing.** Both plans restart pods in the `ai`
  namespace that the `paperclip` controller's `wait-for-postgres` initContainer
  depends on (`nc -z paperclip-postgresql 5432`), and `backup-cleanup.yaml`'s
  CronJob uses `podAffinity` to co-schedule onto the same node as `paperclip`
  — a concurrent postgres cutover plus a paperclip pod restart on the same
  node/window makes failure attribution ambiguous (was it the toolchain
  rebuild or the DB cutover that broke something?). If both are scheduled in
  the same window, **run this plan's debian leg first and independently
  verified (§4) before starting the postgres cutover**, so a failure in either
  is unambiguous. Confirm the actual `plan_id` for the postgres plan at
  vetting time — this file guesses `paperclip-postgresql-18.6` in
  `conflicts_with` but that plan is being authored separately.
- **The ubuntu leg is deliberately inert in this plan.** If a future window
  agent run is tempted to "just do it since it's a plan file sitting here" —
  don't. §1b's gate must be re-run and show a materially different result
  first, and even then the accepted-risk AR-101 needs an explicit operator
  update, not an automatic supersede by this plan landing.
- `maxHistory: 1` and default `upgrade.remediation.retries: 1` are `paperclip`'s
  standing HelmRelease settings — a bad rollout auto-retries once then reports
  failed; there is no multi-revision `helm rollback` available, so recovery is
  via git-revert (§5), not `helm rollback`.

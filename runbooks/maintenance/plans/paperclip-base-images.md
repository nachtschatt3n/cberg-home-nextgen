---
plan_id: paperclip-base-images
component: paperclip
pr: null                              # digest-pinned base images; no Renovate PR (float-tag policy)
kind: image
current: "mise-install initContainer: debian trixie-slim@sha256:26f98ccd… (built 2026-03-16, ~Debian 13.4-era) | tools container: ubuntu 24.04@sha256:d78ab76…"
target: "mise-install initContainer ONLY: debian 13.7-slim@sha256:a99cfc517144bc59b1978475ec53b46ecabec7e43635402ee5b77cc54cd1b20a. tools container (ubuntu): OUT OF SCOPE, stays on 24.04 under AR-101, see §1b"
update_type: minor                    # debian-only scope (2026-09-26 operator re-scope): intra-major 13.4-era -> 13.7 refresh, see §1a. The ubuntu 26.04 leg (the only major) is excluded.
risk: medium                          # persisted toolchain rebuild, ABI risk
est_duration_min: 40
needs_reboot: false
touches:
  namespaces: [ai]
  resources:
    - helmrelease/paperclip
    - pvc/paperclip-data                          # /paperclip — persists mise-install's built toolroot
    - initcontainer/mise-install (debian leg — the ONLY leg in scope)
  shared: []                                       # no ingress/cert-manager/cilium/coredns/shared-DB perturbed;
                                                    # paperclip-postgresql is a SEPARATE Deployment (see conflicts_with)
depends_on: []
conflicts_with: []   # 2026-09-26: paperclip-chart-5.2.1 EXECUTED and retired first (same HelmRelease + pod); ref resolved
                                                    # paperclip-postgresql-18.6 was the old placeholder: it EXECUTED
                                                    # 2026-09-07 (status: executed), so that conflict is moot and removed.
autonomy_override: human-gated  # ADDED 2026-09-06. The target field itself
                                # reads "RECOMMENDED: DO NOT EXECUTE, see 1b",
                                # yet this derived AUTO-NIGHT -- auto-schedulable
                                # the moment anyone vetted it. The refusal now
                                # lives in the field the derivation reads.
status: vetted   # 2026-09-26 plan-reviewer needs-fix -> 24 edits applied verbatim (debian-only scope, ubuntu leg excluded, 6 premises, gates that can fail, real rollback); order: after paperclip-chart-5.2.1
window: "now:2026-09-26"   # ON-DEMAND NOW run 2026-09-26 (run-now.py stamp; was None)
# auto_execute RETIRED 2026-08-26 (P2.1b) — execution class is derived from
# capability_change/rollback_class per runbooks/autonomy-policy.yaml.
security_ref: F-ae420ae8              # live accepted-risk finding for the ubuntu leg (AR-101); F-afa93406 is its
                                       # resolved predecessor recording the original hold decision. Detail DB-only.
capability_change: false              # no user-visible behaviour change on either leg
rollback_class: git-revert
finding_refs: []                      # no open version finding for the debian leg (checked 2026-09-26, `finding list --grep paperclip`).
                                      # The accepted debian:trixie-slim image rows (AR-029) are re-evaluated by the next security sweep after the re-pin.
premises:
  - id: init-pin-is-still-the-trixie-digest
    why: >-
      The debian leg replaces exactly this pin. If the rendered Deployment's
      mise-install image is already something else, someone has been here
      before and Step 1's edit and the rollback target are wrong.
    run: kubectl get deploy -n ai paperclip -o jsonpath='{.spec.template.spec.initContainers[?(@.name=="mise-install")].image}'
    expect_exact: "debian:trixie-slim@sha256:26f98ccd92fd0a44d6928ce8ff8f4921b4d2f535bfa07555ee5d18f61429cf0c"
  - id: running-pod-ran-the-trixie-digest
    why: >-
      Baseline for the §4 image-identity gate: the live init imageID is the
      OLD index digest, so reading the NEW digest afterwards is a real
      transition, not a reading that was always true.
    run: kubectl get pods -n ai -l app.kubernetes.io/name=paperclip -o jsonpath='{.items[*].status.initContainerStatuses[?(@.name=="mise-install")].imageID}'
    expect_exact: "docker.io/library/debian@sha256:26f98ccd92fd0a44d6928ce8ff8f4921b4d2f535bfa07555ee5d18f61429cf0c"
  - id: toolchain-cache-present-and-skipped
    why: >-
      Step 2 exists because the init script skips the sysroot build while
      /paperclip/.local/bin/gcc exists. This is also the known-bad baseline
      for the §4 rebuild gate: the grep that must find "Sysroot ready" after
      the change finds only the skip line today.
    run: kubectl logs -n ai deploy/paperclip -c mise-install --tail=200 | grep -c 'Build toolchain already present, skipping'
    expect_exact: "1"
  - id: ubuntu-tools-leg-untouched
    why: >-
      The ubuntu leg is OUT OF SCOPE (AR-101). The tools container must be on
      the 24.04 pin before (and after) this plan; if it is not, stop.
    run: kubectl get deploy -n ai paperclip -o jsonpath='{.spec.template.spec.containers[?(@.name=="tools")].image}'
    expect_exact: "ubuntu:24.04@sha256:d78ab76437b1afc5f01e223d6bf0172763f404bb166441328845adbef44518cb"
  - id: paperclip-healthy
    why: >-
      Do not start a toolchain rebuild on a pod that is already unhealthy; a
      failure afterwards would be unattributable. Two containers: app + tools.
    run: kubectl get pods -n ai -l app.kubernetes.io/name=paperclip -o jsonpath='{.items[*].status.containerStatuses[*].ready}'
    expect_exact: "true true"
  - id: helmrelease-ready
    why: >-
      No in-flight or failed upgrade to stack this change on (maxHistory 1,
      no helm rollback available).
    run: kubectl get helmrelease -n ai paperclip -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: "True"
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/vulnerability-disclosure.md
generated: "2026-09-05"
retargeted: "2026-09-25"                # debian leg 13.6-slim -> 13.7-slim (13.7 released 2026-09-12); DO-NOT-EXECUTE on the ubuntu leg re-confirmed
---

# paperclip: debian base-image bump for mise-install (ubuntu tools leg EXCLUDED)

> **SCOPE (operator, 2026-09-26): execute the DEBIAN `mise-install` leg ONLY.**
> The ubuntu `tools` leg is NOT part of this plan's executable scope: no step,
> gate or rollback below edits the `tools` image. An executor that finds itself
> editing `repository: ubuntu` / `24.04@sha256:d78ab764...` is off-plan: STOP.

## 1) Summary & why held

Both images live in `kubernetes/apps/ai/paperclip/app/helmrelease.yaml`, in two
unrelated containers of the `paperclip` controller. They were bundled into one
sweep item because they're both digest-pinned base-image bumps on the same
component, but **they are different questions with different answers.**

### 1a) `mise-install` initContainer: `debian:trixie-slim` → `13.7-slim`

**This is NOT a codename→number no-op rename, despite trixie being Debian 13
both before and after.** Verified against the registry, not assumed from the
tag string:

- The **currently pinned** digest
  (`sha256:26f98ccd92fd0a44d6928ce8ff8f4921b4d2f535bfa07555ee5d18f61429cf0c`)
  decodes to an image built `2026-03-16T00:00:00Z` (OCI `created` annotation,
  debuerreotype build). That build date lands two days after **Debian 13.4**
  released (2026-03-14) — i.e. the container running today is effectively a
  13.4-era `trixie-slim` snapshot, not 13.7.
- **Re-targeted 2026-09-25 (13.6 → 13.7).** Debian 13.7 released 2026-09-12
  (debian.org/News/2026/20260912). Docker Hub, checked 2026-09-25: the
  **`13.7-slim`** tag resolves to index digest `sha256:a99cfc51…`
  (`last_updated: 2026-09-19`), **byte-identical** to the floating
  `trixie-slim` tag — i.e. 13.7 IS the current stable trixie build, not a
  pre-release. `13.8-slim` → 404. The old target `13.6-slim` (`sha256:d7e12182…`,
  2026-08-25) is now superseded and must not be used.
- **13.7 notes relevant to this container:** a **glibc update** (packages
  rebuilt against it), a new upstream OpenSSL release, kernel ABI bump to
  6.12.107 (irrelevant here — containers use the node's Talos kernel). No
  gcc/binutils/apt changes and no package removals called out. The glibc
  update is the one that matters: it is exactly the component the persisted
  sysroot toolchain (below) is built from, so the §4 compile-and-run gate is
  load-bearing, not ceremonial. It does not change the risk class (still an
  intra-major point-release refresh, `risk: medium`).
- **Conclusion: this is a real intra-major refresh, ~13.4 → 13.7**, carrying
  three Debian point releases (13.5, 13.6, 13.7) of stable-update package
  patches — glibc, gcc, openssl, binutils, coreutils, apt — NOT a distro
  major bump (still Debian 13) and NOT a no-op digest-only republish. The
  auto-updater's "unknown" classification is a **codename-vs-number string
  comparison blind spot** (it cannot semantically diff `trixie-slim` against
  `13.7-slim`), not evidence of anything more dramatic than the above.

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

### 1b) `tools` container: `ubuntu:24.04` → `26.04` — EXCLUDED FROM THIS PLAN (DO NOT EXECUTE, AR-101)

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
> Neither has occurred. **Re-confirmed 2026-09-25:** F-ae420ae8 is still
> `accepted` / last seen 2026-09-25 under AR-101 — the DO-NOT-EXECUTE on this
> leg stands unchanged by the debian re-target.
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

Run before touching anything (debian leg only; the ubuntu leg is excluded):

```bash
cd /Users/mu/code/cberg-home-nextgen
mise exec -- flux get helmrelease -n ai paperclip           # Ready=True, no in-flight reconcile
mise exec -- kubectl get pods -n ai -l app.kubernetes.io/name=paperclip
mise exec -- kubectl get pvc -n ai paperclip-data            # Bound, note current usage: `kubectl exec` df -h /paperclip
.venv/bin/python3 runbooks/plan-premises.py paperclip-base-images --require-premises   # every premise PASS, else STOP
```

**Debian leg only** — confirm the PVC actually holds a stale toolroot before
planning to clear it (if it doesn't, e.g. first boot after a PVC recreate,
Step 2 in §3 is a no-op and can be skipped):

```bash
mise exec -- kubectl exec -n ai deploy/paperclip -c app -- \
  sh -c 'ls -la /paperclip/.local/bin/gcc /paperclip/toolroot 2>&1 | head -5'
```

**Ubuntu leg gate — NOT RUN in this plan's execution (reference only).** The
re-evaluation belongs to AR-101's own review, not to this window. Do not run
the block below as part of executing this plan:

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
   First confirm the tag still resolves to the reviewed index digest (a
   different value = upstream re-pushed 13.7-slim: STOP and re-review, do not
   pin an unreviewed digest):
   ```bash
   curl -s "https://hub.docker.com/v2/repositories/library/debian/tags/13.7-slim" | python3 -c "import sys,json;d=json.load(sys.stdin)['digest'];print(d);print('DIGEST_MATCH' if d=='sha256:a99cfc517144bc59b1978475ec53b46ecabec7e43635402ee5b77cc54cd1b20a' else 'DIGEST_MOVED_STOP')"
   ```
   Then apply the edit (BSD-safe, asserts exactly one match, touches ONLY the
   mise-install line; the ubuntu `tools` pin is not in the replaced text).
   The block is deliberately NOT indented: copy it as-is (a heredoc terminator
   and Python both break on leading spaces):

```bash
cd /Users/mu/code/cberg-home-nextgen && python3 - <<'EOF'
p="kubernetes/apps/ai/paperclip/app/helmrelease.yaml"; s=open(p).read()
old="tag: trixie-slim@sha256:26f98ccd92fd0a44d6928ce8ff8f4921b4d2f535bfa07555ee5d18f61429cf0c  # digest-pinned to the RUNNING image 2026-08-18 (float-tag policy); re-pin deliberately"
new="tag: 13.7-slim@sha256:a99cfc517144bc59b1978475ec53b46ecabec7e43635402ee5b77cc54cd1b20a  # digest-pinned 2026-09-26 to the Debian 13.7-slim index digest (float-tag policy); re-pin deliberately"
n=s.count(old); assert n==1, f"old text found {n}x - STOP"
open(p,"w").write(s.replace(old,new)); print("EDITED")
EOF
git -C /Users/mu/code/cberg-home-nextgen diff --numstat kubernetes/apps/ai/paperclip/app/helmrelease.yaml   # PASS: "1  1  kubernetes/apps/ai/paperclip/app/helmrelease.yaml"
```

2. **Clear the persisted toolchain cache so the bump actually takes effect.**
   This is the step the idempotent init script cannot do for itself — it only
   rebuilds when these files are *absent*:
   Run it in the `tools` container (`runAsUser: 0`, same `/paperclip` mount):
   the `app` container runs as uid 1000 (`node`) and the toolroot was written
   by the root init container. Do this IMMEDIATELY before Step 3's push:
   ```bash
   mise exec -- kubectl exec -n ai deploy/paperclip -c tools -- \
     rm -rf /paperclip/toolroot /paperclip/toolchain.log \
            /paperclip/.local/bin/gcc /paperclip/.local/bin/cc \
            /paperclip/.local/bin/g++ /paperclip/.local/bin/c++ \
            /paperclip/.local/bin/make /paperclip/.local/bin/ld \
            /paperclip/.local/bin/ld.bfd /paperclip/.local/bin/as \
            /paperclip/.local/bin/ar /paperclip/.local/bin/nm \
            /paperclip/.local/bin/strip /paperclip/.local/bin/objdump
   mise exec -- kubectl exec -n ai deploy/paperclip -c tools -- \
     sh -c 'test ! -e /paperclip/.local/bin/gcc && echo GCC_WRAPPER_CLEARED'
   # PASS: prints GCC_WRAPPER_CLEARED (the ONLY file the init script's rebuild gate keys on). Anything else: STOP.
   ```
   Leave `mise`, `zsh`, `oh-my-zsh`, `gh`, `unifictl` in place — their own
   `NEED_APT` gate is unrelated to the base-image ABI question this plan is
   about, and re-installing them adds run time and risk for no verification
   benefit. If a future plan wants those refreshed too, do it as its own step
   with its own verification.

3. Commit and push:
   ```bash
   cd /Users/mu/code/cberg-home-nextgen
   git commit --only kubernetes/apps/ai/paperclip/app/helmrelease.yaml -m "chore(paperclip): debian mise-install trixie-slim -> 13.7-slim (13.4-era -> 13.7, same major)"
   git show --stat HEAD          # exactly one file: kubernetes/apps/ai/paperclip/app/helmrelease.yaml
   git log -1 --format=%s        # must be the subject above
   git push
   ```

4. Reconcile. The init image change alters the pod template, so the helm
   upgrade itself replaces the pod (`strategy: Recreate`). Do NOT
   `kubectl rollout restart`: a second roll after the rebuild makes the final
   pod's init log read "skipping" and fails the §4 rebuild gate falsely.
   ```bash
   mise exec -- flux reconcile kustomization paperclip -n ai --with-source
   mise exec -- flux reconcile helmrelease paperclip -n ai
   mise exec -- kubectl rollout status deployment/paperclip -n ai --timeout=15m
   ```
   The toolroot rebuild runs inside the helm wait (HR `timeout` default 5m).
   If the HR reports an upgrade timeout while the pod is still `Init` running
   `mise-install`, do not intervene: let the init finish, then judge by §4.

### Ubuntu leg (`tools`) — EXCLUDED, no steps

No steps. Do not edit the `tools` image in this plan. If the §2 gate result changes the operator's call, that is a new
plan (or an explicit re-scope of this one with `security_ref` updated and
AR-101 revisited) — not a silent extension of this plan's approved scope.

## 4) Verification

Floor: `flux get helmrelease -n ai paperclip` → `Ready=True`; `paperclip` pod
`2/2` (app + tools), 0 unexpected restarts; `mise-install` initContainer `Completed`;
premise `ubuntu-tools-leg-untouched` still PASS (`.venv/bin/python3 runbooks/plan-premises.py paperclip-base-images`
— the three trixie/skip premises are EXPECTED to fail after the change; that is the transition).

**Image-identity gate (debian leg)** — prove the initContainer actually ran the
13.7 digest you pinned, not a cached old one. Fails (prints the OLD
`sha256:26f98ccd…` or an empty line) if the rollout did not pick up the pin:

```bash
mise exec -- kubectl get pods -n ai -l app.kubernetes.io/name=paperclip \
  -o jsonpath='{range .items[*]}{.status.initContainerStatuses[?(@.name=="mise-install")].imageID}{"\n"}{end}'
# PASS: prints exactly docker.io/library/debian@sha256:a99cfc517144bc59b1978475ec53b46ecabec7e43635402ee5b77cc54cd1b20a
# FAIL: prints ...26f98ccd... (the pre-change reading, measured 2026-09-26) or nothing
```

**CONTENTS ASSERTION (debian leg): the toolroot was actually rebuilt against
the new image, and native gem compilation still works end-to-end** — a green
pod proves the OS pulled, not that the toolchain functions:

```bash
# a) prove the rebuild happened against the NEW image, not stale cache
mise exec -- kubectl logs -n ai deploy/paperclip -c mise-install --tail=300 | grep -cE 'Building sysroot|gcc wrapper ->|ld wrapper ->|Sysroot ready'
# PASS: 4. FAIL: 0 is the pre-change reading (measured 2026-09-26: the log holds only
# "Build toolchain already present, skipping"); <4 = partial build ("ERROR: gcc wrapper ..." path).

mise exec -- kubectl exec -n ai deploy/paperclip -c app -- \
  sh -c 'stat -c %y /paperclip/toolchain.log; grep -cE -e "^--- (crtbeginS\.o|stdio\.h|libgcc_s\.so\.1): YES ---$" /paperclip/toolchain.log; grep -c -e "^ld-linux: OK$" /paperclip/toolchain.log; /paperclip/.local/bin/gcc --version | head -1'
# PASS: timestamp dated today; then 3; then 1; then a gcc banner. A missing piece prints "NO" in the log
# and the count drops below 3 (regex dry-tested 2026-09-26 against a log with one NO: prints 2).

# b) compile something real through the sysroot wrapper — the actual failure mode
# to catch is "gcc exists but native extension linking is broken against this glibc"
mise exec -- kubectl exec -n ai deploy/paperclip -c app -- \
  sh -c 'printf "int main(){return 0;}" > /tmp/t.c && /paperclip/.local/bin/gcc -o /tmp/t /tmp/t.c && /tmp/t && echo COMPILE_AND_RUN_OK'
# PASS: COMPILE_AND_RUN_OK. Calls the sysroot wrapper by absolute path, so a missing wrapper
# cannot fall through to some other gcc on PATH.
# INFORMATIONAL ONLY (not a PASS criterion — an absence reading, never shown to match a bad case):
mise exec -- kubectl logs -n ai deploy/paperclip -c app --tail=100 | grep -iE 'gyp|extconf|native extension|error' || echo "no native-build errors in recent app log"
```

`COMPILE_AND_RUN_OK` with no linker/glibc errors is the actual proof this
bump is safe; a healthy pod alone is a shape check that would pass even if
the rebuilt toolchain silently produces broken binaries.

## 5) Rollback

Debian leg. **The stale-cache trap cuts both ways:** if the 13.7 build
completed, `/paperclip/.local/bin/gcc` exists and a bare revert would SKIP the
rebuild, leaving the 13.7-built toolroot in place under the old pin. So clear
the wrapper again first (if the pod is not Running, the build did not finish,
the wrapper is absent, and this step is skipped):
```bash
cd /Users/mu/code/cberg-home-nextgen
mise exec -- kubectl exec -n ai deploy/paperclip -c tools -- \
  sh -c 'rm -rf /paperclip/toolroot /paperclip/.local/bin/gcc; test ! -e /paperclip/.local/bin/gcc && echo GCC_WRAPPER_CLEARED'
git revert --no-edit "$(git log -1 --format=%H --grep='debian mise-install trixie-slim -> 13.7-slim' -- kubernetes/apps/ai/paperclip/app/helmrelease.yaml)"
git show --stat HEAD && git push
mise exec -- flux reconcile kustomization paperclip -n ai --with-source
mise exec -- flux reconcile helmrelease paperclip -n ai
mise exec -- kubectl rollout status deployment/paperclip -n ai --timeout=15m
```
Confirm with the §4 commands: imageID back to `...26f98ccd...`, rebuild count 4,
COMPILE_AND_RUN_OK.

Ubuntu leg: excluded from this plan, nothing to roll back.

## 6) Interference notes

- **No shared infra perturbed.** No ingress, cert-manager, CNI, CoreDNS, or
  shared-DB touched by either leg. Safe to co-schedule with unrelated plans
  from a shared-infra standpoint.
- **`paperclip-postgresql-18.6` EXECUTED 2026-09-07 — the note below is historical.**
  **Do not co-schedule with the parallel `paperclip-postgresql` (17→18) plan
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
- **`paperclip-chart-5.2.1`** (F-44278983) edits the same HelmRelease; now in
  `conflicts_with` both ways. Serial in one on-demand run is fine (run-now
  marks the later one `settle_before`). ORDER DECIDED 2026-09-26 (coordinator):
  the chart plan runs FIRST (label-only, no roll; its premise
  `helmrelease-file-unchanged-since-review` pins the HR file and would fail if
  this plan landed first). This plan starts only after the chart plan's §4
  SAME_POD gate has passed and its close-out is pushed; this plan's premises
  read the init/tools pins and the running pod, which the chart plan does not
  change. Never let this plan's pod roll land between the chart plan's §2b
  baseline and its §4 verification.
- `maxHistory: 1` and default `upgrade.remediation.retries: 1` are `paperclip`'s
  standing HelmRelease settings — a bad rollout auto-retries once then reports
  failed; there is no multi-revision `helm rollback` available, so recovery is
  via git-revert (§5), not `helm rollback`.

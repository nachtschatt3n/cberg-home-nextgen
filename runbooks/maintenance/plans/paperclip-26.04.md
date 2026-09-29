---
plan_id: paperclip-26.04
component: paperclip                  # the `tools` SIDECAR of deploy/paperclip, not the app image
pr: null                              # no Renovate PR; coverage.py reports it from the version
                                      # snapshot (image:ubuntu, subsection helmrelease_image)
kind: image
current: "24.04@sha256:d78ab76437b1afc5f01e223d6bf0172763f404bb166441328845adbef44518cb"
target: "26.04@sha256:da6fc2be547864451aa253836dd926da33623312df4a9a243e35dc877c378a78"
update_type: major                    # Ubuntu LTS -> LTS (noble -> resolute)
risk: low                             # stock distro sidecar, no probe, no persistent writes;
                                      # the only cost is one Recreate of the paperclip pod
est_duration_min: 20
needs_reboot: false
touches:
  namespaces: [ai]
  resources:
    - helmrelease/paperclip                    # one image line in the tools container
    - deployment/paperclip                     # pod template changes -> Recreate (app down ~1-3 min)
    - pvc/paperclip-data                       # detached/re-attached by the Recreate; not written by this change
  shared: []                                   # no gateway/envoy change (HTTPRoute untouched), no
                                               # shared DB (paperclip-postgresql is not restarted), no
                                               # storage-engine change. Falco/Wazuh suppression 100413
                                               # keys on repository docker.io/library/ubuntu, which
                                               # does not change.
depends_on: []
conflicts_with:                       # none of these name a paperclip image, but each either
                                      # re-renders every HelmRelease incl. helmrelease/paperclip or
                                      # snapshots workloads incl. deploy/paperclip; a same-night
                                      # paperclip roll would make their gates unattributable.
  - app-template-5.2.1                # --compare-workloads baseline counts deploy/paperclip
  - helm-drift-detection              # adds spec.driftDetection to every HR incl. paperclip
  - flux-oci-chart-sources            # may rewrite paperclip's chart source (bjw-s app-template)
  - flux-reconciler-impersonation     # exclusive; changes the identity that applies ai/
exclusive: false
security_ref: null                    # driver is currency. The HOLD this plan lifts was a
                                      # posture decision recorded on F-afa93406 (cited in §1);
                                      # no security finding drives the bump.
capability_change: false              # same sidecar role (root shell with a build toolchain);
                                      # toolchain minor versions move with the distro, no new
                                      # route, permission, API or exposure
rollback_class: git-revert            # nothing forward-only: the sidecar apt-installs into its
                                      # ephemeral rootfs and writes nothing under /paperclip
finding_refs: [F-ae420ae8]            # the open version finding (accepted under AR-101)
premises:
  - id: tools-still-on-24.04-pin
    why: >-
      current: and the §4 baselines (VERSION_ID 24.04, gcc 13.3, libpq 16) were
      measured against this exact digest. If the sidecar already moved, the plan
      is stale.
    run: kubectl get deploy -n ai paperclip -o jsonpath='{.spec.template.spec.containers[?(@.name=="tools")].image}'
    expect_exact: "ubuntu:24.04@sha256:d78ab76437b1afc5f01e223d6bf0172763f404bb166441328845adbef44518cb"
  - id: repo-pin-is-24.04
    why: "Step 3.1's python edit anchors on this exact line; zero or two matches means the file moved under the plan."
    run: >-
      grep -c '^[[:space:]]*tag: "24\.04@sha256:d78ab76437b1afc5f01e223d6bf0172763f404bb166441328845adbef44518cb"$' kubernetes/apps/ai/paperclip/app/helmrelease.yaml
    expect_exact: "1"
  - id: hr-ready
    why: "A HelmRelease already failing would mask whether the bump itself reconciled."
    run: kubectl get helmrelease -n ai paperclip -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: "True"
  - id: strategy-recreate
    why: >-
      Single replica on an RWO Longhorn PVC (paperclip-data): a RollingUpdate
      could block on Multi-Attach (docs/sops/longhorn-rwo-multi-attach.md).
      Live value 2026-09-29 is Recreate.
    run: kubectl get deploy -n ai paperclip -o jsonpath='{.spec.strategy.type}'
    expect_exact: Recreate
  - id: data-volume-healthy
    why: "The Recreate detaches and re-attaches paperclip-data; it must be healthy before we bounce it."
    run: kubectl get volumes.longhorn.io -n storage pvc-cdbd0a10-fa71-43f7-a442-00b4d7f99808 -o jsonpath='{.status.state}/{.status.robustness}'
    expect_exact: attached/healthy
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/longhorn-rwo-multi-attach.md
  - docs/sops/vulnerability-disclosure.md
review: null
status: draft
window: null
generated: "2026-09-29"
---

# paperclip `tools` sidecar: ubuntu 24.04 -> 26.04 LTS

## 1. Summary & why held

**What this really is.** The only `ubuntu` reference under
`kubernetes/apps/ai/paperclip` is `controllers.paperclip.containers.tools.image`
in `app/helmrelease.yaml` — a stock `docker.io/library/ubuntu` **sidecar** next to
the paperclip app. It is not the app image (`reeoss/paperclipai-paperclip`), not
an init container (those are `busybox` and `debian:13.7-slim`), and not a base
layer of anything we build (`docs/sops/self-built-image-rebuild.md` records that
paperclip owns no self-built image). So this is NOT rebuild-lane work: it is a
plain one-line image bump.

What the sidecar does (entire command, runs as uid 0):

```
apt-get update -qq
apt-get install -y -qq build-essential curl git wget vim nano less \
  libssl-dev libreadline-dev zlib1g-dev libpq-dev libsqlite3-dev
exec sleep infinity
```

No probe, no ports, nothing written to the shared `/paperclip` PVC (apt writes
to the container's own rootfs). It exists to give an operator/agent `kubectl
exec` a root shell with a build toolchain.

**Why held.** `coverage.py`: *major — needs an assessed window plan.* The
version finding (`F-ae420ae8`) is currently suppressed by **AR-101**, because
on 2026-08-19 the sidecar was bumped to 26.04 (`e9b70b73`) and then reverted to
24.04 (`d49c3175`): the 26.04 base had a **worse measured scanner posture** than
24.04 at the time. That decision, its numbers and its re-evaluation triggers are
on finding **F-afa93406** (detail stays in the DB). Trigger (a) was "the 26.04
base drops back to 0 HIGH".

**Trigger (a) is now met — measured 2026-09-29** with trivy 0.70.0,
`--platform linux/amd64 --severity HIGH,CRITICAL`:

| image | result |
|---|---|
| `ubuntu@sha256:da6fc2be…c378a78` (26.04 = `resolute-20260912`, the target pin) | **0 HIGH / 0 CRITICAL** |
| negative control: the 2026-08 26.04 digest `6df9e8dd…` that caused the hold | non-zero HIGH (reproduces F-afa93406's measurement, so the scanner is not blind) |

26.04 is GA (Resolute Raccoon, April 2026; Docker Hub `26.04` → OCI index
`sha256:da6fc2be547864451aa253836dd926da33623312df4a9a243e35dc877c378a78`,
amd64 manifest present). Pinned by that index digest.

**LTS -> LTS breakage assessment for this script:**

- **Package names** — every package the script installs exists in `resolute`
  (checked against `archive.ubuntu.com/ubuntu/dists/resolute/{main,universe}`
  Packages index): build-essential 12.12ubuntu2, curl 8.18.0, git 2.53.0,
  wget 1.25.0, vim 9.1, nano 8.7.1, less 668, libssl-dev 3.5.5,
  libreadline-dev 8.3, zlib1g-dev 1.3.1, libpq-dev 18.3, libsqlite3-dev 3.46.1.
  No rename. Note: the script has **no `set -e`** — if apt failed, the container
  would still reach `sleep infinity` and look healthy with no toolchain. §4 G3
  exists for exactly that.
- **coreutils** — 26.04 ships `rust-coreutils` (uutils 0.8.0) as default
  coreutils. The script's only coreutils call is `sleep infinity`; uutils 0.8.0
  `parse_time::from_str` maps `inf`/`infinity` to `Duration::MAX` (upstream unit
  test `test_infinity`, `src/uucore/src/lib/features/parser/parse_time.rs`). If
  it did not, PID 1 would exit and the container would crash-loop — G2 catches it.
- **Toolchain versions move** (gcc 13 -> 15, libpq 16 -> 18, glibc 2.39 -> 2.43).
  Nothing in paperclip consumes the sidecar's libraries; the app container
  and the `/paperclip/toolroot` sysroot (built by the Debian `mise-install`
  init container) are untouched by this change.
- **Security tooling** — Falco/Wazuh rule 100413 suppresses the sidecar's
  apt/dpkg postinst noise by matching `container_image_repository=docker.io/library/ubuntu`;
  the repository is unchanged, so no new alert flood.

Verdict: the hold was correct when made and its own lapse condition is now true.
Genuinely low risk; the only user-visible effect is a 1-3 min paperclip outage
from the Recreate (in-flight agent runs are interrupted).

## 2. Pre-checks

```bash
cd /Users/mu/code/cberg-home-nextgen
.venv/bin/python3 runbooks/plan-premises.py paperclip-26.04        # all premises must PASS

# 2.1 Re-scan the TARGET pin now — the whole reason for the hold. ABORT on non-zero.
T=$(mise which trivy)
$T image --quiet --platform linux/amd64 --severity HIGH,CRITICAL --format json \
  ubuntu@sha256:da6fc2be547864451aa253836dd926da33623312df4a9a243e35dc877c378a78 \
  | python3 -c "import sys,json;d=json.load(sys.stdin);n=sum(len(r.get('Vulnerabilities') or []) for r in d.get('Results',[]));print('TARGET_HIGH_CRIT', n);sys.exit(1 if n else 0)"
# PASS: "TARGET_HIGH_CRIT 0", exit 0. FAIL: non-zero -> STOP, do not bump; the
# F-afa93406 condition no longer holds. (Docker Hub anonymous pull limits can make
# trivy error out — an error is NOT a pass; retry later or authenticate.)

# 2.2 Negative control — proves 2.1 can fail. Must print a NON-zero count.
$T image --quiet --platform linux/amd64 --severity HIGH,CRITICAL --format json \
  ubuntu@sha256:6df9e8dd1eac389ebfef692c9648449adeb815d01e16e29cd6f3e50fe64ba9a6 \
  | python3 -c "import sys,json;d=json.load(sys.stdin);print('NEG_CONTROL', sum(len(r.get('Vulnerabilities') or []) for r in d.get('Results',[])))"
# PASS: NEG_CONTROL >= 1. If it prints 0, the scanner DB is empty/blind -> 2.1 is meaningless, STOP.

# 2.3 App baseline (also the §4 G4 comparison)
kubectl -n ai get pod -l app.kubernetes.io/name=paperclip \
  -o custom-columns='NAME:.metadata.name,READY:.status.containerStatuses[*].ready,RESTARTS:.status.containerStatuses[*].restartCount'
kubectl -n ai port-forward svc/paperclip 13100:3100 >/dev/null 2>&1 & PF=$!; sleep 3
curl -s http://localhost:13100/api/health; echo; kill $PF 2>/dev/null
# expect {"status":"ok",...,"authReady":true,"bootstrapStatus":"ready",...}  (measured 2026-09-29)

# 2.4 No in-flight reconcile on the app
flux get kustomization -n ai paperclip; flux get helmrelease -n ai paperclip
```

## 3. Steps (GitOps)

3.1 Edit the pin (dry-tested on a scratch copy 2026-09-29 — anchors on exactly
one block and aborts otherwise):

```bash
cd /Users/mu/code/cberg-home-nextgen && python3 - <<'EOF'
p = "kubernetes/apps/ai/paperclip/app/helmrelease.yaml"
s = open(p).read()
old = (
    "              # digest-pinned (float-tag policy). HELD on 24.04 LTS deliberately;\n"
    "              # rationale + re-evaluation triggers live on the finding record.\n"
    "              # security_ref: F-afa93406\n"
    '              tag: "24.04@sha256:d78ab76437b1afc5f01e223d6bf0172763f404bb166441328845adbef44518cb"\n'
)
new = (
    "              # digest-pinned (float-tag policy). 24.04 -> 26.04 LTS once the 26.04\n"
    "              # base met the re-evaluation trigger recorded on the finding record.\n"
    "              # security_ref: F-afa93406  (plan paperclip-26.04)\n"
    '              tag: "26.04@sha256:da6fc2be547864451aa253836dd926da33623312df4a9a243e35dc877c378a78"\n'
)
n = s.count(old)
assert n == 1, f"expected exactly 1 anchor, found {n}"
open(p, "w").write(s.replace(old, new))
print("EDIT_OK")
EOF
git diff --stat kubernetes/apps/ai/paperclip/app/helmrelease.yaml   # expect 1 file, 4+/4-
```

Resulting diff (from the dry run):

```
-              # digest-pinned (float-tag policy). HELD on 24.04 LTS deliberately;
-              # rationale + re-evaluation triggers live on the finding record.
-              # security_ref: F-afa93406
-              tag: "24.04@sha256:d78ab76437b1afc5f01e223d6bf0172763f404bb166441328845adbef44518cb"
+              # digest-pinned (float-tag policy). 24.04 -> 26.04 LTS once the 26.04
+              # base met the re-evaluation trigger recorded on the finding record.
+              # security_ref: F-afa93406  (plan paperclip-26.04)
+              tag: "26.04@sha256:da6fc2be547864451aa253836dd926da33623312df4a9a243e35dc877c378a78"
```

3.2 Validate and commit (shared worktree rules):

```bash
kubeconform -summary -ignore-missing-schemas kubernetes/apps/ai/paperclip
cat > /tmp/paperclip-26.04.msg <<'EOF'
chore(paperclip): tools sidecar ubuntu 24.04 -> 26.04 LTS, digest-pinned

Plan paperclip-26.04. Lifts the 2026-08-19 hold: its recorded re-evaluation
trigger is met (detail on the finding record).

security_ref: F-afa93406
EOF
git commit --only kubernetes/apps/ai/paperclip/app/helmrelease.yaml -F /tmp/paperclip-26.04.msg
git log -1 --format=%s     # must be the subject above; amend before push if not
git show --stat HEAD       # exactly one file
git push
```

3.3 Let the Flux webhook reconcile (no manual `flux reconcile`). Wait for the
HelmRelease to report the new revision:

```bash
for i in $(seq 1 30); do
  IMG=$(kubectl get deploy -n ai paperclip -o jsonpath='{.spec.template.spec.containers[?(@.name=="tools")].image}')
  case "$IMG" in *da6fc2be547864451aa253836dd926da33623312df4a9a243e35dc877c378a78) echo "TEMPLATE_UPDATED"; break;; esac
  sleep 20
done
```

## 4. Verification

The sidecar has no readiness probe, so pod `2/2 Ready` goes green **before** apt
has run. Every gate below reads the running process or the installed package
set, not pod shape.

```bash
P=$(kubectl -n ai get pod -l app.kubernetes.io/name=paperclip -o jsonpath='{.items[0].metadata.name}'); echo "$P"
```

**G1 — the running container is the new digest (not the old generation).**
```bash
kubectl -n ai get pod "$P" -o jsonpath='{range .status.containerStatuses[?(@.name=="tools")]}{.imageID}{"\n"}{end}'
```
PASS: ends in `da6fc2be547864451aa253836dd926da33623312df4a9a243e35dc877c378a78`.
FAIL guarded: rollout status green-lighting the old pod (`feedback_rollout_status_old_generation`) prints `d78ab764…`.

**G2 — the bootstrap script finished and `sleep infinity` holds PID 1.** Poll up to 10 min:
```bash
for i in $(seq 1 30); do
  C=$(kubectl -n ai exec "$P" -c tools -- cat /proc/1/comm 2>/dev/null)
  [ "$C" = "sleep" ] && { echo "PID1_SLEEP"; break; }; sleep 20
done
kubectl -n ai get pod "$P" -o jsonpath='{.status.containerStatuses[?(@.name=="tools")].restartCount}'; echo
```
PASS: `PID1_SLEEP` and restartCount `0`. FAIL guarded: while apt runs PID 1 is
`bash` (so the loop cannot pass early); if uutils `sleep` rejected `infinity`,
PID 1 exits and restartCount climbs (baseline 24.04: `sleep`, 0 — measured 2026-09-29).

**G3 — CONTENTS: OS release and the full package set are installed.**
```bash
kubectl -n ai exec "$P" -c tools -- sh -c '. /etc/os-release; echo VERSION_ID=$VERSION_ID; for p in build-essential curl git wget vim nano less libssl-dev libreadline-dev zlib1g-dev libpq-dev libsqlite3-dev; do printf "%s=%s\n" "$p" "$(dpkg-query -W -f="\${Status}" "$p" 2>/dev/null || echo NOT-INSTALLED)"; done | grep -vc "=install ok installed$"'
```
PASS: `VERSION_ID=26.04` then `0` (zero packages not installed). FAIL guarded:
the script has no `set -e`, so a failed/partial apt still reaches `sleep infinity`
— this prints a non-zero count. Negative control (measured 2026-09-29):
`dpkg-query -W -f='${Status}' no-such-pkg-xyz` prints nothing and exits non-zero,
which the loop turns into `NOT-INSTALLED`.

CONTENTS ASSERTION: the sidecar is ubuntu 26.04 with all 12 requested packages in
`install ok installed` state — measured by the G3 dpkg-query loop, compared to
the 24.04 baseline of `0` not-installed on 2026-09-29.

**G4 — CONTENTS: the toolchain actually compiles and links against libpq + sqlite.**
Run with a clean PATH (see §6 — the sidecar's default PATH resolves `as` to a
broken Debian copy under `/paperclip/.local/bin`, a pre-existing defect):
```bash
kubectl -n ai exec "$P" -c tools -- env PATH=/usr/sbin:/usr/bin:/sbin:/bin sh -c 'printf "%s\n" "#include <libpq-fe.h>" "#include <sqlite3.h>" "#include <stdio.h>" "int main(void){printf(\"LINK_OK pq=%d sqlite=%s\\n\", PQlibVersion(), sqlite3_libversion());return 0;}" > /tmp/t.c && gcc -I/usr/include/postgresql /tmp/t.c -o /tmp/t -lpq -lsqlite3 && /tmp/t; rc=$?; rm -f /tmp/t /tmp/t.c; echo rc=$rc; gcc --version | head -1'
```
PASS: `LINK_OK pq=18…` (a 6-digit value starting `18`), `sqlite=3.46.x`, `rc=0`,
and `gcc (Ubuntu 15…`. Baseline 24.04 (2026-09-29): `LINK_OK pq=160015 sqlite=3.45.1`,
`rc=0`, `gcc (Ubuntu 13.3.0-…)`. FAIL guarded: a missing `-dev` package prints a
`fatal error: libpq-fe.h` / `cannot find -lpq` and `rc=1`; a still-24.04 container
prints `pq=16…`.

**G5 — the app came back and serves (floor; the app image is unchanged).**
```bash
kubectl get helmrelease -n ai paperclip -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'; echo
kubectl -n ai port-forward svc/paperclip 13100:3100 >/dev/null 2>&1 & PF=$!; sleep 3
curl -s http://localhost:13100/api/health; echo; kill $PF 2>/dev/null
```
PASS: `True`, and the health JSON contains `"status":"ok"`, `"authReady":true`,
`"bootstrapStatus":"ready"` (identical to the §2.3 baseline). FAIL guarded: the
app not reconnecting to paperclip-postgresql after the Recreate prints a
non-ok status or connection refused.

**G6 — Prometheus sees no crash loop on the pod over 10 min after G2.**
```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 >/dev/null 2>&1 & PF=$!; sleep 3
curl -s --data-urlencode 'query=sum(increase(kube_pod_container_status_restarts_total{namespace="ai",pod=~"paperclip-[a-z0-9]+-[a-z0-9]+"}[10m]))' http://localhost:9090/api/v1/query
curl -s --data-urlencode 'query=count(kube_pod_container_info{namespace="ai",container="tools",image_id=~".*da6fc2be.*"})' http://localhost:9090/api/v1/query
kill $PF 2>/dev/null
```
PASS: restarts increase `0`; `kube_pod_container_info` count `1` (a result of `[]`
means the instrument is not seeing the pod — treat as FAIL, not as pass;
measured 2026-09-29 before the change: the same query reads `[]` because the
live series carries `image_id=…d78ab764…`, so this gate demonstrably fails on
the old generation). No alertname CONTROL: `KubePodCrashLooping` is chart-bundled
and invisible to `plan-premises.py --controls` (manifest-only oracle); the
restart counter above is the same signal, read directly.

CONTROL: metric kube_pod_container_status_restarts_total — sum of increase over 10m for the paperclip pod must be 0
CONTROL: metric kube_pod_container_info — exactly 1 series for container=tools carrying the new digest (non-empty floor)

**After all gates pass (DB bookkeeping, not cluster):** AR-101's needle
(`paperclip: image ubuntu 24.04`) self-lapses once the version title no longer
says 24.04. Retire it deliberately rather than letting it idle:
`runbooks/policy-cli.py risk disable AR-101 --reason 'lapsed: sidecar moved to 26.04 (plan paperclip-26.04, <sha>)'`,
and append the new measurement to F-afa93406 via `finding detail`.

## 5. Rollback

Rollback class `git-revert`: nothing forward-only happens (no schema, no PVC
writes, apt state lives in the ephemeral container rootfs).

```bash
cd /Users/mu/code/cberg-home-nextgen
git revert --no-edit <sha-of-3.2>
git log -1 --format=%s     # confirm it is YOUR revert
git show --stat HEAD       # only kubernetes/apps/ai/paperclip/app/helmrelease.yaml
git push
```

Confirm the cluster is back:

```bash
kubectl get deploy -n ai paperclip -o jsonpath='{.spec.template.spec.containers[?(@.name=="tools")].image}'; echo
# expect ubuntu:24.04@sha256:d78ab76437b1afc5f01e223d6bf0172763f404bb166441328845adbef44518cb
```

Then re-run G1 (expect imageID ending `d78ab764…`), G2, G3 (expect `VERSION_ID=24.04`
and `0`), G4 (expect `pq=160015`) and G5. If you had already disabled AR-101,
re-enable it (or re-add with the same needle, `--expires` set) so the version
finding does not resurface as critical.

## 6. Interference notes

- **Blast radius is paperclip only.** One pod Recreate (single replica, RWO
  `paperclip-data`, strategy Recreate) → paperclip UI/API unavailable ~1-3 min;
  in-flight agent runs are interrupted. `paperclip-postgresql` is a separate
  Deployment and is NOT restarted. No other `ai` app uses this pod.
- **Init containers re-run** on the Recreate: `wait-for-postgres` and the Debian
  `mise-install` script (idempotent; skips everything already under `/paperclip`,
  but needs outbound HTTPS if anything is missing). Its runtime is independent of
  this change.
- **conflicts_with** carries every open plan that re-renders or snapshots
  `helmrelease/paperclip` / `deploy/paperclip` (app-template-5.2.1,
  helm-drift-detection, flux-oci-chart-sources, flux-reconciler-impersonation).
  Those plans do not yet list this one back; reciprocity is not checked by
  `--validate`. G6 reads Prometheus; no kube-prometheus-stack plan is open today —
  add one here if it appears.
- **Pre-existing defect, out of scope (do not fix in this window):** inside the
  `tools` container the default `PATH` puts `/paperclip/.local/bin` first, where
  the Debian `mise-install` init container drops `as`/`ld` copies built for
  Debian's binutils. `gcc` in the tools sidecar therefore resolves `as` to a
  binary that fails with a missing `libbfd-2.44` shared object — measured on
  24.04 on 2026-09-29, and 26.04's binutils will not provide that Debian soname
  either. That is why G4 uses a clean PATH. The upgrade neither causes nor fixes it.
- **Falco/Wazuh:** the apt run after the Recreate produces the usual
  drop-and-exec events; rule 100413 still matches (repository unchanged).

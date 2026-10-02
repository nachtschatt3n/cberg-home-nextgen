---
plan_id: python-fleet-3.14.8
component: python                     # image fleet keyed on the Docker Official Image `python` (slim);
                                      # the three consumers are named in also_covers so coverage.py's
                                      # match_plan() joins each PLAN-lane row to this file
also_covers: [openclaw-probe, mcpo, mealie-shopping-sync]
pr: null                              # coverage.py needs_plan_groups (direct-bump lane) — no Renovate PR
kind: image
current: "python:3.14.7-slim on 3 PLAN-lane consumers (ai/openclaw-probe CronJob, ai/mcpo initContainer runtime-setup, office/mealie-shopping-sync CronJob)"
target: "python:3.14.8-slim on the same 3 consumers (one commit)"
update_type: patch
risk: low                             # same-minor CPython maintenance release on the SAME Debian (trixie)
                                      # base (§1.2); stdlib-only scripts; every consumer is a 5–30 min
                                      # CronJob or a stateless init that already re-runs on every pod start.
                                      # The hold is a policy misattribution, not an image property (§1.1).
est_duration_min: 25                  # pre-checks 5 · edit/commit/push 3 · Flux apply ~2 · mcpo Recreate
                                      # + init ~2 (measured 34 s init, ~90 s to Ready) · wait for the next
                                      # openclaw-probe tick (≤30 min worst case — schedule the window so a
                                      # :00/:30 tick falls inside, or accept the §4.1 gate running late) · gates 5
needs_reboot: false
touches:
  namespaces: [ai, office]
  resources:
    - cronjob/openclaw-probe            # ai — Flux Kustomization ai/openclaw; only the CronJob object changes,
                                        # deployment/openclaw is NOT rolled (no openclaw values/chart edit)
    - helmrelease/mcpo                  # ai — app-template values: initContainer runtime-setup image tag only
    - deployment/mcpo                   # ai — rolls (strategy Recreate, emptyDir only, no PVC); ~90 s outage
                                        # of the admin MCP tool server
    - cronjob/mealie-shopping-sync      # office — Flux Kustomization office/mealie; deployment/mealie untouched
  shared: [monitoring]                  # §4 reads Prometheus (kube-state-metrics) — the window's instrument.
                                        # No gateway/envoy, DNS, CNI, storage or Authentik surface: none of the
                                        # three has an HTTPRoute, a PVC, or an SSO path.
depends_on: []
conflicts_with:
  - app-template-5.2.1                  # nightly:2026-10-02 — edits the SAME file kubernetes/apps/ai/mcpo/app/
                                        # helmrelease.yaml (chart line, Batch A) and rolls helmrelease/openclaw in
                                        # the SAME Flux Kustomization (ai/openclaw) as cronjob/openclaw-probe.
                                        # Same-night: a failed mcpo upgrade could not be attributed. That plan
                                        # does not list us yet — the window agent should add the reciprocal ref.
  - helm-drift-detection                # adds spec.driftDetection to every HR incl. helmrelease/mcpo
  - flux-fleet-0.60.0                   # restarts the Flux controllers that apply this change
  - flux-oci-chart-sources              # rewrites HelmRelease chart sources (bjw-s app-template consumers incl. mcpo)
exclusive: false
security_ref: F-141129dd                # the python:3.14.7-slim image finding (detail in sweep_findings only)
capability_change: false                # same-behaviour interpreter patch under unchanged scripts; no new
                                        # route, permission, API or exposure
rollback_class: git-revert              # nothing forward-only: no PVC, no schema, no data written by the bump
finding_refs: [F-141129dd]              # python:3.14.7-slim image row; this plan moves the 3 PLAN-lane consumers off it
premises:
  # All read-only. Values measured live 2026-10-02 ~03:40 Europe/Berlin.
  - id: probe-on-3.14.7
    why: >-
      `current:` claims the CronJob still runs python:3.14.7-slim. Anything else means it was
      bumped (plan is a no-op — retire it) or changed shape (the §3 sed would not match).
    run: kubectl get cronjob openclaw-probe -n ai -o jsonpath='{.spec.jobTemplate.spec.template.spec.containers[0].image}'
    expect_exact: python:3.14.7-slim
  - id: mcpo-init-on-3.14.7
    why: >-
      The python image is the mcpo initContainer `runtime-setup`, not the app container
      (ghcr.io/open-webui/mcpo). A different first init image means the values shape moved.
    run: kubectl get deploy mcpo -n ai -o jsonpath='{.spec.template.spec.initContainers[0].name}={.spec.template.spec.initContainers[0].image} {.spec.strategy.type}'
    expect_exact: runtime-setup=python:3.14.7-slim Recreate
  - id: mealie-sync-on-3.14.7
    why: "Third member, pulled into PLAN by coverage.py lockstep on the same image+target (§1.1)."
    run: kubectl get cronjob mealie-shopping-sync -n office -o jsonpath='{.spec.jobTemplate.spec.template.spec.containers[0].image}'
    expect_exact: python:3.14.7-slim
  # The two registry facts (same Debian base; past the 24 h patch cooldown) cannot be premises:
  # plan-premises.py allows only kubectl/flux/helm/git/text-filter stages (no curl/python).
  # They are §2 pre-check gates 2.1/2.2 instead, each printing a STOP token on failure.
review: null
status: draft
window: null
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/auto-update.md
  - docs/sops/verification-contents-not-shape.md
generated: "2026-10-02"
---

# python-fleet-3.14.8 — python:3.14.7-slim → 3.14.8-slim on openclaw-probe, mcpo (init), mealie-shopping-sync

## 1. Summary & why held

One commit moves three inline `python:*-slim` pins from `3.14.7-slim` to
`3.14.8-slim`:

| Consumer | Object | What python does there | File |
|---|---|---|---|
| ai/openclaw-probe | CronJob `*/30` | runs `probe.py` (stdlib `urllib`/`json`) — TTS health check that POSTs fire/resolve of `OpenClawVoiceProviderDown` to Alertmanager | `kubernetes/apps/ai/openclaw/app/openclaw-probe.yaml` |
| ai/mcpo | Deployment `mcpo`, **initContainer `runtime-setup`** | build environment only: `apt-get` nodesource `node_20`, `pip install uv`, `npm install -g` the three node MCP servers into the `/shared` emptyDir, then copies `node`, `uv`, `uvx` into `/shared/bin`. The **app container is `ghcr.io/open-webui/mcpo:git-44ce6d0` and is NOT changed**; no python interpreter from this image reaches it. | `kubernetes/apps/ai/mcpo/app/helmrelease.yaml` |
| office/mealie-shopping-sync | CronJob `*/5` | runs `sync.py` (stdlib only) Mealie → HA shopping list | `kubernetes/apps/office/mealie/app/shopping-sync-cronjob.yaml` |

Upstream: Python 3.14.8 (released 2026-09-30) is, per python.org's release
page, "an expedited security release and the eighth maintenance release of
3.14" — bugfixes plus updated bundled libraries, no language or API change
within 3.14. The image-side reason to take it is recorded on the security
finding `F-141129dd` (detail in `sweep_findings`, not here).

### 1.1 Why it was held — the hold is a policy MISATTRIBUTION for two of three members

Verified in `runbooks/coverage.py` (`deny_rule_for()` — first matching glob
decides, a rule with no `max:` blocks every update type; `deny_rule_for_item()`
matches the COMPONENT key first) against `runbooks/auto-update-policy.yaml`
(version `2026.10.01`), and by running `coverage.py --json` on 2026-10-02:

- **openclaw-probe** — held by `match: "*openclaw*"` (no `max:`), reason
  *"held at 2026.6.11 pending the Memory Core→SQLite migration (2026.7.1
  blocked)."* That rule exists for the OpenClaw APP image. It fires here only
  because the component key `openclaw-probe` contains the substring
  `openclaw`. The probe is a stdlib python script with no OpenClaw code, no
  Memory Core and no coupling to the OpenClaw version; the same file moved
  3.14.x via the nightly direct-bump lane before (`ea1e860d`, 2026-08-27).
  **Misattribution.**
- **mcpo** — held by `match: "*mcpo*"` (no `max:`), reason *"python init base
  image major (3.11→3.14) rides these tags."* That rule was added in
  `bf1850ac` (2026-07-25) while the init was on `3.11-slim`; the 3.11→3.14
  major it guards **was executed in `39fa6625` (2026-09-13)**. Its premise is
  spent, and with no `max:` it now holds every mcpo update — including this
  same-minor patch and the mcpo chart/app legs. **Stale rule.**
- **mealie-shopping-sync** — no deny rule of its own. It was AUTO-eligible
  and `_apply_lockstep()` pulled it into PLAN because `openclaw-probe` is PLAN
  on the same repo `python` at the same target `3.14.8-slim` (coverage reason
  string: *"lockstep — openclaw-probe is PLAN on the SAME image python at the
  same target"*). It is listed in `also_covers` so it is not stranded.

**Second-order effect the operator should know about:** 14 other
`python:3.14.7-slim` consumers (ai/ollama-toolfix, download/tube-archivist-
{image,nfo}-sync, 11 media/library-tools CronJobs + media-dashboard) are
currently HELD only by the 24 h cooldown (tag is ~2 h old at authoring). When
the cooldown lapses they become AUTO and the same lockstep key
`(python, 3.14.8-slim)` will pull every one of them into PLAN behind this
plan — the misattributed openclaw rule ends up holding the whole slim fleet.
They are deliberately NOT in this plan's scope (separate unrelated CronJobs,
no deployable-unit coupling; two of the media files are edited by
`jellyfin-config-rwo-migration`/read by `jellyfin-12.1`). Once this plan
executes, the holder disappears and they return to the nightly AUTO lane on
their own. The cleaner fix is the policy correction in §6 — after which this
whole plan is a candidate for retirement (`maintenance-plan.py --verify` will
flag it if the AUTO lane lands the bump first).

The four `python:3.14.7-alpine` / `docker.io/library/python` consumers are a
different repo string and tag and are unaffected by any of this.

**Verdict:** the hold is a false positive with respect to the image. Risk
`low`. Planned anyway because the policy currently routes it here; the
window agent / operator decides.

### 1.2 Evidence for "same base, same behaviour"

- Docker Hub, measured 2026-10-02: `3.14.7-slim` digest == `3.14.7-slim-trixie`
  digest, and `3.14.8-slim` (`sha256:89fb7d3d…`) == `3.14.8-slim-trixie`. Both
  tags are Debian trixie; amd64 present. (Pre-check §2.1.)
- mcpo's init therefore keeps installing the same nodesource `node_20`
  for the same distribution, and the `node` binary it copies into the mcpo
  app container is unchanged in kind. Note this init is **non-hermetic
  regardless of this bump**: every pod start pulls the newest node 20.x,
  `uv`, and the newest `@upstash/context7-mcp`, `prometheus-mcp`,
  `@modelcontextprotocol/server-github` from the internet. The roll in §3 will
  therefore also refresh those — the §4.2 tool-count gate is what catches a
  bad npm release, not the python bump.
- Both CronJob scripts import only stdlib (`json`, `os`, `time`,
  `urllib.request`); 3.14.8 changes no public API inside 3.14.

## 2. Pre-checks

Run from the repo root on the Mac mini (zsh). All read-only.

```bash
cd /Users/mu/code/cberg-home-nextgen
.venv/bin/python3 runbooks/plan-premises.py python-fleet-3.14.8      # every premise must PASS

# 2.1 same Debian base (§1.2's risk claim). Prints trixie; DIFFERENT => STOP and re-plan.
python3 -c "import json,urllib.request as u;g=lambda t: json.load(u.urlopen('https://hub.docker.com/v2/repositories/library/python/tags/'+t))['digest'];print('trixie' if g('3.14.8-slim')==g('3.14.8-slim-trixie') else 'DIFFERENT')"

# 2.2 past the 24 h patch cooldown (policy minimum_release_age_hours_by_type.patch). Prints AGED; YOUNG => STOP.
python3 -c "import json,urllib.request as u,datetime as d;t=json.load(u.urlopen('https://hub.docker.com/v2/repositories/library/python/tags/3.14.8-slim'))['last_updated'];a=(d.datetime.now(d.timezone.utc)-d.datetime.fromisoformat(t.replace('Z','+00:00'))).total_seconds()/3600;print('AGED' if a>=24 else 'YOUNG')"

# Flux owners healthy and on HEAD
flux get kustomizations -n ai openclaw mcpo
flux get kustomizations -n office mealie
flux get helmreleases -n ai mcpo                                         # Ready True

# Baseline: last runs of both CronJobs succeeded
kubectl -n ai get cronjob openclaw-probe -o jsonpath='{.status.lastSuccessfulTime} {.status.lastScheduleTime}{"\n"}'
kubectl -n office get cronjob mealie-shopping-sync -o jsonpath='{.status.lastSuccessfulTime} {.status.lastScheduleTime}{"\n"}'

# Baseline: the running python imageID (containerd reports the platform-manifest digest, not
# the tag's index digest — on 2026-10-02 the mcpo init showed …bd65a5ebe91c401c8e83 for 3.14.7-slim)
kubectl -n ai get pod -l app.kubernetes.io/name=mcpo -o jsonpath='{.items[0].status.initContainerStatuses[0].imageID}{"\n"}'

# Baseline: mcpo per-server tool counts (the §4.2 contents baseline).
# Measured 2026-10-02: context7=2 prometheus=10 alertmanager=9 kubernetes=14 github=26
kubectl -n ai port-forward svc/mcpo 18000:8000 >/dev/null 2>&1 & PF=$!; sleep 3
for s in context7 prometheus alertmanager kubernetes github; do
  printf '%s ' "$s"; curl -s http://localhost:18000/$s/openapi.json | python3 -c "import sys,json;print(len(json.load(sys.stdin).get('paths',{})))"
done
kill $PF 2>/dev/null
```

STOP if any premise fails, any Flux object is not Ready, or the baseline
counts differ from the measured line by more than the operator is willing to
attribute to upstream npm drift (re-record the baseline then; §4.2 compares to
what you record HERE, not to the 2026-10-02 numbers).

## 3. Steps

```bash
cd /Users/mu/code/cberg-home-nextgen
git pull --rebase

# 3.1 the two CronJobs (BSD sed; dry-tested 2026-10-02 on scratch copies)
sed -i '' 's|image: python:3\.14\.7-slim$|image: python:3.14.8-slim|' \
  kubernetes/apps/ai/openclaw/app/openclaw-probe.yaml \
  kubernetes/apps/office/mealie/app/shopping-sync-cronjob.yaml

# 3.2 the mcpo initContainer tag (app-template values; the app container tag git-44ce6d0 is NOT touched)
sed -i '' 's|^\([[:space:]]*tag:[[:space:]]*\)3\.14\.7-slim$|\13.14.8-slim|' \
  kubernetes/apps/ai/mcpo/app/helmrelease.yaml

git diff --stat    # expect exactly 3 files, 3 insertions, 3 deletions
```

Dry-test result (scratch copies, 2026-10-02):

```
openclaw-probe.yaml       95c95  <  image: python:3.14.7-slim   >  image: python:3.14.8-slim
shopping-sync-cronjob.yaml 48c48 <  image: python:3.14.7-slim   >  image: python:3.14.8-slim
helmrelease.yaml (mcpo)   47c47  <  tag: 3.14.7-slim            >  tag: 3.14.8-slim
```

(`shopping-sync-cronjob.yaml` still contains the string `3.14.7-slim` once,
inside a comment on line ~44 — that is expected; do not "fix" it in this
commit.)

```bash
# 3.3 commit ONLY these paths (shared worktree) and verify before pushing
cat > /tmp/msg-python-fleet.txt <<'EOF'
chore(deps): python 3.14.7-slim -> 3.14.8-slim on openclaw-probe, mcpo init, mealie-shopping-sync

Plan: runbooks/maintenance/plans/python-fleet-3.14.8.md (security_ref F-141129dd)
EOF
git commit --only \
  kubernetes/apps/ai/openclaw/app/openclaw-probe.yaml \
  kubernetes/apps/office/mealie/app/shopping-sync-cronjob.yaml \
  kubernetes/apps/ai/mcpo/app/helmrelease.yaml \
  -F /tmp/msg-python-fleet.txt
git show --stat HEAD            # exactly the 3 files above
git log -1 --format=%s          # must be the subject above; amend before push if not
git push
```

Flux applies on the push webhook; no manual reconcile (the SOP's default).
If nothing has applied after 10 minutes, `flux get kustomizations -n ai openclaw`
shows the revision — escalate rather than force.

## 4. Verification

Run `export PUSH_TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)` right after the push (exported: the python one-liners below read it from the environment). Every
gate below compares against objects created AFTER `PUSH_TS`.

**4.0 Applied (floor).** Each live spec carries the new tag:

```bash
kubectl -n ai get cronjob openclaw-probe -o jsonpath='{.spec.jobTemplate.spec.template.spec.containers[0].image}{"\n"}'          # python:3.14.8-slim
kubectl -n office get cronjob mealie-shopping-sync -o jsonpath='{.spec.jobTemplate.spec.template.spec.containers[0].image}{"\n"}' # python:3.14.8-slim
kubectl -n ai get deploy mcpo -o jsonpath='{.spec.template.spec.initContainers[0].image}{"\n"}'                                    # python:3.14.8-slim
```

Fails (prints `3.14.7-slim`) if Flux has not applied — wait/escalate, do not
proceed to judge 4.1–4.3 on old pods (`feedback_rollout_status_old_generation`).

**4.1 openclaw-probe — CONTENTS ASSERTION: the probe still measures TTS and
still reaches Alertmanager on the new interpreter** — measured on the first
Job created after `PUSH_TS` (next `:00`/`:30` tick), compared to the baseline
log shape (`local_tts_ok=True` + two `alertmanager POST 200` lines, seen
2026-10-02 on job `openclaw-probe-29848410`).

```bash
J=$(kubectl -n ai get jobs -o json | python3 -c "
import sys,json,os
ts=os.environ['PUSH_TS']
js=[j for j in json.load(sys.stdin)['items']
    if (j['metadata'].get('ownerReferences') or [{}])[0].get('name')=='openclaw-probe'
    and j['metadata']['creationTimestamp']>ts]
js.sort(key=lambda j:j['metadata']['creationTimestamp']); print(js[-1]['metadata']['name'] if js else 'NONE')")
echo "$J"                                                                   # NONE => tick not reached yet; wait
kubectl -n ai get job "$J" -o jsonpath='{.status.succeeded}{"\n"}'           # 1
kubectl -n ai get pod -l job-name="$J" -o jsonpath='{.items[0].status.containerStatuses[0].imageID}{"\n"}'  # must DIFFER from the 3.14.7 imageID recorded in §2
kubectl -n ai logs job/"$J" | grep -ciE '^local_tts_ok=true$'               # 1
kubectl -n ai logs job/"$J" | grep -ciE '^alertmanager POST 200 '           # 2
```

PASS = succeeded 1, `local_tts_ok=True` 1, `POST 200` 2. What failure prints:
an import/runtime break gives `succeeded` empty and a traceback; a TLS/urllib
regression in the interpreter prints `tts health error:` and
`local_tts_ok=False` (count 0 on the first grep — and it would ALSO fire
`OpenClawVoiceProviderDown` critical, which is the user-visible symptom); an
Alertmanager POST failure raises and the Job fails. Caveat that keeps this
honest: `local_tts_ok=False` can also mean the Mac-mini TTS server is down
for unrelated reasons — if so, curl its `/health` from the Mac before
blaming the image.

**4.2 mcpo — CONTENTS ASSERTION: every MCP server still starts and exposes its
tools** — per-server `paths` count from `/<server>/openapi.json`, compared to
the §2 baseline. Equal or higher per server = PASS; any server returning a
non-200 or `0` paths = FAIL.

```bash
kubectl -n ai get pod -l app.kubernetes.io/name=mcpo -o jsonpath='{.items[0].status.startTime} {.items[0].status.initContainerStatuses[0].image} {.items[0].status.initContainerStatuses[0].state.terminated.exitCode}{"\n"}'
# startTime must be AFTER PUSH_TS; image python:3.14.8-slim; exitCode 0
kubectl -n ai wait --for=condition=Ready pod -l app.kubernetes.io/name=mcpo --timeout=600s
kubectl -n ai port-forward svc/mcpo 18000:8000 >/dev/null 2>&1 & PF=$!; sleep 3
for s in context7 prometheus alertmanager kubernetes github; do
  printf '%s ' "$s"; curl -s -o /tmp/mcpo-$s.json -w '%{http_code} ' http://localhost:18000/$s/openapi.json
  python3 -c "import json;print(len(json.load(open('/tmp/mcpo-$s.json')).get('paths',{})))" 2>/dev/null || echo PARSE_FAIL
done
curl -s -o /dev/null -w 'negative-control %{http_code}\n' http://localhost:18000/nonexistent/openapi.json   # must be 404
kill $PF 2>/dev/null
```

Why this can fail: mcpo mounts each server at `/<name>` only after that
server's stdio process starts and lists tools; a server whose `node`/`uvx`
binary from the init is broken is absent (404) or empty. The negative control
was measured 2026-10-02 (`/nonexistent/openapi.json` → 404), so a 404 on a
real server name is a real failure, not a URL mistake. Init-container failure
shows earlier as a non-zero `exitCode` / `Init:CrashLoopBackOff` and the
Ready wait timing out.

**4.3 mealie-shopping-sync — CONTENTS ASSERTION: the sync still reads Mealie
and Home Assistant** — first Job after `PUSH_TS` (≤5 min), compared to
baseline `done: pushed=0 already-synced=119 excluded=0 lists=1` (2026-10-02).

```bash
J=$(kubectl -n office get jobs -o json | python3 -c "
import sys,json,os
ts=os.environ['PUSH_TS']
js=[j for j in json.load(sys.stdin)['items']
    if (j['metadata'].get('ownerReferences') or [{}])[0].get('name')=='mealie-shopping-sync'
    and j['metadata']['creationTimestamp']>ts]
js.sort(key=lambda j:j['metadata']['creationTimestamp']); print(js[-1]['metadata']['name'] if js else 'NONE')")
kubectl -n office get job "$J" -o jsonpath='{.status.succeeded}{"\n"}'                    # 1
kubectl -n office logs job/"$J" | grep -iE '^done: pushed=[0-9]+ already-synced=[1-9][0-9]* ' # one line, already-synced > 0
```

PASS = succeeded 1 and `already-synced` non-zero (a floor, not just "ran":
an empty Mealie read would print `already-synced=0` and fail the regex).

**Instruments (CONTROL lines)** — all from kube-state-metrics in the
`kube-prometheus-stack` Prometheus, verified to return series 2026-10-02
(and an empty result for a nonexistent job name, i.e. the selectors are not
vacuous):

CONTROL: metric kube_job_status_failed — for `job_name=~"openclaw-probe.*|mealie-shopping-sync.*"` in ns ai/office, every Job created after PUSH_TS must read 0 (baseline 0/0).
CONTROL: metric kube_job_status_succeeded — same selector, the post-push Jobs must read 1 (baseline 1/1).
CONTROL: metric kube_deployment_status_replicas_available — `{namespace="ai",deployment="mcpo"}` must return to 1 within 10 min of the push (baseline 1).
CONTROL: metric kube_pod_init_container_status_restarts_total — `{namespace="ai",container="runtime-setup"}` must stay 0 on the new pod (an init crash loop shows here first).

```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 19090:9090 >/dev/null 2>&1 & PF=$!; sleep 3
for q in 'kube_job_status_failed{namespace=~"ai|office",job_name=~"openclaw-probe.*|mealie-shopping-sync.*"}' \
         'kube_deployment_status_replicas_available{namespace="ai",deployment="mcpo"}' \
         'kube_pod_init_container_status_restarts_total{namespace="ai",container="runtime-setup"}'; do
  printf '%s => ' "$q"; curl -s -G http://localhost:19090/api/v1/query --data-urlencode "query=$q" \
    | python3 -c "import sys,json;r=json.load(sys.stdin)['data']['result'];assert r,'EMPTY RESULT';print([x['metric'].get('job_name',x['metric'].get('pod',''))+'='+x['value'][1] for x in r])"
done
kill $PF 2>/dev/null
```

(The `assert r` makes an empty answer a failure, not a pass.)

## 5. Rollback

Nothing forward-only happens: no PVC, no schema, no persisted state is
written by a base-image change (mcpo's `/shared` is an emptyDir rebuilt on
every start). Rollback is a revert:

```bash
cd /Users/mu/code/cberg-home-nextgen
git revert --no-edit <sha-of-3.3>
git show --stat HEAD            # the same 3 files, tags back to 3.14.7-slim
git log -1 --format=%s          # "Revert \"chore(deps): python 3.14.7-slim -> 3.14.8-slim ..."
git push
```

Confirm back: re-run the three §4.0 commands — each prints
`python:3.14.7-slim`; mcpo pod `startTime` is after the revert push and §4.2
counts match the §2 baseline; the next openclaw-probe and mealie Jobs pass
§4.1/§4.3. If §4.2 failed because an npm package moved (not python), the
revert alone will NOT fix it — the init re-pulls the same newest npm
packages on the reverted image too; then pin the offending package in the
init script under a separate plan/commit and say so in the window report.

If `OpenClawVoiceProviderDown` fired during a failed §4.1, it resolves on the
next successful probe tick (the probe POSTs `endsAt=now`); no manual
Alertmanager action needed.

## 6. Interference notes

- **Same file as tonight's `app-template-5.2.1`** (nightly:2026-10-02, Batch A
  edits the chart version line of `kubernetes/apps/ai/mcpo/app/helmrelease.yaml`;
  Batch C rolls `helmrelease/openclaw` in the same Flux Kustomization as
  `cronjob/openclaw-probe`). Do not share a window; textual merge would work,
  attribution of an mcpo failure would not. Declared in `conflicts_with`; the
  other side does not list this plan yet.
- Not rolled by this plan: `deployment/openclaw`, `deployment/ollama-toolfix`,
  `deployment/mealie`. Only the mcpo pod restarts (~90 s, Recreate). mcpo is
  the admin MCP tool server (no HTTPRoute — `ingress.main.enabled: false`);
  in-flight tool calls during the roll fail and retry.
- openclaw-probe fires at `:00/:30` (UTC cron in-cluster); avoid scheduling
  the push within 2 min of a tick to keep §4.1's "first job after push" clean.
  No OpenClaw cron/voice briefing is touched (`feedback_no_openclaw_roll_during_crons`
  is about rolling the openclaw pod, which this does not do).
- **Repo corrections owed (out of scope for this plan; report, do not
  silently plan around):**
  1. `auto-update-policy.yaml` `*openclaw*` (no `max:`) catches
     `openclaw-probe` by substring and attaches the OpenClaw app's Memory-Core
     reason to a stdlib python CronJob. Via `_apply_lockstep` it then holds
     every other `python:3.14.8-slim` consumer. Suggested shape: a narrower
     rule placed ABOVE it (first match wins) for `openclaw-probe` with an
     honest reason and `max: minor`, or narrow `*openclaw*` to the app image
     repo. Operator decision.
  2. `*mcpo*` reason "python init base image major (3.11→3.14) rides these
     tags" is spent — that major landed in `39fa6625` (2026-09-13). With no
     `max:` it holds every mcpo update type. Suggested: drop it, or re-issue
     with a current reason and `max: patch`/`minor`.
  3. Minor doc drift: the comment in `shopping-sync-cronjob.yaml` says the
     inline tag "is not tracked by the version checker" — it is tracked now
     (coverage reports it). Cosmetic.

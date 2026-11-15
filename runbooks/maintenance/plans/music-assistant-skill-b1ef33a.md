---
plan_id: music-assistant-skill-b1ef33a
component: music-assistant-skill
pr: 224                               # Renovate "update ghcr.io/alams154/music-assistant-skill ( ad7ec55 -> b1ef33a )",
                                      # 1 line in music-assistant-server/app/helmrelease.yaml; Flate Render Gate +
                                      # both Flux Local Diffs green 2026-11-14. Automerge disabled by config.
kind: image
current: "latest@sha256:ad7ec55a51d9304032a74d8ae0fda43743bf64ae68afa49dd6949d9477726ccf"
                                      # live 2026-11-14: container alexa-skill imageID == this digest, 0 restarts
target: "latest@sha256:b1ef33ad0b05b7e0a315535e8141177898be4b6a0401decf43dedf424f0d90f1"
                                      # GHCR 2026-11-14: this digest carries tags 0.0.39-beta + latest (pushed 2026-10-15)
update_type: digest
risk: medium                          # third-party BETA image, floating tag, no semver gate; the change touches
                                      # the Alexa stream-URL path, which is load-bearing and externally exposed.
                                      # Blast radius is small though: stateless container, one voice feature.
est_duration_min: 25
needs_reboot: false
touches:
  namespaces: [home-automation]
  resources:
    - helmrelease/music-assistant-server   # tag edit on the alexa-skill sidecar ONLY
    - deployment/music-assistant-server    # Recreate: the SAME pod holds the MA server (app) + the skill
                                           # sidecar, so the MA web UI/streaming is down ~1-2 min as well
    - pvc/music-assistant-config           # not edited; re-attached (Longhorn static, RWO)
    - httproute/music-assistant-alexa-api  # not edited; backend :5000 is the container being replaced
    - httproute/music-assistant-alexa-stream # not edited; its path is what the target's URL fix changes
  shared: [public-edge]               # envoy-external carries both Alexa hostnames; not changed, only exercised
depends_on: []
conflicts_with: [envoy-gateway-1.10.0, kube-prometheus-stack-93.3.0, longhorn-1.13.0, coredns-1.50.5, iobroker-v12.0.0-digest-005ba9c, otbr-thread-rcp-recovery, otbr-0.4.0, talos-linux-1.14.5]
                                      # iobroker-v12.0.0-digest-005ba9c, otbr-thread-rcp-recovery, otbr-0.4.0: all touch
                                      #   home-automation; section 6 forbids overlap with any plan in that namespace.
                                      # talos-linux-1.14.5: node roll reboots the node this hostNetwork pod runs on.
                                      # envoy-gateway-1.10.0: restarts the public edge both Alexa routes use; a
                                      #   failing §4.3 would be unattributable. Serialize, either order.
                                      # kube-prometheus-stack-93.3.0: §4 reads kube_pod_container_status_* from
                                      #   Prometheus; the window instrument must not be mid-upgrade.
                                      # longhorn-1.13.0 (sun-attended:2026-11-15): this plan re-attaches
                                      #   volume/music-assistant-config; never the same slot.
                                      # coredns-1.50.5: §4.3 resolves public names; keep DNS stable.
                                      # Built 2026-11-14 from `maintenance-plan.py --open` + plan frontmatter.
exclusive: false
security_ref: F-a54886d3              # image CVE detail lives on the DB record only (AR-029 accepted rows
                                      # F-f3a60554, F-a54886d3 name this image); do not copy counts here.
finding_refs: [F-a54886d3, F-f3a60554]
                                      # `policy-cli.py finding list --grep music` 2026-11-14: both are AR-029
                                      # rows on ghcr.io/alams154/music-assistant-skill:latest. This is a THIRD-PARTY
                                      # image: remediation is bump-only, never rebuild. F-5ff5d278 / F-cf4da6a7
                                      # name the MA SERVER image at a stale 2.10.9 (live is 2.10.12) - not this plan.
capability_change: false              # same app, same env, same ports/routes. Upstream notes behaviour fixes (below)
                                      # but add no route, permission, API or exposure for us.
rollback_class: git-revert            # stateless container: no schema, no PVC write by the skill (it mounts only
                                      # /cache emptyDir + /data of the MA server). Old digest stays pullable.
review: ready-for-go@2026-11-15      # plan-reviewer 2nd pass 2026-11-15: ready-for-go, 0 blocking (1st pass needs-fix: stale MA server digest + conflicts_with, both fixed + verified live). Attended window preferred (voice test 4.6).
status: vetted
window: null
premises:
  - id: live-skill-digest-is-old
    why: "`current:` and the rollback target claim ad7ec55. If the live sidecar already moved, the baseline is wrong."
    run: kubectl get deploy -n home-automation music-assistant-server -o jsonpath='{.spec.template.spec.containers[?(@.name=="alexa-skill")].image}'
    expect_exact: ghcr.io/alams154/music-assistant-skill:latest@sha256:ad7ec55a51d9304032a74d8ae0fda43743bf64ae68afa49dd6949d9477726ccf
  - id: strategy-is-recreate
    why: "RWO Longhorn PVC + replicas 1: RollingUpdate would Multi-Attach-deadlock (docs/sops/longhorn-rwo-multi-attach.md)."
    run: kubectl get deploy -n home-automation music-assistant-server -o jsonpath='{.spec.strategy.type}'
    expect_exact: Recreate
  - id: helmrelease-ready
    why: "A HelmRelease already failing would make a post-upgrade failure unattributable."
    run: kubectl get helmrelease -n home-automation music-assistant-server -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: "True"
  - id: data-volume-healthy
    why: "The roll re-attaches this volume; a degraded volume turns a re-attach into a data risk."
    run: kubectl get volume -n storage music-assistant-config -o jsonpath='{.status.robustness}'
    expect_exact: healthy
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/longhorn-rwo-multi-attach.md
  - docs/sops/storage-safety.md
generated: "2026-11-14"
---

# music-assistant-skill: digest ad7ec55 -> b1ef33a (0.0.39-beta, floating `latest`)

## 1. Summary & why held

`ghcr.io/alams154/music-assistant-skill` is the Alexa skill/API sidecar that runs in the
`music-assistant-server` pod next to the MA server (`ghcr.io/music-assistant/server`, 2.10.12 live and in git since commit 81dce96dc,
imageID sha256:7eb272e2e13d..., unchanged by this plan). It serves `/alexa/intents` to MA's Alexa provider and rewrites stream
URLs for Echo devices (`MA_HOSTNAME=https://music-stream.<domain>`). **It is NOT our image**: upstream
is `alams154/music-assistant-alexa-skill-prototype` (third-party, self-described prototype), so the rule
is bump-only; there is no rebuild-and-roll and no `ghcr.io/nachtschatt3n/**` involvement.

**Why held.** The upstream publishes only the floating `latest` (now also `0.0.39-beta`), so the repo
pins `latest@sha256:...` and bumps by hand (comment in the HelmRelease). A digest move has no semver
signal, the auto-updater cannot read release notes for it, and the target is tagged **beta**. The
sidecar fronts the externally exposed Alexa routes (`envoy-external`), and the MA streamserver path is
documented as fragile in the HelmRelease (MA publishes `http://music-stream.<domain>:80` and the skill
rewrites to https). So: PLAN lane, operator go/no-go.

**What changed upstream** (commits 2026-10-14..15 on `master`, read via the GitHub API; the live digest
dates from before these):
- `f162306` percent-encodes the WHOLE stream URL (was spaces only) and leaves `shouldEndSession` unset
  in the APL metadata refresh. Behaviour fix on the exact path we care about: URLs containing e.g. an
  apostrophe in the MA player name used to be rejected by Alexa. Relevant to us; it should help.
- `535bc75` binds to `$HOST` (default `0.0.0.0`, our case unchanged), posts metadata to `$HOST:$PORT`
  instead of `localhost:5000`, exits on SIGTERM (faster pod stop), logs why Alexa ended a session.
  Our `PORT=5000` and hostNetwork pod: unchanged semantics. Note the HelmRelease does not set `HOST`.
- `d025e43` / `4e22690` the simulator page now runs requests in-app (stays behind the web UI password).
  No exposure change for us.
- No change to `LOCALE`, `MA_HOSTNAME`, `PORT` handling seen in README env table (re-read 2026-11-14).
  README documents `SKIP_URL_VALIDATION` (default false) and `ENABLE_APL` (default false); we set neither.
No breaking change was found. **Not found** (and not claimed): a changelog - upstream has no releases
page; the above comes from commit messages and file diffs, so unknown regressions are possible. That is
why this is `medium`, not `low`.

**Side effect to plan for.** Both containers share ONE pod and the Deployment is `Recreate`, so the MA
server (web UI, Home Assistant integration, all players' streams) restarts too: ~1-2 min outage, music
playing on any player stops. The MA server image is NOT changed.

**Attended or not?** Prefer an **attended** window (sat/sun): the only end-to-end proof that the Alexa
path works is a voice command to an Echo, which needs a human. A `nightly` run can still prove §4.1-4.3
(pod, intents, routes) but not §4.4; if the operator accepts that, it may run unattended, with a morning
voice check.

## 2. Pre-checks (all read-only; abort on any failure)

```bash
# 2.1 PR still open, still the same one-line change to the same digests
gh pr view 224 --json state,title,files --jq '.state, .title, ([.files[].path]|join(","))'
# expect OPEN / "... ( ad7ec55 -> b1ef33a )" / the one helmrelease.yaml path. MERGED or retitled -> STOP, re-plan.
# 2.2 target digest still exists and still carries `latest` (GHCR can retag/delete)
gh api '/users/alams154/packages/container/music-assistant-skill/versions' \
  --jq '.[]|select(.name|startswith("sha256:b1ef33ad0b05"))|.metadata.container.tags|join(",")'
# expect: 0.0.39-beta,latest   (empty -> target gone -> STOP; a different tag set -> re-read upstream)
# 2.3 premises: live digest, Recreate, HR Ready, volume healthy
python3 runbooks/plan-premises.py music-assistant-skill-b1ef33a --require-premises
# 2.4 baseline for the gates: record the live skill contract BEFORE the roll
kubectl port-forward -n home-automation svc/music-assistant-server 15000:5000 & PF=$!; sleep 3
curl -s -o /dev/null -w '%{http_code}\n' localhost:15000/alexa/intents                  # baseline: 200
curl -s localhost:15000/alexa/intents | python3 -c "import sys,json; d=json.load(sys.stdin)['intents']; print(len(d), [i['intent'] for i in d][:3]); print(d[0]['utterances'])"
kill $PF                                                                                # always clean up the forward
# baseline 2026-11-14: HTTP 200, German utterances (e.g. AMAZON.CancelIntent -> "abbrechen"). Save the count.
# 2.4b baseline of the MA SERVER (app) imageID: §4.1 asserts equality with THIS, not a hard-coded digest
kubectl get pod -n home-automation -l app.kubernetes.io/name=music-assistant-server -o jsonpath='{.items[*].status.containerStatuses[?(@.name=="app")].imageID}'
# expect (2026-11-15 reference): ghcr.io/music-assistant/server@sha256:7eb272e2e13d... (server 2.10.12). RECORD the full value as APP_BASE.
# If the container is not named "app" this prints empty -> STOP and read the container names first.
# 2.5 no unrelated pod in the namespace is already unhealthy (unattributable failure otherwise)
kubectl get pods -n home-automation --no-headers | awk '$3!="Running" && $3!="Completed"'
# expect empty output
# 2.6 not the same slot as a conflicting plan: python3 runbooks/maintenance-plan.py --open  (see conflicts_with)
# 2.7 nobody is listening: confirm with the operator that no music is playing (the pod restarts)
```

No volume backup is needed (nothing stateful changes); the nightly Longhorn backup of
`music-assistant-config` is the safety net and the re-attach is routine.

## 3. Steps (GitOps; one commit)

Prefer landing the Renovate PR itself (it is exactly the intended one-line change):

```bash
gh pr merge 224 --squash        # operator/window agent GO required (automerge is disabled by config)
git pull --ff-only origin main
git diff HEAD~1 -- kubernetes/apps/home-automation/music-assistant-server/app/helmrelease.yaml
# expect exactly one line: tag: latest@sha256:ad7ec55... -> tag: latest@sha256:b1ef33ad...
```

If the PR is unusable (conflict, closed), make the equivalent edit by hand. BSD-sed safe form, dry-run on a
copy first (`cp helmrelease.yaml /tmp/x.yaml`; the anchor contains no `\s`):

```bash
F=kubernetes/apps/home-automation/music-assistant-server/app/helmrelease.yaml
sed -i '' 's/sha256:ad7ec55a51d9304032a74d8ae0fda43743bf64ae68afa49dd6949d9477726ccf/sha256:b1ef33ad0b05b7e0a315535e8141177898be4b6a0401decf43dedf424f0d90f1/' "$F"
git diff -- "$F"        # exactly 1 line changed; the app (MA server) tag 2.10.12 untouched
git commit --only "$F" -F msg.txt && git log -1 --format=%s   # subject must be YOURS (shared worktree)
git push origin main
```

Then let the Flux webhook reconcile (no manual `flux reconcile` unless the webhook is not firing).
Expected: HelmRelease upgrade -> Deployment rolls (Recreate) -> a new pod with 2/2 containers.

## 4. Verification (any FAIL -> section 5)

```bash
# 4.1 rollout landed on the NEW generation and the new digest (rollout status alone green-lights the old one)
kubectl get pod -n home-automation -l app.kubernetes.io/name=music-assistant-server \
  -o jsonpath='{range .items[*]}{.metadata.name} {.status.phase} {range .status.containerStatuses[*]}{.name}={.ready}/{.restartCount}/{.imageID} {end}{"\n"}{end}'
# PASS: exactly ONE pod; alexa-skill imageID ends sha256:b1ef33ad0b05...; app imageID EQUALS the APP_BASE recorded at §2.4b (UNCHANGED; reference 2026-11-15: sha256:7eb272e2e13d...);
#       both ready=true; restartCount 0 for both.
# FAIL prints: two pods (old one not gone), the old ad7ec55 digest, ready=false or restartCount>0 (a crash loop shows >=1 within 2 min).
# Wait 3 min and re-read the restart count: a startup that dies on first Alexa request is not caught by the first read.

# 4.2 skill contract: intents served, same locale and shape as the baseline (this is what MA's provider consumes)
kubectl port-forward -n home-automation svc/music-assistant-server 15001:5000 & PF=$!; sleep 3   # distinct port from §2.4
curl -s -o /dev/null -w '%{http_code}\n' localhost:15001/alexa/intents
curl -s localhost:15001/alexa/intents | python3 -c "import sys,json; d=json.load(sys.stdin)['intents']; print(len(d), d[0]['utterances'])"
kill $PF                                                                                         # clean up
# PASS: 200, same intent count as §2.4, German utterances.
# FAIL prints: 404/500/connection refused (app did not start), or ENGLISH utterances / different count
# (the new image dropped or ignored LOCALE=de-DE: that silently breaks the German Echo commands while the pod stays Ready).

# 4.3 public edge still routes to the new container (the Alexa path is external)
kubectl get httproute -n home-automation music-assistant-alexa-api music-assistant-alexa-stream \
  -o jsonpath='{range .items[*]}{.metadata.name} {.status.parents[*].conditions[?(@.type=="Accepted")].status}{"\n"}{end}'
# PASS: both lines end True. Then from OUTSIDE the cluster network (a mobile hotspot, or the operator's phone):
#   curl -s -o /dev/null -w '%{http_code}\n' https://music-api.<domain>/alexa/intents     # PASS 200 (same as 4.2)
# FAIL prints: 404/503 from the edge, or a timeout (route/backend broken). Use the real domain at run time; it is not committed here.
# NOTE: the off-network curl needs a human (hotspot/phone), so it only runs ATTENDED. Unattended fallback: the
# Accepted check above (must be True) plus, from inside the cluster, the §4.2 forward; record "external curl pending"
# on the plan and have the operator run it next morning. Do not report 4.3 PASS on the Accepted check alone.

# 4.4 log scan: the new image logs why Alexa ends a session, so errors are now visible
kubectl logs -n home-automation deploy/music-assistant-server -c alexa-skill --since=10m | grep -i -E 'traceback|error|exception|critical'
# PASS: no match (grep exit 1) AND the line "Mounted MA API app at /ma and Alexa API at /alexa" is present (grep -c >= 1).
# FAIL prints: a traceback, or the Mounted line missing. Check BOTH, an empty log also yields "no match".

# 4.5 MA server side unaffected: UI up through the internal route, player list intact
curl -s -o /dev/null -w '%{http_code}\n' -k https://music.<domain>/        # PASS 200
# FAIL: 5xx/000 -> app container not healthy; check `kubectl logs ... -c app`.

# 4.6 ATTENDED ONLY, the real end-to-end proof: say "Alexa, ask <skill invocation> to play <something>" to an
#     Echo (the invocation name is in the operator's Alexa app; not committed). PASS: audio starts within ~10 s
#     and §4.4 shows no new error. FAIL: Echo says it cannot reach the skill, or silence, or the session ends at
#     once (the new session-end log line in §4.4 names the reason). A failing 4.6 with green 4.1-4.5 still = FAIL.
#     §4.6 is the ONLY proof that this skill digest is compatible with MA server 2.10.12 (the changelog-free beta was
#     never tested against that server by us); 4.1-4.5 prove the container and routes, not the MA<->skill handshake.
```

If §4.6 cannot be run (unattended window): record "end-to-end voice check pending" on the plan and have the
operator test next morning; keep §5 ready for that day.

## 5. Rollback

The old digest stays pullable from GHCR; nothing forward-only happens (no migration, no PVC write by the skill).

```bash
git revert <sha-of-the-bump-commit>        # restores tag: latest@sha256:ad7ec55a51d9...
git commit --only ... ; git log -1 --format=%s ; git push origin main
```
Confirm: re-run §4.1 with the OLD digest `ad7ec55a51d9...` as the expected skill imageID, and §4.2/4.5. If Flux's
`upgrade.remediation: rollback` fires on a failed Helm upgrade first, the cluster is already back; then revert
the git commit anyway so git and cluster agree (otherwise the next reconcile retries the bad digest). If the old digest
were ever deleted from GHCR, the fallback is to disable the `alexa-skill` container block (the MA server works
without it; Alexa voice only) and escalate - do NOT rebuild the third-party image.
Also: if `music-assistant-config` fails to attach after the roll (Multi-Attach), follow
`docs/sops/longhorn-rwo-multi-attach.md`; restore from the nightly Longhorn backup only as a last resort.

## 6. Interference notes

- **Same pod as the MA server**: this plan briefly takes down MA (UI + streams) too; it is also the reason
  it cannot overlap any plan touching `home-automation` or Home Assistant's MA integration.
- **Public edge**: only exercised, not changed; do not run in the slot of `envoy-gateway-1.10.0` (edge restart
  makes §4.3 unattributable).
- **Monitoring**: §4.1 can also be read from Prometheus; do not run with `kube-prometheus-stack-93.3.0`.
- **Storage**: re-attach of `volume/music-assistant-config`; not the slot of `longhorn-1.13.0` (sun-attended:2026-11-15).
- **Floating-tag caveat (repo correction, not this plan's scope)**: `latest@sha256` bumps carry no version signal;
  once upstream publishes numbered tags, switch the pin to `0.0.39-beta`-style tags so Renovate can classify them.
  Until then every digest bump is a PLAN-lane item, as here.
- Fits one nightly or attended slot (~25 min incl. checks). Needs a human only for §4.6.

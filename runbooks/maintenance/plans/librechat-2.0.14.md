---
plan_id: librechat-2.0.14
component: librechat
pr: null                              # No Renovate PR. Dispatched by the nightly window 2026-09-28
                                      # Step 0.5 from coverage.py needs_plan_groups (G3: release
                                      # notes unavailable). Upstream publishes NO GitHub release for
                                      # chart 2.0.4..2.0.14 (last chart-* release is chart-2.0.3),
                                      # which is why G3 found nothing — §1 uses the chart tarball
                                      # diff + the helm/librechat commit log instead.
kind: chart
current: "2.0.7"                      # live-verified 2026-09-28: HR status "librechat@2.0.7",
                                      # flux_resource_info revision="2.0.7", image v0.8.7
target: "2.0.14"
update_type: patch
risk: low                             # With our values the rendered diff is 4 ConfigMap keys removed
                                      # (all SHADOWED by the Secret, proven by hash in §2.3), one
                                      # envFrom `optional: true -> false` (Secret exists), and
                                      # label/checksum churn. Every image is byte-identical. The
                                      # hold was a G3 no-notes hold, not a software risk.
est_duration_min: 25                  # ~10 active (pre-checks, push, reconcile) + ~2 min Recreate gap
                                      # of the librechat pod + ~10 verification.
needs_reboot: false
touches:
  namespaces: [ai]
  resources:
    - helmrelease/librechat           # chart.spec.version edit (the ONLY git change)
    - deployment/librechat-librechat  # pod-template labels + checksum/configEnv change -> ONE Recreate roll
    - configmap/librechat-librechat-configenv   # loses CREDS_KEY/CREDS_IV/JWT_SECRET/JWT_REFRESH_SECRET (shadowed today)
    - secret/librechat-credentials-env          # NOT edited; becomes a HARD dependency (optional: false)
    - pvc/librechat-librechat-images  # NOT edited; RWO Longhorn, detached/re-attached by the Recreate roll
    - service/librechat-librechat     # NOT edited; label churn only; backend of httproute/librechat
    - serviceaccount/librechat-librechat        # label churn only
    - httproute/librechat             # NOT edited; public hostname 503s for the ~1-2 min roll only
    - deployment/librechat-mongodb    # NOT changed by the render (asserted in §4.5 — pod must NOT roll)
    - statefulset/librechat-meilisearch         # NOT changed by the render (asserted in §4.5)
  shared: []                          # envoy-external not reconfigured (route unchanged); Authentik
                                      # provider/blueprint untouched (OIDC is exercised, not changed);
                                      # Ollama host only read. Prometheus is READ in §4 (see conflicts).
depends_on: []
conflicts_with: [helm-drift-detection, flux-reconciler-impersonation, flux-fleet-0.60.0, kube-prometheus-stack-91.4.1]
                                      # helm-drift-detection: adds spec.driftDetection to every HR incl.
                                      #   helmrelease/librechat — two writers, one object, one reconcile.
                                      # flux-reconciler-impersonation: changes the identity kustomize-/
                                      #   helm-controller apply ai/ with (exclusive in its own right);
                                      #   a same-night failed upgrade here would be unattributable.
                                      # kube-prometheus-stack-91.4.1: §4.4/§4.6 read flux_resource_info
                                      #   and the LibreChat* alerts through Prometheus — the window's
                                      #   instrument (executed; kept so a re-run/revert is serialized).
exclusive: false
security_ref: null
capability_change: false              # app image stays v0.8.7 (pinned); effective env identical (§2.3)
rollback_class: git-revert            # nothing forward-only: no image change, no DB migration, mongo
                                      # and meilisearch are not re-rendered, no PV/volumeHandle moves.
finding_refs: [F-fbe854a6]            # "librechat: chart 2.0.7 → 2.0.14 (patch)"
status: vetted    # plan-reviewer 2026-09-28 (F-2c849d1e): needs-fix (§4.4(c) browser gate unrunnable unattended) -> fixed -> delta re-review ready-for-go. AUTO-NIGHT + risk low => SD-10 pre-approved for the nightly.
review: ready-for-go@2026-09-28
window: null
premises:
  - id: hr-chart-still-2.0.7
    why: >-
      current and the rollback target assume chart 2.0.7 is what is installed. If a Step 0
      direct-bump or a hand edit already moved it, this plan is stale.
    run: kubectl get helmrelease -n ai librechat -o jsonpath='{.status.history[0].chartVersion}'
    expect_exact: "2.0.7"
  - id: manifest-chart-pin-2.0.7
    why: >-
      §3 edits exactly this line; if it is gone or duplicated the sed in §3 is wrong.
    run: >-
      grep -c '^      version: "2.0.7"$' kubernetes/apps/ai/librechat/app/helmrelease.yaml
    expect_exact: "1"
  - id: app-image-pin-present
    why: >-
      LOAD-BEARING. Chart 2.0.14 sets appVersion v0.8.8-rc4 and the chart's image.tag default
      is "" -> .Chart.AppVersion. Without our explicit `image.tag: "v0.8.7"` this chart bump
      silently becomes an app upgrade to a RELEASE CANDIDATE. The whole low-risk verdict rests on it.
    run: >-
      grep -c '^      tag: "v0.8.7"$' kubernetes/apps/ai/librechat/app/helmrelease.yaml
    expect_exact: "1"
  - id: live-app-image-v0.8.7
    why: >-
      The §4.2 contents gate compares against v0.8.7; if the live image already moved the
      baseline is wrong.
    run: kubectl get deploy -n ai librechat-librechat -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: registry.librechat.ai/danny-avila/librechat:v0.8.7
  - id: secret-carries-credentials
    why: >-
      2.0.14 drops the published CREDS_KEY/CREDS_IV/JWT_SECRET/JWT_REFRESH_SECRET defaults from
      the ConfigMap and makes the Secret non-optional. Safe ONLY if the Secret holds all four
      (plus MEILI_MASTER_KEY/MONGO_URI). Prints key NAMES only, never values.
    run: kubectl get secret -n ai librechat-credentials-env -o go-template='{{range $k,$v := .data}}{{$k}} {{end}}'
    expect_matches: "CREDS_IV CREDS_KEY JWT_REFRESH_SECRET JWT_SECRET MEILI_MASTER_KEY MONGO_URI"
  - id: envfrom-secret-after-configmap
    why: >-
      The Secret wins a key collision only because it is listed AFTER the ConfigMap in envFrom.
      That ordering is why the removed ConfigMap defaults are dead values today.
    run: kubectl get deploy -n ai librechat-librechat -o jsonpath='{.spec.template.spec.containers[0].envFrom}'
    expect_matches: 'configMapRef.*librechat-librechat-configenv.*secretRef.*librechat-credentials-env'
  - id: hr-ready
    why: A reconcile already failing would make the §4.1 gate unattributable.
    run: kubectl get helmrelease -n ai librechat -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: "True"
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/longhorn-rwo-multi-attach.md
  - docs/sops/verification-contents-not-shape.md
generated: "2026-09-28"
---

# librechat chart 2.0.7 -> 2.0.14

## 1. Summary & why held

**Change:** `spec.chart.spec.version` of `helmrelease/librechat` (ns `ai`) from `2.0.7` to
`2.0.14`. Chart source: `HelmRepository/flux-system/librechat`,
`oci://ghcr.io/danny-avila/librechat-chart` (the chart lives in `helm/librechat` of the
upstream LibreChat monorepo). No other file changes.

**Why held:** G3 could not find release notes. That is accurate, not a tooling fault:
upstream stopped cutting `chart-*` GitHub releases after `chart-2.0.3` (2026-05-13); chart
2.0.4..2.0.14 shipped only as OCI artifacts. The evidence below replaces the notes.

**Evidence (primary sources, gathered 2026-09-28):**

- Pulled both tarballs (`helm pull ... --version 2.0.7` digest `sha256:7ef07cc1...`, `2.0.14`
  digest `sha256:5d2cbc2b...`) and diffed them. Subchart versions are IDENTICAL
  (mongodb 16.5.45, meilisearch 0.11.0, redis 24.1.3, librechat-rag-api 0.5.3; rag-api 0.5.3 in 2.0.14
  newly bundles a nested postgresql subchart, disabled for us and absent from the render diff).
- `helm/librechat` commit log 2026-06-24..2026-09-24; the relevant PRs:
  - **#14680 "Remove Published Credential Defaults"** (merged 2026-08-07): "replaced published
    credential defaults with generated temporary credentials ... Remove insecure defaults
    from environment examples and Helm values." -> chart `values.yaml` no longer sets
    `librechat.configEnv.CREDS_KEY/CREDS_IV/JWT_SECRET/JWT_REFRESH_SECRET`.
  - **#16175 "Require Named Helm Credential Secrets"** (merged 2026-09-22): "Require a named
    Secret to exist (`optional: false`). Kubernetes blocks container startup if it is missing."
    Upstream's own risk note: "A configured but missing Secret now blocks startup
    intentionally ... Existing Secrets and credential values are not modified."
  - #13872 / #14207: opt-in Langfuse fanout gateway (`langfuseFanout.enabled: false` default —
    renders nothing for us).
  - Chart.yaml: `appVersion: v0.8.7 -> v0.8.8-rc4` (a pre-release).
- **Rendered with OUR values** (`helm template librechat <chart> -n ai -f <spec.values>` for
  both versions, `diff`): the complete diff is
  1. `configmap/librechat-librechat-configenv` loses `CREDS_IV`, `CREDS_KEY`,
     `JWT_REFRESH_SECRET`, `JWT_SECRET` (the published chart defaults);
  2. `deployment/librechat-librechat` envFrom `secretRef librechat-credentials-env`:
     `optional: true -> false`;
  3. `checksum/configEnv` annotation changes -> the librechat pod rolls once;
  4. `helm.sh/chart` and `app.kubernetes.io/version` labels on the librechat
     ServiceAccount/Service/Deployment (the version label will read `v0.8.8-rc4` although
     the pod runs v0.8.7 — cosmetic; NOT a selector label, selectors are unchanged).
  Every rendered `image:` is identical; mongodb and meilisearch objects do not appear in the
  diff at all.

**Why the credential change is a no-op for us (measured live, hashes only):** the Secret
`librechat-credentials-env` already carries all four keys and is listed AFTER the ConfigMap in
envFrom, so it wins. sha256 prefixes on 2026-09-28: pod env == Secret for all four keys; the
ConfigMap value == the published chart default and != the pod value for all four. The keys the
chart is deleting have been dead values since the Secret was introduced. (Worst case if this
were wrong: a JWT change logs every user out; a CREDS change breaks decryption of stored user
API keys — `db.keys` holds 0 documents today, so blast radius would be a logout.)

**The trap that must be respected:** chart 2.0.14's appVersion is `v0.8.8-rc4`, and
`image.tag: ""` defaults to it. Our HelmRelease pins `image.tag: "v0.8.7"` (the comment above it
predicted exactly this for 2.0.8). The pin is what keeps this a chart-only change. Do not remove
or "tidy" it in the same commit. The app upgrade to v0.8.8 is a separate decision, to take once
upstream publishes a v0.8.8 release (not an -rc).

## 2. Pre-checks

Run from the repo root on the Mac mini (zsh).

2.1 Premises (fail closed):
```bash
.venv/bin/python3 runbooks/plan-premises.py librechat-2.0.14
```
PASS = all 7 premises OK. Any FAIL -> stop, the plan is stale.

2.2 Target exists and is the artifact reviewed here:
```bash
helm show chart oci://ghcr.io/danny-avila/librechat-chart/librechat --version 2.0.14 2>&1 | grep -E '^(version|appVersion):'
```
PASS = `appVersion: v0.8.8-rc4` and `version: 2.0.14`. (If appVersion differs, the tag was
re-pushed; re-run the §1 render diff before continuing.)

2.3 Credentials baseline (hashes only; never print values). Record the output:
```bash
h(){ tr -d '\n' | shasum -a 256 | cut -c1-12; }
for k in CREDS_KEY CREDS_IV JWT_SECRET JWT_REFRESH_SECRET MEILI_MASTER_KEY MONGO_URI; do
  p=$(kubectl exec -n ai deploy/librechat-librechat -- printenv $k | h)
  s=$(kubectl get secret -n ai librechat-credentials-env -o "jsonpath={.data.$k}" | base64 -d | h)
  [ "$p" = "$s" ] && echo "$k OK" || echo "$k MISMATCH pod=$p secret=$s"
done
```
PASS = six `OK` lines. (Measured 2026-09-28: six OK. The gate can fail: the ConfigMap's copy
of each key hashes differently from the Secret's, so a pod reading the ConfigMap prints
MISMATCH.)

2.4 Data baseline (read-only mongosh; the password is read from the file inside the pod):
```bash
kubectl exec -n ai deploy/librechat-mongodb -c mongodb -- sh -c 'mongosh --quiet -u librechat -p "$(cat $MONGODB_EXTRA_PASSWORDS_FILE)" --authenticationDatabase LibreChat LibreChat --eval "JSON.stringify({u:db.users.countDocuments(),c:db.conversations.countDocuments(),m:db.messages.countDocuments()})"'
```
Record the JSON (2026-09-28: `{"u":1,"c":1,"m":6}`).

2.5 Untouched-pod baseline (for §4.5):
```bash
kubectl get pod -n ai -l 'app.kubernetes.io/instance=librechat' -o custom-columns='NAME:.metadata.name,UID:.metadata.uid' --no-headers | sort > /tmp/librechat-pods-before.txt; cat /tmp/librechat-pods-before.txt
```

2.6 Backups fresh (no DB change is expected, but the images PVC re-attaches):
```bash
for v in $(kubectl get pvc -n ai librechat-librechat-images librechat-mongodb librechat-meilisearch -o jsonpath='{.items[*].spec.volumeName}'); do kubectl get volumes.longhorn.io -n storage $v -o jsonpath='{.metadata.name} {.status.lastBackupAt} {.status.robustness}{"\n"}'; done
```
PASS = every volume `healthy` and lastBackupAt within 48h (lastBackupAt can lag one cycle —
cross-check the newest Completed Backup CR per `docs/sops/backup.md` before calling it stale).

2.7 No in-flight reconcile:
```bash
flux get helmreleases -n ai librechat; flux get kustomizations -n ai librechat
```
PASS = both `Ready True`, not suspended.

## 3. Steps

3.1 Edit the chart version (dry-tested on a scratch copy with BSD sed 2026-09-28):
```bash
sed -i '' -E 's/^([[:space:]]*version: )"2\.0\.7"$/\1"2.0.14"/' kubernetes/apps/ai/librechat/app/helmrelease.yaml
git diff kubernetes/apps/ai/librechat/app/helmrelease.yaml
```
Expected diff — exactly one line:
```
-      version: "2.0.7"
+      version: "2.0.14"
```
Confirm `image.tag: "v0.8.7"`, `updateStrategy: Recreate` and `ingress.enabled: false` are
still present and untouched (`grep -n -E 'tag: "v0.8.7"|type: Recreate|enabled: false' ...`).

3.2 Validate:
```bash
kubeconform -summary -ignore-missing-schemas kubernetes/apps/ai/librechat
```

3.3 Commit and push (shared worktree rules):
```bash
printf 'feat(librechat): chart 2.0.7 -> 2.0.14 (plan librechat-2.0.14)\n\nChart-only: image stays pinned at v0.8.7 (2.0.14 appVersion is v0.8.8-rc4).\nRender diff: 4 shadowed credential defaults leave the ConfigMap, envFrom\nSecret becomes optional:false. mongodb/meilisearch not re-rendered.\n\nCo-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>\n' > /tmp/librechat-msg.txt
git commit --only kubernetes/apps/ai/librechat/app/helmrelease.yaml -F /tmp/librechat-msg.txt
git log -1 --format=%s     # must be the subject above; amend before push if not
git show --stat HEAD       # exactly one file
git push
```

3.4 Let the Flux webhook reconcile (no manual `flux reconcile` needed). Watch:
```bash
kubectl get pods -n ai -l app.kubernetes.io/name=librechat-librechat -o wide
```
Expected: old pod terminates, new pod starts (Recreate; ~1-2 min gap). If the new pod sits in
`ContainerCreating` with a `Multi-Attach` event, the strategy did not render — go to §5.

## 4. Verification

4.1 HelmRelease on the new chart:
```bash
kubectl get helmrelease -n ai librechat -o jsonpath='{.status.history[0].chartVersion} {.status.conditions[?(@.type=="Ready")].status}{"\n"}'
```
PASS = `2.0.14 True`. Fails with `2.0.7 True` if the upgrade was remediated back, or `False`.

4.2 CONTENTS ASSERTION: the app did NOT slip to the release candidate — measured by the
running build's own report, compared to the §1 baseline (commit `9e74cc0`, branch `v0.8.7`):
```bash
kubectl port-forward -n ai svc/librechat-librechat 13080:3080 >/dev/null 2>&1 & PF=$!; sleep 3
curl -s localhost:13080/api/config | python3 -c "import sys,json; b=json.load(sys.stdin)['buildInfo']; print('BUILD_OK' if b.get('branch')=='v0.8.7' and b.get('commitShort')=='9e74cc0' else 'BUILD_WRONG %s' % b)"
kill $PF 2>/dev/null
```
PASS = `BUILD_OK`. If the pin were lost the rc4 image reports a different branch/commit and
this prints `BUILD_WRONG`; an unreachable app raises a JSON error (no `BUILD_OK`) — both fail.
Also: `kubectl get deploy -n ai librechat-librechat -o jsonpath='{.spec.template.spec.containers[0].image}'`
must print `registry.librechat.ai/danny-avila/librechat:v0.8.7`.

4.3 CONTENTS ASSERTION: the pod's effective credentials are unchanged — re-run the §2.3 loop
against the NEW pod. PASS = six `OK` lines, identical to the pre-check. This is the property
#14680/#16175 could silently break (JWT drift = everyone logged out; CREDS drift = stored keys
undecryptable) while the pod is perfectly Ready. Additionally assert the ConfigMap no longer
carries the published defaults:
```bash
kubectl get cm -n ai librechat-librechat-configenv -o go-template='{{range $k,$v := .data}}{{$k}} {{end}}' | tr ' ' '\n' | grep -c -E '^(CREDS_KEY|CREDS_IV|JWT_SECRET|JWT_REFRESH_SECRET)$'
```
PASS = `0` (it prints `4` on 2.0.7 — measured).

4.4 CONTENTS ASSERTION: data and login path intact —
(a) re-run §2.4; PASS = counts >= the recorded baseline and `u >= 1` (a floor; an empty or
unauthenticated DB returns 0 or an auth error).
(b) OIDC wiring renders:
```bash
kubectl port-forward -n ai svc/librechat-librechat 13080:3080 >/dev/null 2>&1 & PF=$!; sleep 3
curl -s localhost:13080/api/config | python3 -c "import sys,json; d=json.load(sys.stdin); print('OIDC_OK' if d.get('openidLoginEnabled') is True and d.get('registrationEnabled') is False else 'OIDC_WRONG')"
curl -s -o /dev/null -w '%{http_code}\n' localhost:13080/oauth/openid
kill $PF 2>/dev/null
```
PASS = `OIDC_OK` and `302` (a 500 means the openid strategy did not register).
(c) ATTENDED ONLY, NOT a pass criterion. When an operator is present (SD-8), the coordinator in
Chrome (existing session, never passwords): open the LibreChat URL, "Sign in with Authentik", land
in the chat UI, open the existing conversation, send one prompt to the Ollama model and get a
reply. In an unattended nightly run, skip it and record `4.4(c) skipped-unattended` in the run
notes; that is NOT a STOP. The JWT/CREDS property is proven by §4.3 (hash equality) and the OIDC
route by §4.4(b); the Ollama endpoint is not touched by this change.

4.5 Blast-radius assertion — mongodb and meilisearch were NOT restarted:
```bash
kubectl get pod -n ai -l 'app.kubernetes.io/instance=librechat' -o custom-columns='NAME:.metadata.name,UID:.metadata.uid' --no-headers | sort > /tmp/librechat-pods-after.txt
diff /tmp/librechat-pods-before.txt /tmp/librechat-pods-after.txt
```
PASS = the diff shows ONLY the `librechat-librechat-*` line changing; `librechat-mongodb-*` and
`librechat-meilisearch-0` UIDs identical. Any change there means the render diff in §1 was not
what got applied -> investigate before closing.

4.6 Instruments (Prometheus, port-forward `svc/kube-prometheus-stack-prometheus 9090`). The verdict rests on the two positive controls (flux_resource_info revision="2.0.14" == 1, replicas_available == 1); the three "not firing" alert controls are informational (absence, no known-bad demonstration):

CONTROL: metric flux_resource_info — `flux_resource_info{kind="HelmRelease",name="librechat",revision="2.0.14",ready="True"}` returns exactly 1 series (returns 0 before the change — measured 2026-09-28, the live series carries `revision="2.0.7"`).

CONTROL: metric kube_deployment_status_replicas_available — `{namespace="ai",deployment="librechat-librechat"}` == 1 at T+10 min.

CONTROL: alertname LibreChatPodNotReady — not firing at T+10 min (`ALERTS{alertname="LibreChatPodNotReady"}` empty; the Recreate gap is under its 5m `for:`).

CONTROL: alertname LibreChatPodCrashLooping — not firing at T+15 min.

CONTROL: alertname FluxResourceNotReady — no firing instance with `name="librechat"` at T+20 min.

## 5. Rollback

Nothing in this change is forward-only (no image change, no schema migration, mongodb and
meilisearch untouched, no PV/volumeHandle change), so a git revert is the complete procedure.

5.1 Trigger: any §4 gate fails, or the pod does not become Ready within 10 min.

5.2 Revert:
```bash
git revert --no-edit <sha-of-3.3-commit>
git log -1 --format=%s    # confirm it is the revert
git push
```

5.3 If the HelmRelease is stuck `False` after an exhausted remediation (`upgrade.remediation.retries: 1`), the revert alone may not re-trigger; then (SOP-sanctioned recovery, not routine):
```bash
flux reconcile helmrelease -n ai librechat --with-source
```

5.4 If the pod is stuck on `Multi-Attach` (strategy lost), check the rendered strategy
`kubectl get deploy -n ai librechat-librechat -o jsonpath='{.spec.strategy.type}'` (must be
`Recreate`); per `docs/sops/longhorn-rwo-multi-attach.md` the stuck pod clears once the old pod
is gone — do not delete PVCs.

5.5 Confirm rollback: `status.history[0].chartVersion` = `2.0.7`, Ready `True`; re-run §2.3
(six OK) and §4.2 (BUILD_OK); `flux_resource_info{name="librechat"}` shows `revision="2.0.7"`.

## 6. Interference notes

- **Only the librechat pod rolls** (~1-2 min public outage of the chat UI on envoy-external).
  MongoDB and Meilisearch are not re-rendered; §4.5 proves it. No Authentik, Gateway, DNS or
  storage-class change; the Ollama host on the Mac mini is only called by the §4.4(c) prompt.
- **Conflicts:** `helm-drift-detection` (second writer on `helmrelease/librechat`),
  `flux-reconciler-impersonation` (changes how ai/ is applied), `kube-prometheus-stack-91.4.1`
  (§4.6 reads Prometheus). Reciprocity is NOT yet declared on those plans' side — the vetting
  pass should add `librechat-2.0.14` to their `conflicts_with`.
- **Do not bundle the app upgrade.** `v0.8.8-rc4` is a pre-release; LibreChat v0.8.8 also brings
  #14680's credential-generation/drift-detection startup code and #15324's generation protocol
  change. That is a separate plan once a final v0.8.8 exists.
- **Stale comment, harmless:** the `image:` comment in `helmrelease.yaml` still says "Chart 2.0.7
  already defaults to appVersion v0.8.7 ... this is a no-op today". After this plan the pin is
  load-bearing, not a no-op. Worth rewording in a later non-window commit; deliberately not
  part of this diff so §3.1 stays a one-line change.
- **Source ownership (F-97411988, separate):** upstream moved its repo to the `LibreChat-AI` org
  (commit f13b0eaef4, 2026-09-24, after 2.0.14 was published), but chart 2.0.14 exists only at
  `ghcr.io/danny-avila/librechat-chart` (`ghcr.io/librechat-ai/librechat-chart/librechat:2.0.14`
  -> not found, checked 2026-09-28). Do not repoint the HelmRepository in this window.
- **Alerts:** no silence needed — the Recreate gap is shorter than `LibreChatPodNotReady`'s 5m
  `for:`, and a new pod starts with restart count 0 (`LibreChatPodRestarted` stays quiet).

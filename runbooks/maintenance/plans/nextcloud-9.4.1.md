---
plan_id: nextcloud-9.4.1
component: nextcloud-exporter
pr: null                              # no Renovate PR. REWRITTEN 2026-10-23 as EXPORTER-ONLY. The plan_id keeps the
                                      # historic name (plans README: refresh, do not replace; nextcloud-mcp-0.200.2
                                      # still references it); the chart 9.4.1 / server 35.0.2 leg it once closed out
                                      # was executed on 2026-10-23 (helm revision 58, see section 1).
kind: image
current: "xperimental/nextcloud-exporter 0.9.1 (helmrelease/nextcloud values.metrics.image.tag, tag only, no digest pin in git)"
target: "xperimental/nextcloud-exporter 0.9.2 (single tag line)"
update_type: patch
risk: low                             # one stateless 1-replica Deployment (nextcloud-metrics), no PVC, RollingUpdate;
                                      # render diff measured 2026-10-23: exactly 1 image line, nothing else.
est_duration_min: 15                  # edit + render gate ~5, rollout ~3, verification ~5, slack ~2
needs_reboot: false
touches:
  namespaces: [office]
  resources:
    - helmrelease/nextcloud                     # values.metrics.image.tag 0.9.1 -> 0.9.2 (one line). A values change makes
                                                # helm-controller run a helm upgrade of the whole release (revision 58 -> 59),
                                                # but the render diff proves only the metrics Deployment changes.
    - deployment/nextcloud-metrics              # rolled (RollingUpdate, 1 replica, no PVC)
  shared:
    - monitoring                                # Prometheus is the verification instrument and the exporter's consumer
                                                # (ServiceMonitor monitoring/nextcloud-metrics)
depends_on: []                                  # chart 9.4.1 / server 35.0.2 are live (nextcloud-fleet-35.0.1 executed
                                                # 2026-10-23 and its file is retired)
conflicts_with:
  - redis-fleet-8.10.2                          # restarts nextcloud-redis (and nextcloud): nextcloud_up reads 0 mid-
                                                # verification, a false FAIL. Holds sat-attended:2026-10-24: do NOT take
                                                # the nightly run of that night (the 03:30 run on 2026-10-24 or 10-25 is
                                                # adjacent to the sat window); pick another night.
  - flux-oci-chart-sources                      # replaces chart.spec on this HelmRelease (premise chart-source reads nothing)
  - helm-drift-detection                        # patches helmrelease/nextcloud
  - bitnamilegacy-exit-nextcloud-db             # same helmrelease.yaml (blocked; kept for safety)
  - nextcloud-whiteboard-2.1.2                  # same Kustomization office/nextcloud (whiteboard-proxy.yaml); one office change per night
  - nextcloud-mcp-0.201.2                       # same office namespace, scrapes nothing of ours but a concurrent roll muddies
                                                # "what restarted"; low value, serialize anyway
  # No kube-prometheus-stack plan is open (92.x retired 2026-10-23). Section 4 reads Prometheus: if one is ever planned
  # for the same night, add it here and serialize.
exclusive: false
security_ref: F-4cfb8d73              # security driver, tracked on the record
capability_change: false              # Go runtime/deps bump + a free-space nil fix, same metrics, same ports
rollback_class: git-revert            # stateless exporter tag; no data, no schema
finding_refs: [F-b436cd6f, F-4cfb8d73, F-a6233ebd]
                                      # F-b436cd6f version/monitor exporter 0.9.1 -> 0.9.2
                                      # F-4cfb8d73 security driver (detail on the record)
                                      # F-a6233ebd AR-029 acceptance of 0.9.1 (premise "no newer tag" is now false)
review: ready-for-go@2026-10-23      # delta plan-reviewer 2026-10-23: ready-for-go
status: vetted
window: "nightly:2026-10-28"          # nightly 03:30, unattended, SD-10 eligible (low risk, capability_change false, git-revert);
                                      # NOT the night around 2026-10-24 (redis-fleet-8.10.2)
review_note: "2026-10-23 rewrite per independent review: exporter-only, nightly, digest-pin premise fixed."
premises:
  # Runner grammar (plan-premises.py): kubectl/flux/git/helm READ verbs + bare text filters (no gh/curl).
  - id: live-chart-is-9.4.1
    why: "The chart leg is DONE; this plan must not be the one that finds it half-applied."
    run: kubectl get helmrelease -n office nextcloud -o jsonpath='{.spec.chart.spec.version}'
    expect_exact: "9.4.1"
  - id: live-server-image-is-35.0.2
    why: >-
      Server leg done. The live image is DIGEST-PINNED (docker.io/nextcloud:35.0.2@sha256:...),
      so an exact "docker.io/nextcloud:35.0.2" can never match (the previous draft's premise
      was wrong in exactly that way); match tag with an optional digest suffix.
    run: kubectl get deploy -n office nextcloud -o jsonpath='{.spec.template.spec.containers[?(@.name=="nextcloud")].image}'
    expect_matches: '^docker\.io/nextcloud:35\.0\.2(@sha256:[0-9a-f]{64})?$'
  - id: helmrelease-ready
    why: A failed/in-flight helm upgrade must not be stacked on.
    run: kubectl get helmrelease -n office nextcloud -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: "True"
  - id: exporter-running-0.9.1
    why: "`current:` claim. The Deployment pins the TAG (git has no digest pin for the exporter); the digest only appears in the pod's imageID."
    run: kubectl get deploy -n office nextcloud-metrics -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: "docker.io/xperimental/nextcloud-exporter:0.9.1"
  - id: exporter-one-ready-replica
    why: The exporter must be scraping before we change it, or section 4 compares against nothing.
    run: kubectl get deploy -n office nextcloud-metrics -o jsonpath='{.status.readyReplicas}'
    expect_exact: "1"
  - id: git-pin-is-0.9.1-exactly-once
    why: "The sed in section 3 is anchored on this line; 0 means it moved/was edited, 2 means a second metrics block."
    run: "grep -c '^        tag: 0\\.9\\.1$' kubernetes/apps/office/nextcloud/app/helmrelease.yaml"
    expect_exact: "1"
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/maintenance-windows.md
  - docs/sops/verification-contents-not-shape.md
generated: "2026-10-19"
---

# nextcloud-exporter 0.9.1 -> 0.9.2 (exporter-only; the chart 9.4.1 / Nextcloud 35.0.2 leg already executed)

## 1) Summary & why held

**Scope after the 2026-10-23 rewrite: ONE values line.** The first draft of this plan closed
out a chart 9.3.0 -> 9.4.1 leg that rode `nextcloud-fleet-35.0.1`. That plan has executed
(live, re-measured 2026-10-23: `helm history` revision 58 `nextcloud-9.4.1` / app `35.0.2`
"Upgrade complete", HelmRelease `9.4.1` Ready, server image
`docker.io/nextcloud:35.0.2@sha256:3f05f4d5...`), so everything chart- and major-related is
gone from this file. What remains is the stateless exporter tag.

**Why held.** The `*nextcloud*` deny rule matches the exporter because it is pinned inside
`helmrelease/nextcloud`. For this leg the rule's reasons (occ migrations, Mail custom_app,
stuck maintenance) do not apply: only `deployment/nextcloud-metrics` rolls (stateless, no PVC,
RollingUpdate) and the render diff below proves `deployment/nextcloud` is untouched. **The hold
is a false positive for the exporter**; it is planned so the window agent, not the auto-updater,
lands it.

**Upstream evidence (xperimental/nextcloud-exporter v0.9.2, 2026-10-18, not a prerelease).**
CHANGELOG verbatim: *"Changed - Updated Go runtime and dependencies. Fixed - Unknown free space
no longer reported as zero free space."* Only behaviour change: `nextcloud_free_space_bytes`
is **omitted** (instead of emitted as 0) when the serverinfo payload carries no `freespace`.
Live now (0.9.1 on Nextcloud 35.0.2): the series is present and non-zero
(25144634966016), so it keeps arriving. No repo PrometheusRule references any `nextcloud_*`
series (only the ServiceMonitor). Docker Hub tag `0.9.2` digest (Hub API, 2026-10-23, matches
the 2026-10-19 measurement): `sha256:512ddd1f1e1ea0ea7b4f0821c9740bcefa5fc15deb57fb9cd05dfb68e7e8390d`.

**Security.** Security driver, tracked as F-4cfb8d73; bumping is the only remedy (bump-never-rebuild). F-a6233ebd (AR-029) assumed "no newer tag" and
is now stale; the sweep will re-rate it. Detail stays on the records.

**Repo corrections (NOT done by this planner):** (1) `nextcloud-fleet-34.0.5` is a contingency
for a 34 hold that no longer exists (35.0.2 is live) and should be retired; (2) the old draft's
`live-server-image-is-35.0.2` premise could never pass against a digest-pinned image.

## 2) Pre-checks

Run from `/Users/mu/code/cberg-home-nextgen`, zsh, each block one Bash call.

```bash
.venv/bin/python3 runbooks/plan-premises.py nextcloud-9.4.1        # all PASS, else STOP
#   HOW IT FAILS: git-pin-is-0.9.1-exactly-once reads 0 => someone already bumped it (or Renovate
#   did): re-read helmrelease.yaml, then there may be nothing to do. exporter-running-0.9.1 reads
#   :0.9.2 => already executed.
git fetch origin main && git merge --ff-only origin/main
```

```bash
# BASELINES + the verification instrument (section 4 uses the same script)
kubectl get deploy -n office nextcloud -o jsonpath='{.metadata.generation}{"\n"}'   # record (66 on 2026-10-23): gate 2
kubectl get pods -n office -l app.kubernetes.io/component=metrics -o jsonpath='{.items[*].status.containerStatuses[*].imageID}{"\n"}'
#   EXPECT docker.io/xperimental/nextcloud-exporter@sha256:3e90a38976516444d05f5f6758e5d572ca559b69ad3005ec4029786e9daf9129 (0.9.1)
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 19090:9090 >/dev/null 2>&1 & PF=$!
sleep 3
mkdir -p "$TMPDIR" && cat > "$TMPDIR/nx-gate.py" <<'PY'
import sys, json, urllib.parse, urllib.request, subprocess
WANT = sys.argv[1]                                   # exporter version expected, e.g. 0.9.2
def q(e):
    u = "http://localhost:19090/api/v1/query?query=" + urllib.parse.quote(e)
    return json.load(urllib.request.urlopen(u, timeout=20))["data"]["result"]
pod = subprocess.check_output(["kubectl","get","pods","-n","office","-l","app.kubernetes.io/component=metrics",
      "-o","jsonpath={.items[*].metadata.name}"], text=True).split()
bad = []
def need(name, ok, detail):
    print(("PASS " if ok else "FAIL ") + name + " " + detail)
    if not ok: bad.append(name)
r = q("nextcloud_exporter_info")
need("exporter_info", len(r)==1 and r[0]["metric"].get("version")==WANT and [r[0]["metric"].get("pod")]==pod,
     f"series={len(r)} version={[x['metric'].get('version') for x in r]} pods_now={pod}")
r = q("nextcloud_up");          need("nextcloud_up", len(r)==1 and r[0]["value"][1]=="1", f"{[x['value'][1] for x in r]}")
r = q("nextcloud_system_info"); need("system_info", len(r)==1 and r[0]["metric"].get("version","").startswith("35.0.2"), f"{[x['metric'].get('version') for x in r]}")
r = q("nextcloud_free_space_bytes"); need("free_space", len(r)==1 and float(r[0]["value"][1])>0, f"{[x['value'][1] for x in r]}")
r = q('up{service="nextcloud-metrics"}'); need("scrape_up", len(r)==1 and r[0]["value"][1]=="1", f"{[x['value'][1] for x in r]}")
r = q("sum(increase(nextcloud_scrape_errors_total[10m]))"); need("scrape_errors", len(r)==1 and float(r[0]["value"][1])==0, f"{[x['value'][1] for x in r]} (empty list = FAIL)")
sys.exit(1 if bad else 0)
PY
python3 -I "$TMPDIR/nx-gate.py" 0.9.1      # MUST print 6x PASS, rc 0 (instrument works, baseline healthy)
python3 -I "$TMPDIR/nx-gate.py" 0.9.2      # MUST print FAIL exporter_info (the gate CAN fail), rc 1
#   Both measured live 2026-10-23: first run 6x PASS rc=0 (pod nextcloud-metrics-5bf8db56f8-*, system_info 35.0.2.2);
#   second run "FAIL exporter_info ... version=['0.9.1']" rc=1. Anything else => the instrument reads nothing: fix BEFORE step 3.
kill $PF 2>/dev/null
```

Abort if: any premise fails, the first gate run is not 6x PASS, or `redis-fleet-8.10.2`
or another `office` change is mid-flight.

## 3) Steps (GitOps)

**3.1 Edit one line.** Dry-tested on a scratch copy 2026-10-23 with macOS BSD sed (the
`-E` form and the anchored pattern are BSD-safe; no `\s`):

```bash
cd /Users/mu/code/cberg-home-nextgen
sed -i '' -E 's|^        tag: 0\.9\.1$|        tag: 0.9.2|' kubernetes/apps/office/nextcloud/app/helmrelease.yaml
git diff -- kubernetes/apps/office/nextcloud/app/helmrelease.yaml
#   EXPECT exactly one hunk (scratch diff, line 561 today):
#   561c561
#   <         tag: 0.9.1
#   ---
#   >         tag: 0.9.2
#   Anything else => STOP, `git checkout -- kubernetes/apps/office/nextcloud/app/helmrelease.yaml`.
```

**3.2 Render-diff gate** (against the LIVE chart 9.4.1, measured 2026-10-23: both renders
1446 lines, exactly one differing line):

```bash
mkdir -p /tmp/nc941-exec && cd /tmp/nc941-exec && rm -rf c && mkdir c
curl -sfL https://github.com/nextcloud/helm/releases/download/nextcloud-9.4.1/nextcloud-9.4.1.tgz | tar xz -C c
grep -E '^version:' c/nextcloud/Chart.yaml                        # EXPECT version: 9.4.1 (empty => STOP)
cd /Users/mu/code/cberg-home-nextgen
git show HEAD:kubernetes/apps/office/nextcloud/app/helmrelease.yaml > /tmp/nc941-exec/hr-head.yaml
.venv/bin/python3 -c "
import yaml
for s,d in (('/tmp/nc941-exec/hr-head.yaml','/tmp/nc941-exec/v-old.yaml'),('kubernetes/apps/office/nextcloud/app/helmrelease.yaml','/tmp/nc941-exec/v-new.yaml')):
    yaml.safe_dump(yaml.safe_load(open(s))['spec']['values'],open(d,'w'))"
for N in old new; do
  helm template nextcloud /tmp/nc941-exec/c/nextcloud -n office -f /tmp/nc941-exec/v-$N.yaml > /tmp/nc941-exec/r-$N.yaml || echo "RENDER $N FAILED"
done
wc -l /tmp/nc941-exec/r-old.yaml /tmp/nc941-exec/r-new.yaml
diff /tmp/nc941-exec/r-old.yaml /tmp/nc941-exec/r-new.yaml
#   EXPECT both ~1446 lines (> 1000 floor) and EXACTLY:
#   1015c1015
#   <           image: "docker.io/xperimental/nextcloud-exporter:0.9.1"
#   >           image: "docker.io/xperimental/nextcloud-exporter:0.9.2"
#   HOW IT FAILS: "RENDER .. FAILED" or a tiny line count => measured nothing: STOP. No diff output => the edit
#   did not land in values: STOP. Any other line => STOP and revert the edit.
```

**3.3 Commit and push** (shared worktree: `--only`, message file first):

```bash
cd /Users/mu/code/cberg-home-nextgen
printf '%s\n\n%s\n\n%s\n' \
  "fix(nextcloud): bump nextcloud-exporter 0.9.1 -> 0.9.2 (plan nextcloud-9.4.1)" \
  "Stateless metrics exporter only; render diff = 1 image line on deployment/nextcloud-metrics." \
  "<the executing agent's Co-Authored-By trailer>" > /tmp/nc941-exec/msg.txt
git commit --only kubernetes/apps/office/nextcloud/app/helmrelease.yaml -F /tmp/nc941-exec/msg.txt
git log -1 --format=%s                 # MUST be the subject above (shared-worktree message-swap race)
git show --stat HEAD                   # MUST list exactly that one file, 1 insertion / 1 deletion
git push origin main
```

**3.4 Let Flux apply it** (webhook; no manual reconcile). Wait up to 10 min:

```bash
kubectl get helmrelease -n office nextcloud -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} {.status.lastAttemptedRevision}{"\n"}'
kubectl -n office rollout status deploy/nextcloud-metrics --timeout=300s
```

## 4) Verification

CONTROL: metric nextcloud_exporter_info
CONTROL: metric nextcloud_up
CONTROL: metric nextcloud_system_info
CONTROL: metric nextcloud_free_space_bytes
CONTROL: metric nextcloud_scrape_errors_total

```bash
# gate 1 — release healthy, server NOT rolled (CONTENTS: the server pod template is unchanged)
helm history nextcloud -n office --max 1        # PASS: revision 59 "deployed ... nextcloud-9.4.1  35.0.2".
                                                # FAIL: "failed"/"pending-upgrade" => section 5
kubectl get deploy -n office nextcloud -o jsonpath='{.metadata.generation}{"\n"}'
#   PASS: equals the section 2 baseline (66). FAIL: incremented => the commit changed the server pod
#   template (contradicts the render gate): STOP, section 5, then investigate.

# gate 2 — the exporter pod runs the 0.9.2 artifact (by DIGEST, not tag)
kubectl get pods -n office -l app.kubernetes.io/component=metrics \
  -o jsonpath='{.items[*].status.containerStatuses[*].imageID}{"\n"}'
#   PASS: exactly one pod, ...nextcloud-exporter@sha256:512ddd1f1e1ea0ea7b4f0821c9740bcefa5fc15deb57fb9cd05dfb68e7e8390d
#   FAIL: the 0.9.1 digest 3e90a389... (rollout did not happen) or two imageIDs (old pod not gone: wait 5 min, re-run once).
#   If the imageID differs from BOTH, re-read the tag digest (`curl -s https://hub.docker.com/v2/repositories/xperimental/nextcloud-exporter/tags/0.9.2`)
#   before judging: the upstream tag may have been re-pushed.

# gate 3 — every series ARRIVES from the new exporter; wait >= 2 scrape intervals (30 s) after rollout,
# and >= 5 min if the old pod's series are still fresh (stale series vanish ~5 min after the old pod terminates)
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 19090:9090 >/dev/null 2>&1 & PF=$!   # own shell: the section 2 forward is gone
sleep 3
python3 -I "$TMPDIR/nx-gate.py" 0.9.2     # recreate the script from section 2 if $TMPDIR was reset
#   PASS: six PASS lines, rc 0. Each term can fail (controls measured 2026-10-23, section 2):
#   exporter_info needs exactly ONE series, version '0.9.2' and the CURRENT pod name (0.9.1 or two series => FAIL);
#   an empty result is never read as success (every check requires len(result)==1);
#   free_space > 0 is a floor: 0 series means the 0.9.2 nil branch fired (Nextcloud stopped sending freespace);
#   report it, it is not a rollback by itself because no rule consumes it. nextcloud_up == 0 IS a rollback trigger.
kill $PF 2>/dev/null
```

Close-out: set `status: executed`. F-b436cd6f / F-4cfb8d73 clear on the next version/security
scan once the pin reads 0.9.2; confirm with `runbooks/policy-cli.py finding list --grep exporter`.

## 5) Rollback

Stateless exporter; `git revert` is the complete procedure (no data, no PVC, no migration):

```bash
cd /Users/mu/code/cberg-home-nextgen
git fetch origin main && git merge --ff-only origin/main
git log --oneline -5 -- kubernetes/apps/office/nextcloud/app/helmrelease.yaml   # find the section 3.3 sha
git revert --no-edit <sha-from-3.3>
git show --stat HEAD                    # exactly helmrelease.yaml, -0.9.2 +0.9.1
git log -1 --format=%s                  # MUST be 'Revert "fix(nextcloud): bump nextcloud-exporter ..."'
git push origin main
kubectl -n office rollout status deploy/nextcloud-metrics --timeout=300s
kubectl get pods -n office -l app.kubernetes.io/component=metrics -o jsonpath='{.items[*].status.containerStatuses[*].imageID}{"\n"}'
#   CONFIRM back to ...@sha256:3e90a38976516444d05f5f6758e5d572ca559b69ad3005ec4029786e9daf9129 (0.9.1),
#   then `python3 -I "$TMPDIR/nx-gate.py" 0.9.1` -> six PASS.
```

Trigger: `nextcloud_up` 0 for > 5 min after rollout, a CrashLoop on `nextcloud-metrics`, or
`helm history` not `deployed`. If the revert does not restore `nextcloud_up 1`, the exporter is
not the cause: look at the server (`docs/sops/` nextcloud) and Mail/occ state.

## 6) Interference notes

- **Slot: any `nightly` except the night adjacent to `redis-fleet-8.10.2` (sat-attended:2026-10-24).**
  That plan restarts `nextcloud-redis`/`nextcloud`, which reads as `nextcloud_up 0`, a false FAIL of
  gate 3. Risk low, `capability_change: false`, `git-revert`: eligible for unattended nightly.
- Prometheus is the verification instrument: no same-night `kube-prometheus-stack` bump (none is
  open today; add it to `conflicts_with` if one is planned).
- Same `helmrelease.yaml` as `nextcloud-mcp-0.201.2`? No (that is the mcp Deployment), but both touch
  `office`; serialize to keep "what restarted" unambiguous.
- No Longhorn, CIFS (`nextcloud-data` untouched), gateway, Authentik or DNS impact. Consumers of
  Nextcloud (openclaw mail/calendar skills, nextcloud-mcp, Homepage) are unaffected by an exporter roll.
- Alert silence: none needed; a real scrape break must stay visible.

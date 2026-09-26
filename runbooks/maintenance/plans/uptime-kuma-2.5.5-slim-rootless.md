---
plan_id: uptime-kuma-2.5.5-slim-rootless
component: uptime-kuma
pr: null                              # no Renovate PR: a variant switch at the SAME upstream version
                                      # is not something Renovate proposes. Operator-requested
                                      # follow-up to the 2026-09-25 AR-059 investigation.
kind: image
current: "2.5.5"                      # louislam/uptime-kuma:2.5.5, index digest
                                      # sha256:c74379ac4509ce2d2c2633f509e67003ee2e45b6e995c5e43fc101f45a0e1fbe
                                      # (live pod imageID, re-verified 2026-09-26)
target: "2.5.5-slim-rootless"         # index digest sha256:a292237a108fa8843d09bb4066e738f02e913ef893542740f80c26556601ab77
                                      # (Docker Hub, pushed 2026-09-16, same build run as 2.5.5)
update_type: security                 # variant/base switch at an unchanged app version; the driver is
                                      # the image's scanner surface (security_ref), not a feature
risk: medium                          # low-medium: same app version, no schema migration, git-revert
                                      # rollback — but it changes the process uid, the PVC ownership
                                      # and the capability set of the one component that watches
                                      # 68 active endpoints; a wrong capability set silently turns
                                      # every ping monitor DOWN (proven, §1.3).
est_duration_min: 45                  # §7 breakdown
needs_reboot: false
exclusive: false
touches:
  namespaces: [monitoring]
  resources:
    - helmrelease/monitoring/uptime-kuma          # values: image.tag, podSecurityContext, securityContext
    - deployment/monitoring/uptime-kuma           # Recreate: ~1 min with no Kuma process
    - pvc/monitoring/kuma-monitoring-config       # longhorn-static RWO 5Gi; chown -R 1000:1000 (§3.2) +
                                                  # kubelet fsGroup walk; sqlite backup file written (§2.5)
    - volume.longhorn.io/storage/kuma-monitoring-config   # on-demand Snapshot + Backup CR (§2.6)
    - kubernetes/apps/monitoring/uptime-kuma/app/helmrelease.yaml
  shared:
    - monitoring                      # Kuma IS an instrument: 68 active monitors + the Telegram
                                      # notification path go dark for the Recreate gap; §4 also reads
                                      # Prometheus (monitor_status / monitor_response_time).
    - storage/longhorn                # one on-demand snapshot + backup to the default backup target
    - authentik                       # read-only dependency: kuma.<domain> is served ONLY through the
                                      # ak-outpost-uptime-kuma-forward-auth proxy outpost (§1.5);
                                      # nothing in authentik is changed.
depends_on: []
conflicts_with:
  - talos-1.14.1                      # sun-attended:2026-09-27, exclusive. A node roll evicts the Kuma
                                      # pod and reboots ping targets, so §4's "down-count == baseline"
                                      # gate cannot be read on the same night. (talos-1.14.1 is exclusive,
                                      # so the scheduler already refuses the slot; named here for the
                                      # on-demand path and for the reason.)
  - flux-oci-chart-sources            # stage 7 moves the dirsigler chart source (uptime-kuma) to the
                                      # charts-mirror track: same HelmRelease, different spec.chart.
  - helm-drift-detection              # adds spec.driftDetection to every HelmRelease incl. this one;
                                      # a same-night Helm upgrade here muddies its §4.1 "no upgrade" proof.
  - flux-reconciler-impersonation     # exclusive; rewrites how helm-controller applies this release.
                                      # No kube-prometheus-stack plan is open (91.4.1 executed): if one
                                      # appears, it must be added here — §4 reads Prometheus.
capability_change: true               # the slim variant drops Chromium (Real-Browser monitor type) and
                                      # the embedded MariaDB option, and rootless can no longer start
                                      # nscd via sudo. None is used here (0 real-browser monitors,
                                      # db-config.json = sqlite, all 63 ping targets are IP literals),
                                      # but capabilities ARE removed => never unattended.
rollback_class: git-revert            # same app version, no migration; the root image reads uid-1000
                                      # files (CAP_DAC_OVERRIDE). Break-glass restore from the §2.5
                                      # sqlite backup is written out in §5.3 anyway.
security_ref: F-cf27b98e              # AR-059 finding for louislam/uptime-kuma:2.5.5 (detail in DB only)
finding_refs:
  - F-cf27b98e                        # [AR-059] fixable-unbumpable finding on 2.5.5 — the one this switch shrinks
  - F-28d0a513                        # [AR-029] sibling (no upstream fix) on 2.5.5 — re-measured post-switch
  - F-117aba8a                        # AR-059 COMPENSATING POSTURE text is stale (still says ingress) —
                                      # §7.3 rewrites it in the same policy-cli edit
premises:
  # All read-only single commands (plan-premises.py allowlist). Values measured 2026-09-26.
  - id: live-image-is-2.5.5-root
    why: >-
      `current:` claims the Deployment runs louislam/uptime-kuma:2.5.5 with NO pod or container
      securityContext (i.e. as root). If someone already switched the tag or added a
      securityContext, §3's edit anchors and §4's baseline are wrong. Prints a different string
      and fails.
    run: kubectl get deploy -n monitoring uptime-kuma -o jsonpath='{.spec.template.spec.containers[0].image} psc={.spec.template.spec.securityContext} csc={.spec.template.spec.containers[0].securityContext} strategy={.spec.strategy.type}'
    expect_exact: louislam/uptime-kuma:2.5.5 psc={} csc={} strategy=Recreate
  - id: pvc-bound-longhorn-static
    why: >-
      §2.6 snapshots Longhorn volume `kuma-monitoring-config`, which must be the PV/volumeHandle
      behind the PVC. A rename or re-provision prints something else and fails.
    run: kubectl get pvc -n monitoring kuma-monitoring-config -o jsonpath='{.status.phase} {.spec.storageClassName} {.spec.volumeName} {.spec.accessModes[0]}'
    expect_exact: Bound longhorn-static kuma-monitoring-config ReadWriteOnce
  - id: longhorn-csi-applies-fsgroup
    why: >-
      fsGroup is only honoured when the CSIDriver's fsGroupPolicy allows it. With `None` the
      kubelet skips the group walk and the §3.2 chown becomes the ONLY thing standing between
      uid 1000 and a 0600 root-owned kuma.db. Any other value fails and must be re-assessed.
    run: kubectl get csidriver driver.longhorn.io -o jsonpath='{.spec.fsGroupPolicy}'
    expect_exact: ReadWriteOnceWithFSType
  - id: backup-target-available
    why: >-
      §2.6 takes an on-demand Longhorn backup to the `default` target. An unavailable target
      means the backup CR never completes and the off-cluster rollback copy does not exist.
    run: kubectl get backuptargets.longhorn.io -n storage default -o jsonpath='{.status.available}'
    expect_exact: "true"
  - id: kuma-series-scraped
    why: >-
      §4 reads monitor_status / monitor_response_time from Prometheus. This asserts the
      scrape is alive and every monitor_type group is present BEFORE the change (ping, group,
      json-query, snmp — the dns monitor is inactive and exports nothing). An empty result
      (scrape gone, ServiceMonitor broken) fails the regex.
    run: kubectl get --raw '/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query?query=count%20by%20(monitor_type)%20(monitor_status)'
    expect_matches: '"monitor_type":"ping"\},"value":\[[0-9.]+,"[1-9][0-9]*"\]'
  - id: kuma-alert-rules-in-repo-exist
    why: >-
      §4 names KumaMonitorMetricsAbsent / KumaPingLatencyMetricAbsent as CONTROLs. The rule
      file must still be tracked; a deleted file prints nothing and fails.
    run: git ls-files kubernetes/apps/monitoring/kube-prometheus-stack/app/uptime-kuma-alerts.yaml
    expect_exact: kubernetes/apps/monitoring/kube-prometheus-stack/app/uptime-kuma-alerts.yaml
status: awaiting-go                   # plan-reviewer 2026-09-26: ready-for-go (2 blockers fixed). NO GO RECORDED — the operator gives it.
window: "sat-attended:2026-10-03"      # reviewer-recommended empty attended slot; set because validate rejects a slotless awaiting-go. The window agent may move it.
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/longhorn.md
  - docs/sops/backup.md
  - docs/sops/storage-safety.md
  - docs/sops/authentik.md
  - docs/sops/verification-contents-not-shape.md
  - docs/sops/vulnerability-disclosure.md
generated: "2026-09-26"
---

# uptime-kuma 2.5.5 → 2.5.5-slim-rootless

## 1. Summary & why held

**What changes.** One HelmRelease values edit: the image tag moves from `2.5.5` to
the upstream `2.5.5-slim-rootless` variant (same app version, same build run on
2026-09-16), and the pod gains a non-root security context (uid/gid/fsGroup 1000,
`runAsNonRoot`, `allowPrivilegeEscalation: false`, drop ALL + add NET_RAW). Before
the switch the existing data is backed up three ways and re-owned to uid 1000.

**Why this is not an auto-update.** No version moves, so the auto-updater never
sees it. It is an operator-requested remediation for the AR-059 finding
(`security_ref: F-cf27b98e`; scanner detail lives on the finding record only).
The variant drops the Chromium and embedded-MariaDB layers, which is where most of
the scanner surface sits. The measured before/after figures are on the finding, not
here. The change is also non-trivial: it moves the process uid, the PVC ownership
and the capability set of the component that watches 68 active endpoints.

### 1.1 Image facts (primary source: the registry, 2026-09-26)

| | `2.5.5` (live) | `2.5.5-slim-rootless` (target) |
|---|---|---|
| index digest | `sha256:c74379ac…1fbe` | `sha256:a292237a…ab77` |
| amd64 manifest | `sha256:22f93b4e…329e` | `sha256:8bdad438…e1f6` |
| `USER` | unset (root) | `node` (uid 1000 / gid 1000, created by the node base image) |
| entrypoint | `dumb-init -- node server/server.js` | identical: no root-only entrypoint step, no `chown`/`su-exec` (application-update SOP §7d does not apply) |
| Chromium, fonts, `mariadb-server`, `UPTIME_KUMA_ENABLE_EMBEDDED_MARIADB=1` | present | **absent** |
| `sqlite3`, `iputils-ping`, `curl`, `apprise`, `cloudflared`, `sudo`+`nscd` | present | present (identical layer commands) |
| `/app` | `COPY --chown=node:node` | same |

"Slim drops Chromium and embedded MariaDB" was checked against the image history:
the full image's only extra layer is
`apt install chromium fonts-* mariadb-server` plus the `ENV UPTIME_KUMA_ENABLE_EMBEDDED_MARIADB=1`.
Neither is used here: `db-config.json` is `{"type": "sqlite"}`, and there are 0
monitors of type `real-browser`/`docker`/`mysql`/`mongodb`.

### 1.2 Live data (2026-09-26)

- PVC `kuma-monitoring-config`: longhorn-static, RWO, 5Gi, ext4; 1.2G used / **3.8G free**.
- `kuma.db` is 1,185,374,208 B, plus `-wal` about 9 MB. Files are `root:root`, mostly `0700`/`0600`.
  The mount root is `0777`.
- Monitors: 74 in total. By type: ping 63 (58 active), group 6, json-query 3, snmp 1, dns 1 (inactive).
  **68 active**; Prometheus exports 68 `monitor_status` series with **0 down**.
- Notifications: 1 (`Cberg-Server-Alarm-Telegram`, active, default). Status pages: 1 (slug `cberg`, 1 group, 3 monitors).
- All 63 ping targets are IP literals, so nscd has nothing to cache (§1.4).
- The ping interval is 60 s for every active ping monitor.
- The last start went from "Welcome" to `Listening on` in about 1 s. The 1.2G SQLite opens instantly.

### 1.3 Ping without root (the one thing that can break every monitor)

`/usr/bin/ping` in this image family carries the **file capability
`cap_net_raw=ep`**. It is not setuid. The pod sandbox's `net.ipv4.ping_group_range`
is `0 2147483647`. Measured in the live pod with `setpriv` as uid/gid 1000, pinging
192.168.55.1:

| bounding set | no_new_privs | result |
|---|---|---|
| all dropped | on | **`setpriv: failed to execute ping: Operation not permitted`** |
| all dropped | off | **same EPERM** |
| only `net_raw` | off | reply, rtt 0.5 ms |
| only `net_raw` | on | reply, rtt 0.5 ms |

So `drop: [ALL]` **without** `add: [NET_RAW]` makes execve(ping) fail with EPERM,
and all 58 active ping monitors go DOWN. The kernel refuses to exec an `=ep`
file-cap binary whose capability is outside the bounding set. With NET_RAW in the
bounding set it works, with or without `allowPrivilegeEscalation: false`. With
no_new_privs on, ping does not actually GAIN NET_RAW at exec: it falls back to an
unprivileged ICMP datagram socket, which the sandbox `ping_group_range` permits.
NET_RAW in the bounding set is what stops the kernel refusing the exec at all. The
plan therefore sets both. `allowPrivilegeEscalation: false` is an addition to the brief,
and it is safe because of the last row. It also neutralises the image's
`/etc/sudoers` entry `node ALL=(root) NOPASSWD: /usr/sbin/service`. That entry
would otherwise be a root path from the app uid.

### 1.4 Behaviour that changes (expected, not failures)

- **nscd will not start.** The `nscd` setting is `true`, and Kuma runs
  `sudo service nscd start` at boot (`server/uptime-kuma-server.js:511-519`).
  Under drop ALL + no_new_privs, sudo cannot escalate. Kuma catches the error and
  logs `[SERVICES] INFO: Failed to start nscd`, then carries on. Impact: none,
  because every ping target is an IP literal.
- The Chromium-based Real-Browser monitor type and the embedded-MariaDB choice
  disappear. Both are unused here (§1.1).

### 1.5 Cloudflare tunnel and `disableAuth`: what the new image can and cannot re-enable

- `cloudflared` **is still shipped** in slim-rootless (identical layer).
  Upstream starts it in exactly one place, `server/server.js:1789`
  `cloudflaredAutoStart(cloudflaredToken)`. It starts only when
  `--cloudflared-token`, `UPTIME_KUMA_CLOUDFLARED_TOKEN`, or the DB setting
  `cloudflaredTunnelToken` is non-empty (`cloudflared-socket-handler.js:103-117`).
  - Live, 2026-09-26: the setting has length 0, no `cloudflared` process runs,
    and the HelmRelease sets no such env.
  - The image switch changes none of these, so it cannot re-enable the tunnel.
    §4.6 asserts it anyway.
  - The contained bypass (F-38db1658) stays tracked on its own finding. This plan
    does not touch the Cloudflare side or the token backup file named on it.
- **`disableAuth=true` stays.** Kuma's own login is off, and the only thing that
  authenticates a human is the Authentik **proxy outpost**.
  - HTTPRoute `monitoring/uptime-kuma` sends both `/` and `/outpost.goauthentik.io`
    to `kube-system/ak-outpost-uptime-kuma-forward-auth:9000` on `envoy-external`.
  - **Risk to keep in view:** any path that reaches port 3001 without passing the
    outpost is unauthenticated. That covers a second tunnel, a route repointed to
    `svc/uptime-kuma`, a port-forward, or any in-cluster client.
  - The rootless switch neither widens nor narrows this. It only lowers what a
    compromise of the Kuma process can do inside the container.
  - This plan does not change the HTTPRoute. §4.7 confirms that the outpost
    still gates it.

### 1.6 Scanner classification after the switch (checked, not assumed)

`security-check.py` classifies fixable findings through
`_newer_upstream_tag_exists()`. The version checker resolves the newest tag
**within the variant line**. Measured 2026-09-26 with `VersionChecker.get_latest_image_tag`:
`2.5.5-slim-rootless → latest=2.5.5-slim-rootless, equal=True`. So any residual
fixable findings on the new image keep the "already the newest upstream tag" class.
The switch therefore does not create a spurious "bump available" critical.
Whether the residual keeps the **AR-059 wording** depends on its size:
- `security-check.py` produces that wording only while the fixable-critical count
  stays at or above `_UNBUMPABLE_CRIT_ESCALATE` (50; `security-check.py:2121,3515`).
- Below that threshold, the finding is emitted in the AR-029 wording instead.
Either way it stays an accepted class. §7.3 handles both outcomes.

## 2. Pre-checks

The executor works from the repo root in zsh. Create the evidence dir once:

```bash
cd /Users/mu/code/cberg-home-nextgen
E=/Users/mu/db-dumps/uptime-kuma-2.5.5-slim-rootless-exec; mkdir -p $E
```

**2.1 Premises.**
`.venv/bin/python3 runbooks/plan-premises.py uptime-kuma-2.5.5-slim-rootless --require-premises`: all PASS (exit 0).

**2.2 Flux and the release are idle.**
```bash
flux get helmrelease -n monitoring uptime-kuma
flux get kustomization -A | awk 'NR==1 || $0 ~ /uptime-kuma/'
```
EXPECT: `READY True`, and the message names the currently applied chart `uptime-kuma@4.2.0`.
HOW IT FAILS: `False`, `Unknown` or "in progress" means another reconcile is in flight. Stop.

**2.3 Baseline: Kuma's own view and Prometheus' view.** Save both, because §4 diffs against them.
```bash
POD=$(kubectl get pod -n monitoring -l app.kubernetes.io/name=uptime-kuma -o jsonpath='{.items[0].metadata.name}')
echo $POD > $E/pod-before.txt
kubectl exec -n monitoring $POD -- sqlite3 -readonly /app/data/kuma.db \
  "select count(distinct h.monitor_id) from heartbeat h join monitor m on m.id=h.monitor_id where m.type='ping' and m.active=1 and h.status=1 and h.ping is not null and h.time > datetime('now','-4 minutes');" \
  "select count(*) from monitor where active=1;" \
  "select key||'='||length(value) from setting where key='cloudflaredTunnelToken';" | tee $E/db-baseline.txt
for Q in 'count(monitor_status{monitor_type!="group"} == 1)' 'count(monitor_status == 0) or vector(0)' 'count(monitor_response_time{monitor_type="ping"} > 0)' 'ALERTS{alertname=~"KumaMonitorDown|KumaMonitorMetricsAbsent|KumaPingLatencyMetricAbsent"}'; do
  kubectl get --raw "/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query?query=$(python3 -c 'import sys,urllib.parse;print(urllib.parse.quote(sys.argv[1]))' "$Q")"; echo
done | tee $E/prom-baseline.txt
```
EXPECT (2026-09-26 values):
- DB lines: `58`, `68`, `cloudflaredTunnelToken=0`.
- Prometheus lines: `62`, `0`, `58`, then an `ALERTS` result of `[]`. That last
  result is the known-down alert set §4.5 compares against. Any `KumaMonitorDown`
  series it lists (monitor_name) is pre-existing and is recorded, not caused by
  this change.

**Record the actual numbers; they are the §4 baseline.** A non-zero down count is
acceptable when it is a known-down device, such as the Shelly in F-794c688d. §4
compares against this recorded number, not against 0.

HOW IT FAILS:
- `cloudflaredTunnelToken` length above 0 means the token has come back since
  2026-09-25. STOP and re-open F-38db1658. Do not proceed.

**2.4 Free space for the sqlite backup.**
```bash
kubectl exec -n monitoring $POD -- sh -c 'A=$(df -B1 --output=avail /app/data | tail -1); D=$(stat -c %s /app/data/kuma.db); W=$(stat -c %s /app/data/kuma.db-wal); echo avail=$A need=$(( (D+W)*3/2 )); [ $A -gt $(( (D+W)*3/2 )) ] && echo SPACE_OK || echo SPACE_LOW'
```
EXPECT: `SPACE_OK`. On 2026-09-26: avail 3.8G against a need of about 1.8G.
HOW IT FAILS: `SPACE_LOW` means the in-volume backup would fill the PVC, and SQLite
then fails its writes. Instead, take the backup straight off-cluster (§2.5 with
`kubectl cp` of a `.backup` written to `/tmp` inside the pod; `/tmp` is the node's
ephemeral disk), or stop.

**2.5 SQLite online backup: consistent copy, integrity-checked, copied off-cluster.**
```bash
TS=$(date +%Y%m%d_%H%M%S); echo $TS > $E/ts.txt
kubectl exec -n monitoring $POD -- sqlite3 /app/data/kuma.db ".backup /app/data/kuma.db.pre-rootless.$TS"
kubectl exec -n monitoring $POD -- sqlite3 -readonly /app/data/kuma.db.pre-rootless.$TS \
  "pragma integrity_check;" "select count(*) from monitor;" "select count(*) from notification;"
kubectl cp monitoring/$POD:/app/data/kuma.db.pre-rootless.$TS $E/kuma.db.pre-rootless.$TS
ls -l $E/kuma.db.pre-rootless.$TS
```
EXPECT:
- `ok`, `74`, `1`.
- The local file is roughly 1.1–1.2 GB (this is a 1.2 GB transfer, so allow a couple of minutes).

`.backup` uses SQLite's online-backup API, so it is consistent while Kuma writes.

HOW IT FAILS:
- Any integrity output other than `ok`, or a monitor count that differs from the
  live `select count(*) from monitor`: STOP.
- A local file under 1 GB means the `kubectl cp` was truncated. Re-copy it.

**2.6 Longhorn snapshot + backup** (taken after 2.5, so the backup file is inside it).
```bash
kubectl apply -f - <<'EOF'
apiVersion: longhorn.io/v1beta2
kind: Snapshot
metadata:
  name: kuma-monitoring-config-pre-rootless
  namespace: storage
spec:
  volume: kuma-monitoring-config
  createSnapshot: true
EOF
sleep 10
kubectl get snapshots.longhorn.io -n storage kuma-monitoring-config-pre-rootless -o jsonpath='{.status.readyToUse}{"\n"}'
kubectl apply -f - <<'EOF'
apiVersion: longhorn.io/v1beta2
kind: Backup
metadata:
  name: kuma-monitoring-config-pre-rootless
  namespace: storage
  labels:
    backup-volume: kuma-monitoring-config
    backup-target: default
spec:
  snapshotName: kuma-monitoring-config-pre-rootless
EOF
# poll until Completed (typ. 1-3 min for ~1.4 GB incremental)
for i in $(seq 1 30); do S=$(kubectl get backups.longhorn.io -n storage kuma-monitoring-config-pre-rootless -o jsonpath='{.status.state}'); echo "$i $S"; [ "$S" = Completed ] && break; [ "$S" = Error ] && break; sleep 10; done
kubectl get backups.longhorn.io -n storage kuma-monitoring-config-pre-rootless -o jsonpath='{.status.state} {.status.url} {.status.size}{"\n"}' | tee $E/longhorn-backup.txt
```
EXPECT: snapshot `true`; backup `Completed` with a non-empty `url` and a `size` above
1,000,000,000.

The Backup CR shape (labels `backup-volume` + `backup-target`, `spec.snapshotName`)
matches the recurring-job backup `backup-0bca75bfcef24bad` on this volume.

HOW IT FAILS:
- `Error`, or still empty after 5 min: the off-cluster Longhorn copy does not exist.
  Last night's `daily-backup-all-volumes` backup (03:04Z) plus the §2.5 local copy
  remain.
- Proceeding without the on-demand backup is an operator decision; say so explicitly.

**2.7 Silence + active-update marker** (application-update SOP Step 1).
```bash
runbooks/update-marker.sh add uptime-kuma monitoring 2 "2.5.5 -> 2.5.5-slim-rootless (plan uptime-kuma-2.5.5-slim-rootless)"
kubectl port-forward -n monitoring svc/kube-prometheus-stack-alertmanager 9093:9093 >/dev/null 2>&1 & PF=$!
sleep 3
NOW=$(python3 -c "from datetime import *;print(datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z'))")
END=$(python3 -c "from datetime import *;print((datetime.now(timezone.utc)+timedelta(hours=2)).strftime('%Y-%m-%dT%H:%M:%S.000Z'))")
# (a) pod/deployment rollout noise — these alerts DO carry namespace=monitoring
curl -s -X POST localhost:9093/api/v2/silences -H 'Content-Type: application/json' -d '{
  "matchers":[{"name":"namespace","value":"monitoring","isRegex":false,"isEqual":true},
              {"name":"alertname","value":"Kube(Pod|Deployment).*","isRegex":true,"isEqual":true}],
  "startsAt":"'$NOW'","endsAt":"'$END'","createdBy":"maintenance-window-agent",
  "comment":"uptime-kuma rootless switch - Recreate gap. auto-expires 2h"}' > $E/silence-kube.json
# (b) the two absent() guards — absent() output carries NO namespace label, only
#     severity/category/component (uptime-kuma-alerts.yaml:53-60,126-132), so they
#     need their own matcher set keyed on component
curl -s -X POST localhost:9093/api/v2/silences -H 'Content-Type: application/json' -d '{
  "matchers":[{"name":"component","value":"uptime-kuma","isRegex":false,"isEqual":true},
              {"name":"alertname","value":"KumaMonitorMetricsAbsent|KumaPingLatencyMetricAbsent","isRegex":true,"isEqual":true}],
  "startsAt":"'$NOW'","endsAt":"'$END'","createdBy":"maintenance-window-agent",
  "comment":"uptime-kuma rootless switch - Recreate gap. auto-expires 2h"}' > $E/silence-absent.json
python3 -c "import json;[print(f, json.load(open('$E/'+f))['silenceID']) for f in ('silence-kube.json','silence-absent.json')]"
kill $PF 2>/dev/null
```
EXPECT: two `silenceID` lines. HOW IT FAILS: a `KeyError` means Alertmanager
rejected a body. Read `$E/silence-*.json`.

`KumaMonitorDown` is **deliberately not silenced**: a real ping failure after the
switch must stay loud. It cannot fire from the Recreate gap itself, because the
series vanish (absent) rather than read 0.

## 3. Steps

**3.1 Pin the evidence of what runs now.**
`kubectl get pod -n monitoring $POD -o jsonpath='{.status.containerStatuses[0].imageID}{"\n"}' > $E/imageid-before.txt`.
EXPECT: `docker.io/louislam/uptime-kuma@sha256:c74379ac4509ce2d2c2633f509e67003ee2e45b6e995c5e43fc101f45a0e1fbe`.

**3.2 Re-own the data to uid/gid 1000 while the root image is still running.**
This is a data-level operation on a PVC. It has no GitOps path and is operator-requested.
```bash
kubectl exec -n monitoring $POD -- chown -R 1000:1000 /app/data
kubectl exec -n monitoring $POD -- sh -c 'find /app/data \( ! -uid 1000 -o ! -gid 1000 \) -print | wc -l; stat -c "%u:%g %a %n" /app/data /app/data/kuma.db /app/data/kuma.db-wal /app/data/kuma.db-shm'
```
EXPECT: `0`, and `1000:1000` on all four paths.

The root process keeps working after the chown, because root ignores DAC.
- A file the root process creates in the gap between here and §3.4 would be
  root-owned.
- That is covered twice: the kubelet's fsGroup walk gives it group 1000 plus g+rw,
  and §4.3 re-checks ownership from inside the new pod.
- Keep §3.2 → §3.4 short (minutes, not hours).

HOW IT FAILS: a non-zero count means files were not re-owned. Re-run the chown.
Do not push §3.3 while the count is above 0.

**3.3 The git change.** This is an exact-anchor edit that refuses to run twice
(dry-tested on a scratch copy on macOS, 2026-09-26):
```bash
cd /Users/mu/code/cberg-home-nextgen
python3 - <<'EOF'
import pathlib
p = pathlib.Path("kubernetes/apps/monitoring/uptime-kuma/app/helmrelease.yaml")
s = p.read_text()
old_tag = "      repository: louislam/uptime-kuma\n      tag: 2.5.5\n"
new_tag = "      repository: louislam/uptime-kuma\n      tag: 2.5.5-slim-rootless\n"
old_tail = "    strategy:\n      type: Recreate\n"
new_tail = old_tail + (
    "\n"
    "    # Rootless (plan uptime-kuma-2.5.5-slim-rootless). The image's USER is node\n"
    "    # (uid/gid 1000); fsGroup makes the Longhorn PVC group-writable for it.\n"
    "    podSecurityContext:\n"
    "      runAsUser: 1000\n"
    "      runAsGroup: 1000\n"
    "      fsGroup: 1000\n"
    "      fsGroupChangePolicy: OnRootMismatch\n"
    "    securityContext:\n"
    "      runAsNonRoot: true\n"
    "      allowPrivilegeEscalation: false\n"
    "      capabilities:\n"
    "        drop: [ALL]\n"
    "        # /usr/bin/ping carries file cap cap_net_raw=ep: without NET_RAW in the\n"
    "        # bounding set execve(ping) fails EPERM and every ping monitor goes DOWN.\n"
    "        add: [NET_RAW]\n"
)
assert s.count(old_tag) == 1, "tag anchor not unique/absent"
assert s.count(old_tail) == 1, "strategy anchor not unique/absent"
assert "podSecurityContext" not in s and "\n    securityContext" not in s, "already edited"
p.write_text(s.replace(old_tag, new_tag).replace(old_tail, new_tail))
print("EDITED")
EOF
git diff --stat -- kubernetes/apps/monitoring/uptime-kuma/app/helmrelease.yaml
```
EXPECT: `EDITED`, then `1 file changed, 17 insertions(+), 1 deletion(-)`.

The dry-run diff (scratch copy) is:
```
-      tag: 2.5.5
+      tag: 2.5.5-slim-rootless
@@ -117,3 +117,19 @@
     strategy:
       type: Recreate
+
+    # Rootless (plan uptime-kuma-2.5.5-slim-rootless). ...
+    podSecurityContext:
+      runAsUser: 1000
...
+        add: [NET_RAW]
```
A second run fails with `AssertionError: tag anchor not unique/absent`, which was
tested and is intended.

**3.3a Validate the RENDERED Deployment.** kubeconform skips HelmRelease CRDs; see
feedback_apptemplate_helm_render_validation.
```bash
T=$(mktemp -d); export HELM_CACHE_HOME=$T/c HELM_CONFIG_HOME=$T/f
helm pull uptime-kuma --repo https://helm.irsigler.cloud --version 4.2.0 --untar -d $T
yq '.spec.values' kubernetes/apps/monitoring/uptime-kuma/app/helmrelease.yaml > $T/values.yaml
helm template uptime-kuma $T/uptime-kuma -n monitoring -f $T/values.yaml > $T/render.yaml
yq ea -o=json -I=0 '[select(.kind=="Deployment")][0].spec | [.strategy.type, .template.spec.securityContext, .template.spec.containers[0].image, .template.spec.containers[0].securityContext]' $T/render.yaml | head -1
```
EXPECT (verbatim, measured on the scratch render):
```
["Recreate",{"fsGroup":1000,"fsGroupChangePolicy":"OnRootMismatch","runAsGroup":1000,"runAsUser":1000},"louislam/uptime-kuma:2.5.5-slim-rootless",{"allowPrivilegeEscalation":false,"capabilities":{"add":["NET_RAW"],"drop":["ALL"]},"runAsNonRoot":true}]
```
The same command on the unedited file prints `["Recreate",{},"louislam/uptime-kuma:2.5.5",{}]`,
which is the negative control. It proves the gate reads the values and does not just
echo them.

HOW IT FAILS:
- Any `{}` in positions 2/4 means the chart dropped the key. `podSecurityContext`
  and `securityContext` are top-level values in dirsigler 4.2.0
  (`templates/deployment.yaml:39-40,53-54`).
- `strategy` other than `Recreate` risks Multi-Attach on the RWO volume.

**3.4 Commit + push** (plan's own file only; shared worktree rules):
```bash
cat > $E/commit-msg.txt <<'EOF'
feat(uptime-kuma): switch to 2.5.5-slim-rootless, run as uid 1000

Same upstream version, slim+rootless variant; drop ALL + NET_RAW (ping's
file capability needs it in the bounding set), no privilege escalation.
Plan: uptime-kuma-2.5.5-slim-rootless. security_ref F-cf27b98e.
EOF
git commit --only kubernetes/apps/monitoring/uptime-kuma/app/helmrelease.yaml -F $E/commit-msg.txt
git log -1 --format=%s     # MUST be "feat(uptime-kuma): switch to 2.5.5-slim-rootless, run as uid 1000"
git show --stat HEAD       # MUST list only helmrelease.yaml
git push
```
No manual reconcile. The Flux webhook picks it up, and helm-controller's interval is 5m.

## 4. Verification

Wait for the new pod and re-resolve its name. Every `$NEW` below is this pod.
```bash
for i in $(seq 1 40); do NEW=$(kubectl get pod -n monitoring -l app.kubernetes.io/name=uptime-kuma -o jsonpath='{.items[?(@.status.phase=="Running")].metadata.name}'); [ -n "$NEW" ] && [ "$NEW" != "$(cat $E/pod-before.txt)" ] && break; sleep 15; done; echo NEW=$NEW
```

**4.1 The new pod runs the target digest, not the old ReplicaSet.** See feedback_rollout_status_old_generation.
```bash
kubectl get pod -n monitoring $NEW -o jsonpath='{.status.containerStatuses[0].imageID} restarts={.status.containerStatuses[0].restartCount}{"\n"}'
```
EXPECT: `docker.io/louislam/uptime-kuma@sha256:a292237a108fa8843d09bb4066e738f02e913ef893542740f80c26556601ab77 restarts=0`.
HOW IT FAILS: the `c74379…` digest means the old pod is still serving. A restart
count above 0 is a crash-loop; go to 4.3 and read the logs.

**4.2 The process is uid 1000 with only NET_RAW in its bounding set.**
```bash
kubectl exec -n monitoring $NEW -- sh -c 'id -u; id -g; grep -E "^(Uid|Gid|CapEff|CapBnd|NoNewPrivs)" /proc/1/status'
```
EXPECT:
- `1000`, `1000`
- `Uid: 1000 1000 1000 1000`, `Gid: 1000 …`
- `CapEff: 0000000000000000`
- `CapBnd: 0000000000002000` (bit 13 = CAP_NET_RAW)
- `NoNewPrivs: 1`

HOW IT FAILS: `Uid: 0` means the securityContext did not render (see 3.3a).
`CapBnd: 0000000000000000` means NET_RAW is missing, and 4.4 will show every ping
DOWN. The live root pod reads `CapBnd: 00000000a80425fb`, the contrasting value.

**4.3 The app opened its database read-write as uid 1000.**
```bash
kubectl logs -n monitoring $NEW | sed 's/\x1b\[[0-9;]*m//g' | grep -i -E 'connected to the database|listening on|sqlite_readonly|sqlite_cantopen|eacces|permission denied|readonly database|failed to start nscd'
kubectl exec -n monitoring $NEW -- sh -c 'find /app/data ! -uid 1000 -print | wc -l; test -w /app/data/kuma.db && test -w /app/data/kuma.db-wal && echo WRITABLE'
```
EXPECT:
- `Connected to the database`, `Listening on:`, and `Failed to start nscd`.
  The last one is expected (§1.4) and proves no_new_privs blocked sudo.
- **No** `SQLITE_READONLY` / `SQLITE_CANTOPEN` / `EACCES` / `permission denied` /
  `readonly database` lines.
- Then `0` and `WRITABLE`.

The grep is case-insensitive on purpose: upstream prints `SQLITE_READONLY`
upper-case, and Node prints `EACCES` in mixed-case contexts.

HOW IT FAILS: any of those error strings, or a missing `Listening on`, means
ownership or permissions are wrong. Go to §5.

**4.4 CONTENTS ASSERTION: every active ping monitor produces successful heartbeats
with a latency after the switch.** Measured from Kuma's own database, as the new uid.
Wait at least **5 minutes after `Listening on`**, which is 5 ping cycles at the
60 s interval.
```bash
kubectl exec -n monitoring $NEW -- sqlite3 -readonly /app/data/kuma.db \
  "select count(distinct h.monitor_id) from heartbeat h join monitor m on m.id=h.monitor_id where m.type='ping' and m.active=1 and h.status=1 and h.ping is not null and h.time > datetime('now','-4 minutes');" \
  "select count(distinct h.monitor_id) from heartbeat h join monitor m on m.id=h.monitor_id where m.type='ping' and m.active=1 and h.status in (0,2) and h.time > datetime('now','-4 minutes');" \
  "select substr(h.msg,1,80), count(*) from heartbeat h join monitor m on m.id=h.monitor_id where m.type='ping' and h.status in (0,2) and h.time > datetime('now','-4 minutes') group by 1;"
```
CONTENTS ASSERTION: the up-with-latency ping count must equal the §2.3 recorded
baseline (58 on 2026-09-26), and the down count must equal the baseline (0).
Both are measured by the query above and compared to `$E/db-baseline.txt`.

HOW IT FAILS: with NET_RAW missing, execve(ping) fails with EPERM (proven in §1.3).
Every ping heartbeat is then `status=0`. The first count collapses to 0, the second
reaches 58, and the third query prints the error text. A baseline-sized first count
is only possible if ping actually ran as uid 1000. The same query read `58` / `0`
on the root pod on 2026-09-26, so the instrument is proven to read real data.

**4.5 Prometheus sees the new pod's series with the baseline counts.**
```bash
for Q in "count(monitor_status{pod=\"$NEW\",monitor_type!=\"group\"} == 1)" "count(monitor_status{pod=\"$NEW\"} == 0) or vector(0)" "count(monitor_response_time{pod=\"$NEW\",monitor_type=\"ping\"} > 0)" "absent(monitor_status{pod=\"$NEW\"})" 'ALERTS{alertname=~"KumaMonitorMetricsAbsent|KumaPingLatencyMetricAbsent|KumaMonitorDown"}'; do
  echo "## $Q"; kubectl get --raw "/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query?query=$(python3 -c 'import sys,urllib.parse;print(urllib.parse.quote(sys.argv[1]))' "$Q")"; echo
done
```
CONTROL: metric monitor_status — scoped to `pod="$NEW"`. The non-group up count
must equal the §2.3 baseline (62), the down count must equal the baseline (0), and
the absent() query must return `"result":[]`. Scoping to the new pod label stops
the old pod's last samples from satisfying the gate.

CONTROL: metric monitor_response_time — `{monitor_type="ping", pod="$NEW"} > 0`.
The count must equal the baseline (58). Guards KumaPingLatencyHigh's input.

CONTROL: alertname KumaMonitorMetricsAbsent — must not be firing or pending
(`ALERTS` returns no such series).

CONTROL: alertname KumaPingLatencyMetricAbsent — must not be firing or pending.

CONTROL: alertname KumaMonitorDown — must show no series beyond the §2.3 known-down
set.

The two `*Absent` alerts have `for: 10m`, so a 1–3 min Recreate gap cannot make
them fire. That makes them weak on their own: they can only fail after 10 minutes
of total absence. The pod-scoped `absent(monitor_status{pod=…})` query above is the
gate that can fail immediately. The alerts are read again at §4.9, 15 min after the
switch.

The Alertmanager silence from §2.7 does not affect `ALERTS` (a Prometheus-side
series). HOW IT FAILS:
- Empty results or count 0 mean the scrape broke; check `up{job="uptime-kuma"}`.
- A down count above baseline has the same cause as a 4.4 failure.

**4.6 The Cloudflare tunnel did NOT come back.**
```bash
kubectl exec -n monitoring $NEW -- sqlite3 -readonly /app/data/kuma.db "select key||'='||length(value) from setting where key='cloudflaredTunnelToken';"
kubectl exec -n monitoring $NEW -- sh -c 'L=$(for p in /proc/[0-9]*; do tr "\0" " " < $p/cmdline 2>/dev/null; echo; done); echo "$L" | awk "\$1 ~ /(^|\\/)dumb-init\$/" | wc -l; echo "$L" | awk "\$1 ~ /(^|\\/)cloudflared\$/" | wc -l; echo "/usr/bin/cloudflared tunnel run" | awk "\$1 ~ /(^|\\/)cloudflared\$/" | wc -l'
kubectl logs -n monitoring $NEW | grep -i -c 'start cloudflared'
```
EXPECT:
- `cloudflaredTunnelToken=0`
- `1`, `0`, `1` for the three /proc lines:
  - `1`: positive control. The walk sees `dumb-init` as PID 1's program.
  - `0`: no process whose PROGRAM (first argv word) is `cloudflared`.
  - `1`: known-bad control. The same awk matches a real cloudflared command line.
- `0` for the log grep. This is an absence-only check with no demonstrated positive
  case, so it is supporting evidence only. The DB token length and the /proc walk
  are the gate.

The slim image has no `ps`, which is why this walks `/proc`. The walk matches on
**`$1` (the program), never a substring of the whole command line**. The first
version grepped the full line and counted its own `sh -c` script, which contains the
words it searched for. Replayed on the healthy root pod on 2026-09-26, that version
read `4`/`3` and would have forced a revert on every good run. The fixed line read
`1`/`0`/`1` on the same pod.

HOW IT FAILS: a length above 0, a cloudflared (second) count of 1 or more, or the log line
means the bypass is live again. Revert at once (§5) and re-open F-38db1658.

**4.7 Status page and Authentik gate.** The in-cluster part runs here; the browser
part is done by the coordinator in Chrome.
```bash
kubectl port-forward -n monitoring svc/uptime-kuma 13001:3001 >/dev/null 2>&1 & PF=$!; sleep 3
curl -s localhost:13001/api/status-page/cberg | python3 -c "import sys,json;d=json.load(sys.stdin);print('groups',len(d['publicGroupList']),'monitors',sum(len(g['monitorList']) for g in d['publicGroupList']))"
curl -s localhost:13001/api/status-page/heartbeat/cberg | python3 -c "import sys,json;d=json.load(sys.stdin);print('hb',len(d['heartbeatList']), 'last-up', sum(1 for v in d['heartbeatList'].values() if v and v[-1]['status']==1))"
kill $PF 2>/dev/null
kubectl get httproute -n monitoring uptime-kuma -o jsonpath='{range .spec.rules[*]}{.backendRefs[0].namespace}/{.backendRefs[0].name}:{.backendRefs[0].port} {end}{"\n"}'
```
EXPECT:
- `groups 1 monitors 3` and `hb 3 last-up 3`. The baseline measured on the root
  pod on 2026-09-26 was groups 1 / monitors 3 / hb 3.
- `kube-system/ak-outpost-uptime-kuma-forward-auth:9000 kube-system/ak-outpost-uptime-kuma-forward-auth:9000`.
  Both rules still go through the outpost, so `disableAuth=true` stays covered (§1.5).

Browser checks (coordinator, Chrome):
- (a) A fresh private session to `https://kuma.<domain>/` lands on the Authentik
  login, not the Kuma dashboard.
- (b) After login, the dashboard lists the monitors, with the up count matching §2.3.
- (c) `https://kuma.<domain>/status/cberg` renders its 3 monitors.

**4.8 Telegram notification delivers.** The coordinator runs this in Chrome:
Settings → Notifications → `Cberg-Server-Alarm-Telegram` → **Test**. EXPECT the
test message to arrive in the Telegram chat, and the UI toast to report success.

HOW IT FAILS: an error toast such as `ECONNREFUSED` or `ETIMEDOUT` means the
notification path is broken. Rootless should not affect outbound HTTPS, and apprise
is present in both images. That is a revert-and-investigate.

**4.9 Settle (T+15 min).** Re-run 4.1 (`restarts=0`), the first two queries of 4.4,
and the `ALERTS` query of 4.5. EXPECT the same results. Then delete both §2.7
silences early and remove the marker:
```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-alertmanager 9093:9093 >/dev/null 2>&1 & PF=$!; sleep 3
for f in silence-kube.json silence-absent.json; do curl -s -X DELETE localhost:9093/api/v2/silences/$(python3 -c "import json;print(json.load(open('$E/$f'))['silenceID'])"); done; kill $PF 2>/dev/null
runbooks/update-marker.sh clear uptime-kuma
```

## 5. Rollback

**5.1 Trigger.** Any §4.1–4.8 failure that is not fixed in one obvious try. Also any
§4.6 hit, which means revert immediately with no retry.

**5.2 Revert (primary; `rollback_class: git-revert`).**
```bash
cd /Users/mu/code/cberg-home-nextgen
SHA=$(git log -1 --format=%H --grep='switch to 2.5.5-slim-rootless' -- kubernetes/apps/monitoring/uptime-kuma/app/helmrelease.yaml); echo $SHA
git revert --no-edit $SHA
git log -1 --format=%s; git show --stat HEAD   # only helmrelease.yaml
git push
```
Why this is sufficient: the app version is identical, and no schema migration ran.
The root image reads and writes the uid-1000 files, because root has
CAP_DAC_OVERRIDE and the default container capability set includes it.
- Leave the ownership at 1000:1000. It is harmless under root and saves a second
  chown if the switch is retried.
- Files the root pod creates later will be root-owned again. A retry must therefore
  repeat §3.2.

Confirm the cluster is back:
- §4.1 with the **old** digest `sha256:c74379ac…1fbe`.
- §4.2 prints `Uid: 0` and `CapBnd: 00000000a80425fb`.
- §4.4 and §4.5 match the §2.3 baseline.
- §4.6 is clean.

**5.3 Break-glass: restore the database** (only if kuma.db itself is damaged, e.g. §4.3
shows corruption rather than permissions). Take the local `$E/kuma.db.pre-rootless.<TS>`
from §2.5.

1. Suspend the release so Flux does not fight the scale-down:
   `flux suspend helmrelease -n monitoring uptime-kuma`.
2. Stop Kuma: `kubectl scale deploy -n monitoring uptime-kuma --replicas=0`, then wait
   until `kubectl get pod -n monitoring -l app.kubernetes.io/name=uptime-kuma` returns
   no pods.
3. Start a helper pod on the RWO PVC. It uses the old root image, which has sqlite3:
   ```bash
   kubectl run kuma-restore -n monitoring --restart=Never --image=louislam/uptime-kuma:2.5.5 \
     --overrides='{"spec":{"containers":[{"name":"kuma-restore","image":"louislam/uptime-kuma:2.5.5","command":["sleep","3600"],"volumeMounts":[{"name":"d","mountPath":"/app/data"}]}],"volumes":[{"name":"d","persistentVolumeClaim":{"claimName":"kuma-monitoring-config"}}]}}'
   kubectl wait -n monitoring --for=condition=Ready pod/kuma-restore --timeout=180s
   TS=$(cat $E/ts.txt)
   kubectl exec -n monitoring kuma-restore -- sh -c "mv /app/data/kuma.db /app/data/kuma.db.broken.$TS; rm -f /app/data/kuma.db-wal /app/data/kuma.db-shm; cp /app/data/kuma.db.pre-rootless.$TS /app/data/kuma.db && sqlite3 /app/data/kuma.db 'pragma integrity_check;' && chown -R 1000:1000 /app/data"
   ```
   If the in-volume copy is gone, `kubectl cp $E/kuma.db.pre-rootless.$TS monitoring/kuma-restore:/app/data/kuma.db`
   first.
4. Clean up, resume, and **scale back up explicitly**:
   ```bash
   kubectl delete pod -n monitoring kuma-restore
   # apply the §5.2 revert first if it is not already pushed
   flux resume helmrelease -n monitoring uptime-kuma
   kubectl scale deploy -n monitoring uptime-kuma --replicas=1
   kubectl get deploy -n monitoring uptime-kuma -o jsonpath='{.spec.replicas} {.status.readyReplicas}{"\n"}'
   ```
   The explicit scale is required. The HelmRelease has no `spec.driftDetection`
   (checked live 2026-09-26). If values and chart are unchanged at resume, for
   example because the revert landed before the suspend, Flux runs no Helm upgrade
   and the manual `replicas=0` stays. Kuma would then remain dark with nothing
   reporting it. `replicas: 1` equals the chart's value, so the scale introduces
   no drift.

   EXPECT: `1 1`.

   Restore gate: re-run §4.1 (expected digest per whichever image is now declared),
   §4.4 against the §2.3 baseline, and §4.6. HOW IT FAILS: `1 <empty>` for more
   than 2 min means the pod is not Ready. Read `kubectl logs` and go to step 5.
5. Last resort: restore Longhorn backup `kuma-monitoring-config-pre-rootless` per
   `docs/sops/backup.md`. This is a restore to a new volume, then a PV swap under the
   static-volume rules in `docs/sops/longhorn.md`.

Heartbeats written between §2.5 and the restore are lost. That is minutes of
monitoring history, and acceptable.

## 6. Interference notes

- **Kuma is an instrument.** For the Recreate gap (about 1 min) and until §4.4
  passes, 68 endpoints are unwatched and the Telegram path is down.
  - Do not run this in the same window as a plan whose own verification relies on
    Kuma, or on `KumaMonitorDown` staying quiet.
  - Nextcloud's plans pre-silence Nextcloud's Kuma alerts, for example. Run this
    one first or last, alone.
- **talos-1.14.1** (sun-attended:2026-09-27, `exclusive: true`) must not share a
  window. It is in `conflicts_with` for that reason.
  - After the roll, this plan is unaffected. fsGroup plus `OnRootMismatch` makes a
    rescheduled pod on another node a cheap no-op.
  - Before the roll, the talos plan does not care which Kuma image runs.
  - Either order works. **Not the same night**: the node reboots take ping targets
    (the nodes themselves) down and poison §4.4's baseline comparison.
  - `talos-1.14.1` does not list this plan back. It is exclusive, so the scheduler
    already refuses the slot. Reciprocity is flagged to the coordinator as a repo
    correction rather than edited here, because that file is being refreshed by
    another session.
- **flux-oci-chart-sources** stage 7 (dirsigler → charts-mirror) and
  **helm-drift-detection** both modify this HelmRelease's spec. Serialize them.
- **Longhorn:** the on-demand backup lands inside the 03:00Z
  `daily-backup-all-volumes` run if the window overlaps it. That is harmless, but
  §2.6 polling then takes longer. The on-demand snapshot is a user snapshot. Delete
  it in §7.4 once soaked, so it does not pin about 1.2G of the volume's chain.
- **Renovate:** after the switch, Renovate treats `-slim-rootless` as a
  compatibility suffix and proposes `2.5.x-slim-rootless`. The auto-updater's safe
  lane then keeps the variant, and no deny rule is needed. If a future PR proposes a
  plain tag, reject it.
- **Not touched:** the HTTPRoute, the Authentik outpost/provider, ServiceMonitor,
  metrics Secret, the Cloudflare side of F-38db1658, and the token backup file named
  on that finding.

## 7. Post-change, duration

**7.1 Re-scan.** Let the next sweep's `security-check.py` re-scan (or run the sweep's CVE
subsection ad hoc). Confirm the AR-059-class finding now carries the new image ref
`louislam/uptime-kuma:2.5.5-slim-rootless`. Record the before/after figures **on the
finding record only**:
```bash
source runbooks/lib/sweep-pg-dsn.sh && sweep_pg_dsn_up
runbooks/policy-cli.py finding list --grep uptime-kuma
runbooks/policy-cli.py finding detail F-cf27b98e --plan uptime-kuma-2.5.5-slim-rootless --detail-file <file with the measured delta>
```
The finding for the new image ref may get a NEW id, because the title embeds the
image. If so, carry this plan's detail over and let F-cf27b98e resolve on its own
when the old ref stops appearing.

**7.2 Close-out of findings.** Agent-authored rows never auto-close
(feedback_close_plan_findings_after_fix). Close F-117aba8a with the commit of §7.3's
AR edit. F-cf27b98e and F-28d0a513 are script-owned and resolve when the scanner stops
seeing the old ref. Verify with `finding show`; do not force-close them.

**7.3 AR-059 re-word** (`runbooks/policy-cli.py risk edit AR-059 …`).
- **Do not touch `description`.** It is the drift-stable needle, and §1.6 showed it
  still matches post-switch.
- Rewrite `justification`:
  - (a) Record the variant switch as the "viable base/variant switch" the AR asked
    for, and state that the residual is accepted pending upstream.
  - (b) Replace the stale COMPENSATING POSTURE paragraph (ingress → HTTPRoute on
    envoy-external, both rules to the kube-system outpost; this closes F-117aba8a).
  - (c) State that the container is now rootless (uid 1000, drop ALL + NET_RAW, no
    privilege escalation).
- Re-stamp `last_reviewed_at`. Retire AR-059 only if the re-scan shows zero fixable
  findings on the new tag.
- If the residual is reclassified under AR-029 alone, preview with
  `risk match --description` before any change.

**7.4 Soak cleanup** (after 7 clean days, not in the window):
- delete the in-volume copy `/app/data/kuma.db.pre-rootless.<TS>`;
- delete the Longhorn Snapshot `kuma-monitoring-config-pre-rootless` (keep the Backup);
- keep or discard the Mac-local copy in `$E` per the operator.

Then delete this plan file in the same commit that records it executed.

**Duration (45 min):**

| Step | Minutes |
|---|---|
| §2.1–2.4 premises and baseline | 5 |
| §2.5 backup, integrity check and 1.2 GB `kubectl cp` | 8 |
| §2.6 Longhorn snapshot and backup | 5 |
| §2.7 silence | 2 |
| §3.1–3.3a chown, edit and render | 5 |
| §3.4 push and Flux pickup | 3 |
| §4.1–4.3 | 3 |
| §4.4 5-minute ping soak | 6 |
| §4.5–4.8, including the coordinator's browser and Telegram checks | 5 |
| Buffer | 3 |

The §4.9 T+15 settle overlaps the browser checks. Rollback, if needed, adds about
10 min, or about 25 min for §5.3.

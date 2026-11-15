---
plan_id: unpoller-5.9.5
component: unpoller
pr: 260                               # Renovate PR #260 (renovate/ghcr.io-unpoller-unpoller-5.x). The dispatch said v5.9.4;
                                      # the PR now proposes v5.5.1 -> v5.9.5 (v5.9.5 published 2026-11-11T02:40:35Z, after
                                      # v5.9.4 on 2026-11-04). `target:` below is authoritative. Its diff is exactly the one
                                      # `tag:` line; the plan hand-edits that SAME line and inserts a lineage comment (3.2) and Renovate
                                      # autocloses the PR. CI on the PR was green (Flate Render Gate, Flux Local Diff x2).
kind: image
current: "v5.5.1"                    # MEASURED 2026-11-14: HR spec.values.image.tag v5.5.1, chart 2.4.0, Ready=True, one pod
                                      # unpoller-77fbdfc497-wqgsx 1/1, imageID sha256:6d941ea1..., age 21d, restarts 2 (last
                                      # termination 2026-11-12T13:30:50Z exit 255 reason Unknown, no crash loop since).
target: "v5.9.5"                      # ghcr manifest HEAD 200 for v5.9.5 (index sha256:092e6ef8c388fcc9d8b52e8a5e04e6662f85b25ea3a0d4bb7d0d13e43a9b9c8d)
                                      # and v5.9.4 (sha256:bf2ef9706159c60f81a631030fb792e5ab809d872791ee5d0029a023212b48a7).
                                      # GitHub release v5.9.5: isDraft false, isPrerelease false, Latest.
update_type: minor
risk: low                             # stateless leaf exporter, one image-tag line, git-revert is a true rollback. What keeps it
                                      # from "trivial": the hop is 14 tagged releases (v5.6.0 ... v5.9.5), two of which FIX label
                                      # bugs on series our dashboards select (1.3), and one adds a per-poll controller API call (1.4).
est_duration_min: 25                  # commit+push 2, reconcile+rollout 3, >=6 min settle (60s scrape, 2m cache, 5m lookback
                                      # retires rollout twins), verification ~10, slack 4
needs_reboot: false
touches:
  namespaces: [monitoring]
  resources:                          # every object verified to EXIST live 2026-11-14
    - helmrelease/unpoller            # git edit: spec.values.image.tag v5.5.1 -> v5.9.5; chart stays 2.4.0
    - deployment/unpoller             # ROLLS ONCE (RollingUpdate, no PVC so no Multi-Attach exposure)
    - servicemonitor/unpoller         # unchanged; Prometheus must re-find the new pod
    - service/unpoller                # unchanged (hand-written, port named http)
    - "ghcr.io/unpoller/unpoller"
  shared: []                          # DELIBERATE: leaf exporter, restarts nothing shared. Off-cluster surface: one extra
                                      # authenticated GET per poll against the UniFi controller (1.4), no new login. Verification
                                      # READS Prometheus and the unpoller pod log; expressed in conflicts_with.
depends_on: []
conflicts_with:                       # checked 2026-11-14 against maintenance-plan.py --open and every plan frontmatter naming
                                      # `monitoring`/`unpoller`. Only this field is honoured by the scheduler.
  - kube-prometheus-stack-93.3.0      # restarts Prometheus, the instrument every gate in section 4 reads
  - flux-oci-chart-sources            # re-sources HelmReleases; its stage 8 parks unpoller, but it rolls flux-system sources
  - helm-drift-detection              # adds spec.driftDetection to EVERY HelmRelease incl. helmrelease/unpoller: same object
  - flux-reconciler-impersonation     # changes how Flux applies every Kustomization incl. this one
  - talos-linux-1.14.5                # node roll evicts the pod and Prometheus mid-gate (exclusive)
  - longhorn-1.13.0                   # exclusive storage move; Prometheus volumes re-attach (baseline gap)
  - coredns-1.50.5                    # unpoller reaches the controller and InfluxDB by name; a DNS blip reads as an exporter regression
  - mac-tooling-pins-2026-11          # SOFT: Mac-side tooling (kubectl/flux pins) used to run the gates
exclusive: false
security_ref: F-e4755b2b              # open security row on the CURRENT image, "newer upstream tag available". Detail stays in the
                                      # DB (policy-cli finding show F-e4755b2b). v5.9.5 is the newest tag, so this bump IS the
                                      # remediation we perform (bump, never rebuild; ghcr.io/unpoller is third-party). Whether
                                      # v5.9.5 clears the fixable count is checked in 2.6, not asserted here.
capability_change: false              # FACT: no new route, permission, exposure or config key; rendered delta is one image tag.
                                      # New exporters (per-WAN, console update availability, mesh/uplink fields) are additive
                                      # series from the same scrape; no new listener, no Secret change.
rollback_class: git-revert            # stateless; InfluxDB receives additive points only (1.5)
finding_refs: [F-464c9d8b]            # F-464c9d8b = open version-lane row "unpoller: image ... v5.5.1 -> v5.9.5 (minor)"
                                      # (re-read 2026-11-14). Script-owned: auto-closes when the pin moves; never close by hand.
                                      # F-e4755b2b is cited via security_ref, not claimed as owned.
review: ready-for-go@2026-11-16      # plan-reviewer 2nd pass 2026-11-16: ready-for-go, 0 blocking (1st pass needs-fix: 429/Influx/ERROR gates misfired; all three replayed live on 48h pod log and verified). Etcd must be quiet before the nightly slot (general window gate).
status: vetted
window: "now:2026-11-16"   # ON-DEMAND NOW run 2026-11-16 (run-now.py stamp; was None)
                                      # kube-prometheus-stack-93.3.0). Operator GO not required by class (capability_change false,
                                      # git-revert, low risk); the reviewer decides whether SD-10 applies.
premises:
  - id: live-image-is-v5.5.1
    why: "`current:` claims v5.5.1. Any other tag means the bump already landed (Renovate/Step 0 patch lane) or the plan is mis-based: verify per section 4 and retire, do not execute."
    run: kubectl get deploy unpoller -n monitoring -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: "ghcr.io/unpoller/unpoller:v5.5.1"
  - id: git-pin-is-v5.5.1
    why: "The step 3.2 edit targets exactly ONE `tag: v5.5.1` line. Zero or two matches = the file moved."
    run: "git show HEAD:kubernetes/apps/monitoring/unpoller/app/helmrelease.yaml | grep -c '^      tag: v5[.]5[.]1$'"
    expect_exact: "1"
  - id: chart-still-2.4.0
    why: "The chart-leg decision (stay on 2.4.0, keep the image.tag override) holds for chart 2.4.0 only."
    run: kubectl get helmrelease unpoller -n monitoring -o jsonpath='{.spec.chart.spec.version}'
    expect_exact: "2.4.0"
  - id: http-chart-repo-newest-still-2.4.0
    why: "If a v5-aware chart appears on our HTTP source the chart half must be re-assessed (the override might become droppable) before this runs. Measured 2026-11-14: newest 2.4.0, appVersion v3.5.0."
    run: "helm show chart unpoller --repo https://unpoller.github.io/helm-chart"
    expect_matches: '(?s)appVersion: v3\.5\.0.*version: 2\.4\.0|version: 2\.4\.0.*appVersion: v3\.5\.0'
  - id: helmrelease-ready
    why: "Never stack a bump on an already-failing release."
    run: kubectl get helmrelease unpoller -n monitoring -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: "True"
  - id: chart-service-still-disabled
    why: "Keeps chart 2.4.0's own Service (port `tcp`) from displacing the hand-written one (port `http`, which the ServiceMonitor scrapes)."
    run: kubectl get helmrelease unpoller -n monitoring -o jsonpath='{.spec.values.service.enabled}'
    expect_exact: "false"
  - id: chart-podmonitor-still-disabled
    why: "A second 30s scrape doubles UniFi controller API load (429 path) and duplicates every series, corrupting the 4.x counts."
    run: kubectl get helmrelease unpoller -n monitoring -o jsonpath='{.spec.values.podMonitor.enabled}'
    expect_exact: "false"
  - id: servicemonitor-scrapes-port-http
    why: "The ServiceMonitor scrapes `port: http`; the hand-written Service must still carry that name."
    run: kubectl get servicemonitor unpoller -n monitoring -o jsonpath='{.spec.endpoints[0].port}'
    expect_exact: "http"
  - id: no-env-on-workload
    why: "Config comes only from the upConfig secret file; env vars would re-open the config-library behaviour question (see 1.3 of the v5.5.0 lineage). Empty output is a PASS here, so the premise reads the container name too."
    run: kubectl get deploy unpoller -n monitoring -o jsonpath='{.spec.template.spec.containers[0].name}:{.spec.template.spec.containers[0].env}'
    expect_exact: "unpoller:"
  - id: pod-running-baseline
    why: "A baseline can only be taken from a running exporter."
    run: kubectl get pods -n monitoring -l app.kubernetes.io/name=unpoller -o jsonpath='{.items[0].status.phase}'
    expect_exact: "Running"
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/unifi-controller-rate-limit.md
  - docs/sops/monitoring.md
  - docs/sops/auto-update.md
  - docs/sops/verification-contents-not-shape.md
generated: "2026-11-14"
---

# unpoller: image v5.5.1 -> v5.9.5 (image minor; chart leg stays 2.4.0, override stays)

## 1) Summary & why held

**Why held.** The `*unpoller*` deny rule in `runbooks/auto-update-policy.yaml` carries `max: patch`: the pinned image tag
permanently outranks the chart appVersion, so image/chart minors go through the PLAN lane. Renovate PR #260 is the same
change as a one-line diff. The hold is a policy guard, not a known breaking change: nothing in the v5.6.0...v5.9.5 notes is
marked breaking. Risk call: **LOW**, unattended-capable window (nightly), operator GO not required by class.

### 1.1 What changes, and the chart half

**Image leg: one line.** `image.tag: v5.5.1 -> v5.9.5` in
`kubernetes/apps/monitoring/unpoller/app/helmrelease.yaml` (line 78) plus a lineage comment. No `upConfig` (secret) edit,
no policy edit, no ServiceMonitor/Service change.

**Chart leg: does NOT move; the `image.tag` override cannot be dropped.** Re-measured 2026-11-14: our HTTP source
(`https://unpoller.github.io/helm-chart`) still has newest stable chart **2.4.0 / appVersion v3.5.0**; the template renders
`image.tag | default .Chart.AppVersion`, so dropping the override would silently DOWNGRADE to v3.5.0. The OCI chart line
(2.5.0..2.8.0, appVersions v5.2.x/v5.3.0) is byte-identical in templates and would force a source move that
`flux-oci-chart-sources` stage 8 deliberately parks. The `*unpoller*` deny rule STAYS (its removal precondition, a chart at
or above the pinned tag, is unmet).

### 1.2 Upstream evidence (`gh api` release list + commit reads, 2026-11-14)

Releases between live and target, with the commits as published in the Renovate PR body and read from the commits themselves:

| Release | Content | Effect on us |
|---|---|---|
| v5.6.0 | fix(promunifi): export station counts with the right `station_type` and `tag`; feat(unas) SSD cache exporter; deps | **label-bug fix on a series we select** (1.3a); UNAS exporter inert (no UNAS device) |
| v5.6.1 | unifi lib v6.4.0, drop fork replace | transitive; same login path |
| v5.6.2 | fix(promunifi): export temperature and storage with the right labels; lint | **label-bug fix on a series we select** (1.3b) |
| v5.6.3 | fix(promunifi): USG mobile/handheld station counts | gateway counts now come from their own fields (1.3a) |
| v5.7.0 | feat: per-WAN latency, availability, status for UDM/UXG; deps | additive NEW series on our UDM (1.3c) |
| v5.8.0 | InfluxDB: drop `state` field from UDM access point; reuse fetched clients for DHCP lease association; datadog prefix | Influx field removal (1.5); DHCP-lease fix touches a log error we see today (1.6) |
| v5.8.1 / v5.8.2 | otel-only fixes; skip null system temperature sensors | otel inert (no `[otel]` block); null-temp skip is a robustness fix |
| v5.8.3 | datadog-only fix; docker/login-action | inert |
| v5.9.0 | unifi lib v6.6.0; keep configured scrapes independent of optional metrics; **expose UniFi OS console update availability** | one extra API call per poll (1.4) + new series |
| v5.9.1 | U5G APN/data-plan metrics; UAP uplink parent, mesh RSSI/signal, PHY rates | cellular inert (no U5G); UAP uplink/mesh series additive on our 4 APs |
| v5.9.2 | mask Influx token/OTel key in web server; verify api.ui.com cert in remote mode | masking is a hardening that also covers our `[influxdb]` token; remote mode is not used (local `url`) |
| v5.9.3 | `skip_device_tags` controller option; deps | opt-in key, default off, not set |
| v5.9.4 | feat: export when each neighbor AP was last seen (`unpoller_rogueap_last_seen`) | additive, only emitted when rogue-AP data is exported (1.4b) |
| v5.9.5 | fix: export PDU outlet `relay_state`/`cycle_enabled`; deps; docker/login-action | PDU inert (no PDU in live device types) |

No release marks anything breaking. **Not touched by any commit read:** `examples/up.conf.example` config contract keys we
use (`[unifi]`, `[[unifi.controller]]`, `[prometheus]`, `[influxdb]`; our decrypted `upConfig` key names, values never
printed, 2026-11-14: `dynamic, url, user, pass, sites, save_ids, save_dpi, save_sites, save_alarms, save_events,
save_anomalies, hash_pii, verify_ssl, http_listen, namespace, interval, disable, buffer, org, bucket, auth_token`).

### 1.3 The behaviour changes that DO reach us

**1.3a Station-count labels (v5.6.0 + v5.6.3).** Root cause upstream: `labels := append(baseLabels, tag)` aliased a shared
backing array, so station_type/tag labels could be overwritten by a later append. v5.6.0 adds `slices.Clip`; v5.6.3 fixes
the USG path that passed `d.UserNumSta`/`d.GuestNumSta` for the mobile and handheld arguments. Our selectors:
`unpoller_device_stations{station_type=~"desktop|user|mobile|guest|handheld"}` (usg-insights dashboard) and
`unpoller_device_stations/_radio_stations{station_type="user|guest"}` (usw-insights). **Expected: the gateway
`mobile`/`handheld` panels change value (they were mirroring user/guest counts); `user`/`guest` unchanged in meaning.** This is
a correction, not a regression, and the gate in 4.5 must NOT treat a value change there as failure (it asserts non-empty and
records before/after).

**1.3b Temperature/storage labels (v5.6.2).** Same alias class: `unpoller_device_temperature_celsius` `temp_area`/`temp_type`
(and storage `mountpoint`/`storage_name`) were mis-assigned for some device types. uap-insights panel "Device Temperature(s)"
selects `sum by (name,temp_area,temp_type) (unpoller_device_temperature_celsius ...)`. **Expected: the same devices still
emit a series; the label VALUES may change.** Gate asserts non-empty and the device names present, records the label sets.

**1.3c New per-WAN series (v5.7.0)** on our UDM: additive new families. They enter the family count; none shares a name with
an existing family (upstream adds descriptors, no renames).

### 1.4 The one operational change: one more controller API call per poll (v5.9.0)

`collectConsoleSystem` runs `c.Unifi.GetConsoleSystem()` after the Network poll when `c.APIKey == "" && !c.Remote`. We use
user/pass and a local URL, so **it will fire every poll**. Properties read from the commit: best-effort (error logged at
DEBUG "continuing", never fails the Network poll); uses the existing authenticated session (no new `POST /api/auth/login`,
which is the only endpoint the 429 throttle guards per `docs/sops/unifi-controller-rate-limit.md`). Risk is therefore a
slightly higher controller API load, not a login storm. Gate 4.6 watches real 429 text (anchored regex) and `Re-authenticating` against the measured
baseline, plus a positive `Measurements Exported` rate.

**1.4b Rogue-AP last seen (v5.9.4).** The controller keeps hundreds of neighbour APs. `unpoller_rogueap_*` is emitted only when
rogue-AP data is collected. Live 2026-11-14: `count({__name__=~"unpoller_(rogueap|console|wan|device_mbb|lte).*"})` = **30**
series today (this includes existing wan series); the pre-change NAME LIST is captured in 2.4 so the post-change diff names
exactly what is new. The ceiling check in 4.4 (series total <= 1.5x baseline) is the cardinality guard.

### 1.5 InfluxDB write side

`[influxdb]` is enabled (url/org/bucket/auth_token). v5.8.0 drops the `state` field from the UDM access-point measurement and
v5.7.0 adds WAN fields. No tag key is renamed in this hop (the v5.1.0 tag rename and the v5.2.8 `band` tag landed earlier).
In-repo dashboards are Prometheus-datasource (see helmrelease.yaml lineage comment); only operator-built Influx panels
selecting the UDM AP `state` field could go blank. Rolling back restores the field; points already written stay, additive.

### 1.6 Baseline noise measured (re-measured 2026-11-15, 48 h pod log, so gates are relative, not absolute)

- `Re-authenticating ... (poll error: ...)` INFO lines: **36**/48 h (about 0.75/h; GetClients/GetSites 5xx-class poll errors).
- `[ERROR]` lines: **16**/48 h, of which 14 are `failed to fetch clients for DHCP lease association` and **2** are non-DHCP, both
  from ONE event at 2026-11-14 15:38:35 (a `GetSites()` 401 after a session lapse): `Failed to collect events from controller`
  and `event fetch for InfluxDB failed`. The second contains the words "Influx" and "Unauthorized" but is the controller
  read path, NOT the InfluxDB write path (gate 4.8 excludes it by name).
- Literal ` 429` appears **4** times in 48 h, ALL benign INFO `UniFi Metrics Recorded ... Dur: 429ms` lines (a duration, not an
  HTTP status). Real 429 text count: **0**. Gate 4.6 uses an anchored regex for that reason.
- `UniFi Measurements Exported`: 2882/48 h; **12 per 10 min** live.
- Pod restarts: restartCount 2 on the CURRENT pod (last 2026-11-12T13:30:50Z, exit 255, `reason: Unknown`). The counter resets
  with the NEW pod, so the post-roll baseline is 0 (4.1/4.2), not 2; a restart of the new pod is a failure.

## 2) Pre-checks

All read-only. Run from the repo root. Scratch dir for baselines is a FIXED path (a `mktemp -d` value does not survive across Bash calls): every block that uses it
begins `SCR=/tmp/unpoller-5.9.5-scr; mkdir -p $SCR`. It is read again in section 4 and step 3.4.

2.1 Premises hold: `.venv/bin/python3 runbooks/plan-premises.py unpoller-5.9.5 --require-premises` (no `REFUSED`, all PASS).

2.2 Not stale: `.venv/bin/python3 runbooks/maintenance-plan.py --verify` must not list unpoller-5.9.5; and
`kubectl get deploy unpoller -n monitoring -o jsonpath='{.spec.template.spec.containers[0].image}'` still `...:v5.5.1`.

2.3 Target is real and still the newest. FAIL prints `curl` 404 or a different `Latest`.
```bash
gh release view v5.9.5 -R unpoller/unpoller --json isDraft,isPrerelease,tagName --jq '.tagName+" draft="+(.isDraft|tostring)+" pre="+(.isPrerelease|tostring)'
# PASS: v5.9.5 draft=false pre=false     (if a newer v5.9.x exists, retarget in place per README, keep plan_id)
T=$(curl -s "https://ghcr.io/token?scope=repository:unpoller/unpoller:pull" | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
curl -s -o /dev/null -w '%{http_code}\n' -I -H "Authorization: Bearer $T" -H "Accept: application/vnd.oci.image.index.v1+json" https://ghcr.io/v2/unpoller/unpoller/manifests/v5.9.5
# PASS: 200
```

2.4 Capture the BASELINE (Prometheus via port-forward, then kill it; PID is kept so cleanup cannot hit another process):
```bash
SCR=/tmp/unpoller-5.9.5-scr; mkdir -p $SCR
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 19090:9090 >/dev/null 2>&1 & PF=$!; sleep 4
q(){ curl -s --data-urlencode "query=$1" http://localhost:19090/api/v1/query; }
# a) family-name list + total series
q 'count by (__name__) ({__name__=~"unpoller_.*"})' | python3 -c "import sys,json;d=json.load(sys.stdin)['data']['result'];assert len(d)>250,len(d);open('$SCR/fam_before.txt','w').write('\n'.join(sorted(r['metric']['__name__'] for r in d)));print('families',len(d))"
q 'count({__name__=~"unpoller_.*"})' | python3 -c "import sys,json;v=json.load(sys.stdin)['data']['result'][0]['value'][1];open('$SCR/series_before.txt','w').write(v);print('series',v,'ceiling(1.5x)',int(float(v)*1.5))"
# b) device types
q 'count by (type) (unpoller_device_info)' | python3 -c "import sys,json;print(sorted((r['metric']['type'],r['value'][1]) for r in json.load(sys.stdin)['data']['result']))"
# c) the exact dashboard selectors that 1.3 says will change values
q 'count by (station_type) (unpoller_device_stations)'   > $SCR/stations_before.json
q 'count by (name,temp_area,temp_type) (unpoller_device_temperature_celsius)' > $SCR/temps_before.json
kill $PF
```
PASS (re-measured 2026-11-15): families **288**, series **8054** (2026-11-14 read 7521; the count drifts with client churn, which is why the 4.4 ceiling is computed from THIS capture, ceiling 12081 at 8054), types `uap 4, udm 1, usw 5`. FAIL: fewer than 250 families
(assertion in a)), or a missing device type: the exporter is already unhealthy; stop, do not stack the bump.

2.5 Pod and log baseline:
```bash
kubectl get pod -n monitoring -l app.kubernetes.io/name=unpoller -o jsonpath='{.items[0].metadata.name} restarts={.items[0].status.containerStatuses[0].restartCount} imageID={.items[0].status.containerStatuses[0].imageID}{"\n"}'
kubectl logs -n monitoring deploy/unpoller --since=1h | grep -c 'UniFi Measurements Exported'     # expect >= 55 (one per 60s)
kubectl logs -n monitoring deploy/unpoller --since=1h | grep -ciE 'HTTP 429|status.{0,12}429|too many requests|LIMIT_REACHED'   # expect 0
```
Record restarts (baseline 2 on this pod; the counter RESETS with the new pod, so 4.1 expects 0) and the imageID
`sha256:6d941ea1...`. FAIL: restarts increased since 2026-11-14, or the 429 grep prints >= 1: the controller rate-limit path
is already active, follow SOP section 4.3 first. The regex is anchored on purpose: a bare ` 429` matches the benign
`Metrics Recorded ... Dur: 429ms` INFO line (4 hits in 48 h, replayed 2026-11-15; the anchored regex gives 0 on the same
48 h log). Replay on a known-bad scratch set (`HTTP 429 Too Many Requests`, `AUTHENTICATION_FAILED_LIMIT_REACHED (status 429)`,
`poll error: 429 too many requests`, wording taken from SOP lines 26/188/279): **3 of 3 matched** (3 bad lines, 4 non-bad lines in the file).

2.6 Security cross-check (read-only, informational): `.venv/bin/python3 runbooks/policy-cli.py finding show F-e4755b2b`
(needs `SWEEP_PG_DSN`). After the roll, the next sweep's Trivy scan decides whether the fixable count cleared. Do NOT
hand-edit the finding. No scan result is asserted by this plan (v5.9.5 not scanned at authoring time).

2.7 Alerts quiet and no overlapping window work: `kubectl get helmrelease -A | grep -v True` shows nothing new, and no plan in
`conflicts_with` is scheduled into the same slot.

## 3) Steps

GitOps only. No `flux reconcile`, no `kubectl` mutation. Work on `main`.

3.1 Dry-test (done on a scratch copy at authoring time, BSD sed on macOS; result):
```
$ sed -i '' 's/^      tag: v5\.5\.1$/      tag: v5.9.5/' hr-copy.yaml
78c78
<       tag: v5.5.1
---
>       tag: v5.9.5
```

3.2 Two edits to `kubernetes/apps/monitoring/unpoller/app/helmrelease.yaml` (the sed changes ONLY the tag; the lineage comment
is a separate manual insert, there is no automation for it). First the sed, whose dry-run diff is in 3.1:
```bash
sed -i '' 's/^      tag: v5\.5\.1$/      tag: v5.9.5/' kubernetes/apps/monitoring/unpoller/app/helmrelease.yaml
```
Then, with the Edit tool, INSERT these four comment lines (6-space indent, same as the existing comment block) immediately
above the `      tag: v5.9.5` line (directly after the line `      # >= v5.5.0.`), replacing `NN` with the execution day:
```yaml
      # 2026-11-NN: v5.5.1 -> v5.9.5 image minor (plan unpoller-5.9.5, PR #260). Chart STILL 2.4.0 and this
      # override STAYS (no published chart ships appVersion >= v5.5). Deltas: station-count and
      # temperature/storage LABEL fixes (v5.6.0/.2/.3), per-WAN series (v5.7.0), one extra best-effort
      # console-system API call per poll (v5.9.0), rogueap last_seen (v5.9.4), PDU/UNAS/cellular inert.
```
```bash
git diff -- kubernetes/apps/monitoring/unpoller/app/helmrelease.yaml    # expect exactly: 1 changed tag line + 4 added comment lines, nothing else
```

3.3 Static gate before commit: `task kubeconform` passes, and
`helm template` is NOT required (values-only tag change; CI `Flate Render Gate` covers render).

3.4 Commit with `--only` (shared worktree), message file written BEFORE any gate:
```bash
SCR=/tmp/unpoller-5.9.5-scr; mkdir -p $SCR      # write $SCR/msg.txt BEFORE this call
git commit --only kubernetes/apps/monitoring/unpoller/app/helmrelease.yaml -F "$SCR/msg.txt"
git show --stat HEAD            # exactly one file
git log -1 --format=%s          # confirm the subject is YOURS before pushing
git push origin main
```
Subject: `chore(unpoller): image v5.5.1 -> v5.9.5 on chart 2.4.0 (plan unpoller-5.9.5)`. Renovate PR #260 closes itself.
Append the session's attribution lines.

3.5 Wait for Flux (webhook flow). Observe, do not force:
```bash
kubectl get deploy unpoller -n monitoring -o jsonpath='{.spec.template.spec.containers[0].image}{" ready="}{.status.readyReplicas}{" updated="}{.status.updatedReplicas}{"\n"}'
```
Poll until the image reads `:v5.9.5` with ready=1 updated=1 (budget 6 min). If the HR shows `Ready=False` with a
rollback, stop at section 5.

## 4) Verification

Settle first: **wait >= 6 minutes after the new pod is Ready** (60s scrape + 2m cache + 5m lookback; counting before
that reads rollout twins). Then re-open the port-forward (same `q` helper as 2.4, and `SCR=/tmp/unpoller-5.9.5-scr` again; the baselines are files there). Every gate states what FAIL looks like.

4.1 **The new generation is actually running** (rollout status green-lights the OLD generation; check the pod):
```bash
kubectl get pod -n monitoring -l app.kubernetes.io/name=unpoller -o jsonpath='{range .items[*]}{.metadata.name} {.spec.containers[0].image} {.status.containerStatuses[0].imageID} {.status.containerStatuses[0].restartCount}{"\n"}{end}'
```
PASS: exactly ONE line, image `ghcr.io/unpoller/unpoller:v5.9.5`, imageID digest NOT `6d941ea1...`, restarts 0 (the pre-roll pod's 2 does not carry over: restartCount is per pod).
FAIL prints: a second line (old pod lingering), the old image/digest, or restarts >= 1.

4.2 **No restart/crash in the settle window:** repeat 4.1 at the end of verification; PASS restarts still 0.
FAIL: `restartCount` 1+ (exit code in `.lastState.terminated`; config-parse failure after a library bump prints
`[ERROR]`/`FATAL` in `kubectl logs --previous`).

4.3 **Scrape is up and fresh (Prometheus, not the pod):**
`count(up{job=~".*unpoller.*"} == 1)` -> PASS `1`. FAIL: empty (target not found; ServiceMonitor/Service wiring broke) or `0`.
`unpoller_prometheus_cache_age_seconds` < 180 -> PASS; FAIL: empty or large (stuck cache).

4.4 **No metric lost, no cardinality blow-up** (the data-contents gate):
```bash
SCR=/tmp/unpoller-5.9.5-scr
q 'count by (__name__) ({__name__=~"unpoller_.*"})' | python3 -c "
import sys,json
after={r['metric']['__name__'] for r in json.load(sys.stdin)['data']['result']}
before=set(open('$SCR/fam_before.txt').read().split())
lost=sorted(before-after); new=sorted(after-before)
print('lost',lost); print('new',len(new),new[:40])
sys.exit(1 if lost or len(after)<len(before) else 0)"
q 'count({__name__=~"unpoller_.*"})' | python3 -c "
import sys,json
v=float(json.load(sys.stdin)['data']['result'][0]['value'][1]); b=float(open('$SCR/series_before.txt').read())
print('series',v,'ceiling',1.5*b); sys.exit(1 if v>1.5*b else 0)"
```
PASS: `lost []`, and total series <= 1.5 x the series count captured in 2.4 (`series_before.txt`; live 8054 gives 12081; the old
hard-coded 11,300 was 1.5 x a stale 7521). FAIL: any family listed under `lost` (a renamed/removed
metric: name it in the report, check the dashboards/rules grep from 1.3, revert), or the series total above the ceiling
(rogue-AP/neighbour cardinality, section 1.4b: revert, then plan `skip`/disable). `new` is informational and is expected
to be non-empty (1.3c, 1.4); an EMPTY `new` is a surprise worth a note, not a failure.

4.5 **Dashboard selectors still return data** (guards 1.3 without demanding unchanged values):
```bash
q 'count by (type) (unpoller_device_info)'                     # PASS uap 4, udm 1, usw 5 (same as 2.4b). FAIL: any type missing
q 'sum(unpoller_device_stations{station_type="user"})'         # PASS: a value > 0. FAIL: empty (label bug in the opposite direction)
q 'count by (station_type) (unpoller_device_stations)'         # compare with stations_before.json; PASS: user and guest still present; mobile/handheld may differ (1.3a)
q 'count by (name,temp_area,temp_type) (unpoller_device_temperature_celsius)'   # PASS: >= 1 series for each device name in temps_before.json; label values may differ (1.3b)
```
FAIL: any query EMPTY that was non-empty in 2.4, or a device name present in `temps_before.json` absent now. A mere
change of `temp_area`/`temp_type` values or of `mobile`/`handheld` counts is RECORDED in the report, not a failure.

4.6 **Controller load: no 429, no re-auth storm** (rate-limit SOP "Test 2", with real baselines):
```bash
L='kubectl logs -n monitoring deploy/unpoller --since=10m'
$L | grep -c 'UniFi Measurements Exported'                                               # PASS >= 8 (live 12 per 10 min). FAIL <= 7 (exporter stalled or polling slowed)
$L | grep -ciE 'HTTP 429|status.{0,12}429|too many requests|LIMIT_REACHED'              # PASS 0. FAIL >= 1 (stop; SOP 4.3; revert)
$L | grep -c 'Re-authenticating'                                                         # PASS <= 2 (baseline 36/48h = 0.75/h, ~0.1 per 10 min). FAIL >= 5 = storm
$L | grep '\[ERROR\]' | grep -vcE 'DHCP lease association|Failed to collect events from controller|event fetch for InfluxDB failed'   # PASS 0. FAIL >= 1
```
`Re-authenticating` and `Measurements Exported` are the positive pair: a stalled exporter shows Exported low with Re-auth ALSO
low (nothing polling), a storm shows Re-auth high. The last grep counts `[ERROR]` lines that are NOT one of the three known
baseline shapes (14 DHCP-lease lines plus the 2-line GetSites 401 event, 16 per 48 h in total). v5.8.0 may make the DHCP line
disappear: fine. A single baseline-shaped 401 pair in the window is therefore excluded, not a failure; any other ERROR is.

Replay (2026-11-15). Regexes: 429 = `HTTP 429|status.{0,12}429|too many requests|LIMIT_REACHED`; ERROR exclusion as above.
- Known-bad scratch file (7 lines: 3 real-429 shapes, 2 influx-write shapes, 1 baseline-shaped `Failed to collect events`,
  1 novel `[ERROR] something new and nasty`): 429 grep -> **3** (expect 3); ERROR grep -> **5** (expect 5: every ERROR except the
  baseline-shaped one; the novel line is caught).
- Live 48 h log (4373 lines): 429 grep -> **0** (the old ` 429` pattern printed **4**, all `Dur: 429ms`); ERROR grep after
  exclusion -> **0** (raw 16, so the exclusion removes exactly the 16 known lines and hides nothing else).
- Live last 10 min: Exported **12**, real-429 **0**, Re-authenticating **0**.
Also expect `UMBB: 0` to still appear in `Measurements Exported` (format kept since v5.5.0): its absence means the log
prefix changed, update the SOP greps, not a failure.

4.7 **Alerts:** `ALERTS{alertstate=~"firing|pending",alertname=~"Unifi.*"}` -> PASS empty. FAIL: `UnifiMetricsAbsent`,
`UnifiClientMetricsAbsent`, `UnifiControllerUnreachable` pending/firing (the `for: 15m` means a total outage shows here only
after 15 min: do NOT use this gate alone, 4.3/4.4 are the fast ones).

4.8 **InfluxDB write path:**
```bash
kubectl logs -n monitoring deploy/unpoller --since=10m | grep -iE 'influx.*(write|unauthorized|denied)' | grep -vic 'event fetch for InfluxDB failed'
```
PASS 0. FAIL >= 1 (token/org/bucket rejection or a schema/write error after the `state` field drop, section 1.5). Baseline
RESTATED 2026-11-15: the old `influx.*(error|fail|denied|unauthorized)` grep over 48 h is **1, not 0**: the
`event fetch for InfluxDB failed ... GetSites() ... 401 Unauthorized` line of 2026-11-14 15:38:35, which is the controller READ
path. The corrected gate narrows to the write verbs and excludes that one line shape by name. Replay: known-bad scratch lines
(`influxdb write failed: unauthorized: token invalid`, `influx: 403 Forbidden denied for org`) -> **2 of 2** matched; the
excluded shape in the scratch set is not counted; live 48 h log: raw match **1**, after exclusion **0**.

4.9 **Flux health unchanged:** `flux get helmreleases -n monitoring | grep unpoller` -> Ready True at the new revision;
`flux get kustomizations -A | awk 'NR==1 || $5 != "True"'` -> header only.

Close-out: record the new-family list and any label-value changes (4.5) in the commit follow-up or sweep note. Then retire this
plan per README (delete the file in the commit that records execution); `F-464c9d8b` auto-closes when the pin moves.

## 5) Rollback

Stateless exporter: no PVC, no migration. **Trigger:** any FAIL in 4.1-4.4 or 4.6, or a regression the operator names.

```bash
git revert --no-edit <bump-commit-sha>        # restores tag v5.5.1 and removes the lineage comment
git log -1 --format=%s                          # confirm the revert subject is YOURS
git push origin main
```
Confirm: `kubectl get deploy unpoller -n monitoring -o jsonpath='{.spec.template.spec.containers[0].image}'` -> `...:v5.5.1`,
one pod 1/1, restarts 0, and 4.3/4.4 pass against the 2.4 baseline (families 288, series about 8.0k (2.4 capture), types uap 4 / udm 1 / usw 5).
If the HelmRelease already auto-rolled back (`upgrade.remediation.strategy: rollback`), the git revert still has to land, or
Flux re-applies v5.9.5 on the next 30 min interval. InfluxDB points written by v5.9.5 remain (additive; the dropped `state`
field simply reappears under v5.5.1). If 429s appeared, follow `docs/sops/unifi-controller-rate-limit.md` section 4.3 (gateway
counter reset is operator-only) before re-trying any bump.

## 6) Interference notes

- **Attended window: NO.** Low risk, git-revert, no reboot, no data. Suits `nightly` 03:30 unattended; a human is needed only
  if a gate FAILs (then revert is mechanical).
- **Serialize with** every entry in `conflicts_with` (Prometheus is this plan's instrument; Flux/HelmRelease-wide plans change
  attribution). A same-night `kube-prometheus-stack-93.3.0` is the hard one: Prometheus is down 2-4 min and the 4.4 family diff
  would read false loss or false pass.
- **Step 0 coupling:** every window starts with the safe-update apply. The `*unpoller*` deny rule (`max: patch`) keeps Step 0 from
  moving this image minor, but it WILL allow a later v5.9.x patch via the direct-bump lane: if one lands first it only shrinks
  the reviewed delta, and the `live-image-is-v5.5.1` premise fails by design: re-baseline, do not force.
- **Off-cluster surface:** the UniFi controller (192.168.30.1) takes one extra authenticated GET per poll. Do not run this in the
  same slot as `unifi-device-firmware` work or a controller restart (a login blip would be misread as a 429 regression).
- **Downstream readers:** Grafana unpoller dashboards (5 ConfigMaps) and `prometheusrule/unpoller` read the series; neither
  restarts. `slo-burn-rate-alerts.yaml` references unpoller families: covered by 4.4's lost-family gate.
- **Third-party image rule:** v5.9.5 is a bump to the newest upstream tag. Never rebuild or patch the image; if CVE fixes are
  incomplete in v5.9.5, the answer is wait/replace/compensate per CLAUDE.md, not a rebuild.

---
plan_id: unpoller-v5.1.0
component: unpoller
pr: null                              # no open Renovate PR (deny-listed; verified 2026-08-28)
kind: image                           # image-only on chart 2.4.0 — see §1 for why that is now OK
current: "image v3.5.0 (chart 2.4.0)"
target: "image v5.1.0 (chart stays 2.4.0 unless a v5-aware chart ships — pre-check 2)"
update_type: major
risk: medium
est_duration_min: 30
needs_reboot: false
touches:
  namespaces: [monitoring]
  resources:
    - helmrelease/unpoller
    - "ghcr.io/unpoller/unpoller"
    - runbooks/auto-update-policy.yaml   # deny-rule reason retargeted in the same commit
  shared: [influxdb]                  # writes renamed tags/fields into influxdb2 bucket `default` (databases ns) — schema drift for any InfluxDB consumer, no restart of anything shared
depends_on: []
conflicts_with:
  - grafana-13.0.0                # same window + same namespace (monitoring).
                                  # Run AFTER grafana-13.0.0: this plan renames
                                  # influxdb tags/fields that grafana's
                                  # datasources read, and grafana's own
                                  # verification gate is "are the datasources
                                  # alive?". Going first would drift the data
                                  # under that gate and make a grafana failure
                                  # unattributable. Serialize, do not
                                  # interleave.
security_ref: F-a5ceabc1
capability_change: false              # scraper internals; all new v4/v5 features (UNAS, Protect) are opt-in and stay OFF
rollback_class: git-revert
finding_refs: [F-a5ceabc1]            # version-currency critical; the plan-or-page join keys on THIS field (the v4 plan only carried security_ref — that is why the finding read OVERDUE-UNPLANNED)
status: scheduled
window: "sat-attended:2026-09-19"      # matches the recorded operator approval
                                      # (decision `approve`, exec_state pending).
                                      # Was `null` until 2026-09-05 despite that
                                      # approval, so the reconciler could not see
                                      # it and ran NO capacity/interference check.
                                      # ORDER: run AFTER grafana-13.0.0 — see
                                      # conflicts_with.
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/monitoring.md
generated: "2026-08-28"
---

# unpoller: image v3.5.0 → v5.1.0 (image-only, chart stays 2.4.0)

Supersedes `unpoller-v4` (deleted in the commit that added this file). Upstream
moved past v4: v4.0.0/v4.0.1 (2026-08-19/23), then v5.0.1 + v5.1.0 (both
2026-08-27; there is no v5.0.0 GitHub release — the release tooling broke and
v5.0.1 fixed it). Target is **v5.1.0** — tag verified present on ghcr
(manifest HEAD 200, 2026-08-28).

## 1) Summary & why held

Held by the `*unpoller*` deny rule in `runbooks/auto-update-policy.yaml`
(chart/image lockstep: no chart templating for v4+ exists). Chart index as of
2026-08-28 — newest is still `2.4.0 -> appVersion v3.5.0 (2026-08-18)`.

**Posture change vs the v4 plan: the missing chart is no longer treated as a
blocker.** The v4 plan assumed "v4 binary against v3-shaped values" was the
lockstep trap. Chart 2.4.0 was pulled and inspected for this plan: it is a
version-agnostic wrapper — the Deployment mounts `up.conf` rendered verbatim
from OUR `upConfig` value (via `unpoller-credentials` secret) and runs the
image; no chart template encodes v3-specific config or flags. Our values
additionally disable the chart's Service, PodMonitor and dashboards (hand-written
`service.yaml`/`servicemonitor.yaml` own scraping). So the only chart↔image
coupling is `image.tag | default .Chart.AppVersion`, which we override. Waiting
for upstream is also open-ended (chart cadence: 2.1.0 Jan-2026 → 2.4.0
Aug-2026, published the day BEFORE image v4.0.0), while F-a5ceabc1 sits
critical. Image-only bump is sound; the deny rule stays and is retargeted (§3
step 4).

Breaking-change review for the actual v3.5.0→v5.1.0 span:

- **v4.0.0** — opt-in UNAS Pro support; `refactor(unas): replace disable flag
  with enable, defaulting to off`. We set neither flag → no config change.
  (We DO own a UNAS Pro at 192.168.55.240 — enabling `unas` metrics is a
  possible follow-up feature, deliberately NOT part of this window.)
- **v4.0.1** — fixes tx packets reported under `stat_rx_packets` (InfluxDB/
  DataDog outputs only; Prometheus unaffected).
- **v5.0.x** — bumps `github.com/unpoller/unifi` to v6 ("breaking change:
  FlexInt/FlexBool/FlexFloat replace nullable pointers") — internal API-parsing
  rework against the controller; this is the main regression surface for our
  UDM-Pro polling. Adds opt-in UniFi Protect metrics (`save_protect_devices`,
  gated by `protect_api_key`) — we don't run Protect; default off.
- **v5.1.0** — InfluxDB v3 support + **tag/field schema-collision fixes** that
  apply to ALL InfluxDB versions (upstream `pkg/influxunifi/MIGRATION.md`):
  `clients` tag `channel`→`channel_name`, `uap_radios` field
  `channel`→`channel_num`, duplicate fields `wan_ip`/`source`/`version` removed
  (remain tags) on `subsystems`/`usg`/`ubb`/`uci`/`udm`/`uxg`. This CHANGES the
  schema of what we write into the shared influxdb2 (`databases` ns, bucket
  `default`). Config compatibility confirmed against upstream README: with
  `version` omitted, `auth_token`+`org`+`bucket` still selects the v2 write
  path — our `[influxdb]` block needs no edit. Also fixes
  `default_site_name_override` in remote mode (we don't use remote mode).

In-repo Grafana dashboards (`app/dashboards/*.yaml`) are ALL Prometheus-datasource
(verified by grep), so the InfluxDB schema drift touches no committed dashboard;
only UI-created InfluxDB panels (if any) could reference renamed keys.

F-a5ceabc1 is a version-currency finding (section `version`), not a CVE
finding — no vulnerability detail exists to withhold; the record is cited via
`security_ref`/`finding_refs`.

## 2) Pre-checks

1. Baseline health — HR Ready, pod Running with 0 recent restarts:
   ```bash
   flux get helmrelease unpoller -n monitoring
   kubectl -n monitoring get pods -l app.kubernetes.io/name=unpoller
   ```
2. **Chart-index re-check** (decides image-only vs lockstep):
   ```bash
   curl -sL https://unpoller.github.io/helm-chart/index.yaml | python3 -c "
   import sys, yaml
   es = yaml.safe_load(sys.stdin)['entries']['unpoller']
   es.sort(key=lambda e: e.get('created',''), reverse=True)
   [print(e['version'],'->',e.get('appVersion'),'|',e.get('created','')[:10]) for e in es[:3]]"
   ```
   If a chart with appVersion v5.x now exists: diff its `values.yaml` against
   ours (the 2.1.0→2.4.0 move added a Service/PodMonitor that would have
   silently broken our scrape — see helmrelease.yaml comments) and bump chart
   `version:` + `image.tag` in the ONE commit of §3 instead.
3. Image tag still published: `HEAD https://ghcr.io/v2/unpoller/unpoller/manifests/v5.1.0`
   via token → expect 200 (was 200 on 2026-08-28).
4. Baselines for §4 (record the numbers):
   ```bash
   kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 &
   curl -s 'http://localhost:9090/api/v1/query?query=up{job="unpoller"}'            # expect 1
   curl -s 'http://localhost:9090/api/v1/query?query=count(unpoller_site_adopted)'  # expect >0 — record value
   # InfluxDB newest unpoller point (bucket `default`, influxdb2 in databases ns):
   kubectl port-forward -n databases svc/influxdb-influxdb2 8086:80 &
   # token: sops -d kubernetes/apps/monitoring/unpoller/app/secret.sops.yaml (auth_token)
   curl -s http://localhost:8086/api/v2/query?org=influxdata \
     -H "Authorization: Token $INFLUX_TOKEN" -H 'Content-Type: application/vnd.flux' \
     -d 'from(bucket:"default") |> range(start:-15m) |> filter(fn:(r)=>r._measurement=="uap_radios") |> keep(columns:["_time"]) |> last(column:"_time")'
   ```
5. No in-flight reconcile on `monitoring`: `flux get kustomizations -A | awk 'NR==1 || $5 != "True"'`.

## 3) Steps

1. Silence unpoller alerts for the rollout (attended-tier default,
   `docs/sops/application-update.md` step 1): namespace `monitoring`,
   alertname regex `Unifi.*|Kube(Pod|Deployment).*`, TTL 4h.
2. Edit `kubernetes/apps/monitoring/unpoller/app/helmrelease.yaml`:
   `image.tag: v3.5.0` → `image.tag: v5.1.0`. (Chart `version: 2.4.0`
   unchanged unless pre-check 2 found a v5-aware chart.) No `upConfig` secret
   edit is needed (§1: v2 InfluxDB selection is unchanged; new features stay
   opt-out).
3. **Do NOT remove the `*unpoller*` deny rule** — retarget its reason in
   `runbooks/auto-update-policy.yaml` (same commit). After this executes the
   live state is image v5.1.0 pinned on chart 2.4.0 (appVersion v3.5.0): the
   coredns shape, where a future chart bump scores as a safe minor and lands
   unattended while the pinned `image.tag` permanently outranks appVersion and
   chart templates change semantics between releases (2.4.0 itself added a
   Service that would have collided with our hand-written one). New reason,
   roughly: "image v5.1.0 pinned ahead of chart 2.4.0 (appVersion v3.5.0);
   chart bumps must go through the PLAN lane until a chart ships appVersion >=
   the pinned tag AND its values diff is re-vetted against our
   Service/PodMonitor overrides." Also fix the stale `plan unpoller-v4`
   pointer in the rule's comment → `unpoller-v5.1.0`.
4. Commit BOTH files together, shared-worktree safe:
   ```bash
   git commit --only kubernetes/apps/monitoring/unpoller/app/helmrelease.yaml \
     runbooks/auto-update-policy.yaml -m "feat(unpoller): image v3.5.0 -> v5.1.0 on chart 2.4.0 (plan unpoller-v5.1.0)"
   git show --stat HEAD   # only these two files
   git push
   ```
5. Let Flux reconcile on the webhook (no manual `flux reconcile`). Watch:
   `kubectl -n monitoring get pods -l app.kubernetes.io/name=unpoller -w`.
6. On success, delete this plan file in the follow-up close-out commit and
   expire the silence early.

## 4) Verification

`Ready=True` is not proof — a running unpoller that stopped emitting looks
identical to a healthy one. Wait ≥5 min after the new pod is Ready (scrape
interval 60s, poll interval 2m), then:

1. Pod Ready, 0 restarts, image is `ghcr.io/unpoller/unpoller:v5.1.0`
   (`kubectl -n monitoring get pod -l app.kubernetes.io/name=unpoller -o jsonpath='{.items[0].spec.containers[0].image}'`).
2. Logs show a successful UniFi controller login against 192.168.30.1, not an
   auth/parse-error loop — the unifi-lib v6 rework (§1) fails HERE if it fails.
3. **CONTENTS ASSERTION (Prometheus): the scraped series still arrive** —
   `up{job="unpoller"} == 1` AND
   `count(count_over_time(unpoller_site_adopted[5m]))` restricted to a window
   AFTER the rollout is > 0 and `count(unpoller_site_adopted)` matches the §2.4
   baseline. This fails if v5 renamed/killed the exporter output while the pod
   sits green. (Live prefix is `unpoller_` — the config sets
   `namespace = "unpoller"`.)
4. **CONTENTS ASSERTION (InfluxDB): the write path still advances** — re-run
   the §2.4 flux query; the newest `_time` on `uap_radios` must be NEWER than
   the pre-change baseline. A frozen timestamp = the schema-collision rework
   broke our v2 write path; that is the failure this line exists to catch.
5. Grafana UniFi dashboards (Prometheus-based, in-repo) render current data,
   not a flat line ending at the rollout.

## 5) Rollback

Revert the single commit and let Flux reconcile:

```bash
git revert <sha>            # restores image.tag v3.5.0 + the old deny-rule reason
git push
```

Confirm: pod image back on `v3.5.0`, §4.3 and §4.4 pass again. unpoller holds
no persistent state — it is a stateless scraper — so rollback loses only the
points from the bad window. InfluxDB needs no cleanup: v2 is schemaless-enough
that the old field/tag names simply resume alongside any v5-written points
(mixed keys in the bucket for the window's duration are cosmetic).

## 6) Interference notes

- **Blast radius if wrong:** UniFi observability only — `unpoller_*` series
  stop, the `unifi.*` alert groups go blind, InfluxDB unpoller measurements
  freeze. No workload, ingress, storage or auth path depends on unpoller.
- **Shared infra:** writes to the shared influxdb2 (`databases` ns, bucket
  `default`) with RENAMED tags/fields from v5.1.0 (§1 table). Nothing shared is
  restarted. Any operator-built InfluxDB Grafana panel referencing `channel` on
  `clients`/`uap_radios` or the removed duplicate fields will need repointing —
  in-repo dashboards are unaffected (all Prometheus).
- **UniFi controller load is unchanged** (same 2m poll cadence, background
  refresh already in place since v3.2.0) — no risk of 429ing the UDM-Pro.
- Do not co-schedule with anything that restarts kube-prometheus-stack in the
  same window: §4.3/§4.4 need a stable scrape/write pipeline to be meaningful.
- **Pre-existing, NOT this plan's scope, do not "fix" mid-window:** the
  `unifi.devices` alerts in `app/prometheusrule.yaml` match `unifipoller_*`
  while the exporter emits `unpoller_*` (verified against the live /metrics,
  2026-08-28: 0 `unifipoller_` series, 8148 `unpoller_` series) — every
  device-level alert there is inert today, before and after this upgrade. Only
  `UnifiControllerUnreachable` (`up{job="unpoller"}`) can fire. Reported
  upward for its own finding/fix.

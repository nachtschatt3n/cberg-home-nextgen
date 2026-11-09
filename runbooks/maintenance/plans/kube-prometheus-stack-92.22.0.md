---
plan_id: kube-prometheus-stack-92.22.0
component: kube-prometheus-stack
pr: 428                           # Renovate "feat(container): update kube-prometheus-stack ( 92.11.1 -> 92.22.0 )",
                                  # branch renovate/kube-prometheus-stack-92.x, OPEN, MERGEABLE, 4 checks SUCCESS incl.
                                  # Flate Render Gate (measured 2026-11-09). One-line diff in
                                  # kubernetes/apps/monitoring/kube-prometheus-stack/app/helmrelease.yaml. The PR is
                                  # held ONLY by the time-boxed deny rule in runbooks/auto-update-policy.yaml; this plan
                                  # is the deliberate, attended slot that rule asks for. PR #501 (-> 93.1.0, MAJOR) is
                                  # NOT this plan: section 6.3 lists what its own plan must check.
kind: chart
current: "92.11.1"                # MEASURED 2026-11-09: HelmRelease monitoring/kube-prometheus-stack, helm revision 50
                                  # (92.11.1, deployed 2026-10-26), revision 49 = 92.11.0 superseded (maxHistory 2)
target: "92.22.0"                 # OCI artifact oci://ghcr.io/prometheus-community/charts/kube-prometheus-stack:92.22.0,
                                  # digest sha256:f3987a327638427f4a4a514f2dd2f1065b8c1f89669ea8517627b67a56790601,
                                  # byte-identical to the classic-repo tgz I rendered (diff -r empty, 2026-11-09).
                                  # Chart appVersion v0.94.2. (Newer charts exist: 93.1.0 is PR #501.)
update_type: minor
risk: medium                      # NOT because of schema or values changes (there are none: section 1.3) but because
                                  # of blast radius: this restarts Prometheus, Alertmanager, the operator, kube-state-
                                  # metrics and all three node-exporters, i.e. the cluster's only alerting/verification
                                  # instrument, and it contains two subchart MAJORS (kube-state-metrics 9, node-exporter 5)
                                  # plus an untested-on-a-real-API-server secret-type migration (section 1.2 item 3).
                                  # Failure mode is "blind for minutes", not data loss: webhooks are failurePolicy Ignore,
                                  # no Prometheus remote-write exists, TSDB format is unchanged.
est_duration_min: 60              # 15 pre-checks + 3 commit/push + 12 hook/roll (operator, KSM, node-exporter x3,
                                  # Prometheus, Alertmanager) + 20 settle (alert `for:` guards are up to 15m) + 10 verify.
                                  # Fits a 90 min attended slot after Step 0 (20); leaves ~10 for a git-revert rollback.
needs_reboot: false
touches:
  namespaces: [monitoring]
  resources:                      # every object below verified to EXIST live 2026-11-09
    - helmrelease/kube-prometheus-stack          # chart version pin; the only git edit
    - configmap/kube-prometheus-stack-values     # READ-ONLY here: values are unchanged
    - deployment/kube-prometheus-stack-operator  # v0.94.1 -> v0.94.2, new cert paths (tls.crt/tls.key), RollingUpdate
    - deployment/kube-prometheus-stack-kube-state-metrics  # subchart 8.6.0 -> 9.0.0: nodeSelector kubernetes.io/os=linux (pod roll)
    - daemonset/kube-prometheus-stack-prometheus-node-exporter  # subchart 4.60.0 -> 5.0.0: seccompProfile RuntimeDefault (3-pod rolling, maxUnavailable 1, hostNetwork :9100, RAPL init container re-runs)
    - statefulset/prometheus-kube-prometheus-stack         # v3.15.0 -> v3.16.0-distroless + config-reloader v0.94.2; pod prometheus-kube-prometheus-stack-0 restarts
    - statefulset/alertmanager-kube-prometheus-stack       # v0.34.1 -> v0.34.2 + config-reloader; pod restarts
    - secret/kube-prometheus-stack-admission              # Opaque{ca,cert,key} -> kubernetes.io/tls (delete+recreate by the pre-upgrade hook, section 1.2 item 3)
    - validatingwebhookconfiguration/kube-prometheus-stack-admission  # caBundle re-patched by the post-upgrade hook (failurePolicy Ignore)
    - mutatingwebhookconfiguration/kube-prometheus-stack-admission    # same
    - crd/alertmanagerconfigs.monitoring.coreos.com   # all 10 monitoring.coreos.com CRDs re-applied by Flux CreateReplace;
    - crd/alertmanagers.monitoring.coreos.com         # schemas are IDENTICAL to the live ones (header annotation 0.94.1 -> 0.94.2 only, section 1.3)
    - crd/podmonitors.monitoring.coreos.com
    - crd/probes.monitoring.coreos.com
    - crd/prometheusagents.monitoring.coreos.com
    - crd/prometheuses.monitoring.coreos.com
    - crd/prometheusrules.monitoring.coreos.com
    - crd/scrapeconfigs.monitoring.coreos.com
    - crd/servicemonitors.monitoring.coreos.com
    - crd/thanosrulers.monitoring.coreos.com
    - pvc/prometheus-kube-prometheus-stack-db-prometheus-kube-prometheus-stack-0  # PV prometheus-tsdb, 30Gi longhorn-static RWO, re-attached by the same StatefulSet pod (no Multi-Attach: StatefulSet)
    - pvc/alertmanager-kube-prometheus-stack-db-alertmanager-kube-prometheus-stack-0  # PV alertmanager-kube-prometheus-stack, 1Gi; holds the silences + notification log
  shared: [monitoring, prometheus-instrument, alertmanager-routing]   # the window's own verification instrument + the
                                  # Telegram/claude-webhook alert path. NOT gateway/envoy: the alertmanager HTTPRoute and
                                  # Service are untouched. NOT storage/longhorn: no volume is created or moved.
depends_on: []
conflicts_with:                   # Built 2026-11-09 from every non-superseded plan whose frontmatter lists `monitoring` in
                                  # touches or whose gates read Prometheus (authoring rule 4). window-scheduler.py reads this
                                  # field in BOTH directions (window-scheduler.py:313-323), so the other plans need no edit.
  - talos-linux-1.14.5            # EXCLUSIVE node roll: evicts Prometheus (F-e8bb3113) and blinds its own gates
  - longhorn-1.13.0               # EXCLUSIVE storage engine: Prometheus/Alertmanager volumes re-attach
  - edot-collector-0.165.0
  - grafana-chart-14.4.0
  - helm-drift-detection
  - flux-oci-chart-sources        # re-sources every HelmRelease incl. this one
  - flux-reconciler-impersonation
  - envoy-gateway-1.10.0
  - envoy-proxy-config-distroless-v1.40.0
  - envoy-proxy-config-distroless-v1.40.2
  - etcd-timeouts-5000-500
  - talos-power-tuning-ab
  - descheduler-0.37.0
  - postgres-digest-refresh-2026-11
  - redis-fleet-8.10.3
  - tube-archivist-0.6.0
  - tube-archivist-elasticsearch-9.5.5
  - frigate-reolink-go2rtc-flv
  - otbr-0.4.0
  - otbr-thread-rcp-recovery
  - icloud-drive-fleet-2.3.0
  - nextcloud-12.0.2
  - nextcloud-mcp-0.203.0
  - nextcloud-mcp-0.204.0
  - nextcloud-mcp-0.206.0
  - grafana-chart-14.4.0          # names 12-12 as an attended fallback; Grafana queries the instrument this plan restarts
  - anythingllm-1.19
  - bitnamilegacy-exit-nextcloud-db
exclusive: true                   # "its own slot" is the whole point of the policy hold: no other change may be in flight,
                                  # including plans not written yet. Cost: one attended Saturday slot.
security_ref: F-7e7b8df7          # open image-scan findings against the CURRENT prometheus, alertmanager, operator and
                                  # config-reloader images (F-7e7b8df7, F-dd9a8523, F-e2c374bf, F-765d40f3), each with a
                                  # newer upstream tag. This bump moves all four. Detail stays in the DB; the next sweep's
                                  # scan of the running pods decides whether they close - this plan does not assert it.
capability_change: false          # Same behaviour, newer builds. Observable differences are hardening or chart plumbing:
                                  # Alertmanager stops sending CORS headers by default (no browser client here: section 1.2
                                  # item 5), admission secret becomes kubernetes.io/tls, node-exporter gains a seccomp
                                  # profile, KSM gets a Linux nodeSelector, the operator ClusterRole regains */finalizers
                                  # (restores permissions an earlier chart trimmed; upstream PR "Restore finalizer patch
                                  # permissions"). No new route, receiver, exposure, API or user-visible feature.
rollback_class: git-revert        # one commit revert; the two forward-only surfaces are analysed in section 5.3/5.4 and
                                  # neither is one-way (secret migration keeps the legacy keys; TSDB format unchanged).
finding_refs: [F-ec382720]        # "kube-prometheus-stack: chart 92.11.1 -> 92.22.0 (minor)", section version, last seen
                                  # 2026-11-08, action "held by auto-update-policy (*kube-prometheus-stack*) - PLAN lane".
                                  # F-e8bb3113 (node rolls blind Prometheus) is context for the slot choice, not answered here.
review: ready-for-go@2026-11-09   # plan-reviewer 2026-11-09: needs-fix (4.8 probe alert side effects) + 8 non-blocking items, all fixed; ATTENDED ONLY (the operator confirms the Telegram probe); last of a NOW queue, after every other NOW plan has settled
status: vetted
window: "sat-attended:2026-12-12"                      # RECOMMENDED SLOT: sat-attended:2026-12-12 (first slot with no ASSIGNED plan - grafana-chart-14.4.0 (nightly 11-11, attended fallback 12-12) and vaultwarden-1.37.5 (fallback 12-12) name it as a fallback, hence both are in conflicts_with: Saturdays
                                  # 11-14 open-webui+python-fleet, 11-21 coredns, 11-28 helm-drift, 12-05 edot-collector;
                                  # Sundays 11-15 longhorn, 11-22 talos, 11-29 redis, 12-06 n8n+vaultwarden, 12-13 flux-oci,
                                  # 12-20 postgres). 12-19 is the fallback. Not stamped: the window agent assigns it.
premises:
  # Re-checked at EXECUTION time. All RUN on 2026-11-09 while writing this plan.
  - id: helmrelease-still-pinned-92.11.1
    why: >-
      `current:` claims 92.11.1. If the PR was merged by hand or by Step 0 after someone narrowed the deny rule, the
      upgrade already happened (or is mid-flight) and section 3 is the wrong tool. Prints the actual pin when it fails.
    run: kubectl get helmrelease -n monitoring kube-prometheus-stack -o jsonpath='{.spec.chart.spec.version}'
    expect_exact: "92.11.1"
  - id: helmrelease-is-ready
    why: >-
      Never start from a HelmRelease that is already failing: a pre-existing Ready=False would be misattributed to this
      bump. Measured True 2026-11-09.
    run: kubectl get helmrelease -n monitoring kube-prometheus-stack -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: "True"
  - id: prometheus-still-v3.15.0
    why: >-
      Section 4.2 asserts the new version; this asserts the OLD one is what runs now, so the version gate can fail
      (a gate whose "before" is already the target proves nothing). Measured v3.15.0-distroless.
    run: kubectl get prometheus -n monitoring kube-prometheus-stack -o jsonpath='{.spec.version}'
    expect_exact: "v3.15.0-distroless"
  - id: admission-secret-still-opaque
    why: >-
      Section 1.2 item 3: the pre-upgrade hook migrates this Secret Opaque -> kubernetes.io/tls. If it is already
      kubernetes.io/tls something ran the new chart (or the hook) before us. Measured `Opaque ca cert key`.
    run: kubectl get secret -n monitoring kube-prometheus-stack-admission -o go-template='{{.type}} {{range $k,$v := .data}}{{$k}} {{end}}'
    expect_matches: '^Opaque ca cert key\s*$'
  - id: crds-still-at-0.94.1
    why: >-
      Section 4.3 asserts the CRD header annotation moved to 0.94.2; this asserts it is 0.94.1 now. Measured 0.94.1 on
      all 10 (prometheuses shown).
    run: kubectl get crd prometheuses.monitoring.coreos.com -o jsonpath='{.metadata.annotations.operator\.prometheus\.io/version}'
    expect_exact: "0.94.1"
  - id: rules-are-loaded-before-we-start
    why: >-
      Never roll the instrument while it is already not evaluating rules. Measured sum(prometheus_rule_group_rules)=547
      (129 groups, 456 alerting) on 2026-11-09. The awk `$1+0` coercion makes an empty result fail closed (RULES_LOW).
      Written with `<` because the premise sandbox refuses the greater-than character.
    run: kubectl get --raw '/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query?query=sum(prometheus_rule_group_rules)' | sed -E 's/.*"value":\[[0-9.]+,"([0-9]+).*/\1/' | awk '{print ($1+0<400)?"RULES_LOW":"RULES_OK"}'
    expect_exact: "RULES_OK"
  - id: all-monitoring-pods-settled
    why: >-
      A pod already CrashLooping/Pending in monitoring (e.g. left by Step 0) would confuse every gate. Counts pods that are
      neither Running nor Completed. Measured 0.
    run: kubectl get pods -n monitoring --no-headers | grep -c -v -e Running -e Completed
    expect_exact: "0"
  - id: three-nodes-ready-and-uncordoned
    why: >-
      node-exporter is a 3-pod DaemonSet with maxUnavailable 1 and hostNetwork; a cordoned/NotReady node (a node roll in
      flight) would stall the roll and blind a node. Measured 3 Ready, 0 SchedulingDisabled.
    run: kubectl get nodes --no-headers | grep -c ' Ready '
    expect_exact: "3"
  - id: no-node-cordoned
    why: Companion to the previous premise; grep -c prints 0 (exit 1 with output is still evaluated). The backup-freshness gate is deliberately NOT a premise - plan-premises.py refuses python3 - it is section 2.4 (runbooks/longhorn-backup-age.py).
    run: kubectl get nodes --no-headers | grep -c SchedulingDisabled
    expect_exact: "0"
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/monitoring.md
  - docs/sops/alertmanager-config-routing.md
  - docs/sops/backup.md
  - docs/sops/verification-contents-not-shape.md
generated: "2026-11-09"
---

# kube-prometheus-stack: chart 92.11.1 -> 92.22.0 (Prometheus 3.15.0 -> 3.16.0, Alertmanager 0.34.1 -> 0.34.2, operator 0.94.1 -> 0.94.2)

## 0) Execution class: ATTENDED ONLY

The window agent must run this plan ONLY with the operator present, whether in its dated slot or as an on-demand NOW run (the operator has asked for NOW, as the last of a queue; `window:` stays as recorded). Any derived AUTO-NIGHT / unattended label does not describe it: section 4.8 needs the operator to confirm a Telegram message and the plan is `exclusive` (nothing else may be in flight - in a NOW queue this plan runs LAST, after every other NOW plan has finished and settled).

## 1) Summary & why held

### 1.1 Why it was held

`runbooks/auto-update-policy.yaml` carries a TIME-BOXED deny rule `*kube-prometheus-stack*` (added 2026-11-02): the stack
is the shared verification instrument of every pending maintenance plan, so an unattended Step 0 bump would restart it
mid-run and blind their gates. The rule says "apply it deliberately, in its own slot, when no plan is mid-flight". This
plan IS that slot: `exclusive: true`, attended, nothing else scheduled with it. The chart change itself is a minor.

### 1.2 What actually changes (measured by rendering both charts with the LIVE values, 2026-11-09)

I pulled 92.11.1 and 92.22.0, rendered both with `helm template kube-prometheus-stack ... -n monitoring -f <live values from
configmap/kube-prometheus-stack-values>`, normalised the version labels and diffed. **22 hunks, 56 changed lines.** No
PrometheusRule, Service, dashboard ConfigMap or Alertmanager config object differs; exactly ONE ServiceMonitor differs (item 3b). The whole delta:

1. **Images.** Prometheus `v3.15.0-distroless` -> `v3.16.0-distroless`; Alertmanager `v0.34.1` -> `v0.34.2`;
   prometheus-operator and config-reloader `v0.94.1` -> `v0.94.2`; thanos default `v0.42.4` -> `v0.42.5` (not deployed);
   kube-webhook-certgen `1.11.0` -> `1.11.1`. kube-state-metrics (`v2.20.0`) and node-exporter (`v1.12.1-distroless`) are
   UNCHANGED images.
2. **Two subchart MAJORS, both harmless here.** kube-state-metrics chart 8.6.0 -> 9.0.0: its README "Upgrading to v9.0.0"
   says the default `nodeSelector` now includes `kubernetes.io/os: linux` and "triggers a pod rollout on upgrade"; all 3
   nodes are Linux. prometheus-node-exporter chart 4.60.0 -> 5.0.0: "Version 5.0.0 adds restrictive security context
   defaults ... `seccompProfile.type: RuntimeDefault` ... Host access is unchanged". Our `containerSecurityContext`
   override keeps `readOnlyRootFilesystem`, `allowPrivilegeEscalation: false`, `drop: [ALL]` and the render adds only
   `seccompProfile: RuntimeDefault`. The RAPL `permissionInitContainer` is unchanged (UID 0, CHOWN only). The grafana
   (14.0.1 -> 14.4.0) and windows-exporter subcharts are NOT deployed (`grafana.enabled: false`; Grafana is its own
   release `monitoring/grafana`, chart 14.0.1, untouched by this plan).
3. **Admission-webhook certificate Secret type changes (the one real risk).** Chart PR "use kubernetes.io/tls secret for
   admission webhook certificates": the create hook now runs `--secret-type=kubernetes.io/tls`, the hook Role gains
   `delete` on exactly `secrets/kube-prometheus-stack-admission`, and the operator reads `/cert/tls.crt` + `/cert/tls.key`
   (was `/cert/cert`, `/cert/key`). Upstream certgen PR #188 (v1.11.0): an existing Secret of another type "is deleted and
   recreated as `kubernetes.io/tls` with the same certificates ... Missing `ca.crt`/`tls.crt`/`tls.key` entries are copied
   from the legacy `ca`/`cert`/`key` entries; all existing entries ... are kept, so pods still mounting `/cert/cert` keep
   working"; delete uses UID+resourceVersion preconditions. **The PR text itself says "Not yet run against a real API server:
   the fake clientset enforces neither delete preconditions nor secret type validation."** That is why section 2.5 snapshots
   the Secret and section 4.5 asserts its contents. Blast radius if it misbehaves is small: all three webhooks are
   `failurePolicy: Ignore` (measured), and the old operator pod keeps serving while the new one is not Ready
   (Deployment RollingUpdate, 1 replica).
3b. **The operator's own ServiceMonitor changes its CA key** (`tlsConfig.ca.secret.key: ca` -> `ca.crt`, pointing at the same admission Secret). The operator target is scraped over https on :10250, so if the migrated Secret lacked `ca.crt` the operator target would go down: probe gates `targets_up_not_below_base` / `no_new_down_job` catch it, and 4.5 asserts `ca.crt` is present.
4. **Operator ClusterRole** gains `alertmanagers/finalizers`, `prometheusagents/finalizers`, `prometheuses/finalizers`,
   `thanosrulers/finalizers`; operator pod labels no longer carry the chart version (so the operator no longer restarts on
   every chart bump with no other change); `ServiceMonitor` template gains an optional `scrapeClass` (unset here).
5. **Alertmanager 0.34.2 release note:** "api: Alertmanager no longer sends CORS headers by default ... api/v2 now
   disallows cross-origin requests. This is a breaking change. `--web.cors.origin` restores the previous behaviour."
   I grepped for browser-side callers: Grafana reaches Alertmanager only through `access: proxy` datasources
   (server-side, `kubernetes/apps/monitoring/grafana/app/helmrelease.yaml`), the UI at the `alertmanager` HTTPRoute is
   same-origin behind Authentik, and the other consumers (ai-sre, openclaw-probe, alert-triage, ops-retro, health-check.sh)
   are server-side. No `--web.cors.origin` is needed; section 4.8 still exercises the UI path.
6. **Prometheus 3.16.0 release notes (2026-11-05)** - CHANGE entries: experimental search endpoints clamp `batch_size`;
   `--web.external-url` defaults to https only when `--web.config.file` enables TLS (we do not); subquery sample accounting
   in query stats; remote-write 2.0 `prometheus_remote_storage_metadata_*` metrics dropped; exemplar label uniqueness.
   I grepped `kubernetes/ runbooks/ docs/` for `prometheus_remote_storage_metadata`, `query_exemplars` and
   `prometheus_api_remote_write_without_metadata`: **zero uses**. There is no `remote_write`/`remote_read` in the running
   config (checked via `/api/v1/status/config`), so no Elasticsearch/remote-write exporter hangs off Prometheus: ES
   ingestion is the OTLP path through `edot-collector`, a separate release this plan does not touch. XOR2 chunk encoding
   (the only on-disk-format change in the 3.15/3.16 notes, "Stabilize the XOR2 float chunk encoding") is OPT-IN via
   `storage.tsdb.chunk_encoding.floats: xor2` and is NOT set here (`kubectl get prometheus ... -o jsonpath='{.spec}' | grep -c -i xor2` = 0),
   so blocks written by 3.16.0 stay readable by 3.15.0 (section 5.4). 3.16.0 is 4 days old at authoring; 3.15.1 exists on the old line.
7. **prometheus-operator v0.94.2 notes:** two [SECURITY] rebuilds only. **Chart-level UPGRADE.md has no 92.x -> 92.x entry**
   for this range (the only 92.x section is "91.x to 92.x", nodeSelector, already applied by our 92.11.1).

### 1.3 CRDs: how they are managed here, and what this bump does to them

`crds: enabled: true` in values; HelmRelease sets `install.crds: CreateReplace` and `upgrade.crds: CreateReplace`, so
**Flux's helm-controller (not Helm) replaces the 10 `monitoring.coreos.com` CRDs from the chart's `crds` subchart on every
upgrade** - proven live: all 10 carry annotation `operator.prometheus.io/version: 0.94.1`, the previous chart's version.
There is no `crds.upgradeJob` and no manual `kubectl apply` step in this range. I diffed
`charts/crds/crds/*.yaml` of 92.11.1 vs 92.22.0: **every difference is the two header lines** (source-URL comment and the
`operator.prometheus.io/version` annotation, 0.94.1 -> 0.94.2). Schemas are identical, so `metadata.generation` must NOT
move on any CRD (section 4.3 asserts exactly that; pre-values: alertmanagerconfigs 5, alertmanagers 6, podmonitors 32,
probes 32, prometheusagents 6, prometheuses 6, prometheusrules 2, scrapeconfigs 32, servicemonitors 32, thanosrulers 6).
NOT confirmed: that the LIVE CRD specs equal 92.11.1's. A server-side diff of live vs chart CRDs hits field-ownership conflicts with helm-controller, so equality is established chart-to-chart only (file diff above) plus the live annotation/generation. The 4.3 generation gate therefore fails closed: any `gen=` movement stops the run. CRDs cannot be downgraded safely in general (section 5.3) but this bump needs no downgrade path because nothing changes.

### 1.4 What we ship that must keep working (all measured 2026-11-09)

- **Prometheus:** 110 active targets, 109 up (the 1 down is `scrapeConfig/monitoring/arag-scrape` at the Mac mini: a
  known pre-existing alert, `AragScrapeDown`); 129 rule groups / 547 rules (456 alerting), 0 unhealthy; 85
  PrometheusRule objects, all carrying `release: kube-prometheus-stack` (a rule without it is silently never loaded -
  memory `prometheusrule_silent_ignore`); `ruleSelector` keeps that label constraint; ~350k head series; 7d / 20GiB
  retention on `prometheus-tsdb` (30Gi, 2 Longhorn replicas, healthy); last WAL replay took 14.6 s
  (`prometheus_tsdb_data_replay_duration_seconds`), process uptime 17 d. `prometheusSpec.resources` limit 6Gi.
- **Alertmanager:** v0.34.1, single replica (cluster status `disabled`), 1Gi volume holding silences + nflog; 9 ACTIVE
  silences (IDs recorded by the probe; they were created by `ops-console` and `alert-triage-agent`); config is generated
  from three AlertmanagerConfig objects (`monitoring/telegram`, `monitoring/claude-watch-webhook`, `storage/telegram`) via
  `alertmanagerConfigSelector` label `alertmanager-config: telegram` and `alertmanagerConfigMatcherStrategy: None`.
  Routes: Watchdog and InfoInhibitor -> `null`; critical/warning -> `telegram`. `alertmanager_config_hash` =
  94709764113048 (stable; the operator regenerates the same config, so the hash is a CONTENTS gate for routing).
- **SLO queries (sweep_history `slo_definitions`, 7 enabled; the probe gates 6 - `arag-push-freshness` is deliberately ungated: its source is already down and silenced, so it carries no signal about this change):** metrics `probe_success`, `monitor_status`,
  `longhorn_volume_robustness`/`longhorn_volume_state`, `up{job="mosquitto-metrics"}`, `unpoller_device_uptime_seconds`,
  `arag_scrape_last_push_success_timestamp_seconds`. None of these metric families is produced by a component this bump
  changes except through the scrape path (Prometheus itself). Baselines: dns 2/2, http 3/3, kuma 62/62, longhorn 75/75,
  mosquitto 1/1, unifi 10.
- **Dashboards:** Grafana (separate release) queries Prometheus/Alertmanager by Service name; Service names, ports and
  selectors are unchanged by the render diff.
- **node-exporter:** 3 targets up, `node_rapl_package_joules_total` on 3 nodes (the RAPL work of 2026-10-04),
  `count(node_scrape_collector_success == 0)` = 18 (pre-existing, per-node unsupported collectors; the gate is "not above 18").

## 2) Pre-checks

Run from the repo root on the Mac. Everything here is read-only except the scratch files under `$SCR`.

```bash
export SCR=${TMPDIR:-/tmp}/kps-window-$(date +%Y%m%d); mkdir -p "$SCR"; chmod 700 "$SCR"; echo "$SCR"
```

(Shell state does not persist between calls: re-export `SCR` in each one.)

1. **Slot is exclusive.** `.venv/bin/python3 runbooks/maintenance-plan.py --open` lists no other plan with the same
   `window:` as this one, and `.venv/bin/python3 runbooks/maintenance-plan.py --validate` is clean. If Step 0 of THIS
   window already bumped something in `monitoring` (grafana, blackbox, pushgateway, unpoller, uptime-kuma, headlamp,
   edot-collector, otel-operator), wait for its health gate and `kubectl get pods -n monitoring` all Running for 10 min;
   otherwise a failed gate is not attributable.
2. **The PR still means what this plan says.**
   `gh pr view 428 --json state,title,files --jq '{state,title,files:[.files[].path]}'` -> `OPEN`, title contains
   `92.11.1 → 92.22.0`, one file `.../kube-prometheus-stack/app/helmrelease.yaml`. If Renovate retargeted it (title shows
   92.23+), STOP: this is a drift refresh, re-read section 1.2 for the new range (`helm pull oci://ghcr.io/prometheus-community/charts/kube-prometheus-stack --version <new>` and repeat the render diff in 2.3). Also confirm the
   artifact: `helm pull oci://ghcr.io/prometheus-community/charts/kube-prometheus-stack --version 92.22.0` prints
   `Digest: sha256:f3987a327638427f4a4a514f2dd2f1065b8c1f89669ea8517627b67a56790601`.
3. **Re-render and re-diff against the LIVE values** (proves nothing moved since this plan was written):
   ```bash
   export SCR=${TMPDIR:-/tmp}/kps-window-$(date +%Y%m%d)
   kubectl get cm kube-prometheus-stack-values -n monitoring -o jsonpath='{.data.values\.yaml}' > "$SCR/vals.yaml"
   for v in 92.11.1 92.22.0; do mkdir -p "$SCR/$v"; (cd "$SCR/$v" && helm pull oci://ghcr.io/prometheus-community/charts/kube-prometheus-stack --version $v --untar >/dev/null)
     helm template kube-prometheus-stack "$SCR/$v/kube-prometheus-stack" -n monitoring -f "$SCR/vals.yaml" | sed -E 's/92\.(11\.1|22\.0)/CHART/g; s/kube-state-metrics-(8\.6\.0|9\.0\.0)/KSM/; s/prometheus-node-exporter-(4\.60\.0|5\.0\.0)/NE/' > "$SCR/r-$v.yaml"; done
   diff "$SCR/r-92.11.1.yaml" "$SCR/r-92.22.0.yaml" | grep -c '^[<>]'     # expect 56 (measured 2026-11-09)
   diff "$SCR/r-92.11.1.yaml" "$SCR/r-92.22.0.yaml" | grep -E '^[<>]' | grep -c -e 'alert:' -e 'expr:' -e 'record:' -e 'scrapeClass' -e 'endpoints:'   # expect 0 (no rule body or endpoint list changed)
   diff "$SCR/r-92.11.1.yaml" "$SCR/r-92.22.0.yaml" | grep -E '^[<>]' | grep -c 'key: ca'   # expect 2 (the one known ServiceMonitor change, item 1.2.3b: `key: ca` -> `key: ca.crt`); any other count = an unreviewed ServiceMonitor/Secret-key change
   grep -c 'alert:' "$SCR/r-92.22.0.yaml"                                  # positive control: the pattern DOES match the render (139 on 2026-11-09), so a 0 above is meaningful
   diff -r "$SCR/92.11.1/kube-prometheus-stack/charts/crds/crds" "$SCR/92.22.0/kube-prometheus-stack/charts/crds/crds" | grep -E '^[<>]' | grep -v -e '^[<>] #' -e 'operator.prometheus.io/version' | wc -l   # expect 0 (CRD schemas identical)
   ```
   The gates can fail: a changed line count or a non-zero rule/CRD residue means the chart or the values drifted; stop and
   re-read section 1.2. (Dry-run of these exact commands on 2026-11-09 printed 56 / 0 / 139 / 2 / 0; the CRD diff has 40 raw lines = 10 files x 4 header lines, all excluded by the filter.)
4. **Backups fresh.** `python3 runbooks/longhorn-backup-age.py prometheus-tsdb alertmanager-kube-prometheus-stack --max-hours 26`
   -> both `FRESH` (exit 0). The helper is the only accepted freshness gate (`python3 runbooks/tests/test-longhorn-backup-age.py` guards the shape; it printed `all passed` 2026-11-09). A TSDB restore is NOT part of the rollback
   (section 5.4) - the backup exists for the unforeseen.
5. **Snapshot the things that cannot be re-derived** (kept in `$SCR`, mode 700, NEVER copied into the repo; the Secret holds a
   private key; delete `$SCR` at the end of the window):
   ```bash
   export SCR=${TMPDIR:-/tmp}/kps-window-$(date +%Y%m%d)
   kubectl get secret kube-prometheus-stack-admission -n monitoring -o yaml > "$SCR/admission-secret.yaml"; chmod 600 "$SCR/admission-secret.yaml"
   helm get manifest kube-prometheus-stack -n monitoring > "$SCR/helm-manifest-rev50.yaml"
   kubectl get crd -o jsonpath='{range .items[?(@.spec.group=="monitoring.coreos.com")]}{.metadata.name} gen={.metadata.generation} ver={.metadata.annotations.operator\.prometheus\.io/version}{"\n"}{end}' | sort > "$SCR/crd-before.txt"; cat "$SCR/crd-before.txt"
   kubectl get pods -n monitoring -o wide > "$SCR/pods-before.txt"
   kubectl get prometheusrule -A --no-headers | wc -l; kubectl get prometheusrule -A -l release=kube-prometheus-stack --no-headers | wc -l   # equal (85 / 85 on 2026-11-09)
   ```
   Expect 10 CRD lines all `ver=0.94.1` with the generations listed in 1.3.
6. **Write the probe and take the BASELINE.** The probe is read-only and prints one `PASS`/`FAIL` token per gate.
   Write the script (copy exactly; the heredoc terminator must start in column 0):

```bash
export SCR=${TMPDIR:-/tmp}/kps-window-$(date +%Y%m%d)
cat > "$SCR/kps-probe.py" <<'PYEOF'
#!/usr/bin/env python3
"""kps-probe.py snap > f.json  |  kps-probe.py gate base.json now.json  (Prometheus :19090, Alertmanager :19093)"""
import json, sys, urllib.parse, urllib.request
P, A = "http://localhost:19090", "http://localhost:19093"
def get(u): return json.load(urllib.request.urlopen(u, timeout=30))
def q(e):
    r = get(P + "/api/v1/query?query=" + urllib.parse.quote(e))["data"]["result"]
    return [(x["metric"], float(x["value"][1])) for x in r]
def one(e):
    r = q(e); return r[0][1] if r else None
SLO = {
 "dns": ('count(probe_success{probe_class="dns"} == 1)', 'count(probe_success{probe_class="dns"})'),
 "http": ('count(probe_success{probe_class="http"} == 1)', 'count(probe_success{probe_class="http"})'),
 "kuma": ('count(max by (monitor_name) (monitor_status{monitor_type!="group"}) == 1)', 'count(max by (monitor_name) (monitor_status{monitor_type!="group"}))'),
 "longhorn": ('count(count by (volume) (longhorn_volume_robustness{state="healthy"} == 1))', 'count(count by (volume) (longhorn_volume_state{state="attached"} == 1))'),
 "mosquitto": ('max(up{job="mosquitto-metrics"})', 'count(up{job="mosquitto-metrics"})'),
 "unifi": ('count(count by (name) (unpoller_device_uptime_seconds > 0))', 'count(count by (name) (unpoller_device_uptime_seconds))'),
}
def snap():
    t = get(P + "/api/v1/targets")["data"]["activeTargets"]
    rg = get(P + "/api/v1/rules")["data"]["groups"]
    sil = [s["id"] for s in get(A + "/api/v2/silences") if s["status"]["state"] == "active"]
    al = get(A + "/api/v2/alerts")
    bi = q("prometheus_build_info")
    return {
     "targets": len(t), "up": sum(x["health"] == "up" for x in t),
     "down": sorted({x["labels"]["job"] for x in t if x["health"] != "up"}),
     "groups": len(rg), "rules": sum(len(g["rules"]) for g in rg),
     "rules_bad": sum(1 for g in rg for r in g["rules"] if r.get("health") != "ok"),
     "watchdog": 1.0 if any(m.get("alertname") == "Watchdog" for m, _ in q('ALERTS{alertstate="firing"}')) else None,
     "cfg_hash": one("alertmanager_config_hash"),
     "silences": sorted(sil),
     "firing": sorted({a["labels"]["alertname"] for a in al if a["status"]["state"] == "active"}),
     "prom_version": bi[0][0]["version"] if bi else None,
     "am_version": get(A + "/api/v2/status")["versionInfo"]["version"],
     "ne_up": one('count(up{job="node-exporter"} == 1)'), "ksm_up": one('count(up{job="kube-state-metrics"} == 1)'),
     "rapl": one("count(node_rapl_package_joules_total)"),
     "ne_fail": one("count(node_scrape_collector_success == 0)"),
     "head_series": one("prometheus_tsdb_head_series"),
     "slo": {k: [one(n), one(d)] for k, (n, d) in SLO.items()},
    }
def gate(b, n):
    ok = True
    def r(name, cond, detail=""):
        nonlocal ok; ok &= bool(cond); print(("PASS " if cond else "FAIL ") + name + (" " + str(detail) if detail else ""))
    r("targets_up_not_below_base", n["up"] >= b["up"], f'{n["up"]}>={b["up"]}')
    r("no_new_down_job", set(n["down"]) <= set(b["down"]), f'now={n["down"]} base={b["down"]}')
    r("rule_groups_equal", n["groups"] == b["groups"], f'{n["groups"]} vs {b["groups"]}')
    r("rules_equal", n["rules"] == b["rules"], f'{n["rules"]} vs {b["rules"]}')
    r("rules_all_healthy", n["rules_bad"] == 0, n["rules_bad"])
    r("watchdog_firing", n["watchdog"] == 1, n["watchdog"])
    r("am_config_hash_unchanged", n["cfg_hash"] is not None and n["cfg_hash"] == b["cfg_hash"], f'{n["cfg_hash"]} vs {b["cfg_hash"]}')
    r("silences_preserved", set(b["silences"]) <= set(n["silences"]), f'missing={sorted(set(b["silences"])-set(n["silences"]))}')
    r("no_new_firing_alert", set(n["firing"]) <= set(b["firing"]), f'new={sorted(set(n["firing"])-set(b["firing"]))}')
    r("node_exporter_all_up", n["ne_up"] == b["ne_up"] and b["ne_up"] == 3, n["ne_up"])
    r("ksm_up", n["ksm_up"] == 1, n["ksm_up"])
    r("rapl_on_3_nodes", n["rapl"] == 3, n["rapl"])
    r("node_collectors_failing_not_above_base", n["ne_fail"] is not None and n["ne_fail"] <= b["ne_fail"], f'{n["ne_fail"]} vs {b["ne_fail"]}')
    r("head_series_within_30pct", n["head_series"] and abs(n["head_series"] - b["head_series"]) <= 0.3 * b["head_series"], f'{n["head_series"]} vs {b["head_series"]}')
    for k in b["slo"]:
        bn, bd = b["slo"][k]; nn, nd = n["slo"][k]
        r("slo_" + k, nd and nd > 0 and nn is not None and nn / nd >= (bn / bd if bd else 0) - 0.02, f'{nn}/{nd} base {bn}/{bd}')
    return ok
if __name__ == "__main__":
    if sys.argv[1] == "snap": print(json.dumps(snap(), indent=1))
    else: sys.exit(0 if gate(json.load(open(sys.argv[2])), json.load(open(sys.argv[3]))) else 1)
PYEOF
```

Then the port-forward helper and the baseline (column 0 again so it pastes):

```bash
export SCR=${TMPDIR:-/tmp}/kps-window-$(date +%Y%m%d)
# port-forwards bind to ONE pod and die when it restarts: this helper is re-run after every Prometheus/Alertmanager roll
pf() { pkill -f 'port-forward.*1909[03]' 2>/dev/null; sleep 1
       kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 19090:9090 >/dev/null 2>&1 &
       kubectl port-forward -n monitoring svc/kube-prometheus-stack-alertmanager 19093:9093 >/dev/null 2>&1 &
       sleep 4; }
pf; python3 "$SCR/kps-probe.py" snap > "$SCR/base.json" && head -c 600 "$SCR/base.json"
python3 "$SCR/kps-probe.py" snap > "$SCR/now.json"; python3 "$SCR/kps-probe.py" gate "$SCR/base.json" "$SCR/now.json"; echo "exit=$?"
```

   Expected on 2026-11-09: `up` 109 of 110 targets, `down` = `["scrapeConfig/monitoring/arag-scrape"]`, 129 groups / 547
   rules, `watchdog` 1.0, `cfg_hash` 94709764113048.0, 9 silence ids, `firing` = `["Watchdog"]` (silenced alerts are
   `suppressed`, not `active`), `prom_version` 3.15.0, `am_version` 0.34.1, `ne_up` 3, `rapl` 3, `ne_fail` 18, 0 FAIL.
   **NEGATIVE CONTROL (the gate must be able to fail):** tamper a copy and require FAIL:

```bash
export SCR=${TMPDIR:-/tmp}/kps-window-$(date +%Y%m%d)
python3 - <<'EOF'
import json,os; p=os.environ["SCR"]; b=json.load(open(p+"/base.json")); b["rules"]+=1; b["cfg_hash"]+=1; b["silences"].append("deadbeef"); b["up"]+=2
json.dump(b,open(p+"/base-tampered.json","w"))
EOF
python3 "$SCR/kps-probe.py" gate "$SCR/base-tampered.json" "$SCR/now.json" | grep -c FAIL     # expect 4 (targets, rules, hash, silences)
```

   (Dry-run 2026-11-09: tampered baseline printed FAIL for `targets_up_not_below_base`, `rules_equal`,
   `am_config_hash_unchanged`, `silences_preserved`; a tampered `now` printed FAIL for `watchdog_firing`,
   `no_new_firing_alert`, `slo_dns`, `node_collectors_failing_not_above_base`.) Any FAIL on the un-tampered baseline = the
   instrument is already degraded: do not proceed.
   Also record the Alertmanager config text for a human diff if the hash ever moves:
   `curl -s localhost:19093/api/v2/status | python3 -c 'import sys,json; print(json.load(sys.stdin)["config"]["original"])' > "$SCR/am-config-before.yaml"`.
6b. **No baseline silence may expire during the run.** The 9 baseline silences end between 2026-11-08 and 2026-11-15 on 2026-11-09 and will have changed by the window. Right after taking `base.json`: `curl -s localhost:19093/api/v2/silences | python3 -c 'import sys,json,datetime as d; now=d.datetime.now(d.timezone.utc); print(sorted(s["endsAt"] for s in json.load(sys.stdin) if s["status"]["state"]=="active" and (d.datetime.fromisoformat(s["endsAt"].replace("Z","+00:00"))-now).total_seconds()<7200))'` must print `[]`. Any silence ending within ~2 h would expire mid-window and falsely FAIL `silences_preserved` / `no_new_firing_alert`: re-take the baseline after it expires (or after the operator extends it), do not proceed on it.
7. **Positive control for the alert-selector shape used in 4.7:** the probe's `watchdog` field (a selector on the `ALERTS` series for the always-firing Watchdog
   alert, which the chart ships and no repo manifest declares) is `1.0` in `base.json`, so a label matcher on `ALERTS` returns data; the repo-defined guards `ContainerMemoryMetricsAbsent` and
   `KumaMonitorMetricsAbsent` (`for: 15m` / `for: 10m`) are NOT in the baseline `firing` list.

## 3) Steps

All cluster changes are GitOps. No `flux reconcile`, no `helm`, no `kubectl apply/delete` in the happy path.

1. **Edit the pin** (BSD sed dry-tested on a scratch copy of `helmrelease.yaml` 2026-11-09; resulting diff is exactly one line):
   ```bash
   cd /Users/mu/code/cberg-home-nextgen
   F=kubernetes/apps/monitoring/kube-prometheus-stack/app/helmrelease.yaml
   sed -i '' 's/^\(      version: \)92\.11\.1$/\192.22.0/' "$F"
   git diff -U0 -- "$F" | grep '^[-+] '      # expect exactly:  -      version: 92.11.1   /   +      version: 92.22.0
   ```
2. **Commit only that file and verify the subject** (shared worktree - `--only`, then check the message is yours):
   ```bash
   printf 'chore(monitoring): kube-prometheus-stack 92.11.1 -> 92.22.0 (plan kube-prometheus-stack-92.22.0, attended slot)\n' > "$SCR/msg.txt"
   git commit --only "$F" -F "$SCR/msg.txt" && git log -1 --format=%s && git show --stat HEAD | tail -3
   ```
   The subject must be the one above and the stat must list only `helmrelease.yaml`; otherwise `git commit --amend` before pushing.
3. **Push.** `git push origin main`. The Flux webhook reconciles `kustomization/kube-prometheus-stack`; then
   `helmrelease/kube-prometheus-stack` upgrades at its next interval trigger (the Kustomization change makes the HR spec
   differ, so helm-controller acts immediately). Do NOT force-reconcile unless `kubectl get hr -n monitoring kube-prometheus-stack` still shows
   92.11.1 after 5 minutes. PR #428 closes itself (Renovate sees the pin on main) or `gh pr close 428 --comment "applied by plan kube-prometheus-stack-92.22.0"`.
4. **Watch the roll in this order** (bounded; each stage <= 5 min, whole roll ~12 min). Re-run `pf` (from 2.6) after stage d,
   because the port-forwards die with the Prometheus/Alertmanager pods:
   ```bash
   for i in $(seq 1 60); do kubectl get hr -n monitoring kube-prometheus-stack -o jsonpath='{.status.history[0].chartVersion} {.status.history[0].status} {.status.conditions[?(@.type=="Ready")].status}{"\n"}'; sleep 10; done
   kubectl get pods -n monitoring -w   # in a second terminal if attended: operator, KSM, node-exporter x3, prometheus-0, alertmanager-0
   ```
   a. **pre-upgrade hook** `job/kube-prometheus-stack-admission-create` runs certgen 1.11.1 (the Role is created first; the
      Job pod is GC'd after 60 s, so grab its log within a minute: `kubectl logs -n monitoring job/kube-prometheus-stack-admission-create` and keep it in `$SCR`).
   b. operator Deployment surges a new pod (v0.94.2, `/cert/tls.crt`); old pod stays until the new is Ready.
   c. KSM Deployment roll; node-exporter DaemonSet rolls one node at a time (`maxUnavailable 1`).
   d. operator rolls `prometheus-kube-prometheus-stack` (image v3.16.0-distroless; WAL replay last measured 14.6 s) and
      `alertmanager-kube-prometheus-stack` (v0.34.2); then the **post-upgrade hook** `kube-prometheus-stack-admission-patch` re-patches the webhook caBundle.
   Expected scrape gap on Prometheus restart: ~2-4 min total (termination + image pull + replay); no alert in this stack has a
   `for:` below 5 min, and Prometheus restores `ALERTS_FOR_STATE` across restarts (default outage tolerance 1h).
5. **Settle 20 minutes after Prometheus reports Ready** (needed: the `ContainerMemoryMetricsAbsent` guard has `for: 15m`, rate()
   windows are 5-15 m, and head series must refill). Do not run `runbooks/health-check.sh` during the roll: its Section 38 webhook
   probe POSTs empty bodies to the operator's admission routes and logs benign nil-deref panics (F-d410589c) that would read as
   upgrade damage.

## 4) Verification

Run after the settle. `pf` first. Every gate lists the failure it guards against.

1. **4.1 Flux/Helm.** `kubectl get hr -n monitoring kube-prometheus-stack -o jsonpath='{.status.history[0].chartVersion} {.status.history[0].status} {.status.conditions[?(@.type=="Ready")].status}'`
   must print `92.22.0 deployed True`; `helm history kube-prometheus-stack -n monitoring | tail -2` shows revision 51
   `deployed` and 50 `superseded`. Guards: remediation. A failed hook leaves `False`, or helm-controller rolls back to
   92.11.1 (history[0] then shows 92.11.1 with a higher revision) - the string compare fails in both cases.
2. **4.2 Versions that actually run** (CONTENTS ASSERTION: the live pods run the new builds, not just a Ready HR; pre-values were 3.15.0 / 0.34.1 / v0.94.1, so the compare can fail):
   ```bash
   kubectl get pods -n monitoring -o jsonpath='{range .items[*]}{.metadata.name}{" "}{range .spec.containers[*]}{.image}{" "}{end}{"\n"}{end}' | grep -E 'prometheus-kube|alertmanager-kube|operator-|state-metrics|node-exporter'
   ```
   Expect `quay.io/prometheus/prometheus:v3.16.0-distroless`, `quay.io/prometheus/alertmanager:v0.34.2`,
   `quay.io/prometheus-operator/prometheus-operator:v0.94.2`, config-reloader `v0.94.2` on BOTH stateful pods,
   KSM `v2.20.0`, node-exporter `v1.12.1-distroless` x3; and the probe's snapshot (4.4) shows `prom_version` 3.16.0 / `am_version` 0.34.2.
   Verify the rollout is of the NEW generation (a green rollout status can describe the old one): the pod `startTime` of
   prometheus-0, alertmanager-0 and the operator is later than the push.
3. **4.3 CRDs** (CONTENTS ASSERTION: all 10 re-applied AND no schema change).
   `kubectl get crd -o jsonpath='{range .items[?(@.spec.group=="monitoring.coreos.com")]}{.metadata.name} gen={.metadata.generation} ver={.metadata.annotations.operator\.prometheus\.io/version}{"\n"}{end}' | sort > "$SCR/crd-after.txt"; diff "$SCR/crd-before.txt" "$SCR/crd-after.txt"`
   must differ on EXACTLY 10 lines and ONLY in `ver=0.94.1` -> `ver=0.94.2`; any `gen=` change means a schema moved
   (contradicts section 1.3: stop and read the diff). Guards: helm-controller skipping CreateReplace (annotation stays 0.94.1) and an unexpected schema change.
4. **4.4 Instrument gate** (the main one). `export SCR=...; pf; python3 "$SCR/kps-probe.py" snap > "$SCR/after.json"; python3 "$SCR/kps-probe.py" gate "$SCR/base.json" "$SCR/after.json"; echo exit=$?`
   Expect 20 `PASS`, 0 `FAIL`, exit 0 (the `prom_version`/`am_version` fields differ from base by design and are asserted in 4.2).
   The tokens map to the failure each guards: `targets_up_not_below_base`/`no_new_down_job` (a ServiceMonitor or
   selector no longer matched, node-exporter/KSM not scraped after the roll), `rule_groups_equal`/`rules_equal`/
   `rules_all_healthy` (rules not loaded: the `release` label / `ruleSelector` regression or a bad rule file; live count 547/129 must be
   IDENTICAL since no rule changed), `watchdog_firing` (Prometheus not evaluating or Alertmanager not receiving),
   `am_config_hash_unchanged` (routing/receivers changed under the operator bump), `silences_preserved` (Alertmanager
   restarted onto an empty data dir: all 9 silences gone), `no_new_firing_alert`, `node_exporter_all_up` + `rapl_on_3_nodes` +
   `node_collectors_failing_not_above_base` (the seccomp profile blocked a collector or the RAPL init container did not re-run),
   `head_series_within_30pct`, `slo_*` (the 6 DB SLO numerators/denominators still return data and are not below baseline - 0.02).
   If `head_series_within_30pct` is the only FAIL within 10 min of Ready, wait another 10 and repeat once.
   CONTROL: metric up — targets_up_not_below_base reads `/api/v1/targets` (floor = baseline 109 up of 110)
   CONTROL: metric prometheus_rule_group_rules — rule count equality (baseline 547 rules / 129 groups, read via `/api/v1/rules`)
   CONTROL: metric alertmanager_config_hash — must equal the baseline 94709764113048 (a live-measured, exported metric)
   CONTROL: metric node_rapl_package_joules_total — count by node must be 3
   CONTROL: metric node_scrape_collector_success — failing collectors must be <= baseline 18
   CONTROL: metric prometheus_tsdb_head_series — within 30% of baseline ~350k
   CONTROL: metric probe_success — SLO dns 2/2 and http 3/3 not below baseline
   CONTROL: metric monitor_status — SLO kuma 62/62
   CONTROL: metric longhorn_volume_robustness — SLO longhorn 75/75
   CONTROL: metric unpoller_device_uptime_seconds — SLO unifi 10
   CONTROL: metric ALERTS — the always-firing Watchdog series must read 1 (positive control that the selector shape returns data)
   **NEGATIVE CONTROL for 4.4:** rerun the gate against `$SCR/base-tampered.json` from 2.6; it must print 4 FAIL and exit 1
   (proves the live instrument can still say FAIL after the roll, not just that it prints PASS).
5. **4.5 Admission webhook Secret migration** (CONTENTS ASSERTION: the Secret is the new type AND the webhooks carry its CA).
   `kubectl get secret -n monitoring kube-prometheus-stack-admission -o go-template='{{.type}} {{range $k,$v := .data}}{{$k}} {{end}}'`
   must print `kubernetes.io/tls ca ca.crt cert key tls.crt tls.key` (new keys present, legacy keys retained, per certgen PR #188;
   pre-state was `Opaque ca cert key`). Then
   `S=$(kubectl get secret -n monitoring kube-prometheus-stack-admission -o jsonpath='{.data.ca\.crt}'); [ -n "$S" ] && [ "$S" = "$(kubectl get validatingwebhookconfiguration kube-prometheus-stack-admission -o jsonpath='{.webhooks[0].clientConfig.caBundle}')" ] && [ "$S" = "$(kubectl get mutatingwebhookconfiguration kube-prometheus-stack-admission -o jsonpath='{.webhooks[0].clientConfig.caBundle}')" ] && echo CABUNDLE_MATCH || echo CABUNDLE_MISMATCH`
   -> `CABUNDLE_MATCH` (measured pre-state: both 756 chars; an empty `ca.crt` or an un-run patch hook prints MISMATCH).
   `kubectl get deploy -n monitoring kube-prometheus-stack-operator -o jsonpath='{.status.readyReplicas}'` = 1.
   Guards: the certgen migration failing on a real API server (the upstream tests used a fake clientset) and the operator mounting a cert path that does not exist.
6. **4.6 Operator is reconciling.**
   CONTROL: metric prometheus_operator_reconcile_errors_total — `sum(prometheus_operator_reconcile_errors_total)` must be 0 (pre: 0 on all controllers; the counter resets with the new pod, so 0 here means "no error since start").
   `curl -s 'localhost:19090/api/v1/query?query=min(prometheus_operator_ready)'` -> value `1`. Rule-object parity:
   `kubectl get prometheusrule -A --no-headers | wc -l` equals `kubectl get prometheusrule -A -l release=kube-prometheus-stack --no-headers | wc -l` (85 / 85 before) - the silent-never-loaded failure shape.
7. **4.7 Absent() guards and alert state** (20 min after Ready).
   CONTROL: alertname ContainerMemoryMetricsAbsent — must NOT be firing (`for: 15m`; fires if cadvisor/KSM series stay absent after the roll); positive control: the probe's `watchdog` field reads 1.0 (2.7).
   CONTROL: alertname KumaMonitorMetricsAbsent — must NOT be firing (`for: 10m`).
   `curl -s localhost:19093/api/v2/alerts | python3 -c 'import sys,json; print(sorted({a["labels"]["alertname"] for a in json.load(sys.stdin) if a["status"]["state"]=="active"}))'` must equal the baseline `firing` list (also asserted by `no_new_firing_alert`). A NEW alert that appeared during the roll and then resolved is fine; one still firing is not. These two absence gates have no demonstration of their own; they are backed by the probe's `no_new_firing_alert` negative control (4.4: a tampered `now` with an injected alert name prints FAIL), and the Watchdog read in 2.7 shows the `ALERTS` selector returns data.
8. **4.8 Alertmanager end to end** (ATTENDED ONLY; the operator is the gate). This posts ONE synthetic alert and has side effects the operator and window agent must expect:
   - the live config's FIRST route sends every alert to `claude-watch-webhook` (`continue: true`, group_wait 1s), so the probe also reaches the alert bridge, which types `[ALERT-PUSH] ... KpsUpgradeRouteProbe ... via alert-triage-agent` into the ops console (one automated triage turn; if the console is busy the bridge retries after ~15 min and sends a second Telegram "could not type" notice). **`[ALERT-PUSH] KpsUpgradeRouteProbe` is EXPECTED: the console / triage handler should dismiss it. Create NO silence and no alert-record for it, and silence nothing real.**
   - the operator receives a FIRING Telegram message and, because the Telegram receiver has `sendResolved: true`, a RESOLVED Telegram message when the alert ends (so two messages in total, plus the console push).
   - the `alertmanager_notifications_total` rise below is NOT specific to the probe (any other warning-route repeat inside the 90 s also bumps it). It is a floor, not the gate: **the operator's confirmation that the probe message arrived is the real gate.**
   CONTROL: metric alertmanager_notifications_total — `sum(alertmanager_notifications_total{integration="telegram"})` rises by >= 1 after the probe (necessary, NOT sufficient; operator confirmation decides).
   CONTROL: metric alertmanager_notifications_failed_total — `sum(alertmanager_notifications_failed_total{integration="telegram"})` must stay 0 (all integrations read 0 pre-roll).
   ```bash
   B=$(curl -s 'localhost:19090/api/v1/query?query=sum(alertmanager_notifications_total%7Bintegration%3D%22telegram%22%7D)' | python3 -c 'import sys,json; r=json.load(sys.stdin)["data"]["result"]; print(r[0]["value"][1] if r else 0)'); echo before=$B
   post() { curl -s -XPOST localhost:19093/api/v2/alerts -H 'Content-Type: application/json' -d "[{\"labels\":{\"alertname\":\"KpsUpgradeRouteProbe\",\"severity\":\"warning\",\"namespace\":\"monitoring\"},\"annotations\":{\"summary\":\"maintenance plan kube-prometheus-stack-92.22.0 route probe - ignore\"},\"endsAt\":\"$1\"}]"; }
   post "$(date -u -v+10M +%Y-%m-%dT%H:%M:%SZ)"
   sleep 90   # first notification of a new group goes out at group_wait (1s); Prometheus scrapes Alertmanager every 30s
   curl -s 'localhost:19090/api/v1/query?query=sum(alertmanager_notifications_total%7Bintegration%3D%22telegram%22%7D)' | python3 -c 'import sys,json; print("after=",json.load(sys.stdin)["data"]["result"][0]["value"][1])'
   ```
   Ask the operator to confirm the FIRING message arrived. **CLEANUP (always, pass or fail):** resolve the probe immediately by re-posting it with `endsAt` = now: `post "$(date -u +%Y-%m-%dT%H:%M:%SZ)"`; the RESOLVED Telegram message follows within seconds (tell the operator to expect it). Then confirm it is gone: `curl -s localhost:19093/api/v2/alerts | grep -c KpsUpgradeRouteProbe` must print `0` within ~1 min (the check can fail: before cleanup it prints >=1).
   Pass: operator confirms the firing message AND `after` >= `before` + 1 AND cleanup shows 0. If the counter does not rise, read `kubectl logs -n monitoring alertmanager-kube-prometheus-stack-0 -c alertmanager --tail=50 | grep -i -e error -e telegram`. Sanity floor (not a gate): `kubectl get httproute -n monitoring alertmanager -o jsonpath='{.status.parents[0].conditions[?(@.type=="Accepted")].status}'` = `True`.
9. **4.9 Storage unchanged.** `kubectl get pvc -n monitoring | grep -e prometheus-kube-prometheus -e alertmanager-kube-prometheus` both `Bound`, same
   volumes (`prometheus-tsdb` 30Gi, `alertmanager-kube-prometheus-stack` 1Gi); `kubectl get volume -n storage prometheus-tsdb alertmanager-kube-prometheus-stack -o custom-columns=N:.metadata.name,ROB:.status.robustness,STATE:.status.state`
   -> `healthy`/`attached`. Guards: a detach that did not re-attach.
10. **Pass = 4.1-4.8 all green.** Then delete `$SCR` (`rm -rf "$SCR"`; it contains the admission private key snapshot) and
    stop the port-forwards (`pkill -f 'port-forward.*1909[03]'`).

## 5) Rollback

Decide within 15 minutes of the first failing gate; do not diagnose forward in the window.

1. **Normal path - revert the one commit:**
   ```bash
   cd /Users/mu/code/cberg-home-nextgen
   git revert --no-edit <the-sha-from-step-3.2> && git log -1 --format=%s    # confirm it is the revert before pushing
   git push origin main
   ```
   Flux then upgrades the release BACK to chart 92.11.1 (helm revision 52); the pod set rolls through the same sequence
   in reverse. Confirm with 4.1 (expect `92.11.1 deployed True`), 4.2 (old image tags) and 4.4 against `base.json` (the same
   20 gates; `prom_version`/`am_version` return to 3.15.0/0.34.1). **Do NOT use `helm rollback` by hand:** the HelmRelease
   still pins 92.22.0, so helm-controller would simply upgrade again on the next reconcile.
2. **If the helm upgrade itself fails** (hook failure, timeout 15m), helm-controller auto-remediates (`upgrade.remediation.retries: 3`, default strategy `rollback` to revision 50). `kubectl get hr -n monitoring kube-prometheus-stack` then shows `Ready=False` with a retries message
   while the cluster is back on 92.11.1 pods. Still do step 1, or the controller keeps retrying the failing target.
3. **CRDs.** CRD downgrade is not supported in general (a CRD cannot drop a field that stored objects use, and Helm itself never
   downgrades CRDs; only Flux's CreateReplace re-applies them). It is not needed for THIS rollback: the 92.22.0 CRD schemas
   are identical to 92.11.1's (section 1.3, generations asserted unchanged in 4.3), so the revert re-applies the old header
   annotation over an identical schema. If 4.3 ever shows a `gen=` change, that statement is false and the rollback needs a
   manual look before step 1.
4. **Admission Secret (forward-only surface).** After the upgrade the Secret is `kubernetes.io/tls` and KEEPS the legacy `ca`/`cert`/`key`
   entries (certgen PR #188), so the 92.11.1 operator (which reads `/cert/cert`, `/cert/key`) starts against it, and the 92.11.1
   create hook (certgen 1.11.0 without `--secret-type`) only checks existence and leaves it alone. Verify after the revert:
   `kubectl get deploy -n monitoring kube-prometheus-stack-operator -o jsonpath='{.status.readyReplicas}'` = 1. Last resort if the
   operator is CrashLooping on the cert: `cp "$SCR/admission-secret.yaml"` is a snapshot of the ORIGINAL Opaque Secret, but
   re-applying it is not possible (type is immutable): instead `kubectl delete secret -n monitoring kube-prometheus-stack-admission`
   and let the next pre-upgrade hook recreate it (webhooks are failurePolicy Ignore, so PrometheusRule/AlertmanagerConfig
   admission degrades to "unvalidated" for the minutes this takes - Prometheus's own rule loader remains the gate).
5. **TSDB / Alertmanager data.** Prometheus 3.16.0 writes the same block and chunk format as 3.15.0 here (XOR2 is opt-in and not
   enabled: `grep -c -i xor2` of the Prometheus spec = 0), so 3.15.0 reads the volume back; Alertmanager 0.34.2 -> 0.34.1 is a
   patch with no data-dir change (silences + nflog persist on the 1Gi PVC; 4.4 `silences_preserved` re-asserted after the revert).
   If a restart ever reports a corrupt WAL (`prometheus_tsdb_wal_corruptions_total` > 0), the data is metrics-only with 7 d
   retention: restore `prometheus-tsdb` from the Longhorn backup per `docs/sops/backup.md` (volume name `prometheus-tsdb`,
   freshness via `runbooks/longhorn-backup-age.py`) or accept the loss; the cost of losing it is blind history, not a fault.

## 6) Interference notes

1. **This plan is `exclusive: true` and lists every monitoring-touching plan in `conflicts_with`** so the scheduler keeps the slot
   to itself in both directions. Reason: Prometheus is down ~2-4 min, Alertmanager ~1 min, KSM/node-exporter gaps of seconds to a
   minute each. Any plan reading Prometheus in the same window would record a baseline across a restart and read a false
   regression (or a false pass on an empty result). `talos-linux-1.14.5` and `longhorn-1.13.0` are exclusive on their own and
   additionally evict/re-attach these exact volumes (F-e8bb3113: a node roll already left Prometheus with no samples for a
   reboot window). Pick a slot with no plan: the recommendation in `window:` is `sat-attended:2026-12-12`.
2. **Step 0 still runs first in the window** (safe-update apply). It cannot touch this chart (deny rule `*kube-prometheus-stack*` stays in
   force until the operator edits it), but it can bump other `monitoring` components; section 2.1 requires 10 quiet minutes after it.
3. **Follow-on, NOT this plan - PR #501 (-> 93.1.0, MAJOR).** It must be its own plan, after this one lands (the major would
   otherwise stack on three untested subchart/secret changes). What I measured and what that plan must check:
   - **Operator v0.95.1** (appVersion v0.95.1). Release notes for v0.95.0 add AlertmanagerConfig route `labels`, global Telegram
     `botToken`, `extraScrapeMetrics`, `alertmanagerConfigFileSystemMode`, a new `StatusForConfigurationResources` surface, distroless
     images, and bug-fix validation of receivers (PagerDuty/Webex/MSTeamsV2). Read v0.95.0 AND v0.95.1 notes fully for breaking entries.
   - **CRD changes are REAL this time.** Diffing 92.22.0 vs 93.1.0 `charts/crds/crds`: controller-gen v0.22.0 -> v0.23.0, new fields (route `labels`,
     `extraScrapeMetrics`, `alertmanagerConfigFileSystemMode`) and **a new `x-kubernetes-validations` rule in
     `crd-alertmanagerconfigs.yaml` (~line 10706) requiring `httpConfig.authorization` or `httpConfig.bearerTokenSecret`** on an
     httpConfig-bearing receiver. Our three AlertmanagerConfigs (`monitoring/telegram`, `monitoring/claude-watch-webhook` (a webhook receiver),
     `storage/telegram`) must be server-side dry-run validated against the new CRD BEFORE the bump, or the operator may stop
     reconciling the one object and the Alertmanager config silently loses a receiver. UPGRADE.md says to apply the CRDs with
     `kubectl apply --server-side` first for "traditional" upgrades; here CreateReplace does a replace - confirm that is sufficient or switch the plan to a server-side apply step.
     CRDs do not downgrade: this plan needs a forward-fix rollback story and an AlertmanagerConfig export taken first.
   - **Removed values:** none (values.yaml 92.22.0 -> 93.1.0 only ADDS `alertmanagerSpec.alertmanagerConfigFileSystemMode` and `prometheusSpec.extraScrapeMetrics`; nothing changed or removed). Rendered with our values the delta is operator/reloader image `v0.94.2 -> v0.95.1`, and the operator ClusterRole
     (`alertmanagerconfigs/status` added, `delete` on core `pods` removed).
   - **Alertmanager config:** hash gate (`alertmanager_config_hash`) must be re-baselined AFTER reading whether 0.95 regenerates the config differently; keep the `silences_preserved` gate.
   - Re-run the whole 2.3 render-diff method (it is the cheapest way to see what a chart bump really changes), re-grep `runbooks/ kubernetes/` for metrics named in the notes, and keep the same exclusive slot discipline.
4. **After success, a decision for the operator (not made here):** the deny rule has no `max:`. Narrowing it to `max: patch` (as done for mariadb/longhorn)
   would let future patch bumps of the stack ride Step 0 again; the rule's own text asks for a revisit by 2026-11-30, which falls BEFORE the
   recommended slot, so either extend it or accept that #428 may need a Renovate rebase (the plan's pin is explicit: `92.22.0`).
   The rule's comment said "92.11.1 -> 92.17.0" and "revisit no later than 2026-11-30"; both were corrected in the working tree (comment + revisit date 2026-12-31, no rule semantics change) - uncommitted, to ride with the operator's next policy commit.
5. **Repo observations for the reviewer:** (a) REPO CORRECTION (docstring fixed in the working tree, test passes): the `runbooks/longhorn-backup-age.py` docstring ("Premise form: run: python3 runbooks/longhorn-backup-age.py ...") was wrong - `plan-premises.py` REFUSES `python3` (`REFUSED: 'python3' is not an allowed read command`, measured 2026-11-09 against this plan), so any plan that follows the docstring has a premise that can never pass; the freshness gate belongs in the section 2 pre-checks, as here. (b) Both stateful volumes carry `recurring-job-group.longhorn.io/default`, so they ride `daily-backup-all-volumes` (cron `0 23 * * *` UTC) - the 26 h bound matches that cadence. (c) The deny-rule comment in `auto-update-policy.yaml` still reads "92.11.1 -> 92.17.0"; the PR is now 92.22.0.

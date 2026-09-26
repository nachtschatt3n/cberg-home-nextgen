---
plan_id: kube-prometheus-stack-91.4.1   # ID KEPT at 91.4.1 on the 2026-09-25 retarget to
                                        # 91.5.2: 21 other plans name this id in
                                        # conflicts_with/prose, and --validate fails the
                                        # WHOLE set on an unresolvable ref. Rename the file
                                        # + id only in a coordinated pass over all 21.
component: kube-prometheus-stack
pr: null                              # no Renovate PR — coverage.py direct-bump lane
                                      # routed it to PLAN ("major — needs an assessed
                                      # window plan"). Sweep finding F-f1e564f2 was
                                      # filed at 91.2.1; the target moved to 91.4.0
                                      # (2026-09-14) and then to 91.4.1 (2026-09-16).
                                      # RETARGETED 91.4.0 -> 91.4.1 on 2026-09-20 (target:
                                      # below carries the measurement). 91.4.1 is the newest
                                      # 91.x on the prometheus-community index as of
                                      # 2026-09-20. If a later 91.x exists at window time,
                                      # re-read its release notes and bump `target:` — the
                                      # 90.0.0 premise still holds.
                                      # RETARGETED 91.4.1 -> 91.5.2 on 2026-09-25 (sweep
                                      # stale-target report). 91.5.2 is the newest 91.x on
                                      # the index; NO 92.x exists (index read 2026-09-25).
kind: chart
current: "90.0.0"                     # live: helm revision 40 (2026-09-22, still chart
                                      # 90.0.0), operator v0.93.1 — re-read 2026-09-25
target: "91.5.2"                      # released 2026-09-24, operator v0.94.1. MEASURED
                                      # 2026-09-25 by diffing the 91.4.1 and 91.5.2 chart
                                      # tarballs: (1) appVersion v0.94.0 -> v0.94.1 (upstream
                                      # v0.94.1 = ONE bugfix: restore `update` on the
                                      # */finalizers subresources in the operator
                                      # ClusterRole; 0.94.0..0.94.1 touches no Go source
                                      # besides go.mod); (2) all ten CRD files differ ONLY in
                                      # the source-URL comment + the
                                      # operator.prometheus.io/version annotation
                                      # (0.94.0 -> 0.94.1) — schemas byte-identical;
                                      # (3) values.yaml: ONE line, alertmanager image
                                      # v0.34.0 -> v0.34.1 (upstream bugfix: inhibition
                                      # could improperly un-mute alerts) — so Alertmanager's
                                      # ENGINE image now moves too; (4) chart ClusterRole
                                      # moves */finalizers into their own `update`-only rule
                                      # (91.5.2, PR 7295); (5) two default-rule template
                                      # fixes (KubeJobNotCompleted honours
                                      # label_excluded_from_alerts; the apiserver
                                      # `...:rate5m` recording rules used a [1d] range, now
                                      # [5m]); (6) 35 dashboard templates differ ONLY in the
                                      # never-rendered `Generated from` header. Subchart
                                      # pins (ksm 8.5.0, node-exporter 4.57.0, grafana
                                      # 13.2.5) identical to 91.4.1. Prometheus engine image
                                      # unchanged. Superseded note below kept for history:
                                      # (91.4.1: released 2026-09-16, operator v0.94.0 — the SAME
                                      # appVersion as 91.4.0. MEASURED 2026-09-20 against
                                      # the prometheus-community index AND both chart
                                      # tarballs: 91.4.0 -> 91.4.1 differs in 3 of 313 chart
                                      # files (Chart.yaml, Chart.lock, charts/grafana/
                                      # Chart.yaml) — the grafana SUBCHART dependency only
                                      # (13.2.4 -> 13.2.5). values.yaml and all ten CRD
                                      # files are BYTE-IDENTICAL. So every risk statement
                                      # below (operator v0.93.1 -> v0.94.0, ten CRDs
                                      # replaced, Prometheus + Alertmanager restart once)
                                      # is unchanged by this retarget.
update_type: major
risk: medium                          # shared monitoring infra: Prometheus AND
                                      # Alertmanager pods restart once (config-reloader
                                      # sidecar image moves), 10 cluster-scoped CRDs are
                                      # REPLACED, and the window's own health gate reads
                                      # this Prometheus. No reboot, no data migration,
                                      # Prometheus engine image unchanged; Alertmanager
                                      # v0.34.0 -> v0.34.1 is a bugfix patch riding the
                                      # restart it already had (91.5.2 retarget),
                                      # rollback is a real git revert (§5).
est_duration_min: 35
needs_reboot: false
touches:
  namespaces:
    - monitoring
  resources:
    - helmrelease/kube-prometheus-stack
    - deployment/kube-prometheus-stack-operator            # v0.93.1 -> v0.94.1
    - clusterrole/kube-prometheus-stack-operator           # wildcard verbs -> explicit
    - statefulset/prometheus-kube-prometheus-stack         # restarts (reloader sidecar)
    - statefulset/alertmanager-kube-prometheus-stack       # restarts (reloader sidecar + alertmanager v0.34.0 -> v0.34.1)
    - deployment/kube-prometheus-stack-kube-state-metrics  # subchart 8.4.2 -> 8.5.0, image unchanged
    - daemonset/kube-prometheus-stack-prometheus-node-exporter  # subchart 4.56.3 -> 4.57.0, image unchanged
    - "crd/*.monitoring.coreos.com (10, CLUSTER-SCOPED, replaced by Flux CreateReplace)"
    - pvc/prometheus-kube-prometheus-stack-db-prometheus-kube-prometheus-stack-0  # RWO longhorn-static PV prometheus-tsdb; NOT modified, re-attached on restart
  shared:
    - monitoring                      # every alert, every SLO, the sweep alert-watcher
                                      # and the window health gates ride on this stack.
                                      # Prometheus is blind for ~2-5 min during its
                                      # restart; Alertmanager for ~1 min.
autonomy_override: human-gated   # ADDED 2026-09-20 on independent review. NOT because the category is
                                  # unproven (chart/AUTO-NIGHT is graduated) but because this plan's HARDEST
                                  # constraint is enforced by NOTHING: §6 says it MUST run LAST in its window
                                  # or alone, and window-scheduler.py has no ordering or exclusivity primitive
                                  # at all — conflicts_with only keeps NAMED plans out, so any unnamed plan may
                                  # share the slot and nothing makes this one go last (F-48a45acf). This
                                  # component IS the window's instrument: its 2-5 min blind spot is also the
                                  # blind spot of Step 0's auto-revert decision and the Step 4 'never start on
                                  # a degraded cluster' gate. A chart major that blinds the mechanism meant to
                                  # catch its own failure is the one case where the absent human is load-bearing.
                                  # Remove this ONLY when the scheduler can guarantee sole occupancy.
exclusive: true   # §6 "LAST in its window, or alone" — enforced by window-scheduler.py since 1f2d56f6
                  # (added 2026-09-25 review). NOT read by run-now.py preflight: in an on-demand
                  # NOW run the attending operator/agent enforces sole occupancy (run it alone).
depends_on:
  # RESOLVED 2026-09-20: prometheus-crd-ownership EXECUTED (1a551276, helm rev 25) and retired (9d87171b) — this dependency is SATISFIED. kube-prometheus-stack is now the single writer of all ten monitoring.coreos.com CRDs.
                                      # monitoring.coreos.com CRDs before this plan stamps
                                      # all ten to 0.94.1; otherwise the next nightly
                                      # otel patch bump re-stamps four back to 0.92.0 and
                                      # §4.3 holds only until then (CRD planner,
                                      # 2026-09-15). window-scheduler.py will not place
                                      # this plan until that one is `executed`.
conflicts_with:                       # HARD slot exclusions — window-scheduler.py keys on
  - nextcloud-mcp-0.187.1
                                      # this field only; the shared:[monitoring] overlap
                                      # is a post-placement warning (2026-09-15 review).
                                      # 2026-09-17: otel-operator-0.21.0 ref REMOVED — that
                                      # plan executed (9a35168f) and was retired (37f7c7a6)
                                      # in the nightly window. It mattered because both
                                      # CreateReplace the same four monitoring.coreos.com
                                      # CRDs (last writer wins, 0.94.0 vs 0.92.0) and landing
                                      # THIS plan first flips their
                                      # helm.toolkit.fluxcd.io/name label to
                                      # kube-prometheus-stack. MEASURED 2026-09-17 after that
                                      # plan ran: the four still read GEN 30, OPVER 0.92.0,
                                      # origin otel-operator, and helm-controller's last write
                                      # to them is still 2026-09-14 — a byte-identical
                                      # CreateReplace leaves no trace. Any future
                                      # otel-operator plan must re-add this exclusion.
                                      # 2026-09-16: unpoller-v5.2.5 ref REMOVED — that plan
                                      # executed (b0ffb944) and was retired (f3869634) in the
                                      # nightly window. The guard only ever protected its §4
                                      # settle, where a Prometheus restart blind spot would
                                      # have read as "no data" and triggered a needless revert.
  # RESOLVED 2026-09-20: prometheus-crd-ownership EXECUTED (1a551276) and retired (9d87171b) — there is no longer a plan to collide with, so this guard protected nothing. Removed per the dead-ref convention (F-6acb231c).
                                      # writers of the same ten CRDs in one window is the
                                      # race that plan exists to end; it runs in an EARLIER
                                      # window, never this one.
  - otel-operator-0.23.0              # ADDED 2026-09-20 (RECIPROCITY). That plan already
                                      # lists THIS plan in its conflicts_with; the README
                                      # requires the exclusion on BOTH sides because
                                      # --validate checks that refs resolve, not that they
                                      # are mutual. Same mechanism as the retired -0.21.0
                                      # ref above: both HRs CreateReplace the same four
                                      # monitoring.coreos.com CRDs, last writer wins.
  - edot-collector-0.161.0            # ADDED 2026-09-20 (RECIPROCITY). That plan lists THIS
                                      # plan in its conflicts_with: its §4 reads THIS
                                      # Prometheus, and the 2-5 min restart blind spot of
                                      # §3.4 would read there as a collector regression.
  - unpoller-v5.2.7                   # ADDED 2026-09-20 (RECIPROCITY). Successor to the
                                      # retired unpoller-v5.2.5 ref below, same reason: its
                                      # §4.3-4.5 query THIS Prometheus over a >=5-min settle.
                                      # DEAD-REF CLOSED 2026-09-20: this entry briefly read
                                      # `unpoller-v5.2.6` — an id that ceased to exist when
                                      # that plan was retargeted — and `maintenance-plan.py
                                      # --validate` failed the WHOLE plan set on it
                                      # (validate_plans() treats an unresolvable depends_on/
                                      # conflicts_with ref as an ERROR, not a warning:
                                      # "names no existing plan — this guard is not
                                      # enforced"). RE-VERIFIED 2026-09-20 after the fix:
                                      # --validate exits 0, and unpoller-v5.2.7 carries
                                      # `kube-prometheus-stack-91.4.1` in its own
                                      # conflicts_with, so the slot exclusion is mutual.
  # RESOLVED 2026-09-21: cilium-1.20.2 EXECUTED (80395710, chart 1.20.1 -> 1.20.2) and retired (c0797253) -- there is no longer a plan to collide with, so this guard protected nothing. Removed per the dead-ref convention: --validate treats an unresolvable ref as an ERROR, because a guard pointing at nothing enforces nothing.
security_ref: null                    # no security driver
capability_change: false              # 91.5.2 retarget (2026-09-25): no dashboard JSON
                                      # change 91.4.1 -> 91.5.2 either (35 header-only
                                      # diffs, 0 content lines); the two default-rule
                                      # template fixes change rule EXPRESSIONS, not the
                                      # rule/alert set. Original note:
                                      # operator 0.94.0 adds CRD fields (retentionPercentage,
                                      # clusterPeerName) we do not set; alerts, rules and
                                      # receivers render identically. CORRECTED 2026-09-20:
                                      # there is NO dashboard JSON change. 28 of the 35
                                      # dashboard TEMPLATES differ 90.0.0 -> 91.4.1 by exactly
                                      # one line each — the `Generated from …<sha>` header
                                      # (mixin 9dec3323 -> f3f97b13) — which sits inside a
                                      # `{{- /* … */}}` Helm comment and is never rendered.
                                      # MEASURED: 0 non-header diff lines across all 28; the
                                      # other 7 templates are byte-identical. The 28 rendered
                                      # ConfigMaps do still change, but only in their
                                      # chart-version labels (§1, §4.7).
rollback_class: git-revert            # Flux CreateReplace re-applies the 90.0.0 CRD files
                                      # on the revert (operator-version 0.93.1); helm
                                      # maxHistory: 2 keeps the 90.0.0 revision (40 as of
                                      # 2026-09-25) reachable. §5.
finding_refs:
  - F-f1e564f2                        # live record RE-READ 2026-09-20 (`policy-cli.py finding
                                      # show F-f1e564f2`): the title is already retargeted —
                                      # "kube-prometheus-stack: chart 90.0.0 → 91.4.1 (major)",
                                      # section `version`, triage_lane PLAN, severity critical,
                                      # status unchanged, resolved_at None (OPEN), last_seen
                                      # 2026-09-19. The previous inline text here quoted
                                      # "→ 91.2.1", which was the FILING-time title, not the
                                      # current one — corrected so the plan-or-page join is
                                      # readable against the live record.
                                      # RE-READ 2026-09-25: F-f1e564f2 is now status
                                      # RESOLVED (2026-09-23) — version-check now reports the
                                      # same-major step (F-ec382720, "90.0.0 → 90.2.0
                                      # (minor)", severity monitor) with 91.5.2 as "newest
                                      # overall", and no open finding names the 91.x major.
                                      # Ref kept (it is this plan's origin); see §2.1a for
                                      # what a Step-0 landing of 90.2.0 does to this plan.
status: executed   # EXECUTED 2026-09-26 on-demand NOW run (attended; consent: home-operation approve by operator
                   # 2026-09-26T04:50:32Z). Landing commit 87432c93 (chart 90.0.0 -> 91.5.2), helm rev 41 deployed
                   # over rev 40 superseded. Verified live 04:57-05:08Z: HR True 91.5.2 v0.94.1; operator v0.94.1,
                   # AM v0.34.1, prometheus v3.14.0-distroless (pod imageIDs read); 10/10 CRDs opver 0.94.1, served
                   # versions unchanged; targets 101/101 (baseline 101); rules 532 vs 531 (+1 upstream recording
                   # rule); Watchdog in AM updatedAt 05:02:03Z > AM start 04:57:01Z; AM 0.34.1 + telegram receiver;
                   # tsdb_floor 2026-09-19 00:00Z unchanged; active series 354132 -> 353206 (head_series 369200 ->
                   # 421399 = WAL-replay churn of restarted pods, not new scrape load); node_load1 4 samples/node;
                   # AM alerts received 5m 16.6; operator 172 log lines, 0 denied, 0 errors; ClusterRole 0 wildcard
                   # verbs; bundled grafana 0, separate grafana 13.2.5 restarts 0, GF_PLUGINS_PREINSTALL_DISABLED
                   # still true, Prometheus datasource health OK; 28/33 dashboard CMs, sidecar re-read. Transient:
                   # container.memory.rules eval failures 04:58:43-05:01:43 ("duplicate series" kube_pod_container_
                   # resource_limits from old+new kube-state-metrics pod in the staleness window), 0 after 05:03.
                   # File KEPT (not deleted) only because 21 plans name this id; retire with that ref pass.
window: null       # was now:2026-09-26 (run-now.py stamp, 9c369c21); cleared on execution
premises:
  - id: hr-still-on-90.0.0
    why: >-
      `current:` claims 90.0.0. If the HelmRelease already moved (a later plan,
      a hand bump, or a 91.x that slipped through Step 0), this plan's baseline
      and its rollback target are both stale.
    run: kubectl get helmrelease -n monitoring kube-prometheus-stack -o jsonpath='{.spec.chart.spec.version}'
    expect_exact: "90.0.0"
  - id: operator-live-is-0.93.1
    why: >-
      The whole risk assessment is "operator 0.93.1 -> 0.94.1, CRDs replaced".
      If the running operator is something else, the release-notes delta in §1
      is not the delta this window would apply.
    run: kubectl get deploy -n monitoring kube-prometheus-stack-operator -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: quay.io/prometheus-operator/prometheus-operator:v0.93.1
  - id: crds-applied-by-flux-createreplace
    why: >-
      §3 relies on Flux applying the chart's `crds/` directory on upgrade
      (install AND upgrade policy CreateReplace). With `Skip` or `Create` the
      CRDs would silently stay at 0.93.1 under a 0.94.1 operator and the
      upstream UPGRADE.md `kubectl apply --server-side` step would be required.
    run: kubectl get helmrelease -n monitoring kube-prometheus-stack -o jsonpath='{.spec.install.crds}/{.spec.upgrade.crds}'
    expect_exact: CreateReplace/CreateReplace
  - id: bundled-grafana-stays-disabled
    why: >-
      Grafana is a SEPARATE HelmRelease (grafana-community 13.2.4, 69cf5388).
      91.4.0 added GrafanaDatasource provisioning under the bundled grafana
      subchart, and 91.4.1 bumps that subchart again (13.2.4 -> 13.2.5, subchart
      appVersion 13.2.1 -> 13.2.2); 91.5.2 keeps 13.2.5 (measured 2026-09-25).
      Both must stay inert. If someone flipped
      `grafana.enabled`, this bump would ALSO roll out a second Grafana on the
      same hostname.
    run: kubectl get configmap -n monitoring kube-prometheus-stack-values -o jsonpath='{.data.values\.yaml}' | grep -A1 '^grafana:' | tail -1 | tr -d ' '
    expect_exact: "enabled:false"
  - id: no-bundled-grafana-deployment-exists
    why: >-
      The values premise above checks intent; this checks outcome. A
      kube-prometheus-stack-grafana Deployment would mean the subchart is live
      regardless of what the ConfigMap says.
    run: kubectl get deploy -n monitoring -o name | grep -c kube-prometheus-stack-grafana
    expect_exact: "0"
  - id: prometheus-engine-unchanged-by-this-bump
    why: >-
      91.5.2 ships prometheus v3.14.0-distroless — the SAME image that is live —
      so this plan claims no Prometheus engine change (no TSDB format risk).
      Re-measured 2026-09-25: 91.4.1 -> 91.5.2 values.yaml differs in ONE line,
      the alertmanager tag (premise alertmanager-live-is-v0.34.0); the
      prometheus tag is unchanged.
      If the live Prometheus image differs, that claim is stale and the WAL /
      TSDB compatibility question must be re-asked.
    run: kubectl get prometheus -n monitoring kube-prometheus-stack -o jsonpath='{.spec.image}'
    expect_exact: quay.io/prometheus/prometheus:v3.14.0-distroless
  - id: alertmanager-live-is-v0.34.0
    why: >-
      ADDED 2026-09-25 with the 91.5.2 retarget: 91.5.x moves the Alertmanager
      engine image v0.34.0 -> v0.34.1 (upstream bugfix release, inhibition
      fixes only). §4.1 asserts v0.34.1 afterwards. If the live image is
      already something else, the §1 delta and the §5 rollback image are
      stale. MEASURED live 2026-09-25: quay.io/prometheus/alertmanager:v0.34.0.
    run: kubectl get alertmanager -n monitoring kube-prometheus-stack -o jsonpath='{.spec.image}'
    expect_exact: quay.io/prometheus/alertmanager:v0.34.0
  - id: tsdb-pvc-bound-to-static-pv
    why: >-
      The Prometheus pod restarts and must re-attach the SAME volume. The PVC
      is pinned to the speaking-name static PV `prometheus-tsdb`; if that pin
      is gone the StatefulSet could regenerate an EMPTY dynamic volume on
      restart and the "TSDB floor unchanged" verification in §4 has no meaning.
    run: kubectl get pvc -n monitoring prometheus-kube-prometheus-stack-db-prometheus-kube-prometheus-stack-0 -o jsonpath='{.spec.volumeName}/{.status.phase}'
    expect_exact: prometheus-tsdb/Bound
  - id: alertmanagerconfig-api-still-v1alpha1
    why: >-
      Three AlertmanagerConfig objects (monitoring/telegram, monitoring/
      claude-watch-webhook, storage/telegram) and three ScrapeConfigs are
      v1alpha1. Operator 0.94.1's CRDs still serve ONLY v1alpha1 for both
      (2026-09-25: the 91.5.2 CRD files differ from 91.4.1's only in the
      version annotation and source comment — schemas byte-identical)
      (RE-VERIFIED 2026-09-20 against the 91.4.1 chart files, which are
      byte-identical to 91.4.0's: served=v1alpha1 for alertmanagerconfigs,
      prometheusagents and scrapeconfigs; v1 for the other seven; all ten
      annotated operator.prometheus.io/version=0.94.0), so no API migration is
      needed. If a served version other than v1alpha1 appears, re-check.
    run: kubectl get crd alertmanagerconfigs.monitoring.coreos.com -o jsonpath='{.spec.versions[*].name}'
    expect_exact: v1alpha1
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/monitoring.md
  - docs/sops/verification-contents-not-shape.md   # ADDED 2026-09-20. §4.5 implements its
                                                   # "chart/version bump on anything SCRAPED"
                                                   # row verbatim, and §4.6 was rewritten
                                                   # against its "cannot distinguish working
                                                   # from empty" test. Sibling monitoring
                                                   # plans (otel-operator-0.23.0,
                                                   # edot-collector-0.161.0, unpoller-v5.2.7)
                                                   # all cite it; this plan was the outlier.
generated: "2026-09-15"
---

# kube-prometheus-stack chart 90.0.0 → 91.5.2 (prometheus-operator v0.93.1 → v0.94.1)

## 1) Summary & why held

Bump the `kube-prometheus-stack` HelmRelease in `monitoring` from chart **90.0.0**
to **91.5.2** *(retargeted from 91.4.1 on 2026-09-25 — see "91.4.1 → 91.5.2 delta" below)*. This is the cluster's Prometheus / Alertmanager / prometheus-operator
stack — every PrometheusRule (86), ServiceMonitor (49), PodMonitor (3), Probe (4),
ScrapeConfig (3) and AlertmanagerConfig (3) in the cluster is interpreted by it, and
the maintenance-window health gate, the sweep's alert-watcher and all five SLOs read
from it.

Held because it is a chart **major**. Upstream bumps the major exactly when the
CRDs change, and this one does:

> **From 90.x to 91.x**
> This version upgrades Prometheus-Operator to v0.94.0
> The operator's ClusterRole no longer grants wildcard verbs, following the tightened RBAC shipped upstream in v0.94.0.
> Since 68.4.0 it is also possible to use `crds.upgradeJob.enabled` for upgrading the CRDs.
> For traditional upgrades, please run these commands to update the CRDs before applying the upgrade.
>
> (verbatim from `charts/kube-prometheus-stack/UPGRADE.md` — the 90→91 section; no
> 91.x→91.5 section exists, 91.5.x is a minor line; originally fetched at tag
> `kube-prometheus-stack-91.4.1` — re-fetched and diffed 2026-09-20: UPGRADE.md is
> byte-identical at tags 91.4.0 and 91.4.1, and RE-DIFFED 2026-09-25: byte-identical at
> 91.5.2 too, so this quote is the 91.5.2 text — followed
> by the ten `kubectl apply --server-side -f
> …/prometheus-operator/v0.94.0/example/prometheus-operator-crd/monitoring.coreos.com_*.yaml`
> commands — which Flux `CreateReplace` performs for us, premise
> `crds-applied-by-flux-createreplace`)

**What actually changes, measured against the two chart tags (not the summary):**

| | 90.0.0 (live) | 91.5.2 | Effect here |
|---|---|---|---|
| prometheus-operator (appVersion) | v0.93.1 | **v0.94.1** | operator Deployment rolls; config-reloader sidecar in BOTH StatefulSets moves → **Prometheus and Alertmanager pods restart once** |
| prometheus image | v3.14.0-distroless | v3.14.0-distroless | **unchanged** — no TSDB/WAL format risk |
| alertmanager image | v0.34.0 | **v0.34.1** | **CHANGED by the 91.5.x retarget** — upstream bugfix release (2026-09-17, not a prerelease): *"inhibit: Fix several issues related to inhibitions that caused alerts to be improperly un-muted in some cases."* We run inhibit rules (the kps default `InfoInhibitor` set; `alertmanager-telegram-config.yaml` routes on it), so the only behavioural effect is FEWER spurious un-mutes. No config/format change; the pod was restarting anyway |
| kube-state-metrics subchart | 8.4.2 (image v2.20.0) | 8.5.0 (image v2.20.0) | chart-only; image identical |
| node-exporter subchart | 4.56.3 (image v1.12.1) | 4.57.0 (image v1.12.1) | chart-only; image identical |
| grafana subchart | 13.2.2 | **13.2.5** | subchart **workloads inert** (`grafana.enabled: false`, premise) — **but** `grafana.forceDeployDashboards: true` (`helmvalues.yaml`) makes the kps chart itself render **28** `grafana_dashboard=1` ConfigMaps (live count 2026-09-15) that the separate Grafana's `grafana-sc-dashboard` sidecar loads, and **none of them change dashboard JSON** relative to 90.0.0. *(CORRECTED 2026-09-20 — the earlier "10 of them change content" was wrong. RE-MEASURED by extracting both chart tarballs and diffing `templates/grafana/dashboards-1.14/` file by file: 28 of the 35 dashboard templates differ, 7 are byte-identical, and every one of the 28 differs by **exactly one line** — the `Generated from …<sha>` header, mixin `9dec3323` → `f3f97b13`. That header sits inside a `{{- /* … */}}` Helm comment (verified in the template head) and is therefore **never rendered**: 0 non-header diff lines across all 28.)* The 28 rendered ConfigMaps **do** still change, for a different reason: the shared `kube-prometheus-stack.labels` helper stamps `app.kubernetes.io/version: "{{ .Chart.Version }}"` and `chart: {{ chartref }}`, both of which move with the chart version. That label churn is what makes the sidecar re-read them — harmless; §4.7 checks the sidecar picked them up and the count did not move. **Expect no visible dashboard change in the Grafana UI.** NOTE the two 13.2.x lines are DIFFERENT objects: this row is the bundled SUBCHART (inert); the separate `grafana` HelmRelease is chart 13.2.4 and is NOT touched (§4.2) |
| CRDs (`operator.prometheus.io/version`) | 0.93.1 | **0.94.1** | all 10 replaced by Flux `CreateReplace` (0.94.1 schemas byte-identical to 0.94.0's) |
| values.yaml (non-comment diff) | — | only ADDED keys: `clusterPeerName`, `datasourcesEnabled`, `retentionPercentage`, `tsdb.chunkEncoding`, `staleSeriesCompactionThreshold`, `prometheusSpec.rules` (a new template branch — the top-level `rules:`/`defaultRules` keys already existed at 90.0.0), `schedulerName`; one type change `admissionWebhooks.matchConditions: {}` → `[]` | **no removed or renamed values**; we set none of the changed keys |

Per-release content of the 91.x line (GitHub releases, 2026-09-13/14): 91.0.0 = the
operator bump (PR 7269); 91.1.0 = `retentionPercentage` + `clusterPeerName` values;
91.2.0 = `rules`/`tsdb`/thanosRuler spec gaps; 91.2.1 = webhook `matchConditions`
rendered as a list; 91.2.2/91.2.3 = docs + CRD-upgrade-job labels; 91.3.0 = ksm
subchart; 91.4.0 = optional `GrafanaDatasource` provisioning (default off); **91.4.1 =
grafana subchart dependency 13.2.4 -> 13.2.5 and a CI change only** (measured 2026-09-20
by diffing both chart tarballs: 3 of 313 files differ — `Chart.yaml`, `Chart.lock`,
`charts/grafana/Chart.yaml`; `values.yaml` and all ten CRD files byte-identical).

**91.4.1 → 91.5.2 delta (retarget 2026-09-25, measured by diffing both chart tarballs
+ GitHub releases):** 91.5.0 (2026-09-22) = "dependency non-major updates" (PR 7307):
alertmanager image v0.34.0 → **v0.34.1**, refreshed mixin (rules + dashboard headers);
91.5.1 (2026-09-23) = prometheus-operator **v0.94.1** (PR 7312); 91.5.2 (2026-09-24) =
`fix(rbac)` (PR 7295): the chart ClusterRole moves `alertmanagers|prometheusagents|
prometheuses|thanosrulers/finalizers` out of the create/update/patch/delete status
rule into their own `update`-only rule — matching operator v0.94.1's only change,
*"[BUGFIX] Restore `update` permission on finalizer subresources in the operator's
ClusterRole, required by `OwnerReferencesPermissionEnforcement` when
`blockOwnerDeletion` is set."* (net: the finalizer rule is NARROWER than in 91.4.1,
update-only). Default-rule template fixes: `KubeJobNotCompleted` now excludes jobs
labelled `excluded_from_alerts=true`; the `cluster_verb:apiserver_request_sli_*:rate5m`
recording rules had a `[1d]` range and now use `[5m]` (upstream mixin bug fix — values
of those recorded series change shape, alerts do not appear or disappear). Dashboard
templates: 35 differ, every one only in the unrendered `Generated from` header — 0
content lines. Subchart pins identical to 91.4.1. **No new migration, no removed
values, no CRD schema change → risk class unchanged (`medium`).** 92.x does not exist
(index read 2026-09-25).

Prometheus-operator **v0.94.0** (2026-09-09; v0.94.1 adds only the finalizer-RBAC bugfix above) changes that could bite, checked against
our objects:

- *[CHANGE] discard zero-value duration fields (`retention`, `clusterGossipInterval`,
  `clusterPushpullInterval`, `clusterPeerTimeout`) in Alertmanager resources instead
  of passing them as CLI flags … Ignored fields are reported via the `IgnoredFields`
  status condition.* — our `alertmanagerSpec` sets none of these. The regenerated
  Alertmanager StatefulSet may differ in flags; that is the restart, not a failure.
- *[CHANGE] Reject empty strings in `namespaceDiscovery.names`, `consulSDConfig.*`
  … in the ScrapeConfig CRD; named enums for Hetzner/DockerSwarm/OpenStack.* — our
  three ScrapeConfigs (`macos-scrapeconfigs.yaml`: static macOS targets) use none of
  those blocks.
- *[ENHANCEMENT] Tighten the operator's ClusterRole by replacing wildcard verbs with
  explicit permissions per resource.* — the chart ships the matching ClusterRole. The
  residual risk is an upstream omission; §4.6 checks the new operator's log for
  `forbidden`.
- *[FEATURE] Expose status conditions as Prometheus metrics* — new series appear
  (`prometheus_operator_*_status_condition`-style); head-series count rises slightly.

**Not a false positive, but not dramatic either.** The hold is correct because the
CRD replace and the double restart are real, and because this is the one component
whose failure blinds every other verification in the window. It is `risk: medium`
because nothing migrates, the Prometheus engine image does not move (Alertmanager's moves one bugfix patch), and the revert is genuine.

**Retention (F-741361a7) is untouched.** `retention: 7d` / `retentionSize: 20GB` live
in our values ConfigMap and this bump does not alter them. 91.1.0 does expose the
new `retentionPercentage` field, which is a possible lever for that finding's
option (b) — a separate operator decision, not part of this plan.

### Admission-validator panics (F-a002e49b) -- answered, not fixed by this bump

The nil dereference at `pkg/admission/admission.go:234` is `ar.Request` being
nil. A real API-server call always carries `request`; the only caller that did
not was `runbooks/health-check.sh` section 38, which posted `{}` to every
registered webhook path once per sweep (panic days = sweep days, three lines per
run, one per registered path). The probe now sends a well-formed review, and
the operator answers with a resource-mismatch response instead. Checked
2026-09-22: v0.94.0 ships a byte-identical `admission.go` (and v0.94.1 changes no Go
source at all besides `go.mod`, compare v0.94.0...v0.94.1 read 2026-09-25), so this plan changes
nothing about it -- and nothing needs changing. PrometheusRule validation was
never bypassed.

### The CRD-ownership contention this plan must live with (read before executing)

The ten `monitoring.coreos.com` CRDs are written by **two** HelmReleases, both with
`crds: CreateReplace`, and the last one to upgrade wins:

```
alertmanagerconfigs / alertmanagers / prometheusagents / prometheuses /
prometheusrules / thanosrulers         -> helm.toolkit.fluxcd.io/name=kube-prometheus-stack, opver 0.93.1
podmonitors / probes / scrapeconfigs /
servicemonitors                        -> helm.toolkit.fluxcd.io/name=otel-operator,          opver 0.92.0  (generation 30)
```

`otel-operator` is the `opentelemetry-kube-stack` chart (0.20.9, upgraded by Step 0 on
2026-09-14 05:45) whose values default to `crds.installPrometheus: true`. It bundles an
older copy of four of these CRDs, and each of its near-weekly patch bumps stamps them
back to 0.92.0 — which is why they read 0.92.0 today six days after kps 90.0.0 wrote
0.93.1. Consequences for this plan:

1. After this upgrade all ten will read **0.94.1** (§4.3 asserts it). The 0.94.1
   operator runs fine against the older 0.92.0 schemas too (we use no 0.93+/0.94+
   fields on those four kinds); what the contention costs is validation of new
   fields, not function.
2. **The durable fix is its own plan, and this plan depends on it:
   `prometheus-crd-ownership` (`depends_on`, sweep record F-a85e8943).** It sets
   `crds.installPrometheus: false` on the otel-operator HelmRelease. The
   cascade-delete question that made this a "must investigate first" item has been
   answered in that plan with three-sourced proof: the four CRDs come from a
   `crds/` directory in the condition-gated `prometheus-crds` subchart, they are
   not Helm release resources (`helm get manifest` has zero CRDs; no release
   annotation on the objects), and helm-controller prunes `condition: false`
   subcharts before collecting `crds/` and never deletes on `CreateReplace`. So the
   flip removes a *writer* and deletes nothing. **Ordering:** that plan runs in an
   earlier window (its human-gated first execution), then this one — after which
   all ten CRDs are written by kube-prometheus-stack alone and §4.3 holds
   permanently instead of until the next otel patch bump. It does NOT rewrite the
   four CRDs itself, so §2.5's expected pre-state is unchanged by it.
3. **Effect on `otel-operator-0.23.0`.** *(CORRECTED 2026-09-20: this paragraph
   previously named `otel-operator-0.21.0`. That plan EXECUTED (`9a35168f`) and was
   RETIRED (`37f7c7a6`) — its file no longer exists, so it could neither be a
   conflict nor a sequencing partner. The live otel HR is chart 0.21.0 and the OPEN
   successor plan is `otel-operator-0.23.0` (status draft, window null, HUMAN-GATED),
   which the frontmatter already lists correctly.)* This upgrade re-stamps all ten
   CRDs and the `helm.toolkit.fluxcd.io/name` label follows the last applier
   (observed: the four flipped to `otel-operator` on the 2026-09-14 otel Step-0 bump).
   Landing this plan first therefore changes the four's label to
   `kube-prometheus-stack`; the otel plan measures that in its §2.6 instead of gating
   on it (its former premise `this-hr-owns-the-prometheus-crds` was removed for
   exactly this reason). The preferred order is still `otel-operator-0.23.0`
   **before** this plan (§6) — and both declare the other in `conflicts_with`
   (verified mutual 2026-09-20), so they can never share a slot in either order.

## 2) Pre-checks

Run inside the window, **after Step 0 has finished and its health gate has passed**
(§6). Every check has a pass condition; a fail is a no-go.

```bash
cd /Users/mu/code/cberg-home-nextgen
export KUBECONFIG="$PWD/kubeconfig"
```

**2.1 — Premises hold (the scheduler ran them at placement; re-run now).**

```bash
python3 runbooks/plan-premises.py kube-prometheus-stack-91.4.1 --require-premises
```
**PASS:** exit 0, 9/9 premises pass (the plan id stays `-91.4.1`; the target is 91.5.2).

**2.1a — Step 0 may have moved the chart to 90.2.0 first.** Since 2026-09-23 the
version-check reports the same-major step `90.0.0 → 90.2.0 (minor)` (F-ec382720) and
there is NO deny rule for `kube-prometheus-stack` in `runbooks/auto-update-policy.yaml`
(checked 2026-09-25), so Step 0 of any window may legitimately land 90.2.0. If it has,
premise `hr-still-on-90.0.0` FAILS in 2.1 — that is correct: the baseline, the §5
revert target and the helm revision numbers are then stale. **No-go; send the plan
back for a re-read against the new `current`**, do not edit the premise in-window.

**2.2 — Flux fully green, nothing mid-upgrade in `monitoring`, and the dependency
has landed.** A concurrent otel-operator upgrade would race the CRD write; and
`prometheus-crd-ownership` has already EXECUTED (2026-09-20, commit 1a551276)
and its plan file is retired, so the `depends_on` ref is gone from frontmatter.
**Nothing enforces this at placement any more — this check IS the enforcement.**
Do not skip it on the assumption the scheduler gated it; it cannot.

```bash
mise exec -- flux get kustomizations -A | awk 'NR==1 || $5 != "True"'
mise exec -- flux get helmreleases   -A | awk 'NR==1 || $5 != "True"'
kubectl get helmrelease -n monitoring otel-operator kube-prometheus-stack grafana \
  -o custom-columns='NAME:.metadata.name,CHART:.status.history[0].chartVersion,READY:.status.conditions[?(@.type=="Ready")].status'
kubectl get helmrelease -n monitoring otel-operator -o jsonpath='installPrometheus=[{.spec.values.crds.installPrometheus}]{"\n"}'
```
**PASS:** both `flux get` commands print only the header; all three HRs `READY=True`,
kps at `90.0.0`; `installPrometheus=[false]` (the otel HR no longer writes the
four shared CRDs). `installPrometheus=[]` = the dependency has not landed:
**no-go**, regardless of what the scheduler believed.

*(COMMAND FIXED 2026-09-20 — it was broken before this pass and could never have
passed. The `READY:` column read
`.status.conditions[?(@.type=="Ready").status]`, closing the filter after
`.status`; kubectl prints the header and then `error: unclosed array expect ]`,
rc=1. Corrected to `…[?(@.type=="Ready")].status`. MEASURED both forms live
2026-09-20: the old one errors, the new one prints all three HRs. The whole block
was then re-run verbatim end-to-end from this file — rc=0. Note this was a
fail-LOUD defect, not a pass-on-failure one, but it would have stalled the window
at its first pre-check.)*

**WRITE DOWN the `grafana` chart version this prints.** §4.2 compares against it
and must NOT use any figure printed in this plan — see §4.2 and the §6 bullet on
the grafana deny rule. It reads `13.2.4` as of 2026-09-20, but Step 0 of THIS
window may legitimately have moved it to `13.2.5` before you get here.

**2.3 — Target chart exists at the OCI source, with a negative control.**

```bash
TOKEN=$(curl -s "https://ghcr.io/token?scope=repository:prometheus-community/charts/kube-prometheus-stack:pull&service=ghcr.io" \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
for TAG in 91.5.2 99.99.99; do
  printf "%-10s HTTP %s\n" "$TAG" "$(curl -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $TOKEN" \
    -H "Accept: application/vnd.oci.image.manifest.v1+json" \
    "https://ghcr.io/v2/prometheus-community/charts/kube-prometheus-stack/manifests/$TAG")"
done
```
**PASS — EXACTLY:** `91.5.2 -> 200` and `99.99.99 -> 404`. *(RE-MEASURED 2026-09-25
for the 91.5.2 target: `91.5.2 -> 200`, `91.4.1 -> 200`, `99.99.99 -> 404`. Earlier,
2026-09-20: `91.4.1 -> 200`, `91.4.0 -> 200`, `99.99.99 -> 404`. The older
2026-09-15 datapoint was `91.4.0 -> 200 / 99.99.99 -> 404`.)* Both 200 = intercepting
proxy, result invalid.

**2.4 — Observability baseline. Write these numbers down; §4 diffs against them.**

```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9099:9090 >/dev/null 2>&1 & PF1=$!
kubectl port-forward -n monitoring svc/kube-prometheus-stack-alertmanager 9093:9093 >/dev/null 2>&1 & PF2=$!
sleep 4
curl -s localhost:9099/api/v1/targets | python3 -c "
import sys,json
t=json.load(sys.stdin)['data']['activeTargets']
print('targets',len(t),'up',sum(1 for x in t if x['health']=='up'))
print('down:',[(x['labels'].get('job'),x['labels'].get('instance')) for x in t if x['health']!='up'])"
curl -s localhost:9099/api/v1/rules | python3 -c "
import sys,json; g=json.load(sys.stdin)['data']['groups']
print('groups',len(g),'rules',sum(len(x['rules']) for x in g))"
curl -s localhost:9099/api/v1/alerts | python3 -c "
import sys,json
a=[x for x in json.load(sys.stdin)['data']['alerts'] if x['state']=='firing'
   and x['labels'].get('alertname') not in ('Watchdog','InfoInhibitor')]
print('firing:',len(a),sorted(set(x['labels'].get('alertname') for x in a)))"
curl -s -G localhost:9099/api/v1/query --data-urlencode 'query=prometheus_tsdb_head_series' \
  | python3 -c "import sys,json;print('head_series',json.load(sys.stdin)['data']['result'][0]['value'][1])"
curl -s -G localhost:9099/api/v1/query --data-urlencode 'query=prometheus_tsdb_lowest_timestamp_seconds' \
  | python3 -c "import sys,json,datetime;v=float(json.load(sys.stdin)['data']['result'][0]['value'][1]);print('tsdb_floor',datetime.datetime.fromtimestamp(v,datetime.timezone.utc))"
curl -s 'localhost:9093/api/v2/alerts?filter=alertname%3DWatchdog' | python3 -c "
import sys,json;a=json.load(sys.stdin);print('watchdog_in_AM',len(a),[x['status']['state'] for x in a])"
curl -s localhost:9093/api/v2/silences | python3 -c "
import sys,json;print('active_silences',len([x for x in json.load(sys.stdin) if x['status']['state']=='active']))"
kill $PF1 $PF2 2>/dev/null
```
**Historical datapoint — measured 2026-09-15 01:58Z (kept, NOT rewritten):**
`targets 98 up 98` · `down: []` · `groups 117 rules 474` ·
`firing: 1 ['LonghornVolumeAllocationHigh']` · `head_series 353092` ·
`tsdb_floor 2026-09-08 00:00Z` · `watchdog_in_AM 1 ['active']` · `active_silences 0`.

**Re-measured 2026-09-20 (retarget pass, same commands):** `targets 98 up 98` ·
`down: []` · `groups 118 rules 478` · `firing: 0 []` · `head_series 351993` ·
`tsdb_floor 2026-09-13 00:00Z` · `watchdog_in_AM 1 ['active']`.

**These numbers are a SANITY RANGE, not the gate.** The gate is the baseline you take
in THIS window, immediately before §3.2 — §4.4/§4.5 diff against *that*, never against
a printed number. Note why: `tsdb_floor` MOVES every day (7d retention — it read
2026-09-08 on 09-15 and 2026-09-13 on 09-20), and `groups`/`rules`/`head_series` drift
as apps come and go. A gate hardcoded to a plan-time figure would false-fail.
**PASS:** targets all up, `watchdog_in_AM` = 1 active. Any target down is a no-go
(the post-upgrade count comparison would be ambiguous).

**2.5 — CRD pre-state (so §4.3 is a diff, not a guess).**

```bash
kubectl get crd -o json | python3 -c "
import sys,json
for c in json.load(sys.stdin)['items']:
    n=c['metadata']['name']
    if n.endswith('monitoring.coreos.com'):
        print(f\"{n:45s} opver={c['metadata'].get('annotations',{}).get('operator.prometheus.io/version')} hr={c['metadata'].get('labels',{}).get('helm.toolkit.fluxcd.io/name')}\")"
```
**Expected (RE-MEASURED 2026-09-25):** 10 × `0.93.1 hr=kube-prometheus-stack` — prometheus-crd-ownership removed the otel writer and kps revision 40 (2026-09-22) re-stamped the four formerly otel-owned CRDs (now generation 31). Ten CRDs total. *(The 2026-09-15/20 picture — 6 × kps 0.93.1 + 4 × otel 0.92.0 — is history; the §1 contention block describes the pre-2026-09-22 state.)* Any other
picture: stop and re-derive §1 before proceeding.

**2.6 — Storage: the TSDB volume is healthy and backed up.**

```bash
kubectl get volume -n storage prometheus-tsdb -o jsonpath='{.status.state}/{.status.robustness}/{.status.lastBackupAt}{"\n"}'
```
**PASS:** `attached/healthy/<timestamp within 48h>`.

## 3) Steps

GitOps only. Nothing here touches the cluster directly; Flux does the apply.

**3.1 — Silence rollout noise (SOP §4 Step 1) and drop the active-update marker.**
Prometheus cannot fire while it restarts, but the Alertmanager restart and the
operator's outgoing-pod teardown (see `docs/sops/monitoring.md` "Chart-bump rollout
noise") produce `KubePod*`/`KubeStatefulSet*`/`TargetDown` transients. 1-hour TTL.

```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-alertmanager 9093:9093 >/dev/null 2>&1 & PF=$!
sleep 3
NOW=$(python3 -c "from datetime import *;print(datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z'))")
END=$(python3 -c "from datetime import *;print((datetime.now(timezone.utc)+timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M:%S.000Z'))")
curl -s -X POST localhost:9093/api/v2/silences -H 'Content-Type: application/json' -d '{
  "matchers":[{"name":"namespace","value":"monitoring","isRegex":false,"isEqual":true},
              {"name":"alertname","value":"KubePod.*|KubeStatefulSet.*|KubeDeployment.*","isRegex":true,"isEqual":true}],
  "startsAt":"'$NOW'","endsAt":"'$END'","createdBy":"maintenance-window",
  "comment":"kube-prometheus-stack chart 90.0.0->91.5.2 rollout. auto-expires 1h"}'
kill $PF 2>/dev/null
runbooks/update-marker.sh add kube-prometheus-stack monitoring 1 "chart 90.0.0->91.5.2"
```

Do **not** silence `Watchdog`, `Prometheus*` or `Alertmanager*` alerts — those are the
signals §4 reads. Leave `upgrade.remediation` at `retries: 3` (rollback on failure is
the desired behaviour here: there is no init migration to protect).

**3.2 — The bump. One line, one file.**

```bash
sed -i '' 's/^      version: 90\.0\.0$/      version: 91.5.2/' \
  kubernetes/apps/monitoring/kube-prometheus-stack/app/helmrelease.yaml
git --no-pager diff kubernetes/apps/monitoring/kube-prometheus-stack/app/helmrelease.yaml
```
**Expected diff** (DRY-TESTED 2026-09-25 for 91.5.2, and 2026-09-20 before it, on a scratch copy of the real file with this
exact BSD-sed command; it produced precisely this and nothing else):

```diff
12c12
<       version: 90.0.0
---
>       version: 91.5.2
```

No values change: `helmvalues.yaml` needs nothing for 91.x (no removed/renamed keys, §1).

**3.3 — Commit and push (`--only`, shared worktree).**

```bash
cat > /tmp/kps-msg.txt <<'EOF'
chore(monitoring)!: kube-prometheus-stack chart 90.0.0 -> 91.5.2 (operator v0.94.1)

Chart major: prometheus-operator v0.93.1 -> v0.94.1 with the matching CRD set
(applied by Flux CreateReplace) and the tightened operator ClusterRole.
Prometheus image (v3.14.0) is unchanged; Alertmanager moves v0.34.0 -> v0.34.1
(bugfix). Both pods restart once for the config-reloader sidecar. kube-state-metrics and
node-exporter subcharts move without image changes. Bundled grafana stays
disabled (its subchart pin moves 13.2.2 -> 13.2.5 and renders nothing); grafana
is its own HelmRelease. Values untouched.

Plan: runbooks/maintenance/plans/kube-prometheus-stack-91.4.1.md
Finding: F-f1e564f2
EOF
# Append YOUR OWN attribution trailer here (the executing agent's, not the
# planner's) per the session's attribution rules — do NOT copy a planner's
# Claude-Session link into a commit you are making.
git fetch origin main && git merge --ff-only origin/main
git commit --only kubernetes/apps/monitoring/kube-prometheus-stack/app/helmrelease.yaml -F /tmp/kps-msg.txt
git show --stat HEAD          # exactly ONE file
git push origin main
```

**3.4 — Watch the rollout (no manual reconcile; the webhook drives it).** The
Kustomization applies the new HR spec and helm-controller upgrades immediately on
the spec change. Expected sequence, ~5-8 min end to end: HR `Reconciling` → CRDs
replaced → operator Deployment rolls → operator regenerates both StatefulSets →
`prometheus-kube-prometheus-stack-0` and `alertmanager-kube-prometheus-stack-0`
terminate and come back (Prometheus replays WAL; with ~350k head series budget
1-3 min before `2/2 Ready`).

```bash
kubectl get helmrelease -n monitoring kube-prometheus-stack -w      # until Ready=True with 91.5.2
kubectl get pods -n monitoring -l 'app.kubernetes.io/name in (prometheus,alertmanager)' -w
```

If the HR has not started reconciling 5 minutes after the push (webhook missed):
`mise exec -- flux reconcile source git flux-system` — that is the one manual
reconcile the SOP allows, and it only re-fetches git.

**Expected noise, NOT a failure** (`docs/sops/monitoring.md` §Troubleshooting):
`InvalidConfiguration … context canceled` and readiness `connection refused` from the
**outgoing** operator pod. Do not revert on those; run §4.

**3.5 — On success:** clear the marker, delete the silence early if §4 is green
before it expires, and retire this plan file in the same commit series
(`README.md`: plans are transient).

```bash
runbooks/update-marker.sh clear kube-prometheus-stack
```

## 4) Verification

Floor: HR Ready, pods healthy. The section is the alert pipeline end to end and
the CRD contents.

**4.1 — HelmRelease and images.**

```bash
kubectl get helmrelease -n monitoring kube-prometheus-stack \
  -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} {.status.history[0].chartVersion} {.status.history[0].appVersion}{"\n"}'
kubectl get deploy -n monitoring kube-prometheus-stack-operator -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'
kubectl get sts -n monitoring prometheus-kube-prometheus-stack alertmanager-kube-prometheus-stack \
  -o jsonpath='{range .items[*]}{.metadata.name}: {range .spec.template.spec.containers[*]}{.image} {end}{"\n"}{end}'
kubectl get pods -n monitoring -l 'app.kubernetes.io/name in (prometheus,alertmanager,kube-prometheus-stack-prometheus-operator)'
helm history kube-prometheus-stack -n monitoring | tail -2
```
**PASS:** `True 91.5.2 v0.94.1`; operator image `…prometheus-operator:v0.94.1`;
each StatefulSet lists `prometheus-config-reloader:v0.94.1`, next to the UNCHANGED
`prometheus:v3.14.0-distroless` and the MOVED `alertmanager:v0.34.1` respectively
(`alertmanager:v0.34.0` still listed = the operator did not regenerate the AM
StatefulSet — FAIL); all pods `Running`, `2/2`, 0 restarts after settle; helm shows
the new revision `deployed` directly above the 90.0.0 one `superseded` (revision 41
over 40 as of 2026-09-25 — live history reads 39 superseded / 40 deployed, both
90.0.0; a Step-0 or other upgrade before the window shifts these by one, so read
the pair, not the literals).

**4.2 — Bundled grafana still absent; separate grafana untouched.**

```bash
kubectl get deploy -n monitoring -o name | grep -c kube-prometheus-stack-grafana   # MUST be 0
kubectl get helmrelease -n monitoring grafana \
  -o jsonpath='grafana_chart={.status.history[0].chartVersion} ready={.status.conditions[?(@.type=="Ready")].status}{"\n"}'
kubectl get pods -n monitoring -l app.kubernetes.io/name=grafana \
  -o jsonpath='{range .items[*]}{.metadata.name} {.status.phase} restarts={.status.containerStatuses[0].restartCount}{"\n"}{end}'
```
**PASS:** the bundled-grafana count is `0`; `ready=True`; the grafana pod is
`Running` and its restart count did not move (this plan must not restart the
separate Grafana); and `grafana_chart` **equals the value YOU recorded in §2.2 in
this window** — not a figure printed here.

**Do NOT hardcode `13.2.4` — that was a false-fail waiting to happen.** *(FIXED
2026-09-20; this line previously asserted a literal `# 13.2.4 True`.)* `grafana` is
a SEPARATE HelmRelease with an OPEN patch bump 13.2.4 → 13.2.5 (no Renovate PR, so
the no-PR DIRECT-BUMP half of Step 0 owns it), and **Step 0 runs FIRST in every
window, including this one.** MEASURED 2026-09-20 by calling the exact classifier
Step 0 uses (`coverage.py::deny_rule_for` / `denied`): `grafana patch ->
ALLOWED (eligible for AUTO/Step 0)`, while `grafana minor` and `grafana major` ->
BLOCKED. The `match: "*grafana*"` deny rule carries `max: patch`, and both
`policy_block` and `deny_rule_for` block only when
`RANK[update_type] > RANK[max]` — for a patch that is `0 > 0`, false, a **decisive
ALLOW**. So the rule explicitly PERMITS this bump rather than holding it. If Step 0
lands it, §4.2 seeing `13.2.5` is CORRECT and must not be read as a regression.

**4.3 — CRDs: all ten at 0.94.1, and served versions unchanged.**

```bash
kubectl get crd -o json | python3 -c "
import sys,json
rows=[c for c in json.load(sys.stdin)['items'] if c['metadata']['name'].endswith('monitoring.coreos.com')]
for c in rows:
    print(f\"{c['metadata']['name']:45s} opver={c['metadata'].get('annotations',{}).get('operator.prometheus.io/version')} served={[v['name'] for v in c['spec']['versions'] if v.get('served')]}\")
print('total',len(rows),'at 0.94.1:',sum(1 for c in rows if c['metadata'].get('annotations',{}).get('operator.prometheus.io/version')=='0.94.1'))"
```
**PASS:** `total 10 at 0.94.1: 10`; served versions identical to §2.5 (`v1` for
alertmanagers/podmonitors/probes/prometheuses/prometheusrules/servicemonitors/
thanosrulers, `v1alpha1` for alertmanagerconfigs/prometheusagents/scrapeconfigs).
**If exactly the four formerly otel-owned CRDs read 0.92.0:** an otel-operator
upgrade ran after ours (check `helm history otel-operator -n monitoring`) **while
still collecting the Prometheus CRDs** — with `prometheus-crd-ownership` executed
(`depends_on`, §2.2) that cannot happen, so it means that fix was reverted or did
not take. Record it as a NEW finding (that plan is retired — do not file against it); it is the §1
contention, not a failed kps apply — do not retry the kps upgrade.

**4.4 — Alert pipeline end to end (the load-bearing section).**

```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9099:9090 >/dev/null 2>&1 & PF1=$!
kubectl port-forward -n monitoring svc/kube-prometheus-stack-alertmanager 9093:9093 >/dev/null 2>&1 & PF2=$!
sleep 4
# (a) scrape target count unchanged, all up
curl -s localhost:9099/api/v1/targets | python3 -c "
import sys,json
t=json.load(sys.stdin)['data']['activeTargets']
print('targets',len(t),'up',sum(1 for x in t if x['health']=='up'))
print('down:',[(x['labels'].get('job'),x['labels'].get('instance')) for x in t if x['health']!='up'])"
# (b) rules loaded via /api/v1/rules — same group/rule count as baseline
curl -s localhost:9099/api/v1/rules | python3 -c "
import sys,json; g=json.load(sys.stdin)['data']['groups']
print('groups',len(g),'rules',sum(len(x['rules']) for x in g))
print('Watchdog rule present:', any(r.get('name')=='Watchdog' for x in g for r in x['rules']))"
# (c) Watchdog is firing in Prometheus AND has reached Alertmanager AFTER the restart
curl -s localhost:9099/api/v1/alerts | python3 -c "
import sys,json
a=json.load(sys.stdin)['data']['alerts']
print('Watchdog firing in Prometheus:', any(x['labels'].get('alertname')=='Watchdog' and x['state']=='firing' for x in a))
f=[x['labels'].get('alertname') for x in a if x['state']=='firing' and x['labels'].get('alertname') not in ('Watchdog','InfoInhibitor')]
print('other firing:',sorted(set(f)))"
curl -s 'localhost:9093/api/v2/alerts?filter=alertname%3DWatchdog' | python3 -c "
import sys,json;a=json.load(sys.stdin)
print('watchdog_in_AM',len(a),[(x['status']['state'],x['updatedAt']) for x in a])"
# (d) Alertmanager loaded OUR config (telegram receiver from the AlertmanagerConfig CRs)
curl -s localhost:9093/api/v2/status | python3 -c "
import sys,json;d=json.load(sys.stdin)
print('AM',d['versionInfo']['version'],'telegram receiver in config:', 'telegram' in d['config']['original'])"
kill $PF1 $PF2 2>/dev/null
```
**PASS:** (a) `targets N up N` with N = the count YOU took in §2.4 this window (100 on 2026-09-25), `down: []` — same count as the baseline YOU took
in §2.4 this window (a ±1 drift is acceptable ONLY if explained by a pod that
legitimately came or went during the window; a lower count with `down:` entries is a
fail). (b) an equal-or-higher group/rule count than your §2.4 baseline — a LOWER
count means PrometheusRules stopped being selected (the `release:
kube-prometheus-stack` ruleSelector still applies — check the operator log for
rejected rules). `Watchdog rule present: True`. *(Sanity range only, re-measured
live 2026-09-20: `groups 118 rules 478`. The stale `groups 117 rules 474` printed
here until 2026-09-20 was the 2026-09-15 figure and contradicted §2.4's own
re-measure — these numbers drift as apps come and go, which is exactly why the gate
is your in-window baseline and never a printed figure.)*
(c) `Watchdog firing in Prometheus: True`; `watchdog_in_AM 1` with state `active`
and an `updatedAt` **later than the Alertmanager pod's start time** — that is the
proof the pipeline re-established itself post-restart, not a stale reading. `other
firing` equals the §2.4 set you recorded, plus at most the transients the §3.1
silence covers. *(Re-measured 2026-09-20: `firing: 0 []` — the cluster is currently
quiet. The older `['LonghornVolumeAllocationHigh']` figure was 2026-09-15 and has
since cleared; do NOT treat its absence as a regression, and do NOT treat its
presence as one either — compare to YOUR baseline.)* (d) `AM 0.34.1` (still `0.34.0` = the operator did not roll the Alertmanager image — FAIL), `telegram
receiver in config: True`.

**4.5 — CONTENTS ASSERTIONS (chart bump on the thing that IS the scraper).**

```
CONTENTS ASSERTION 1: series still ARRIVE after the restart — measured by
  count(up == 1) and a representative series evaluated over a range that starts
  AFTER the Prometheus pod's new start time; compared to the §2.4 target count.
CONTENTS ASSERTION 2: the TSDB the new pod mounted is the OLD one — measured by
  prometheus_tsdb_lowest_timestamp_seconds; compared to the §2.4 tsdb_floor
  (2026-09-13 00:00Z when last measured 2026-09-20; must be unchanged across the
  restart, never "now"). The floor ROLLS DAILY under 7d retention, so the only
  gate is the value YOU recorded in §2.4 in this window.
CONTENTS ASSERTION 3: alerts still TRAVERSE Prometheus -> Alertmanager — measured
  by increase(alertmanager_alerts_received_total[5m]) > 0 on the new Alertmanager
  pod; compared to zero.
```

CONTROL: metric up — count(up == 1) after the restart must equal the §2.4 in-window target count (100 up of 100 on 2026-09-25)
CONTROL: metric prometheus_tsdb_lowest_timestamp_seconds — must equal the §2.4 in-window floor; a value at the new pod's start time = empty volume mounted
CONTROL: metric alertmanager_alerts_received_total — sum(increase(...[5m])) > 0 on the new pod (24.4 measured live 2026-09-25)
CONTROL: metric prometheus_tsdb_head_series — within ±10 % of the §2.4 in-window baseline
CONTROL: metric node_load1 — >= 3 samples per node over the last 2m (4 per node measured live 2026-09-25)

*(2026-09-25 review: `TargetDown` and `PrometheusOperator.*` REMOVED from the §3.1
silence — the operator alerts are exactly what a broken 0.94.x RBAC would raise, and
`TargetDown` (`for: 600s`) cannot fire inside a 2-5 min blind spot anyway.)*

```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9099:9090 >/dev/null 2>&1 & PF=$!
sleep 4
START=$(kubectl get pod -n monitoring prometheus-kube-prometheus-stack-0 -o jsonpath='{.status.startTime}')
echo "prometheus pod started: $START"
curl -s -G localhost:9099/api/v1/query --data-urlencode 'query=count(up == 1)' \
  | python3 -c "import sys,json;print('up==1 now:',json.load(sys.stdin)['data']['result'][0]['value'][1])"
curl -s -G localhost:9099/api/v1/query --data-urlencode "query=count_over_time(node_load1{job=\"node-exporter\"}[2m])" \
  | python3 -c "import sys,json;r=json.load(sys.stdin)['data']['result'];print('node-exporter samples last 2m per node:',[(x['metric'].get('instance'),x['value'][1]) for x in r])"
curl -s -G localhost:9099/api/v1/query --data-urlencode 'query=prometheus_tsdb_lowest_timestamp_seconds' \
  | python3 -c "import sys,json,datetime;v=float(json.load(sys.stdin)['data']['result'][0]['value'][1]);print('tsdb_floor',datetime.datetime.fromtimestamp(v,datetime.timezone.utc))"
curl -s -G localhost:9099/api/v1/query --data-urlencode 'query=prometheus_tsdb_head_series' \
  | python3 -c "import sys,json;print('head_series',json.load(sys.stdin)['data']['result'][0]['value'][1])"
curl -s -G localhost:9099/api/v1/query --data-urlencode 'query=sum(increase(alertmanager_alerts_received_total[5m]))' \
  | python3 -c "import sys,json;r=json.load(sys.stdin)['data']['result'];print('AM alerts received 5m:',r[0]['value'][1] if r else 'NO DATA')"
kill $PF 2>/dev/null
```
**PASS:** `up==1 now` == the §4.4(a) up count (98 at both measurements); every node
shows ≥ 3 samples in the last 2 m (≥ 5 min after the pod start — wait if not);
`tsdb_floor` **identical to the value YOU recorded in §2.4 in this window** (not to any
figure printed in this plan — retention rolls the floor daily; a floor equal to the pod
start time means an EMPTY volume was mounted — STOP, §5, and check the PVC binding);
`head_series` within ~±10 % of the §2.4 figure you just recorded (sanity range,
measured 2026-09-20: 351993 early in the day and 354416 a few hours later — i.e. it
drifts by thousands within a single day, so ONLY your in-window baseline is the
gate; 353092 on 2026-09-15) (a small rise from the new status-condition metrics is
expected; a collapse to a few thousand means targets are not being scraped);
`AM alerts received 5m` > 0 and not `NO DATA`.

**4.6 — Operator RBAC tightening did not break the operator.**

This is the ONLY gate covering the v0.94.0 ClusterRole tightening (plus the 91.5.2
narrowing of `*/finalizers` to `update`-only) — the single
genuinely new risk in this upgrade — so it must be **two-sided**: prove the log
stream is non-empty BEFORE a zero denial count is allowed to mean anything.

```bash
LOGS=$(kubectl logs -n monitoring deploy/kube-prometheus-stack-operator --since=15m 2>&1); RC=$?
LEVEL_LINES=$(printf '%s\n' "$LOGS" | grep -c 'level=')
DENIED=$(printf '%s\n' "$LOGS" | grep -ciE 'forbidden|cannot (list|watch|get|update|patch|create|delete)')
echo "logs_rc=$RC operator_log_lines=$LEVEL_LINES denied_lines=$DENIED"
printf '%s\n' "$LOGS" | grep -iE 'forbidden|cannot (list|watch|get|update|patch|create|delete)' | tail -20
printf '%s\n' "$LOGS" | grep -iE 'level=(error|warn)' | grep -v 'context canceled' | tail -20
kubectl get prometheus,alertmanager -n monitoring -o jsonpath='{range .items[*]}{.kind}/{.metadata.name}: {range .status.conditions[*]}{.type}={.status} {end}{"\n"}{end}'
```
**PASS — all three, not just the last:** `logs_rc=0` **AND**
`operator_log_lines` > 0 **AND** `denied_lines=0`; no error lines from the NEW pod
other than the documented teardown noise; both CRs `Available=True Reconciled=True`.

**Why it is written this way — the previous form PASSED ON FAILURE.** Until
2026-09-20 this gate was a bare
`kubectl logs … | grep -ciE 'forbidden|…'` with "PASS: prints `0`". MEASURED live
2026-09-20, all four controls:

| Control | Old gate | New gate |
|---|---|---|
| real operator, healthy (`--since=15m`) | prints `0` → PASS | `logs_rc=0 operator_log_lines=28 denied_lines=0` → **PASS** |
| **deployment does not exist** (renamed / never rolled) | prints `0` → **PASS (wrong)** | `logs_rc=1 operator_log_lines=0` → **FAIL** |
| **exists but stream empty** (`--since=1s`; rc=0, nothing logged) | prints `0` → **PASS (wrong)** | `logs_rc=0 operator_log_lines=0` → **FAIL** |
| a genuine denial line fed to the pattern | counts `1` → FAIL (correct) | counts `1` → **FAIL** (correct) |

So the old gate printed the identical `0` on success and on the two failures it
exists to catch. Two details that matter: `2>&1` is deliberate — it captures the
kubectl error into `$LOGS` instead of discarding it, so the failure is visible in
the output rather than silently becoming an empty stream; and the positive control
is `grep -c 'level='`, **not** `wc -l`, because a captured stderr message is also a
"line" — `wc -l` counts noise as evidence of life, while `level=` only matches real
operator log lines. (`wc -l` is additionally off by one here: measured
`level_lines=28` vs `wc -l=27` on the same stream, since the last line carries no
trailing newline.) Both greps are plain/`-E` patterns with no `\s`, so they behave
identically under BSD grep on this Mac.

If `operator_log_lines` is 0 on a genuinely healthy operator, widen the window
(`--since=30m`) before reading it as a fault — measured steady-state rate is ~2
log lines/min (28 lines in 15 min; 1901 in 24 h) — but never drop the check.

**4.7 — Grafana still reads this Prometheus, and re-read the re-labelled dashboards**
(the separate HelmRelease's datasource points at
`kube-prometheus-stack-prometheus.monitoring.svc:9090`; its `grafana-sc-dashboard`
sidecar loads the 28 `grafana_dashboard=1` ConfigMaps this chart ships). *(REASON
CORRECTED 2026-09-20 — the gate is unchanged and still fires, but not for the reason
previously written here. No dashboard JSON changes at all between 90.0.0 and 91.4.1,
nor between 91.4.1 and 91.5.2 (re-measured 2026-09-25: 35 header-only diffs);
the ConfigMaps change only in their chart-version labels, `app.kubernetes.io/version`
and `chart`, stamped by the `kube-prometheus-stack.labels` helper — §1. That label
change is what the sidecar reacts to. Do NOT expect a visible dashboard difference,
and do NOT read its absence as the sidecar having failed.)*

```bash
kubectl port-forward -n monitoring svc/grafana 3000:80 >/dev/null 2>&1 & PF=$!
sleep 3
curl -s -o /dev/null -w '%{http_code}\n' localhost:3000/api/health
kill $PF 2>/dev/null
kubectl get cm -n monitoring -l grafana_dashboard=1 -o json | python3 -c "
import sys,json; i=json.load(sys.stdin)['items']
print('kps dashboard ConfigMaps:', sum(1 for x in i if x['metadata'].get('annotations',{}).get('meta.helm.sh/release-name')=='kube-prometheus-stack'), 'of', len(i), 'total')"
kubectl logs -n monitoring deploy/grafana -c grafana-sc-dashboard --since=30m | grep -ciE 'writing|placing|updated' || true
```
**PASS:** `200`; `kps dashboard ConfigMaps: 28 of 33 total` (RE-VERIFIED live
2026-09-20 — identical to the 2026-09-15 reading; a lower kps count means the chart
stopped rendering a dashboard, a higher one is a new upstream dashboard to look at,
neither is a rollback trigger on its own); the sidecar log shows ≥ 1
write/placing line since the upgrade (it re-reads the re-labelled ConfigMaps — `0`
means the sidecar did not see them; check the sidecar's `--since` window covers the
HR upgrade time before reading it as a fault). **Note this last count is a floor,
not a delta:** the sidecar is chatty — measured 2026-09-20, `--since=24h` returns
10080 matching lines across ALL dashboard sources, not just this chart's — so use a
`--since` that starts at the HR upgrade, and treat only `0` as the failure signal.
Container name verified live: `grafana-sc-dashboard` (alongside
`grafana-sc-datasources` and `grafana`). A datasource query via the UI is the
operator's optional extra.

## 5) Rollback

Trigger: any §4 fail that a second read 5 minutes later does not clear, or Flux
remediation already rolled the release back on its own (`helm history` shows a
`rollback` revision) — in which case the git revert is still required so the
manifest matches the cluster.

**5.1 — Git revert (the real rollback).**

```bash
cd /Users/mu/code/cberg-home-nextgen
git fetch origin main && git merge --ff-only origin/main
git revert --no-edit <sha-of-3.3-commit>
git show --stat HEAD          # exactly helmrelease.yaml
git push origin main
```

Flux upgrades the release to chart 90.0.0 — a "downgrade" is just an upgrade
action with an older chart, so `upgrade.crds: CreateReplace` **re-applies the
90.0.0 CRD files (`operator.prometheus.io/version: 0.93.1`) in the same action**.
The CRD downgrade is safe because no CR uses a 0.94.x-only field (`retentionPercentage`,
`clusterPeerName` — premise-level fact: we set neither); Kubernetes prunes unknown
fields on the next write of an object, it does not reject the CRD update. Operator
returns to v0.93.1, both StatefulSets regenerate with the v0.93.1 reloader and
restart once more (same ~3-5 min blind spot); Alertmanager returns to v0.34.0 (a
patch downgrade within the same 0.34 minor; v0.34.1's only change is inhibition logic,
so no on-disk state format moves in either direction).

**5.2 — If helm is wedged `pending-upgrade`** (crash-loop during `--wait`):

```bash
helm history kube-prometheus-stack -n monitoring          # the 90.0.0 revision (40 as of 2026-09-25) must still be present (maxHistory: 2)
helm rollback kube-prometheus-stack <90.0.0-revision-from-history> -n monitoring --wait=false
mise exec -- flux reconcile helmrelease -n monitoring kube-prometheus-stack --force
```
The `flux reconcile helmrelease --force` here is a **deliberate exception** to the
SOP's "source git only" allowance (§3.4): it exists only to un-wedge a
`pending-upgrade` release that the git revert alone cannot, and it is the
break-glass path, not a step. `helm rollback` restores release resources but
**does NOT touch CRDs** — after it,
either leave the CRDs at 0.94.1 (harmless under a 0.93.1 operator: superset schema)
or let the git revert's Flux upgrade re-stamp them to 0.93.1. Do not
`kubectl apply --server-side` the 0.93.1 CRD files by hand while a helm-controller
reconcile is in flight.

**5.3 — Confirm the cluster is back.**

```bash
kubectl get helmrelease -n monitoring kube-prometheus-stack -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} {.status.history[0].chartVersion} {.status.history[0].appVersion}{"\n"}'   # True 90.0.0 v0.93.1
kubectl get deploy -n monitoring kube-prometheus-stack-operator -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'  # :v0.93.1
kubectl get crd prometheuses.monitoring.coreos.com -o jsonpath='{.metadata.annotations.operator\.prometheus\.io/version}{"\n"}'  # 0.93.1 (after the git-revert path)
```
Then re-run §4.4 and §4.5 in full — the rollback restarted Prometheus and
Alertmanager too, and the same "Watchdog reached AM after the restart" and
"tsdb_floor unchanged" proofs apply. Clear the marker
(`runbooks/update-marker.sh clear kube-prometheus-stack`), keep the plan file with
`status: blocked` and the failure quoted.

## 6) Interference notes

- **This stack IS the window's instrument — this plan MUST run LAST in its
  window, or alone. A constraint, not a preference.** The maintenance-window
  health gate, Step 0's auto-revert decision, the window agent's Step 4 "never
  start the next plan on a degraded cluster" check, the sweep alert-watcher and all
  SLO burn-rate reads come from this Prometheus, which is blind for 2-5 min during
  §3.4. **Order rule:** run this plan only AFTER Step 0 (safe-update batch) has
  been applied AND its health gate has PASSED on the old stack, and run **no other
  plan** — not its steps, not its verification — after §3.2 in the same window: a
  verification that queries Prometheus while it replays its WAL reads "no data" as
  failure, and a Step-4 gate that reads it mid-restart would refuse to continue or
  misread the restart as a regression. The derived class is HUMAN-GATED
  (autonomy_override); `exclusive: true` keeps every other plan out of the slot, and
  the attending operator enforces "after Step 0's health gate, nothing after §3.2".
- **Blind spot:** ~2-5 min with no scraping/evaluation while
  `prometheus-kube-prometheus-stack-0` restarts, ~1 min with no routing while
  `alertmanager-kube-prometheus-stack-0` restarts. Alerts that would have fired in
  that gap fire late, not never; `absent()`-guarded rules
  (`absenty-alerts.yaml` et al.) may need one extra evaluation cycle to settle.
- **Cluster-scoped CRD replace.** Every namespace holding a ServiceMonitor /
  PrometheusRule / Probe / ScrapeConfig / AlertmanagerConfig is touched in the
  schema sense (no object is rewritten). No other plan should be adding or
  changing those objects in the same window — a `PrometheusRule` applied during the
  CRD swap can land on the old or new schema unpredictably (identical for our
  fields, but the apply can transiently 404 during the Update).
- **otel-operator (`opentelemetry-kube-stack`) shares four of these CRDs.** With
  `prometheus-crd-ownership` executed first (`depends_on`), its near-weekly Step 0
  patch bumps no longer write them, so a Step 0 otel bump in the same window is
  harmless as long as it finishes BEFORE this plan (Step 0 ordering already ensures
  that), and later otel bumps cannot revert the four to 0.92.0 any more. If §2.2
  shows `installPrometheus=[]`, the dependency has not landed — no-go.
- **`otel-operator-0.23.0` — hard conflict (`conflicts_with`), and this plan should
  run AFTER it.** *(CORRECTED 2026-09-20: this bullet named `otel-operator-0.21.0`,
  which EXECUTED (`9a35168f`) and was RETIRED (`37f7c7a6`) — its file no longer
  exists. The prose therefore contradicted the frontmatter and told the window agent
  to sequence behind a plan that cannot run. The open successor is
  `otel-operator-0.23.0` — status draft, `window: null`, HUMAN-GATED — and it
  declares the same CRD mechanism; the conflict is mutual, verified 2026-09-20.)*
  Both HRs `CreateReplace` the same four CRDs, so never the same window. Ordering
  effect if THIS plan lands first: all ten CRDs read 0.94.1 and the four's
  `helm.toolkit.fluxcd.io/name` label flips from `otel-operator` to
  `kube-prometheus-stack` (the label follows the last applier). The otel plan no
  longer gates on that label (its former premise `this-hr-owns-the-prometheus-crds`
  was removed and replaced by an in-window measurement, §1 point 3), so it stays
  schedulable either way — but if it then runs *without* the ownership fix it
  downgrades the four to 0.92.0 (the accepted contention F-a85e8943). Preferred
  sequence: otel-operator-0.23.0 → prometheus-crd-ownership (attended) →
  this plan (a later nightly, alone). Note `otel-operator-0.23.0` also declares
  `depends_on: prometheus-crd-ownership`, so it cannot in fact run before that one.
- **`unpoller-v5.2.7` — LIVE hard conflict (`conflicts_with`).** *(REWRITTEN
  2026-09-20. This bullet previously read "`unpoller-v5.2.5` — conflict RESOLVED
  2026-09-16, ref dropped", which was true of v5.2.5 but actively misleading now: a
  successor plan is open and the mechanism never went away.)* `unpoller-v5.2.7` is
  open, AUTO-NIGHT, `window: null`, and its §4.3-4.5 port-forward and query THIS
  Prometheus over a ≥5-min settle — exactly the window in which the §3.4 restart
  blind spot reads as an unpoller regression and triggers a needless revert. The
  exclusion is declared on BOTH sides (verified 2026-09-20), so the two cannot share
  a nightly slot in either placement order. History, for the record: the original
  `unpoller-v5.2.5` executed (`b0ffb944`) and was retired (`f3869634`) on 2026-09-16;
  the ref then briefly pointed at `unpoller-v5.2.6`, which was itself retargeted,
  leaving a dead ref that failed `--validate` until it was repointed at
  `unpoller-v5.2.7`. **Any future unpoller plan must re-add the exclusion.**
- **Grafana.** Separate HelmRelease (`grafana`, chart 13.2.4). Its datasource and
  its `ServiceMonitor` are consumers of this stack; it does not restart. The bundled
  grafana subchart is disabled and stays disabled (two premises).
- **Storage.** `prometheus-tsdb` is an RWO `longhorn-static` volume on a
  StatefulSet — immune to the Deployment multi-attach lottery
  (`docs/sops/longhorn-rwo-multi-attach.md`). The Longhorn `daily-backup-all-volumes`
  CronJob (ns `storage`; `backup-of-all-volumes` does not exist — verified
  2026-09-15) runs 03:00; the `nightly` window starts 03:30, so a backup may still be
  finishing snapshots on this volume while the pod restarts — harmless (snapshot
  then attach), but do not run this plan concurrently with a Longhorn engine/manager
  plan.
- **Why `conflicts_with` and `depends_on` are set — refreshed 2026-09-20 against
  the WHOLE plan set, not just this file.** The rule: `window-scheduler.py` keys slot
  exclusion on `conflicts_with` ONLY; the `shared: [monitoring]` intersection is a
  shallow post-placement warning, and the prose "serialize" rules earlier drafts
  relied on are read by nobody. So every open plan whose verification reads THIS
  Prometheus must be named here. Current set, each verified open and mutual on
  2026-09-20: `unpoller-v5.2.7` (AUTO-NIGHT, window null), `edot-collector-0.161.0`
  (AUTO-NIGHT, window null), `cilium-1.20.2` (HUMAN-GATED, window null),
  `otel-operator-0.23.0` (HUMAN-GATED, window null), and `prometheus-crd-ownership`,
  which is both a dependency (ordering) and a conflict (never the same window).
  *(Historical note: the 2026-09-15 version of this bullet named
  `otel-operator-0.21.0` and `unpoller-v5.2.5`; both have since executed and been
  retired, and their successors are the entries above.)* `grafana-chart-13.2.3` is
  superseded and not a constraint.
- **Step 0 may bump the separate `grafana` HelmRelease in this very window — §4.2
  is written to survive that.** There is an open patch bump `grafana: chart 13.2.4 →
  13.2.5` (finding F-cce839da, `"type": "patch"`) with **no Renovate PR**, so the
  no-PR DIRECT-BUMP half of Step 0 owns it, and Step 0 runs FIRST in every window.
  **Do not assume the `*grafana*` deny rule holds it back: MEASURED 2026-09-20, it
  does not.** Calling the exact classifier Step 0 uses
  (`coverage.py::deny_rule_for`/`denied`) returns `grafana patch -> ALLOWED
  (eligible for AUTO/Step 0)`; only `minor` and `major` come back BLOCKED. The rule
  carries `max: patch`, and both `policy_block` and `deny_rule_for` block only when
  `RANK[update_type] > RANK[max]` — `0 > 0` is false, which the code comments call a
  "decisive ALLOW". *(This corrects the 2026-09-20 review note, which stated the
  opposite — that the deny rule made a §4.2 false-fail impossible — and marked it
  "Verified, not assumed". It is the `max:` narrowing of 2026-09-12 that changed
  this; the rule's own prose still reads as a blanket hold, which is what makes the
  mistake easy.)* Consequence: §4.2 now compares against the version recorded in
  §2.2 **in this window** instead of a hardcoded `13.2.4`, and a reading of `13.2.5`
  is correct, not a regression. This plan neither causes nor prevents that bump.
- **Future patch/minor bumps of this chart are Step 0 material** — the chart is
  not on the deny-list; only the major crosses into PLAN. After this lands, 91.x
  patches will auto-apply nightly under the normal gates.

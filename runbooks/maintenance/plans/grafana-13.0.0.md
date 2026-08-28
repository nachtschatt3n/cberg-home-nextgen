---
plan_id: grafana-13.0.0
component: grafana
pr: null                          # no Renovate PR yet (2026-08-28); if one
                                  # appears, execute by merging it instead of
                                  # the hand-edit in §3, same verification.
kind: chart
current: "12.11.2"
target: "13.0.0"
update_type: major
risk: medium
est_duration_min: 45
needs_reboot: false
touches:
  namespaces: [monitoring]
  resources:
    - helmrelease/grafana
    - pvc/grafana-config
    - "docker.io/grafana/grafana (variant change: plain -> distroless)"
  shared: []                      # grafana is a CONSUMER of shared infra
                                  # (prometheus, ES, influxdb, ingress
                                  # internal), not shared infra itself; the
                                  # alerting path does not run through it
depends_on: []
conflicts_with: []
security_ref: null                # no security driver; F-de4d92cd is cited in
                                  # the body as the -slim variant EVIDENCE record
capability_change: false          # same Grafana 13.2.0; packaging/hardening only
rollback_class: git-revert        # same appVersion both sides — no forward-only
                                  # sqlite migration is crossed (see §1)
finding_refs: [F-8c1f6717]
status: draft
window: null                      # recommend an ATTENDED window (sat-attended /
                                  # sun-attended): the datasource gate is a
                                  # judgement call, and this variant class has
                                  # burned us before (F-de4d92cd)
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/grafana-image-changes.md   # THE gate for any grafana image change
  - docs/sops/monitoring.md              # "Image variants" section + access recipes
generated: "2026-08-28"
---

# grafana: chart 12.11.2 → 13.0.0 (major — image variant flips to distroless)

## 1) Summary & why held

Held by the auto-updater as a chart **major** (finding `F-8c1f6717`). The
entire major is one upstream PR
([grafana-community/helm-charts#756](https://github.com/grafana-community/helm-charts/pull/756),
release `grafana-13.0.0`) — a packaging/hardening change, **not** a Grafana
version change:

> "The Grafana container now runs with `readOnlyRootFilesystem: true` and uses
> the `distroless` image tag by default. `/tmp` is now mounted as an `emptyDir`
> volume by default … The distroless image does not include Grafana's Docker
> `/run.sh` entrypoint. As a result, `GF_*__FILE` environment variables and the
> deprecated `GF_INSTALL_PLUGINS` environment variable are not supported with
> distroless image tags." — chart README, "To 13.0.0"

Concretely, against OUR values:

1. **`image.tag` default becomes `{{ .Chart.AppVersion }}-distroless`**
   (= `13.2.0-distroless`). We deliberately carry **no** `image.tag` pin, so
   merging this chart silently flips the running image from plain `13.2.0` to
   `13.2.0-distroless`. This is exactly the change class that killed 6/7
   datasources on 2026-08-18 with `-slim` (`security_ref: F-de4d92cd`) —
   which is why this plan exists and why `docs/sops/grafana-image-changes.md`
   is the governing SOP.
2. **appVersion stays 13.2.0.** Chart 12.11.2 already shipped Grafana 13.2.0.
   No sqlite schema migration is crossed, so — unlike a version bump — a plain
   `git revert` of the chart IS a safe rollback (SOP §11's "roll the variant,
   never the version" and this bump agree: only the variant moves).
3. **`GF_*__FILE` env vars fail chart validation on distroless**
   (new `templates/validate.yaml`). We have **none**: `env` carries only
   `GF_EXPLORE_ENABLED`, and `grafana-admin-secret` (envFromSecret) carries
   `GF_AUTH_GENERIC_OAUTH_CLIENT_ID/SECRET` + datasource vars — all plain env.
   Our secret file refs already use the native providers
   (`$__file{/etc/secrets/elasticsearch/elastic}`, `$__env{…}`), which are the
   chart's own recommended replacement. No values change required.
4. **`readOnlyRootFilesystem: true` + `/tmp` emptyDir**: sqlite + plugins +
   dashboards live on the `grafana-config` PVC at `/var/lib/grafana`; chart
   default `grafana.ini` keeps `log.mode: console` (we don't override the
   `log` section, helm coalesce preserves it). No writable-path conflict
   identified.
5. **Dashboard download init container** now runs `set -eufo pipefail`
   (xtrace OFF — it used to leak download commands to logs) and does its own
   `mkdir`. Uses the separate curl image, not distroless — unaffected by the
   entrypoint change.

**Variant risk pre-cleared (2026-08-28, registry inspection, no cluster
change):** `docker.io/grafana/grafana:13.2.0-distroless` amd64
(`sha256:4a8233a6a672604bd88f02bafad7b6631de490b3c6d3c6718a5de11e23de36e7`)
ships **13 entries in `/usr/share/grafana/data/plugins-bundled`** —
elasticsearch, grafana-postgresql-datasource, influxdb, prometheus, loki,
mysql, mssql, jaeger, tempo, zipkin, opentsdb, stackdriver,
grafana-pyroscope-datasource — **identical to the plain-image baseline
(bundled=13)**. The `-slim` failure mode (bundled dir EMPTY) does not apply.
This is why risk is `medium`, not `high`. The runtime datasource gate in §4
still runs in full — packaging facts are necessary, not sufficient.

**Known verification friction:** distroless has **no shell**. Every SOP
command that does `kubectl exec … sh -c` (§6 test 3, §8 A/C, §9 wget) will
fail on the new pod with "executable not found". §4 below substitutes
API-based checks (port-forward), which were always the authoritative gate.
Do not read an exec failure as an image failure.

## 2) Pre-checks

```bash
cd /Users/mu/code/cberg-home-nextgen

# 2.1 Cluster/component healthy, no in-flight reconcile
mise exec -- flux get hr grafana -n monitoring          # Ready=True
mise exec -- kubectl -n monitoring get pods -l app.kubernetes.io/name=grafana  # 3/3 Running, 0 recent restarts
mise exec -- flux get kustomizations -A | awk 'NR==1 || $5 != "True"'

# 2.2 grafana-config backup fresh (03:00 daily; lastBackupAt can lag one cycle —
#     cross-check newest Completed Backup CR per docs/sops/backup.md)
mise exec -- kubectl get volumes -n storage grafana-config \
  -o custom-columns=NAME:.metadata.name,LAST_BACKUP:.status.lastBackupAt --no-headers

# 2.3 BASELINE (SOP §8 A, API form — capture BEFORE the roll; the old pod dies)
POD=$(mise exec -- kubectl -n monitoring get pods -l app.kubernetes.io/name=grafana -o jsonpath='{.items[0].metadata.name}')
mise exec -- kubectl -n monitoring exec $POD -c grafana -- sh -c \
  'grafana server -v; echo bundled=$(ls /usr/share/grafana/data/plugins-bundled | wc -l)'
# expect: Version 13.2.0…, bundled=13  (exec still works — incumbent is plain)
U=$(mise exec -- kubectl -n monitoring get secret grafana-admin-secret -o jsonpath='{.data.admin-user}' | base64 -d)
P=$(mise exec -- kubectl -n monitoring get secret grafana-admin-secret -o jsonpath='{.data.admin-password}' | base64 -d)
mise exec -- kubectl -n monitoring port-forward svc/grafana 33001:80 & sleep 4
curl -s -u "$U:$P" 'http://127.0.0.1:33001/api/plugins?embedded=0&type=datasource' \
  | python3 -c 'import sys,json; d=json.load(sys.stdin); print("datasource plugins:", len(d))'
# record the number (expected 18) — §4 compares against it
kill %1

# 2.4 Render gate: pull chart 13.0.0 and template OUR values through it
#     (runs upstream validate.yaml; also proves flux-local/kubeconform will pass)
mise exec -- helm repo add grafana-community https://grafana-community.github.io/helm-charts 2>/dev/null; mise exec -- helm repo update grafana-community
mise exec -- helm template grafana grafana-community/grafana --version 13.0.0 \
  -n monitoring -f <(python3 -c "
import yaml,sys
d=yaml.safe_load(open('kubernetes/apps/monitoring/grafana/app/helmrelease.yaml'))
yaml.safe_dump(d['spec']['values'], sys.stdout)") \
  | grep -E 'image: .*grafana/grafana|readOnlyRootFilesystem|mountPath: "/tmp"'
# MUST show: image …grafana/grafana:13.2.0-distroless, readOnlyRootFilesystem: true,
# the /tmp mount — and MUST NOT fail validation. (Flux postBuild vars like
# ${SECRET_DOMAIN} render literally here; that's fine for this grep.)
```

Abort if: HR not Ready, backup missing/stale beyond one cycle, baseline
datasource count could not be captured, or the render gate fails.

## 3) Steps (GitOps)

1. Edit `kubernetes/apps/monitoring/grafana/app/helmrelease.yaml`:
   - `spec.chart.spec.version: 12.11.2` → `13.0.0`
   - **Update the comment block at the (absent) image tag** — it currently
     documents "chart default (13.2.0)"; from 13.0.0 the chart default is
     `13.2.0-distroless`. Append one dated line, e.g.:
     `# 2026-08-XX: chart 13.0.0 — default image is now 13.2.0-distroless
      (readOnlyRootFilesystem, /tmp emptyDir, no /run.sh). Bundled datasource
      backends verified = 13 (same as plain) before the roll; no exec/sh on
      this pod — verify via API only. See plan grafana-13.0.0 / F-de4d92cd SOP.`
2. Validate locally:
   ```bash
   task kubeconform
   ```
3. Commit **only** this file (shared worktree rules):
   ```bash
   git commit --only kubernetes/apps/monitoring/grafana/app/helmrelease.yaml \
     -m "feat(grafana)!: chart 12.11.2 -> 13.0.0 (distroless default, readOnlyRootFilesystem)" \
     -m "Same appVersion 13.2.0 — packaging change only. Plan: grafana-13.0.0, finding F-8c1f6717."
   git show --stat HEAD          # exactly one file
   git push
   ```
4. Let the Flux webhook reconcile. Only if slow:
   `mise exec -- flux -n monitoring reconcile hr grafana --with-source`.
   Before judging the result, confirm the values landed (SOP §8 D):
   ```bash
   mise exec -- kubectl -n monitoring get hr grafana -o jsonpath='{.spec.chart.spec.version}{"\n"}'
   ```
5. `deploymentStrategy: Recreate` — expect one brief Grafana outage while the
   pod is replaced. That is normal, not a failure signal.

## 4) Verification (run ALL — SOP §6, distroless-adapted)

```bash
POD=$(mise exec -- kubectl -n monitoring get pods -l app.kubernetes.io/name=grafana -o jsonpath='{.items[0].metadata.name}')

# 4.1 Pod healthy and on the intended image (must say 13.2.0-distroless)
mise exec -- kubectl -n monitoring get pods -l app.kubernetes.io/name=grafana
mise exec -- kubectl -n monitoring get deploy grafana \
  -o jsonpath='{range .spec.template.spec.containers[?(@.name=="grafana")]}{.image}{"\n"}{end}'

# 4.2 Schema untouched — every migrator logs performed=0 (same appVersion)
mise exec -- kubectl -n monitoring logs $POD -c grafana | grep "migrations completed"

# 4.3 No missing-plugin / unexpected-preinstall noise at startup (SOP §8 E)
mise exec -- kubectl -n monitoring logs $POD -c grafana | grep -iE 'plugin.*not found|preinstall|permission denied|read-only file system'
# "plugin … not found" or "read-only file system" => FAIL, go to §5

# 4.4 GATE (contents, not shape): full datasource check via API — NO exec on distroless
U=$(mise exec -- kubectl -n monitoring get secret grafana-admin-secret -o jsonpath='{.data.admin-user}' | base64 -d)
P=$(mise exec -- kubectl -n monitoring get secret grafana-admin-secret -o jsonpath='{.data.admin-password}' | base64 -d)
mise exec -- kubectl -n monitoring port-forward svc/grafana 33001:80 & sleep 4
curl -s -u "$U:$P" 'http://127.0.0.1:33001/api/plugins?embedded=0&type=datasource' \
  | python3 -c 'import sys,json; d=json.load(sys.stdin); print(len(d)); print(sorted(p["id"] for p in d))'
for uid in prometheus elasticsearch influxdb unpoller-influxdb pellets TeslaMate; do
  printf '%s -> ' "$uid"
  curl -s -u "$U:$P" -X POST "http://127.0.0.1:33001/api/datasources/uid/$uid/health" \
    | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d.get("status"), "|", str(d.get("message"))[:60])'
done
# Alertmanager has NO backend health check — use the proxy (the real path):
curl -s -u "$U:$P" 'http://127.0.0.1:33001/api/datasources/proxy/uid/alertmanager/api/v2/status' | head -c 120
# A real query through the data path:
curl -s -u "$U:$P" -H 'Content-Type: application/json' -X POST \
  'http://127.0.0.1:33001/api/ds/query' \
  -d '{"queries":[{"refId":"A","datasource":{"uid":"prometheus","type":"prometheus"},"expr":"count(kube_pod_info)","instant":true}]}'
kill %1

# 4.5 Still scraped (chart bump on a scraped thing): target up AND series flowing
mise exec -- kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 & sleep 3
curl -s 'http://localhost:9090/api/v1/query?query=up{namespace="monitoring",pod=~"grafana.*"}' | python3 -c 'import sys,json; r=json.load(sys.stdin)["data"]["result"]; print(r or "NO SERIES — FAIL")'
kill %1
```

**CONTENTS ASSERTION:** provisioned datasources actually work on the new
image — measured by the §4.4 datasource-plugin count (must be ≥ the §2.3
baseline, expected 18), all six `/health` checks `OK`, the Alertmanager proxy
returning config, and `/api/ds/query` returning a number — compared to the
pre-roll baseline. This fails on a stripped image even while the pod is
Ready, the UI serves, and `/api/health` says `"database": "ok"` (the exact
false-green of F-de4d92cd).

Also confirm ingress + Homepage path once: `https://grafana.<domain>` loads a
dashboard (any) behind Authentik.

## 5) Rollback

Same appVersion on both sides ⇒ no migration crossing ⇒ chart revert is safe
and complete:

```bash
git revert <sha-of-step-3-commit> && git push
mise exec -- flux -n monitoring reconcile ks grafana --with-source
mise exec -- flux -n monitoring reconcile hr grafana
# Confirm back: deploy image == docker.io/grafana/grafana:13.2.0 (plain),
# chart version 12.11.2 in the HR, then RE-RUN §4.4 — a rollback is a change
# and needs the same gate. Expect "migrations completed … performed=0" again.
```

Fallback only if the datasource gate fails but the operator wants to keep
chart 13.0.0 anyway: pin `image.tag: "13.2.0"` (plain) in values — the chart
permits non-distroless tags (validation only rejects `GF_*__FILE` **with**
distroless). That contradicts the file's "no pin" stance, so it requires
updating the comment block and `docs/sops/grafana-image-changes.md` in the
same commit. Config-store damage (not expected here): `grafana-config`
Longhorn backup, 03:00 daily.

## 6) Interference notes

- **Namespace `monitoring` is busy but nothing templates Grafana's
  resources**: kube-prometheus-stack sets `grafana.enabled: false` (this HR
  alone owns Grafana), unpoller's plan (`unpoller-v4`) is `blocked` and
  unscheduled, eck/edot/headlamp are separate HRs. No resource overlap.
- **Sequence AFTER Step 0.** The same window's safe-update batch will likely
  touch monitoring too (kube-prometheus-stack 88.6.0, edot 0.159.0 are
  pending minors). Run this plan only after Step 0's health gate passes, so a
  regression attributes to one change, not two.
- **Expected blips, do not page:** one Recreate outage of the Grafana UI
  (~1–2 min) and a matching gap in the grafana ServiceMonitor scrape. The
  alerting path (Prometheus → Alertmanager → Telegram) does not run through
  Grafana (`handleGrafanaManagedAlerts: false`); dashboards are the only
  user-visible impact.
- **Verification tooling changes permanently:** post-merge, no `kubectl exec
  … sh` and no in-pod `wget` on the grafana container. Health snippets in
  `docs/sops/grafana-image-changes.md` §6/§8/§9 and `docs/sops/monitoring.md`
  that exec into the pod need a distroless follow-up edit after execution
  (note it in the executing commit; do not pre-edit the SOP before the roll).
- **Why attended:** the pass/fail call on the datasource gate plus this
  variant class's history (F-de4d92cd) warrant an operator present; the
  mechanics themselves are low-drama. No reboot, no shared-infra restart.

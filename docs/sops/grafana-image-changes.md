# SOP: Grafana Image Changes — the datasource pre-flight gate

> Description: How to change the Grafana container image (tag, variant, or chart-driven bump) without silently breaking datasources, and why "the pod started and the UI loads" is not evidence that it worked.
> Version: `2026.08.18`
> Last Updated: `2026-08-18`
> Owner: `homelab-sre`

---

## 1) Description

Grafana's datasource *backends* ship as plugin binaries inside the image. Which
binaries are present is a property of the **image variant**, and from 13.2.0 the
bundled binary **is** the delivery mechanism for a core datasource — not a
duplicate of something compiled into `bin/grafana`. An image that omits them
starts cleanly, serves the UI, answers `/api/health` with `"database": "ok"`,
and has no working Prometheus.

Every ordinary readiness signal passes. That is the whole problem, and it is why
this SOP exists as a gate rather than a checklist item.

- Scope: `kubernetes/apps/monitoring/grafana/app/helmrelease.yaml` — any change
  to `image.tag`, `image.repository`, the chart version, or anything that alters
  which plugins ship or are preinstalled.
- Prerequisites: repo-pinned tooling via `mise exec --`, cluster access.
- Out of scope: dashboard/datasource *provisioning* content (that is
  `docs/sops/monitoring.md`), and Grafana's Authentik integration.

---

## 2) Overview

| Setting | Value |
|---------|-------|
| Namespace | `monitoring` |
| HelmRelease | `grafana` (kube-prometheus-stack sets `grafana.enabled: false`, so this release alone owns Grafana) |
| Image | chart default — **no `image.tag` override**, deliberately |
| Config store | sqlite on the `grafana-config` Longhorn PVC (`longhorn-static`) |
| Provisioned datasources | 7 — Alertmanager, Prometheus, Elasticsearch, InfluxDB, Unpoller InfluxDB, TeslaMate, Pellets |
| Rejected variant | `-slim` on 13.x — see §7 |
| Evidence record | `security_ref: F-de4d92cd` |

**Three facts that drive everything below.**

1. **Datasource backends live in `/usr/share/grafana/data/plugins-bundled`.**
   Upstream expanded that set from 2 entries to 13 across 13.2.0 (PR #129593),
   as preparation for extracting core datasources from the monolith. These are
   packaging facts, not scan results.
2. **Plugins persisted on the PVC are untrustworthy evidence.** `/var/lib/grafana/plugins`
   survives image changes. A stripped image can present a handful of plugins that
   are leftovers from a *previous* image, so "it has datasources" proves nothing
   about the image you just rolled.
3. **The sqlite schema migration is forward-only.** Grafana 13 migrates on boot.
   Once a newer minor has booted against `grafana-config`, rolling the *version*
   back is a downgrade across a completed migration. Rollback is therefore a
   variant/tag change within the same version, never a chart revert.

---

## 3) Blueprints

No new manifest. The change is a values edit on the existing HelmRelease:

```yaml
# kubernetes/apps/monitoring/grafana/app/helmrelease.yaml
spec:
  values:
    image:
      tag: "<candidate>"        # omit entirely to follow the chart default
    env:
      # Required for ANY image that ships plugins-bundled empty, or the
      # container re-downloads them from grafana.com at startup and the
      # shipped image stops matching the running container.
      GF_PLUGINS_PREINSTALL_DISABLED: "true"
```

---

## 4) Operational Instructions

1. **Record the incumbent baseline first** (§8, command A). You cannot judge the
   candidate without it, and after the roll the old pod is gone.
2. Decide the candidate. Prefer the chart default; a pin needs a reason written
   at the tag.
3. **Pre-flight the candidate image OFF the live PVC** (§8, command B) — this is
   the step that makes the PVC-leftover trap unreachable. If you skip it, do
   §8 command C immediately after the roll and be ready to revert.
4. Edit the HelmRelease. Commit and push; let Flux reconcile (no manual apply).
5. `flux -n monitoring reconcile hr grafana` only if the webhook is slow. Note
   the HelmRelease values must have landed **before** the helm upgrade runs —
   confirm `kubectl -n monitoring get hr grafana -o jsonpath='{.spec.values.image}'`
   shows your change, or you will reconcile the old values and conclude wrongly.
6. Run **every** Verification Test in §6. Not a subset.
7. If any datasource fails: revert immediately (§11). Do not debug in place —
   monitoring is the thing you debug *with*.

---

## 5) Examples

**Following the chart default (current, intended state).** No `image` key at
all. The comment block at the tag explains why, so the absence reads as a
decision rather than an omission.

**Pinning a variant.** Add `image.tag` plus the preinstall env var, and a
comment stating what was verified and when.

---

## 6) Verification Tests

Run all of these. Tests 3 and 4 are the gate; 1 and 2 are necessary but prove
nothing on their own.

```bash
POD=$(mise exec -- kubectl -n monitoring get pods -l app.kubernetes.io/name=grafana \
        -o jsonpath='{.items[0].metadata.name}')

# 1. Pod healthy and on the intended image
mise exec -- kubectl -n monitoring get pods -l app.kubernetes.io/name=grafana
mise exec -- kubectl -n monitoring get deploy grafana \
  -o jsonpath='{range .spec.template.spec.containers[?(@.name=="grafana")]}{.image}{"\n"}{end}'

# 2. Schema untouched — expect performed=0 on every migrator
mise exec -- kubectl -n monitoring logs $POD -c grafana | grep "migrations completed"

# 3. GATE: the image actually ships the datasource backends
mise exec -- kubectl -n monitoring exec $POD -c grafana -- \
  sh -c 'echo bundled=$(ls /usr/share/grafana/data/plugins-bundled 2>/dev/null | wc -l)'
# Compare against the incumbent baseline from §8 command A. A DROP is a failure,
# even if the UI works.

# 4. GATE: every provisioned datasource resolves AND returns data
U=$(mise exec -- kubectl -n monitoring get secret grafana-admin-secret -o jsonpath='{.data.admin-user}' | base64 -d)
P=$(mise exec -- kubectl -n monitoring get secret grafana-admin-secret -o jsonpath='{.data.admin-password}' | base64 -d)
mise exec -- kubectl -n monitoring port-forward svc/grafana 33001:80 &
sleep 4
# plugin inventory — compare the COUNT to the baseline
curl -s -u "$U:$P" 'http://127.0.0.1:33001/api/plugins?embedded=0&type=datasource' \
  | python3 -c 'import sys,json; d=json.load(sys.stdin); print(len(d)); print(sorted(p["id"] for p in d))'
# per-datasource health
for uid in prometheus elasticsearch influxdb unpoller-influxdb pellets TeslaMate; do
  printf '%s -> ' "$uid"
  curl -s -u "$U:$P" -X POST "http://127.0.0.1:33001/api/datasources/uid/$uid/health" \
    | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d.get("status"), "|", str(d.get("message"))[:60])'
done
# Alertmanager implements NO backend health check — /health reports
# "Plugin unavailable" even when healthy. Use the proxy, which is the real path.
curl -s -u "$U:$P" 'http://127.0.0.1:33001/api/datasources/proxy/uid/alertmanager/api/v2/status' | head -c 120
# a real query through the data path, not just a connection test
curl -s -u "$U:$P" -H 'Content-Type: application/json' -X POST \
  'http://127.0.0.1:33001/api/ds/query' \
  -d '{"queries":[{"refId":"A","datasource":{"uid":"prometheus","type":"prometheus"},"expr":"count(kube_pod_info)","instant":true}]}'
```

**Pass criteria:** bundled-plugin count not lower than baseline; datasource
plugin count not lower than baseline; all six health checks `OK`; Alertmanager
proxy returns config; the `/api/ds/query` call returns a number.

---

## 7) Troubleshooting

**`-slim` on 13.x — tested and rejected 2026-08-18.** Applied in `c8a1f6e9`,
reverted in `f08a32e9` four minutes later. The pod started, the tag existed, and
the chart did not override the pin — the **datasource gate** failed.
`plugins-bundled` was empty, the API exposed a fraction of the expected
datasource plugins, and every one that remained was a PVC leftover. Grafana
logged `reason="plugin prometheus not found"`. Six of seven provisioned
datasources would have been dead. Do not retry on 13.x without first confirming
upstream has restored compiled-in core datasources.

**`GF_PLUGINS_PREINSTALL_DISABLED` is load-bearing, not optional.** Upstream also
grew `defaultPreinstallPlugins` from 6 to 18. Without the env var a stripped
image re-downloads the same binaries at startup, so the shipped image and the
running container diverge — the image is no longer a description of what runs.
It also adds a grafana.com egress dependency at pod start.

**"It works, I can see datasources in the UI."** Check whether they are PVC
leftovers (§8 command C). This is the specific trap that makes a naive check
pass a fatal image.

**Alertmanager reports `Plugin unavailable`.** Expected — that datasource type
implements no backend health check. Verify via the proxy path instead.

**`grafana-oss`** is deprecated (since 12.4.0) and its newest tag is far behind.
Not a variant option.

---

## 8) Diagnose Examples

```bash
# A. BASELINE — capture BEFORE any change
POD=$(mise exec -- kubectl -n monitoring get pods -l app.kubernetes.io/name=grafana -o jsonpath='{.items[0].metadata.name}')
mise exec -- kubectl -n monitoring exec $POD -c grafana -- sh -c \
  'grafana server -v; echo bundled=$(ls /usr/share/grafana/data/plugins-bundled | wc -l)'

# B. PRE-FLIGHT a candidate WITHOUT the live PVC — the trap-proof check.
#    A throwaway pod mounts no grafana-config, so /var/lib/grafana/plugins is
#    empty and what you count is exactly what the IMAGE ships. This is the one
#    check the PVC-leftover trap cannot fool.
#    Use -i, not -it: with -it the attach races container startup and prints a
#    "couldn't attach, falling back to streaming logs" warning. Output is the
#    same either way, but the warning reads like a failure.
mise exec -- kubectl -n monitoring run grafana-preflight --rm -i --restart=Never --quiet \
  --image=docker.io/grafana/grafana:<candidate> --command -- \
  sh -c 'echo bundled=$(ls /usr/share/grafana/data/plugins-bundled 2>/dev/null | wc -l); \
         echo persisted=$(ls /var/lib/grafana/plugins 2>/dev/null | wc -l)'
# Verified 2026-08-18 against the incumbent 13.2.0: bundled=13, persisted=0.
# `persisted=0` is the proof the count is untainted. The pod self-deletes.

# C. Distinguish shipped plugins from PVC leftovers on a running pod
mise exec -- kubectl -n monitoring exec $POD -c grafana -- sh -c \
  'echo "shipped:"; ls /usr/share/grafana/data/plugins-bundled 2>/dev/null | wc -l;
   echo "persisted on PVC:"; ls /var/lib/grafana/plugins 2>/dev/null | wc -l'

# D. Did the values actually land before the upgrade ran?
mise exec -- kubectl -n monitoring get hr grafana -o jsonpath='{.spec.values.image}{"\n"}'
mise exec -- helm -n monitoring history grafana | tail -3

# E. Startup errors that name a missing plugin
mise exec -- kubectl -n monitoring logs $POD -c grafana | grep -iE 'plugin.*not found|preinstall|migrat'
```

---

## 9) Health Check

```bash
mise exec -- kubectl -n monitoring get pods -l app.kubernetes.io/name=grafana
mise exec -- kubectl -n monitoring get hr grafana
mise exec -- kubectl -n monitoring get pvc grafana-config
mise exec -- kubectl -n monitoring exec deploy/grafana -c grafana -- \
  wget -qO- localhost:3000/api/health
```

Expect the pod `3/3 Running` with 0 restarts, HelmRelease `Ready=True`, PVC
`Bound`, and `"database": "ok"`. Note again that all four can pass with dead
datasources — this section is a liveness check, not the gate.

---

## 10) Security Check

- Scan figures for any candidate image belong on the finding record, never in
  the manifest, a commit message, or this SOP
  (`docs/sops/vulnerability-disclosure.md`). Plugin/package **counts used to
  compare packaging** are fine; counts of findings are not.
- Grafana's ingress is `ingressClassName: internal`. Any change that would move
  it to `external` is out of scope here and needs its own review.
- Admin credentials come from the `grafana-admin-secret` Secret. The
  verification commands above read them into shell vars — do not echo them, and
  do not paste command output containing them into a plan file or commit.
- `GF_PLUGINS_PREINSTALL_DISABLED=false` (or absent, on a stripped image) means
  the pod fetches executable content from the internet at startup. Treat that as
  a supply-chain change, not a config tweak.

---

## 11) Rollback Plan

**Roll the variant/tag, never the version.** The sqlite migration is
forward-only, so a chart revert or a minor-version downgrade is the riskiest
available move and is not the rollback path.

```bash
git revert <sha> && git push
mise exec -- flux -n monitoring reconcile ks grafana --with-source
mise exec -- flux -n monitoring reconcile hr grafana
# then re-run §6 tests 3 and 4 — a rollback is a change and needs the same gate
```

Verified 2026-08-18: reverting `-slim` to the plain tag restored all datasources,
and both boots logged `migrations completed performed=0` with `grafana.db`
byte-identical, so the round trip did not touch the schema.

If the config store itself is ever damaged, the fallback is the `grafana-config`
Longhorn backup (03:00 daily).

---

## 12) References

- `kubernetes/apps/monitoring/grafana/app/helmrelease.yaml` — the comment block at the tag
- [monitoring.md](monitoring.md) — "Image variants: plain vs `-slim`", Grafana access, dashboards
- [vulnerability-disclosure.md](vulnerability-disclosure.md) — where scan figures live
- [longhorn.md](longhorn.md) — `grafana-config` static PV/PVC pattern
- Finding record: `security_ref: F-de4d92cd`

---

## Version History

| Version | Date | Change |
|---------|------|--------|
| `2026.08.18` | 2026-08-18 | Initial SOP. Written from the `13.2.0-slim` roll+revert: the datasource gate, the PVC-leftover trap that makes a naive check pass a fatal image, the preinstall env var, and variant-not-version rollback. |

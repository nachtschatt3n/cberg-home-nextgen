---
plan_id: unpoller-v4
component: unpoller
pr: null
kind: image+chart                     # BOTH halves, one window — see §2
current: "image v3.5.0 / chart 2.4.0"
target: "image v4.0.0 + the first v4-aware chart (DOES NOT EXIST YET — see §1)"
update_type: major
risk: medium
est_duration_min: 30
needs_reboot: false
touches:
  namespaces: [monitoring]
  resources:
    - helmrelease/unpoller
    - "ghcr.io/unpoller/unpoller"
  shared: []                          # writes to InfluxDB; no other component templates it
depends_on: []
conflicts_with: []
status: blocked                       # BLOCKED ON UPSTREAM: no v4-aware chart published
window: null                          # cannot be scheduled until the chart exists
# auto_execute RETIRED 2026-08-26 (P2.1b) — execution class is now DERIVED
# from capability_change/rollback_class per runbooks/autonomy-policy.yaml.
# (original rationale: image major + chart move in lockstep)
security_ref: F-a5ceabc1
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/monitoring.md
generated: "2026-08-19"
---

# unpoller: v3.5.0 → v4.0.0 (blocked on a v4-aware chart)

## 1) Why this is blocked, and the check that decides it

Upstream published **image v4.0.0 on 2026-08-19**, one day after v3.5.0. The
chart repo has not followed:

```
$ curl -sL https://unpoller.github.io/helm-chart/index.yaml   # 2026-08-19
chart 2.4.0 -> appVersion v3.5.0 | 2026-08-18   <-- newest
chart 2.3.0 -> appVersion v3.4.1 | 2026-08-18
chart 2.1.0 -> appVersion v2.21.0 | 2026-01-02
```

So there is no chart that templates for v4. Setting `image.tag: v4.0.0` under
chart 2.4.0 runs a v4 binary against v3-shaped values — the same lockstep split
that made `unpoller-v3` retarget twice.

**Re-run exactly that curl before doing anything else.** If the newest entry
still maps to appVersion v3.5.0, this plan stays blocked; there is nothing to
execute and no window to take. That check is the whole gate.

## 2) The trap this plan exists to prevent

> The predecessor plan carried the note *"Remove this rule when unpoller-v3 has
> executed"* against the `*unpoller*` deny rule in
> `runbooks/auto-update-policy.yaml`. unpoller-v3 HAS executed. **Following that
> instruction would have re-armed the failure it was written to prevent** — with
> the rule gone, the v4 image major scores as a normal bump and lands unattended
> at Step 0 of the next maintenance window, against a v3-only chart.
>
> The rule was therefore retargeted, not removed (2026-08-19). Do not remove it
> when this plan executes either — rewrite its reason for whatever the next
> mismatch is, or leave it in place.

`coverage.py::_apply_lockstep` does not save us here: it only fires when a
sibling is HELD, and after v3 executed neither half was.

## 3) Steps (once a v4-aware chart exists)

1. Re-run the index check in §1; record the chart version and its appVersion.
2. Read the v4.0.0 release notes for config/flag breaking changes — v4 is a
   major and unpoller's config surface (InfluxDB output, Prometheus exporter,
   UniFi auth) is exactly where a major breaks.
3. Cross-check the chart's `values.yaml` diff against ours — the retarget in
   unpoller-v3 was caused by values moving between chart versions.
4. Edit `kubernetes/apps/monitoring/unpoller/app/helmrelease.yaml`: chart
   `version:` and `image.tag` in ONE commit.
5. Push; let Flux reconcile. Do not manually reconcile.

## 4) Verification (contents, not shape)

`Ready=True` is not proof — a running unpoller that has stopped writing points
looks identical to a healthy one.

1. Pod Ready and no restarts after 5 minutes.
2. Logs show a successful UniFi controller login, not an auth loop.
3. **Point count rises**: query InfluxDB for the newest timestamp in an unpoller
   measurement before and after; it must advance. A frozen series is the failure
   this step exists to catch.
4. The Grafana UniFi dashboards render current data, not a flat line.

## 5) Rollback

Revert the single commit (chart + image together) and let Flux reconcile.
unpoller holds no persistent state of its own — it is a scraper writing to
InfluxDB — so a revert is clean and loses only the points from the bad window.

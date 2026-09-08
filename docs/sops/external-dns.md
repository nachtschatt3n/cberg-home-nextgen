# SOP: external-dns — public DNS publication (Cloudflare, `policy: sync`)

> Description: How public DNS records for this cluster are created, changed and destroyed by external-dns, why `policy: sync` makes a failed *create* a total outage rather than a no-op, and the version/annotation traps that have taken public DNS down twice in two days.
> Version: `2026.09.08`
> Last Updated: `2026-09-08`
> Owner: `homelab-sre`

---

## 1) Description

external-dns is the only writer of public DNS for this household. Every
internet-facing hostname under `${SECRET_DOMAIN}` exists because external-dns
published it and continues to exist because external-dns keeps re-asserting it.
There is no manually-maintained record set to fall back on.

This SOP exists because that component had **zero alert coverage** until
2026-09-08, and on that day a routine-looking image pin took every public
hostname down for 94 seconds. It was caught only because the operator happened
to be awake. The SOP covers what to know before touching it, and what the new
alerts mean when they fire.

- **Scope**: `kubernetes/apps/network/external/external-dns/` (HelmRelease +
  SOPS secret), the `external-dns.alpha.kubernetes.io/target` annotation on
  `kubernetes/apps/network/envoy-gateway/app/gateways.yaml`, and
  `kubernetes/apps/monitoring/kube-prometheus-stack/app/external-dns-alerts.yaml`.
- **Prerequisites**: mise toolchain, cluster `kubectl`, and — for anything that
  changes the record set — an **attended** window. external-dns is on the
  auto-update deny-list (`runbooks/auto-update-policy.yaml`, policy
  `2026.09.08.1`) at every update type, in both the PR-merge and direct-bump
  lanes.
- **Out of scope**: internal DNS. LAN names are served by k8s-gateway
  (`docs/sops/k8s-gateway-dns.md`) and AdGuard, neither of which external-dns
  touches. The Cloudflare tunnel itself is `docs/sops/cloudflare.md`.

### The one thing to internalise: `policy: sync` deletes before it creates

This deployment runs `policy: sync`, not `upsert-only`. Under `sync`,
external-dns owns the record set absolutely: anything it believes should no
longer exist is **removed**, and a changed record is applied as a
*delete-then-create* pair.

The consequence is the entire reason for this document:

> **A failed create is not a no-op. It is an outage.**

Under `upsert-only`, a rejected write leaves the previous record in place and
you lose nothing but the update. Under `sync`, the old record is already gone by
the time the create is attempted, so a provider rejection leaves the hostname
with **no record at all** — public NXDOMAIN for every name in the affected set.
There is no partial degradation and no self-healing while the cause persists.

Treat any external-dns change as a change that can withdraw public DNS, and
capture the record set before and after (§4).

---

## 2) Overview

| Setting | Value |
|---------|-------|
| Namespace | `network` |
| Source of truth | `kubernetes/apps/network/external/external-dns/helmrelease.yaml` |
| Chart / image | `external-dns` 1.21.1 / `registry.k8s.io/external-dns/external-dns:v0.21.0` |
| Provider | `cloudflare`, `--cloudflare-proxied` |
| Policy | **`sync`** — deletes records, and delete-then-creates on change |
| Sources | `crd` (`DNSEndpoint`) + `gateway-httproute` |
| Gateway allowlist | `--gateway-name=envoy-external`, `--gateway-namespace=network` (default-deny, one Gateway) |
| Record target | `external-dns.alpha.kubernetes.io/target` on the **Gateway** `envoy-external` |
| Registry | TXT, `txtPrefix: k8s.`, `txtOwnerId: default` |
| Domain filter | `${SECRET_DOMAIN}` |
| Steady-state record count | 25 verified CNAMEs (healthy 24h floor: 24) |
| Sync interval / staleness | ~60 s; worst observed excursion 147 s |
| Metrics | `--metrics-address=0.0.0.0:7979`, ServiceMonitor at 30 s |
| Alerts | `external-dns.sync.health` + `external-dns.metrics.presence` (§9) |
| Auto-update | **DENIED at every update type**, both lanes |

Two properties of the config are load-bearing and easy to undo by accident:

- **`sources: ["crd", "gateway-httproute"]`** — `ingress` was dropped on
  2026-09-08 because the cluster holds zero `Ingress` objects after
  ingress-nginx was deleted (`ad1ea7c2`). It was safe *precisely because the
  count is zero*: under `policy: sync`, an unlisted source whose objects still
  exist would have its records **deleted**. If an Ingress is ever reintroduced,
  the source must be added back **before** the object is created.
- **`--gateway-name` / `--gateway-namespace`** form a default-deny allowlist of
  exactly one Gateway. A route whose parents are not in that set yields no
  endpoints, so a typo, a rename or a newly-added gateway all fail **closed**
  (not published) rather than open. `--ingress-class=external` filters Ingress
  objects only and has no effect on the gateway source. `--gateway-name` takes
  a single name: if a second externally-facing Gateway is ever added, switch to
  `--gateway-label-filter` and label that Gateway explicitly.

---

## 3) Blueprints

- HelmRelease: `kubernetes/apps/network/external/external-dns/helmrelease.yaml`
- Cloudflare API token (SOPS): `kubernetes/apps/network/external/external-dns/secret.sops.yaml`
- Target annotation: `kubernetes/apps/network/envoy-gateway/app/gateways.yaml`
- Alert rules: `kubernetes/apps/monitoring/kube-prometheus-stack/app/external-dns-alerts.yaml`

**The target annotation goes on the GATEWAY, never on the HTTPRoute.**
external-dns runs `--source=gateway-httproute`, and for that source it derives
each record's target from the **parent Gateway**. An
`external-dns.alpha.kubernetes.io/target` annotation on an `HTTPRoute` is
**silently ignored** — no error, no warning, no event. Set it once:

```yaml
# Gateway envoy-external, namespace network — set ONCE, cluster-wide
apiVersion: gateway.networking.k8s.io/v1
kind: Gateway
metadata:
  name: envoy-external
  namespace: network
  annotations:
    external-dns.alpha.kubernetes.io/target: "external.${SECRET_DOMAIN}"
```

Every HTTPRoute attached to that Gateway then publishes a proxied CNAME to the
tunnel hostname. Routes attached to `envoy-internal` publish nothing public,
which is the intended default-deny.

### Version trap: v0.22.x needs `--default-targets` in the SAME change

**v0.22.x stops honouring the target annotation on the parent Gateway.** It
publishes the Gateway's own address instead — here the private LAN address
`192.168.55.104` — which Cloudflare refuses as the content of a *proxied*
record. Every create is rejected, and under `policy: sync` the originals are
already deleted.

A bare version bump is therefore **known-broken regardless of its semver
label**. Moving to v0.22.x requires a manifest change landed in the same commit:

```yaml
    extraArgs:
      # REQUIRED from v0.22.0: the Gateway annotation is no longer read.
      - --default-targets=external.${SECRET_DOMAIN}
```

This is why `*external-dns*` is denied in `runbooks/auto-update-policy.yaml` at
every update type. The hazard is not the image pin itself — that one was
attended and reverted in 94 s (`aa79cf7a`) — it is that chart 1.22.x will ship
appVersion 0.22.0 and would classify as a **safe MINOR**, landing at Step 0 of
an unattended nightly 03:30 window with nobody watching. `security_ref:
F-14528040`.

---

## 4) Operational Instructions

Every change follows GitOps: edit manifests, commit, push, let the Flux webhook
reconcile. Never `kubectl apply` or hand-edit records in the Cloudflare UI —
under `policy: sync` a hand-made record is deleted at the next reconcile.

**1. Capture the record set BEFORE the change.** This is the diff baseline and,
if things go wrong, the list of what has to come back.

```bash
cd /Users/mu/code/cberg-home-nextgen
mise exec -- kubectl -n network logs -l app.kubernetes.io/name=external-dns --tail=500 \
  > /tmp/edns-before.log
mise exec -- kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 &
curl -s 'http://localhost:9090/api/v1/query?query=external_dns_controller_verified_records' \
  | python3 -m json.tool > /tmp/edns-records-before.json
```

**2. Make the change.** For a version move, land the manifest change and the
version change in **one commit** (see §3). For a routing change, confirm the
target annotation lives on the Gateway, not the route.

**3. Commit and push** (shared worktree — explicit paths):

```bash
git commit --only kubernetes/apps/network/external/external-dns/helmrelease.yaml -F msg.txt
git show --stat HEAD          # is every file here actually yours?
git push
```

**4. Watch the reconcile and the record count together.** The HelmRelease going
Ready proves nothing about DNS.

```bash
mise exec -- flux get helmreleases -n network external-dns
mise exec -- kubectl -n network logs -l app.kubernetes.io/name=external-dns -f
```

**5. Run the verification tests in §6 before walking away.** A 94-second outage
is entirely survivable if you are watching and have a revert ready; it is not if
you have already closed the terminal.

### Adding a new public hostname

1. Create the `HTTPRoute` with `parentRefs` → Gateway `envoy-external`,
   namespace `network`, `sectionName: https`
   (`docs/sops/gateway-api-httproute.md`).
2. Do **not** add `external-dns.alpha.kubernetes.io/target` to the route — it is
   inert there and its presence misleads the next reader into thinking routing
   is configured when it is not.
3. Commit + push; external-dns picks it up within ~60 s.
4. Verify with §6 Test 1.

---

## 5) Examples

### Example A: routine health snapshot

```bash
cd /Users/mu/code/cberg-home-nextgen
mise exec -- kubectl -n network get pods -l app.kubernetes.io/name=external-dns
mise exec -- kubectl -n network logs -l app.kubernetes.io/name=external-dns --tail=50 \
  | grep -iE 'error|level=error' || echo "no errors in last 50 lines"
```

### Example B: version bump to v0.22.x (attended, one commit)

```bash
# helmrelease.yaml — BOTH edits in the same change set:
#   chart version   1.21.1 -> 1.22.x
#   extraArgs       + --default-targets=external.${SECRET_DOMAIN}
mise exec -- kubeconform -summary -fail-on error kubernetes/apps/network/external/external-dns
git commit --only kubernetes/apps/network/external/external-dns/helmrelease.yaml -F msg.txt
git show --stat HEAD && git push
# then STAY and watch — §6 Test 1 and Test 2, and keep `git revert` ready
```

### Example C: what NOT to do

```bash
# ❌ bumping the image/chart alone — known-broken from v0.22.0, and `sync`
#    has already deleted the old records by the time the create is rejected
# ❌ putting external-dns.alpha.kubernetes.io/target on an HTTPRoute — inert
# ❌ creating a record by hand in the Cloudflare UI — deleted at next reconcile
# ❌ removing an entry from `sources:` while objects of that kind still exist
```

---

## 6) Verification Tests

### Test 1: the record set is intact and proxied

```bash
mise exec -- kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 &
curl -s 'http://localhost:9090/api/v1/query?query=external_dns_controller_verified_records' \
  | python3 -c "
import sys, json
for r in json.load(sys.stdin)['data']['result']:
    print(r['metric'].get('record_type'), r['value'][1])"
```

Expected:
- `cname` count is **25** (healthy 24h floor 24). A value in the low single
  digits is the 2026-09-08 outage shape.

If failed:
- Read the controller log for provider rejections (Test 2), then §11.

### Test 2: no provider rejections

```bash
mise exec -- kubectl -n network logs -l app.kubernetes.io/name=external-dns --tail=200 \
  | grep -iE 'error|9003|not allowed'
```

Expected:
- no output.

If failed:
- `9003 / "Target is not allowed for a proxied record"` means external-dns is
  publishing a **private A target** instead of the CNAME. See §8 Diagnose 1.

### Test 3: public resolution end-to-end

```bash
# resolve against a public resolver, NOT the LAN resolver — AdGuard/k8s-gateway
# answer internally and will happily mask a missing public record
dig +short @1.1.1.1 auth.${SECRET_DOMAIN}
```

Expected:
- a Cloudflare proxied address, not `NXDOMAIN` and not `192.168.55.x`.

If failed:
- `NXDOMAIN` → the record was deleted and not recreated (Test 1 + Test 2).
- a `192.168.55.x` answer → the target annotation is not being honoured (§3).

### Test 4: the alert rules are actually LOADED

A `PrometheusRule` missing `release: kube-prometheus-stack` is **silently never
loaded** — no error, no event, and the file looks fine in git.

```bash
curl -s http://localhost:9090/api/v1/rules \
  | python3 -c "
import sys, json
names = [r['name'] for g in json.load(sys.stdin)['data']['groups'] for r in g['rules']]
for a in ['ExternalDNSRegistryErrors','ExternalDNSSourceErrors','ExternalDNSSyncStalled',
          'ExternalDNSRecordsCollapsed','ExternalDNSErrorMetricsAbsent','ExternalDNSSyncMetricsAbsent']:
    print(f'{a:32} {\"LOADED\" if a in names else \"*** MISSING ***\"}')"
```

Expected:
- all six `LOADED`.

If failed:
- check the three `kube-prometheus-stack` labels on the PrometheusRule. Never
  verify this with `kubectl apply` success.

---

## 7) Troubleshooting

| Symptom | Likely Cause | First Fix |
|---------|--------------|-----------|
| Public hostname `NXDOMAIN`, LAN resolution fine | Record deleted by `sync` and the recreate was rejected | §8 Diagnose 1; `git revert` the last external-dns/Gateway change |
| Log shows `9003` / `Target is not allowed for a proxied record` | Publishing a private A target instead of the tunnel CNAME | Target annotation missing on the Gateway, or on v0.22.x without `--default-targets` (§3) |
| Annotation is on the HTTPRoute and nothing happens | `gateway-httproute` source reads the **parent Gateway** only; route annotation is inert | Move it to `envoy-external` in `gateways.yaml` |
| A new hostname is never published | Its route's `parentRefs` is not `envoy-external`/`network` | The gateway allowlist fails **closed** by design — fix `parentRefs` |
| Records for one app vanish after a manifest change | Its source was removed from `sources:`, or its Gateway was renamed | Restore the source/name; under `sync` an unlisted source is a delete instruction |
| `ExternalDNSSyncStalled` with no errors | Controller wedged: it never tries, so it never books an error | `kubectl -n network rollout restart deploy/external-dns` |
| Everything green but records are wrong | Alerts may be blind — check the `*MetricsAbsent` guards | §6 Test 4 |

```bash
# Quick debugging
mise exec -- kubectl -n network logs -l app.kubernetes.io/name=external-dns --tail=200
mise exec -- kubectl -n network describe deploy external-dns
mise exec -- kubectl -n network get servicemonitor external-dns
mise exec -- kubectl -n network get gateway envoy-external -o jsonpath='{.metadata.annotations}'
```

---

## 8) Diagnose Examples

### Diagnose Example 1: public DNS is down after an external-dns change

```bash
# 1. is the record set collapsed?
curl -s 'http://localhost:9090/api/v1/query?query=external_dns_controller_verified_records' \
  | python3 -m json.tool | grep -A2 cname

# 2. what is the provider rejecting, and with what target?
mise exec -- kubectl -n network logs -l app.kubernetes.io/name=external-dns --tail=200 \
  | grep -iE '9003|not allowed|error'

# 3. what target does external-dns think it should publish?
mise exec -- kubectl -n network get gateway envoy-external \
  -o jsonpath='{.metadata.annotations.external-dns\.alpha\.kubernetes\.io/target}'; echo

# 4. what version is actually running?
mise exec -- kubectl -n network get deploy external-dns \
  -o jsonpath='{.spec.template.spec.containers[0].image}'; echo
```

Expected:
- A collapsed cname count **plus** `9003` rejections **plus** a private-IP target
  in the log confirms the annotation/version trap: either the Gateway annotation
  is gone, or the image is v0.22.x without `--default-targets`.

If unclear:
- Compare `/tmp/edns-before.log` from §4 step 1 against the current log. The
  first line that changed shape is the change that did it.

### Diagnose Example 2: alerts are green but something is clearly wrong

```bash
curl -s 'http://localhost:9090/api/v1/query?query=absent(external_dns_registry_errors_total)'
curl -s 'http://localhost:9090/api/v1/query?query=absent(external_dns_controller_last_sync_timestamp_seconds)'
mise exec -- kubectl -n network get servicemonitor external-dns
mise exec -- kubectl -n network get endpoints external-dns
```

Expected:
- Both `absent()` queries return **no result** (the metrics exist). A result of
  `1` means the detectors are blind: a rule matching no series sits at
  `state=inactive` and looks healthy forever.

If unclear:
- Check the ServiceMonitor carries `release: kube-prometheus-stack` and that
  `--metrics-address=0.0.0.0:7979` is still in `extraArgs`.

---

## 9) Health Check

```bash
cd /Users/mu/code/cberg-home-nextgen
mise exec -- kubectl -n network get pods -l app.kubernetes.io/name=external-dns
mise exec -- kubectl -n network logs -l app.kubernetes.io/name=external-dns --tail=100 | grep -i error
mise exec -- kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 &
curl -s 'http://localhost:9090/api/v1/query?query=external_dns_controller_verified_records{record_type="cname"}'
curl -s 'http://localhost:9090/api/v1/query?query=time()-external_dns_controller_last_sync_timestamp_seconds'
```

Expected:
- pod `1/1 Running`, no errors, cname count ≥ 24, sync staleness < 150 s.

### The alert rules, and what each means when it fires

Added 2026-09-08 (`b88109a2`). Every threshold is derived from a **measured**
series, with the measurement recorded next to the rule in the manifest.

**Group `external-dns.sync.health`** — the detectors:

| Alert | Expression | Severity | What it means |
|---|---|---|---|
| `ExternalDNSRegistryErrors` | `increase(external_dns_registry_errors_total[10m]) > 0`, `for: 5m` | critical | **Treat as an active public-DNS outage, not a warning.** external-dns is failing to write at the provider, and under `policy: sync` the old record is already deleted — so hostnames are unresolvable *now*. Baseline is exactly zero errors over 7 days. Go to §8 Diagnose 1. |
| `ExternalDNSSourceErrors` | `increase(external_dns_source_errors_total[10m]) > 0`, `for: 5m` | warning | external-dns cannot read its Kubernetes sources (`crd`, `gateway-httproute`). Publishing stalls and the record set drifts from cluster state, but nothing is being deleted by this alone — hence warning. |
| `ExternalDNSSyncStalled` | `time() - external_dns_controller_last_sync_timestamp_seconds > 900`, `for: 5m` | critical | The controller is not reconciling at all. Records are frozen at their last state and every cluster change is unpublished. **This is the case the error alerts cannot catch: a controller that never tries never books an error.** Normal interval ~60 s, worst observed 147 s; 900 s is ~6× that. Also covers "came up and never synced" — the gauge reads 0 before the first sync, and `for: 5m` rides through a healthy start. |
| `ExternalDNSRecordsCollapsed` | `external_dns_controller_verified_records{record_type="cname"} < 20`, `for: 3m` | critical | Published records have been deleted and not recreated. This is the exact 2026-09-08 failure shape. Steady state 25, healthy 24h floor 24, incident pod 1. `for: 3m` rather than 5m because a collapsed record set is unambiguous and already user-visible. |

`increase()` over a 10-minute window rather than `rate`/`irate` is
load-bearing: the outage lasted 94 seconds, so an instantaneous expression would
go true and false again well inside any sane `for:` and would never fire.

**Group `external-dns.metrics.presence`** — the blindness guards:

| Alert | Expression | Severity | What it means |
|---|---|---|---|
| `ExternalDNSErrorMetricsAbsent` | `absent(external_dns_registry_errors_total)`, `for: 15m` | warning | `ExternalDNSRegistryErrors` and `ExternalDNSSourceErrors` are **currently blind** and will stay green no matter what the provider does. Either external-dns is not running or its ServiceMonitor stopped being scraped. |
| `ExternalDNSSyncMetricsAbsent` | `absent(external_dns_controller_last_sync_timestamp_seconds)`, `for: 15m` | warning | `ExternalDNSSyncStalled` and `ExternalDNSRecordsCollapsed` are **currently blind**. |

Both guards exist because a rule whose metric family stops reporting does not
fail — it matches no series and sits at `state=inactive`, i.e. it looks exactly
like "healthy" forever. This repo has been bitten by that before. **A firing
`*MetricsAbsent` alert is not cosmetic: it means the four detectors above are
not protecting anything.**

---

## 10) Security Check

```bash
cd /Users/mu/code/cberg-home-nextgen
# 1. the Cloudflare API token is SOPS-encrypted, never plaintext
head -20 kubernetes/apps/network/external/external-dns/secret.sops.yaml | grep -q "sops:" \
  && echo "OK: encrypted" || echo "FAIL: not encrypted"
grep -rn "CF_API_TOKEN" kubernetes/apps/network/external/external-dns/helmrelease.yaml
# expect only a secretKeyRef — never a literal

# 2. the gateway allowlist has not been widened
mise exec -- kubectl -n network get deploy external-dns \
  -o jsonpath='{.spec.template.spec.containers[0].args}' | tr ',' '\n' | grep -E 'gateway|source|policy'

# 3. nothing internal has leaked to public DNS
mise exec -- kubectl get httproute -A \
  -o jsonpath='{range .items[*]}{.metadata.namespace}/{.metadata.name} {.spec.parentRefs[*].name}{"\n"}{end}' \
  | grep envoy-external
```

Expected:
- token present only as a `secretKeyRef`; no plaintext token anywhere in git.
- `--gateway-name=envoy-external` and `--gateway-namespace=network` both present
  — **removing either widens publication to every Gateway in the cluster**, which
  would push internal-only hostnames onto public DNS.
- the `envoy-external` route list contains only hostnames that are *intended* to
  be internet-facing. Anything unexpected there is a public exposure, not a DNS
  bug.
- no real domain committed anywhere — `${SECRET_DOMAIN}` only.

---

## 11) Rollback Plan

`rollback_class: git-revert`. external-dns holds no state of its own: the TXT
registry is derived, and the record set is re-asserted from cluster state on the
next sync. Reverting the manifest restores the records.

```bash
cd /Users/mu/code/cberg-home-nextgen
git revert <sha>          # the external-dns or Gateway commit
git push                  # Flux webhook reconciles
mise exec -- kubectl -n network logs -l app.kubernetes.io/name=external-dns -f
```

Recovery is ~60 s once the correct target is being published — the 2026-09-08
incident was 94 s end to end. **Do not** use `git reset --hard` or force-push,
and do not hand-create records in the Cloudflare UI to "bridge the gap": under
`policy: sync` they are deleted at the next reconcile, and they make the real
record set harder to reason about while you are diagnosing.

If a revert does *not* restore the records, the cause is upstream of
external-dns — check the Gateway still exists and still carries the target
annotation, then the tunnel (`docs/sops/cloudflare.md`).

---

## 12) References

- `kubernetes/apps/network/external/external-dns/helmrelease.yaml`
- `kubernetes/apps/network/envoy-gateway/app/gateways.yaml`
- `kubernetes/apps/monitoring/kube-prometheus-stack/app/external-dns-alerts.yaml`
- `runbooks/auto-update-policy.yaml` — the `*external-dns*` deny rule
- [`gateway-api-httproute.md`](gateway-api-httproute.md) — HTTPRoute pattern
- [`cloudflare.md`](cloudflare.md) — the tunnel the CNAMEs point at
- [`k8s-gateway-dns.md`](k8s-gateway-dns.md) — internal DNS (separate system)
- [`new-deployment-blueprint.md`](new-deployment-blueprint.md) §11 — the
  annotation-on-the-Gateway gotcha
- [`auto-update.md`](auto-update.md) — why this component is deny-listed
- `security_ref: F-14528040`

---

## Version History

- `2026.09.08`: Initial SOP. Created after external-dns took public DNS down for
  94 s on an attended v0.21.0 → v0.22.0 image pin (reverted in `aa79cf7a`), and
  the follow-up found it had **zero** alert coverage — none of the 382 loaded
  alerting rules matched it. Captures the `policy: sync` delete-before-create
  semantics, the Gateway-not-HTTPRoute annotation rule, the v0.22.x
  `--default-targets` requirement, the Cloudflare `9003` signature, and the six
  alert rules added in `b88109a2`.

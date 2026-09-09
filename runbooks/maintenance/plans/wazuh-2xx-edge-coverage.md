---
plan_id: wazuh-2xx-edge-coverage
component: wazuh
pr: null
kind: infra
current: "Edge HTTP detection (Wazuh rules 100700-100708, ported to Envoy Gateway access logs 2026-09-09 in 9d9dad86) sees only non-2xx traffic — the level-0 baseline rule deliberately keeps 2xx/3xx out of the indexer for volume. Authentication that SUCCEEDS is therefore invisible at the edge. The stated mitigation was 'app-level and Authentik logging'; measured 2026-09-09, that mitigation does not exist: Authentik writes successful logins to its Postgres `authentik_events_event` table ONLY (no stdout line, no webhook transport, no notification rule on `action: login`), Wazuh has zero authentik decoders or rules, and the `client_ip` Authentik does record is the envoy-external POD IP, identical for every external user."
target: "Phase 1 ONLY, and only Phase 1 is windowed here: Authentik records the true client IP on every auth event, so that any later detection has an identity axis to correlate on. Phases 2 and 3 (getting successful-auth out of Authentik, and building the detection) are scoped in §7 and each need their own plan."
update_type: install                  # this is new detection capability, not a version bump
risk: medium                          # touches the request path of the external
                                      # gateway, i.e. every internet-facing app
est_duration_min: 45                  # PHASE 1 ONLY. Phases 2-3 are not in this number.
needs_reboot: false
touches:
  namespaces: [network, kube-system]
  resources:
    - "gateway/envoy-external (network)"
    - "clientTrafficPolicy / envoy-gateway policies.yaml"
    - helmrelease/authentik
    - deployment/authentik-server
  shared: [gateway/envoy]             # the external gateway's request path
depends_on: []
conflicts_with: []                    # deliberately EMPTY. The plans that could
                                      # collide are other gateway/envoy changes;
                                      # none is open today. No forward reference
                                      # to an unconfirmed plan_id — a dangling
                                      # ref silently disables the guard.
capability_change: false              # no user-visible behaviour change; this
                                      # changes what gets RECORDED, not what the
                                      # apps do
autonomy_override: human-gated        # RESTRICTS only. A change on the external
                                      # gateway's request path must not run
                                      # unattended, whatever the policy derives.
rollback_class: git-revert            # pure manifest change; revert + reconcile
status: draft                         # PROPOSED, not approved. Goes to
                                      # awaiting-go when the window agent or the
                                      # operator picks it up; the window below is
                                      # a capacity claim, not a granted go.
window: "sat-attended:2026-09-26"     # attended (external request path), and the
                                      # first Saturday with real slack: 09-12
                                      # already holds 4 plans / 100 min against a
                                      # 90 min cap, and 09-19 holds
                                      # media-audit-durable-output at 45 min, so
                                      # adding this plan's 45 would put that slot
                                      # at exactly 90/90 with zero margin. 09-26
                                      # is empty. NOT sun-attended:2026-09-27,
                                      # which is at 140 of 150 min for talos-1.14.0,
                                      # and not a Sunday slot generally — this is
                                      # not reboot work.
security_ref: null                    # the gap itself is already described in
                                      # 9d9dad86 in this repo; no undisclosed
                                      # vulnerability detail is added here
finding_refs:
  - F-aae0f363                        # external attack attribution blind: real client IP absent
sops_refs:
  - docs/sops/gateway-api-httproute.md
  - docs/sops/authentik.md
  - docs/sops/monitoring.md
  - docs/sops/verification-contents-not-shape.md
generated: "2026-09-09"
---

# Close the 2xx blind spot at the edge — Phase 1: recover the client IP

## 1. Summary & why this is held

`9d9dad86` ported HTTP edge detection from ingress-nginx to Envoy Gateway access
logs (rules 100700–100708) and recorded a deliberate blind spot: the level-0
baseline rule keeps 2xx/3xx out of the indexer, because the volume of successful
requests would swamp it. That is the right trade for volume. Its consequence is
narrow and specific:

> **Credential stuffing that SUCCEEDS is undetected at the edge.**
> A wrong password produces a 4xx and is seen. A *right* password — stolen,
> reused, or the 4.7-month-public Superset one — produces a 2xx and is not.

The commit named the mitigation as "app-level and Authentik logging". **This plan
begins by reporting that the mitigation does not currently exist.** Every claim
below was measured read-only on 2026-09-09.

### 1.1 What Authentik actually emits for a successful login

| Question | Measured answer |
|---|---|
| Is there a stdout line for a successful login? | **No.** Only failures appear: an `invalid_login` / `invalid_identifier` JSON line. Phrase searches for `Created Event` / `authentik.events` over 48h return zero. |
| Where do successful logins go? | The Postgres table `authentik_events_event` **only**. Over 24h: `login` ×2, `authorize_application` ×2, `login_failed` ×1. |
| Is there a webhook / forwarding transport? | **No.** Only the stock `default-email-transport` and `default-local-transport`, and the three notification rules are `default-notify-{configuration-error,update,exception}` — **none matches `action: login`**. |
| Env config that could change this? | None. The HelmRelease sets only `AUTHENTIK_SECRET_KEY`, the five `AUTHENTIK_POSTGRESQL__*`, and `AUTHENTIK_SESSIONS__UNAUTHENTICATED_AGE`. No `AUTHENTIK_LOG_LEVEL`, no `AUTHENTIK_EVENTS__*`, no `AUTHENTIK_LISTEN__TRUSTED_PROXY_CIDRS`. |

So the data a 2xx detection would key on exists in exactly one place, is reachable
only by querying a Postgres table nothing currently queries, and is not on any
path to Wazuh or Elasticsearch.

### 1.2 What Wazuh sees from Authentik

The **collection** path exists; the **parse and detect** path does not.

- The agent tails `/host/var/log/containers/*.log` with a single exclusion
  (`*_security_*.log`), so `kube-system_authentik-server-*.log` *is* being read
  (`kubernetes/apps/security/wazuh/app/wazuh-config-configmap.yaml`).
- There is **no authentik decoder and no authentik rule** anywhere in
  `kubernetes/apps/security/wazuh/` — the only four matches are passing comments
  in the envoy and unifi decoders.
- Ground truth on the manager: authentik-derived alerts in `alerts.json` = **0**.
- `logall`/`logall_json` are `no`, so there is no archive to retro-hunt either.

### 1.3 The blocker that makes Phase 1 first: the client IP is destroyed

Authentik recorded `client_ip: "::ffff:10.69.0.235"` on both the `login` and the
`login_failed` event. That address is the **`envoy-external` gateway pod itself**
(`network/envoy-external-…`, node k8s-nuc14-02) — not the true client, not even
the Cloudflare edge.

The cause is in `kubernetes/apps/network/envoy-gateway/app/policies.yaml`: the
external gateway uses `clientIPDetection.customHeader: CF-Connecting-IP`
(`failClosed: false`). Consequently `x-forwarded-for` is NULL on ~96% of external
requests, and Authentik — with no `AUTHENTIK_LISTEN__TRUSTED_PROXY_CIDRS`
override — falls back to the socket peer, which is always the gateway pod.

**Every external login from every user currently records one of three pod IPs.**
GeoIP is loaded and working in Authentik (`GeoLite2-City` and `GeoLite2-ASN`
MMDBs), so the enrichment is *ready* and *useless*: it geolocates our own cluster.

That kills, in advance, every detection anyone would reasonably propose here —
impossible-travel, new-device-from-new-ASN, unusual-hour-from-unusual-country,
burst-of-successes-from-one-IP. All of them are `client_ip` correlations. It also
means the *existing* failed-login signal is already degraded in the same way.

**Therefore Phase 1 is not preparation for the real work. It is the precondition
without which the real work produces confident nonsense.** A plan that skipped
straight to writing rules would ship a detector that groups the whole household
into one bucket and reports it as normal.

### 1.4 Two constraints on the design, both learned this week

- **Do NOT propose an Elasticsearch field aggregation over Envoy data.** Envoy
  access logs arrive in ES as an unparsed JSON string in `body.text`; there is no
  parsed field structure. Wazuh sees fields only because it parses raw log lines.
  Any design whose detection step is an ES `terms` aggregation on an Envoy field
  is unimplementable as written.
- **`body.text` is mapped `keyword` with `ignore_above: 1024`** (verified on
  `.ds-logs-generic-default-2026.09.05-000191`). Two consequences: no
  phrase/full-text search (`match_phrase` returns 0 where `wildcard` returns
  >10k), and **44 authentik-server documents per 24h exceed 1024 characters and
  are not indexed at all** — which is precisely the
  `/api/v3/flows/executor/default-authentication-flow/?query=…` login-flow lines.
  They are present in `_source` and unqueryable. Any ES-side route must fix that
  index template first, with its own volume consequences. This is a second reason
  the Wazuh route is preferred over the ES route.
- **`downstream_remote_address` carries a `:port` suffix.** Where an Envoy-side
  detection uses it as the client IP, the port must be stripped before
  correlation, or per-IP grouping fragments into one bucket per connection and
  every threshold silently becomes unreachable.

## 2. Scope of THIS plan

**In scope (Phase 1, 45 min):** make Authentik record the true client IP on every
auth event, and prove it with a real login.

**Explicitly out of scope, each needing its own plan:** emitting successful-auth
off-box (Phase 2), and the decoder + ruleset + thresholds that turn it into
detection (Phase 3). §7 scopes both so the sequencing is on the record; neither
is windowed here and neither should be started before Phase 1 verifies.

## 3. Pre-checks

```bash
cd /Users/mu/code/cberg-home-nextgen

# 3.1 Baseline: what does Authentik record RIGHT NOW? (this is the §5 baseline)
mise exec -- kubectl -n kube-system exec deploy/authentik-pg -- \
  psql -U authentik -d authentik -c \
  "select action, client_ip, created from authentik_events_event
    where action in ('login','login_failed','authorize_application')
    order by created desc limit 20;"
# EXPECT (the defect): client_ip is a 10.69.0.x pod address on every row.

# 3.2 Which pods own those addresses — confirm they are the gateway, not clients
mise exec -- kubectl get pods -A -o wide | grep -E 'envoy-external|envoy-internal'

# 3.3 Current gateway client-IP config
sed -n '1,60p' kubernetes/apps/network/envoy-gateway/app/policies.yaml

# 3.4 Cluster quiet + external routing healthy before touching the gateway
mise exec -- flux get kustomizations -A | awk 'NR==1 || $5 != "True"'
mise exec -- kubectl -n network get gateway envoy-external -o wide
```

### 3.5 Diagnose BEFORE changing anything — which layer drops the IP?

There are two candidate layers and the remedy differs. **Do not guess.** Capture
the headers Authentik actually receives:

```bash
# Tail an authentik-server pod while performing ONE login from an external client,
# then inspect the request line and any XFF/CF-Connecting-IP header it logged.
mise exec -- kubectl -n kube-system logs deploy/authentik-server --tail=200 -f
```

- **Case A — Envoy is not forwarding a usable header.** `CF-Connecting-IP` is
  consumed for client-IP detection but nothing propagates the resolved address
  to the backend. Remedy: configure the external gateway's client traffic policy
  to append the resolved client IP to `x-forwarded-for` for backends.
- **Case B — Envoy forwards it, Authentik does not trust it.** Remedy:
  `AUTHENTIK_LISTEN__TRUSTED_PROXY_CIDRS` covering the pod CIDR.

The measured evidence leans to Case A (the recorded peer `10.69.0.235` is inside
the private ranges Authentik trusts by default, so had an XFF header been
present it should already have been used) — **but that is an inference, and this
step is what turns it into a measurement.** Apply only the remedy the diagnosis
selects; applying both blindly makes the verification unattributable.

## 4. Steps

1. Run §3.5 and write down which case it is.
2. Apply the corresponding remedy as a GitOps change:
   - **Case A:** edit `kubernetes/apps/network/envoy-gateway/app/policies.yaml`
     so the external gateway propagates the resolved client IP to backends.
     Keep `failClosed: false` — changing it in the same commit would conflate a
     logging fix with an availability decision.
   - **Case B:** add `AUTHENTIK_LISTEN__TRUSTED_PROXY_CIDRS` to the authentik
     HelmRelease env, scoped to the pod CIDR only.
3. Validate and commit on exactly the touched paths (shared worktree):
   ```bash
   mise exec -- task kubeconform
   git commit --only <the one path you edited> -F /tmp/msg.txt
   git show --stat HEAD      # every file must be yours
   git push
   ```
4. Watch Flux reconcile; for Case A confirm the gateway's Envoy deployment rolled
   and every external HTTPRoute is still `Accepted`.

## 5. Verification

```
CONTENTS ASSERTION — the recorded client IP is the REAL client, not the gateway:
  perform ONE login from a known external client whose public IP you know, then
  re-run the §3.1 query. The newest `login` row's `client_ip` must equal that
  public IP. Compared against the §3.1 baseline, where every row was 10.69.0.x.

  This is the assertion, and nothing weaker substitutes for it:
   - "Authentik pods are Ready" is green today, with the defect present.
   - "the header is now set" proves the header, not what Authentik stored.
   - "client_ip changed" is not enough — it must change to a value you can
     independently confirm is your client's address. A different WRONG IP (the
     Cloudflare edge) reads as success and re-buries the same problem one layer
     out.

NEGATIVE CONTROL — prove the assertion could have failed:
  perform a second login from an internal LAN client via envoy-internal. Its
  `client_ip` must be that host's 192.168.x address, NOT the external client's
  and NOT a pod IP. Two logins from different networks yielding two different,
  correct addresses is what distinguishes "IP propagation works" from "one
  hardcoded value happens to match".
```

Plus, because this touches the external request path:

```bash
# every external app still routes (the change's real blast radius)
mise exec -- kubectl -n network get httproutes -A -o wide | awk 'NR==1 || $0 !~ /True/'
mise exec -- kubectl -n network get gateway envoy-external -o yaml | grep -A5 conditions
```

Then run `health-check-agent` and `security-agent`.

## 6. Rollback

`git revert` the single commit from §4.3 and push; Flux restores the previous
gateway policy or authentik env within one reconcile. There is no state change to
undo — nothing was migrated, and the Authentik event rows already written keep
whatever `client_ip` they were written with. Confirm rollback with the §3.1 query
returning to pod IPs.

## 7. Phases 2 and 3 — scoped here, NOT windowed here

Recorded so the sequencing survives this plan and nobody restarts the analysis.

### Phase 2 — get successful-auth out of Authentik (~1 window)

Preferred: a **blueprint-managed** `notificationtransport` of mode `webhook` plus
a `notificationrule` bound to an `EventMatcherPolicy` on `action: login`, in
`kubernetes/apps/kube-system/authentik/app/configmap.sops.yaml`. UI-only
configuration is forbidden (`docs/sops/authentik.md`), and a webhook needs a
receiver, so Phase 2 cannot start until the receiver is chosen.

**Reject the cheap alternative:** `AUTHENTIK_LOG_LEVEL=debug` would surface a
`Created Event` line on stdout, but these pods already ship **77,882 documents
per 24 h** from authentik-server alone (mostly `/health/live`, `/health/ready`,
`/metrics` probe noise). Turning up debug to extract ~2 login events per day is
a five-figure-per-day log-volume decision to solve a two-event-per-day problem,
and `docs/sops/log-volume-runaway.md` exists because of exactly that shape.

### Phase 3 — the detection (~1 window, plus a baseline period)

Wazuh route, preferred (the ES route is blocked by the `body.text` mapping in
§1.4):

- A **fifth** decoder/rules ConfigMap, following the existing per-source layout
  (`unifi-decoder`, `envoy-decoder`, `wazuh-local-rules`, `wazuh-config`), plus
  its `<rule_dir>` entry in `wazuh-config-configmap.yaml`, its `kustomization.yaml`
  entry, and its mount in `wazuh-manager-statefulset.yaml`.
- **Rule IDs: allocate from `100800-100899`.** In use today, repo-wide:
  `100102-100128`, `100150-100153`, `100199-100204`, `100210`, `100300`,
  `100400-100404`, `100410-100415`, `100600`, `100610`, `100620-100622`,
  `100700-100708`. IDs must be unique across ALL rule ConfigMaps.
- **Reload contract:** analysisd reads rules only at process start. A new or
  edited ConfigMap requires bumping its `checksum/<name>` annotation on the
  manager StatefulSet (`sha256sum <configmap>.yaml | awk '{print substr($1,1,12)}'`).
  Without the bump the rules load silently as *nothing*.
- **Load-order trap:** a child `<if_sid>` resolves only against rules already
  loaded, and `local` loads before `unifi`/`envoy`. Chaining off a built-in is
  safe; chaining off another custom rule is not, without deliberate `<rule_dir>`
  ordering.
- **Thresholds must be measured, not invented.** The house standard set by the
  100705/100707 comments is a measured base rate over N real requests. With ~2
  logins/day across the household, a "burst of successes from one IP" threshold
  guessed at 10 would never fire, and an inert rule sitting at
  `state=inactive` looks exactly like a healthy one. Pair any rule with an
  `absent()`-style guard so a rule that matches nothing is visible as a fault.
- **There is no Wazuh rule-authoring SOP** — `docs/sops/falco.md` is about
  exempting a built-in Falco rule and explicitly puts the Wazuh decoder side out
  of scope; `docs/sops/wazuh-siem-recovery.md` is recovery-only. Writing one is
  part of Phase 3, not optional polish.

Candidate detections, once client IP is real: new-ASN-for-user, first-seen-device
(`context.auth_method_args.known_device` is already recorded), unusual-hour, and
success-following-failures-from-the-same-IP. The last one is the closest thing to
a direct credential-stuffing signal and is the only one that also uses the
existing 4xx-side coverage.

## 8. Interference notes for the window agent

- **Shared infra:** `gateway/envoy`. Case A rolls the external gateway's Envoy
  deployment — a brief external-routing blip for every internet-facing app. Do
  not co-schedule with any other plan touching Gateway API, cert-manager, or
  external-dns; in particular this and `external-dns-unowned-cnames` must not
  share a window (both perturb the external request/name path, and a failure in
  either would be misattributed to the other). They are deliberately one week
  apart — this at `sat-attended:2026-09-26`, that at `sat-attended:2026-10-03`.
  Not encoded in `conflicts_with:` because both plans are `draft`; promote to a
  real pair when either is vetted, and never write a forward reference to a
  plan_id that has not been confirmed to exist.
- **Attended only** (`autonomy_override: human-gated`), because the change is on
  the request path of every external app and the verification requires a human to
  perform a login from a known external address.
- **The verification needs an external client.** Schedule it when someone can
  reach the services from off-LAN; an operator on the LAN alone cannot complete
  §5.
- **Case B is materially smaller than Case A** (an authentik env var, no gateway
  roll). If §3.5 selects Case B, tell the window agent — the slot frees ~25 min.

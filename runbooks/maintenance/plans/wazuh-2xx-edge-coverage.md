---
plan_id: wazuh-2xx-edge-coverage
component: wazuh
pr: null
kind: infra
current: "Phase 1's goal is ALREADY MET (re-measured 2026-09-26). envoy-external switched from `customHeader: CF-Connecting-IP` to `xForwardedFor.trustedCIDRs: [10.69.0.0/16]` in 2df8ec7f (2026-09-11), and authentik got `AUTHENTIK_LISTEN__TRUSTED_PROXY_CIDRS: 10.69.0.0/16` on server+worker in f2d6c667 (2026-09-22, F-649e78b6, resolved). authentik_events_event since 2026-09-11 09:00: 0 login/login_failed rows with a pod (10.69.x) client_ip, 7 with a public client_ip, all carrying a residential/mobile ISP ASN (none Cloudflare); the same query over 2026-09-01..09-11 09:00 returns 4 pod-IP rows. The 2xx edge blind spot itself (Phases 2-3) is NOT closed: successful auth is still not shipped off-box."
target: "Phase 1 VERIFICATION ONLY, no manifest change: prove on authentik 2026.8.3 that a fresh external login records the operator's real public IP and a fresh LAN login records the LAN address, then retire Phase 1. Phases 2 and 3 (getting successful-auth out of Authentik, and building the detection) are scoped in section 7 and each need their own plan."
update_type: n/a                      # verification only; nothing is installed or bumped
risk: low                             # read-only: two logins + SELECTs; no manifest,
                                      # gateway or authentik change
est_duration_min: 15
needs_reboot: false
touches:
  namespaces: [kube-system]
  resources:
    - "authentik_events_event (SELECT only, via deployment/authentik-pg)"
  shared: [authentik]                 # its baseline must be taken on the
                                      # post-upgrade authentik, never mid-roll
depends_on: []   # 2026-09-26: authentik-2026.8.3 EXECUTED + retired (d4ccfa09, last outpost push 06:25:51Z);
                                      # the client_ip baseline must still be taken on 2026.8.3 after
                                      # its 20-min soak - enforced live by section 3.0
conflicts_with:
  # - authentik-2026.8.3 (RESOLVED 2026-09-26: executed + retired; ref removed) # reciprocal of its own conflicts_with entry;
                                      # a roll mid-verification makes the login
                                      # land on a terminating pod
  # - authentik-pg17-decommission   # RESOLVED 2026-09-26: executed + retired in the now:2026-09-26 run; ref removed
  - talos-1.14.1                      # a node roll evicts authentik-server mid-verification
capability_change: false              # records nothing new, changes nothing
autonomy_override: human-gated        # RESTRICTS only. The verification needs a
                                      # human to log in from a known off-LAN
                                      # address; it cannot run unattended.
rollback_class: git-revert            # nothing is changed, so nothing to roll back
status: vetted   # 2026-09-26 plan-reviewer needs-fix -> rewritten check-only (Phase 1 already shipped in 2df8ec7f + f2d6c667); depends_on authentik-2026.8.3 + 20-min soak
window: "now:2026-09-26"   # ON-DEMAND NOW run 2026-09-26 (run-now.py stamp; was None)
security_ref: null                    # the client-IP defect this plan was written
                                      # for is FIXED (F-649e78b6 resolved,
                                      # f2d6c667); F-aae0f363 (the ingress-nginx
                                      # ES-field finding) was resolved 2026-09-20.
                                      # Neither is open, and a fixed defect needs
                                      # no DB-held detail.
finding_refs: []                      # re-checked 2026-09-26: `finding list --grep`
                                      # wazuh/authentik/client/login/attribution/edge
                                      # returns no open finding for this target.
                                      # F-649e78b6 and F-aae0f363 are both resolved.
premises:
  - id: authentik-server-trusts-pod-cidr
    why: "Phase 1 is met only because authentik-server trusts XFF from the pod CIDR (f2d6c667). If this was reverted, the plan is stale and Phase 1 is open again."
    run: kubectl get deploy -n kube-system authentik-server -o jsonpath='{.spec.template.spec.containers[0].env[?(@.name=="AUTHENTIK_LISTEN__TRUSTED_PROXY_CIDRS")].value}'
    expect_exact: "10.69.0.0/16"
  - id: authentik-worker-trusts-pod-cidr
    why: "f2d6c667 mirrors the setting on the worker; both env blocks must stay identical."
    run: kubectl get deploy -n kube-system authentik-worker -o jsonpath='{.spec.template.spec.containers[0].env[?(@.name=="AUTHENTIK_LISTEN__TRUSTED_PROXY_CIDRS")].value}'
    expect_exact: "10.69.0.0/16"
  - id: envoy-external-xff-pod-cidr-only
    why: "The external gateway must resolve the client from XFF trusting only the pod CIDR (2df8ec7f). A return to customHeader, or any extra trusted range, changes what authentik records."
    run: kubectl get clienttrafficpolicy -n network envoy-external-client -o jsonpath='{.spec.clientIPDetection}'
    expect_exact: '{"xForwardedFor":{"trustedCIDRs":["10.69.0.0/16"]}}'
sops_refs:
  - docs/sops/authentik.md
  - docs/sops/gateway-api-httproute.md
  - docs/sops/verification-contents-not-shape.md
generated: "2026-09-09"
---

# Close the 2xx blind spot at the edge — Phase 1: recover the client IP

> **Status 2026-09-26 (plan-reviewer re-measurement): Phase 1's goal is already
> met.** Sections 1.1-1.3 below are the 2026-09-09 diagnosis and are kept as the
> historical "why"; they no longer describe the cluster. The client-IP loss was
> fixed in two commits: `2df8ec7f` (envoy-external: `customHeader` ->
> `xForwardedFor` trusting only the pod CIDR, 2026-09-11) and `f2d6c667`
> (authentik: `AUTHENTIK_LISTEN__TRUSTED_PROXY_CIDRS` = pod CIDR, 2026-09-22).
> Since 2026-09-11 09:00 no `login`/`login_failed` row carries a pod address and
> every external login carries a residential or mobile ISP address. This plan is
> therefore VERIFICATION ONLY: one fresh external and one fresh LAN login on
> authentik 2026.8.3, then Phase 1 is retired. Phases 2-3 (section 7) remain open
> and still need their own plans.

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
- Ground truth on the manager confirms the consequence: the rules that do not
  exist have never produced an alert. Retention/archive posture is recorded on
  `F-aae0f363` rather than here — see §1.6.

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

### 1.6 Disclosure posture — what still needs to move off this file

A security-agent pass on 2026-09-09 rated this file **Warning** under the
two-part test in `docs/sops/vulnerability-disclosure.md`: it is `status: draft`
in a **public** repo, so §1.1–§1.3 sit publicly for the ~17 days until the
window, and read together they concentrate more measured present-state detail
about named internet-facing services than that test allows. No single sentence
crosses the line; the concentration is what does.

Two corrections were applied immediately: `security_ref` now cites
`F-aae0f363` (the previous `null` rested on reasoning that does not hold — see
the frontmatter comment), and the archive/retention line was removed from §1.2.

**Still owed, and it needs DB write scope this plan's author did not have:**
migrate the measured present-state in §1.1–§1.3 — the per-source event counts,
the transport/rule inventory, and the indexing-gap figures — onto
`F-aae0f363`'s `security_detail`, and replace them here with the citation. Keep
§2–§5 as they are: scope, pre-checks, diagnosis and steps are "how to fix" prose,
which the SOP puts squarely on the publishable side.

Do not simply delete the measurements. `README.md` is explicit that losing the
"why" is worse than the disclosure — the finding record is where the "why" must
land first, and only then does the deletion here become safe.

Also for the record, since a commit message cannot be quietly edited: the commit
that added this file (`88c170f5`) carries a document-volume figure that does not
appear in the file itself, and residual present-tense claims about named
components. That is a permanent artifact. The narrower lesson is that the
disclosure hook's residual tier is a closed list of phrasings and paraphrase
defeats it by design (SOP §2.4), which is an argument for extending
`.githooks/lib/disclosure_patterns.py`, not for trusting the hook's silence.

## 2. Scope of THIS plan

**In scope (15 min, verification only, no commit):** prove on authentik 2026.8.3
that the recorded `client_ip` is the real client for both an off-LAN and a LAN
login, then retire Phase 1.

**Out of scope:** any manifest change. If a gate below fails, STOP and re-plan;
do not improvise the old Case A/Case B remedies in-window. Phases 2 and 3 are
scoped in section 7 and need their own plans.

## 3. Pre-checks

```bash
cd /Users/mu/code/cberg-home-nextgen
.venv/bin/python3 runbooks/plan-premises.py wazuh-2xx-edge-coverage --require-premises
# EXPECT: 3/3 PASS. Any FAIL -> STOP (Phase 1 may be open again).

# 3.0 ORDER GATE: authentik-2026.8.3 has landed AND soaked >= 20 min.
mise exec -- kubectl -n kube-system get pods \
  -l app.kubernetes.io/name=authentik,app.kubernetes.io/component=server \
  -o jsonpath='{range .items[*]}{.metadata.name} {.status.startTime} {.spec.containers[0].image}{"\n"}{end}'
# EXPECT: every line ends ghcr.io/goauthentik/server:2026.8.3 AND the newest
# startTime is >= 20 min ago. Any 2026.8.2 line, or a younger pod -> STOP/wait.

# 3.1 Historical gate, WITH its known-bad control (same query, two windows).
for w in "'2026-09-01' and '2026-09-11 09:00'" "'2026-09-11 09:00' and now()"; do
  mise exec -- kubectl -n kube-system exec deploy/authentik-pg -- \
    psql -U authentik -d authentik -At -F ' ' -c \
    "select count(*) filter (where host(client_ip) ~ '^(::ffff:)?10\.69\.') as pod_rows,
            count(*) as total
       from authentik_events_event
      where action in ('login','login_failed') and created between $w;"
done
# EXPECT line 1 (control, pre-fix window): pod_rows >= 1 (measured 4 of 10 on
#   2026-09-26). If it prints 0, the query cannot detect the defect -> STOP.
# EXPECT line 2 (post-fix window): pod_rows = 0 (measured 0 of 15).
```

## 4. Steps

1. Operator, on a phone with Wi-Fi OFF (mobile data): look up the phone's
   current public IP on any IP-echo page and note it (not via authentik; that
   would be circular). Open a private/incognito browser tab so a fresh `login`
   event is created (an existing session emits none), and log in to authentik.
2. Operator, on a LAN machine on the home network: note its LAN address
   (192.168.x, or its own 2a00:6020:ad52:43xx address if it connects over
   IPv6), open a private tab, log in to authentik.
3. Run the section 5 query. No commit, no reconcile.

## 5. Verification

```bash
mise exec -- kubectl -n kube-system exec deploy/authentik-pg -- \
  psql -U authentik -d authentik -At -F ' ' -c \
  "select created, host(client_ip), coalesce(context->'asn'->>'asn','-')
     from authentik_events_event
    where action = 'login' and created > now() - interval '20 minutes'
    order by created desc;"
```

```
G1 CONTENTS (external): a row whose host(client_ip) EQUALS the IP noted in
   step 4.1, and whose asn is NOT 13335 (Cloudflare). Can fail: a pod address
   (the 2026-09-07/08 rows) or a Cloudflare edge address prints a different
   value; a missing row (session reused) prints nothing -> FAIL, not PASS.
G2 NEGATIVE CONTROL (LAN): a second row whose host(client_ip) EQUALS the LAN
   address from step 4.2 and differs from G1's. Two different, independently
   known addresses rule out one hard-coded value matching by accident.
G3 NO POD ADDRESS: neither row starts 10.69. -- already covered by G1/G2
   equality; its standalone form is the 3.1 query, whose control window
   demonstrates it returns non-zero on the defect.
PASS = G1 and G2. Any other outcome -> STOP, record the observed values on a
new finding (DB, not this file), leave Phase 1 open.
```

## 6. Rollback

None needed: this plan changes nothing (two logins and SELECTs). On PASS, set
`status: executed`; the orchestrator records Phase 1 as retired. On FAIL, leave
the plan open and re-plan from the observed values.

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

- **Order (operator instruction, 2026-09-26):** `authentik-pg17-decommission`
  residual -> `authentik-2026.8.3` -> 20-min soak -> THIS plan. Encoded as
  `depends_on: [authentik-2026.8.3]`, reciprocal `conflicts_with`, and the
  section 3.0 order gate. Never co-run with either authentik plan: a roll while
  the operator logs in lands the login on a terminating pod and the baseline is
  taken on the wrong version.
- **No gateway change any more.** The earlier `gateway/envoy` touch and the
  external-dns pairing note were for the Case A remedy, which already shipped
  in `2df8ec7f`; this plan does not perturb the external request path.
- **Does not read Prometheus**, so a same-night `kube-prometheus-stack` bump is
  not interference for this plan.
- **Attended only** (`autonomy_override: human-gated`): the verification needs a
  human logging in from an independently known off-LAN address.

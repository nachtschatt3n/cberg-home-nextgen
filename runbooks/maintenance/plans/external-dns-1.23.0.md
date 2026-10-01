---
plan_id: external-dns-1.23.0
component: external-dns
pr: null                              # no Renovate PR; surfaced by coverage.py (deny rule *external-dns*)
kind: chart
current: "1.22.0"
target: "1.23.0"                      # chart 1.22.0 -> 1.23.0 = image v0.22.0 -> v0.23.0 (appVersion 0.23.0)
update_type: minor
risk: medium                          # NOT from the diff: the rendered chart diff is the image tag + labels only
                                      # (section 1.2), and the one v0.23.0 code change on our path (gateway
                                      # source indexer rewrite, #6545) preserves our allowlist semantics on
                                      # reading (section 1.3). Medium because blast radius = EVERY public
                                      # hostname and policy: sync turns any wrong desired-state into deletes.
est_duration_min: 45                  # 2 pre-checks/baseline 10 + 3.2 flag commit+gate 10 + 3.3 bump+gate 15 + 4 soak 10
needs_reboot: false
exclusive: false
touches:
  namespaces: [network]
  resources:
    - helmrelease/network/external-dns                  # values arg rename (3.2), chart 1.22.0 -> 1.23.0 (3.3)
    - deployment/network/external-dns                   # 1 replica, strategy Recreate: pod replaced TWICE (3.2, 3.3)
    - helmchart/flux-system/network-external-dns        # source-controller pulls chart 1.23.0
    - kubernetes/apps/network/external/external-dns/helmrelease.yaml
  shared:
    - public-dns                      # the ONLY writer of public DNS (Cloudflare, policy: sync)
    - public-edge                     # every envoy-external hostname's CNAME (27 measured 2026-10-01)
    - monitoring                      # section 4 reads Prometheus (external_dns_* series) as its instrument
depends_on: []
conflicts_with:
  - envoy-gateway-1.9.2               # rolls envoy-external; its gateway status/route re-translation feeds the
                                      # gateway-httproute source and would confound the section 4 no-change gate
  - app-template-5.2.1                # relabels ~45 HTTPRoutes incl. every envoy-external route -> source re-list
                                      # in the same window; attribution of any record change becomes ambiguous
  - chart-patches-coredns-reloader-blackbox   # rolls CoreDNS (external-dns resolves the Cloudflare API through
                                      # it) AND reloader (external-dns pod carries a reloader annotation)
  - helm-drift-detection              # adds spec.driftDetection to every HelmRelease incl. this one
  - flux-fleet-0.60.0                 # upgrades helm-controller, which applies this HelmRelease
  - flux-reconciler-impersonation     # exclusive; changes the identity that applies this HelmRelease
  - flux-oci-chart-sources            # moves chart sources; external-dns is in its stage-4 set
security_ref: null                    # queried 2026-10-01: no open sweep finding for external-dns (only
                                      # resolved rows; F-14528040 was the v0.21.0 image and closed 2026-09-17)
capability_change: false              # same-behaviour version bump + a deprecated-flag rename to its documented
                                      # successor with the identical value; no new source, route, permission,
                                      # record type or exposure. --enable-legacy-annotation-prefix NOT added.
rollback_class: git-revert            # no forward-only state: TXT registry format unchanged (#6680 changes only
                                      # how a DELETE matches the stored value), no CRD/schema, no data on disk
finding_refs: []                      # policy-cli finding list --grep external-dns (and --all): zero open rows
review: null
status: draft
window: null                          # ATTENDED slot only (sat-attended / sun-attended) — docs/sops/external-dns.md
                                      # section 1 Prerequisites: a change that can alter the record set is attended
sops_refs:
  - docs/sops/external-dns.md
  - docs/sops/application-update.md
  - docs/sops/gateway-api-httproute.md
  - docs/sops/verification-contents-not-shape.md
premises:
  - id: live-chart-is-1.22.0
    why: "current: claims 1.22.0. If anything already moved it, 3.3's sed matches nothing and the rollback target is wrong."
    run: kubectl get helmrelease external-dns -n network -o jsonpath='{.spec.chart.spec.version}'
    expect_exact: "1.22.0"
  - id: hr-ready
    why: "Do not stack a bump on a failing release; helm remediation retries would mask every section 4 result."
    run: kubectl get helmrelease external-dns -n network -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: "True"
  - id: live-image-is-v0.22.0
    why: "The source analysis in section 1.3 is a v0.22.0 -> v0.23.0 diff; a different running image voids it."
    run: kubectl get deploy external-dns -n network -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: "registry.k8s.io/external-dns/external-dns:v0.22.0"
  - id: strategy-recreate
    why: "Two external-dns replicas under policy sync would fight over the record set; Recreate guarantees one at a time."
    run: kubectl get deploy external-dns -n network -o jsonpath='{.spec.strategy.type}'
    expect_exact: "Recreate"
  - id: gateway-carries-ga-target-key
    why: "v0.22+ reads ONLY external-dns.kubernetes.io/target (no fallback). Without it the source publishes the LAN status address and sync deletes every CNAME (the 2026-09-08 outage)."
    run: >-
      kubectl get gateway envoy-external -n network -o jsonpath='{.metadata.annotations.external-dns\.kubernetes\.io/target}' | awk '/^external\./ {print "ga-key-present"}'
    expect_exact: "ga-key-present"
  - id: no-flags-on-a-changed-code-path
    why: "v0.23.0 changes the crd registry (#6606), TXT encryption (#6675/#6680), filter validation (#6610), legacy prefix (#6703). All are inert ONLY while none of these flags is set."
    run: >-
      kubectl get deploy external-dns -n network -o jsonpath='{.spec.template.spec.containers[0].args}' | tr ',' '\n' | awk '/annotation-prefix/ {n++} /default-targets/ {n++} /label-filter/ {n++} /annotation-filter/ {n++} /txt-encrypt/ {n++} /registry=crd/ {n++} /dry-run/ {n++} /provider-cache-time/ {n++} END {print n+0}'
    expect_exact: "0"
  - id: load-bearing-flags-present
    why: "txt registry, sync policy, the one-Gateway allowlist and both sources are what section 1.3 was verified against; all six must be present."
    run: >-
      kubectl get deploy external-dns -n network -o jsonpath='{.spec.template.spec.containers[0].args}' | tr ',' '\n' | awk '/--registry=txt/ {n++} /--policy=sync/ {n++} /--gateway-name=envoy-external/ {n++} /--gateway-namespace=network/ {n++} /--source=gateway-httproute/ {n++} /--source=crd/ {n++} END {print n+0}'
    expect_exact: "6"
  - id: no-controller-annotation-on-gateways-or-routes
    why: "v0.23.0 (#6545) now applies IsControllerMatch to GATEWAYS at index time, not only routes. A controller annotation on envoy-external would drop it from the index and every route would yield no endpoints -> sync deletes all CNAMEs."
    run: >-
      kubectl get gateway,httproute -A -o jsonpath='{range .items[*]}{.metadata.annotations}{"\n"}{end}' | awk 'tolower($0) ~ /external-dns[^"]*\/controller/ {n++} END {print n+0}'
    expect_exact: "0"
  - id: deprecated-flag-anchor-unique
    why: "3.2's sed is anchored on this exact line; 0 or 2 matches means the edit silently no-ops or double-applies."
    run: >-
      grep -c -- '^      - --request-timeout=60s$' kubernetes/apps/network/external/external-dns/helmrelease.yaml
    expect_exact: "1"
  - id: version-anchor-unique
    why: "3.3's sed is anchored on this exact line."
    run: >-
      grep -c '^      version: 1\.22\.0$' kubernetes/apps/network/external/external-dns/helmrelease.yaml
    expect_exact: "1"
generated: "2026-10-01"
---

# external-dns chart 1.22.0 -> 1.23.0 (image v0.22.0 -> v0.23.0)

## 1. Summary & why held

### 1.1 What changes

- Chart `external-dns` **1.22.0 -> 1.23.0** in
  `kubernetes/apps/network/external/external-dns/helmrelease.yaml`. Chart
  1.23.0 (published 2026-09-30) ships `appVersion: 0.23.0`, i.e. image
  `registry.k8s.io/external-dns/external-dns:v0.23.0` (tag verified to resolve
  on registry.k8s.io, HTTP 200 on the OCI index, 2026-10-01).
- **Preceding, separate commit:** `--request-timeout=60s` ->
  `--kube-api-request-timeout=60s`. `docs/sops/external-dns.md` §3 ("Pending")
  requires this rename land *in its own commit before the next bump*, never
  bundled with it. It is behaviour-identical (section 1.4).

### 1.2 Why it was held — and what the chart diff actually is

Held by the `*external-dns*` deny rule in `runbooks/auto-update-policy.yaml`
(every update type, both lanes): external-dns runs `policy: sync`, so a wrong
desired state is applied as **deletes** of public CNAMEs, and a rejected
create leaves the hostname with no record at all. The 2026-09-08 94 s outage
(`aa79cf7a`) is the precedent. The rule is correct and stays; this plan is the
attended path it asks for.

**Chart diff, measured** (both tarballs pulled from the upstream release
assets, `helm template` with our exploded HelmRelease values, diffed): the ONLY
rendered differences are `helm.sh/chart`/`app.kubernetes.io/version` labels
and `image: ...:v0.22.0 -> ...:v0.23.0`. No values, RBAC, Service,
ServiceMonitor or selector change. Upstream chart CHANGELOG for 1.23.0 has one
entry: *"Update ExternalDNS OCI image version to v0.23.0 (#6772)"*. So all
risk is in the binary.

### 1.3 Upstream v0.23.0 release notes, read against our config

Release notes (GitHub release v0.23.0, 2026-09-18), quoted:

> *"It's recommended to try this version with `--dry-run=true` first"*
>
> **Action required before upgrade**
> - *"`crd` Registry now stores `DNSRecord` objects independantly of source
>   namespace (#6606). Upgrading from v0.22.0: set `--crd-registry-namespace`
>   accordingly."*
> - *"With `--txt-encrypt-enabled`, Go 1.27 changed gzip output (#6675)"*
>
> **Breaking Changes:** `add --crd-registry-namespace` (#6606), `remove
> unmaintained provider gandi` (#6654), `[webhook] bound request and response
> body sizes` (#6484)

| v0.23.0 change | Our config | Verdict |
|---|---|---|
| #6606 crd **registry** namespace | `registry: txt` (pinned 2026-09-23, `57280084`); the `crd` we use is a **source** (DNSEndpoint), not the registry. PR body: *"The CRD registry is unreleased (#5372), so there is no migration."* | inert; premise `no-flags-on-a-changed-code-path` |
| #6675/#6680 TXT encryption + "delete TXT records with their stored value" | no `--txt-encrypt-*`. #6680 makes a TXT **delete** reuse the value read from the zone instead of re-serialising labels — strictly more tolerant; it only runs when a record is removed | inert in steady state |
| #6654 gandi removed, #6484 webhook body cap | provider `cloudflare`, in-tree, no webhook | inert |
| #6703 `--enable-legacy-annotation-prefix` | not needed: Gateway `envoy-external` already carries the GA key (premise). **Do not add it** | n/a |
| #6731 Cloudflare `providerSpecific` names normalised | our only DNSEndpoint (`network/cloudflared`, 1 CNAME) has **no** `providerSpecific`; proxying is the global `--cloudflare-proxied` | inert |
| #6660 cloudflare-go pinned v7.7.0 (batch param structs reshaped) | this is our **write path** (`provider/cloudflare/cloudflare_batch.go`, +209/-?) | exercised **only when a change is submitted**; steady state submits nothing (section 4 gate 2 proves it) |
| **#6545 gateway sources -> indexer-based filtering** | **this is our source** (`gateway-httproute` + `--gateway-name/--gateway-namespace`) | see below — the central risk |

**#6545 read at source (v0.22.0 vs v0.23.0 `source/gateway.go`, cloned
`a10c5665`):** the runtime `Gateways(src.gwNamespace).List(...)` filter and the
`gwNamespace` field are **removed**. Our namespace allowlist survives because
the Gateway informer factory itself is still built with
`newGatewayInformerFactory(client, config.GatewayNamespace, gwLabels)` ->
`gwinformers.WithNamespace(namespace)` (v0.23.0 line 174/79), so only Gateways
in `network` are ever cached. The name allowlist (`c.src.gwName !=
obj.gatewayRef.Name`, v0.23.0 line 439) is unchanged. Upstream unit tests
`GatewayName`, `GatewayNameNoneAccepted`, `GatewayNamespace` cover both. The
indexer's nil label/annotation selectors match everything
(`source/informers/indexers.go` `IndexerWithOptions`). **One new behaviour:**
`IsControllerMatch` is now applied to **Gateways** at index time (previously
only routes were checked). A Gateway carrying an
`external-dns.kubernetes.io/controller` annotation with a foreign value would
silently drop out of the index -> every route yields zero endpoints -> `sync`
deletes all CNAMEs. Measured live: 0 such annotations on any Gateway or
HTTPRoute -> premise `no-controller-annotation-on-gateways-or-routes`.

**Why no `--dry-run` rehearsal (upstream's recommendation):** no external-dns
binary or container runtime on the Mac mini (`docker`/`podman` absent; release
has no binary assets), and an in-cluster dry-run Deployment would be a second
GitOps change with its own Cloudflare-token surface. The substitute is the
source reading above plus the section 4 gate 2, which asserts that the v0.23.0
pod's sync loop **submits zero changes** — the property a dry-run would have
shown — with the `git revert` staged before the push.

### 1.4 The flag rename (3.2) is behaviour-identical

Upstream `pkg/apis/externaldns/types.go` `resolveDeprecatedFlags()` (identical
at v0.22.0 and v0.23.0): when `--request-timeout` differs from its default it
logs the deprecation warning and copies its value into
`KubeAPIRequestTimeout`. Live pod today: `RequestTimeout:1m0s
KubeAPIRequestTimeout:1m0s`. After the rename `KubeAPIRequestTimeout` is set
directly to 60s; the deprecated field drops to its 30s default, whose only
remaining consumer is the **crd registry** (`registry/crd/crd.go:68`), which we
do not use. The k8s client generator reads `KubeAPIRequestTimeout`
(`source/store.go:218`). The flag exists at v0.22.0 (verified), so commit 3.2
runs on the current binary.

### 1.5 Security driver

None open. `policy-cli.py finding list --grep external-dns` (with `--all`)
returns only resolved rows; `security_ref: null`, `finding_refs: []`.

## 2. Pre-checks

Run from the repo root in **one zsh session** (`mise` resolves tools only
inside the repo).

```bash
cd /Users/mu/code/cberg-home-nextgen
.venv/bin/python3 runbooks/plan-premises.py external-dns-1.23.0   # all premises PASS, else STOP

# 2.1 nothing else in flight on network / flux
mise exec -- flux get kustomizations -A | awk 'NR==1 || $5 != "True"'
mise exec -- flux get helmreleases -A   | awk 'NR==1 || $5 != "True"'
# PASS: header line only (or only items unrelated to network/external-dns and already known)

# 2.2 the six ExternalDNS alert rules are LOADED (else section 4 is blind)
mise exec -- kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 19090:9090 >/dev/null 2>&1 & PF=$!; sleep 3
curl -s http://localhost:19090/api/v1/rules | python3 -c "
import sys, json
names = {r['name'] for g in json.load(sys.stdin)['data']['groups'] for r in g['rules']}
want = ['ExternalDNSRegistryErrors','ExternalDNSSourceErrors','ExternalDNSSyncStalled',
        'ExternalDNSRecordsCollapsed','ExternalDNSErrorMetricsAbsent','ExternalDNSSyncMetricsAbsent']
miss = [a for a in want if a not in names]
print('RULES_OK' if not miss else 'RULES_MISSING ' + ' '.join(miss))"
# PASS: RULES_OK. RULES_MISSING -> STOP (the alerts that would page on an outage are not loaded)

# 2.3 BASELINE — record these three numbers; section 4 compares against them, not a constant
q(){ curl -s --get http://localhost:19090/api/v1/query --data-urlencode "query=$1" \
  | python3 -c "import sys,json; r=json.load(sys.stdin)['data']['result']; print(r[0]['value'][1] if r else 'EMPTY')"; }
echo "B_VERIFIED=$(q 'external_dns_controller_verified_records{record_type="cname"}')"
echo "B_SOURCE=$(q 'external_dns_source_endpoints_total')"
echo "B_REGERR7D=$(q 'sum(increase(external_dns_registry_errors_total[7d]))')"
# Measured 2026-10-01: B_VERIFIED=27 B_SOURCE=27 B_REGERR7D=0.
# PASS: B_VERIFIED == B_SOURCE, B_REGERR7D == 0, none EMPTY.
# EMPTY -> STOP: the instrument is not scraping, every later gate would read empty on both sides.
# NOTE: docs/sops/external-dns.md section 2 still says "25" — stale; use the measured value.

# 2.4 independent cross-check of the source count from the cluster, and the public-resolution baseline
mise exec -- kubectl get httproute -A -o json | python3 -c "
import sys,json
items=json.load(sys.stdin)['items']
hosts=sorted({h for i in items if any(p.get('name')=='envoy-external' for p in i['spec'].get('parentRefs',[])) for h in i['spec'].get('hostnames',[])})
print('\n'.join(hosts))" > /tmp/edns-hosts.txt
D=$(mise exec -- kubectl -n network get gateway envoy-external -o jsonpath='{.metadata.annotations.external-dns\.kubernetes\.io/target}' | sed 's/^external\.//')
echo "external.$D" >> /tmp/edns-hosts.txt                      # the tunnel CNAME from DNSEndpoint cloudflared
echo "HOSTS=$(wc -l < /tmp/edns-hosts.txt | tr -d ' ')"
# PASS: HOSTS == B_SOURCE (26 route hostnames + 1 DNSEndpoint = 27 measured 2026-10-01)
pubcheck(){ ok=0; bad=0; while read h; do a=$(dig +short +time=3 +tries=2 @1.1.1.1 "$h" A | grep -E '^[0-9]+\.' | head -1)
  case "$a" in ""|192.168.*|10.*) bad=$((bad+1)); echo "BAD ${h%%.*}";; *) ok=$((ok+1));; esac; done < /tmp/edns-hosts.txt
  echo "public_ok=$ok public_bad=$bad"; }
pubcheck
# PASS: public_bad=0 (measured 27/0). Negative control, run once to prove the check CAN fail
# (no wildcard record in the zone):
dig +short @1.1.1.1 "nonexistent-control-$RANDOM.$D" A | grep -cE '^[0-9]+\.'      # expect 0

# 2.5 log baseline — the current pod must be quiescent (no changes being submitted)
mise exec -- kubectl -n network logs deploy/external-dns --since=15m > /tmp/edns-before.log
echo "noop=$(grep -ci 'all records are already up to date' /tmp/edns-before.log) changes=$(grep -ci 'changing record' /tmp/edns-before.log)"
# PASS: noop >= 10, changes == 0. changes > 0 -> STOP: something else is moving the record set right now
kill $PF 2>/dev/null
```

**Do NOT** add an Alertmanager silence and **do NOT** drop an
`update-marker.sh` marker for this app (deliberate deviation from
`application-update.md` §4 Steps 1/1b): the `ExternalDNS*` alerts are the only
thing that pages on a public-DNS outage, and an active-update marker makes the
`alert-triage-agent` auto-silence exactly `ExternalDNSRecordsCollapsed`.
Recreate leaves a ~15 s sync gap; no rule has a `for:` that short, so there is
no noise to suppress. Likewise keep `upgrade.remediation.strategy: rollback`
(no `retries: 0`): there is no migration that needs the new spec to stick, and
helm's automatic rollback to 1.22.0 is the desired failure mode.

## 3. Steps

Two commits, in order, with a gate between them (SOP §5 Example B shape).

### 3.1 Prepare message files (before any gate — shared worktree)

```bash
cd /Users/mu/code/cberg-home-nextgen
cat > /tmp/edns-msgA.txt <<'EOF'
fix(external-dns): --request-timeout -> --kube-api-request-timeout (same 60s)

Deprecated upstream (types.go resolveDeprecatedFlags); value was already being
forwarded, so behaviour is identical. Own commit ahead of the 1.23.0 bump per
docs/sops/external-dns.md section 3. Plan: external-dns-1.23.0.

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
EOF
cat > /tmp/edns-msgB.txt <<'EOF'
chore(external-dns): chart 1.22.0 -> 1.23.0 (image v0.22.0 -> v0.23.0)

Chart diff is the image tag only. No new flags (no --enable-legacy-annotation-
prefix, no --annotation-prefix, no --default-targets). Gateway envoy-external
already carries the GA target key. Plan: external-dns-1.23.0.

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
EOF
```

### 3.2 Commit A — flag rename (chart stays 1.22.0)

```bash
cd /Users/mu/code/cberg-home-nextgen
F=kubernetes/apps/network/external/external-dns/helmrelease.yaml
sed -i '' 's/^      - --request-timeout=60s$/      - --kube-api-request-timeout=60s/' "$F"
git diff -- "$F"
# EXPECTED (dry-tested on a scratch copy, BSD sed, 2026-10-01) — exactly this one hunk:
#   -      - --request-timeout=60s
#   +      - --kube-api-request-timeout=60s
mise exec -- kubeconform -summary -ignore-missing-schemas kubernetes/apps/network/external/external-dns
git commit --only "$F" -F /tmp/edns-msgA.txt
git log -1 --format=%s     # MUST read: fix(external-dns): --request-timeout -> --kube-api-request-timeout (same 60s)
git show --stat HEAD       # MUST list only helmrelease.yaml, 1 insertion 1 deletion
git push
SHA_A=$(git rev-parse HEAD); echo "SHA_A=$SHA_A"; PUSH_A=$(date -u +%Y-%m-%dT%H:%M:%SZ)
```

**Gate A** (wait for the new pod, then ~3 sync intervals):

```bash
mise exec -- kubectl -n network rollout status deploy/external-dns --timeout=180s
mise exec -- kubectl -n network get pod -l app.kubernetes.io/name=external-dns \
  -o jsonpath='{range .items[*]}{.metadata.name} {.status.startTime}{"\n"}{end}'
# PASS: exactly one pod, startTime later than $PUSH_A (a pod older than the push = Flux has not applied yet; wait)
sleep 200
mise exec -- kubectl -n network logs deploy/external-dns > /tmp/edns-A.log
grep -ci 'request-timeout is deprecated' /tmp/edns-A.log            # PASS: 0   (was 1 on the old pod)
grep -o 'KubeAPIRequestTimeout:[^ ]*' /tmp/edns-A.log | head -1      # PASS: KubeAPIRequestTimeout:1m0s
echo "noop=$(grep -ci 'all records are already up to date' /tmp/edns-A.log) changes=$(grep -ci 'changing record' /tmp/edns-A.log)"
# PASS: noop >= 3, changes == 0
```

FAIL on any line -> section 5.1 (revert A), stop. Do not continue to 3.3.

### 3.3 Commit B — chart 1.22.0 -> 1.23.0

```bash
cd /Users/mu/code/cberg-home-nextgen
F=kubernetes/apps/network/external/external-dns/helmrelease.yaml
sed -i '' 's/^      version: 1\.22\.0$/      version: 1.23.0/' "$F"
git diff -- "$F"
# EXPECTED (dry-tested, BSD sed) — exactly:
#   -      version: 1.22.0
#   +      version: 1.23.0
mise exec -- kubeconform -summary -ignore-missing-schemas kubernetes/apps/network/external/external-dns
git commit --only "$F" -F /tmp/edns-msgB.txt
git log -1 --format=%s     # MUST read: chore(external-dns): chart 1.22.0 -> 1.23.0 (image v0.22.0 -> v0.23.0)
git show --stat HEAD       # MUST list only helmrelease.yaml
# Stage the revert BEFORE pushing so it is one command away:
SHA_B_PARENT=$(git rev-parse HEAD~1)
git push
SHA_B=$(git rev-parse HEAD); echo "SHA_B=$SHA_B"; PUSH_B=$(date -u +%Y-%m-%dT%H:%M:%SZ)

# STAY and watch the first syncs live (Ctrl-C after ~3 "All records are already up to date" lines):
mise exec -- kubectl -n network logs -l app.kubernetes.io/name=external-dns -f --tail=20
```

If `kubectl -n flux-system get helmchart network-external-dns` reports it
cannot find version 1.23.0 (stale repo index; `HelmRepository` interval is 1h),
refresh the SOURCE only — this is a read of the upstream index, not an apply:
`mise exec -- flux reconcile source helm external-dns -n flux-system`.

**Abort trigger during the watch:** any `Changing record.` line with
`action=DELETE`, any `level=error`, or `9003`/`not allowed` -> do not wait for
section 4, go straight to section 5.2.

## 4. Verification

Run after the v0.23.0 pod has been up >= 4 minutes (>= 3 sync intervals at
`--interval=1m`).

```bash
cd /Users/mu/code/cberg-home-nextgen
mise exec -- kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 19090:9090 >/dev/null 2>&1 & PF=$!; sleep 3
q(){ curl -s --get http://localhost:19090/api/v1/query --data-urlencode "query=$1" \
  | python3 -c "import sys,json; r=json.load(sys.stdin)['data']['result']; print(r[0]['value'][1] if r else 'EMPTY')"; }
```

**Gate 1 — the running binary is v0.23.0, and Prometheus is reading the NEW pod.**

```bash
mise exec -- kubectl -n network get deploy external-dns -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'
# PASS: registry.k8s.io/external-dns/external-dns:v0.23.0
mise exec -- kubectl -n network get pod -l app.kubernetes.io/name=external-dns \
  -o jsonpath='{range .items[*]}{.metadata.name} {.status.startTime} {.status.containerStatuses[0].imageID}{"\n"}{end}'
# PASS: one pod, startTime after $PUSH_B (feedback: rollout status can green-light the OLD generation)
curl -s --get http://localhost:19090/api/v1/query --data-urlencode 'query=external_dns_build_info' \
  | python3 -c "import sys,json; print([r['metric']['version'] for r in json.load(sys.stdin)['data']['result']])"
# PASS: a single version ending in -v0.23.0 (today reads ['v20260820-v0.22.0']). Two entries = stale series; wait one scrape.
```
CONTROL: metric external_dns_build_info — `version` label must end `v0.23.0`; it reads `...-v0.22.0` today, so this gate fails if the old pod is still the one scraped.

**Gate 2 — CONTENTS: the v0.23.0 sync loop submits ZERO changes** (the
property `--dry-run` would have shown; a regression in the #6545 source
rewrite or the cloudflare-go batch path shows up here first).

```bash
mise exec -- kubectl -n network logs deploy/external-dns > /tmp/edns-B.log
echo "noop=$(grep -ci 'all records are already up to date' /tmp/edns-B.log) changes=$(grep -ci 'changing record' /tmp/edns-B.log) errors=$(grep -ciE 'level=error|9003|not allowed' /tmp/edns-B.log)"
# PASS: noop >= 3, changes == 0, errors == 0
echo "NOOP_INC=$(q 'increase(external_dns_controller_no_op_runs_total[5m])')"
# PASS: NOOP_INC >= 2 (counter only increments when a sync computes no changes; controller/controller.go)
```
CONTENTS ASSERTION: the set of records external-dns wants equals the set it already has — measured by zero `Changing record.` lines from the v0.23.0 pod and a rising no-op counter, compared to the 2.5 baseline (changes == 0, noop >= 10 per 15 min).
CONTROL: metric external_dns_controller_no_op_runs_total — must increase by >= 2 over 5 min on the new pod.
*Can it fail?* Yes: `Changing record.` is logged once per submitted change at
`provider/cloudflare/cloudflare.go:563` (v0.23.0) **before** the API call; the
2026-09-08 outage shape was exactly a burst of these. The log string and the
"All records are already up to date" string (`controller/controller.go:131`)
were both confirmed at the v0.23.0 tag; greps are case-insensitive.

**Gate 3 — CONTENTS: the record set is intact, against the 2.3 baseline (not a constant).**

```bash
echo "VERIFIED=$(q 'external_dns_controller_verified_records{record_type="cname"}') SOURCE=$(q 'external_dns_source_endpoints_total') REGERR=$(q 'increase(external_dns_registry_errors_total[10m])') SRCERR=$(q 'increase(external_dns_source_errors_total[10m])') STALE=$(q 'time()-external_dns_controller_last_sync_timestamp_seconds')"
# PASS: VERIFIED == B_VERIFIED, SOURCE == B_SOURCE, REGERR == 0, SRCERR == 0, STALE < 150
# EMPTY in any field = FAIL (instrument blind), not PASS.
```
CONTENTS ASSERTION: every public CNAME external-dns owned before the bump is still verified after it — measured by `external_dns_controller_verified_records{record_type="cname"}`, compared to B_VERIFIED from 2.3 (27 on 2026-10-01). A drop of even 1 is a FAIL.
CONTROL: metric external_dns_controller_verified_records — equals B_VERIFIED.
CONTROL: metric external_dns_source_endpoints_total — equals B_SOURCE; a fall means the gateway source stopped emitting (the #6545 failure mode) BEFORE sync has deleted anything.
CONTROL: metric external_dns_registry_errors_total — increase over 10 min == 0.
CONTROL: metric external_dns_source_errors_total — increase over 10 min == 0.
CONTROL: metric external_dns_controller_last_sync_timestamp_seconds — staleness < 150 s.

**Gate 4 — end-to-end public resolution, every hostname.**

```bash
pubcheck      # function + /tmp/edns-hosts.txt from section 2.4 (same shell)
# PASS: public_bad=0 and public_ok == HOSTS
```
Resolver caching (proxied records, 300 s TTL) means this gate can lag a real
deletion by up to 5 minutes — it is the end-to-end confirmation, not the
primary detector (gates 2-3 are). The 2.4 negative control proves it can fail.

**Gate 5 — the outage alerts are quiet and still able to fire.**

```bash
curl -s --get http://localhost:19090/api/v1/query --data-urlencode 'query=ALERTS{alertname=~"ExternalDNS.*",alertstate="firing"}' \
  | python3 -c "import sys,json; print('firing=', [r['metric']['alertname'] for r in json.load(sys.stdin)['data']['result']])"
# PASS: firing= []
echo "ABSENT_ERR=$(q 'absent(external_dns_registry_errors_total)') ABSENT_SYNC=$(q 'absent(external_dns_controller_last_sync_timestamp_seconds)')"
# PASS: both EMPTY (the series exist -> the detectors are not blind). "1" = FAIL.
kill $PF 2>/dev/null
```
CONTROL: alertname ExternalDNSRecordsCollapsed — not firing.
CONTROL: alertname ExternalDNSRegistryErrors — not firing.
CONTROL: alertname ExternalDNSSyncStalled — not firing.
CONTROL: alertname ExternalDNSErrorMetricsAbsent — not firing.
CONTROL: alertname ExternalDNSSyncMetricsAbsent — not firing.

**Gate 6 — Flux settled.**

```bash
mise exec -- flux get helmreleases -n network external-dns
# PASS: Ready True, message names chart external-dns@1.23.0
```

All six PASS -> plan `executed`. Leave the session open ~10 more minutes and
re-run Gate 3 once (soak); then retire this file in the same commit that
updates `docs/sops/external-dns.md` §2 (chart/image row, steady-state count).

## 5. Rollback

`rollback_class: git-revert` — external-dns holds no state; the TXT registry
is re-read every sync and v0.23.0 writes nothing in steady state, so v0.22.0
reads the zone exactly as it left it. Recovery after a correct revert is ~60 s
(2026-09-08 incident: 94 s end to end).

### 5.1 Commit A failed its gate

```bash
cd /Users/mu/code/cberg-home-nextgen
git revert --no-edit "$SHA_A"
git log -1 --format=%s            # MUST be: Revert "fix(external-dns): --request-timeout -> ..."
git show --stat HEAD              # only helmrelease.yaml
git push
```
Confirm: pod restarts, log shows the deprecation warning again and
`KubeAPIRequestTimeout:1m0s`; Gate 3 numbers equal the 2.3 baseline.

### 5.2 Commit B failed (any gate, or an abort trigger during the watch)

```bash
cd /Users/mu/code/cberg-home-nextgen
git revert --no-edit "$SHA_B"     # back to chart 1.22.0; commit A stays (it is independent and was gated)
git log -1 --format=%s            # MUST be: Revert "chore(external-dns): chart 1.22.0 -> 1.23.0 ..."
git show --stat HEAD
git push
mise exec -- kubectl -n network logs -l app.kubernetes.io/name=external-dns -f --tail=20
```
Confirm back:
- deploy image `...:v0.22.0`, one pod started after the revert push;
- `external_dns_build_info` version ends `v0.22.0`;
- `Changing record.` lines from the v0.22.0 pod are **creates** restoring
  records (expected if v0.23.0 deleted any), then "All records are already up
  to date";
- Gate 3 back to B_VERIFIED / B_SOURCE, Gate 4 `public_bad=0` (allow 5 min for
  resolver caches).

If helm is wedged `pending-upgrade` and the revert does not apply (helm
remediation normally rolls back on its own — `strategy: rollback, retries: 3`):
`mise exec -- flux reconcile helmrelease external-dns -n network --force`.

If the revert restores v0.22.0 but records do **not** come back, the cause is
upstream of external-dns: check the Gateway still carries
`external-dns.kubernetes.io/target` and the tunnel (`docs/sops/cloudflare.md`),
per `docs/sops/external-dns.md` §11. **Never** hand-create records in the
Cloudflare UI to bridge the gap — under `policy: sync` they are deleted at the
next reconcile.

## 6. Interference notes

- **Attended only.** `docs/sops/external-dns.md` requires an operator present
  for any change that can alter the record set. Do not place in `nightly`.
- **Public DNS is shared by every internet-facing app.** For the ~45 min of
  this plan, nothing else in the window may add, remove or re-parent an
  `envoy-external` HTTPRoute or touch Gateway `envoy-external`: any such change
  produces legitimate `Changing record.` lines that make Gate 2 unreadable and
  a real regression unattributable. That is why `envoy-gateway-1.9.2` and
  `app-template-5.2.1` (relabels every routed app's HTTPRoute) are in
  `conflicts_with`. Plans that only roll a backend behind an unchanged route
  (jellyfin, n8n, penpot, uptime-kuma) do not conflict.
- **CoreDNS and reloader** (`chart-patches-coredns-reloader-blackbox`):
  external-dns resolves the Cloudflare API through cluster DNS, and its pod
  carries `secret.reloader.stakater.com/reload`; a CoreDNS roll mid-sync books
  provider errors that Gate 3 would attribute to v0.23.0.
- **Flux control-plane plans** (`flux-fleet-0.60.0`,
  `flux-reconciler-impersonation`, `helm-drift-detection`,
  `flux-oci-chart-sources`) all change how or from where this HelmRelease is
  applied; a failure there would be indistinguishable from a chart failure
  here. `flux-oci-chart-sources` additionally moves external-dns's chart source
  in its stage 4 — if that lands first, the 3.3 edit target is unchanged
  (`spec.chart.spec.version`) but re-run the premises.
- **Monitoring is the instrument.** No open `kube-prometheus-stack` plan exists
  today (`kube-prometheus-stack-91.4.1` executed 2026-09-26); any future one
  must not share this window.
- **Reciprocity:** this plan lists seven conflicts; the planner may write only
  this file, so the reciprocal entries on those seven plans are owed (see the
  planner report).
- **No reboot, no storage, no Authentik, no secret change.** The SOPS secret
  `external-dns-secret` is not touched; the pod reads it unchanged.

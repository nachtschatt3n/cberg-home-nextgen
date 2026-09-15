---
plan_id: external-dns-1.22.0
component: external-dns
pr: null                              # direct-bump lane (coverage.py) — no Renovate PR
kind: chart
current: "1.21.1"                     # chart; ships appVersion 0.21.0. Live: deployment/external-dns runs
                                      # registry.k8s.io/external-dns/external-dns:v0.21.0, HR history
                                      # chart=1.21.1 app=0.21.0, verified 2026-09-15
target: "1.22.0"                      # chart, published 2026-09-11 (index.yaml created 2026-09-11);
                                      # ships appVersion 0.22.0; registry.k8s.io tag v0.22.0 exists.
                                      # No 0.22.x patch release exists yet (git tags: v0.21.0, v0.22.0).
update_type: minor
risk: high                            # HONEST. The failure mode is "every internet-facing hostname
                                      # has no public record" — it happened on 2026-09-08 (94 s) from
                                      # the same version move. The MECHANISM is now understood and
                                      # the fix is deterministic (§1), so the probability is low; the
                                      # impact is not. high vetoes every AUTO class by policy.
est_duration_min: 50
needs_reboot: false
touches:
  namespaces: [network]
  resources:
    - helmrelease/external-dns        # chart version line (§3.2)
    - deployment/external-dns         # strategy: Recreate — ~10 s with NO controller running; no
                                      # old/new overlap, so no two-version flapping
    - clusterrole/external-dns        # chart 1.22.0 narrows dnsendpoints/status verbs `*` -> `update`
    - "gateway/envoy-external (network) — metadata.annotations ONLY (§3.1); spec untouched"
    - "cloudflare zone ${SECRET_DOMAIN} — 58 records (26 CNAME + 31 TXT + 1 A); MUST be identical after"
  shared: [gateway/envoy]             # the Gateway object is edited (metadata), and the records this
                                      # controller owns are the public names of every route on it
depends_on: []
conflicts_with:
  - external-dns-unowned-cnames       # same zone, same TXT registry, same controller — §6 explains the
                                      # ORDER (this plan first) and why they must never share a window
  - wazuh-2xx-edge-coverage           # both verify through the public edge path; a probe failure in a
                                      # shared window cannot be attributed
security_ref: F-14528040              # the image on 1.21.1 carries fixable findings; detail on the record
finding_refs:
  - F-14528040                        # security: the fix is gated on exactly this bump (record says so)
  - F-7ef7af04                        # version: "external-dns: chart 1.21.1 -> 1.22.0 (minor)"
capability_change: false              # DNS answers, targets, proxied flags, TTLs: all unchanged
autonomy_override: human-gated        # RESTRICTS only. Public DNS for every external hostname is never
                                      # moved unattended, whatever the policy derives.
rollback_class: git-revert            # external-dns holds no state; the record set is re-asserted from
                                      # cluster state within ~60 s of the revert (measured 2026-09-08)
status: draft
window: null                          # window agent assigns — attended only; see §6 for which fit
premises:
  - id: git-chart-pin-still-1.21.1
    why: >-
      §3.2 edits exactly one line. If the pin already moved, the diff is a no-op and every
      baseline in §4 is stale.
    run: |
      git show HEAD:kubernetes/apps/network/external/external-dns/helmrelease.yaml | grep -c 'version: 1.21.1'
    expect_exact: "1"
  - id: git-has-no-image-override
    why: >-
      31f876fc pinned image.tag ahead of the chart and was reverted (aa79cf7a). If someone re-added
      it, the chart bump would carry a hidden second version move. Refuse to plan on top of it.
    run: |
      git show HEAD:kubernetes/apps/network/external/external-dns/helmrelease.yaml | awk '/^ +tag: v0\./{c++} END{print c+0}'
    expect_exact: "0"
  - id: git-has-no-prefix-or-default-targets-arg
    why: >-
      §1 rejects --default-targets (wrong scope) and does not use --annotation-prefix (Path B).
      If either is already in extraArgs the design here no longer describes the cluster.
    run: |
      git show HEAD:kubernetes/apps/network/external/external-dns/helmrelease.yaml | awk '/annotation-prefix/{c++} /default-targets/{c++} END{print c+0}'
    expect_exact: "0"
  - id: live-image-is-v0.21.0
    why: >-
      `current:` claims v0.21.0 on the serving Deployment. If the cluster already runs v0.22.0,
      stop and find out how (README "known phantoms" shape).
    run: |
      kubectl get deploy -n network external-dns -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: registry.k8s.io/external-dns/external-dns:v0.21.0
  - id: live-hr-ready-on-1.21.1
    why: >-
      A HelmRelease mid-remediation or on a different chart revision means the Flux state
      machine is not where §3.2 assumes it is.
    run: |
      kubectl get helmrelease -n network external-dns -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} {.status.history[0].chartVersion}'
    expect_exact: "True 1.21.1"
  - id: live-args-carry-the-six-load-bearing-flags
    why: >-
      policy=sync + txt registry + owner id + prefix + the one-Gateway allowlist are what make
      the §1 analysis and the §4 baselines true. The chart bump must not change any of them
      (rendered diff proves it does not — §1.4), so they must be present going in.
    run: |
      kubectl get deploy -n network external-dns -o jsonpath='{.spec.template.spec.containers[0].args}' | tr ',' '\n' | grep -c -e '--policy=sync' -e '--registry=txt' -e '--txt-owner-id=default' -e '--txt-prefix=k8s\.' -e '--gateway-name=envoy-external' -e '--gateway-namespace=network'
    expect_exact: "6"
  - id: gateway-carries-the-alpha-target-annotation
    why: >-
      The alpha key is what v0.21.0 reads today and what the §5 rollback relies on. If it is
      gone, v0.21 is already publishing the LAN address and this plan is not the first problem.
    run: |
      kubectl get gateway -n network envoy-external -o jsonpath='{.metadata.annotations.external-dns\.alpha\.kubernetes\.io/target}'
    expect_matches: '^external\.'
  - id: controller-is-quiescent
    why: >-
      The whole verification is "nothing changed". Starting from a controller that is mid-change
      makes the before/after diff meaningless. Three consecutive up-to-date syncs, or wait.
    run: |
      kubectl logs -n network deploy/external-dns --tail=3 | grep -c 'All records are already up to date'
    expect_exact: "3"
  - id: envoy-gateway-kustomization-ready
    why: >-
      §3.1 lands through the `envoy-gateway` Flux Kustomization. If it is not Ready the GA
      annotation never reaches the Gateway and §3.2 would run against a Gateway v0.22 cannot read.
    run: |
      kubectl get kustomization -n network envoy-gateway -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: "True"
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/external-dns.md
  - docs/sops/gateway-api-httproute.md
  - docs/sops/auto-update.md
generated: "2026-09-15"
---

# external-dns chart 1.21.1 -> 1.22.0 (image v0.21.0 -> v0.22.0)

## 1. Summary & why held

**The hold is correct. The remedy the hold prescribes is wrong, and following it
would reproduce the 2026-09-08 outage.** Read this section before touching anything.

### 1.1 What the deny rule and the SOP say

`runbooks/auto-update-policy.yaml` (`*external-dns*`) and `docs/sops/external-dns.md`
§3 "Version trap" both state that v0.22.x "changes how the
`external-dns.alpha.kubernetes.io/target` annotation on the PARENT Gateway is
honoured" and that the chart bump "requires `--default-targets` in extraArgs
landed in the SAME change". The finding record `F-14528040` carries the same
remedy. `security_ref: F-14528040` — the vulnerability detail stays on that record.

### 1.2 What actually changed in v0.22.0 (upstream evidence)

The v0.22.0 release notes list, under breaking changes:

> **switch default annotations prefix to GA (#6424)** — Default annotation prefix
> is now `external-dns.kubernetes.io/` with no fallback

PR #6424's own description: *"You can either migrate your annotations or set
`--annotation-prefix=external-dns.alpha.kubernetes.io/`"* and *"This change can
**delete all** your DNS records"* if annotations are not migrated. Merged
2026-05-09 into v0.22.0.

The code at tag `v0.22.0` confirms exactly how that reaches us:

- `source/annotations/annotations.go:22` — `DefaultAnnotationPrefix = "external-dns.kubernetes.io/"`;
  `TargetKey = AnnotationKeyPrefix + "target"`. At `v0.21.0` the same constant is
  `"external-dns.alpha.kubernetes.io/"`.
- `source/gateway.go:666` and `:697` — the gateway-httproute source takes route
  targets from `annotations.TargetsFromTargetAnnotation(gw.Annotations)`, i.e.
  the **parent Gateway's** annotations under `TargetKey`; with no override it
  falls back to the Gateway's status addresses. A route-level target annotation
  is still not read (the SOP rule stands).
- `pkg/apis/externaldns/validation/validation.go:59-62` — `--annotation-prefix`
  must be non-empty and end in `/`; a malformed value fails at startup.

So on 2026-09-08 the v0.22.0 binary did not "stop honouring Gateway
annotations". It looked for `external-dns.kubernetes.io/target`, our Gateway
carries `external-dns.alpha.kubernetes.io/target`, it found nothing, fell back to
the Gateway address `192.168.55.104`, and under `policy: sync` deleted 17 CNAMEs
before Cloudflare refused the private target (`9003`). That matches the finding
record's reconstruction; only the cause was misattributed.

### 1.3 Why `--default-targets` is NOT the fix (and `--force-default-targets` is worse)

The v0.22.0 flag help (`pkg/apis/externaldns/types.go:515`):

> `--default-targets` — Set globally default host/IP that will apply as a target
> instead of source addresses. **Only applies to the crd source (DNSEndpoint
> resources with empty targets).**

`source/wrappers/multisource.go:41-66` implements it: a default target is applied
only when the source produced **no** targets, or when `--force-default-targets`
is set; otherwise it logs *"Source provided targets for … ignoring default
targets … Use --force-default-targets to revert to old behavior."* The
gateway-httproute source **always** produces a target (the Gateway address when
the annotation is missing), so `--default-targets` alone changes nothing and the
outage repeats. `--force-default-targets` (help text: *DEPRECATED*) would override
**every** source, including `crd/network/cloudflared`, rewriting
`external.${SECRET_DOMAIN}` to point at itself. Neither flag appears in this plan.

### 1.4 What the chart bump itself changes — measured, not assumed

`helm template` of 1.21.1 and 1.22.0 against this HelmRelease's exact `values:`
(2026-09-15) differs in **three things only**: chart labels, the image tag
`v0.21.0 -> v0.22.0`, and `clusterrole` verbs on `dnsendpoints/status` narrowed
from `*` to `update`. Every container arg is identical, `--policy=sync` is
rendered explicitly (chart 1.22.0 made `policy` required with no default — we set
it, so the "Breaking" entry in the chart CHANGELOG is inert here), and the
Deployment is `strategy: Recreate`. Chart-added values (`service.enabled`,
`replicaCount`, `hostAliases`, `registry: crd`) are all at defaults that render
what 1.21.1 rendered.

Other v0.22.0 notes checked and irrelevant to this deployment: TLSRoute moved
to v1 (source not enabled), `a-` TXT prefix for AWS ALIAS (AWS only), Cloudflare
SRV structured data (no SRV records), API-token whitespace trim (benign),
provider removals (akamai/plural/transip), Pi-hole v5 drop.

### 1.5 The fix this plan uses — Path A, dual annotation, ordering-proof

Put the GA-prefixed twin **`external-dns.kubernetes.io/target`** on Gateway
`envoy-external` with the same value, in its **own commit first**, keep the alpha
key, verify it is live on the object, then bump the chart. v0.21 reads the alpha
key and ignores the GA key (its prefix is hard-set alpha; the GA key is just an
unrelated annotation to it); v0.22 reads the GA key and ignores the alpha one.
Both versions therefore agree on the target `external.${SECRET_DOMAIN}` at every
instant, whichever pod is running, and no record is ever recomputed to a
different value — so `sync` has nothing to delete. No flags, nothing deprecated,
and the alpha key remains the live rollback path for as long as v0.21 is where a
revert lands.

**Path B, recorded so it is not re-derived:** `--annotation-prefix=external-dns.alpha.kubernetes.io/`
in `extraArgs`, same commit as the bump. It works (the flag exists on both
versions; the value is validated at startup) and it is a one-file change. It is
not chosen because it keeps every SOP, blueprint and manifest on a prefix
upstream has already left, and because a single mistyped flag value is accepted
as long as it ends in `/` — the GA key on the Gateway cannot be "mistyped into
silently matching nothing" in the same way. Use Path B only if §3.1 cannot land.

### 1.6 Inert alpha annotations elsewhere — checked, no action

`grep` over `kubernetes/` finds the alpha key in 8 files. Only `gateways.yaml`
is live. `iobroker`, `authentik` (helmrelease), `mosquitto` sit on Ingress
templates or Services — neither is in `sources:`; `plex`, `authentik/httproute`,
`zigbee2mqtt`, `echo-server` are comments. None changes behaviour on either
version. `crd/network/cloudflared` (DNSEndpoint) has explicit targets and no
annotation dependency. Migrating those files to the GA prefix is a docs/hygiene
follow-up, not window work.

## 2. Pre-checks

Machine-checked first: `python3 runbooks/plan-premises.py external-dns-1.22.0 --require-premises`
— all nine must PASS. Then, in the window:

```bash
cd /Users/mu/code/cberg-home-nextgen && export KUBECONFIG=$PWD/kubeconfig

# 2.1 Cluster quiet; the two Kustomizations this plan lands through are Ready
mise exec -- flux get kustomizations -A | awk 'NR==1 || $5 != "True"'
mise exec -- flux get helmreleases -n network external-dns

# 2.2 The chart is reachable by Flux — index carries 1.22.0 / appVersion 0.22.0
curl -s https://kubernetes-sigs.github.io/external-dns/index.yaml | python3 -c "
import sys, yaml; e = yaml.safe_load(sys.stdin)['entries']['external-dns'][0]
print(e['version'], e['appVersion']); assert (e['version'], e['appVersion']) == ('1.22.0', '0.22.0')"
mise exec -- kubectl -n flux-system get helmrepository external-dns -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}{"\n"}'

# 2.3 The six external-dns alert rules are LOADED (SOP §6 Test 4) — they ARE the safety net.
#     Do NOT silence them for this window. A firing ExternalDNSRegistryErrors /
#     ExternalDNSRecordsCollapsed is the abort signal for §3.2, not noise.
mise exec -- kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 >/dev/null 2>&1 &
sleep 2; curl -s http://localhost:9090/api/v1/rules | python3 -c "
import sys, json
names = [r['name'] for g in json.load(sys.stdin)['data']['groups'] for r in g['rules']]
for a in ['ExternalDNSRegistryErrors','ExternalDNSSourceErrors','ExternalDNSSyncStalled',
          'ExternalDNSRecordsCollapsed','ExternalDNSErrorMetricsAbsent','ExternalDNSSyncMetricsAbsent']:
    print(f'{a:32} {\"LOADED\" if a in names else \"*** MISSING — STOP ***\"}')"
curl -s 'http://localhost:9090/api/v1/alerts' | grep -o '"alertname":"ExternalDNS[^"]*"' | sort -u   # expect nothing

# 2.4 Metric baselines (compared in §4)
curl -s 'http://localhost:9090/api/v1/query?query=external_dns_controller_verified_records{record_type="cname"}' | python3 -c "import sys,json; print('cname verified:', json.load(sys.stdin)['data']['result'][0]['value'][1])"   # expect 25
curl -s 'http://localhost:9090/api/v1/query?query=external_dns_registry_errors_total' | python3 -c "import sys,json; print('registry errors:', [r['value'][1] for r in json.load(sys.stdin)['data']['result']])"   # note the value; expect 0

# 2.5 Active-update marker (application-update SOP step 1) — marker only, NO silence on ExternalDNS*
runbooks/update-marker.sh add external-dns network 2 "chart 1.21.1->1.22.0 (v0.22.0, GA annotation prefix)"

# 2.6 Rollout-noise silence is NOT needed: strategy Recreate gives a ~10 s pod gap and
#     KubeDeploymentReplicasMismatch has for: 15m.
```

### 2.7 Capture the public record set BEFORE — the §4 baseline and the §5 inventory

Read-only: `GET` only. This snippet must never be edited into a write. The domain
is resolved from the cluster secret and never printed.

```bash
mkdir -p /tmp/edns-1.22.0 && cd /Users/mu/code/cberg-home-nextgen && export KUBECONFIG=$PWD/kubeconfig
CF_TOKEN=$(mise exec -- sops -d kubernetes/apps/network/external/external-dns/secret.sops.yaml | python3 -c "import sys,yaml;print(yaml.safe_load(sys.stdin)['stringData']['api-token'])")
D=$(mise exec -- kubectl -n flux-system get secret cluster-secrets -o jsonpath='{.data.SECRET_DOMAIN}' | base64 -d)
ZID=$(curl -s -H "Authorization: Bearer $CF_TOKEN" "https://api.cloudflare.com/client/v4/zones?name=$D" | python3 -c "import sys,json;print(json.load(sys.stdin)['result'][0]['id'])")
snap() {   # $1 = before | after   — READ-ONLY listing
  curl -s -H "Authorization: Bearer $CF_TOKEN" "https://api.cloudflare.com/client/v4/zones/$ZID/dns_records?per_page=1000" > /tmp/edns-1.22.0/$1.json
  python3 - "$1" <<'EOF'
import sys, json, collections
tag = sys.argv[1]
d = json.load(open(f'/tmp/edns-1.22.0/{tag}.json'))
recs = d['result']
assert len(recs) == d['result_info']['total_count'], 'TRUNCATED LISTING — do not proceed'
rows = sorted((r['type'], r['name'], r['content'], str(r['proxied']), r['id'], r['modified_on']) for r in recs)
open(f'/tmp/edns-1.22.0/{tag}.tsv', 'w').write('\n'.join('\t'.join(x) for x in rows) + '\n')
print(tag, len(recs), dict(collections.Counter(r['type'] for r in recs)))
EOF
}
snap before
# EXPECT (measured 2026-09-15): before 58 {'CNAME': 26, 'TXT': 31, 'A': 1}
#   26 CNAME, all proxied: 25 -> external.${SECRET_DOMAIN} (24 HTTPRoute hosts + echo-server
#   leftover), 1 (`external`) -> the tunnel hostname; 18 k8s.cname-* ownership TXTs;
#   8 CNAMEs unowned (the external-dns-unowned-cnames plan's set). A different shape
#   means the zone moved since this plan was written — re-baseline, do not assume.

# 2.8 Edge-pinned public baseline — NOT via the LAN resolver (external-dns SOP §6 Test 3)
dig +short @1.1.1.1 auth.$D                                   # expect Cloudflare anycast IPs, not 192.168.55.x
dig @1.1.1.1 nx-probe-9f3a.$D A | grep -E 'status:|ANSWER: '  # negative control: expect `ANSWER: 0`
```

## 3. Steps

Shared worktree: `git commit --only <paths>`, `git show --stat HEAD` before every
push. Two cluster commits, strictly in this order, each verified before the next.

### 3.1 Commit 1 — put the GA-prefixed target key on Gateway `envoy-external` (inert on v0.21)

Edit `kubernetes/apps/network/envoy-gateway/app/gateways.yaml`. Directly under the
existing line

```yaml
    external-dns.alpha.kubernetes.io/target: "external.${SECRET_DOMAIN}"
```

add (same indentation, inside the same `annotations:` map of Gateway `envoy-external`):

```yaml
    # GA-prefixed twin of the alpha key above. external-dns v0.22.0 (#6424) reads
    # external-dns.kubernetes.io/* ONLY — there is no fallback to the alpha
    # prefix. Both keys carry the same value so v0.21 (alpha) and v0.22 (GA)
    # agree on the target at every instant; the alpha key is the rollback path
    # and stays until v0.21 is no longer where a revert lands. Never remove one
    # key without proving the other is read by the version that is RUNNING.
    external-dns.kubernetes.io/target: "external.${SECRET_DOMAIN}"
```

Do not touch `envoy-internal`. Do not touch `spec:`.

```bash
cd /Users/mu/code/cberg-home-nextgen
mise exec -- task kubeconform
git add -N kubernetes/apps/network/envoy-gateway/app/gateways.yaml 2>/dev/null; true
git commit --only kubernetes/apps/network/envoy-gateway/app/gateways.yaml -F /tmp/edns-1.22.0/msg1.txt
git show --stat HEAD          # exactly one file, yours
git push origin main
```

Verify commit 1 before going on — all three, no exceptions:

```bash
# (a) both keys live on the object, same value
mise exec -- kubectl -n network get gateway envoy-external -o jsonpath='{.metadata.annotations}{"\n"}' | sed "s/$D/<D>/g"
# EXPECT both external-dns.alpha.kubernetes.io/target and external-dns.kubernetes.io/target = external.<D>

# (b) v0.21 did not care: three more quiescent syncs, zero errors
sleep 200; mise exec -- kubectl -n network logs deploy/external-dns --tail=3 | grep -c 'All records are already up to date'   # 3

# (c) metadata-only: the Envoy proxy pods for envoy-external did NOT restart
mise exec -- kubectl -n network get pods -l gateway.envoyproxy.io/owning-gateway-name=envoy-external -o custom-columns=NAME:.metadata.name,AGE:.metadata.creationTimestamp,RESTARTS:.status.containerStatuses[0].restartCount
```

If (a) fails, the Kustomization did not apply — fix that first; **do not proceed
to 3.2 with the GA key absent**, that is the exact 2026-09-08 configuration.

### 3.2 Commit 2 — the chart bump (one line; no image pin, no new flags)

Edit `kubernetes/apps/network/external/external-dns/helmrelease.yaml`:

```yaml
  chart:
    spec:
      chart: external-dns
      # 1.22.0 ships appVersion 0.22.0. v0.22.0 (#6424) reads ONLY the GA
      # annotation prefix external-dns.kubernetes.io/ — Gateway envoy-external
      # must carry external-dns.kubernetes.io/target BEFORE this line moves, or
      # every owned record is deleted and its recreate rejected (2026-09-08,
      # aa79cf7a). --default-targets does NOT reach the gateway-httproute source
      # (v0.22.0 flag help) and is not the fix. Plan: external-dns-1.22.0.
      version: 1.22.0
```

`values:` are untouched: no `image:` block (the chart's appVersion is the image),
no `--annotation-prefix`, no `--default-targets`. Rendered delta is §1.4.

```bash
mise exec -- kubeconform -summary -ignore-missing-schemas kubernetes/apps/network/external/external-dns
git commit --only kubernetes/apps/network/external/external-dns/helmrelease.yaml -F /tmp/edns-1.22.0/msg2.txt
git show --stat HEAD && git push origin main

# STAY. Watch the reconcile and the FIRST sync of the new binary together.
mise exec -- flux get helmreleases -n network external-dns --watch &     # until 1.22.0 Ready
mise exec -- kubectl -n network logs deploy/external-dns -f
```

What the first v0.22.0 log lines must look like: startup, source/provider
init, then `All records are already up to date`. **Abort to §5 immediately** on
any of: `Desired change: DELETE`, `CREATE … A 192.168.55.104`, `9003`,
`Target is not allowed`, `level=error`, `forbidden` (RBAC), or
`Using custom annotation prefix` (would mean a flag crept in). Do not wait for
the alert `for:` timers — 94 s is the whole incident.

### 3.3 Soak, then §4

Ten minutes on v0.22.0 with the log quiescent, then run every assertion in §4.
Clear the marker on success: `runbooks/update-marker.sh clear external-dns`.

### 3.4 Same window, doc-only commits — correct the wrong remedy where it is written

Each with `git commit --only`, separate from the cluster commits. None reconciles.

1. `docs/sops/external-dns.md` — §2 table (chart/image row), §3 "Version trap"
   and §5 Example B: replace the `--default-targets` remedy with §1.2/§1.3/§1.5 of
   this plan (GA prefix, no fallback, Gateway must carry
   `external-dns.kubernetes.io/target`; `--default-targets` is crd-only). Bump
   the SOP version.
2. `runbooks/auto-update-policy.yaml` — the `*external-dns*` `reason:` text:
   correct the mechanism; **keep the deny** (a future 0.23 can move the ground
   again, and `sync` still deletes before it creates). Bump the policy `version`.
3. `docs/sops/gateway-api-httproute.md` rule 3 and
   `docs/sops/new-deployment-blueprint.md` §11: the Gateway carries both keys;
   new work uses the GA key.
4. On the finding: `runbooks/policy-cli.py finding detail F-14528040 --plan external-dns-1.22.0 --detail-file <note>`
   stating the corrected cause and that the bump landed (DB, not repo — no detail in git).

### 3.5 Retire this plan

Once §4 is green and the doc commits are in: delete this file in the same commit
as the last doc change (README: plans are transient). The security finding
resolves on the next `security-check` cycle against the v0.22.0 image; do not
close it by hand with a count.

## 4. Verification

The floor: `flux get hr -n network external-dns` Ready on `1.22.0`; pod
`1/1 Running`, 0 restarts after settle. The section is the four assertions.

```
CONTENTS ASSERTION 1 — the public record set is BYTE-IDENTICAL, including ids.
  measured by:  snap after && diff /tmp/edns-1.22.0/before.tsv /tmp/edns-1.22.0/after.tsv && echo IDENTICAL
  compared to:  the §2.7 baseline (58 = 26 CNAME + 31 TXT + 1 A).
  The TSV carries record `id` and `modified_on`, so a delete-then-recreate that
  landed on the same name/content STILL shows as a diff. "verified_records == 25"
  alone would pass through a full delete+recreate cycle; this does not.

CONTENTS ASSERTION 2 — the NEW binary is the one that is quiescent.
  measured by:
    kubectl -n network get pod -l app.kubernetes.io/name=external-dns -o jsonpath='{.items[0].spec.containers[0].image} {.items[0].metadata.labels.app\.kubernetes\.io/version}{"\n"}'
      -> registry.k8s.io/external-dns/external-dns:v0.22.0 0.22.0
    kubectl -n network get helmrelease external-dns -o jsonpath='{.status.history[0].chartVersion} {.status.history[0].appVersion}{"\n"}'
      -> 1.22.0 0.22.0
    kubectl -n network logs deploy/external-dns --tail=200 | grep -c 'All records are already up to date'   -> >= 3
    kubectl -n network logs deploy/external-dns --tail=200 | grep -iE '9003|not allowed|level=error|forbidden|ignoring default targets|custom annotation prefix' -> no output
  compared to: the §2.4 metric baselines —
    external_dns_controller_verified_records{record_type="cname"} == 25 (unchanged)
    external_dns_registry_errors_total == the §2.4 value (unchanged; expected 0)
    time() - external_dns_controller_last_sync_timestamp_seconds < 150

CONTENTS ASSERTION 3 — public resolution end-to-end, edge-pinned, with a negative control.
  measured by:
    dig +short @1.1.1.1 auth.$D                                    -> Cloudflare anycast IPs (same as §2.8)
    dig +short @1.1.1.1 hass.$D                                    -> same shape (an UNOWNED record — proves the
                                                                      owner filter still left it alone)
    dig @1.1.1.1 nx-probe-9f3a.$D A | grep -E 'status:|ANSWER: '   -> ANSWER: 0   (discriminate on ANSWER: 0,
                                                                      not NXDOMAIN — Cloudflare returns NODATA)
  compared to: §2.8. A 192.168.55.x answer or an empty answer for a real host = §5, now.

CONTENTS ASSERTION 4 — the RBAC narrowing did not break the crd source.
  measured by:  kubectl -n network get dnsendpoint cloudflared -o jsonpath='{.status}{"\n"}'  (non-empty, observedGeneration present)
                and zero `forbidden` in the log (assertion 2).
```

Then: no `ExternalDNS*` alert firing (`curl -s localhost:9090/api/v1/alerts | grep -o '"alertname":"ExternalDNS[^"]*"'`
→ nothing), and `health-check-agent` + `security-agent` for the standard close-out.

## 5. Rollback

`git revert` of **commit 2 only**. Leave commit 1 (the GA key) in place — it is
inert on v0.21 and harmless, and removing it re-creates the trap for the retry.

```bash
cd /Users/mu/code/cberg-home-nextgen
git revert --no-edit <sha-of-commit-2>      # chart back to 1.21.1 -> image v0.21.0
git show --stat HEAD && git push origin main
mise exec -- kubectl -n network logs deploy/external-dns -f     # v0.21.0 reads the alpha key, re-asserts the set
```

Why this is enough: external-dns holds no state; v0.21.0 derives the desired set
from the cluster and the alpha annotation, which never left the Gateway, and
recreates anything missing on its first sync. Measured 2026-09-08: revert pushed
at 05:45:08, all 17 CNAMEs + TXTs back at 05:45:53.

Confirm the cluster is back:

```bash
mise exec -- kubectl -n network get deploy external-dns -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'   # …:v0.21.0
snap after-rollback
diff <(cut -f1-4 /tmp/edns-1.22.0/before.tsv) <(cut -f1-4 /tmp/edns-1.22.0/after-rollback.tsv) && echo "SET RESTORED (type/name/content/proxied)"
diff /tmp/edns-1.22.0/before.tsv /tmp/edns-1.22.0/after-rollback.tsv | grep -c '^>'    # = number of records that were recreated (new id) — the incident size, for the record
```

If Helm is wedged `pending-upgrade` (application-update SOP §11):
`helm rollback external-dns <last-deployed> -n network --wait=false` then
`flux reconcile helmrelease -n network external-dns --force`. If a revert does
**not** restore the records, the cause is upstream of external-dns: Gateway
still exists and still carries the alpha key (§premises), then the tunnel
(`docs/sops/cloudflare.md`).

Never hand-create records to "bridge the gap": `sync` deletes them at the next
reconcile and they confuse the diff you are relying on.

## 6. Interference notes

- **`external-dns-unowned-cnames` — conflicts, and THIS plan runs FIRST.**
  Same zone, same TXT registry, same controller. Two reasons for the order:
  (1) while the 8 records are unowned they are structurally immune to a `sync`
  delete (that plan §1.1/§4) — a regression here today costs 17 gateway records
  and never `hass` or `flux-webhook`; after adoption it would cost 24 including
  both. Bump on the smaller blast radius, adopt afterwards. (2) That plan's
  premise §5.0.2 asserts the live args (policy=sync, txt, owner `default`,
  prefix `k8s.`) — unchanged by this bump (§1.4), so it stays satisfiable — but
  its §1.1 claim ("ownership TXT is written only on `Create`") was derived from
  v0.21 code. Before it executes on v0.22.0, re-read `registry/txt.go` at tag
  `v0.22.0` and confirm; a one-line check, but its whole Path A depends on it.
  Recommend that plan add `depends_on: [external-dns-1.22.0]` — an edit to that
  file, outside this plan's write scope. Give v0.22.0 **>= 7 days** of
  `All records are already up to date` before adoption.
- **`wazuh-2xx-edge-coverage` — conflicts.** Both verify through the public edge
  path; a probe failure in a shared window cannot be attributed to either.
- **Windows.** Human-gated and `risk: high`: never `nightly`. By capacity and
  duration: `sun-attended:2026-09-20` fits (absenty 60 + 50 = 110 of 200 min,
  risk 1 + 3 = 4 of 6) — it is reboot-capable and this is not reboot work, but
  `sat-attended:2026-09-19` does not fit by duration (media-audit 45 + 50 = 95 > 90)
  unless that plan moves. NOT `sat-attended:2026-09-26` (wazuh) and NOT
  `sat-attended:2026-10-03` (unowned-cnames) — both `conflicts_with`. NOT
  `sun-attended:2026-09-27`: a public-DNS change during rolling Talos reboots is
  a misattribution machine, and 140 + 50 > 200 anyway. Whatever is chosen, it is
  **before 2026-10-03**.
- **Attended means: someone watching the log at §3.2 with the revert command
  typed.** The bound on 2026-09-08 was a human at the keyboard; that is the
  control this plan relies on too.
- **Do not silence the six `ExternalDNS*` rules.** They are the abort signal.
  `ExternalDNSRegistryErrors` and `ExternalDNSRecordsCollapsed` firing during
  §3.2 means §5, not "expected update noise".
- **`Recreate` strategy** (rendered, §1.4): ~10 s with no controller at all
  during the pod swap. Nothing is deleted in that gap — nothing is running to
  delete it. It also means old and new never run concurrently, so there is no
  two-version disagreement to flap on.
- **Shared infra:** `gateway/envoy` — the Gateway object receives a metadata
  annotation (commit 1). Verified in §3.1(c) that the proxy pods do not restart;
  if they do, treat it as a data-plane blip to note, not a reason to abort, and
  record it for the wazuh plan which edits the same object. No cert-manager,
  cilium, coredns, storage or node involvement.
- **The deny rule stays.** This plan does not lift `*external-dns*` from
  `auto-update-policy.yaml`; it corrects the reason text (§3.4). The next
  external-dns release gets its own plan.

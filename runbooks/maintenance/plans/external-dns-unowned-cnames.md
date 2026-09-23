---
plan_id: external-dns-unowned-cnames
component: external-dns
pr: null
kind: infra
current: "8 live public CNAMEs carry no external-dns ownership TXT: drive, echo-server, flux-webhook, hass, kuma, n8n, open-webui, paperless. All 8 were created out-of-band in one 0.55-second scripted burst on 2025-04-19T23:34:30Z and have modified_on == created_on — never touched since, by anything. external-dns reports 25 verified CNAMEs; 18 carry a k8s.cname-* registry record. Because external-dns does not know it owns the 8, a delete would not be repaired."
target: "The 7 unowned records that HAVE a live envoy-external HTTPRoute source are adopted into the txt registry by writing their k8s.cname-* ownership TXT out-of-band — zero CNAME churn, no Create ever emitted. echo-server is deliberately EXCLUDED and decided separately (§3.2). The 4 k8s.a-* and 9 legacy k8s.<host> TXT leftovers are deliberately LEFT IN PLACE (§7)."
update_type: refactor                 # no version moves; this changes who owns what
risk: medium                          # small change set, but the objects are the
                                      # public names of flux-webhook and hass
est_duration_min: 40
needs_reboot: false
touches:
  namespaces: [network]
  resources:
    - "cloudflare zone ${SECRET_DOMAIN} — 7 new TXT records (k8s.cname-*)"
    - helmrelease/external-dns
    - deployment/external-dns
  shared: [gateway/envoy]             # the records are the public names of the
                                      # envoy-external Gateway's routes
depends_on: []                        # 2026-09-15: was [external-dns-1.22.0]. That plan
                                      # EXECUTED and was retired in the same change
                                      # (chart 1.22.0 / v0.22.0 landed 0a316a51, pod up
                                      # 2026-09-15T17:03Z, zone byte-identical), so the
                                      # ref would be a DEAD-REF error. The ORDERING half
                                      # is satisfied. The SOAK half is no longer
                                      # machine-enforced and STILL BINDS: >= 7 days of
                                      # `All records are already up to date` on v0.22.0
                                      # before adoption — not before 2026-09-22T17:03Z.
                                      # While the 8 are unowned they are immune to a
                                      # sync delete, so a bump regression costs 17
                                      # records, never hass or flux-webhook; after
                                      # adoption it would cost 24.
premises:                             # F-9404f24b (2026-09-22). depends_on used to carry
                                      # the 7-day soak as a machine-enforced ordering ref;
                                      # when external-dns-1.22.0 executed and was retired
                                      # the ref became a DEAD-REF error and was cleared,
                                      # leaving the soak as the comment above. These make
                                      # it a gate again: the window agent runs
                                      # `plan-premises.py --require-premises` on every
                                      # sequenced plan, so this plan is REFUSED until both
                                      # hold. Read live 2026-09-22 10:50Z: NOT-SOAKED
                                      # (soak-until 2026-09-22T17:03:05Z), as intended.
  - id: chart-1.22.0-soaked-7d
    why: >-
      Adoption must not run until chart 1.22.0 (external-dns v0.22.0) has been
      the deployed release for at least 7 days. While the 8 CNAMEs are unowned a
      bump regression can only delete the 17 registry-owned records; after
      adoption it would delete 24, including flux-webhook and hass. Time-aware
      on purpose (jq `now` against the HelmRelease's lastDeployed) so the same
      premise refuses on 2026-09-16 and passes on 2026-09-23 -- a static date
      would pass the moment the chart landed. 604800 = 7 * 86400. A chart other
      than 1.22.0 yields NO output (select), which plan-premises.py reads as a
      failure, never as a pass. CORRECTED 2026-09-23 (review): reads the
      EARLIEST 1.22.0 lastDeployed across the whole history, not history[0],
      so the §6.2 registry pin (a new Helm revision of the same chart) cannot
      reset the soak; `select(. != null)` guards `min` of an empty array,
      because jq's `null + 604800` is a number and would have printed SOAKED
      for a chart that was never deployed.
    run: >-
      kubectl get helmrelease -n network external-dns -o json
      | jq '.status.history'
      | jq 'map(select(.chartVersion == "1.22.0"))'
      | jq 'map(.lastDeployed[0:19] + "Z")'
      | jq 'map(fromdateiso8601)'
      | jq 'min'
      | jq 'select(. != null)'
      | jq -r 'if . + 604800 <= now then "SOAKED chart=1.22.0 deployed-epoch=\(.) soak-until-epoch=\(. + 604800) now-epoch=\(now)" else "NOT-SOAKED chart=1.22.0 deployed-epoch=\(.) soak-until-epoch=\(. + 604800) now-epoch=\(now)" end'
    expect_matches: "^SOAKED chart=1\\.22\\.0 "
  - id: pod-runs-v0.22.0
    why: >-
      The soak is on the running binary, not on the chart record: the Deployment
      must actually run external-dns v0.22.0 (chart 1.22.0's appVersion). A
      rolled-back or hand-patched image would leave the HelmRelease history
      saying one thing and the pod doing another.
    run: kubectl get deploy -n network external-dns -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_contains: "external-dns:v0.22.0"
conflicts_with:                       # FILLED 2026-09-21; was deliberately [].
  - jellyfin-12.1                     # ROLLBACK-CLASS STACKING for all five. Each of
  - media-naming-p3                   # them is `rollback_class: backup-restore`, as
  - n8n-2.39.8                        # is this plan, and two backup-restore
  - nextcloud-34.0.4                  # rollbacks in one slot leave no rollback
  - nocodb-2026.09.0                  # capacity for either — the stacking the
                                      # reconciler already rejected for
                                      # jellyfin+frigate (see jellyfin-12.1's
                                      # `window:` note).
                                      # WHY THE FIELD AND NOT JUST THE EXISTING
                                      # CHECK: maintenance-plan.py DOES warn on this
                                      # (IRREVERSIBLE_ROLLBACK is ("one-way",
                                      # "backup-restore")), but it is detective and
                                      # advisory — warnings.append, and only once
                                      # both plans are already slotted. conflicts_with
                                      # is preventive: it is what stops
                                      # window-scheduler.py placing the pair in one
                                      # slot at all.
                                      # DECLARED ONCE PER PAIR. window-scheduler.py
                                      # :253-260 honours this field in EITHER
                                      # direction ("symmetric by meaning"), so the
                                      # five counterpart files need no reciprocal
                                      # entry and nextcloud-34.0.4 — vetted, with a
                                      # recorded operator GO — was left untouched.
                                      # UNCHANGED REASONING: the wazuh-2xx-edge-
                                      # coverage constraint stays in §10 rather than
                                      # here. That plan is `draft`, and a guard is
                                      # only worth what the referenced plan's
                                      # liveness is worth. Re-evaluate when it is
                                      # vetted.
capability_change: false              # DNS answers do not change; only who is
                                      # recorded as owning them
autonomy_override: human-gated        # RESTRICTS only. Writes against the public
                                      # zone that carries flux-webhook and hass
                                      # must never run unattended.
rollback_class: backup-restore        # the undo is "delete the 7 TXTs again",
                                      # which restores the exact prior state —
                                      # but only if the prior state was captured.
                                      # No git commit governs a Cloudflare record,
                                      # so the zone export IS the rollback source
                                      # and the gate below is what makes it real.
backup_gate: >-
  BEFORE any record is written, all four must pass:
  (a) export the FULL zone to a timestamped file — every record's id, type, name,
  content, ttl, proxied flag — and assert the row count equals the live count
  reported by the Cloudflare API in the same call (measured 2026-09-09: 58
  records = 26 CNAME + 1 A + 31 TXT). A partial export that silently truncated is
  the failure this catches;
  (b) assert the export contains all 8 target CNAMEs BY NAME with non-empty
  content — an export that parsed but lost the very records at risk is not a
  backup — AND (added 2026-09-23 review) that each of the 7 adoption targets is
  `proxied: true` with `content` identical to an owned record's content (the
  `jellyfin` CNAME): plan.go:303-304 emits an in-place Update the moment an
  adopted record differs from desired in target or proxied flag, so a mismatch
  means adoption would CHANGE the CNAME and "delete the TXT" would no longer be
  a byte-identical rollback. Any mismatch → do not adopt that host, re-diagnose;
  (c) prove the export is USABLE, not merely present: pick one record from it and
  reconstruct the exact API call that would recreate it (`--dry-run` / print
  only, do not send). If the export cannot be turned back into a create call, it
  is a log file, not a restore path;
  (d) `external_dns_registry_errors_total == 0` and the external-dns log shows
  `All records are already up to date` for the last 3 consecutive reconciles —
  i.e. the controller is quiescent before we perturb its registry.
  If any of (a)-(d) fails, write nothing.
status: vetted                        # VETTED 2026-09-23: plan-reviewer-agent verdict
                                      # needs-fix -> ready-for-go on two file-only gate
                                      # corrections (Assertion 1 discriminator, backup_gate
                                      # (b) proxied/content assertion), both applied in the
                                      # same change together with the premise `min` fix.
                                      # Operator GO recorded for an attended on-demand run
                                      # on 2026-09-23 (soak premise passed 2026-09-22T17:03Z).
window: "sat-attended:2026-10-03"     # see §2 for why deliberately NOT sooner.
                                      # Attended; empty slot; separated by a week
                                      # from wazuh-2xx-edge-coverage (09-26) so
                                      # the two external-path plans cannot share
                                      # a window (§10). NOT sun-attended:2026-09-27,
                                      # which is at 140 of 150 min for talos-1.14.0,
                                      # and not a Sunday slot generally — this is
                                      # not reboot work.
security_ref: null
finding_refs:
  - F-36a7105a                        # public records for externally-routed apps carry no ownership record
  - F-6ed6d4ee                        # a decommissioned-from-external app still has a public record into the tunnel
sops_refs:
  - docs/sops/external-dns.md
  - docs/sops/gateway-api-httproute.md
  - docs/sops/cloudflare.md
generated: "2026-09-09"
---

# Adopt the unowned public CNAMEs into the external-dns registry

Read `docs/sops/external-dns.md` (v2026.09.08) before executing. This plan does
not contradict it; §6.3 flags the one place where it needs a narrow amendment, and
that amendment is a step.

## 1. Diagnosis first — why the 8 are unowned

Four hypotheses were tested read-only on 2026-09-09 against the live zone, the
live Deployment args, and 30 h of controller logs.

| Hypothesis | Verdict | Evidence |
|---|---|---|
| A TXT exists under an **older prefix** and simply isn't matched | **FALSE** | All 31 TXT records in the zone were enumerated. There is **no** TXT of any shape — `k8s.cname-*`, `k8s.a-*`, bare `k8s.*` — for any of the 8. |
| Created by a **different owner id** (second external-dns, old K3s cluster) | **FALSE** | Every TXT in the zone carries `external-dns/owner=default`. There is no second owner value anywhere. |
| The **record pattern changed** (`k8s.a-*` → `k8s.cname-*`) | **Not the cause** | It *is* the cause of the `k8s.a-*` leftovers in §7, but the 8 have no TXT under either pattern. |
| Created **out-of-band, never seen by external-dns** | **TRUE** | All 8 were created 2025-04-19T23:34:30 → :34.19Z, ~0.55 s apart — a script or bulk import — with `modified_on == created_on`. The oldest external-dns-authored TXT in the zone is `k8s.a-auth` from 2025-10-05, six months later. |

### 1.1 The structural reason it will never self-heal

This is the part that matters, and it is not a one-off. **Corrected 2026-09-15
against `registry/txt/registry.go` at tag `v0.22.0`** (the version this plan
now runs on, via `depends_on`; the earlier text cited a `registry/txt.go` that
exists at neither tag, and claimed TXTs are written "only on `Create`"):
`ApplyChanges` (lines 358-403) generates ownership TXTs on **Create** (filtered
by `existingTXTs.isAbsent`), **Delete**, **UpdateOld** and **UpdateNew** — so
the registry *would* write a TXT on an update or delete of a record it
considers its own. The reason that never happens for our 8 is one step
earlier: `FilterEndpointsByOwnerID` drops an unowned record (owner label `""`
≠ `default`) from the `UpdateNew`, `UpdateOld` and `Delete` lists before they
reach the registry, and the `Create` list only carries records that do not
exist yet.

And because the 8 CNAMEs already match the desired state *exactly* — same
proxied CNAME to `external.${SECRET_DOMAIN}` — the plan emits **no change at
all**. The log has said `All records are already up to date` every 60 seconds for
30 hours straight. No change means no `Create`; an unowned record never enters
Update or Delete; which means no TXT, forever.

**There is no adopt-on-read path in v0.21 or v0.22.** This is a stable,
self-perpetuating state, not a transient one that a restart or a longer wait
would clear. Re-confirm the four `ApplyChanges` branches against that file on
execution day — the whole of Path A (§6.1) depends on the owner filter running
first.

### 1.2 The metric that hid it

`external_dns_controller_verified_records{record_type="cname"} = 25`, steady
(`min_over_time[24h] = 25`), and `external_dns_registry_errors_total = 0`. Both
look perfect. **`verified_records` counts the 7 unowned-but-live records as
verified** — it measures "the record matches what I want", not "I own it". That
is why 17 months of drift produced no signal.

Arithmetic that reconciles every number: 25 desired = 24 envoy-external HTTPRoute
hostnames + 1 `crd/network/cloudflared`; 25 = 18 owned + 7 unowned-but-live; the
zone holds 26 CNAMEs, and the 26th is `echo-server`, which is unowned **and**
sourceless. 7 + 1 = the 8.

> **Note for whoever maintains `sweep_findings`:** the title of `F-36a7105a` reads
> "**18 of 25** … carry no external-dns ownership record" and its detail says
> "7 owned, 18 unowned". Measured today it is the other way round: **18 owned, 7
> unowned-but-live** (plus sourceless echo-server). The finding's *conclusion* and
> its Action are right; the counts are inverted. This plan claims the finding and
> its body is the corrected measurement. Do not propagate the inverted figures.

## 2. Why this is deliberately NOT scheduled sooner

The 8 unowned records are currently **structurally immune to deletion** — that is
the flip side of the defect. On 2026-09-08 the owner filter is exactly what
saved them (§4).

**Adoption converts "silently unmanaged but immune" into "managed and therefore
deletable."** After this plan lands, `hass` and `flux-webhook` gain the same
failure mode the other 17 records already have. That is the correct trade — an
unowned record is also an unreapable one, so a route moving internal leaves a
dangling public hostname — but it is a trade, and it should be taken only once
the alerting that catches the new failure mode is trusted.

The six `ExternalDNSRegistryErrors`-class alert rules were added **2026-09-08**
(`b88109a2`), i.e. the day before this plan was written. `sat-attended:2026-10-03`
gives them 25 days of live operation before we hand them two hostnames whose loss
means "GitOps reconciliation-on-push is dead" and "Home Assistant remote access is
dead". Scheduling this into the next available slot would be optimising for queue
throughput against the one property that makes the change safe.

If the operator prefers the exposure gap closed sooner, the honest smaller
alternative is to adopt only the three least consequential hosts (`kuma`,
`open-webui`, `drive`) in an earlier window and keep `hass`/`flux-webhook` for
2026-10-03. Do not do the reverse.

## 3. What is being changed, and what is deliberately not

### 3.1 Adopt these 7 — each has a live envoy-external HTTPRoute

| Hostname | Source HTTPRoute | Parent Gateway |
|---|---|---|
| `drive` | `office/nextcloud` | envoy-external |
| `flux-webhook` | `flux-system/flux-webhook` | envoy-external |
| `hass` | `home-automation/home-assistant` | envoy-external |
| `kuma` | `monitoring/uptime-kuma` | envoy-external |
| `n8n` | `home-automation/n8n` | envoy-external |
| `open-webui` | `ai/open-webui` | envoy-external |
| `paperless` | `office/paperless-ngx` | envoy-external |

### 3.2 🚨 `echo-server` is EXCLUDED — adopting it would DELETE it

Its only HTTPRoute parents **`envoy-internal`**, which the
`--gateway-name=envoy-external` allowlist excludes by design. external-dns
therefore derives **no endpoint** for `echo-server.${SECRET_DOMAIN}`; the public
CNAME is a 2025-04-19 leftover with nothing behind it (edge-pinned probe returns
404 from envoy-external, which has no route for it).

Write a `k8s.cname-echo-server` TXT and the very next sync sees an **owned**
current record with **zero** desired candidates → `Delete` → the owner filter now
*passes* → CNAME and TXT both removed within ~60 s.

That outcome may well be what we want — the record is dead weight pointing into
the tunnel, which is what `F-6ed6d4ee` describes. **But it must be an explicit
operator decision, never a side effect of "adopt the 8."** Adopt 7. Put
echo-server to the operator as a separate yes/no in the window, and if the answer
is "remove it", removing the CNAME directly is clearer than adopting it in order
to make external-dns remove it.

## 4. The 2026-09-08 outage — the mechanism this plan sequences around

Reconstructed from git and Cloudflare `created_on`, all UTC:

- **05:43:51** `31f876fc` pinned the external-dns image v0.21.0 → v0.22.0.
- v0.22.x stops honouring `external-dns.alpha.kubernetes.io/target` on the parent
  Gateway and publishes the Gateway's own address — `192.168.55.104`, a private
  A record. **Under `--policy=sync` a changed record is applied delete-then-create,
  and the delete lands first.** Cloudflare then rejected the create with
  `9003 / "Target is not allowed for a proxied record"`. The old record was
  already gone.
- **A failed create is not a no-op — it is an outage.** 17 hostnames were publicly
  unresolvable.
- **05:45:08** `aa79cf7a` reverted. **05:45:53** all 17 CNAMEs and their 17
  `k8s.cname-*` TXTs were recreated in one atomic batch. ~94 s end to end.

Blast radius was exactly the **17 owned `gateway-httproute` records**. The
CRD-sourced `external` record survived (its target is the `cfargotunnel.com`
hostname, unaffected by the Gateway-address regression) — and **the 8 unowned
records survived only because `FilterEndpointsByOwnerID` dropped them from
`Delete`.** Their `modified_on` is still 2025-04-19.

**The sequencing rule this dictates: never let this plan cause external-dns to
emit a `Create` for a CNAME that still exists.** That is the entire reason §6
takes Path A.

## 5. Pre-checks

Run these in the window, before the backup_gate and before any write. The gate
proves the *rollback source* is good; this section proves the *cluster* is in a
safe pre-state. Both are required.

```bash
cd /Users/mu/code/cberg-home-nextgen

# 5.0.1 external-dns is healthy and quiescent — not mid-reconcile, not erroring
mise exec -- kubectl -n network get deploy external-dns
mise exec -- kubectl -n network logs deploy/external-dns --tail=40
# EXPECT: `All records are already up to date` on the last reconciles, no
# `Failed to submit all changes`, no Cloudflare error codes.

# 5.0.2 The live config still matches what §1 was diagnosed against.
# If ANY of these drifted since 2026-09-09, re-do the §1 diagnosis first —
# the whole of Path A depends on policy=sync + txt registry + owner id `default`.
mise exec -- kubectl -n network get deploy external-dns \
  -o jsonpath='{.spec.template.spec.containers[0].args}' | tr ',' '\n'
# EXPECT: --policy=sync, --registry=txt, --txt-owner-id=default,
#         --txt-prefix=k8s., sources WITHOUT `ingress`.

# 5.0.3 Every hostname being adopted still has its live source route.
# A hostname whose HTTPRoute vanished since §3.1 must be DROPPED from this run —
# adopting a sourceless record makes the next sync DELETE it (the echo-server
# trap in §3.2, which is the single most dangerous mistake available here).
mise exec -- kubectl get httproutes -A -o json | .venv/bin/python3 -c "
import sys, json
want = {'drive','flux-webhook','hass','kuma','n8n','open-webui','paperless'}
seen = {}
for r in json.load(sys.stdin)['items']:
    parents = [p.get('name') for p in r['spec'].get('parentRefs', [])]
    for h in r['spec'].get('hostnames', []):
        label = h.split('.')[0]
        if label in want:
            seen.setdefault(label, []).append(
                (r['metadata']['namespace'] + '/' + r['metadata']['name'], parents))
for h in sorted(want):
    print(h, seen.get(h, 'MISSING — DROP FROM THIS RUN'))
"
# EXPECT all 7 present AND parented by envoy-external. A route parented only by
# envoy-internal is the echo-server shape — exclude it.

# 5.0.4 Cluster is otherwise quiet
mise exec -- flux get kustomizations -A | awk 'NR==1 || $5 != "True"'
mise exec -- kubectl -n network get gateway envoy-external -o wide

# 5.0.5 Capture the pre-adoption public baseline (this is the §8.2 comparison set)
# Edge-pinned — see §8.1 for why a plain curl from the LAN measures nothing.
```

Record the §8.2 status codes for all 7 hosts here, before writing anything. A
verification with no pre-baseline cannot distinguish "still working" from "was
already broken".

## 6. Steps

### 6.1 Path A — write the ownership TXTs out-of-band (zero CNAME churn)

For an unowned record, `Create` is the only TXT-writing path the controller can
reach (Update/Delete are owner-filtered before the registry sees them, §1.1),
and no `Create` will ever be emitted while the CNAME already matches desired
state. So write the TXT directly. On the next
`Records()` the label attaches, desired still equals current, and the controller
stays on `All records are already up to date`. **The CNAME is never read for
change, never deleted, never recreated** — the delete-then-create mechanism from
§4 is never entered at all.

Exact record shape, copied from the live `k8s.cname-jellyfin`:

```
type     TXT
name     k8s.cname-<host>.${SECRET_DOMAIN}
content  "heritage=external-dns,external-dns/owner=default,external-dns/resource=httproute/<ns>/<route-name>"
ttl      1        (auto)
proxied  false
```

Use the namespace/route-name pairs from §3.1 verbatim.

**Order — one at a time, least consequential first, verifying between each:**
`kuma` → `open-webui` → `drive` → `paperless` → `n8n` → **`hass`** →
**`flux-webhook`**. Stop at the first host that does not verify. Adopting seven
in a batch means a systematic mistake (see the silent-failure mode below) lands
on all seven before anything is checked.

**Silent-failure mode to guard against:** the heritage string must parse exactly.
If `NewLabelsFromString` returns `ErrInvalidHeritage`, external-dns treats the
record as a plain unowned TXT endpoint — **adoption fails with no error, no log
line, and a TXT sitting in the zone that looks right.** This is why §8's
verification reads ownership behaviour and not merely "the TXT exists".

**Path B (rejected, recorded so it is not re-proposed):** delete the CNAME to
force external-dns to recreate it with a TXT. It guarantees a correct pair within
≤60 s, and it is a deliberate public NXDOMAIN window per hostname — on `hass` and
`flux-webhook` among others. It is Path A's failure mode, chosen on purpose.

**Anti-pattern, explicitly:** do not do anything that makes external-dns emit a
`Create` for a CNAME that still exists. Cloudflare answers `81053 record already
exists`, which increments `external_dns_registry_errors_total` and fires
`ExternalDNSRegistryErrors` at **critical** — an alert whose documented meaning is
"active public-DNS outage". A false page on that rule in its third week burns its
credibility permanently.

### 6.2 Pin `registry: txt` in the HelmRelease (same window, its own commit)

`--registry=txt` currently comes from the **chart default**; it is not pinned in
`kubernetes/apps/network/external/external-dns/helmrelease.yaml`. Under
`--policy=sync`, a chart-side change of that default would orphan the entire
registry silently — the same class of failure this plan exists to fix, at 25×
the scale. Pin it explicitly. Run this ONLY after all seven adoptions have
verified, and never split the adoptions across it: it creates a new Helm
revision, and the soak premise deliberately reads the EARLIEST 1.22.0
lastDeployed so that this pin cannot reset the soak (2026-09-23 review).

```bash
mise exec -- task kubeconform
git commit --only kubernetes/apps/network/external/external-dns/helmrelease.yaml -F /tmp/msg.txt
git show --stat HEAD     # every file must be yours — shared worktree
git push
```

### 6.3 Amend `docs/sops/external-dns.md` with a narrow carve-out

SOP §5 Example C says: *"❌ creating a record by hand in the Cloudflare UI —
deleted at next reconcile."* That is correct for **data** records, which `sync`
reaps. It is **not** correct for a well-formed **registry TXT**, which becomes the
ownership marker and is not reaped.

Left unamended, the SOP tells the next reader that this plan's central step is
forbidden — and they would be right to refuse to execute it. Add a carve-out
naming registry-TXT backfill specifically, bounded to correctly-formed
`k8s.cname-*` records for hostnames that already have a live source object.
Commit separately with `--only`.

## 7. The leftovers — an explicit decision to LEAVE them

Confirmed present and confirmed unreconcilable:

- **4 ingress-era `k8s.a-*` orphans:** `k8s.a-auth` (2025-10-05), `k8s.a-penpot`
  (2026-01-06), `k8s.a-traccar` (2026-03-22), `k8s.a-rainbow-rescue` (2026-05-06)
  — each labelled `resource=ingress/...`.
- **9 legacy pre-v0.12 `k8s.<host>` TXTs:** `k8s.auth`, `k8s.external`,
  `k8s.jellyfin`, `k8s.langfuse`, `k8s.music-api`, `k8s.music-stream`,
  `k8s.penpot`, `k8s.tube-archivist`, `k8s.whiteboard`.

Unreconcilable, verified: `kubectl get ingress -A` → *No resources found*;
`kubectl get ingressclass` → *No resources found*; `ingress` is not in `--source`.
In `Records()` these are consumed into the label map under a key whose record type
is `A` (for `k8s.a-*`) or `""` (legacy), while every live endpoint is `CNAME`, and
the new-format `k8s.cname-*` TXT takes precedence in the fallback lookup. They
attach to nothing, never enter `Create` or `Delete`, and are never garbage
collected. Empirical proof: they sat untouched through the entire 2026-09-08
delete-and-recreate cycle.

> **OPERATOR DECISION, RECORDED 2026-09-09: LEAVE ALL 13 IN PLACE.**
> They are inert noise. Deleting them is a manual out-of-band write against the
> public zone for zero functional benefit, and every such write is an opportunity
> to fat-finger a live record. **Do not re-propose removing them.** If a future
> sweep finding surfaces them again, this paragraph is the answer.

One record outside all of the above, flagged for completeness and **not in
scope**: `ui.${SECRET_DOMAIN}`, an `A` record, `proxied=false`, modified
2026-09-06, with no TXT and no cluster source object. It is not external-dns's and
this plan does not touch it.

## 8. Verification

### 8.1 The trap that invalidates the obvious probe

**A plain `curl https://<host>.${SECRET_DOMAIN}/` from a LAN machine does NOT
test the public path.** The LAN resolver (AdGuard / k8s-gateway) answers
`${SECRET_DOMAIN}` internally and sends you to `envoy-internal` at
192.168.55.103. Caught live on 2026-09-09: `curl https://echo-server.…/` returned
**200** with `x-forwarded-for` set to the Mac's own LAN IP — a purely internal
round trip — while the same host pinned to the Cloudflare edge returns **404**.
The SOP warns about this for `dig`; it applies to `curl` just as hard.

### 8.2 Assertions

```
CONTENTS ASSERTION 1 — ownership is REAL, not merely present.
  After each adoption, assert external-dns now treats the record as owned:
  the k8s.cname-<host> TXT exists in the zone AND its heritage string parses
  (owner=default, resource=httproute/<ns>/<name> matching §3.1) AND the
  controller log still reads `All records are already up to date` on the next
  two reconciles with external_dns_registry_errors_total unchanged at 0.
  "The TXT exists" alone is the shape check that ErrInvalidHeritage passes.
  DISCRIMINATOR (added 2026-09-23 review): the log line and errors_total above
  ALSO pass on the silent ErrInvalidHeritage case, so on their own they cannot
  fail on the failure this assertion exists to catch. The one scraped
  observable that separates adoption from non-adoption is
  external_dns_registry_endpoints_total (controller.go:83 = len(regRecords);
  registry.go:226-230 appends a NON-parsing TXT to the endpoint list instead of
  consuming it into the label map). Record it before the first write —
  baseline measured 2026-09-23: 27 (26 CNAME + 1 A, all 31 TXTs consumed).
  After each adoption wait >= 2 reconciles (>= 2 min) and assert it is EXACTLY
  the baseline; 28 means the TXT came back as an unowned plain endpoint →
  delete that TXT, fix the string, retry. Per-host and API-free:
  `dig +short @1.1.1.1 TXT k8s.cname-<host>.$D` prints the heritage string
  once written and nothing before.

CONTENTS ASSERTION 2 — the hostname still resolves and routes PUBLICLY.
  Edge-pinned, per host, before and after:
    dig +short @1.1.1.1 $H.$D            # expect Cloudflare anycast answers
    curl -s -o /dev/null -w '%{http_code}\n' --max-time 12 \
         --resolve $H.$D:443:<cf-edge-ip> https://$H.$D/
  Baseline measured 2026-09-09 (edge-pinned):
    drive 302 · flux-webhook 404 · hass 200 · kuma 302 · n8n 200 ·
    open-webui 200 · paperless 302
  flux-webhook's 404 at `/` is CORRECT — its route is PathPrefix `/hook/`.
  Probe https://flux-webhook.$D/hook/ (expect a 404 from the receiver, not a
  Cloudflare 1016 or a 000), or treat "resolves + `server: cloudflare`" as the
  pass. Every post-adoption code must equal its pre-adoption code.

CONTENTS ASSERTION 3 — flux-webhook still delivers, not merely answers.
  After adopting flux-webhook, push a trivial commit and confirm Flux reconciles
  on the webhook rather than on the interval:
  `kubectl -n flux-system get gitrepository flux-system -o jsonpath='{.status.lastHandledReconcileAt}'`
  must advance within seconds of the push (corrected 2026-09-23: the Receiver's
  own status carries only conditions/observedGeneration/webhookPath — the
  field that moves on a webhook is on the GitRepository). An HTTP code proves
  the name resolves; it does not prove GitOps
  reconciliation-on-push survived, which is the entire reason this hostname
  matters.

NEGATIVE CONTROL — proves a "success" could have failed:
    dig @1.1.1.1 nx-probe-9f3a.$D A | grep -E 'status:|ANSWER: '
    curl -s -o /dev/null -w '%{http_code}\n' --max-time 10 https://nx-probe-9f3a.$D/ ; echo "exit=$?"
  Measured: `status: NOERROR, ANSWER: 0` and `http=000 exit=6`.
  DISCRIMINATE ON `ANSWER: 0`, NOT ON THE RCODE — Cloudflare returns NODATA, not
  NXDOMAIN, so a negative control written as `grep NXDOMAIN` silently never
  fires and every probe "passes". curl exit 6 is the clean binary signal.
  Run this control in the SAME session as the positive probes; a control run
  from a different resolver proves nothing about the run that mattered.
```

Then run `health-check-agent` and `security-agent`.

## 9. Rollback

Per-host and immediate: **delete the `k8s.cname-<host>` TXT just written.** The
record returns to unowned — byte-identical to its 2025-04-19 state, since the
CNAME was never touched. Verify with the §8.2 probe for that host and with
`external_dns_registry_errors_total` still at 0.

If a CNAME is somehow lost despite Path A never emitting a Create, recreate it
from the §backup_gate zone export using the reconstructed API call proved in gate
(c). This is the only reason that gate exists and the only reason it demands a
*usable* export rather than a saved response body.

`git revert` covers §6.2 and §6.3, which are ordinary manifest/doc commits.

## 10. Interference notes for the window agent

- **Must NOT share a window with `wazuh-2xx-edge-coverage`.** Both perturb the
  external request/name path; a failure in either would be misattributed to the
  other, and that plan currently proposes `sat-attended:2026-09-26` while this
  one proposes `sat-attended:2026-10-03`. This is stated here rather than in
  `conflicts_with:` because that plan is `draft` — promote it to a real
  `conflicts_with` pair when either is vetted, and do not leave a forward
  reference to a plan_id that has not been confirmed to exist.
- **Do not co-schedule with any cert-manager, Cloudflare-tunnel, or Gateway API
  change** for the same reason.
- **Attended, and needs someone who can probe from off-LAN** — §8.1 makes an
  on-LAN-only verification meaningless.
- **Not reboot work.** `needs_reboot: false`; it must not consume the Sunday
  reboot-capable slot, and specifically not `sun-attended:2026-09-27`
  (140 of 150 min already committed to `talos-1.14.0`).
- **The window's risk is concentrated in two hostnames**, not in the change size.
  Losing `flux-webhook` breaks GitOps reconciliation-on-push; losing `hass`
  breaks Home Assistant remote access. Both are adopted LAST, deliberately, so
  that five successful adoptions have already validated the procedure before
  either is touched.

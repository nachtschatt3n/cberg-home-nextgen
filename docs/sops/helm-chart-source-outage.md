# SOP: Third-Party Chart Source Outage — when one upstream host freezes GitOps cluster-wide

> Description: Diagnosis and remedy for an unreachable third-party Helm chart index or git chart source that sits inside `cluster-meta`'s `wait: true` health gate, which stalls `cluster-apps` reconciliation for EVERY app while nothing is actually degraded.
> Version: `2026.09.20`
> Last Updated: `2026-09-20`
> Owner: `Platform`

---

## 1) Description

A chart source we do not own — a Helm `index.yaml` on someone's GitHub Pages
site, or a chart directory in someone's git repo — can stop GitOps delivery for
the **whole cluster**. Not the app that uses the chart: the whole cluster.

The mechanism is structural, not a bug:

- every `HelmRepository` / `GitRepository` lives under `./kubernetes/flux/meta`,
- `cluster-meta` reconciles that path with **`spec.wait: true`**, so it health-gates
  every object in its own inventory,
- `cluster-apps` carries **`dependsOn: cluster-meta`**.

So that third party's DNS, TLS and hosting availability is a hard dependency of
every deployment in this cluster. **Measured live 2026-09-20:** `cluster-meta`
holds **44 inventory entries — 40 `HelmRepository`, 3 `GitRepository`, 1 Secret**.

**But the exposed set is 33, not 44, and the difference is the whole argument
for OCI.** Of those 40 HelmRepositories, **10 are `type: oci` and carry
`status: {}` — no conditions at all**, because source-controller never fetches
an index for them: they are static references resolved at chart-pull time. They
have no reconcile loop, so they cannot go not-Ready and cannot stall the gate.
The remaining **30 are plain HTTP chart indexes** on hosts we do not control,
plus **3 `GitRepository`** objects. Any one of those 33 can freeze the cluster.

- Scope: `flux-system` sources, `cluster-meta` / `cluster-apps` Kustomizations
- Prerequisites: `kubectl` + `flux` via mise; repo write access; `curl`
- Out of scope: the *revision* churn that makes unrelated Kustomizations blink
  not-Ready after a push — that is benign and self-resolving, and it is a
  different document: `docs/sops/flux-dependency-revision-gate.md`.

**This has happened twice, from two different upstream causes:**

| Date | Source | Upstream cause | Blast radius |
|---|---|---|---|
| 2026-09-11 | `HelmRepository/k8s-gateway` | Pages index **deleted**, 404 (not redirected) | ~90 min, no commit could deploy |
| 2026-09-17 | `HelmRepository/rm3l` | custom domain repointed off Pages, **TLS never configured** — handshake returns zero bytes | stalled from 22:43Z; blocked the 2026-09-18 nightly window's Step 0 |

Findings `F-e2e1605a` (the outage) and `F-e166e134` (this SOP's gap). The
strategic remediation — migrating sources to immutable OCI and moving the rest
out of the gate — is a planned programme, not an incident action:
`runbooks/maintenance/plans/flux-oci-chart-sources.md`.

## 2) Overview

| Setting | Value |
|---------|-------|
| Gate | `Kustomization/flux-system/cluster-meta`, `spec.wait: true` |
| Gate path | `./kubernetes/flux/meta` |
| Gate timeout | **unset → defaults to `spec.interval`, i.e. 30m** (measured failure at 29m30s) |
| Blocked by it | `Kustomization/flux-system/cluster-apps` (`dependsOn: cluster-meta`) → every app |
| Source of truth | `kubernetes/flux/meta/repositories/{helm,git,oci}/*.yaml` |
| Detection | `FluxResourceNotReady` (`platform-alerts.yaml`, `for: 15m`, severity warning) |

**The two facts that make this hard to read correctly:**

**(a) Nothing is degraded.** Every workload keeps running. The cached chart
artifact in `source-controller` keeps serving, so existing HelmReleases stay
Ready. Dashboards are green, users notice nothing. What is dead is **delivery** —
and delivery is invisible until you try to ship something, or until the nightly
maintenance window tries to apply Step 0 and cannot.

**(b) Flux can then neither APPLY nor REVERT — for apps.** This is the trap. The
instinct on a stalled cluster is "revert the last commit", and for anything under
`./kubernetes/apps` that does nothing at all: `cluster-apps` is
`DependencyNotReady`, so it will not apply your revert any more than it applied
the change. The revert is just another revision waiting behind the same gate.
Pushing more commits does not help and makes the history harder to read.

**The one lane that still moves is `./kubernetes/flux/meta`.** A Flux
Kustomization **applies its manifests first and health-gates afterwards**, so
`cluster-meta` still applies changes to its own path while its gate is failing.
That is not theory: the 2026-09-17 stall was cleared by a commit that edited
exactly one file in that path, and both Kustomizations returned to Ready at that
revision. **Fixing the source is therefore the only action that can land during
the stall — which is why it is the whole remedy below.**

## 3) Blueprints

- Source of truth: `kubernetes/flux/meta/repositories/helm/*.yaml`,
  `kubernetes/flux/meta/repositories/git/*.yaml`
- Gate definition: `kubernetes/flux/cluster/ks.yaml`
- Worked example of the remedy, with its reasoning preserved in-file:
  `kubernetes/flux/meta/repositories/helm/rm3l.yaml`
- The other shape (commit-pinned git source): `kubernetes/flux/meta/repositories/git/csi-driver-smb.yaml`

```yaml
# The remedy applied on 2026-09-18: same chart, host-independent index.
# gh-pages is served by raw.githubusercontent, and — critically — this index's
# tarball URLs are GitHub RELEASE assets, not back-references to the dead host.
spec:
  interval: 60m
  url: https://raw.githubusercontent.com/rm3l/helm-charts/gh-pages
```

> **Always leave the reasoning in the manifest.** These files carry a header
> comment recording what broke, why this URL was chosen, what was rejected and
> what would revert it. A bare URL swap with no comment loses the finding, and
> the next person re-derives it under pressure.

## 4) Operational Instructions

### Step 1 — Confirm it is this failure, not the benign revision gate

```bash
mise exec -- kubectl get kustomization -n flux-system cluster-meta \
  -o jsonpath='{range .status.conditions[?(@.type=="Ready")]}{.status} {.reason} {.message}{"\n"}{end}'
```

`False` + `HealthCheckFailed` naming a source (e.g.
`timeout waiting for: [HelmRepository/flux-system/rm3l status: 'InProgress']`)
== this SOP. Anything naming a *dependency revision* is the benign gate — go to
`docs/sops/flux-dependency-revision-gate.md` instead.

### Step 2 — Identify the failing source and read its actual error

Read this from the **API**, not from `flux get` table columns — see the trap in
§9, which false-flags 10 healthy sources on this cluster:

```bash
mise exec -- kubectl get helmrepositories,gitrepositories,ocirepositories -A -o json \
  | .venv/bin/python3 -c "
import sys, json
d = json.load(sys.stdin)
bad = []
for i in d['items']:
    sp, md = i.get('spec', {}), i['metadata']
    if sp.get('suspend'):
        continue
    # type: oci HelmRepositories are static refs: status is {} and never fetches
    if i['kind'] == 'HelmRepository' and sp.get('type') == 'oci':
        continue
    ready = next((c for c in (i.get('status', {}).get('conditions') or []) if c['type'] == 'Ready'), None)
    if ready is None or ready['status'] != 'True':
        bad.append(f\"{i['kind']}/{md['namespace']}/{md['name']}: {(ready or {}).get('reason', 'NoReadyCondition')} {(ready or {}).get('message', '')}\")
print('\n'.join(bad) if bad else 'all reconciling sources Ready')"
```

### Step 3 — Establish whether upstream is transiently down or permanently moved

**This decides everything downstream, so do not skip it.** A 30-minute blip is
worth waiting out; a migration never clears on its own.

```bash
curl -sS -o /dev/null -w '%{http_code} %{ssl_verify_result}\n' https://<chart-host>/index.yaml
dig +short <chart-host>            # resolving to a non-Pages IP => repointed, not down
```

- TLS handshake returns nothing / "no peer certificate available", **and** the
  host resolves somewhere new → **migration. It will not self-heal. Fix it now.**
- 5xx or timeout from the usual IPs → possibly transient; you may wait, but set a
  deadline (see Step 4's clock).

### Step 4 — Know your clock

You get a **~15-minute head start**: `FluxResourceNotReady` fires at `for: 15m`
on the source, while `cluster-meta`'s gate does not time out until ~30m. Acting
inside that window prevents the cluster-wide stall rather than recovering from
it. If a nightly maintenance window is near, treat it as urgent — a stall at
03:30 aborts Step 0 and the whole window.

### Step 5 — Choose the remedy, in this order

1. **Repoint to a host-independent index for the same chart** — preferred, proven.
   Usually the upstream `gh-pages` branch via `raw.githubusercontent.com`.
   **Must pass the tarball check in §6 Test 2.**
2. **Commit-pinned `GitRepository`** — when no usable index exists. Strongest
   integrity (content-addressed), but **forfeits Renovate tracking**, so upgrades
   become manual. Shape and full trade-off: `csi-driver-smb.yaml`.
3. **Delete the source** — only if genuinely unreferenced. Free and permanent.
4. **Move the source out of the gate, and/or migrate it to OCI** — the
   structural fix, and the strongest one: a source in the app's own folder can
   only break its own app, and a `type: oci` HelmRepository / `OCIRepository`
   has **no index fetch to fail** (§1 — those objects carry `status: {}`), so it
   removes the failure mode rather than relocating it. This is the direction of
   `flux-oci-chart-sources.md`; do it as planned work, not mid-incident.

**Do NOT** mass-`flux reconcile` the blocked Kustomizations — they are waiting on
a gate, not a trigger. **Do NOT** push app-side reverts hoping to unstick it (see
§2b). **Do NOT** vendor the chart into this repo — explicitly rejected by the
operator on maintenance-burden grounds.

> **`suspend: true` on the failing source is NOT a verified escape.** It silences
> `FluxResourceNotReady` (the alert excludes suspended), but whether it clears
> `cluster-meta`'s kstatus health gate has never been measured here. If you try
> it, verify `cluster-meta` actually returns Ready within one interval and have a
> real fix ready — do not assume the gate cleared because the alert went quiet.

### Step 6 — Ship it

Edit the manifest under `kubernetes/flux/meta/...`, commit and push per
`AGENTS.md` ("Committing in a SHARED worktree" — use `git commit --only`).
`cluster-meta` applies its own path even while gated, so the fix lands.

## 5) Examples

### Example A: host migrated, TLS never configured (2026-09-17, rm3l)

Upstream moved `helm-charts.rm3l.org` off GitHub Pages; DNS resolved, TCP 443
accepted, the handshake returned zero bytes. The domain was registered and
"active", and the repo's Pages config still claimed the custom domain — so every
surface said healthy. **It was a migration, not an outage**, and would never have
cleared. Remedy: option 1, repoint at the `gh-pages` index.

Two traps that decided which URL to use, both worth reusing:

- `rm3l.github.io/helm-charts/index.yaml` is **not** a valid fallback: Pages has
  `https_enforced` with the custom domain set, so it 301-redirects straight back
  to the broken host.
- The chart had **no OCI artifact** (upstream request still open), so option 4
  was unavailable.

### Example B: index deleted rather than redirected (2026-09-11, k8s-gateway)

Upstream deleted the Pages index; it 404'd. ~90 minutes with no deployable
commit. Resolved by migrating that chart to an `OCIRepository` (`43a3b3e4`, digest
pinned in `0c77bbb0`) — i.e. option 4, taken permanently.

**The near-miss is the lesson here.** `source-controller` stores artifacts in an
**`emptyDir` with no `sizeLimit`**, and the chart tarball existed only in that
cache. One eviction, node drain or Talos roll and internal DNS would have been
unrecoverable — not merely unreconcilable. **A cache is not durability**: what
makes a chart recoverable is the source being alive and immutable.

## 6) Verification Tests

### Test 1: the gate is clear and the whole tree converged

```bash
REV=$(mise exec -- kubectl get gitrepository -n flux-system flux-system \
        -o jsonpath='{.status.artifact.revision}')
mise exec -- kubectl get kustomization -n flux-system cluster-meta cluster-apps \
  -o jsonpath='{range .items[*]}{.metadata.name} {.status.conditions[?(@.type=="Ready")].status} {.status.lastAppliedRevision}{"\n"}{end}'
echo "want both True at: $REV"
```

Expected:
- both `True`, both at the GitRepository's fetched revision.

If failed:
- re-read `cluster-meta`'s Ready message; a *different* source may now be failing.

### Test 2: the swap was a SOURCE change, not a CONTENT change

**Run this before trusting any re-pointed index.** It is what makes option 1 safe:
it proves you changed where the chart comes from, not which chart you run.

```bash
# a) the index's tarball URLs must NOT point back at the failed host
curl -sS https://<new-index-host>/<path>/index.yaml | grep -A3 'urls:' | head
# b) the tarball's sha256 must equal the digest the index advertises
curl -sSL -o /tmp/chart.tgz '<tarball-url-from-index>'
shasum -a 256 /tmp/chart.tgz
```

Expected:
- tarball URLs resolve to a host independent of the failed one (GitHub **Release**
  assets are ideal — they do not depend on the Pages site at all);
- computed sha256 **equals** the index's `digest` for that version, and matches
  the chart the cluster already runs.

If failed:
- **stop.** A different digest means different bytes, which is a chart upgrade
  wearing the costume of an outage fix. Use option 2 (commit-pinned git) instead.

> **The inverse trap — verified on `csi-driver-smb`.** An index can hardcode
> ABSOLUTE tarball URLs back to the original host or a mutable branch. Then
> re-pointing the index pins nothing: you fetch the *index* from the new place
> and the *chart* from the old broken one. Check (a) every time, including on
> future chart bumps of an already-fixed source.

## 7) Troubleshooting

| Symptom | Likely Cause | First Fix |
|---|---|---|
| `cluster-meta` `HealthCheckFailed` naming a source | this SOP — unreachable third-party source | §4 Step 2 |
| `cluster-apps` `DependencyNotReady`, nothing else wrong | downstream of the above; not its own fault | fix `cluster-meta`, never debug `cluster-apps` |
| Pushed a revert, nothing happened | app-path commits are gated (§2b) | fix the source under `./kubernetes/flux/meta` instead |
| Apps all healthy, so "nothing is wrong" | cached artifacts mask a delivery stall | check `cluster-apps` `lastAppliedRevision` vs HEAD |
| Maintenance window aborted at Step 0 | gate was stalled at 03:30 | this SOP, then re-run the window |
| Source Ready again but tree still lagging | normal revision convergence | `docs/sops/flux-dependency-revision-gate.md` |
| Fixed once, same host breaks again | it is a mutable third-party URL | escalate to options 2/4 permanently |

## 8) Diagnose Examples

### Diagnose Example 1: what exactly is inside the gate

```bash
mise exec -- kubectl get kustomization -n flux-system cluster-meta -o json \
  | .venv/bin/python3 -c "
import sys, json, collections
d = json.load(sys.stdin)
inv = (d.get('status', {}).get('inventory') or {}).get('entries') or []
print('entries:', len(inv))
for k, v in collections.Counter(e['id'].split('_')[-1] for e in inv).most_common():
    print(' ', k, v)"
```

Expected:
- the failing object appears here. **If it does not, it is not the cause of the
  stall** — cluster-meta only gates its own inventory.

### Diagnose Example 2: is the upstream host down, or gone?

```bash
dig +short <chart-host>
curl -sSv https://<chart-host>/index.yaml 2>&1 | head -20
```

Expected:
- GitHub Pages serves from `185.199.108-111.153`. **A different IP with a broken
  handshake means the domain was repointed and TLS was never configured** —
  permanent, fix now.

If unclear:
- compare against a known-good peer (`curl -sS -o /dev/null -w '%{http_code}\n'
  https://charts.longhorn.io/index.yaml`) to rule out a local egress/DNS fault.

## 9) Health Check

```bash
# 1) No reconciling source is failing (see the trap below — use the API)
mise exec -- kubectl get helmrepositories,gitrepositories,ocirepositories -A -o json \
  | .venv/bin/python3 -c "
import sys, json
d = json.load(sys.stdin)
bad = []
for i in d['items']:
    sp, md = i.get('spec', {}), i['metadata']
    if sp.get('suspend'):
        continue
    if i['kind'] == 'HelmRepository' and sp.get('type') == 'oci':
        continue
    ready = next((c for c in (i.get('status', {}).get('conditions') or []) if c['type'] == 'Ready'), None)
    if ready is None or ready['status'] != 'True':
        bad.append(f\"{i['kind']}/{md['namespace']}/{md['name']}: {(ready or {}).get('reason', 'NoReadyCondition')}\")
print('\n'.join(bad) if bad else 'all reconciling sources Ready')"

# 2) The gate and the tree are Ready
mise exec -- kubectl get kustomization -n flux-system cluster-meta cluster-apps \
  -o jsonpath='{range .items[*]}{.metadata.name}={.status.conditions[?(@.type=="Ready")].status} {end}{"\n"}'
```

Expected:
- `all reconciling sources Ready` from (1); `cluster-meta=True cluster-apps=True` from (2).

> **Do NOT health-check this with `flux get sources helm -A | awk '$5!="True"'`.**
> Measured 2026-09-20: it reports **10 false positives**, every one of them a
> healthy source whose own MESSAGE column reads `Helm repository is Ready`.
> Two independent reasons, and the second defeats a naive API check too:
>
> 1. **Column shift.** A `type: oci` HelmRepository has an empty REVISION cell,
>    so awk's whitespace splitting collapses the field and `$5` lands on the
>    first word of MESSAGE — the literal string `Helm`, which is `!= "True"`.
> 2. **No conditions at all.** Those same objects have `status: {}`, so testing
>    `Ready != True` against the API flags them too. They must be **skipped**,
>    not evaluated: nothing fetches them, so there is nothing to be not-Ready.
>
> A check that cries wolf on 10 healthy sources is worse than no check — it
> trains you to ignore the one real failure. Same rule as
> `flux-dependency-revision-gate.md` §4: measure from the API, never from
> formatted CLI output.

`FluxResourceNotReady` (`for: 15m`) covers this continuously and fires **before**
the gate times out. **Delivery health is not workload health** — green apps prove
nothing here, so check (2) explicitly after any source change.

## 10) Security Check

```bash
# The source must be HTTPS and its host deliberate — never a redirect to an
# unexpected origin, which would silently move the trust root.
grep -rn "url:" kubernetes/flux/meta/repositories/ | grep -v "https://\|oci://"
curl -sSL -o /dev/null -w '%{url_effective}\n' https://<chart-host>/index.yaml
```

Expected:
- no plaintext-HTTP sources;
- the effective URL is the host you intended (a 301 to a third party is a trust
  change, not a convenience);
- after any source swap, §6 Test 2's digest match — proving the bytes did not
  change with the host.

**Re-pointing a chart source moves who supplies code that runs in this cluster.**
Prefer the project's own canonical distribution point; a re-publisher is a
different trust decision that should be taken deliberately, not during an
incident.

## 11) Rollback Plan

```bash
# Revert the source manifest to the previous URL/ref and push.
# This path is NOT gated (cluster-meta applies its own path), so it lands
# even while the gate is failing.
mise exec -- kubectl get kustomization -n flux-system cluster-meta \
  -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}{"\n"}'
```

Rolling back is safe **only if the original host recovered** — reverting to a
still-dead host re-creates the stall. The rm3l manifest records the trigger for
its own revert ("once upstream restores TLS"); keep that convention.

If the source cannot be made Ready by any option in §4 Step 5 and the cluster
must ship, removing the object from `./kubernetes/flux/meta` clears the gate —
at the cost of that one app becoming unreconcilable. That is a deliberate,
recordable trade (one app frozen instead of all of them), never a silent cleanup.

## 12) References

- `kubernetes/flux/meta/repositories/helm/rm3l.yaml` — the worked remedy
- `kubernetes/flux/meta/repositories/git/csi-driver-smb.yaml` — commit-pinned shape + the index back-reference trap
- `kubernetes/flux/cluster/ks.yaml` — the gate itself
- `runbooks/maintenance/plans/flux-oci-chart-sources.md` — the permanent fix, in stages
- `docs/sops/flux-dependency-revision-gate.md` — the benign look-alike
- `docs/sops/maintenance-windows.md` — why a stall aborts Step 0
- Findings `F-e2e1605a` (outage), `F-e166e134` (this SOP), `F-0e310ef2`, `F-764e4fc3`

## Version History

- `2026.09.20`: Created. Written after the 2026-09-17 rm3l TLS migration stalled
  cluster-wide reconciliation and blocked the 2026-09-18 nightly window's Step 0
  (`F-e166e134`), which was the second instance of the shape after the
  2026-09-11 deleted-index incident. Records the mechanism (a third party's
  availability inside `cluster-meta`'s `wait: true` gate), the non-obvious fact
  that Flux can then neither apply nor revert app changes while
  `./kubernetes/flux/meta` still lands, and the digest check that makes a source
  swap provably a source change rather than a content change.

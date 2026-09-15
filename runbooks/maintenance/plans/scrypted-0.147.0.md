---
plan_id: scrypted-0.147.0
component: scrypted
pr: null                          # no Renovate PR (verified 2026-09-15:
                                  # `gh pr list --state all --limit 200 --search scrypted`
                                  # returns nothing). coverage.py direct-bump lane, held
                                  # to PLAN by the channel gate. The bump is made by hand.
kind: image
current: "v0.145.0-noble-full"    # verified live 2026-09-15: deploy/scrypted image AND
                                  # running imageID docker.io/koush/scrypted@sha256:294be875…
target: "v0.147.0-noble-full"     # GitHub Release prerelease=false, published
                                  # 2026-09-13T18:51:39Z, is `releases/latest`; Hub tag
                                  # pushed 2026-09-13T19:13:40Z, index sha256:e78b4fce…,
                                  # amd64 sha256:57a42bb8… (1.07 GB). Manifest HTTP 200.
update_type: minor
risk: medium                      # see §2.5 — the neighbour (Frigate on the same iGPU), not the app
est_duration_min: 25
needs_reboot: false
touches:
  namespaces: [home-automation]
  resources: [helmrelease/scrypted, deployment/scrypted, pvc/scrypted-data, pvc/scrypted-media]
  shared: [igpu-i915]             # SAME token as scrypted-0.145.0 — `shared` is an
                                  # INTERSECTION key; a synonym detects nothing. The pod
                                  # holds gpu.intel.com/i915:1 on k8s-nuc14-02, the
                                  # physical render node it shares with Frigate (live
                                  # NVR, real cameras). Nothing here reconfigures the
                                  # device plugin; a privileged SYS_ADMIN container
                                  # re-probing i915 is still a real shared-hardware
                                  # perturbation, so it is declared.
depends_on: []                    # Flux `dependsOn: intel-device-plugin-gpu` (ns
                                  # kube-system) is a Kustomization dependency, not a
                                  # plan — covered by premise + gate G2, see §7.
conflicts_with:
  - frigate-0.18.0                # same node (nuc14-02), same /dev/dri/renderD128, both
                                  # privileged GPU churn — co-scheduling makes a driver
                                  # wedge un-bisectable. Frigate is the thing this plan
                                  # can actually hurt (§2.1).
  - talos-1.14.0                  # reboots every node; that plan's own rule is "no other
                                  # plan may share its window".
security_ref: F-09a38bc2          # the image-level finding on the CURRENT tag. What it
                                  # says, and what this bump does to it, live on the record.
capability_change: false          # §2.4 — the one fact a reviewer should attack; premise
                                  # `only-core-plugin-is-loaded` + gate G3 falsify it at
                                  # runtime instead of trusting this file.
rollback_class: git-revert        # §2.3 — established from the upstream server diff AND
                                  # the live state, not assumed. State now PERSISTS on
                                  # /data (it did not when 0.145 was planned), so this is
                                  # the evidence-backed form, not the "nothing survives" form.
finding_refs: [F-b7f7f5c5, F-09a38bc2]   # F-b7f7f5c5 = the version finding for exactly
                                  # this bump (PLAN lane); F-09a38bc2 = the image-level
                                  # security finding this plan answers (cited, not described).
autonomy_override: human-gated    # RESTRICTS the derivation (which would read AUTO-NIGHT
                                  # from capability_change:false + git-revert). The
                                  # `*scrypted*` deny rule in runbooks/auto-update-policy.yaml
                                  # says verbatim: "A stable bump is made deliberately,
                                  # never unattended." AR-081 is the reason. The operator
                                  # also chose to execute the 0.145 bump personally.
                                  # Honour the rule: attended window, explicit GO.
status: draft
window: null
# PREMISES — mechanical, READ-ONLY, run by runbooks/plan-premises.py before
# execution. Its allowlist is cluster/git read verbs only (kubectl get/logs/…,
# flux get, git log/…, bare grep/sort/tr/cat); NO network verbs (gh, curl) and
# NO kubectl exec. So the upstream-channel checks the hold is about (Release
# still prerelease=false, no newer stable, registry manifest 200) CANNOT be
# premises here — they are hand-run ABORT gate G1 in §3, and the sweep-snapshot
# premise below is the closest legal proxy. Likewise the /media file count is
# hand-run gate G3; the plugin-set premise uses the server's own startup log.
premises:
  - id: live-image-is-still-v0.145.0
    why: >-
      `current:` and the rollback target are v0.145.0-noble-full. If the cluster
      already moved (or Helm's own remediation rolled it somewhere else), the
      baselines in §3/§5 are wrong and this plan is stale.
    run: kubectl get deploy -n home-automation scrypted -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: koush/scrypted:v0.145.0-noble-full
  - id: sweep-snapshot-still-targets-v0.147.0
    why: >-
      Legal proxy for "no newer tag has appeared". The sweep's version snapshot
      (working copy, refreshed every cycle) names the release URL of the target
      it currently proposes. If it no longer names v0.147.0-noble-full, upstream
      pushed a newer tag — stable OR dev. Fail closed either way: re-run G1 by
      hand; if v0.147.0 is still the newest prerelease=false Release, update
      this premise's expectation (not the target) and re-vet; if a newer stable
      exists, re-plan against it (the 0.146 lesson).
    run: cat /Users/mu/code/cberg-home-nextgen/runbooks/version-check-current.md | grep -c 'koush/scrypted/releases/tag/v0.147.0-noble-full'
    expect_exact: "1"
  - id: scrypted-volume-is-the-pvc
    why: >-
      `SCRYPTED_VOLUME=/data` (612034be) is what makes state persist on the
      scrypted-data PVC. If it reverted, the upgraded server would write its
      store to the ephemeral overlay and §2.3/§5.4 would be measuring nothing.
    run: kubectl get deploy -n home-automation scrypted -o jsonpath='{.spec.template.spec.containers[0].env[?(@.name=="SCRYPTED_VOLUME")].value}'
    expect_exact: /data
  - id: only-core-plugin-is-loaded
    why: >-
      capability_change:false rests on "no plugin but @scrypted/core, no
      configured devices" — every behavioural delta in the span is in plugin
      code paths. The server logs `starting plugin <id>` once per plugin at
      boot; the unique set must be exactly core. Any other id means the NVR
      has been configured since 2026-09-15 and the plan must be re-derived
      (§2.4). An EMPTY result (log rotated past the boot line) also fails
      closed — run gate G3 by hand, then re-vet.
    run: kubectl logs -n home-automation deploy/scrypted | grep -oE 'starting plugin @scrypted/[a-z0-9-]+' | sort -u | tr '\n' ' '
    expect_exact: starting plugin @scrypted/core
  - id: deployment-strategy-is-recreate
    why: >-
      Recreate is why a failed start costs the iGPU neighbours nothing (§2.1):
      the old pod returns its i915 slot before the replacement is scheduled.
      RollingUpdate on a 1-replica RWO-ish workload is the multi-attach trap.
    run: kubectl get deploy -n home-automation scrypted -o jsonpath='{.spec.strategy.type}'
    expect_exact: Recreate
  - id: intel-gpu-device-plugin-healthy
    why: >-
      ks.yaml `dependsOn: intel-device-plugin-gpu` (kube-system). If that
      Kustomization is not Ready the HelmRelease will not reconcile at all — the
      symptom is "nothing happens", which is easy to misread as Flux lag.
    run: kubectl get kustomization -n kube-system intel-device-plugin-gpu -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: "True"
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/storage-safety.md
  - docs/sops/verification-contents-not-shape.md
  - docs/sops/auto-update.md
  - docs/sops/vulnerability-disclosure.md
generated: "2026-09-15"
---

## 1. Summary & why held

Move the Scrypted NVR from `koush/scrypted:v0.145.0-noble-full` to
`koush/scrypted:v0.147.0-noble-full` — **one stable cut, 11 days and 19
upstream commits** (`v0.145.0` 2026-09-02 → `v0.147.0` 2026-09-13, `compare`
API `total_commits: 19`, 39 files). This is the direct successor of the plan
that executed on 2026-09-11 (`scrypted-0.145.0`), and it is the "NEXT ACTION"
that the retired `scrypted-0.146.0` plan named: *"when upstream cuts the next
prerelease=false Release (expected v0.147.0): dispatch a planner against THAT
tag."* It has.

### 1.1 Why held — the channel gate, and the verification result

`coverage.py` routes every scrypted bump to PLAN because upstream pushes dev
builds to the **same Docker repo** as stable: the tag string carries no channel
marker, so a bump "cannot be shown to be a STABLE-channel successor offline".
The `*scrypted*` deny rule in `runbooks/auto-update-policy.yaml` states the
gate: *"Gate on a prerelease=false Release for the exact tag, never on minor
parity. A stable bump is made deliberately, never unattended."*

**Verified 2026-09-15 against primary sources, not against the sweep's claim:**

```
GET /repos/koush/scrypted/releases?per_page=12
  v0.147.0  prerelease=false  draft=false  2026-09-13T18:51:39Z   <-- newest Release, == releases/latest
  v0.145.0  prerelease=false  draft=false  2026-09-02T15:50:28Z   <-- what we run
  (v0.146.0 and v0.146.1: HTTP 404 — no Release entry at all; still the dev channel)

Docker Hub  koush/scrypted:v0.147.0-noble-full
  tag_last_pushed 2026-09-13T19:13:40Z
  index  sha256:e78b4fcecdd6c61acaaf22b50ccef303c738da58cc0be57afdb116521df52296
  amd64  sha256:57a42bb8cc54a0b664eede57049af7efb0ec53bca73545836a93f4577c8fc4c1  (1,074,375,501 B)
  registry manifest HEAD: 200
  newest tags in the repo: v0.147.0-* (pushed 19:02–19:23Z), then v0.146.2-* (18:41–19:00Z)
  — NO v0.148.x dev tag exists yet, so "newest tag" and "newest stable" coincide today.
  That will stop being true the moment koush pushes v0.148.0; the premises above
  re-check it at execution time.
```

So `v0.147.0-noble-full` **is a shippable stable cut and the rule's own text
says it may be planned** — deliberately, attended, never at Step 0. That is
what this plan is. The hold was correct (the tooling genuinely cannot see the
channel), and it is discharged by this file, not by a false-positive verdict.

**G5 cooldown.** Release published 2026-09-13T18:51:39Z, tag pushed
2026-09-13T19:13:40Z → the 48h supply-chain cooldown clears at
**2026-09-15T19:13:40Z** at the latest. This plan is human-gated (frontmatter),
so the first eligible slot is the next attended window, well past that.

### 1.2 Breaking-change review, v0.145.0 → v0.147.0

Read from the `v0.147.0` release body, the full commit list, and the file diff
of the span. **Enumerated against what this deployment actually runs** (one
plugin, `@scrypted/core 0.3.149`; zero configured devices; zero HomeKit /
Home Assistant / camera plugins — measured, §2.2):

| Upstream change (commit) | Code path | Reaches this deployment? |
|---|---|---|
| server: engine.io API request routing tightened (`a920424`) — public-endpoint gating moved onto `endpointRequest.isPublicEndpoint` in `plugin-host.ts` | server ↔ plugin HTTP endpoints | Only through plugins that expose endpoints. None installed. **Inert here**, but it IS the server-side hardening the security driver (§1.3) points at. |
| core: static-file path handling in `sendFile` (`8ad9f4a`), icon util path (`a91d2ed`) | `@scrypted/core` plugin UI | core is installed — but core is **fetched from npm by the server at runtime** and versioned independently of the image (see §2.3). May advance from 0.3.149; record before/after (§5.4). |
| server: `adm-zip` `^0.5.16` → pinned `0.6.0` (`c269ba4`) | plugin-zip unpacking (`/data/plugins/@scrypted/core/zip`) | **Yes** — the persisted core zip is re-read by the new server. §5.4 asserts the plugin still loads. |
| common: RTSP parser compliance (#2137, `b130434`/`d376846`) | camera RTSP ingestion | No cameras. Inert. |
| python-codecs: arm zygote fork self-destruct (#2139) | arm64 only | amd64 node. Inert. |
| auth: `http-auth-utils` bump, plugins → rollup build (`bd451e7`) | plugin build tooling | Inert at runtime. |
| cloud: `push-receiver` update; amcrest: publish; ha: verup; `install/config.yaml` (HA add-on version string) | plugins we do not run / HA add-on packaging | Inert. |
| `server/src/runtime.ts` | a 2-line type cast | No behaviour. |

**What is NOT in the span, measured on the manifests (the lesson carried from
`scrypted-0.145.0` §1.3):** no Dockerfile, no `install/docker/*`, no
`template/*` change. `SCRYPTED_BASE_VERSION=20250101` on **both** images, the
first **27 of 35** amd64 layers are byte-identical (same prefix length as the
0.143→0.145 span), and the `apt-get install gstreamer1.0-*` layer is still in
both histories. **The pending `scrypted-common:noble-full` rebuild (GStreamer
removal, AMD-OpenCL drop, Intel compute-runtime/IGC rebase) has still not
landed.** It remains deferred, it can arrive on a PATCH tag, and §5.3 asserts
the base did not move under this tag either — the inverse of the assertion the
0.145 plan got wrong the first time.

**No database or state migration exists in the span.** `server/src/db-types.ts`
and the LevelDB layer are untouched; the only server source changes are the
routing edit and a type cast. This matters more than it did for 0.145, because
state now persists (§2.3).

### 1.3 Security driver

> **Security driver — detail withheld from this public repo.**
> Tracked as **F-09a38bc2** (`security` / severity `accepted`).
> Full detail (CVE IDs, counts, exposure, exploitability) lives on the
> finding record — it is deliberately not reproduced here.
>
> - Dashboard: `https://sweep.<DOMAIN>/findings/F-09a38bc2`
> - CLI: `runbooks/policy-cli.py finding show F-09a38bc2`
>
> See `docs/sops/vulnerability-disclosure.md` before adding any
> vulnerability detail to a committed file.

AR-081 (`koush/scrypted`, drift-stable needle) states its own re-review
trigger: *"NEXT RE-REVIEW: when upstream publishes a non-prerelease Release
newer than the live tag."* `v0.147.0` is that Release. This plan is the action
the AR asked for; after execution AR-081 and the image findings are
**re-measured, not assumed cleared** (§5.6). Because the base layer did not
move, base-package findings are expected to be largely unchanged — the
finding record, not this file, says what that means.

## 2. Blast radius, state, and the derived facts

### 2.1 Privilege and hardware coupling (re-verified 2026-09-15)

From the live `deployment/scrypted` and pod `scrypted-5fcd45cc79-ssc9b`:

- **Privileged**: `privileged: true`, `capabilities.add: [SYS_ADMIN]`,
  `allowPrivilegeEscalation: true`, `runAsUser/Group: 0`. This is why AR-081
  refuses the dev channel and why `risk: medium` survives an empty NVR.
- **iGPU**: `gpu.intel.com/i915: 1` in requests and limits, via the
  cluster-wide `intel-device-plugin-gpu` Kustomization (**namespace
  `kube-system`**, DaemonSet `intel-gpu-plugin-intel-gpu-plugin`, 3/3 Ready).
  Live holders, measured:

  | Node | i915 alloc | Holders |
  |---|---|---|
  | k8s-nuc14-01 | 2 / 5 | immich-server, plex |
  | k8s-nuc14-02 | 2 / 5 | **scrypted**, **frigate** |
  | k8s-nuc14-03 | 3 / 5 | jellyfin, makemkv, immich-machine-learning |

  (Immich-ML has moved to -03 since the 0.145 plan; Frigate has not.)

  **Cost of a failed start to the neighbours: nothing, by scheduling** — the
  strategy is `Recreate` (premise), so the old pod releases its slot before the
  replacement is scheduled, and headroom is 3 slots on every node.

  **The exposure that matters is one level down**: the plugin hands out
  scheduling slots, not sessions. A privileged, SYS_ADMIN container
  re-initialising the i915 stack shares the physical `/dev/dri/renderD128` on
  k8s-nuc14-02 with **Frigate, a live NVR with real cameras**. A driver-level
  wedge there is the one way this plan hurts something that matters. Nothing
  suggests it is likely (the GPU userspace layer is byte-identical to what
  runs today, §1.2); it is why `touches.shared` is not `[]` and why
  `frigate-0.18.0` is in `conflicts_with`.

- **`/dev/dri` hostPath block in the HelmRelease is still inert** under
  app-template 5.1.0 — the rendered pod has exactly two volumes (`data`,
  `media`). GPU access is entirely device-plugin + privileged. **Do not "fix"
  it in this window**; it changes the device-access path in the same change as
  an image bump and makes a failure un-bisectable. Unchanged from 0.145 §2.1.

### 2.2 Storage — and what is actually on it

- `scrypted-media` → `cifs-scrypted-media` (`//192.168.55.240/scrypted`,
  `subdir: /media`, `reclaimPolicy: Retain`) — "Severe" tier in
  `docs/sops/storage-safety.md`. Mounted at `/media`. **Measured:
  `find /media -type f | wc -l` → `0`.** No recordings exist.
- `scrypted-data` → `longhorn` dynamic RWX (NFS via share-manager,
  `pvc-bd13d22f-…`), mounted at **`/data`**. **Measured: 45 MB** —
  `plugins/@scrypted/core/zip` (7.7 MB zip + unzipped, written 2026-09-07) and
  `scrypted.db/` (10 MB LevelDB: `000005.ldb` 10.26 MB from 2026-09-07,
  reopened 2026-09-11 at the 0.145 pod start).
- **This plan performs no PVC action whatsoever** — no delete, no resize, no
  StorageClass change. The storage-safety 3-step pre-flight is not triggered.
  The CIFS mount is named only so the window agent knows what must not be
  touched. **Never propose deleting `scrypted-media`** — it is a shared-fs
  PVC; blast radius is set by the StorageClass, not by the fact it is empty.
- No external DB, no schema migration; `docs/sops/backup.md` does not apply.

### 2.3 State and the rollback determination — CHANGED since 0.145, read it

**The 0.145 plan's central state fact no longer holds.** That plan established
`SCRYPTED_VOLUME=/server/volume` (ephemeral overlay, 16 KB, recreated every
restart) and derived the *strong* form of git-revert: "nothing survives the
restart the upgrade itself performs". Commit `612034be` then set
`SCRYPTED_VOLUME=/data`, and the 0.145 execution ran on top of it. Measured
today on the live pod:

```
SCRYPTED_VOLUME=/data                       # pod env — the PVC, not the overlay
/data/scrypted.db/000005.ldb  10,261,553 B  mtime 2026-09-07   # survived the 2026-09-11 restart
/data/scrypted.db/{000007.ldb,000008.log,CURRENT,MANIFEST-000006}  mtime 2026-09-11 07:28 = pod start
/data/plugins/@scrypted/core/zip/            written 2026-09-07, NOT rewritten on 2026-09-11
DB documents: 1 Plugin (@scrypted/core 0.3.149), 33 PluginDevice (all pluginId=@scrypted/core,
              type Builtin), 1 Settings. No camera, no user-added device, no other plugin.
```

So the upgraded server **will open a persisted store and a persisted plugin
zip written by the older version**, and a downgrade would open a store
touched by the newer one. `rollback_class: git-revert` is still correct, but
now on **evidence**, not on emptiness:

1. **No storage-format change in the span** — `db-types.ts` and the LevelDB
   layer are untouched; server source changes are the routing edit and a cast
   (§1.2). There is no migration for a downgrade to trip over.
2. **The persisted state is regenerable** — it is the built-in core plugin
   and its 33 built-in device rows, which a fresh server recreates from
   scratch (the 0.145 plan measured exactly that on the overlay). Nothing a
   human configured is in it.
3. **Core plugin version is decoupled from the server** — the server installs
   and updates `@scrypted/core` from npm at runtime (the live log shows the
   built-in *"Autoupdate Plugins"* automation armed on a daily trigger). Older
   servers run newer core plugins routinely; that is upstream's normal state
   between releases, with or without this bump.

**Belt-and-braces, cheap, and read-only against the cluster:** §3 snapshots
`/data/scrypted.db` + the plugin dir (≈45 MB) to the operator's scratch
before the bump. It is *not* a `backup_gate` and the class does not depend on
it — it exists so that if (1)–(3) are wrong in a way nobody foresaw, §6 has a
restore leg that costs one `kubectl cp` instead of a re-derivation. If the
window agent ever finds `only-core-plugin-is-loaded` or G3 failing, this snapshot
is also the thing that turns "the operator configured cameras" from a loss
into a restore — but that case is an ABORT, not a proceed.

### 2.4 `capability_change: false` — the fact, and how it is falsifiable

Declared **false**. Reasoning, stated so it can be checked rather than trusted:

- Every behavioural delta in the span is in plugin code paths (RTSP parser,
  python-codecs, cloud, amcrest, auth build) or in server↔plugin HTTP routing
  that only plugins exposing endpoints exercise (§1.2 table).
- This instance runs **one plugin, `@scrypted/core`**, and has **zero
  configured devices** (§2.3). The core server with only core serves a login
  page and the plugin-management UI, and that is what it will serve after.
- Therefore no user-visible behaviour of *this deployment* changes.

If the premise is false at execution time, the declaration is false. Premise
`only-core-plugin-is-loaded` and gate **G3** test it and ABORT rather than let
a stale fact carry the run. (It would also mean the operator has started using
the NVR — which is good news and a reason to re-plan with real camera
assertions, not a reason to push through.)

### 2.5 Why `risk: medium`

Not for the app: nothing configured, nothing recorded, state regenerable. It
stays **medium** because a privileged SYS_ADMIN container re-initialising the
iGPU shares the physical render node on k8s-nuc14-02 with Frigate, which *is*
a live NVR. The blast radius that matters is the neighbour. Same verdict and
same reason as the executed 0.145 plan; that execution produced no Frigate
impact, which is evidence for keeping it at medium rather than raising it.

## 3. Pre-checks

Run all of these. **G1–G3 are ABORT gates.** Run `python3
runbooks/plan-premises.py scrypted-0.147.0 --require-premises` FIRST — it
mechanises the cluster-side facts (image, volume, plugin set, strategy, GPU
dependency, sweep snapshot). It CANNOT mechanise G1 (network verbs are outside
its allowlist by design) or the `/media` count in G3 (needs `kubectl exec`), so
those two are hand-run below and are not optional. In particular the
`sweep-snapshot-still-targets-v0.147.0` premise reads
`runbooks/version-check-current.md`, which is git-UNTRACKED and refreshed only
every 48 h by the sweep: a `v0.148.x` tag pushed after the last sweep and
before the window is invisible to it, so **a passing premise set does not
excuse skipping G1**.

```bash
cd /Users/mu/code/cberg-home-nextgen
python3 runbooks/plan-premises.py scrypted-0.147.0 --require-premises   # ALL must pass; fail = ABORT
POD=$(kubectl get pods -n home-automation -l app.kubernetes.io/name=scrypted \
        -o jsonpath='{.items[0].metadata.name}')

# --- G1 (ABORT) — channel + registry, re-run by hand as well. Do not proceed on
#     anything but prerelease=false, latest==v0.147.0, manifest 200.
gh api repos/koush/scrypted/releases/tags/v0.147.0 --jq '"\(.tag_name) prerelease=\(.prerelease) draft=\(.draft) published=\(.published_at)"'
gh api repos/koush/scrypted/releases/latest --jq .tag_name
TOKEN=$(curl -s "https://auth.docker.io/token?service=registry.docker.io&scope=repository:koush/scrypted:pull" \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
curl -s -o /dev/null -w '%{http_code}\n' -H "Authorization: Bearer $TOKEN" \
  -H "Accept: application/vnd.oci.image.index.v1+json,application/vnd.docker.distribution.manifest.list.v2+json" \
  "https://registry-1.docker.io/v2/koush/scrypted/manifests/v0.147.0-noble-full"
#   If a NEWER prerelease=false Release than v0.147.0 exists: STOP, re-plan against it.
#   A newer TAG on Docker Hub (v0.148.x) is NOT that — it is the dev channel unless
#   it has a Release. Apply the gate, never the odd/even heuristic.

# --- G2 (ABORT) — hard Flux dependency (ks.yaml dependsOn). NOTE: kube-system,
#     not flux-system — the 0.145 plan had the namespace wrong.
flux get kustomization -n kube-system intel-device-plugin-gpu
kubectl get ds -n kube-system intel-gpu-plugin-intel-gpu-plugin     # 3/3 READY
flux get kustomization -n home-automation scrypted                   # Ready, not mid-reconcile

# --- G3 (ABORT) — FALSIFY the capability_change:false premise (§2.4).
#     Expected: plugins/ holds ONLY @scrypted/core; pluginId set == {@scrypted/core};
#     PluginDevice rows == 33; media files == 0.
kubectl exec -n home-automation $POD -- sh -c \
  'ls /data/plugins/@scrypted; echo "--- pluginIds ---";
   cat /data/scrypted.db/*.ldb /data/scrypted.db/*.log 2>/dev/null | strings | grep -oE "\"pluginId\":\"[^\"]+\"" | sort | uniq -c;
   echo "--- docs ---";
   cat /data/scrypted.db/*.ldb /data/scrypted.db/*.log 2>/dev/null | strings | grep -oE "\"_documentType\":\"[A-Za-z]+\"" | sort | uniq -c;
   echo "--- media ---"; find /media -type f | wc -l'
#   Any pluginId other than @scrypted/core, any non-Builtin device, or media > 0
#   => the NVR has been configured since 2026-09-15. STOP. Re-derive: capability_change
#   becomes true, §5 needs camera-enumeration + recording-continuity assertions, and
#   the §2.3 snapshot becomes a real backup rather than insurance.
#   `strings` is present in the noble-full image today (these baselines were measured
#   with it on 2026-09-15). If a future base re-cut removes it, that is "run the check
#   differently" (`grep -a -oE` straight on the files, or `kubectl cp` the store out and
#   inspect locally) — NOT a store failure and NOT a reason to skip G3.

# --- Clean pre-state (informational)
flux get helmrelease -n home-automation scrypted
kubectl get pods -n home-automation -l app.kubernetes.io/name=scrypted -o wide     # 0 restarts, on nuc14-02
kubectl get pod -n home-automation $POD -o jsonpath='{.status.containerStatuses[0].imageID}{"\n"}'
#   baseline 2026-09-15: docker.io/koush/scrypted@sha256:294be875371dc4f2897174120ce707c43bde8d18e41545077c4c6c88911af990
git -C /Users/mu/code/cberg-home-nextgen status --porcelain kubernetes/apps/home-automation/scrypted-nvr/

# --- BASELINES for §5. Capture BEFORE touching anything.
kubectl exec -n home-automation $POD -- ffmpeg -hide_banner -encoders 2>/dev/null | grep -c vaapi
#   baseline measured 2026-09-15 on v0.145.0: 7
kubectl exec -n home-automation $POD -- sh -c \
  'ffmpeg -hide_banner -loglevel error -init_hw_device vaapi=va:/dev/dri/renderD128 \
     -f lavfi -i testsrc=size=320x240:rate=5:duration=1 -vf format=nv12,hwupload \
     -c:v h264_vaapi -f null - && echo VAAPI_ENCODE_OK'
#   baseline 2026-09-15: VAAPI_ENCODE_OK
kubectl exec -n home-automation $POD -- sh -c 'command -v gst-launch-1.0'      # baseline: /usr/bin/gst-launch-1.0 (base unchanged)
kubectl logs -n home-automation $POD | grep -E '^Version:' | tail -1          # baseline: "Version:       : 0.145.0"
kubectl exec -n home-automation $POD -- sh -c \
  'cat /data/scrypted.db/*.ldb /data/scrypted.db/*.log 2>/dev/null | strings | grep -oE "\"_documentType\":\"Plugin\".{0,400}" | grep -oE "\"version\":\"[^\"]+\"" | head -1'
#   baseline 2026-09-15: "version":"0.3.149"   (core plugin; MAY advance after the bump — record it)
kubectl exec -n home-automation $POD -- sh -c 'ls -l /data/scrypted.db/000005.ldb; du -sk /data'
#   baseline: 000005.ldb 10261553 B mtime Sep 7; /data 45516 KB
RESTART_TS=$(date -u +%Y-%m-%dT%H:%M:%SZ); echo "RESTART_TS=$RESTART_TS"

# --- STATE SNAPSHOT (§2.3 belt-and-braces; read-only against the cluster)
SNAP=/private/tmp/scrypted-state-$(date -u +%Y%m%dT%H%M%SZ).tgz
kubectl exec -n home-automation $POD -- sh -c 'cd /data && tar czf - scrypted.db plugins' > "$SNAP"
ls -l "$SNAP"; tar tzf "$SNAP" | head -5      # ~45 MB uncompressed; must list scrypted.db/000005.ldb

# --- Alert noise suppression (docs/sops/application-update.md §4 Step 1)
kubectl port-forward -n monitoring svc/kube-prometheus-stack-alertmanager 9093:9093 &
NOW=$(python3 -c "from datetime import *;print(datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z'))")
END=$(python3 -c "from datetime import *;print((datetime.now(timezone.utc)+timedelta(hours=2)).strftime('%Y-%m-%dT%H:%M:%S.000Z'))")
curl -s -X POST localhost:9093/api/v2/silences -H 'Content-Type: application/json' -d '{
  "matchers":[{"name":"namespace","value":"home-automation","isRegex":false,"isEqual":true},
              {"name":"alertname","value":"Scrypted.*|Kube(Pod|Deployment).*","isRegex":true,"isEqual":true}],
  "startsAt":"'$NOW'","endsAt":"'$END'","createdBy":"operator",
  "comment":"scrypted v0.145.0 -> v0.147.0 image bump — rollout noise. auto-expires 2h"}'
runbooks/update-marker.sh add scrypted home-automation 2 "scrypted v0.145.0->v0.147.0"
```

## 4. Steps

GitOps only. One file changes; one value line plus its comment block.

1. Edit `kubernetes/apps/home-automation/scrypted-nvr/app/helmrelease.yaml`,
   `spec.values.controllers.scrypted.containers.app.image`:
   ```yaml
   image:
     repository: koush/scrypted
     # v0.147.0 is the newest STABLE cut: newest tag with a GitHub Release
     # carrying prerelease=false (verified 2026-09-15; Release published
     # 2026-09-13). koush publishes even-minor tags (v0.146.x, v0.148.x…) to
     # the registry with NO Release entry -- upstream's dev channel, not
     # acceptable on a privileged, iGPU-holding NVR (AR-081). The gate is
     # "does a prerelease=false Release exist for THIS exact tag", never
     # "is the minor odd".
     tag: v0.147.0-noble-full     # was: v0.145.0-noble-full
   ```
   Change nothing else. Do **not** touch the inert `extraVolumes` /
   `extraVolumeMounts` block (§2.1), do **not** touch `SCRYPTED_VOLUME` (§2.3),
   do **not** touch the `*scrypted*` deny rule (§7).

2. Confirm the diff is confined to that block:
   ```bash
   git -C /Users/mu/code/cberg-home-nextgen diff --stat kubernetes/apps/home-automation/scrypted-nvr/app/helmrelease.yaml
   git -C /Users/mu/code/cberg-home-nextgen diff kubernetes/apps/home-automation/scrypted-nvr/app/helmrelease.yaml
   ```

3. Commit with `--only` (shared worktree — the index already carries other
   sessions' hunks) and push:
   ```bash
   cd /Users/mu/code/cberg-home-nextgen
   git fetch origin main && git merge --ff-only origin/main
   git commit --only kubernetes/apps/home-automation/scrypted-nvr/app/helmrelease.yaml \
     -m "feat(scrypted): v0.145.0-noble-full -> v0.147.0-noble-full (current upstream stable)"
   git show --stat HEAD        # exactly one file, and it is yours
   git push origin main
   ```
   Keep CVE detail out of the commit message (`docs/sops/vulnerability-disclosure.md`).

4. Watch Flux reconcile. No manual `flux reconcile` — the GitRepository
   webhook plus the 30m HelmRelease interval covers it:
   ```bash
   flux get helmrelease -n home-automation scrypted --watch
   kubectl get pods -n home-automation -l app.kubernetes.io/name=scrypted -w
   ```
   Strategy is `Recreate`: the old pod terminates fully before the new one
   appears — correct, not a stall. Budget for a cold ~1.07 GB pull on
   k8s-nuc14-02 (only 8 of 35 layers are new; the shared 27 are already on
   the node, so the real pull is smaller).

5. Do not hand-delete pods mid-rollout. If it wedges, work
   `docs/sops/application-update.md` §7 before improvising. The HelmRelease
   has `upgrade.remediation.strategy: rollback, retries: 3` — Helm may roll
   the values back on its own while git still says v0.147.0, so always
   confirm the running `imageID`, never the manifest (§5.1).

## 5. Verification

### 5.1 Floor (shape checks — necessary, not sufficient)

```bash
POD=$(kubectl get pods -n home-automation -l app.kubernetes.io/name=scrypted -o jsonpath='{.items[0].metadata.name}')
kubectl get helmrelease -n home-automation scrypted -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}{"\n"}'
kubectl get pods -n home-automation -l app.kubernetes.io/name=scrypted        # 1/1 Running, 0 restarts after settle
kubectl get pod -n home-automation $POD -o jsonpath='{.status.containerStatuses[0].imageID}{"\n"}'
#   MUST be docker.io/koush/scrypted@sha256:e78b4fcecdd6c61acaaf22b50ccef303c738da58cc0be57afdb116521df52296
#   (the v0.147.0-noble-full index digest) — NEW bytes, not a tag string.
```

### 5.2 CONTENTS ASSERTION (primary — carries the plan)

> **CONTENTS ASSERTION: hardware VA-API encode on the shared iGPU still
> actually engages** — measured by initialising a VA-API device on
> `/dev/dri/renderD128` and running a real `h264_vaapi` encode inside the new
> container, compared to the §3 baseline (`VAAPI_ENCODE_OK`; 7 VA-API
> encoders; measured on v0.145.0 on 2026-09-15).

```bash
kubectl exec -n home-automation $POD -- ffmpeg -hide_banner -encoders 2>/dev/null | grep -c vaapi
#   MUST be 7 (av1, h264, hevc, mjpeg, mpeg2, vp8, vp9). Fewer = codec support lost.
kubectl exec -n home-automation $POD -- sh -c \
  'ffmpeg -hide_banner -loglevel error -init_hw_device vaapi=va:/dev/dri/renderD128 \
     -f lavfi -i testsrc=size=320x240:rate=5:duration=1 -vf format=nv12,hwupload \
     -c:v h264_vaapi -f null - && echo VAAPI_ENCODE_OK'
#   MUST print VAAPI_ENCODE_OK.
```

A container whose GPU stack regressed starts perfectly, passes every probe,
reports Ready — and every transcode silently falls back to software.
`-init_hw_device` fails outright on a broken driver and the encode fails on
an unusable render node, so neither goes green on a broken GPU.

### 5.3 CONTENTS ASSERTION (secondary — new build, SAME base)

> **CONTENTS ASSERTION: the running server is the new build AND the base
> layer did not move under the tag** — measured by the server's own version
> banner and by GStreamer still being present, compared to the §3 baseline
> (`0.145.0`; `/usr/bin/gst-launch-1.0` present).

```bash
kubectl logs -n home-automation $POD | grep -E '^Version:' | tail -1
#   MUST read 0.147.0
kubectl exec -n home-automation $POD -- sh -c 'command -v gst-launch-1.0 || echo GSTREAMER_ABSENT'
#   MUST print /usr/bin/gst-launch-1.0. §1.2 measured the base layer identical
#   (SCRYPTED_BASE_VERSION=20250101, gstreamer apt layer in history). GSTREAMER_ABSENT
#   means the base WAS re-cut under this tag after this plan was written — the
#   deferred breaking change landed unannounced. Not a rollback trigger on its own
#   (no plugin here uses it), but it MUST be recorded on the finding/AR re-measure
#   and it re-opens the 0.145 §1.3 item for the next plan.
```

### 5.4 CONTENTS ASSERTION (persistence — new for this plan)

> **CONTENTS ASSERTION: the upgraded server opened the PERSISTED store and
> plugin, not a fresh one** — measured by the pre-existing 10 MB SSTable and
> the plugin document still being present after the restart, compared to the
> §3 baseline (`000005.ldb` 10,261,553 B, 33 PluginDevice rows, core plugin
> present).

```bash
kubectl exec -n home-automation $POD -- sh -c \
  'ls -l /data/scrypted.db/000005.ldb;
   cat /data/scrypted.db/*.ldb /data/scrypted.db/*.log 2>/dev/null | strings | grep -oE "\"_documentType\":\"[A-Za-z]+\"" | sort | uniq -c;
   cat /data/scrypted.db/*.ldb /data/scrypted.db/*.log 2>/dev/null | strings | grep -oE "\"_documentType\":\"Plugin\".{0,400}" | grep -oE "\"version\":\"[^\"]+\"" | head -1'
#   000005.ldb MUST still exist at the same size; document counts MUST match §3 G3
#   (1 Plugin, 33 PluginDevice, 1 Settings — LevelDB compaction may merge files, so
#   compare the COUNTS, and treat a missing 000005.ldb as suspicious only if the
#   counts also changed). Record the core plugin version: 0.3.149 or newer — a
#   newer core is expected upstream behaviour (§2.3 item 3), not a regression.
kubectl logs -n home-automation $POD | grep -iE 'core|plugin' | grep -viE 'debug' | head -5
#   Expect the core plugin loading, not "installing @scrypted/core" from scratch.
```

This is the assertion that would go green on the OLD plan and lie: a server
that silently wrote a fresh store to some other path would be Ready, would
serve a login page, and would have thrown away persistence the operator
deliberately fixed in `612034be`.

### 5.5 Service reachability — both paths

```bash
kubectl -n home-automation port-forward svc/scrypted 11080:11080 >/dev/null 2>&1 & PF=$!; sleep 2
curl -s -o /dev/null -w 'http=%{http_code} bytes=%{size_download}\n' http://localhost:11080/
#   2xx/3xx with a non-trivial body, not 0 bytes.
kill $PF 2>/dev/null
# Resolve the public host from the LIVE HTTPRoute — never from an unexported ${SECRET_DOMAIN},
# which silently tests `https://scrypted./` and records a false failure (review 2026-09-15):
HOST=$(kubectl get httproute -n home-automation scrypted -o jsonpath='{.spec.hostnames[0]}')
[ -n "$HOST" ] || { echo "no hostname on httproute/scrypted — STOP, do not skip this check"; false; }
curl -sk -o /dev/null -w 'http=%{http_code} bytes=%{size_download}\n' "https://$HOST/"
#   Through the HTTPRoute on envoy-internal — proves the route still binds after the
#   Recreate (the Service is untouched, but assert it rather than assume it). Do not run
#   this while an envoy/external-dns plan is mid-rollout in the same slot.
```

### 5.6 Honest note on cameras and recordings

"Cameras enumerate" / "recordings resumed" / "new files under `/media`"
**cannot be asserted honestly on this deployment and must not be faked
green** — zero devices, zero plugins beyond core, zero media files (premise
`only-core-plugin-is-loaded`; gate G3 media count). A `find /media
-newermt …` returning nothing is indistinguishable from a total failure to
record. §5.2 and §5.4 are the load-bearing assertions. Record the inventory as
an unchanged diff (`find /media -type f | wc -l` → still 0) and label it as
such. If G3 ever fails, this section stops being sufficient — and so does the
plan (§2.4): abort, do not improvise camera checks.

### 5.7 Close-out

```bash
curl -s -X DELETE localhost:9093/api/v2/silences/<id>
runbooks/update-marker.sh clear scrypted
rm -f "$SNAP"    # only after §5.4 passed and ≥1 clean restart-free hour; keep it on any doubt
```
Then re-measure the security posture rather than assuming the bump cleared it:
```bash
source runbooks/lib/sweep-pg-dsn.sh && sweep_pg_dsn_up
runbooks/policy-cli.py finding list --grep scrypted
runbooks/policy-cli.py risk show AR-081
```
AR-081's needle (`koush/scrypted`) is version-agnostic, so suppression
continues automatically across the bump — which is exactly why the re-measure
has to be deliberate. Refresh AR-081's `last_reviewed_at` and justification
via `runbooks/policy-cli.py risk` (keep the numbers in the DB). **In the same
edit** (review 2026-09-15): move AR-081's `security_ref` from `F-b885ec1b` —
the v0.143.0 image finding, RESOLVED 2026-09-13 — to the live image finding
**F-09a38bc2** that this plan cites, and replace the justification's
"v0.145.0 IS the newest upstream stable" sentence (false since v0.147.0) with
the post-bump truth; the AR's own NEXT RE-REVIEW trigger has fired and its
evidence currently points at a resolved record. Close `F-b7f7f5c5` with
`--commit <bump-sha>` if the sweep's version check does not resolve it on its
own next cycle. Then **delete this plan file in the same commit that lands the
upgrade** (README: plans are transient). `scrypted-0.145.0.md` (executed) and
`scrypted-0.146.0.md` (superseded) were deleted in the 2026-09-15 review
commit; the `*scrypted*` deny-rule `reason:` in
`runbooks/auto-update-policy.yaml` still names "v0.145.0, live" and the
0.146.0 file — refresh that text and bump the policy `version` IN THE LANDING
COMMIT, keeping the rule itself (§7).

## 6. Rollback

Concrete, and sufficient — §2.3 for why the state leg is insurance, not need.

```bash
cd /Users/mu/code/cberg-home-nextgen
git log --oneline -5 -- kubernetes/apps/home-automation/scrypted-nvr/app/helmrelease.yaml
git revert --no-edit <the-bump-commit>          # or: git checkout <pre-bump-sha> -- <file>
git show --stat HEAD                             # exactly the one file
git push origin main
flux reconcile helmrelease -n home-automation scrypted --force    # only if the interval has not fired
```

Confirm the cluster is actually back — by digest and by the contents
assertions, not by "Ready":

```bash
POD=$(kubectl get pods -n home-automation -l app.kubernetes.io/name=scrypted -o jsonpath='{.items[0].metadata.name}')
kubectl get pod -n home-automation $POD -o jsonpath='{.status.containerStatuses[0].imageID}{"\n"}'
#   MUST be docker.io/koush/scrypted@sha256:294be875371dc4f2897174120ce707c43bde8d18e41545077c4c6c88911af990
kubectl logs -n home-automation $POD | grep -E '^Version:' | tail -1      # -> 0.145.0
kubectl exec -n home-automation $POD -- sh -c \
  'ffmpeg -hide_banner -loglevel error -init_hw_device vaapi=va:/dev/dri/renderD128 \
     -f lavfi -i testsrc=size=320x240:rate=5:duration=1 -vf format=nv12,hwupload \
     -c:v h264_vaapi -f null - && echo VAAPI_ENCODE_OK'
kubectl exec -n home-automation $POD -- sh -c 'ls -l /data/scrypted.db/000005.ldb; find /media -type f | wc -l'
```

**State leg — only if §5.4 showed the store was damaged or rewritten** (not
expected; §2.3 items 1–3). The downgraded server normally reopens the same
`/data/scrypted.db` and the same core zip. If it does not — e.g. it refuses
the store or re-installs core from scratch and the operator wants the
pre-bump state back byte-for-byte:

```bash
kubectl scale deploy -n home-automation scrypted --replicas=0 && sleep 10
kubectl run -n home-automation scrypted-restore --rm -i --restart=Never --image=busybox:1.36 \
  --overrides='{"spec":{"volumes":[{"name":"d","persistentVolumeClaim":{"claimName":"scrypted-data"}}],
  "containers":[{"name":"r","image":"busybox:1.36","stdin":true,"command":["sh","-c","cd /data && rm -rf scrypted.db plugins && tar xzf - && ls -l"],
  "volumeMounts":[{"name":"d","mountPath":"/data"}]}]}}' < "$SNAP"
kubectl scale deploy -n home-automation scrypted --replicas=1
#   Then re-run the §5.4 assertion against the restored store. This is a hand
#   operation on scrypted-data ONLY (Longhorn RWX, 45 MB, regenerable) — it never
#   touches scrypted-media (CIFS, storage-safety "Severe" tier).
```

Then clear the silence and marker as in §5.7.

## 7. Interference notes

- **`touches.shared: [igpu-i915]`** — same token as `scrypted-0.145.0`; keep
  the spelling. Practical rule: do not co-schedule with anything that restarts
  `intel-device-plugin-gpu`, and not with a GPU-heavy plan on **k8s-nuc14-02**
  — today that is exactly `frigate-0.18.0`, hence `conflicts_with`. Frigate's
  own plan says i915 is 2/5 on that node and pins there; both plans are
  privileged GPU churn on one render node, and a wedge with both in flight
  cannot be attributed. It is **not** in `autonomy-policy.yaml`'s
  `forbid_shared` (`[storage, longhorn]`), so declaring it costs nothing.
- **`autonomy_override: human-gated` is deliberate and may not be widened by
  the window agent.** The derivation would read AUTO-NIGHT from the facts
  (`capability_change: false`, `git-revert`, no reboot, medium risk). The
  `*scrypted*` deny rule says a stable bump is "made deliberately, never
  unattended" and AR-081 is its reason; a privileged NVR sharing the iGPU
  with a live NVR is the kind of thing the operator wants to be present for
  (they executed 0.145 personally). Attended window, explicit GO.
- **G5 cooldown** clears 2026-09-15T19:13:40Z (tag push) — irrelevant to an
  attended window on/after 2026-09-19, noted so nobody re-derives it.
- **`intel-device-plugin-gpu` is a hard Flux dependency, not a plan
  dependency** — and it lives in **`kube-system`** (`ks.yaml`
  `dependsOn: {name: intel-device-plugin-gpu, namespace: kube-system}`); the
  0.145 plan's G2 queried `flux-system` and would have printed "not found".
  A dead plan-id ref is a validation error, so it stays out of `depends_on:`;
  the premise `intel-gpu-device-plugin-healthy` and gate G2 cover it. If it is
  mid-reconcile, the symptom is "nothing happens", not a failure.
- **Do NOT remove or loosen the `*scrypted*` deny rule in
  `runbooks/auto-update-policy.yaml`** in this work. It keeps the even-minor
  dev channel (`v0.146.x` today, `v0.148.x` next) out of the nightly Step-0
  auto-apply and stays correct after this bump. Its reason text names
  "v0.145.0, live" (and the since-deleted 0.146.0 plan file) and reads stale
  the moment v0.147.0 is live — refresh that wording and bump the policy
  `version` IN THE LANDING COMMIT (§5.7), so the rule's evidence and the
  cluster do not drift; the rule itself stays.
- **Renovate has no PR for this and will keep pointing at the newest tag**,
  which becomes the dev channel again the moment `v0.148.0-noble-full` is
  pushed. Apply the Release gate (G1, with premise
  `sweep-snapshot-still-targets-v0.147.0` as the mechanical tripwire), never
  the odd/even heuristic.
- **`scrypted-0.146.0.md` (superseded) and `scrypted-0.145.0.md` (executed)
  were DELETED in the 2026-09-15 review commit** — README: plans are
  transient, and the policy comment had already claimed 0.146.0 was retired on
  2026-09-11 while the file sat on disk. This plan supersedes neither's
  reasoning and revives nothing; 0.146's hold verdict stands and is carried by
  the `*scrypted*` policy rule (git history has both files).
- **Out of scope, flagged, not to be fixed here:** the HelmRelease's
  `extraVolumes`/`extraVolumeMounts` `/dev/dri` block is inert under
  app-template 5.1.0 and overstates host access to an auditor (§2.1). Real
  defect, its own plan. (The `SCRYPTED_VOLUME` defect the 0.145 plan flagged
  IS fixed — `612034be` — which is why §2.3 and §5.4 exist.)
- **Biggest gotcha for the executor:** the thing that changed since the last
  scrypted bump is that **state now persists**. "Pod Ready + new digest" was
  never enough (GPU fallback, §5.2); now it is also not enough for a second
  reason — a server that quietly opened a fresh store somewhere else would be
  Ready, serve a login page, and have thrown away the persistence fix. §5.4
  is the check, and it has a measured baseline (`000005.ldb`, 10,261,553 B,
  33 PluginDevice rows) from before the change.

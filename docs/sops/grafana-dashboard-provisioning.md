# SOP: Grafana Dashboard Provisioning (Grafana 13 Unified Storage)

> Description: How provisioned dashboards are actually stored and reconciled in Grafana 13 — they are `dashboard.grafana.app` resources in unified storage, not rows in the legacy `dashboard`/`dashboard_provisioning` tables — plus how to inspect that layer, why the obvious sqlite access path fails on a Longhorn PVC, and why `GF_PLUGINS_PREINSTALL_DISABLED` is load-bearing for dashboards as well as datasources.
> Version: `2026.09.22`
> Last Updated: `2026-09-22`
> Owner: `homelab-sre`

---

## Evidence convention used in this SOP

Operational docs in this repo have caused real incidents by asserting things
that were once true. Every non-obvious factual claim below therefore carries
its provenance:

- **`[verified 2026-09-22]`** — re-measured against the live cluster while
  writing this SOP. The command that produced it is included.
- **`[recovered 2026-09-13]`** — measured during the incident investigation and
  recovered from the now-deleted plan file
  `runbooks/maintenance/plans/grafana-duplicate-provisioning-row.md`
  (commits `d3063e44`, `a30e803c`, `a0556c6d`). **Not re-verified today**,
  because re-verifying it requires writing to the cluster. Treat it as a
  well-evidenced starting hypothesis, not as present-tense fact.

If you act on a `[recovered]` claim, re-measure it first and update the tag.

---

## 1) Description

Grafana 13 moved dashboard storage to **unified storage**. The legacy sqlite
tables that every older runbook, blog post and LLM answer tells you to inspect
(`dashboard`, `dashboard_provisioning`) still exist and still contain
plausible-looking rows — but the running provisioner does not read them. Two
separate corrective changes were executed against those tables in September
2026. Both applied cleanly, both were verified as "the row is gone", and
**both changed nothing observable**, because they edited a dead layer.

That is the specific, expensive mistake this SOP exists to prevent.

- Scope: dashboard **provisioning** for the `grafana` HelmRelease in namespace
  `monitoring` — chart-shipped dashboards, `gnetId`/`url` downloads, and the
  `k8s-sidecar` ConfigMap-label mechanism.
- Prerequisites: repo-pinned tooling via `mise exec --`, cluster read access,
  `grafana-admin-secret` for the admin API.
- Out of scope:
  - **Image/tag/variant changes** → [`grafana-image-changes.md`](grafana-image-changes.md).
    That SOP owns the datasource pre-flight gate; this one does not repeat it.
  - Datasource *definitions* (the `datasources.yaml` values block).
  - Grafana's Authentik/OAuth integration.

---

## 2) Overview

| Setting | Value |
|---------|-------|
| Namespace | `monitoring` |
| HelmRelease | `grafana` — `kube-prometheus-stack` sets `grafana.enabled: false`, so this release alone owns Grafana |
| Source of truth | `kubernetes/apps/monitoring/grafana/app/helmrelease.yaml` |
| Chart / app | chart `13.2.5`, Grafana `13.2.2`, image `grafana:13.2.2-distroless` `[verified 2026-09-22]` |
| Config store | sqlite on PVC `grafana-config` (`longhorn-static`, Bound) `[verified 2026-09-22]` |
| Storage model | **unified storage** — `dashboard.grafana.app` resources |
| Dashboards | **72** — identical via `/api/search` and via the unified-storage API `[verified 2026-09-22]` |
| Provisioned of those | **65** (`managedBy: classic-file-provisioning`); 7 carry no manager `[verified 2026-09-22]` |
| Datasource plugins loaded | **18** `[verified 2026-09-22]` |
| Provisioned datasources | **7** `[verified 2026-09-22]` |
| Critical dependency | `GF_PLUGINS_PREINSTALL_DISABLED: "true"` — see §3 |
| Related findings | `security_ref: F-58574ac3` (this SOP gap), `F-de4d92cd` (image variant evidence) |

### The three facts that drive everything below

**1. Provisioned dashboards live in unified storage, not the legacy tables.**
Dashboards are `dashboard.grafana.app` resources held in the sqlite **`resource`**
table `[recovered 2026-09-13]`. The legacy `dashboard` table (81 rows at the time)
and `dashboard_provisioning` table are **vestigial mirrors** the running
provisioner does not read `[recovered 2026-09-13]`. The proof at the time: deleting
a dashboard through the API returned `200` while its row **remained** in the legacy
`dashboard` table, and a legacy-only dashboard id was absent from unified storage
entirely.

Corroborating measurement today: unified storage and `/api/search` agree exactly
at **72** `[verified 2026-09-22]`. The API group exposes versions `v1`, `v1beta1`,
`v2`, `v2beta1`, `v2alpha1`, `v0alpha1`, preferred `v2` (note: **`v1alpha1` does
not exist** and returns `404`) `[verified 2026-09-22]`.

**2. Provisioning state is carried in resource annotations, not a join table.**
Each provisioned dashboard resource carries `[verified 2026-09-22]`:

| Annotation | Meaning |
|---|---|
| `grafana.app/managedBy` | `classic-file-provisioning` for sidecar/file-provisioned dashboards |
| `grafana.app/managerId` | the provider name, e.g. `sidecarProvider` |
| `grafana.app/sourcePath` | the file on disk the dashboard came from |
| `grafana.app/sourceChecksum` | md5 of that file — half of the skip test |
| `grafana.app/sourceTimestamp` | file mtime — the **other** half of the skip test |

Grafana gates "do I need to re-save this dashboard?" on **mtime AND checksum**.
A changed mtime alone forces a re-save attempt on every reconcile (30s) even when
the content is byte-identical — which is exactly how a stuck provisioner produces
~2,880 identical error lines a day `[recovered 2026-09-13]`.

**3. One `sourcePath` must map to exactly one resource.** When two resources
claim the same `sourcePath`, the provisioner resolves the file to one of them,
writes the *file's* uid onto it, and collides with the other — forever, every
30s. The affected dashboard is then **frozen**: it renders fine, but it can never
receive an upstream content update again, silently. Current state is healthy:
**65 distinct `sourcePath` values across 65 provisioned resources, zero claimed
by more than one resource**, and **0** `same uid already exists` errors in a
10-minute window `[verified 2026-09-22]`.

---

## 3) Blueprints

Source of truth: `kubernetes/apps/monitoring/grafana/app/helmrelease.yaml`.

Three provisioning mechanisms coexist. Know which one owns a dashboard before
you try to change it:

```yaml
spec:
  values:
    # (a) Chart-managed downloads: an init container fetches these to
    #     /var/lib/grafana/dashboards/<provider>/ at pod start.
    dashboards:
      default:
        some-dashboard:
          gnetId: 12345          # grafana.com dashboard id + revision
          revision: 1
          datasource: Prometheus
        another-one:
          url: https://raw.githubusercontent.com/<org>/<repo>/<ref>/dash.json
          datasource: Prometheus

    # (b) The providers that tell Grafana where to read those files from.
    dashboardProviders:
      dashboardproviders.yaml:
        apiVersion: 1
        providers:
          - name: default
            orgId: 1
            folder: ""
            type: file
            disableDeletion: false
            editable: true
            options:
              path: /var/lib/grafana/dashboards/default

    # (c) k8s-sidecar: watches the WHOLE cluster for ConfigMaps labelled
    #     grafana_dashboard and writes them into the sidecar folder. This is
    #     how kube-prometheus-stack's dashboards arrive — they are NOT in this
    #     repo and NOT in the grafana chart.
    sidecar:
      dashboards:
        enabled: true
        searchNamespace: ALL
        label: grafana_dashboard
        folderAnnotation: grafana_folder
        folder: /var/lib/grafana/dashboards/sidecar
        provider:
          disableDelete: true
          foldersFromFilesStructure: true

    env:
      # LOAD-BEARING. Not a tuning knob. See below.
      GF_PLUGINS_PREINSTALL_DISABLED: "true"
```

### `GF_PLUGINS_PREINSTALL_DISABLED` is load-bearing — including for dashboards

`[verified 2026-09-22]` that it is set on the live Deployment, alongside
`readOnlyRootFilesystem: true`.

Grafana's `plugin.backgroundinstaller` runs with `preinstall_auto_update=true`
by default. At **every pod start** it compares the 18 default preinstall plugins
against the grafana.com catalog. When the catalog is newer than the bundled
copy it **kills the running bundled backend first**, then tries to write the
replacement into `/usr/share/grafana/data/plugins-bundled` — which fails on a
read-only root filesystem (`unlinkat …: read-only file system`).

The datasource dies, and **every dashboard that renders through it goes blank**
while Grafana itself stays green: pod `3/3 Running`, `/api/health` → `database: ok`.
Measured on 2026-09-12: five backends (postgres, influxdb, loki, jaeger, mssql)
died this way and the dependent dashboards were empty for 2.5 days.

So: **any pod restart is a dashboard-availability event unless this var is set.**
Do not remove it, and do not assume a green pod means dashboards render. Full
mechanism and the datasource gate live in
[`grafana-image-changes.md`](grafana-image-changes.md).

---

## 4) Operational Instructions

### Adding or changing a provisioned dashboard (the normal path)

1. Identify the owning mechanism first (§3 a/b/c). If the dashboard arrives via
   a labelled ConfigMap from another chart (`kube-prometheus-stack`, Flux, …),
   **it is not yours to edit here** — change it at its source chart, or the
   sidecar will overwrite you on the next reconcile.
2. Edit `kubernetes/apps/monitoring/grafana/app/helmrelease.yaml`.
3. Commit and push. Flux reconciles via webhook — no manual apply.
4. Wait for the pod to roll (chart-downloaded dashboards are fetched by an init
   container, so `gnetId`/`url` changes need a restart; sidecar ConfigMap changes
   land within ~30s without one).
5. Run §6 verification. **`pod Running` is not verification.**

### Repairing stuck provisioning state (the dangerous path)

Read §7 and §8 first. In short, in this order:

1. Confirm the error is real and ongoing (§8 Diagnose Example 1).
2. Identify the resource **in unified storage**, never in the legacy tables.
3. Prefer an API-level remedy. If the API refuses, the remedy is a
   **helper Pod that mounts the PVC** (§8 Diagnose Example 2) — *not* an
   ephemeral debug container, which cannot work (§7).
4. Any write to `grafana.db` is operator-gated and needs a proven-queryable
   backup first.

```bash
# Standard GitOps flow for a dashboard change
git commit --only kubernetes/apps/monitoring/grafana/app/helmrelease.yaml -F msg.txt
git show --stat HEAD     # shared worktree: confirm only your file is in there
git push
mise exec -- flux -n monitoring reconcile hr grafana   # only if the webhook is slow
```

---

## 5) Examples

### Example A: add a grafana.com dashboard

Add under `values.dashboards.<provider>`, then verify it actually landed —
a wrong `gnetId`/`revision` pair makes the init container write a **0-byte
file**, and Grafana then logs `failed to load dashboard … error=EOF` on every
start while the dashboard silently does not exist. (This has happened here: a
`url` entry kept 404ing after upstream renamed the file.)

```bash
# after the roll — the count must have gone UP by exactly the number added
mise exec -- kubectl -n monitoring port-forward svc/grafana 33001:80 >/dev/null 2>&1 &
PF=$!; python3 -c "import time; time.sleep(4)"
U=$(mise exec -- kubectl -n monitoring get secret grafana-admin-secret -o jsonpath='{.data.admin-user}' | base64 -d)
P=$(mise exec -- kubectl -n monitoring get secret grafana-admin-secret -o jsonpath='{.data.admin-password}' | base64 -d)
curl -s -u "$U:$P" 'http://127.0.0.1:33001/api/search?type=dash-db&limit=5000' \
  | python3 -c 'import sys,json;print(len(json.load(sys.stdin)))'
kill $PF
```

### Example B: a dashboard that "exists" but never updates

This is the frozen-dashboard shape. The dashboard renders, so nothing alerts,
but its content is pinned to whenever provisioning last succeeded. Diagnose it
with §8 Example 1 — the tell is a **non-zero and non-decreasing** provisioning
error count paired with a dashboard `version` that never advances.

---

## 6) Verification Tests

### Test 1: dashboard inventory agrees across both layers

```bash
mise exec -- kubectl -n monitoring port-forward svc/grafana 33001:80 >/dev/null 2>&1 &
PF=$!; python3 -c "import time; time.sleep(4)"
U=$(mise exec -- kubectl -n monitoring get secret grafana-admin-secret -o jsonpath='{.data.admin-user}' | base64 -d)
P=$(mise exec -- kubectl -n monitoring get secret grafana-admin-secret -o jsonpath='{.data.admin-password}' | base64 -d)

echo -n "classic /api/search : "
curl -s -u "$U:$P" 'http://127.0.0.1:33001/api/search?type=dash-db&limit=5000' \
  | python3 -c 'import sys,json;print(len(json.load(sys.stdin)))'

echo -n "unified storage     : "
curl -s -u "$U:$P" \
  'http://127.0.0.1:33001/apis/dashboard.grafana.app/v1beta1/namespaces/default/dashboards?limit=5000' \
  | python3 -c 'import sys,json;print(len(json.load(sys.stdin).get("items",[])))'
kill $PF
```

Expected:
- Both numbers equal. Baseline **72 / 72** `[verified 2026-09-22]`.

If failed:
- A mismatch means one layer holds entries the other does not — usually
  legacy-only leftovers. Do **not** "fix" it by deleting legacy rows; see §7.

### Test 2: no `sourcePath` is claimed twice (the freeze precondition)

```bash
curl -s -u "$U:$P" \
  'http://127.0.0.1:33001/apis/dashboard.grafana.app/v1beta1/namespaces/default/dashboards?limit=5000' \
  | python3 -c '
import sys, json, collections
items = json.load(sys.stdin).get("items", [])
sp = collections.Counter()
for it in items:
    p = it["metadata"].get("annotations", {}).get("grafana.app/sourcePath")
    if p:
        sp[p] += 1
dups = {k: v for k, v in sp.items() if v > 1}
print("provisioned:", sum(sp.values()), "distinct sourcePaths:", len(sp))
print("DUPLICATES:", dups if dups else "none")
'
```

Expected:
- `DUPLICATES: none`. Baseline **65 provisioned / 65 distinct** `[verified 2026-09-22]`.

If failed:
- Every dashboard sharing a duplicated `sourcePath` is frozen. Go to §8
  Example 1 and do not touch the legacy tables.

### Test 3: the provisioner is not erroring

```bash
mise exec -- kubectl -n monitoring logs deploy/grafana -c grafana --since=10m \
  | grep -c "same uid already exists"
```

Expected:
- `0` `[verified 2026-09-22]`.

If failed:
- A non-zero count over 10 minutes at roughly 2/min is the 30s reconcile
  retrying a permanently failing save. §8 Example 1.

### Test 4: dashboards can still render (the datasource floor)

```bash
curl -s -u "$U:$P" 'http://127.0.0.1:33001/api/plugins?embedded=0&type=datasource' \
  | python3 -c 'import sys,json;print(len(json.load(sys.stdin)))'
curl -s -u "$U:$P" http://127.0.0.1:33001/api/datasources \
  | python3 -c 'import sys,json;print(len(json.load(sys.stdin)))'
```

Expected:
- `18` datasource plugins and `7` datasources `[verified 2026-09-22]`.
- A **drop** in either is a failure even though every dashboard still "exists" —
  this is the `GF_PLUGINS_PREINSTALL_DISABLED` failure mode from §3.

If failed:
- Confirm the env var is still set on the Deployment, then follow
  [`grafana-image-changes.md`](grafana-image-changes.md) §7.

---

## 7) Troubleshooting

| Symptom | Likely Cause | First Fix |
|---|---|---|
| Dashboard renders but never picks up upstream changes | Two unified-storage resources claim one `sourcePath`; every save collides | §6 Test 2, then §8 Example 1. **Do not** edit `dashboard_provisioning` |
| `same uid already exists` ~2/min forever | Same as above; the 30s reconcile retrying | §8 Example 1 |
| You deleted a legacy row and nothing changed | You edited a **vestigial mirror**; the provisioner reads unified storage | Re-do the analysis against `/apis/dashboard.grafana.app/...` |
| `DELETE /api/dashboards/uid/<uid>` → `400 provisioned dashboard cannot be deleted` | Grafana refuses to delete a managed resource on **both** the classic and `/apis` endpoints `[recovered 2026-09-13]` | Remove the provisioning **source** and let GC run, or detach `grafana.app/managedBy` first — operator decision, see below |
| Panels blank / "Plugin not registered" after a restart | Background plugin installer killed a bundled backend on a read-only rootfs | Confirm `GF_PLUGINS_PREINSTALL_DISABLED: "true"`; §3 |
| `failed to load dashboard … error=EOF` at every start | A `url`/`gnetId` download 404'd and wrote a 0-byte file | Fix the URL/revision in the HelmRelease |
| `kubectl exec … -- sh` fails: `executable file not found` | The image is `-distroless`: no shell, no `ls`, no `wget` | Use the API/port-forward forms in this SOP. Never reintroduce an exec form |

### The two remedies when the API refuses a delete

Both mutate state and are **operator go/no-go**, never unattended:

- **(i) Detach then delete** — `PATCH` the `grafana.app/managedBy` annotation
  off the resource, then delete it. HTTP-only, but it mutates provisioning
  metadata and is unvalidated here `[recovered 2026-09-13]`.
- **(ii) Remove the source, let GC run** — delete the provisioning source file
  (or its ConfigMap) so Grafana garbage-collects the resource, then restore the
  source. Larger blast radius, and if the source is a ConfigMap owned by another
  chart, you are editing someone else's chart output.

Writing directly to the unified-storage `resource` table was considered and
**rejected** — it is the layer everything else depends on `[recovered 2026-09-13]`.

---

## 8) Diagnose Examples

### Diagnose Example 1: a frozen / erroring provisioned dashboard

```bash
mise exec -- kubectl -n monitoring port-forward svc/grafana 33001:80 >/dev/null 2>&1 &
PF=$!; python3 -c "import time; time.sleep(4)"
U=$(mise exec -- kubectl -n monitoring get secret grafana-admin-secret -o jsonpath='{.data.admin-user}' | base64 -d)
P=$(mise exec -- kubectl -n monitoring get secret grafana-admin-secret -o jsonpath='{.data.admin-password}' | base64 -d)

# 1. Who claims this source file? (substitute the filename from the error)
curl -s -u "$U:$P" \
  'http://127.0.0.1:33001/apis/dashboard.grafana.app/v1beta1/namespaces/default/dashboards?limit=5000' \
  | python3 -c '
import sys, json
needle = "prometheus.json"
for it in json.load(sys.stdin).get("items", []):
    a = it["metadata"].get("annotations", {})
    if a.get("grafana.app/sourcePath", "").endswith(needle):
        print(it["metadata"]["name"],
              "|", a.get("grafana.app/managedBy"),
              "|", a.get("grafana.app/managerId"),
              "| checksum", a.get("grafana.app/sourceChecksum"),
              "| ts", a.get("grafana.app/sourceTimestamp"))
'
# 2. Is the dashboard actually advancing, or frozen?
curl -s -u "$U:$P" http://127.0.0.1:33001/api/dashboards/uid/<uid> \
  | python3 -c 'import sys,json;d=json.load(sys.stdin);print("version",d["dashboard"]["version"],"|",d["meta"]["updated"])'
kill $PF
```

Expected:
- **Exactly one** resource per `sourcePath`. Healthy reference: `prometheus.json`
  → a single resource managed by `sidecarProvider` `[verified 2026-09-22]`.
- Two or more resources on one path confirms the collision. The one whose
  `sourceTimestamp`/`sourceChecksum` match the current file is the **keeper**;
  the stale one is the defect.

If unclear:
- Compare `grafana.app/sourceChecksum` against the md5 of the file the sidecar
  currently writes. Identical checksum + stale `version` = frozen, not healthy.
- **Record which resource you intend to remove, and why, before touching
  anything.** A predecessor plan named the *healthy* record for deletion; had it
  run, it would have destroyed the good mapping and left the broken one.

### Diagnose Example 2: reading `grafana.db` — and the trap

The image is `-distroless` (no shell, no `sqlite3`) and the DB is on a Longhorn
PVC. The obvious approach is an ephemeral debug container sharing the pod's PID
namespace and reaching the file through `/proc/1/root`. **It works for reading
bytes out, and it cannot be used to query or write the database.**

```bash
# READ-OUT ONLY — copy the file off and analyse it on the Mac.
POD=$(mise exec -- kubectl -n monitoring get pods -l app.kubernetes.io/name=grafana \
        -o jsonpath='{.items[0].metadata.name}')
mise exec -- kubectl debug -n monitoring "$POD" --image=alpine:3 --target=grafana \
  -c dbread -- sh -c 'sleep 300'
mise exec -- kubectl exec -n monitoring "$POD" -c dbread -- \
  sh -c 'cd /proc/1/root/var/lib/grafana && tar cf - grafana.db' > /tmp/gdb.tar
```

> **NEVER run `kill 1` inside that ephemeral container.** `--target` shares the
> PID namespace, so PID 1 is *Grafana's* process. Doing so restarted Grafana on
> 2026-09-12. Let the `sleep` expire or exit the shell.

**Why sqlite cannot open the DB through `/proc/1/root`** `[recovered 2026-09-13]`.
Measured in this order, so the conclusion is not a guess:

```
ls / head / open(path,'r+b')   on grafana.db         -> OK (readable AND writable)
touch <pvcdir>/.writetest                            -> WRITABLE
sqlite3.connect('<pvcdir>/grafana.db')               -> "unable to open database file"
sqlite3.connect('<pvcdir>/grafana.db')  via chdir    -> "unable to open database file"
sqlite3.connect('/proc/1/root/tmp/_probe.db')        -> OK     <- /proc is NOT the blocker
sqlite3.connect('<pvcdir>/_probe.db')   (brand new)  -> "unable to open database file"
```

The last two lines are decisive: sqlite works fine under `/proc` on an emptyDir,
and fails on the PVC directory **even for a brand-new file**. So it is neither
the `/proc` prefix nor the existing database — sqlite must open the *containing
directory* (for the journal and fsync) and that fails across the mount boundary
into another container's Longhorn mount. Plain `open()` never touches the
directory, which is why raw reads mislead here.

**Therefore, to query or write, use a helper Pod that mounts the PVC properly:**

- **M2 (recommended)** — suspend the HelmRelease, scale Grafana to 0, mount
  `grafana-config` in a helper Pod, edit, scale back. Zero concurrency risk and
  zero `Multi-Attach` risk (the volume detaches first), at ~2 minutes of
  downtime. The Deployment is Flux-managed, so **suspend the HelmRelease first**
  or the scale-down races the next reconcile.
- **M1** — helper Pod mounting `grafana-config` alongside a running Grafana.
  No downtime, but the PVC is **RWO Longhorn**: the helper *must* be pinned
  (`nodeName`) to Grafana's node or the volume goes `Multi-Attach` and Grafana
  goes down. See [`longhorn-rwo-multi-attach.md`](longhorn-rwo-multi-attach.md).

**Do NOT copy-out / edit / copy-back.** Grafana writes to this database
continuously, so restoring an edited copy silently discards every write made in
between.

For a read-only inspection of the PVC without any debug container, mount the
claim read-only in a throwaway Pod — the pattern is in
[`grafana-image-changes.md`](grafana-image-changes.md) §8 command C.

---

## 9) Health Check

```bash
mise exec -- kubectl -n monitoring get pods -l app.kubernetes.io/name=grafana
mise exec -- kubectl -n monitoring get hr grafana
mise exec -- kubectl -n monitoring get pvc grafana-config
mise exec -- kubectl -n monitoring get deploy grafana -o json | python3 -c '
import sys, json
d = json.load(sys.stdin)
for c in d["spec"]["template"]["spec"]["containers"]:
    if c["name"] == "grafana":
        env = {e["name"]: e.get("value") for e in c.get("env", [])}
        print("GF_PLUGINS_PREINSTALL_DISABLED =", env.get("GF_PLUGINS_PREINSTALL_DISABLED"))
'
mise exec -- kubectl -n monitoring logs deploy/grafana -c grafana --since=30m \
  | grep -c "same uid already exists"
```

Expected:
- Pod `3/3 Running`, 0 restarts; HelmRelease `Ready=True`; PVC `Bound`.
- `GF_PLUGINS_PREINSTALL_DISABLED = true`.
- `0` provisioning collisions.
- Plus §6 Tests 1, 2 and 4 at their baselines (72/72, no duplicates, 18 and 7).

All of the first three can pass while every dashboard is blank — this section is
a liveness check, and §6 Test 4 is the one that actually protects rendering.

---

## 10) Security Check

```bash
# 1. Admin credentials come from a Secret and must never be echoed or pasted.
mise exec -- kubectl -n monitoring get secret grafana-admin-secret -o name

# 2. Grafana stays on the LAN-only Gateway.
mise exec -- kubectl -n monitoring get httproute grafana \
  -o jsonpath='{.spec.parentRefs[*].name}{"\n"}'

# 3. No unencrypted secrets in the provisioning values.
grep -nE "password|token|secret" kubernetes/apps/monitoring/grafana/app/helmrelease.yaml \
  | grep -vE '\$__env\{|\$__file\{|existingSecret|envFromSecret|secretName|\$\{'
```

Expected:
- `parentRefs` → `envoy-internal` (LAN-only). Reparenting to `envoy-external`
  is out of scope here and needs its own review.
- Command 3 returns no output — every credential is a `$__env{}` / `$__file{}`
  reference or a SOPS-encrypted Secret, never a literal.
- Dashboard JSON fetched by `gnetId`/`url` is **executable-adjacent third-party
  content** pulled at pod start. Pin `revision` (or a commit ref in the `url`),
  never a moving branch tip, so the dashboard that renders is the one that was
  reviewed. See [`runtime-dependency-pinning.md`](runtime-dependency-pinning.md).
- Vulnerability figures for any Grafana image belong on the finding record, never
  in this SOP or a commit message —
  [`vulnerability-disclosure.md`](vulnerability-disclosure.md).

---

## 11) Rollback Plan

**For a dashboard/provisioning values change** — ordinary git revert:

```bash
git revert <sha> && git push
mise exec -- flux -n monitoring reconcile ks grafana --with-source
mise exec -- flux -n monitoring reconcile hr grafana
# then re-run §6 Tests 1-4 — a rollback is a change and needs the same gate
```

**For a state repair against `grafana.db`** there is no commit to revert. The
rollback is the pre-change backup, and it is only a backup if it was proven
**queryable** (row counts read back), not merely openable —
`pragma integrity_check` returning `ok` on a copy taken from a live sqlite file
is necessary but not sufficient.

**Do not downgrade the Grafana version as a rollback.** Grafana 13 migrates the
sqlite schema on boot and the migration is forward-only. Roll the variant/tag
within the same version instead —
[`grafana-image-changes.md`](grafana-image-changes.md) §11.

If the config store itself is damaged, the fallback is the `grafana-config`
Longhorn backup (03:00 daily) — [`backup.md`](backup.md).

---

## 12) References

- `kubernetes/apps/monitoring/grafana/app/helmrelease.yaml` — provisioning values and the comment block at the image tag
- [`grafana-image-changes.md`](grafana-image-changes.md) — the datasource pre-flight gate; owns any image/tag/variant change
- [`monitoring.md`](monitoring.md) — Grafana access recipes, image-variant evidence
- [`longhorn-rwo-multi-attach.md`](longhorn-rwo-multi-attach.md) — why an M1 helper Pod must be node-pinned
- [`longhorn.md`](longhorn.md) — the `grafana-config` static PV/PVC pattern
- [`verification-contents-not-shape.md`](verification-contents-not-shape.md) — why "pod Running" is not verification
- [`runtime-dependency-pinning.md`](runtime-dependency-pinning.md) — pinning third-party content fetched at pod start
- [`vulnerability-disclosure.md`](vulnerability-disclosure.md) — where scan figures live
- Findings: `security_ref: F-58574ac3` (this SOP gap), `F-de4d92cd` (image variant evidence)
- Deleted plan files recovered for this SOP: `runbooks/maintenance/plans/grafana-duplicate-provisioning-row.md` and `grafana-orphan-dashboard-uid.md` — recoverable via `git show d3063e44^:<path>` / `a0556c6d^:<path>`

---

## Version History

| Version | Date | Change |
|---------|------|--------|
| `2026.09.22` | 2026-09-22 | Initial SOP (`F-58574ac3`). Written by recovering the deleted `grafana-duplicate-provisioning-row` / `grafana-orphan-dashboard-uid` plan files from git history and re-verifying every live-checkable claim: Grafana 13 unified storage and the vestigial legacy tables, the provisioning annotations that carry `sourcePath`/checksum/mtime, the one-path-one-resource rule and the frozen-dashboard failure, the `/proc/1/root` sqlite trap and the M1/M2 helper-Pod remedies, and `GF_PLUGINS_PREINSTALL_DISABLED` as load-bearing for dashboard rendering. Baselines measured 2026-09-22: 72 dashboards (both layers), 65 provisioned / 65 distinct source paths, 18 datasource plugins, 7 datasources, 0 provisioning collisions. |

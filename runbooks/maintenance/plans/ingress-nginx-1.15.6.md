---
plan_id: ingress-nginx-1.15.6
component: ingress-nginx
pr: null                            # NO Renovate PR exists. Upstream kubernetes/ingress-nginx is
                                    # ARCHIVED (read-only since 2026-03-24); final release is chart
                                    # 4.15.1 / controller v1.15.1 — exactly what we run. Renovate
                                    # reports "4.15.1 ✅ up-to-date". This plan was dispatched off a
                                    # Trivy CVE finding, not a held Renovate version PR.
kind: image                         # CVE remediation via controller image override; chart wiring
                                    # (4.15.1) is unchanged in the recommended path.
current: "v1.15.1"                  # registry.k8s.io/ingress-nginx/controller:v1.15.1@sha256:594ceea…
target: "v1.15.6-chainguard-fork"   # controller-v1.15.6 from chainguard-forks/ingress-nginx
                                    # (cgr.dev/<org>/ingress-nginx-controller). SOURCE change, not a
                                    # same-registry bump — see §1 blocker.
update_type: patch                  # 1.15.1→1.15.6 is patch-level by semver, BUT it is a supply-chain
                                    # SOURCE swap (registry.k8s.io → cgr.dev fork). Treat as attended.
risk: high                          # cluster-wide ingress infra, BOTH classes; external feeds the
                                    # Cloudflare tunnel (every externally-reachable app); unproven
                                    # fork/distroless image against a heavy custom config surface.
est_duration_min: 40
needs_reboot: false
touches:
  namespaces: [network]
  resources:
    - helmrelease/internal-ingress-nginx        # network ns
    - helmrelease/external-ingress-nginx        # network ns
    - deployment/internal-ingress-nginx-controller
    - deployment/external-ingress-nginx-controller
    - service/internal-ingress-nginx-controller # LB 192.168.55.100
    - service/external-ingress-nginx-controller # LB 192.168.55.102
    - validatingwebhookconfiguration/internal-ingress-nginx-admission
    - validatingwebhookconfiguration/external-ingress-nginx-admission
    - ingressclass/internal                     # cluster-scoped, default class
    - ingressclass/external                     # cluster-scoped
  shared: [ingress]                 # BLAST RADIUS: 102 Ingress objects (76 internal / 26 external).
                                    # A controller roll briefly perturbs L7 for that class. External
                                    # roll also perturbs the Cloudflare-tunnel data path.
depends_on: []
conflicts_with: []                  # no hard resource conflict, but DO NOT co-schedule with any plan
                                    # that (a) touches cloudflared / cert-manager / a public ingress,
                                    # or (b) verifies via an ingressed endpoint — its check will read
                                    # false during the ingress blip. See Interference notes.
status: draft
window: null                        # window agent assigns. SUGGEST: a no-reboot, OPERATOR-PRESENT
                                    # slot (e.g. sat-early). NOT auto/unattended — supply-chain source
                                    # change + public-ingress blast radius + an operator go/no-go on
                                    # trusting the fork image (§Pre-checks P0).
auto_execute: false
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/maintenance-windows.md
  - docs/sops/cloudflare.md
generated: "2026-08-06"
---

# ingress-nginx controller v1.15.1 → v1.15.6 (Chainguard fork) — CVE remediation

## 1) Summary & why held

**What triggered this.** A fresh Trivy scan (2026-08-06) of the running
controller image `registry.k8s.io/ingress-nginx/controller:v1.15.1`
(`@sha256:594ceea76b01c592858f803f9ff4d2cb40542cae2060410b2c95f75907d659e1`,
identical on **both** the `internal` and `external` releases) flags **3 fixable
CRITICAL CVEs**. Candidate IDs from public advisories in this window:
`CVE-2026-9256` (nginx rewrite heap overflow, fixed in controller v1.15.6),
plus the ingress-nginx configuration-injection class (`CVE-2026-3288` /
`CVE-2026-24512` / `CVE-2026-4342`). **The executor MUST open the actual Trivy
report and read the exact 3 CVE IDs and each one's `FixedVersion` field before
running** — that determines whether the v1.15.6 fork image clears *all three*
(version-attribution rule: do not act on an unverified "X→Y").

**Why this is not a normal held update (the real blocker).** There is **no
Renovate PR and no upstream fix path**:

- `kubernetes/ingress-nginx` was **archived (read-only) on 2026-03-24**. Its
  **final** release is **chart 4.15.1 / controller v1.15.1** — precisely what we
  run. Verified against the live Helm index
  (`https://kubernetes.github.io/ingress-nginx/index.yaml`): newest entry is
  `4.15.1` (appVersion `1.15.1`, created 2026-03-19). Nothing newer exists.
- Our version-check agrees: `internal-ingress-nginx` and
  `external-ingress-nginx` both report **`4.15.1 ✅ (up-to-date)`**. The
  auto-updater has nothing to bump; the official supply chain will **never**
  ship these fixes.
- The only place the fixes exist is a **fork**: Chainguard maintains
  `github.com/chainguard-forks/ingress-nginx` (the designated continuation named
  in upstream's retirement notice); `controller-v1.15.6` backports the fix and
  rebuilds on Chainguard's hardened/distroless base (which also clears
  base-layer criticals). Image path: **`cgr.dev/<ORG>/ingress-nginx-controller`**
  (an authenticated Chainguard-org registry; the free public catalog exposes
  `cgr.dev/chainguard/ingress-nginx-controller` but generally only `:latest`,
  not pinned historical tags).

So "hold" here is honest and correct: Trivy sees fixable criticals, but the
fixed artifact lives **outside the configured supply chain**. Remediation is a
**source-replacement decision**, not a version bump — hence a `draft` plan with a
mandatory operator go/no-go (§Pre-checks P0), not an auto-merge.

**Recommended path (this plan).** Keep both HelmReleases **on chart 4.15.1**
(all tuned config, annotations, LB IPs, `cloudflared` dependency, cert-manager
default cert stay byte-for-byte identical) and **override only
`controller.image`** to the Chainguard fork controller v1.15.6, **digest-pinned**.
Minimal diff, GitOps-clean, per-class reversible. **Sequence internal → external**
(never both at once).

**Alternatives the operator may pick instead (document, don't silently choose):**
- *B — Repoint the chart:* add the fork's Helm repo, bump chart to 4.15.5/4.15.6.
  Larger supply-chain change; only if the fork ships a chart we vet.
- *C — Migrate controller:* to InGate (the ingress-nginx successor) or Cilium
  Gateway API. Large project — out of scope for one window.
- *D — Accept the risk (AR entry):* weak here. Two candidate CVEs are
  config/rewrite-annotation injection, and this cluster runs
  `allow-snippet-annotations: true` + `annotations-risk-level: Critical` on
  **both** classes → *more* exposed, not less. Not recommended without compensating
  controls.

**Biggest gotcha.** The fork image is **distroless / non-root / no shell** and a
different build than `registry.k8s.io`. Our config surface is heavy — brotli,
OCSP stapling, real-IP, `use-forwarded-headers`, `CF-Connecting-IP`
forwarded-for, snippet annotations, a `default-ssl-certificate` extraArg. The new
image must load **all** of it and pass readiness. Both controllers are
**single-replica**, but the Deployment RollingUpdate surges a new pod *before*
terminating the old, so a **bad fork image stalls the rollout with the old pod
still Serving** rather than dropping ingress — good failure mode, but it means
"looks stuck" == "image rejected", verify before declaring success.

## 2) Pre-checks

**P0 — OPERATOR GO/NO-GO (blocking).** This plan points production ingress
(including the public, Cloudflare-tunnel-facing `external` class) at a
**third-party fork image**. Do not proceed without explicit operator approval of:
(a) trusting `cgr.dev` / the Chainguard fork as the controller supply chain, and
(b) that a Chainguard **org + pull credentials** exist for a **pinned** tag
(`cgr.dev/<org>/ingress-nginx-controller:v1.15.6`). If no org/creds, the plan is
**blocked** on provisioning them (or falls back to Alternative B/C/D). Record the
decision in the window log.

```bash
# --- confirm the exact CVEs + their fixed versions (do NOT act on hearsay) ---
# Re-scan the running digest and read the 3 CRITICALs + FixedVersion column:
trivy image --severity CRITICAL --ignore-unfixed \
  registry.k8s.io/ingress-nginx/controller:v1.15.1@sha256:594ceea76b01c592858f803f9ff4d2cb40542cae2060410b2c95f75907d659e1
# → note each CVE-ID and its FixedVersion; confirm v1.15.6 satisfies all three.

# --- baseline: both releases Ready, chart 4.15.1, single replica each ---
kubectl -n network get helmrelease internal-ingress-nginx external-ingress-nginx \
  -o custom-columns=NAME:.metadata.name,CHART:.status.history[0].chartVersion,READY:'.status.conditions[?(@.type=="Ready")].status'
kubectl -n network get deploy -l app.kubernetes.io/name=ingress-nginx \
  -o custom-columns=NAME:.metadata.name,READY:.status.readyReplicas,IMAGE:.spec.template.spec.containers[0].image

# --- current running image digest on each controller (rollback anchor) ---
kubectl -n network get pods -l app.kubernetes.io/name=ingress-nginx \
  -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.containers[0].image}{"\n"}{end}'

# --- ingress inventory (blast radius) ---
kubectl get ingress -A -o jsonpath='{range .items[*]}{.spec.ingressClassName}{"\n"}{end}' | sort | uniq -c
#   expect ~ 76 internal, 26 external

# --- external path health BEFORE (so we can prove we didn't break it) ---
flux -n network get helmrelease external-ingress-nginx
kubectl -n network get pods -l app.kubernetes.io/name=cloudflared   # tunnel up (external dependsOn it)
# hit a known internal ingress and a known external (Cloudflare) hostname, capture 200/302:
#   curl -sko /dev/null -w '%{http_code}\n' https://<an-internal-app>.${SECRET_DOMAIN}
#   curl -sko /dev/null -w '%{http_code}\n' https://<an-external-app>.${SECRET_DOMAIN}

# --- cert-manager default cert still present (extraArg default-ssl-certificate) ---
kubectl -n cert-manager get secret ${SECRET_DOMAIN//./-}-production-tls -o name

# --- confirm the fork tag is pullable with our creds (do this before committing) ---
crane digest cgr.dev/<ORG>/ingress-nginx-controller:v1.15.6   # or: docker manifest inspect …
```

Go criteria: P0 approved + creds confirmed; both HRs Ready @4.15.1; both
controllers 1/1; the 3 CVE IDs + FixedVersions verified against v1.15.6; the fork
tag resolves to a **digest** (pin it); pre-change internal+external curls return
success; cert-manager default cert present.

## 3) Steps

> GitOps only. **Sequence internal → external** (prove the fork image on the
> lower-blast-radius class first). If a pull secret is needed for `cgr.dev`, wire
> it via SOPS as an `imagePullSecrets` entry — never inline a token. Delegate
> cluster application to cberg-agent; attended window only.

**Step 1 — silence expected ingress rollout noise + drop an update marker**
(SOP `application-update.md` §1). Scope to `namespace=network`:
```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-alertmanager 9093:9093 &
NOW=$(python3 -c "from datetime import *;print(datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z'))")
END=$(python3 -c "from datetime import *;print((datetime.now(timezone.utc)+timedelta(hours=3)).strftime('%Y-%m-%dT%H:%M:%S.000Z'))")
curl -s -X POST localhost:9093/api/v2/silences -H 'Content-Type: application/json' -d '{
  "matchers":[{"name":"namespace","value":"network","isRegex":false,"isEqual":true},
              {"name":"alertname","value":"Kube(Pod|Deployment).*|TargetDown|NGINX.*|Ingress.*","isRegex":true,"isEqual":true}],
  "startsAt":"'$NOW'","endsAt":"'$END'","createdBy":"maintenance-window",
  "comment":"ingress-nginx v1.15.1->v1.15.6(fork) controller image swap — rollout noise. auto-expires 3h"}'
runbooks/update-marker.sh add ingress-nginx network 3 "controller image v1.15.1->v1.15.6 fork (CVE)"
```

**Step 2 — (only if cgr.dev needs auth) create the pull secret via SOPS.** Put a
`docker-registry` secret in `kubernetes/apps/network/.../` per the repo SOPS
workflow (CLAUDE.md “SOPS Encryption Rules”), and reference it below via
`controller.image.pullSecrets`. Skip if the org image is already pullable
cluster-wide.

**Step 3 — INTERNAL first: override the controller image.** Edit
`kubernetes/apps/network/internal/ingress-nginx/helmrelease.yaml`, under
`spec.values.controller`, add an `image:` block (leave everything else — config,
annotations, LB IP, metrics — untouched):
```yaml
    controller:
      image:
        registry: cgr.dev
        image: <ORG>/ingress-nginx-controller
        tag: "v1.15.6"
        digest: "sha256:<PINNED_DIGEST_FROM_PRECHECK>"   # pin — do not float :tag
        chroot: false            # fork publishes a non-chroot image; set to match what you pinned
        digestChroot: ""         # clear the chart's default upstream chroot digest
        # pullSecrets: [{ name: cgr-pull }]              # only if Step 2 created one
      # (all existing controller.* keys stay exactly as-is)
```
```bash
git add kubernetes/apps/network/internal/ingress-nginx/helmrelease.yaml
git commit -m "fix(internal-ingress-nginx): controller image v1.15.1 -> v1.15.6 (chainguard fork, CVE remediation)"
git push        # main; no feature branches (repo convention)
```

**Step 4 — watch the INTERNAL rollout.** Single replica surges before terminating:
```bash
flux -n network reconcile helmrelease internal-ingress-nginx --with-source
kubectl -n network rollout status deploy/internal-ingress-nginx-controller --timeout=5m
kubectl -n network get pods -l app.kubernetes.io/instance=internal-ingress-nginx -w
```
If the new pod does **not** reach Ready, the old pod keeps Serving (no outage) —
`kubectl -n network logs deploy/internal-ingress-nginx-controller` for the
config-load error, then **roll back internal** (§5) before touching external.

**Step 5 — VERIFY internal fully (Section 4, internal half) BEFORE external.**
Only proceed once internal is proven on the fork image.

**Step 6 — EXTERNAL: repeat the override.** Edit
`kubernetes/apps/network/external/ingress-nginx/helmrelease.yaml` with the **same**
`controller.image` block, commit, push:
```bash
git add kubernetes/apps/network/external/ingress-nginx/helmrelease.yaml
git commit -m "fix(external-ingress-nginx): controller image v1.15.1 -> v1.15.6 (chainguard fork, CVE remediation)"
git push
flux -n network reconcile helmrelease external-ingress-nginx --with-source
kubectl -n network rollout status deploy/external-ingress-nginx-controller --timeout=5m
```

**Step 7 — on success, restore + clear noise.**
```bash
curl -s localhost:9093/api/v2/silences | python3 -c "import sys,json;[print(s['id']) for s in json.load(sys.stdin) if s['status']['state']=='active' and 'ingress-nginx' in s.get('comment','')]" | xargs -I{} curl -s -X DELETE localhost:9093/api/v2/silences/{}
runbooks/update-marker.sh clear ingress-nginx
```

## 4) Verification

```bash
# --- per class: HR Ready @4.15.1 (chart unchanged), controller on the fork digest ---
for hr in internal external; do
  kubectl -n network get helmrelease ${hr}-ingress-nginx \
    -o jsonpath="{.metadata.name}: Ready={.status.conditions[?(@.type=='Ready')].status} chart={.status.history[0].chartVersion}{'\n'}"
  kubectl -n network get deploy ${hr}-ingress-nginx-controller \
    -o jsonpath="${hr} image={.spec.template.spec.containers[0].image}{'\n'}"   # cgr.dev/...:v1.15.6@sha256:<pinned>
  kubectl -n network get pods -l app.kubernetes.io/instance=${hr}-ingress-nginx \
    -o custom-columns=POD:.metadata.name,READY:.status.containerStatuses[0].ready,RESTARTS:.status.containerStatuses[0].restartCount
done

# --- config actually loaded (no silent drop of brotli/real-ip/snippet config) ---
kubectl -n network logs deploy/internal-ingress-nginx-controller | grep -iE 'reload|error|backend reload' | tail
kubectl -n network logs deploy/external-ingress-nginx-controller | grep -iE 'reload|error' | tail
# Expect "Configuration changes detected, backing off / backend reload successful", no config errors.

# --- INTERNAL serves L7 (do in Step 5) ---
curl -sko /dev/null -w 'internal %{http_code}\n' https://<an-internal-app>.${SECRET_DOMAIN}   # 200/302 as before
kubectl -n network get svc internal-ingress-nginx-controller -o jsonpath='{.status.loadBalancer.ingress[0].ip}{"\n"}'  # 192.168.55.100

# --- EXTERNAL serves L7 through the Cloudflare tunnel (do after Step 6) ---
kubectl -n network get pods -l app.kubernetes.io/name=cloudflared          # still Ready
curl -sko /dev/null -w 'external %{http_code}\n' https://<an-external-app>.${SECRET_DOMAIN}   # 200/302 from the public edge
kubectl -n network get svc external-ingress-nginx-controller -o jsonpath='{.status.loadBalancer.ingress[0].ip}{"\n"}' # 192.168.55.102

# --- TLS intact (default-ssl-certificate extraArg still honored) ---
echo | openssl s_client -connect 192.168.55.100:443 -servername <an-internal-app>.${SECRET_DOMAIN} 2>/dev/null | openssl x509 -noout -issuer -dates

# --- admission webhook healthy (new/changed Ingress can still be admitted) ---
kubectl -n network get validatingwebhookconfiguration | grep ingress-nginx
kubectl get events -A --field-selector type=Warning --sort-by=.lastTimestamp | grep -i admission | tail

# --- CVE actually gone: re-scan the now-running image ---
trivy image --severity CRITICAL --ignore-unfixed cgr.dev/<ORG>/ingress-nginx-controller:v1.15.6@sha256:<pinned>
#   → the 3 previously-fixable CRITICALs no longer present.
```

Success = both HRs Ready @ chart 4.15.1; both controllers on
`cgr.dev/...ingress-nginx-controller:v1.15.6@<pinned digest>`, 1/1, 0 restarts
after settle; config reloads clean (brotli/real-IP/snippet/CF-Connecting-IP all
loaded); internal **and** external return the same HTTP codes as the pre-check;
TLS served by the cert-manager default cert; admission webhooks healthy; Trivy
re-scan shows the 3 criticals cleared.

## 5) Rollback

Per class, independently (that's why we sequenced). Trigger if: rollout stalls
(new pod not Ready), config reload errors, an ingress class stops serving, TLS
breaks, or the external curl fails through Cloudflare.

```bash
# Revert the offending class's commit (chart 4.15.1 unchanged → this just drops
# the controller.image override, back to registry.k8s.io/...:v1.15.1@sha256:594ceea…):
git revert --no-edit <internal-or-external-commit-sha>
git push origin main
flux -n network reconcile helmrelease <internal|external>-ingress-nginx --with-source
kubectl -n network rollout status deploy/<internal|external>-ingress-nginx-controller --timeout=5m
```

Because the old pod keeps Serving until the new one is Ready, a stalled rollout
is **not** an outage — you can revert calmly. If Helm wedges `pending-upgrade`:
```bash
helm -n network history <internal|external>-ingress-nginx
helm -n network rollback <internal|external>-ingress-nginx <last-deployed-rev> --wait=false
flux -n network reconcile helmrelease <internal|external>-ingress-nginx --force
```

Confirm restored: HR Ready @4.15.1, controller image back to
`registry.k8s.io/ingress-nginx/controller:v1.15.1@sha256:594ceea…`, the class's
representative curl returns its pre-check code. Then drop the silence + clear the
marker (Step 7). **Note:** reverting returns the CVE exposure — if rollback is
needed, the finding stays open and routes to Alternative B/C/D.

## 6) Interference notes

- **Cluster-wide ingress infra (`shared: [ingress]`).** These two controllers
  front **102 Ingress objects** (76 internal / 26 external). Each controller roll
  briefly perturbs L7 for its class. Because both are **single-replica** with
  surge-before-terminate, expect **near-zero** downtime **if** the fork image
  comes up Ready — and a **stalled rollout, not an outage,** if it doesn't.
- **External roll also perturbs the public path.** `external` sits behind the
  **Cloudflare tunnel** (`external-ingress-nginx` `dependsOn: cloudflared`, LB
  `192.168.55.102`, `external.${SECRET_DOMAIN}` via external-dns). A bad external
  controller = every publicly-reachable app returns 502 at the edge. This is why
  external goes **second, only after internal is proven,** and why the window
  should be **operator-present**.
- **Sequence, never parallel.** internal → verify → external. Do not bump both
  HelmReleases in one commit.
- **Do NOT co-schedule** with any plan touching `cloudflared`, `cert-manager`
  (the default-ssl-certificate secret), or any single ingressed app, and not with
  any plan whose **verification hits an ingressed endpoint** — during either roll
  its probe can read false-negative. If kube-prometheus-stack is co-scheduled,
  order this one so their blind windows don't overlap.
- **Supply-chain change, not a version bump.** After this lands, the controller
  image is served from `cgr.dev` (Chainguard fork), not `registry.k8s.io`. Update
  the version-check / image-provenance expectations so the next sweep doesn't flag
  the fork registry as drift. The upstream chart stays 4.15.1 and will remain
  "up-to-date" forever (archived) — the *image* is now the thing to track.
- **kube-webhook-certgen image untouched.** The chart's
  `admissionWebhooks.patch.image` (`registry.k8s.io/ingress-nginx/kube-webhook-certgen`)
  is a separate image and is **not** changed here. If Trivy also flags it,
  file/track that separately — it is not one of the 3 controller criticals this
  plan addresses.
- `needs_reboot: false` — no node reboot. `risk: high` + public blast radius +
  supply-chain source change route this to an operator-present slot despite the
  small semver delta.

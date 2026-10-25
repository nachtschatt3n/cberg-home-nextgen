---
plan_id: docs-site-9.8.0
component: docs-site                  # HelmRelease monitoring/docs-site (bjw-s app-template 5.3.0); image squidfunk/mkdocs-material
                                      # is the BUILD initContainer only (nginx-unprivileged serves; not touched here)
pr: 429                               # Renovate "feat(container): update squidfunk/mkdocs-material ( 9.7.7 → 9.8.0 )",
                                      # one-line diff to helmrelease.yaml, all 4 checks SUCCESS incl. Flate Render Gate (measured 2026-10-25)
kind: image
current: "9.7.7"                      # MEASURED live 2026-10-25: initContainer image squidfunk/mkdocs-material:9.7.7,
                                      # imageID index digest sha256:51b87149d227691486b5f08993d28c65ca7e4990010664b697265b8e6fcd5287;
                                      # served <meta name="generator"> = "mkdocs-1.6.1, mkdocs-material-9.7.7"
target: "9.8.0"                       # Coverage asked for "9.8" (a FLOATING series tag). Resolved to the fixed tag 9.8.0:
                                      # Docker Hub tags 9.8.0 / 9.8 / 9 / latest all = index digest
                                      # sha256:dc3b5de76c6e30d18dc0922d4c4a7bed817e5e155f9ff0e594a53eb56e537e64 (pushed 2026-10-24),
                                      # image label org.opencontainers.image.version=9.8.0, upstream CHANGELOG entry
                                      # "mkdocs-material-9.8.0 (2026-10-24)" — a GA release, no pre-release suffix.
update_type: minor
risk: low                             # stateless (emptyDir only), LAN-only docs site, RollingUpdate surge1/unavail0 keeps the OLD pod
                                      # serving if the new build fails; upstream Dockerfile byte-identical 9.7.7→9.8.0; local dry-build
                                      # of this repo with 9.8.0 produced the identical page set (§1.3). Hold was a false positive (§1.1).
est_duration_min: 20                  # 5 pre-checks/baseline, 2 merge, ~3 reconcile + init build (clone + ~13 s mkdocs), 7 verification, 3 buffer
needs_reboot: false
touches:
  namespaces: [monitoring]
  resources:                          # every object verified to EXIST live 2026-10-25 (kubectl get)
    - helmrelease/docs-site           # the only object EDITED (controllers.docs-site.initContainers.build.image.tag)
    - deployment/docs-site            # pod template changes -> one RollingUpdate roll (surge 1, unavailable 0)
    - service/docs-site               # unchanged; used by §4 port-forward
    - httproute/docs-site             # unchanged (envoy-internal, LAN-only)
  shared: []                          # no PVC, no shared DB, no gateway/route change. §4 reads only kubectl + the
                                      # pod's own HTTP; the one Alertmanager CONTROL is a "not firing" floor, see §6.
depends_on: []
conflicts_with:
  - helm-drift-detection              # its §3 uses docs-site as a test target (scales deploy/docs-site to 2, reconciles
                                      # helmrelease/docs-site, reads its Drifted condition) — same object, must not share a window
exclusive: false
security_ref: F-b362e5bd              # Trivy "newer upstream tag available" row on the 9.7.7 image; detail on the finding record only
capability_change: false              # same behaviour: a dependency-minimum + CLI-notice release. No plugin/feature/route/exposure
                                      # change; we use only the built-in `search` plugin and none of the removed recommended extras (§1.2)
rollback_class: git-revert            # nothing forward-only: emptyDir build output, no schema, no PV; revert restores 9.7.7 exactly
finding_refs: [F-25507cfd, F-b362e5bd]   # F-25507cfd = version finding "docs-site: image squidfunk/mkdocs-material 9.7.7 → 9.8 (minor)";
                                         # F-b362e5bd = the security row this bump answers (citation only, no detail here)
review: null
premises:
  - id: live-build-image-is-9.7.7
    why: "Rollback target and the generator-meta baseline assume the running build image is 9.7.7; if it already moved, re-plan."
    run: kubectl get deploy docs-site -n monitoring -o jsonpath='{.spec.template.spec.initContainers[0].image}'
    expect_exact: "squidfunk/mkdocs-material:9.7.7"
  - id: hr-ready-at-current-generation
    why: "No in-flight upgrade to stack on; git revert must land on a known-good revision."
    run: kubectl get helmrelease docs-site -n monitoring -o jsonpath='{.metadata.generation}={.status.observedGeneration}={.status.conditions[?(@.type=="Ready")].status}'
    expect_matches: '^(\d+)=\1=True$'
  - id: target-digest-unchanged
    why: "The plan was investigated against index digest dc3b5de7…; an in-place rebuild of 9.8.0 means re-check before running."
    run: curl -s https://hub.docker.com/v2/repositories/squidfunk/mkdocs-material/tags/9.8.0 | python3 -c "import sys,json;print(json.load(sys.stdin)['digest'])"
    expect_exact: "sha256:dc3b5de76c6e30d18dc0922d4c4a7bed817e5e155f9ff0e594a53eb56e537e64"
  - id: pr-429-open-mergeable
    why: "§3 merges PR #429; a closed/conflicting PR means Renovate re-cut it and the diff must be re-read."
    run: gh pr view 429 --json state,mergeable -q '.state+"="+.mergeable'
    expect_exact: "OPEN=MERGEABLE"
status: draft
window: null
sops_refs:
  - docs/sops/application-update.md
generated: "2026-10-25"
---

# docs-site — squidfunk/mkdocs-material 9.7.7 → 9.8.0

## 1. Summary & why held

### 1.1 What changes, and why it was held

One line in `kubernetes/apps/monitoring/docs-site/app/helmrelease.yaml`: the
`build` initContainer image tag `9.7.7` → `9.8.0` (exactly the diff in Renovate
PR #429). The initContainer clones the public repo and runs
`docs-site/build.sh` → `mkdocs build` into an emptyDir that nginx serves.

The hold was the coverage lane's floating-target guard: `check-all-versions.py`
reported the latest tag as `9.8` (the moving series pointer), and coverage
correctly refused to bump to a tag that "cannot be shown to be GA". **That is a
false positive for the update itself**: the fixed tag `9.8.0` exists, is GA, and
Renovate already has PR #429 open for it with green CI. **Chosen target: the
fixed tag `9.8.0`**, index digest
`sha256:dc3b5de76c6e30d18dc0922d4c4a7bed817e5e155f9ff0e594a53eb56e537e64`
(multi-arch OCI index: linux/amd64, arm64, arm/v7 + attestations).

**Digest is enforced as a verification gate, not written into the manifest.**
The Renovate custom manager for `# renovate: image=` (`.github/renovate.json5`
~L516) captures `tag:` as `currentValue` with no `currentDigest` group, so a
`9.8.0@sha256:…` value would make the whole string the "version" and blind
Renovate to every future docs-site bump — a false negative created by the fix.
§4.2 instead asserts the running pod's `imageID` equals the digest above.

### 1.2 Upstream evidence (CHANGELOG, `mkdocs-material-9.8.0 (2026-10-24)`)

> "This is primarily a security release. It raises dependency minimums to
> address known vulnerabilities. […] Python 3.11 or newer is now required."
>
> "* Removed RSS from recommended dependencies […] * Removed redirects from
> recommended dependencies […] * Updated CLI notice with end-of-life and
> migration guidance"

Applicability to us:
- **Python ≥ 3.11**: the image is `FROM python:3.11-alpine3.21`; upstream
  `Dockerfile` is byte-identical between the 9.7.7 and 9.8.0 tags (diffed). N/A.
- **RSS / redirects removed from the `recommended` extra**: `docs-site/mkdocs.yml`
  declares only `plugins: [search]` ("Zero extra plugins"). N/A.
- **Raised minimums** (`requirements.txt` diff: jinja2, markdown, pygments,
  pymdown-extensions, requests): only lower bounds moved. We use
  `pymdown.superfences/highlight/details`, `admonition`, `attr_list`,
  `md_in_html`, `tables`, `toc` — all present in the new minimums.
- **CLI notice** now names an end-of-life date (2027-05-05) and links the
  Zensical migration guide. Informational log output only; build exit status is
  unaffected (the 9.7.7 build already prints the MkDocs-2.0 banner).
- The security driver is cited as `security_ref: F-b362e5bd`; its detail stays
  on the finding record.

### 1.3 Dry-build measured (2026-10-25, macOS scratch venv, this repo at HEAD)

`pip install mkdocs-material==9.8.0` (resolved mkdocs 1.6.1) vs `==9.7.7`, both
running `sh docs-site/build.sh <clone> <out>`:

| | 9.7.7 | 9.8.0 |
|---|---|---|
| exit | 0 | 0 |
| ERROR/Traceback lines | 0 | 0 |
| content WARNINGs | 1 (`sli-catalog.md` → `slo-check.py`, pre-existing) | same 1 |
| HTML pages | 188 | 188 (identical path set, `diff` empty) |
| search_index docs | 3782 | 3782 |
| generator meta | `mkdocs-material-9.7.7` | `mkdocs-material-9.8.0` |

(The scratch venv resolved the same dependency versions for both; the image
bundles its own, so §4 re-asserts the contents on the real pod.)

### 1.4 Long-term note (not this window)

Upstream now marks Material for MkDocs inactive with EOL 2027-05-05. A
replacement decision (Zensical or other) is an operator choice to make before
then; this plan only takes the last supported line.

## 2. Pre-checks

```bash
cd /Users/mu/code/cberg-home-nextgen && git pull --ff-only

# 2.1 premises (also run by the window runner)
kubectl get deploy docs-site -n monitoring -o jsonpath='{.spec.template.spec.initContainers[0].image}'; echo
#   expect: squidfunk/mkdocs-material:9.7.7
kubectl get helmrelease docs-site -n monitoring -o jsonpath='{.metadata.generation}={.status.observedGeneration}={.status.conditions[?(@.type=="Ready")].status}'; echo
#   expect: N=N=True
curl -s https://hub.docker.com/v2/repositories/squidfunk/mkdocs-material/tags/9.8.0 | python3 -c "import sys,json;print(json.load(sys.stdin)['digest'])"
#   expect: sha256:dc3b5de76c6e30d18dc0922d4c4a7bed817e5e155f9ff0e594a53eb56e537e64
gh pr view 429 --json state,mergeable,files -q '.state+"="+.mergeable+" "+([.files[].path]|join(","))'
#   expect: OPEN=MERGEABLE kubernetes/apps/monitoring/docs-site/app/helmrelease.yaml

# 2.2 not mid-refresh: the 05:30 docs-site-refresh CronJob rolls the same Deployment
kubectl get jobs -n monitoring -l batch.kubernetes.io/cronjob-name=docs-site-refresh --no-headers 2>/dev/null | awk '$2!~/1\/1|Complete/'
#   expect: no output. Do not run between 05:25 and 05:45 Europe/Berlin.

# 2.3 BASELINE of served contents (record all three numbers in the window log)
kubectl -n monitoring port-forward svc/docs-site 18080:8080 >/dev/null 2>&1 & PF=$!; sleep 3
curl -s http://localhost:18080/ | grep -io '<meta name="generator"[^>]*>'
#   expect: ... mkdocs-material-9.7.7
BASE_DOCS=$(curl -s http://localhost:18080/search/search_index.json | python3 -c "import sys,json;print(len(json.load(sys.stdin)['docs']))"); echo "BASE_DOCS=$BASE_DOCS"
#   measured 2026-10-25: 3791
curl -s -o /dev/null -w '%{http_code} %{size_download}\n' http://localhost:18080/docs/sops/application-update/
#   measured: 200 133082
kill $PF 2>/dev/null
```

Abort (no change made) if any premise differs.

## 3. Steps

```bash
cd /Users/mu/code/cberg-home-nextgen

# 3.1 active-update marker so alert-triage treats a stray docs-site alert as expected
runbooks/update-marker.sh add docs-site monitoring 1 "mkdocs-material 9.7.7->9.8.0 (PR 429)"

# 3.2 merge the Renovate PR (same mechanism auto-update.py uses), then sync main
gh pr merge 429 --squash --delete-branch
git pull --ff-only
grep -n 'tag: 9.8.0' kubernetes/apps/monitoring/docs-site/app/helmrelease.yaml
#   expect exactly one line (the build initContainer). git log -1 --format=%s must name mkdocs-material 9.8.0.
```

No other edit: no remediation change (nothing forward-only to protect), no
silence (a RollingUpdate creates a new pod, it does not restart one, so
`DocsSitePodRestarted`/`CrashLooping` have nothing to count; a failed build
surfaces as `DocsSitePodNotReady` after 5 m, which is the signal we WANT).
The GitHub webhook triggers Flux; no manual `flux reconcile` per the SOP. If
the HR has not moved to a new generation after 10 min, `flux reconcile
kustomization docs-site -n monitoring --with-source` once and record why.

## 4. Verification

```bash
# 4.1 Flux floor
kubectl get helmrelease docs-site -n monitoring -o jsonpath='{.metadata.generation}={.status.observedGeneration}={.status.conditions[?(@.type=="Ready")].status}'; echo
#   expect: N=N=True with N = pre-check N + 1
kubectl rollout status deploy/docs-site -n monitoring --timeout=5m
```

```bash
# 4.2 the NEW bytes are running — by imageID, not tag (rollout status can green-light the old generation)
kubectl get pods -n monitoring -l app.kubernetes.io/name=docs-site -o jsonpath='{range .items[*]}{.metadata.name} {.status.phase} {.status.initContainerStatuses[0].imageID}{"\n"}{end}'
#   PASS: exactly ONE pod line, Running, imageID ...squidfunk/mkdocs-material@sha256:dc3b5de76c6e30d18dc0922d4c4a7bed817e5e155f9ff0e594a53eb56e537e64
#   FAIL shapes: two pod lines (new pod stuck in Init, old one still serving under surge) or the old digest 51b87149…
kubectl logs -n monitoring deploy/docs-site -c build --tail=40 | grep -iE 'error|traceback|Documentation built'
#   PASS: exactly one "Documentation built in" line, and no error/traceback line (grep is case-insensitive;
#   the pre-existing WARNING about slo-check.py is expected and is not matched by this pattern)
```

```bash
# 4.3 CONTENTS of what nginx now serves
kubectl -n monitoring port-forward svc/docs-site 18080:8080 >/dev/null 2>&1 & PF=$!; sleep 3
curl -s http://localhost:18080/ | grep -io '<meta name="generator"[^>]*>'
#   PASS: contains mkdocs-material-9.8.0.  This CAN fail: measured today it prints 9.7.7, and it keeps printing 9.7.7
#   whenever the old pod is still the one serving.
NEW_DOCS=$(curl -s http://localhost:18080/search/search_index.json | python3 -c "import sys,json;print(len(json.load(sys.stdin)['docs']))"); echo "NEW_DOCS=$NEW_DOCS BASE_DOCS=$BASE_DOCS"
python3 -c "import sys;b,n=int(sys.argv[1]),int(sys.argv[2]);print('PASS' if b>0 and n>=0.95*b else 'FAIL')" "$BASE_DOCS" "$NEW_DOCS"
#   PASS only if the new search index holds >= 95 % of the baseline entries (dry-build: identical 3782/3782; the 5 % band
#   absorbs docs committed between baseline and rebuild). An empty/partial build or a missing index prints FAIL
#   (a missing index makes python raise -> NEW_DOCS empty -> int('') error = FAIL, never a silent pass).
curl -s -o /dev/null -w '%{http_code} %{size_download}\n' http://localhost:18080/docs/sops/application-update/
#   PASS: 200 and size within +-20 % of the baseline (133082 measured 2026-10-25)
for a in $(curl -s http://localhost:18080/ | grep -o 'assets/[^"]*\.min\.\(js\|css\)' | sort -u); do
  curl -s http://localhost:18080/$a -o /tmp/ds-asset -w "$a %{http_code} %{size_download} " ; head -c 15 /tmp/ds-asset | grep -qi '<!doctype' && echo HTML-FAIL || echo ok
done
#   PASS: every fingerprinted asset (bundle.*.min.js, workers/search.*.min.js, main.*.min.css, palette.*.min.css)
#   returns 200, a size > 1000 bytes, and "ok" (not an HTML error page). Fingerprints will DIFFER from the
#   2026-10-25 baseline (bundle.d7400e89, main.ec1eaa64 …) because upstream rebuilt its Node assets — expected.
kill $PF 2>/dev/null; rm -f /tmp/ds-asset
```

CONTENTS ASSERTION: the served site is the 9.8.0 build and is complete — the
generator meta names `mkdocs-material-9.8.0`, the search index holds ≥ 95 % of
the pre-change `BASE_DOCS` entries, a known deep page returns 200 at baseline
size, and every fingerprinted JS/CSS asset serves real bytes.

CONTROL: metric kube_pod_status_ready — the expression behind DocsSitePodNotReady; the docs-site pod must have condition="true" ready (read via 4.2's kubectl view of the same pod; the alert is the persistent instrument)
CONTROL: alertname DocsSitePodNotReady — must be NOT firing 10 min after the rollout (rule in kubernetes/apps/monitoring/kube-prometheus-stack/app/docs-site-alerts.yaml)
CONTROL: alertname DocsSitePodCrashLooping — must be NOT firing

```bash
# 4.4 alert floor (after 10 min)
kubectl port-forward -n monitoring svc/kube-prometheus-stack-alertmanager 9093:9093 >/dev/null 2>&1 & PF=$!; sleep 2
curl -s localhost:9093/api/v2/alerts | python3 -c "import sys,json;a=[x['labels']['alertname'] for x in json.load(sys.stdin) if x['labels'].get('component')=='docs-site'];print(a or 'NONE')"
#   PASS: NONE.  (The API answering at all is checked by the json.load — an unreachable AM raises, not NONE.)
kill $PF 2>/dev/null
runbooks/update-marker.sh clear docs-site
```

## 5. Rollback

Trigger: any §4 FAIL, or a new pod stuck in `Init` > 10 min (the old pod keeps
serving under surge 1 / unavailable 0, so there is no outage pressure — read
`kubectl logs -n monitoring <new-pod> -c build` first and record it).

```bash
cd /Users/mu/code/cberg-home-nextgen && git pull --ff-only
SHA=$(git log -1 --format=%H --grep='squidfunk/mkdocs-material' -- kubernetes/apps/monitoring/docs-site/app/helmrelease.yaml)
git show --stat "$SHA"                       # must touch ONLY that helmrelease.yaml, subject names 9.8.0
git revert --no-edit "$SHA"
git log -1 --format=%s                       # confirm the subject is YOUR revert before pushing (shared worktree)
git push
```

Confirm back: HR `N=N=True` at a new generation; 4.2 imageID shows
`sha256:51b87149d227691486b5f08993d28c65ca7e4990010664b697265b8e6fcd5287`;
4.3 generator meta prints `mkdocs-material-9.7.7` and the search index is back
≥ 95 % of `BASE_DOCS`. Nothing to restore: the site is rebuilt from git into an
emptyDir on every pod start. Then add a deny rule for
`squidfunk/mkdocs-material` 9.8.x in `runbooks/auto-update-policy.yaml` with
the observed failure, so Step 0 does not re-apply it.

## 6. Interference notes

- **Same object as `helm-drift-detection`** (its §3 scales/reconciles
  docs-site as a drift test target) → `conflicts_with` on that plan id. That
  plan does not list this one; the window agent should add the reciprocal ref
  when it next touches it.
- **05:30 `docs-site-refresh` CronJob** does a `rollout restart` of the same
  Deployment; a nightly 03:30 slot is clear of it. Do not run 05:25–05:45.
- **Step 0 / kube-prometheus-stack**: PR #428 (kube-prometheus-stack
  92.11.0 → 92.13.1) is open and may land via the safe lane at Step 0 of the
  same window. §4.4 reads Alertmanager. No kps *plan* exists to put in
  `conflicts_with`; run this plan only after Step 0's health gate has settled,
  and if kps rolled this window, treat an unreachable Alertmanager in 4.4 as
  "re-run after it is Ready", not as a pass.
- **`flux-oci-chart-sources`** (exclusive, sun-attended 2026-11-22) rewrites
  chart sources fleet-wide; its `exclusive: true` already keeps it apart.
- No shared infra perturbed: no PVC, no DB, no Gateway/route/cert change, no
  reboot. The served nginx container image is unchanged (only its pod rolls).
- Blast radius if everything goes wrong: the LAN handbook shows stale content
  (old pod) or is briefly unavailable; no other workload depends on it.

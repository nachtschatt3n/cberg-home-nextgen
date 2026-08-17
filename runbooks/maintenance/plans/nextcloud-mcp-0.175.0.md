---
plan_id: nextcloud-mcp-0.175.0
component: nextcloud-mcp
pr: null                              # PLAN lane — coverage.py needs_plan, no open Renovate PR.
                                      # Surfaced from the full version universe, not a PR. If
                                      # Renovate opens one before the window, record it here and
                                      # re-verify the tag.
kind: image                           # app-template image-tag bump. NOT a chart bump — see §1.
current: "0.173.0"
target: "0.175.0"                     # ghcr.io/cbcoutinho/nextcloud-mcp-server. v0.175.0 published
                                      # upstream 2026-08-15. Verify the tag in Pre-checks (a).
update_type: minor                    # 0.173 -> 0.175, two minor releases, purely additive.
risk: low                             # HOLD WAS A FALSE POSITIVE (misattribution) — see §1.
                                      # Stateless HTTP MCP bridge: no PVC, no DB, no occ, no
                                      # maintenance mode. The only consumer is OpenClaw (ai ns),
                                      # and the change is reverted by one git-revert of a tag line.
est_duration_min: 10
needs_reboot: false
touches:
  namespaces: [office]
  resources:
    - helmrelease/nextcloud-mcp        # app-template 3.7.3 (UNCHANGED) — only image.tag moves
    - kustomization/nextcloud-mcp       # ns `office` (targetNamespace), NOT flux-system
    - deployment/nextcloud-mcp          # single-replica; rolls one pod (~10s), stateless
    - service/nextcloud-mcp             # UNCHANGED (port 8000) — verify, do not edit
    - ingress/nextcloud-mcp             # UNCHANGED (className: internal, host nextcloud-mcp.*)
  shared: []                            # nothing shared is mutated. It holds ONE Ingress object
                                        # on className `internal` but does NOT restart the ingress
                                        # controller. NO storage op (no PVC exists on this app).
depends_on: []                          # (Flux KS has a standing dependsOn: nextcloud, but that
                                        # is not a plan-ordering dependency — nextcloud is stable.)
conflicts_with:                         # VERIFICATION-CONFOUND conflicts, not danger conflicts.
  - bitnamilegacy-exit-nextcloud-db     # both restart the Nextcloud BACKEND this MCP proxies;
  - bitnamilegacy-exit-nextcloud-redis  # co-scheduling makes §4 tool-surface probe flap. See §6.
security_ref: null                      # no security driver — feature bump held by misattribution.
status: executed   # applied 2026-08-17 ad6bdfcd, pod Ready on 0.175.0
window: null                            # window agent assigns. Recommended: any no-reboot weekday
                                        # slot (mon/tue/wed/thu/fri-early) or sat-early. NOT
                                        # sun-window (reserve reboot-capable slot for Talos churn).
auto_execute: false
sops_refs:
  - docs/sops/application-update.md
generated: "2026-08-16"
---

# nextcloud-mcp 0.173.0 → 0.175.0

## 1. Summary & why held

`nextcloud-mcp` is **not** the Nextcloud server. It is the standalone third-party
**MCP bridge** `ghcr.io/cbcoutinho/nextcloud-mcp-server`, deployed on the generic
bjw-s **app-template** chart (`kubernetes/apps/office/nextcloud-mcp/app/helmrelease.yaml`).
It is a single-replica, **stateless** container:

- **No PVC, no database, no `occ`, no maintenance mode.** It talks to the real
  Nextcloud over the Nextcloud HTTP API using an app-password
  (`NEXTCLOUD_HOST/USERNAME/PASSWORD` from `nextcloud-mcp-config`, a SOPS secret).
- Its only consumer is **OpenClaw** (`ai` namespace) via mcporter — a read-oriented
  tool surface (files, notes, calendar, contacts, deck, tables). Reference:
  `kubernetes/apps/ai/openclaw/app/mcporter-config.yaml` (`"nextcloud"` entry, HTTP
  transport pointing at this service).

**The hold reason is a false positive — a misattribution.** The stated driver
("chart+image must bump together and run occ migrations; Mail custom_app /
stuck-maintenance-mode trap"; MEMORY `project_nextcloud_upgrade_mailapp`) belongs to
the **Nextcloud SERVER**, which is a *different* app:
`kubernetes/apps/office/nextcloud/app/helmrelease.yaml` — chart `nextcloud/nextcloud`
9.2.5, image `nextcloud:34.0.2`, with a PVC, `occ upgrade` on boot, the `mail`
custom_app, and the maintenance-mode trap. **None of that exists in nextcloud-mcp.**
There is no chart+image coupling here either: the chart is app-template (a generic
wrapper), and it is **not** being bumped — only the image tag moves.

**Upstream evidence (0.173.0 → 0.175.0), no breaking change:**

- **v0.174.0** — WebDAV read/post comments on files; namespace-constant + OCS-APIRequest
  header fixes; improved blank-message detection.
- **v0.174.1** — fix: detect embedding dimension for OpenAI/Mistral models.
- **v0.175.0** — feature: request Matryoshka output width via optional
  `EMBEDDING_DIMENSIONS` env var.

No breaking changes, **no new *required* environment variables**, no auth changes, no
config-format changes are documented. `EMBEDDING_DIMENSIONS` is optional and unset here
(and irrelevant unless a search-embedding tool is used). This is written as a plan (not
auto-merged) only because the operator decides on false-positive holds — not because the
change is risky.

## 2. Pre-checks

```bash
# (a) Confirm the target tag is published on ghcr (never bump to a non-existent tag)
crane ls ghcr.io/cbcoutinho/nextcloud-mcp-server 2>/dev/null | grep -x '0.175.0' \
  || echo "MISSING TAG — STOP"
# fallback if crane unavailable:
#   docker manifest inspect ghcr.io/cbcoutinho/nextcloud-mcp-server:0.175.0 >/dev/null && echo OK

# (b) Current state is healthy before touching anything
kubectl get helmrelease -n office nextcloud-mcp \
  -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} {range .spec.values.controllers.main.containers.main.image}{.tag}{end}{"\n"}'
kubectl get pods -n office -l app.kubernetes.io/name=nextcloud-mcp

# (c) Confirm the BACKEND Nextcloud server is up (MCP is useless if it isn't) and
#     that NO nextcloud backend change is mid-flight this window (see §6 conflicts)
kubectl get helmrelease -n office nextcloud \
  -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}{"\n"}'

# (d) No in-flight reconcile on the office kustomization
flux get kustomization -n office nextcloud-mcp
```

Proceed only if: tag `0.175.0` exists, the MCP HelmRelease is `True` on `0.173.0`,
the pod is `Running`, and the `nextcloud` server HelmRelease is `True`.

## 3. Steps (GitOps)

```bash
cd /Users/mu/code/cberg-home-nextgen

# (1) Bump ONLY the image tag in the HelmRelease. Do NOT touch chart.version (3.7.3).
#     File: kubernetes/apps/office/nextcloud-mcp/app/helmrelease.yaml
#       image:
#         repository: ghcr.io/cbcoutinho/nextcloud-mcp-server
#         tag: 0.173.0   ->   tag: 0.175.0
sed -i '' 's/tag: 0.173.0/tag: 0.175.0/' \
  kubernetes/apps/office/nextcloud-mcp/app/helmrelease.yaml

# (2) Sanity-check the diff (exactly one line, the tag)
git diff -- kubernetes/apps/office/nextcloud-mcp/app/helmrelease.yaml

# (3) Commit + push. Flux reconciles on the webhook.
git add kubernetes/apps/office/nextcloud-mcp/app/helmrelease.yaml
git commit -m "chore(nextcloud-mcp): image 0.173.0 -> 0.175.0 (held false-positive; stateless MCP bridge)"
git push
```

No `sops` edit, no manual `flux reconcile`, no PVC operation. This is
application-update.md's "Low (patch, self-contained image)" path — commit, let Flux
reconcile, verify.

## 4. Verification

```bash
# (a) Flux reconciled the HelmRelease to the new tag, Ready=True
kubectl get helmrelease -n office nextcloud-mcp \
  -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}{"\n"}'
kubectl get pods -n office -l app.kubernetes.io/name=nextcloud-mcp \
  -o custom-columns=NAME:.metadata.name,STATUS:.status.phase,IMAGE:.spec.containers[0].image

# (b) TCP readiness probe is green (chart uses tcpSocket:8000 — no HTTP /health)
kubectl describe pod -n office -l app.kubernetes.io/name=nextcloud-mcp \
  | grep -iE 'Readiness|Liveness|Ready' | head

# (c) The MCP tool surface actually answers (the real success signal). Port-forward
#     and hit the MCP HTTP endpoint; it must respond, proving it reached the
#     Nextcloud backend with its app-password.
kubectl port-forward -n office svc/nextcloud-mcp 8000:8000 >/dev/null 2>&1 &
PF=$!; sleep 3
curl -s -o /dev/null -w 'mcp http: %{http_code}\n' http://localhost:8000/
kill $PF 2>/dev/null

# (d) Confirm the consumer (OpenClaw) still sees the tool. Non-fatal but the point of
#     the deployment: OpenClaw pod logs should NOT show nextcloud MCP connect errors.
kubectl logs -n ai -l app.kubernetes.io/name=openclaw --tail=50 2>/dev/null \
  | grep -iE 'nextcloud.*(error|fail|refused)' || echo "no nextcloud MCP errors"
```

Success = HelmRelease `True` on `0.175.0`, pod `Running` on the new image, probe green,
MCP endpoint answers, no nextcloud-MCP connection errors in OpenClaw.

## 5. Rollback

Single-line git revert — no data, no migration, nothing to unwind:

```bash
cd /Users/mu/code/cberg-home-nextgen
git revert --no-edit <this-commit-sha>     # or: sed -i '' 's/tag: 0.175.0/tag: 0.173.0/' <hr> && commit
git push
# Flux rolls the pod back to 0.173.0. Confirm:
kubectl get helmrelease -n office nextcloud-mcp \
  -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}{"\n"}'
kubectl get pods -n office -l app.kubernetes.io/name=nextcloud-mcp
```

If Flux's `upgrade.remediation` (retries: 3) auto-rolls a crash-looping new pod before
you revert, the cluster is already back on `0.173.0` — just revert the git commit to
stop the tag drifting forward again on the next reconcile. `maxHistory: 1` means there
is no Helm history to `helm rollback` to; the git spec IS the rollback (SOP §11).

## 6. Interference notes

- **Blast radius is tiny and self-contained.** One stateless pod in `office`. If the
  bump goes wrong, the only thing that breaks is OpenClaw's Nextcloud tool surface
  (read-oriented). No Nextcloud data is touched — the MCP holds nothing; the real data
  lives in the Nextcloud server + its Longhorn/mariadb backups. No node reboot.
- **`shared: []` is deliberate.** The app owns an Ingress object on className `internal`
  but the reconcile does not restart the ingress controller, and it mounts no storage.
  So this plan does not perturb other ingressed apps or any shared infra.
- **`conflicts_with` is a verification-confound, not a danger.** `bitnamilegacy-exit-nextcloud-db`
  and `bitnamilegacy-exit-nextcloud-redis` restart the **Nextcloud backend** that this
  MCP proxies. If either runs in the SAME window, §4(c)/(d) will flap (the MCP will
  briefly fail to reach its backend) and could mask or fake a failure. They are safe in
  a *different* window. No hard ordering otherwise.
- **Do NOT confuse this with the Nextcloud SERVER upgrade.** Any occ/maintenance-mode/
  Mail-custom-app procedure (MEMORY `project_nextcloud_upgrade_mailapp`) applies to
  `kubernetes/apps/office/nextcloud/`, not here. Executing that recovery recipe against
  this pod is meaningless (there is no `occ` in this image).
- **Recommended window:** any no-reboot weekday slot (mon/tue/wed/thu/fri-early) or
  sat-early. It's a low (weight-1) plan and pairs freely with other low/medium plans
  under the capacity_risk: 6 budget — except the two nextcloud-backend plans above.

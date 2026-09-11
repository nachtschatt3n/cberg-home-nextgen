---
plan_id: nextcloud-mcp-0.185.3
component: nextcloud-mcp
pr: null                              # no open Renovate PR found (`gh pr list --state all
                                      # --search nextcloud-mcp` returns nothing); held by
                                      # the `*nextcloud-mcp*` deny rule in
                                      # runbooks/auto-update-policy.yaml, not by a live PR
kind: image
current: "0.184.5"
target: "0.185.3"
update_type: minor                    # semver label only — see §1, this project treats the
                                      # minor digit as the breaking axis at major version 0
risk: medium
est_duration_min: 25
needs_reboot: false
touches:
  namespaces: [office]
  resources:
    - helmrelease/nextcloud-mcp
    - deployment/nextcloud-mcp
    - httproute/nextcloud-mcp
  shared: []                          # no shared datastore/gateway/CNI perturbed; the
                                      # HTTPRoute/Gateway (envoy-internal) and cilium/coredns
                                      # are untouched. Cross-namespace CONSUMER coupling
                                      # (ai/openclaw) exists but is not a shared-infra
                                      # perturbation in the `touches.shared` sense — see
                                      # Interference notes §7 for how the window agent
                                      # should actually reason about that blast radius.
depends_on: []                        # the Flux Kustomization `dependsOn: nextcloud` is an
                                      # ORDERING constraint (nextcloud-mcp's namespace must
                                      # exist/reconcile first), not a version coupling — see
                                      # §2. No plan currently touches nextcloud itself.
conflicts_with: []                    # bitnamilegacy-exit-nextcloud-db (namespace office,
                                      # status blocked, window null) is NOT added here: an
                                      # unwindowed/blocked plan cannot claim a slot, so there
                                      # is nothing to collide with today. Re-check when that
                                      # plan is revived — see Interference notes §7.
security_ref: F-80459b23              # security-driven bump; a newer upstream tag exists
                                      # (this bump). See §1.3 — all detail stays on the
                                      # finding record, never in this repo.
capability_change: false              # see §2.4 — the one fact a reviewer should challenge.
                                      # The protocol-visible behaviour change in 0.185.0
                                      # (elicitation degradation) only fires on the
                                      # multi-user Login Flow auth path; this deployment
                                      # runs MCP_DEPLOYMENT_MODE=single_user_basic (static
                                      # credentials, no Login Flow at all) — premise 4 below
                                      # re-verifies that fact at execution time, not just now.
rollback_class: git-revert            # stateless bridge: no PVC, no DB. `values.image.tag`
                                      # is the entire diff.
finding_refs: [F-9af9baf7, F-80459b23]
status: draft
window: null                          # RECOMMENDATION (not assignment): sun-attended:2026-09-13.
                                      # sat-attended:2026-09-12 is already over-committed
                                      # (risk-load 7>6, ~100min in a 90min window per the
                                      # dispatch brief) — do not add to it. sun-attended:2026-09-13
                                      # currently holds absenty-drop-npm-runtime (60min, low)
                                      # + authentik-pg18-lockstep (35min, medium) = 95/150min,
                                      # risk-load 3/6. Adding this plan (25min, medium=2) gives
                                      # 120/150min and risk-load 5/6 — fits with margin. Never
                                      # the nightly/unattended window: the deny-rule reason is
                                      # explicit ("never an unattended bump") and this plan does
                                      # not change that judgement, only narrows *why* for this hop.
premises:
  - id: image-is-still-0.184.5
    why: >-
      `current:` claims 0.184.5 and the rollback target is that tag. If the
      cluster already moved, this plan is stale and its diff/verification
      baseline no longer matches reality.
    run: kubectl get deploy -n office nextcloud-mcp -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: ghcr.io/cbcoutinho/nextcloud-mcp-server:0.184.5
  - id: nextcloud-server-unchanged
    why: >-
      No release note in range states a minimum Nextcloud server version, but
      the premise that "nothing else moved underneath this" should be checked
      directly rather than assumed from a stale read.
    run: kubectl get deploy -n office nextcloud -o jsonpath='{.spec.template.spec.containers[?(@.name=="nextcloud")].image}'
    expect_exact: docker.io/nextcloud:34.0.3
  - id: deployment-mode-still-single-user-basic
    why: >-
      `capability_change: false` rests entirely on this deployment running
      MCP_DEPLOYMENT_MODE=single_user_basic (static credentials, no Login Flow,
      no elicitation) — the code path the 0.185.0/0.185.1/0.185.2 protocol and
      auth changes touch. If this value ever changed to a multi-user mode, the
      capability_change fact is false and this plan must be re-vetted as
      attended/human-gated before running, not treated as routine.
    run: kubectl get secret -n office nextcloud-mcp-config -o json | jq -r '.data.MCP_DEPLOYMENT_MODE' | jq -Rr '@base64d'
    expect_exact: single_user_basic
sops_refs:
  - docs/sops/application-update.md
generated: "2026-09-11"
---

## 1. Summary & why held

`kubernetes/apps/office/nextcloud-mcp/app/helmrelease.yaml` pins
`ghcr.io/cbcoutinho/nextcloud-mcp-server` at `0.184.5`. The sweep flagged
`0.185.3` as available (`F-9af9baf7`, section `version`, severity `monitor`,
action "batch with other minor bumps" — that action is **overridden** by the
`*nextcloud-mcp*` deny rule, which must stay above the generic `*nextcloud*`
glob; see the comment at `auto-update-policy.yaml:147-154`). At major version
0, semver treats the **minor** digit as the breaking axis, so `0.184 → 0.185`
is a release-LINE move, not an in-line bump — this project has been bitten by
exactly that shape before (`0.176.0` removed the webhook registration API and
dropped its backing table on what looked like a routine minor).

### 1.1 Registry verification (done 2026-09-11, re-run manually at execution)

Not expressible as a formal `premises:` entry — the premise-checker's
read-only allowlist has no network tool (`curl`/registry client), only
`kubectl`/`flux`/`talosctl`/`helm`/`git` + text utilities. Treat this as a
mandatory manual pre-check instead (§2 step 0).

All five tags in range resolve (GHCR OCI index, `Accept:
application/vnd.oci.image.index.v1+json`, token-authed anonymous pull):

| tag | published (config `created`, UTC) |
|---|---|
| 0.184.5 (live) | 2026-09-04T14:37:06Z |
| 0.185.0 | 2026-09-05T15:10:54Z |
| 0.185.1 | 2026-09-08T15:02:46Z |
| 0.185.2 | 2026-09-09T06:07:50Z |
| 0.185.3 | 2026-09-09T08:16:34Z |

`0.185.3` is confirmed the newest tag: the `latest` tag's amd64 manifest
digest (`sha256:cdedfb41…`) is byte-identical to `0.185.3`'s, and no
`0.185.4`/`0.186.0` manifest exists (404). **Do not plan a stale target** —
re-check `latest` at execution time in case upstream shipped between now and
the window.

**48h release-age cooldown** (`auto-update-policy.yaml` `minimum_release_age_hours:
48`): as of this writing (2026-09-11T02:24Z) `0.185.3` is ~42h old — under the
gate. This is informational only: the gate governs the *unattended* Step-0
merge path, and `*nextcloud-mcp*` is deny-matched out of that path entirely
regardless of age. By any realistic window (earliest attended slot
2026-09-12/13), the tag will be comfortably past 48h anyway.

### 1.2 What actually changed, 0.184.5 → 0.185.3 (read per-hop, not just at the target)

- **0.184.5 → 0.185.0** (2026-09-05): **the one real breaking change in this
  range.** Upstream requires `mcp>=2.1,<3` (MCP protocol dated 2026-07-28) —
  a python-sdk v2 migration. Release notes state plainly: *"Server-initiated
  elicitation no longer reaches 2026-era clients — progressive consent
  degrades to `message_only`, with the login URL carried in the returned
  message. Deployments pinning mcp<2 must stay on the previous release."*
  This is the multi-user **Login Flow** consent path specifically — it is
  a degradation (fallback message), not a hard break, and it is **conditional
  on the auth mode in use** (§2.4). No MCP tool was renamed or removed in this
  hop; the rest is internal refactor (deck/notes/mail tool registration moved
  to module scope, restored error-message propagation that mcp 2.x was
  swallowing).
- **0.185.0 → 0.185.1** (2026-09-08): auth hardening on the Login Flow
  caller-verification path (upstream security advisory; not itself a
  behaviour-visible change for callers that don't use Login Flow). See
  `security_ref: F-80459b23` for the detail this repo tracks — not
  reproduced here per `docs/sops/vulnerability-disclosure.md`.
- **0.185.1 → 0.185.2** (2026-09-09): follow-on hardening — resolves the
  Login Flow caller's UID from Nextcloud itself rather than from IdP claims.
  Same auth path, same conditionality as above.
- **0.185.2 → 0.185.3** (2026-09-09): Deck-module bug fixes only (attachment
  type on id-addressed routes; Files-share attachments no longer hidden on
  cards). No schema change to the `deck_*` tool surface — outputs get more
  complete, not renamed/removed.

**No release in this range changes required Nextcloud server version, no
release drops a table, and no MCP tool is renamed or removed.** The
2026-08-19 `0.176.0` failure mode (removed API + dropped table) does **not**
repeat here — the real risk this hop carries is the MCP protocol/SDK floor,
scoped to a feature this deployment's auth mode does not exercise (§2.4).

### 1.3 Security driver

`security_ref: F-80459b23` — the finding that drives this bump; a newer
upstream tag exists, and taking it is the fix path per the "we bump, we never
rebuild" rule for third-party images. Detail
(counts, CVE IDs) stays on the finding record —
`runbooks/policy-cli.py finding show F-80459b23`. `F-f02df447` (AR-029,
already-accepted CRITICAL/HIGH tally on the same tag) is not expected to
clear fully — verify post-bump whether it narrows, but do not treat a
non-zero residual as a plan failure; that is the accepted-risk model for
third-party base images.

## 2. Pre-checks

0. **Re-verify the target tag still resolves and is still newest** (manual —
   not expressible as a formal premise, see §1.1):
   ```bash
   TOKEN=$(curl -s "https://ghcr.io/token?scope=repository:cbcoutinho/nextcloud-mcp-server:pull&service=ghcr.io" \
     | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
   curl -s -o /dev/null -w '%{http_code}\n' -H "Authorization: Bearer $TOKEN" \
     -H "Accept: application/vnd.oci.image.index.v1+json" \
     "https://ghcr.io/v2/cbcoutinho/nextcloud-mcp-server/manifests/0.185.3"
   # expect: 200
   curl -s -o /dev/null -w '%{http_code}\n' -H "Authorization: Bearer $TOKEN" \
     -H "Accept: application/vnd.oci.image.index.v1+json" \
     "https://ghcr.io/v2/cbcoutinho/nextcloud-mcp-server/manifests/0.185.4"
   # expect: 404 (if 200, upstream shipped again — re-read its release notes
   # before retargeting this plan)
   ```
1. **Cluster health floor** — no unrelated red flags before starting:
   ```bash
   flux get kustomizations -A | awk 'NR==1 || $5 != "True"'
   flux get helmreleases -A   | awk 'NR==1 || $5 != "True"'
   kubectl get pods -n office
   ```
2. **No in-flight reconcile on this HelmRelease**:
   ```bash
   kubectl get helmrelease -n office nextcloud-mcp -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} rev={.status.history[0].chartVersion}{"\n"}'
   # expect: True rev=5.1.0
   ```
3. **Confirm Nextcloud (the consumer's target, not a dependency of this
   image) hasn't silently moved** — the Flux `dependsOn: nextcloud` is
   ordering-only (this Kustomization waits for `office/nextcloud` to exist),
   not a version coupling; no release note in §1.2 states a minimum
   Nextcloud server version. Still worth a sanity read:
   ```bash
   kubectl get deploy -n office nextcloud -o jsonpath='{.spec.template.spec.containers[?(@.name=="nextcloud")].image}{"\n"}'
   # expect: docker.io/nextcloud:34.0.3 (live, verified 2026-09-11)
   ```
4. **No firing alerts for office/ai namespaces** (ignore Watchdog/InfoInhibitor):
   ```bash
   kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 &
   curl -s http://localhost:9090/api/v1/alerts | python3 -c "
   import sys, json
   for a in json.load(sys.stdin)['data']['alerts']:
       ln = a['labels']
       if ln.get('namespace') in ('office','ai'):
           print(ln.get('alertname'), ln.get('namespace'), a.get('state'))
   "
   ```
5. **Record the OpenClaw consumer's baseline** (§2.4) — capture that the
   `nextcloud` MCP tool works BEFORE the bump, so a post-bump failure is
   attributable to this change and not pre-existing drift. From the `ai`
   namespace, exercise the same tool-list call as Verification §4 step 3
   against the CURRENT `0.184.5` server and save the output for diff.

### 2.4 The fact to challenge: is the Login Flow path even reachable here?

`kubernetes/apps/office/nextcloud-mcp/app/secret.sops.yaml` sets
`MCP_DEPLOYMENT_MODE: single_user_basic` — static username/password
credentials configured at deploy time, no interactive OAuth-style Login Flow,
no elicitation. If that is still true at execution time, the 0.185.0
elicitation-degradation change and the 0.185.1/0.185.2 Login-Flow auth
hardening are **inert for this deployment** — the affected code path is never
invoked. That is why `capability_change: false` above. Premise 4 (§3)
re-checks this at execution time rather than trusting today's read.

## 3. Steps

1. **Confirm all premises pass** (below) before touching anything.
2. Edit the image tag:
   ```bash
   # kubernetes/apps/office/nextcloud-mcp/app/helmrelease.yaml
   #   containers.main.image.tag: 0.184.5 -> 0.185.3
   ```
3. Commit + push (single-file, GitOps-only — see the shared-worktree commit
   convention, `git commit --only`):
   ```bash
   git commit --only kubernetes/apps/office/nextcloud-mcp/app/helmrelease.yaml -m "$(cat <<'EOF'
   fix(nextcloud-mcp): bump ghcr.io/cbcoutinho/nextcloud-mcp-server 0.184.5 -> 0.185.3

   Release-line move (0.184 -> 0.185); minor digit is the breaking axis at
   major version 0. No tool rename/removal or DB schema change in this range
   (verified per-hop release notes) -- the real change is an MCP protocol/SDK
   floor (mcp>=2.1) affecting only the multi-user Login Flow auth path, which
   this deployment does not use (MCP_DEPLOYMENT_MODE=single_user_basic).
   Also lands two upstream Login Flow auth-hardening fixes.

   security_ref: F-80459b23
   finding_refs: F-9af9baf7, F-80459b23
   EOF
   )"
   git push
   ```
4. Let Flux reconcile (`interval: 30m` — force if the window needs it sooner:
   `flux reconcile hr -n office nextcloud-mcp --with-source`). No immutable
   selectors, no PVC, no migration job — a plain rolling Deployment update.
5. Watch the rollout (single replica, default `RollingUpdate` — this
   controller has no PVC, so the RWO multi-attach guard in
   `docs/sops/longhorn-rwo-multi-attach.md` does not apply here):
   ```bash
   kubectl get pods -n office -l app.kubernetes.io/name=nextcloud-mcp -w
   ```

## 4. Verification

1. **Flux Ready**:
   ```bash
   kubectl get helmrelease -n office nextcloud-mcp -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}{"\n"}'
   # expect: True
   ```
2. **Pod running the new tag** (imageID, not just the tag string — the tag
   here is a real version bump so the string itself is sufficient evidence,
   but confirm restarts settle at 0):
   ```bash
   kubectl get deploy -n office nextcloud-mcp -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'
   # expect: ghcr.io/cbcoutinho/nextcloud-mcp-server:0.185.3
   kubectl get pods -n office -l app.kubernetes.io/name=nextcloud-mcp
   # expect: 1/1 Running, 0 restarts after settle
   ```
3. **CONTENTS ASSERTION — the tool surface, not just liveness.** A TCP-socket
   probe (this controller's only configured probe) proves the port is open;
   it says nothing about whether the MCP tool list still matches. Call the
   server's MCP endpoint directly and diff against the §2 pre-check baseline:
   ```bash
   <!-- Short service name, not the .svc.cluster.local FQDN: the probe pod runs
        in this same namespace so the short form resolves identically, and the
        FQDN is a cluster-Secret value that trips the pre-commit Layer-1 scanner.
        Do not re-expand it. -->
   kubectl run -n office mcp-probe --rm -it --restart=Never --image=curlimages/curl -- \
     curl -s -X POST http://nextcloud-mcp:8000/mcp \
     -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
     -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
   ```
   Assert: the response is a valid JSON-RPC result (not an error), and the
   tool name set is a **superset** of the pre-bump baseline (no tool present
   before is now missing — new tools/fields appearing is fine, per §1.2).
4. **The actual consumer still works, not just the endpoint.** From the
   OpenClaw session (`ai` namespace), exercise one read-oriented Nextcloud
   operation through the `nextcloud` MCP entry (e.g. list a known folder or
   note) and confirm it returns real data, not an error/timeout. This is the
   one assertion that would catch an mcporter-side protocol mismatch that a
   raw `tools/list` call against the server alone cannot — mcporter is
   installed via `install_npm mcporter` at pod start (unpinned), so its MCP
   client library version is not statically knowable from this repo.
5. **No new firing alerts** in `office` or `ai` (ignore Watchdog/InfoInhibitor) —
   re-run the §2 pre-check query and diff.

## 5. Rollback

Stateless bridge, no data, no migration — a straight image-tag revert:

```bash
git revert --no-edit <bump-commit-sha>
git push
flux reconcile hr -n office nextcloud-mcp --with-source   # optional, speeds up the 30m interval
kubectl get deploy -n office nextcloud-mcp -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'
# expect: ghcr.io/cbcoutinho/nextcloud-mcp-server:0.184.5
kubectl get pods -n office -l app.kubernetes.io/name=nextcloud-mcp
# expect: 1/1 Running, 0 restarts after settle
```

Confirm the cluster is back by re-running Verification §4.3–4.4 against the
reverted pod — the tool-list call and the OpenClaw round-trip should both
match the pre-bump baseline exactly.

## 6. Interference notes

- **Cross-namespace consumer, not a shared-infra token.** OpenClaw
  (`ai` namespace) consumes this server as its `nextcloud` MCP tool
  (`kubernetes/apps/ai/openclaw/app/mcporter-config.yaml`) for files, notes,
  calendar, contacts, deck and tables. This plan edits nothing in `ai`, but
  the blast radius of a bad bump includes OpenClaw losing that tool
  silently (outbound keeps working, the tool call just starts failing) — the
  window agent should treat a post-bump OpenClaw nextcloud-tool failure as
  belonging to THIS plan, not as unrelated `ai` noise.
- **`mcpo-python-3.14`** (queued `sat-attended:2026-09-12`) also touches the
  `ai` namespace (a different app, `mcpo`, unrelated resources — no shared
  Deployment/PVC/HelmRelease). Not a hard conflict, but if both this plan and
  that one land in the same window, sequence them with a verification gap
  between so a failure in `ai`'s MCP tooling can be attributed to the right
  change rather than blamed on whichever ran second.
- **`bitnamilegacy-exit-nextcloud-db`** (namespace `office`, status
  `blocked`, `window: null`) is the other open item touching the Nextcloud
  stack. It is unwindowed today so there is no scheduling collision — but it
  restarts `deployment/nextcloud` and its sidecars when revived. If both this
  plan and that one are ever live in the same window, re-add it to
  `conflicts_with` and sequence this (lighter, stateless) bump first.
- **Flux `dependsOn: nextcloud`** is this Kustomization's only structural
  coupling — an ordering constraint (namespace/reconcile-first), confirmed
  NOT a version coupling by reading every release note in range (§1.2). No
  action needed beyond the §2 sanity read.
- Nothing here touches Longhorn, cert-manager, cilium, coredns, or the
  envoy-internal Gateway's other routes — safe to run alongside unrelated
  `office`/`ai` work that doesn't share a resource listed in `touches`.

## What I could not verify

- **mcporter's actual MCP client protocol/SDK version** — it is installed
  fresh via `install_npm mcporter` at each OpenClaw pod start, unpinned in
  this repo, so I cannot confirm from static analysis whether it is on
  `mcp>=2.1` or whether it would even notice the elicitation-degradation
  change. Verification §4.4 is written to catch this empirically since it
  can't be proven ahead of time.
- Whether `F-f02df447`'s CRITICAL/HIGH tally actually narrows after the bump
  (base-OS package drift is independent of the app-level version) — flagged
  as a post-bump check, not a blocker.

---
plan_id: envoy-gateway-phase2
component: envoy-gateway
pr: null
kind: migration-bulk                # Phase 2: internal bulk conversion (~76 Ingresses)
current: "internal apps on ingress-nginx"
target: "all internal apps on HTTPRoute/envoy-internal; nginx snippet-annotations disabled"
update_type: migration
risk: medium                        # per-app blast radius only; each batch = one
                                    # commit = one git revert; DNS flips back via
                                    # k8s-gateway TTL 60 on revert
est_duration_min: 120               # spans 2 sessions (thu 08-20 start, tue 08-25 finish)
needs_reboot: false
touches:
  namespaces: [all-internal]        # batch-per-namespace commits
  resources:
    - "~76 internal Ingress -> HTTPRoute conversions (app-template route: block where possible)"
    - "9 remaining forward-auth apps -> SecurityPolicy pattern from phase1 pilot"
    - "nextcloud/whiteboard security headers -> ResponseHeaderModifier"
    - "langfuse: HTTPRoute + app-side cookie env (NextAuth) + explicit OAuth test"
    - "wazuh/kibana: HTTPRoute + EG Backend tls.insecureSkipVerify"
    - "HARDENING MILESTONE: allow-snippet-annotations=false on both nginx HRs"
  shared: [auth]                    # forward-auth apps convert one at a time;
                                    # authentik provider mode flips per app
depends_on: [envoy-gateway-phase1]  # GATED: phase1 pilots must be GO (operator review)
conflicts_with: []                  # not with authentik/cloudflared/cert-manager plans
status: scheduled
window: "thu-early:2026-08-20"      # session 1 of 2; session 2 = tue-early:2026-08-25
                                    # (finish + hardening milestone). Batches that
                                    # miss simply carry to the next slot.
auto_execute: false
sops_refs:
  - docs/troubleshooting/ingress-migration-plan.md
generated: "2026-08-07"
---

# Envoy Gateway — Phase 2: internal bulk (~76 objects, 2 sessions)

Execute per the decision doc §P2. Batch by namespace, one commit per batch,
flux-local CI green before merge; `gethomepage.dev/*` annotations move
Ingress→HTTPRoute in the same commit (no double discovery). app-template apps
(~60) use the chart's native `route:` block; foreign charts get standalone
httproute.yaml. Forward-auth apps replicate the pilot-B pattern (HTTPRoute +
outpost route + ReferenceGrant + SecurityPolicy + ak provider mode flip).
langfuse keeps its Ingress until its OAuth loop is proven on the new path.

**Session 2 exit criterion:** zero internal Ingresses left except langfuse
(if still soaking) → set `allow-snippet-annotations: false` +
`annotations-risk-level: High` on BOTH nginx HelmReleases (neutralizes the
injection-CVE class per AR-055's compensating-control commitment).

Verify per batch: app serves via .103 (k8s-gateway flipped), auth loop OK on
converted auth apps, homepage tile intact, 0 firing alerts. Rollback per app:
revert the commit.

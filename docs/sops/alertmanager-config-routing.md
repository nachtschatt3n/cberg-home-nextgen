# SOP: AlertmanagerConfig Root-Route Isolation

> Description: How the Prometheus Operator merges multiple `AlertmanagerConfig` CRs into one generated Alertmanager config, why an unscoped root route silently double-pages, and how to prove routing is correct from the generated config instead of trusting how a CR reads.
> Version: `2026.09.05`
> Last Updated: `2026-09-05`
> Owner: `platform`

---

## 1) Description

Closes sweep finding `F-cdcf8c58` ("two AlertmanagerConfigs each rendered an
unmatched root route, double-paging every alert"). This SOP documents:

- How the Prometheus Operator composes multiple `AlertmanagerConfig` CRs into
  the single generated Alertmanager configuration, and why that composition
  is **additive, not exclusive**, by default.
- The rule every non-primary `AlertmanagerConfig` must follow so it cannot
  silently become a second catch-all.
- How to read the operator-generated config directly (`amtool config routes
  test`) to prove routing behavior, because a CR that *looks* correctly
  scoped can still overlap with another CR in ways that are invisible from
  reading either CR alone.

- Scope: `monitoring` and `storage` namespaces, `kube-prometheus-stack`
  Alertmanager StatefulSet, all `AlertmanagerConfig` CRs cluster-wide.
- Prerequisites: `kubectl` access to the `monitoring` namespace; no local
  tooling needed — `amtool` ships inside the `alertmanager` container image.
- Out of scope: Alert *rule* authoring (see `docs/sops/monitoring.md` §
  "Alert Rule Authoring Gotchas"), the `OnNamespace` matcher-strategy hazard
  (already covered in `docs/sops/monitoring.md` § "AlertmanagerConfig
  Namespace Routing" — a related but distinct failure mode: that one is about
  an *implicit* namespace matcher dropping alerts; this one is about the
  *absence* of a matcher duplicating them).

---

## 2) Overview

| Setting | Value |
|---------|-------|
| Namespace(s) | `monitoring`, `storage` |
| Source of truth | `kubernetes/apps/*/[app]/alertmanager-*-config.yaml`, `kubernetes/apps/monitoring/kube-prometheus-stack/app/claude-watch-webhook.yaml` |
| Generated config | Secret `alertmanager-kube-prometheus-stack-generated` (key `alertmanager.yaml.gz`), namespace `monitoring` |
| Rendered-config-on-disk | `/etc/alertmanager/config_out/alertmanager.env.yaml` inside the `alertmanager` container |
| Route-test tool | `amtool config routes test` (bundled in the `alertmanager` container, no local install) |
| Critical dependency | `alertmanagerConfigMatcherStrategy: {type: None}` (see `docs/sops/monitoring.md`) — with this set, CRs get **no** automatic namespace scoping, so an empty `matchers: []` root route really does mean "every alert, from every namespace" |

**As of this writing (2026-09-05), the cluster has 3 live `AlertmanagerConfig` CRs:**

| CR | Root matcher | Root receiver | Notes |
|----|---------------|----------------|-------|
| `monitoring/claude-watch-webhook` | none (`matchers: []`) | `claude-webhook` (Mac-side bridge) | Intentional catch-all — mirrors every alert to a *different* destination, parallel to Telegram, not competing with it |
| `monitoring/telegram` | none (`matchers: []`) | `telegram` | Intentional primary catch-all for Telegram |
| `storage/telegram` | `category="storage"` | `telegram` | **Same destination as `monitoring/telegram`** — this is the pairing that matters |

---

## 3) Blueprints

- Source of truth file(s):
  - `kubernetes/apps/monitoring/kube-prometheus-stack/app/alertmanager-telegram-config.yaml`
  - `kubernetes/apps/storage/longhorn/app/alertmanager-telegram-config.yaml`
  - `kubernetes/apps/monitoring/kube-prometheus-stack/app/claude-watch-webhook.yaml`
- Related manifests: `kubernetes/apps/monitoring/kube-prometheus-stack/app/helmvalues.yaml`
  (`alertmanager.alertmanagerSpec.alertmanagerConfigMatcherStrategy.type: None`)
- Required IDs/constants: none — labels only (`severity`, `category`,
  `alertname`). Bot tokens and chat IDs live in
  `kubernetes/apps/*/app/secret.sops.yaml` / inline `telegramConfigs.chatID`
  and must never appear unredacted outside SOPS-encrypted files.

```yaml
# Minimal pattern for a NON-PRIMARY AlertmanagerConfig sharing a destination
# with an existing catch-all CR (e.g. adding a 4th CR that also pages Telegram):
apiVersion: monitoring.coreos.com/v1alpha1
kind: AlertmanagerConfig
metadata:
  name: <new-config>
  namespace: <ns>
spec:
  route:
    receiver: telegram
    matchers:
      # REQUIRED: a matcher that no other Telegram-destined CR's alerts can
      # also satisfy. A label check is not enough on its own — see §4 and
      # the "Current Reality" note in §5 for why.
      - name: category
        value: <ns-specific-value>
    routes: []
  receivers:
    - name: telegram
      telegramConfigs: [...]
```

---

## 4) Operational Instructions

### How the merge actually works

The Prometheus Operator watches every `AlertmanagerConfig` matched by the
Alertmanager CR's `alertmanagerConfigSelector` / `alertmanagerConfigNamespaceSelector`
and renders **each CR's `spec.route` as its own top-level sibling** under a
single synthetic global root (`route.routes[]` in the generated config,
labelled `<namespace>/<cr-name>/<receiver>`). Two properties of this merge
are the whole story:

1. **Every synthesized top-level sibling gets `continue: true`.** This is
   set by the operator itself, not something you control from the CR. It
   exists so that independent CRs from different teams/apps can coexist
   without one silently swallowing alerts meant for another. The direct
   consequence: **the operator will happily evaluate every sibling against
   every alert** — nothing stops two siblings from both matching the same
   alert and both delivering it.
2. **A route node's own receiver is a fallback, not just a container.** If a
   node's matcher matches an alert and *none* of its children also match,
   the alert is delivered to that node's own `receiver` — not dropped. This
   means giving a root route a receiver (as every `AlertmanagerConfig` must)
   makes that CR a full delivery path even for alerts none of its `routes:`
   children were written to catch.

Put together: **duplicate delivery only requires two top-level siblings
whose matchers can both be satisfied by the same alert AND whose ultimate
receivers point at the same destination.** "Same destination" does not
require the same receiver *name* — `monitoring/telegram/telegram` and
`storage/telegram/telegram` are different receiver entries in the generated
config, but both hold `telegramConfigs` pointed at the same bot/chat, so
both independently POST to Telegram for any alert that satisfies both trees.

### The rule

**Every non-primary `AlertmanagerConfig` root route must carry a matcher
that (a) is not empty and (b) cannot ALSO be satisfied by any other CR
already routing to the same destination — including via that other CR's own
child routes, not just its root matcher.** Read that second clause twice: a
correctly-scoped root matcher on the new CR is necessary but **not
sufficient** if an existing broader CR's *children* independently reach the
same category of alert (see §5 for the case where this bit us even after
the "fix"). The only way to be sure is to render the merged config and test
it — never reason from the CRs in isolation.

### Adding a new AlertmanagerConfig safely

1. Decide the destination (receiver) and check whether any existing CR
   already routes to it (`kubectl get alertmanagerconfigs -A`, then inspect
   each `spec.route`/`spec.receivers` for the same webhook URL / bot+chat).
2. Write a root matcher that is disjoint from every sibling already reaching
   that destination — not just "scoped," but scoped in a way nothing else
   overlaps.
3. Apply, then immediately run the `amtool config routes test` verification
   in §6 with label combinations spanning (a) your new CR's intended
   traffic, (b) each existing sibling's intended traffic, and (c) the
   intersection, if any labels could plausibly co-occur.
4. Commit only after the generated config confirms exactly one receiver per
   tested label combination (or the intended number, for genuinely parallel
   destinations like the Claude webhook mirror).

---

## 5) Examples

### Example A: the catastrophic case, fixed 2026-09-03 (commit `3d43caaf`)

Before the fix, `storage/telegram`'s root route had `matchers: []` — a
second, fully unscoped catch-all pointed at the same Telegram bot/chat as
`monitoring/telegram`. Every `severity=warning` alert from anywhere in the
cluster matched both `monitoring/telegram`'s `severity="warning"` child and
`storage/telegram`'s own root fallback receiver, so it was delivered twice.
Fix: scope `storage/telegram`'s root to `category="storage"` (see the CR's
own inline comment for the original incident writeup). This closed the
"every alert" case.

### Example B: Current Reality — a narrower duplicate is still live

Verified against the running generated config on 2026-09-05 (`amtool config
routes test`, exact commands in §6):

```
severity=warning, category=storage  -> monitoring/telegram/telegram, storage/telegram/telegram   (Telegram fires TWICE)
severity=critical, category=storage -> monitoring/telegram/telegram, storage/telegram/telegram   (Telegram fires TWICE)
category=storage (no severity)      -> monitoring/telegram/telegram, storage/telegram/telegram   (Telegram fires TWICE)
severity=warning, category=network  -> monitoring/telegram/telegram                               (fires once, correct)
severity=critical (no category)     -> monitoring/telegram/telegram                               (fires once, correct)
```

**The 2026-09-03 fix reduced the blast radius from "every alert" to "every
`category=storage` alert," but did not eliminate the duplicate.** Root
cause, per the mechanics in §4:

- `monitoring/telegram`'s root route has no `category` exclusion at all — it
  is still the intentional global catch-all, so it correctly (by design)
  matches `category=storage` alerts too, via its own `severity="warning"` /
  `severity="critical"` children (or its own root fallback for anything
  else).
- `storage/telegram`'s root matcher (`category="storage"`) independently
  matches the *same* alert, because the operator's forced `continue: true`
  on every top-level sibling means `monitoring/telegram` matching first does
  not stop `storage/telegram` from also being evaluated.
- `storage/telegram`'s own root `receiver: telegram` is a functioning
  fallback (§4, point 2), so even alerts that miss all of its explicit
  `routes:` children (e.g. `severity=critical,category=storage`, which has
  no matching child) still deliver via the parent node itself.

So this finding is **not closed by the 2026-09-03 commit** — it is narrower,
not gone. It has not paged as "every alert doubles" since the fix (which is
presumably why it read as resolved), but any storage-category alert (the
volumes/Longhorn/`cifs-*` alert family) is still doubled. This SOP does not
apply a further code fix (out of scope for a doc-only sweep close); it
records the mechanism and the exact test so the fix can be verified when
made. Candidate remediations, for whoever picks this up:

- Fold `storage/telegram`'s overrides into `monitoring/telegram` as
  ordered children (specific-before-general) instead of a second sibling
  tree — eliminates the parallel-path problem structurally.
- Or: exclude `category="storage"` on `monitoring/telegram`'s `severity`
  children (`category!=storage` matcher) so that category is handled
  exclusively by `storage/telegram`.

---

## 6) Verification Tests

`amtool config routes test` evaluates the **live rendered config** inside
the Alertmanager pod against a synthetic label set and prints the receivers
that would fire — no alert is actually sent, nothing pages. This is the
authoritative test; do not substitute reading the CRs.

### Test 1: single delivery for a non-overlapping alert

```bash
kubectl exec -n monitoring alertmanager-kube-prometheus-stack-0 -c alertmanager -- \
  amtool config routes test --config.file=/etc/alertmanager/config_out/alertmanager.env.yaml \
  severity=warning category=network
```

Expected:
- Exactly one Telegram-destined receiver in the comma-separated output
  (today: `monitoring/claude-watch-webhook/claude-webhook,monitoring/telegram/telegram`
  — the webhook mirror is a separate, intentional destination, not a
  duplicate).

If failed (two `*/telegram/telegram`-style receivers appear):
- A new sibling `AlertmanagerConfig` has a root matcher — or a fallback via
  its own root receiver — that overlaps this label set. `kubectl get
  alertmanagerconfigs -A` and inspect each for `category`/`severity`
  matchers that could also be satisfied.

### Test 2: assert the known-open residual duplicate (regression guard)

```bash
kubectl exec -n monitoring alertmanager-kube-prometheus-stack-0 -c alertmanager -- \
  amtool config routes test --config.file=/etc/alertmanager/config_out/alertmanager.env.yaml \
  severity=warning category=storage
```

Expected (current, as of 2026-09-05 — this is a KNOWN OPEN gap, see §5B):
- `monitoring/telegram/telegram,storage/telegram/telegram` both present —
  confirms the residual duplicate is exactly what §5 Example B describes.
- **When this is fixed**, expected output becomes a single
  `*/telegram/telegram` receiver. Update this SOP's Example B and this
  test's "Expected" block in the same change that fixes the routing —
  otherwise this SOP goes stale the moment the underlying bug is closed.

If the output ever regresses to include the Claude webhook receiver missing,
or three+ Telegram-family receivers: something else has been added to the
merge; re-run §6 Test 3 (full enumeration) and re-derive the matrix.

### Test 3: full enumeration after any AlertmanagerConfig change

```bash
for combo in "severity=critical" "severity=warning" "severity=info" \
             "severity=warning category=storage" "severity=critical category=storage" \
             "category=storage" "alertname=Watchdog" "alertname=InfoInhibitor"; do
  echo "=== $combo ==="
  kubectl exec -n monitoring alertmanager-kube-prometheus-stack-0 -c alertmanager -- \
    amtool config routes test --config.file=/etc/alertmanager/config_out/alertmanager.env.yaml $combo
done
```

Expected:
- `Watchdog`/`InfoInhibitor` resolve to `null` receivers only (no Telegram,
  no webhook).
- Every other combination resolves to exactly one Telegram-family receiver
  **except** the still-open `category=storage` combinations (Test 2).
- Re-run this after adding, removing, or re-scoping any
  `AlertmanagerConfig`, and paste the delta into the commit message.

---

## 7) Troubleshooting

| Symptom | Likely Cause | First Fix |
|---------|--------------|-----------|
| Telegram alert arrives twice with identical timestamp/content | Two `AlertmanagerConfig` root routes both reach Telegram for the same label set | Run §6 Test 3, find the overlapping pair, add a disjoint matcher to the newer/narrower CR |
| New `AlertmanagerConfig` never delivers anything | `alertmanagerConfigMatcherStrategy` reverted to `OnNamespace` after a chart upgrade, or the CR's `metadata.labels` no longer match the Alertmanager CR's `alertmanagerConfigSelector` | Check `docs/sops/monitoring.md` § "AlertmanagerConfig Namespace Routing"; `kubectl get alertmanager kube-prometheus-stack -n monitoring -o jsonpath='{.spec.alertmanagerConfigMatcherStrategy}'` |
| A "more specific" child route never fires even though its matcher is correct | It is listed **after** a broader sibling matcher in the same `routes:` list — first match wins unless the broader one sets `continue: true` | Reorder so the more specific child comes first, or add `continue: true` (only if you intend BOTH to fire) |
| Duplicate persists after scoping the newer CR's root matcher | The OLDER/broader CR's own root receiver is acting as a fallback for alerts none of its children caught (§4 point 2) — scoping only the new CR doesn't stop the old catch-all's fallback path | Exclude the new CR's label from the old CR's catch-all children (`label!=value` matcher), or restructure as nested children of one CR instead of two siblings |

```bash
# Quick debugging: dump the full rendered config
kubectl get secret alertmanager-kube-prometheus-stack-generated -n monitoring \
  -o jsonpath='{.data.alertmanager\.yaml\.gz}' | base64 -d | gunzip

# List every AlertmanagerConfig and its root matcher/receiver at a glance
kubectl get alertmanagerconfigs -A -o json | python3 -c "
import sys, json
for cr in json.load(sys.stdin)['items']:
    r = cr['spec']['route']
    print(f\"{cr['metadata']['namespace']}/{cr['metadata']['name']}: matchers={r.get('matchers', [])} receiver={r.get('receiver')}\")"
```

---

## 8) Diagnose Examples

### Diagnose Example 1: "operator sent a duplicate page, why?"

```bash
# 1. Get the exact labels of the duplicated alert from either Telegram message
#    or Alertmanager UI (port-forward svc/kube-prometheus-stack-alertmanager 9093:9093)

# 2. Feed those exact labels to amtool
kubectl exec -n monitoring alertmanager-kube-prometheus-stack-0 -c alertmanager -- \
  amtool config routes test --config.file=/etc/alertmanager/config_out/alertmanager.env.yaml \
  severity=<value> category=<value> alertname=<value>
```

Expected:
- More than one `*/telegram/*`-style (or whatever the destination receiver
  family is) entry in the output confirms and reproduces the duplicate
  deterministically — this is your proof, not a guess.

If unclear:
- Dump the full generated config (§7 quick debug) and manually trace which
  top-level sibling(s) the label set satisfies, and whether it's a child
  match or a parent-fallback match (§4 point 2) — the distinction changes
  the fix.

### Diagnose Example 2: "did my new AlertmanagerConfig actually get merged?"

```bash
# Confirm the CR is selected by the Alertmanager CR's selectors
kubectl get alertmanager kube-prometheus-stack -n monitoring \
  -o jsonpath='{.spec.alertmanagerConfigSelector}{"\n"}{.spec.alertmanagerConfigNamespaceSelector}'

# Confirm it shows up as its own top-level sibling in the generated config
kubectl get secret alertmanager-kube-prometheus-stack-generated -n monitoring \
  -o jsonpath='{.data.alertmanager\.yaml\.gz}' | base64 -d | gunzip \
  | grep -A2 '<namespace>/<cr-name>/'
```

Expected:
- A `- receiver: <namespace>/<cr-name>/<receiver-name>` block present under
  the top-level `route.routes:` list.

If unclear:
- Not present → check CR labels match the selector above, or that the
  Alertmanager Operator's reconcile loop actually ran (`kubectl logs -n
  monitoring -l app.kubernetes.io/name=kube-prometheus-stack-operator
  --tail=50`).

---

## 9) Health Check

```bash
# Run the full-enumeration test (§6 Test 3) and confirm the ONLY
# multi-receiver Telegram-family result is the known-open category=storage
# gap (§5 Example B). Any OTHER combination showing 2+ Telegram-family
# receivers is a new regression, not the known issue.
for combo in "severity=critical" "severity=warning" "severity=info category=storage"; do
  kubectl exec -n monitoring alertmanager-kube-prometheus-stack-0 -c alertmanager -- \
    amtool config routes test --config.file=/etc/alertmanager/config_out/alertmanager.env.yaml $combo
done
```

Expected:
- No unexpected duplicate receiver pairs. `severity=info category=storage`
  and similar combinations should resolve to a single Telegram-family
  receiver, or none for `null`-routed alertnames.

---

## 10) Security Check

```bash
# Confirm bot token / chat ID never appear in a non-SOPS file
rg -n "bot_token|chatID|chat_id" kubernetes/ --glob '!*.sops.yaml' --glob '!*secret*'

# Confirm the generated-config Secret is the only place the rendered
# (decrypted) routing tree lives outside the cluster's own storage —
# never paste its output into a commit, PR body, or this repo.
kubectl get secret alertmanager-kube-prometheus-stack-generated -n monitoring -o jsonpath='{.type}'
```

Expected:
- No plaintext bot tokens/chat IDs outside `*.sops.yaml`.
- This SOP itself contains only label names/values (`severity`, `category`,
  `storage`) — no bot tokens, chat IDs, webhook URLs, or real domains. The
  webhook URL example (`http://192.168.30.111:8788/alertmanager`) is the
  operator's own trusted-VLAN Mac mini, already documented elsewhere in this
  repo (`claude-watch-webhook.yaml`), not a secret.

---

## 11) Rollback Plan

```bash
# If a new/changed AlertmanagerConfig matcher causes alerts to stop
# delivering entirely (over-scoped instead of under-scoped):
git log --oneline -- kubernetes/apps/<ns>/<app>/alertmanager-*-config.yaml | head -5
git revert <bad-commit-sha>   # or hand-edit matchers back, commit, push
# Flux reconciles on push; confirm with §6 Test 1/3 against the labels that
# stopped delivering.
```

No cluster-side rollback is needed — `AlertmanagerConfig` is a declarative
CR; reverting the git commit and letting Flux reconcile is sufficient.

---

## 12) References

- `docs/sops/monitoring.md` § "AlertmanagerConfig Namespace Routing" — the
  related-but-distinct `OnNamespace` matcher-strategy hazard (alerts
  dropped, not duplicated).
- `docs/sops/failed-job-alerting.md`
- `kubernetes/apps/monitoring/kube-prometheus-stack/app/alertmanager-telegram-config.yaml`
- `kubernetes/apps/storage/longhorn/app/alertmanager-telegram-config.yaml`
- `kubernetes/apps/monitoring/kube-prometheus-stack/app/claude-watch-webhook.yaml`
- Prometheus Operator docs: `AlertmanagerConfig` CRD, `alertmanagerConfigMatcherStrategy`
- Finding: `F-cdcf8c58` (`runbooks/policy-cli.py finding show F-cdcf8c58`)
- Fix commit for the catastrophic (every-alert) case: `3d43caaf`

---

## Version History

- `2026.09.05`: Initial SOP. Closes `F-cdcf8c58`. Documents operator merge
  mechanics, the disjoint-matcher rule, and records that the 2026-09-03 fix
  (`3d43caaf`) narrowed but did not eliminate the duplicate — a residual
  double-page for every `category=storage` alert is confirmed live via
  `amtool config routes test` and captured as a regression-guard test (§6
  Test 2) pending an actual routing fix.

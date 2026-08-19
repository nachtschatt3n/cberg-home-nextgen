# SOP: Flux dependsOn Revision Gate — why a push makes unrelated Kustomizations go not-Ready

> Description: Explains Flux's revision-gated `dependsOn`, why a burst of commits makes large numbers of unrelated Kustomizations report not-Ready, and how to tell that churn apart from a genuine failure.
> Version: `2026.08.19`
> Last Updated: `2026-08-19`
> Owner: `Platform`

---

## 1) Description

`dependsOn` between Flux Kustomizations gates on **revision**, not only on
readiness. A dependent will not proceed until its dependency has applied *the
same source revision the dependent itself is at*. Every push therefore re-arms
the gate for every dependent of every changed Kustomization, and the fan-out
follows the dependency graph.

The result is a burst of not-Ready Kustomizations in namespaces that have
nothing to do with what you changed — and, critically, whose error messages
name a **dependency** rather than your commit. The mechanism is invisible from
the message text, which is why it gets misdiagnosed as an outage in whatever
component the message happens to name.

## 2) Overview

**Every Kustomization re-reconciles on every new source revision — including
the ones you depend on.** While a dependency is mid-reconcile its `Ready`
condition goes `Unknown`, and any dependent that happens to evaluate the gate
in that window records a failure. So one push produces a rolling wave of
not-Ready dependents that has nothing to do with health.

Three states appear during that wave, and **none of them implies a fault**:

| Status / message | What it means |
|---|---|
| `Unknown` — `Reconciliation in progress` | this Kustomization is mid-apply right now |
| `False` — `dependency '<ns>/<name>' revision is not up to date` | the dependency is healthy but has not yet applied the revision this dependent is at |
| `False` — `dependency '<ns>/<name>' is not ready` | at the moment this dependent last evaluated the gate, the dependency was not Ready — **usually because the dependency was itself mid-reconcile** |

> **The messages are LAST-ATTEMPT SNAPSHOTS, not live state.** A dependent
> keeps displaying the conclusion it drew at its last reconcile until its next
> one. The dependency can be perfectly healthy *now* while a dozen dependents
> still advertise it as broken.
>
> Measured 2026-08-19: `storage/longhorn` went `Ready=True` at **06:17:42Z**;
> `ai/anythingllm`, `office/nextcloud` and `home-automation/frigate` had
> concluded `dependency 'storage/longhorn' is not ready` at **06:17:41-42Z** —
> at or one second *before* the flip. Root demonstrably healthy (webhook
> endpoints 3/3, DaemonSet 3/3, HelmRelease Ready), messages stale by seconds.

**Therefore `is not ready` does NOT mean "investigate the dependency"** — that
rule, in the first version of this SOP, produced a false positive within
minutes of being written. The only sound triage is to ask the named dependency
its CURRENT state, not to read the dependent's stale opinion of it:

```bash
# The dependent's message names a dependency. Ask THAT object directly.
mise exec -- kubectl get kustomization -n storage longhorn \
  -o jsonpath='{range .status.conditions[?(@.type=="Ready")]}{.status} {.lastTransitionTime} {.message}{"\n"}{end}'
```

- dependency `Ready=True`, and its `lastTransitionTime` is at or after the
  dependent's → **stale snapshot, wait**;
- dependency genuinely not Ready for minutes → **investigate the dependency**.

**Measured, 2026-08-19.** Three commits landed 190 seconds apart during a
Longhorn chart upgrade. `storage/longhorn` has **36 direct dependents** plus
transitive ones (`monitoring/grafana` → `monitoring/unpoller`, …). Each commit
re-armed the gate across that whole subtree, staggered by each Kustomization's
own reconcile interval. Observed effect: the not-Ready set **rotated** rather
than drained — across one 90-second interval, 12 Kustomizations left the set
and 12 different ones entered, while the count moved only 27 → 26. Kustomizations
were entering the not-Ready set while the underlying storage layer was already
fully healthy.

## 3) Blueprints

N/A — this is Flux behaviour, not a deployable artefact.

## 4) Operational Instructions

**When you see a wide not-Ready fan-out after a push:**

1. Identify the ROOT the messages point at (usually one or two objects), and
   ask those objects their current state — do not triage on the dependents'
   messages, which are stale snapshots. Counting message shapes tells you
   nothing: in one measured fan-out the split was 0 *revision is not up to
   date* vs 15 *is not ready*, with the root fully healthy the whole time.

2. Judge recovery by **revision convergence**, measured from the API against
   the revision the CLUSTER actually fetched — not local `git rev-parse HEAD`
   (in a shared repo another agent's push moves it under you, and the cluster
   only knows what its GitRepository pulled), and not by grepping formatted
   CLI output (`flux get | grep -cv` miscounted 98 where the API showed 89
   converged of 136):

   ```bash
   REV=$(mise exec -- kubectl get gitrepository -n flux-system flux-system \
           -o jsonpath='{.status.artifact.revision}')
   mise exec -- kubectl get kustomizations -A -o json | mise exec -- python3 -c "
   import sys, json
   d = json.load(sys.stdin); rev = '$REV'
   lag = [i['metadata']['namespace'] + '/' + i['metadata']['name']
          for i in d['items']
          if (i.get('status', {}).get('lastAppliedRevision') or '') != rev]
   print(f'{len(d[\"items\"]) - len(lag)}/{len(d[\"items\"])} converged; lagging: {len(lag)}')"
   ```

3. **Stop pushing while you are measuring.** Each further commit re-arms the
   gate across the same subtree, so a stream of commits keeps the set rotating
   indefinitely and makes the system look stuck when it is making progress.

4. Do not mass-`flux reconcile` the dependents. They are waiting on a gate, not
   on a trigger; reconciling adds load without advancing the gate.

## 5) Examples

### Example 1: the gate, correctly read

```
office  nextcloud-mcp  False  dependency 'office/nextcloud' revision is not up to date
```

`office/nextcloud` is healthy. `nextcloud-mcp`'s source is at a newer revision
than nextcloud has applied. Nothing to do.

### Example 2: the message that looks like a failure and is not

```
databases  memgraph  False  dependency 'storage/longhorn' is not ready
```

Do not act on this line. Ask `storage/longhorn` directly. If it reports
`Ready=True` with a `lastTransitionTime` at or after memgraph's last
conclusion, memgraph is showing a stale snapshot from while longhorn was
mid-reconcile — wait for memgraph's next interval. Only if longhorn is *still*
not Ready, minutes later, is there anything to investigate.

## 6) Verification Tests

```bash
# 1) Everything converges to HEAD (the real success condition)
HEAD=$(git rev-parse --short HEAD)
mise exec -- flux get kustomizations -A | grep -cv "$HEAD"      # expect 0

# 2) No Kustomization is not-Ready for a NON-dependency reason
mise exec -- flux get kustomizations -A | awk '$5!="True"' | grep -v "dependency"
```

## 7) Troubleshooting

- **Set is static, not rotating** — membership unchanged across several polls
  *and no new commits landed in that time*: that is a stall, not the gate.
  Confirm by asking the named dependency its current state; if it has been
  not-Ready for minutes rather than seconds, investigate it.
- **A dependency is Ready but its dependents never converge** — check the
  dependency's `status.lastAppliedRevision` against the GitRepository revision;
  a dependency wedged on an *older* revision blocks the whole subtree
  indefinitely.
- **The fan-out never ends** — confirm nobody (including a concurrent agent) is
  still pushing. See "Committing in a SHARED worktree" in `AGENTS.md`.

## 8) Diagnose Examples

```bash
# Which Kustomizations depend on X (live, authoritative — a repo grep miscounts)
mise exec -- kubectl get kustomizations -A -o json | mise exec -- python3 -c "
import sys, json
d = json.load(sys.stdin)
target = ('storage', 'longhorn')
for i in d['items']:
    for dep in (i['spec'].get('dependsOn') or []):
        if (dep.get('namespace', 'storage'), dep.get('name')) == (target[0], target[1]):
            print(i['metadata']['namespace'] + '/' + i['metadata']['name'])"

# What revision has the dependency actually applied?
mise exec -- kubectl get kustomization -n storage longhorn \
  -o jsonpath='{.status.lastAppliedRevision}{"\n"}'
```

## 9) Health Check

```bash
HEAD=$(git rev-parse --short HEAD)
mise exec -- flux get kustomizations -A | grep -cv "$HEAD"
mise exec -- flux get kustomizations -A | awk '$5!="True"' | grep -cv "dependency"
```

Both zero == converged and healthy.

## 10) Security Check

N/A — no credentials, secrets, or exposure surface. Read-only diagnosis.

## 11) Rollback Plan

Nothing to roll back: the gate is normal Flux behaviour and resolves itself.
Rolling back a commit to "fix" it makes it worse — the revert is another
revision, which re-arms the gate again across the same subtree.

## 12) References

- `docs/sops/longhorn.md` — "Chart Upgrade Storm", the case that surfaced this
- `AGENTS.md` — "Committing in a SHARED worktree"
- `docs/sops/flux-upgrade.md`

## Version History

- `2026.08.19` (b): Corrected within the hour, by its own diagnostic. The
  original triage rule ("a population dominated by `is not ready` means
  investigate the dependency") gave a false positive on a demonstrably healthy
  `storage/longhorn`: dependents' messages are last-attempt SNAPSHOTS, and a
  dependency that is merely mid-reconcile makes its dependents record
  `is not ready`. Also: convergence must be measured from the API against the
  GitRepository's fetched revision, not by grepping `flux get` output against
  local `git rev-parse HEAD`.
- `2026.08.19`: Created. Written after a Longhorn chart upgrade produced ~60
  not-Ready Kustomizations, where the tail turned out to be driven by our own
  commit cadence rather than by storage. Corrects the earlier assumption that
  the not-Ready count falls monotonically.

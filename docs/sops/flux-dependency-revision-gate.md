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

Two distinct messages, two distinct meanings:

| Message | Meaning | Action |
|---|---|---|
| `dependency '<ns>/<name>' is not ready` | the dependency is genuinely unhealthy | investigate the dependency |
| `dependency '<ns>/<name>' revision is not up to date` | the dependency is *healthy* but has not yet applied the revision this dependent is at | **wait** — this is the revision gate |

The second is the one that gets misread. It names a component that is fine.

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

1. Split the messages by kind before doing anything else:

   ```bash
   mise exec -- flux get kustomizations -A | grep "revision is not up to date" | wc -l
   mise exec -- flux get kustomizations -A | grep "is not ready"              | wc -l
   ```

   A population dominated by *revision is not up to date* is the gate, not a
   fault.

2. Judge recovery by **revision convergence**, which is monotonic per-revision:

   ```bash
   HEAD=$(git rev-parse --short HEAD)
   mise exec -- flux get kustomizations -A | grep -cv "$HEAD"   # -> 0 when converged
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

### Example 2: an actual dependency failure

```
databases  memgraph  False  dependency 'storage/longhorn' is not ready
```

Here `storage/longhorn` really is not Ready — investigate it, not memgraph.

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
  with no new commits: that is a stall, not the gate. Investigate the named
  dependency.
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

- `2026.08.19`: Created. Written after a Longhorn chart upgrade produced ~60
  not-Ready Kustomizations, where the tail turned out to be driven by our own
  commit cadence rather than by storage. Corrects the earlier assumption that
  the not-Ready count falls monotonically.

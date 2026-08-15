# Maintenance plans — one file per held (non-safe) update

Each `<plan_id>.md` is an **executable upgrade plan** for one update that the
auto-updater HELD (see `docs/sops/auto-update.md`). An `upgrade-planner-agent`
writes it; the `maintenance-window-agent` reads the frontmatter to vet plans for
interference + side effects and to sequence the window; `runbooks/maintenance-plan.py`
reconciles held-updates ↔ plans ↔ windows and the sweep reports the schedule.

Plans are transient: once `status: executed` (and the change is in `main`),
delete the file in the same commit that lands the upgrade — don't accumulate
history here (git has it).

## Required frontmatter

```yaml
---
plan_id: affine-0.27.3            # kebab: <component>-<target>
component: affine                 # the app/chart/image short name
pr: 203                           # Renovate PR number (or null if none yet)
kind: image                       # image | chart | infra
current: "0.27.1"
target: "0.27.3"
update_type: minor                # patch | minor | major
risk: medium                      # low | medium | high  (weights 1/2/3)
est_duration_min: 20
needs_reboot: false               # true → only a window with allow_reboot:true
touches:                          # interference surface — be precise
  namespaces: [default]
  resources: [helmrelease/affine, pvc/affine-data]
  shared: []                      # shared infra perturbed: ingress, cert-manager,
                                  # cni/cilium, coredns, a shared DB, storage/longhorn
depends_on: []                    # other plan_ids that must run first
conflicts_with: []               # plan_ids that must NOT share a window
security_ref: null                # F-xxxxxxxx if this plan has a security driver.
                                  # The DETAIL stays in the DB — see "Public repo"
                                  # below. Never inline CVE IDs or counts here.
status: draft                     # draft | vetted | scheduled | awaiting-go |
                                  #   executed | blocked | superseded
                                  # awaiting-go = window agent asked for go/no-go;
                                  # the sweep re-reminds you every cycle until answered
window: null                      # e.g. "sun-window:2026-07-27" once scheduled
auto_execute: false               # opt-in unattended (only honored if risk:low + policy allows)
sops_refs:                        # SOPs the executor must follow
  - docs/sops/application-update.md
generated: "2026-07-25"
---
```

## Required body sections

1. **Summary & why held** — what changes, and the breaking/risk reason it isn't
   auto-safe (quote the release-notes / migration-guide evidence). If the driver
   is a security finding, cite it — do not describe it (see below).
2. **Pre-checks** — commands to confirm the cluster is in a safe pre-state
   (health, backups fresh, no in-flight reconcile).
3. **Steps** — the exact GitOps change (file edits, `sops` edits, commit/push),
   numbered and copy-pasteable. Follow the referenced SOPs.
4. **Verification** — how to prove success (Flux Ready, pods healthy, app probe,
   data intact).
5. **Rollback** — the exact revert path if verification fails.
6. **Interference notes** — anything the window agent must know (shared infra it
   restarts, ordering constraints, why `conflicts_with` is set).

## Public repo — vulnerability detail does NOT go in a plan

**This repository is public and plans sit here for weeks in `draft` / `blocked` /
`scheduled` state**, describing gaps that are still open. Full convention and the
exact boundary: **`docs/sops/vulnerability-disclosure.md`**.

The test, applied to every sentence you write:

> Does this tell a reader (a) *what is currently unfixed*, on (b) *a specific
> service we run*? **Both true → it does not go in the plan.**

| Write this | Not this |
|---|---|
| `security_ref: F-35f34061` + the reference block | "N fixable CRITICAL CVEs on controller vX.Y.Z" |
| image tags, chart versions, digests, build dates | a CVE ID tied to a currently-deployed artifact |
| "post-rebuild: 0 fixable CRITICAL" (a **zero** is safe) | any **non-zero** count for something we run |
| "exploitability assessed on the finding record" | "not network-reachable, exploitability low" |
| the verification *command* | the scanner *output* |

The same rule applies to the **commit message** that adds or updates the plan.

### How to cite instead

```bash
source runbooks/lib/sweep-pg-dsn.sh && sweep_pg_dsn_up

# The CVE check has almost certainly already filed it:
runbooks/policy-cli.py finding list --section security --grep <image-or-component>

# Attach your analysis (why the obvious fix doesn't work, what the real blocker is):
runbooks/policy-cli.py finding detail F-xxxxxxxx --plan <plan_id> --detail-file /tmp/d.md

# No finding exists (scanner blind spot, or a residual after partial remediation)?
runbooks/policy-cli.py finding add --title '<publish-safe one-liner>' \
  --component <name> --plan <plan_id> --detail-file /tmp/d.md

# Print the block to paste into the plan:
runbooks/policy-cli.py finding ref F-xxxxxxxx
```

Losing the "why" would be worse than the disclosure — that is why the reference
is mandatory, not optional. The finding **outlives the plan**: plans are deleted
once executed, the finding record is the durable answer to "why did we do this".

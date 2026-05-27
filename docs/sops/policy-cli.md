# SOP: policy-cli — operator interface for sweep_history policy tables

> Description: How to edit the four operator-curated policy tables that back the daily sweep (accepted_risks, slo_definitions, noise_suppressions, security_acceptances) from the operator's local Claude CLI / mise session.
> Version: `2026.05.27`
> Last Updated: `2026-05-27`
> Owner: `homelab-operator`

---

## 1) Description

After the 2026-05-27 policy-in-DB migration, four categories of operator decisions moved from git-tracked files into purpose-built tables in the sweep-history Postgres. `runbooks/policy-cli.py` is the operator's editing surface: it auto-port-forwards postgresql, decodes the `WRITER_DSN` secret, and runs typed INSERT/UPDATE/DELETE commands.

- Scope: editing policy from the operator's Mac (mise toolchain). The dashboard at `https://sweep.<DOMAIN>/policies/` is the read-only counterpart.
- Prerequisites: a working `kubectl` context (the same kubeconfig used by `runbooks/sweep-run.py`) + mise.
- Out of scope: schema changes (those live in `kubernetes/apps/databases/sweep-history/app/schema-configmap.yaml`).

---

## 2) Overview

The four tables and their CLI namespaces:

| Table | CLI namespace | Replaced |
|---|---|---|
| `accepted_risks` | `policy-cli risk …` | `docs/security-accepted-risks.md` |
| `slo_definitions` | `policy-cli slo …` | `runbooks/slo-catalog.yaml` |
| `noise_suppressions` | `policy-cli noise …` | `runbooks/noise_allowlist.yaml` |
| `security_acceptances` | `policy-cli sec …` | `runbooks/security_check_acceptances.py` |

Every entity supports `list`, `add`, `disable`, `delete`. Risk + SLO also have `show`. Risk also has `review` (bumps `last_reviewed_at`).

`enabled = false` is soft-disable — preferred over hard delete when you want an audit trail. Loaders treat disabled rows as absent.

---

## 3) Blueprints

N/A — this is a CLI tool, not a manifest. Implementation: `runbooks/policy-cli.py`.

---

## 4) Operational Instructions

Run from the repo root (or anywhere — mise activates the venv automatically):

```bash
# always-safe inspection
python3 runbooks/policy-cli.py stats
python3 runbooks/policy-cli.py risk list
python3 runbooks/policy-cli.py slo list
python3 runbooks/policy-cli.py noise list
python3 runbooks/policy-cli.py sec list

# edits
python3 runbooks/policy-cli.py risk add AR-028 \
    --description 'Authentik admin password rotated 2026-06-01' \
    --severity informational \
    --justification 'previous credential was committed; rotated + service restarted'

python3 runbooks/policy-cli.py slo add my-new-slo \
    --source prom --target 0.99 --window 30d \
    --numerator 'sum(up{job="my-job"})' \
    --denominator 'count(up{job="my-job"})' \
    --tag pilot --tag broker

# soft-disable preserves audit trail
python3 runbooks/policy-cli.py noise disable 42
python3 runbooks/policy-cli.py noise delete 42   # only when sure

# periodic backup snapshot
python3 runbooks/policy-cli.py export --out ~/policy-backups/$(date +%Y-%m-%d)/
```

The CLI auto-resolves the DSN via `kubectl get secret -n databases sweep-history`. If `SWEEP_PG_DSN` is already set in the env (e.g. inside `sweep-run.py`), the CLI reuses it and skips the port-forward.

---

## 5) Examples

### Add a new accepted risk

You decide that the noisy Falco rule for one container is acceptable for 30 days while you decide on a permanent mute path:

```bash
python3 runbooks/policy-cli.py risk add AR-028 \
    --description 'Falco rule 100412 (drop+exec) firing for legitimate Argo CD sync image' \
    --severity warning \
    --justification 'Argo CD container does a legitimate fs-write during sync; rule tuning planned for sprint X'
```

### Disable an SLO temporarily during a migration

```bash
python3 runbooks/policy-cli.py slo disable longhorn-volume-health
# … do migration work that intentionally creates degraded volumes …
python3 runbooks/policy-cli.py slo disable longhorn-volume-health  # idempotent — already disabled
# (no current `enable` subcommand; UPDATE via psql or re-add via `delete` + `add`)
```

### Add a noise suppression for a new flaky device

```bash
python3 runbooks/policy-cli.py noise add \
    --category flaky_iot_devices \
    --match-key name \
    --match-value 'Doorbell (Aqara)' \
    --note 'Aqara T1 doorbell — battery-saving sleep cycle causes hourly reconnects'
```

### Whitelist a new external-ingress app

```bash
python3 runbooks/policy-cli.py sec add \
    --category external_ingress_accepted \
    --pattern 'new-public-app' \
    --ar-id AR-027 \
    --note 'app is read-only; auth handled by app itself'
```

---

## 6) Verification Tests

After any add/disable/delete:

```bash
python3 runbooks/policy-cli.py stats                  # row counts shift as expected
python3 runbooks/policy-cli.py <ns> list              # newly-added row visible
```

For accepted_risks: rerun security-check.py end-to-end and confirm the matching finding is now tagged `🛡️ [AR-NNN]` instead of being flagged critical/warning:

```bash
SWEEP_PG_DSN=... python3 runbooks/security-check.py | grep -F "[AR-028]" || echo "AR-028 not yet matching anything"
```

For SLOs: rerun slo-check.py:

```bash
SWEEP_PG_DSN=... python3 runbooks/slo-check.py --once --no-write
```

Browse the dashboard:

```
https://sweep.<DOMAIN>/policies/                  # landing
https://sweep.<DOMAIN>/policies/accepted-risks    # row list
https://sweep.<DOMAIN>/policies/slos
https://sweep.<DOMAIN>/policies/noise
https://sweep.<DOMAIN>/policies/security
```

---

## 7) Troubleshooting

**"port-forward postgresql:5432 timed out"** — kubectl context not pointing at the cluster, or the pod isn't running. Run `kubectl get pod -n databases` and confirm `postgresql-*` is `Running 1/1`.

**"could not decode sweep-history WRITER_DSN"** — the SOPS secret `sweep-history` in `databases` namespace is missing or unreadable. Check `kubectl get secret -n databases sweep-history -o yaml`. Re-apply manifests if needed via Flux.

**"AR-XXX already exists"** on `risk add` — the AR-ID is already in use. Either pick a new ID or `delete` first.

**"permission denied for table accepted_risks"** on a write — `sweep_writer` should have DML. Verify with `psql -c '\dp accepted_risks'`. If grants are missing, re-run the init Job (bump to v3 or higher).

---

## 8) Diagnose Examples

```bash
# Direct psql session (requires port-forward first)
kubectl port-forward -n databases svc/postgresql 5433:5432 &
psql "$(kubectl get secret -n databases sweep-history -o jsonpath='{.data.WRITER_DSN}' \
       | base64 -d | sed 's|postgresql\.databases\.svc\.cluster\.local:5432|127.0.0.1:5433|')"

# In psql:
\dt                                            # all tables
SELECT ar_id, severity, status FROM accepted_risks;
SELECT name, target, window_size FROM slo_definitions WHERE enabled;
SELECT category, COUNT(*) FROM noise_suppressions GROUP BY category;
```

---

## 9) Health Check

`policy-cli stats` is the quick health check — counts should be within ~5 of historical baseline (27 ARs, 3 SLOs, ~24 noise, ~88 security acceptances as of 2026-05-27). Significant drops mean something deleted rows en masse — inspect with `policy-cli risk list` etc.

---

## 10) Security Check

- The CLI uses `sweep_writer` DSN (DML, no DDL). It cannot create or drop tables — schema is GitOps-controlled via the init Job manifest.
- The DSN secret is SOPS-encrypted at rest; only operators with the age key can decode it locally.
- Dashboard `/policies/*` endpoints are LAN-only (internal ingress, no Authentik) — same exposure surface as the rest of the sweep dashboard.
- `policy-cli export` writes plain-text YAML to disk — store backup directories somewhere encrypted (e.g. inside the operator's encrypted home dir, not in plain-text on a shared volume).

---

## 11) Rollback Plan

To roll back a recent edit:

1. Find the row ID via `policy-cli <ns> list`.
2. Either `policy-cli <ns> delete <ID>` (hard) or `policy-cli <ns> disable <ID>` (soft).
3. For accepted_risks, also consider whether the matching findings should be re-flagged: rerun `security-check.py` after the change.
4. For deleted SLOs, the historical `slo_snapshots` rows remain — useful evidence even after the definition is gone.

To restore from a `policy-cli export` snapshot: import via direct psql `COPY FROM` (no `import` subcommand today — Phase 3 polish task).

---

## 12) References

- [SOP-TEMPLATE.md](SOP-TEMPLATE.md) — section structure
- [sli-catalog.md](sli-catalog.md) — SLO inventory + when to add a new SLO
- `runbooks/policy-cli.py` — the CLI implementation
- `runbooks/sweep-run.py` — shares the same port-forward + DSN mechanic
- `kubernetes/apps/databases/sweep-history/app/schema-configmap.yaml` — the four table schemas
- `containers/sweep-dashboard/app/main.py` — read-only `/policies/*` and `/api/policies/*` route handlers

---

## Version History

| Date | Version | Change |
|---|---|---|
| 2026-05-27 | 2026.05.27 | Initial — Phase 3 of policy-in-DB migration |

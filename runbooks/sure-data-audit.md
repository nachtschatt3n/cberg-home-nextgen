# Sure data audit (weekly)

Read-only weekly audit of the Sure finance app's data quality. Catches three things that the AI pipelines (`AutoCategorizeJob`, `AutoDetectMerchantsJob`, transfer auto-pairing) produce as silent garbage over time:

1. **Duplicate merchants** from case variation (`Aldi` vs `ALDI`).
2. **"Magnet" merchants** — entries the LLM mis-tagged into a famous brand (e.g. random POS payments labelled `Apple`, `Apple PAY`, `Siemens`, `Landesbank Hessen-Thüringen Girozentrale`).
3. **Mounting pending transfers** that were never confirmed.

Plus the standard pipeline health checks (Sidekiq, bank-refresh metric, sure-monmon errors, alerts).

## Scope

- Touches `office` namespace pods: `sure-pg`, `sure-redis`, `sure-web`, `sure-worker`.
- Bank-refresh metric on the Mac Mini at `http://192.168.30.111:9100/metrics`.
- Local `~/.sure/sure-monmon.log` on the Mac Mini for valuation errors.

Run from `/Users/mu/code/cberg-home-nextgen` so `mise exec -- kubectl ...` picks up the right binary.

## Queries

### A. Duplicate merchant pairs

```sql
SELECT lower(trim(name)) AS norm, COUNT(*),
       string_agg(DISTINCT name, ' | ' ORDER BY name) AS variants
FROM merchants
GROUP BY 1
HAVING COUNT(*) > 1
ORDER BY 2 DESC;
```

Healthy: 0 rows. Each non-empty row is a merge candidate.

### B. "Magnet" merchants (entry-name diversity)

```sql
WITH me AS (
  SELECT m.id AS mid, m.name AS merchant,
         lower(split_part(trim(e.name), ' ', 1)) AS tok
  FROM transactions t
  JOIN entries e ON e.entryable_id=t.id AND e.entryable_type='Transaction'
  JOIN merchants m ON m.id=t.merchant_id
  JOIN accounts a ON a.id=e.account_id
  WHERE a.status='active'
)
SELECT merchant, COUNT(*) AS tx, COUNT(DISTINCT tok) AS distinct_tokens,
       (array_agg(DISTINCT tok))[1:6] AS sample_tokens
FROM me GROUP BY merchant
HAVING COUNT(*) >= 5 AND COUNT(DISTINCT tok) > 3
ORDER BY COUNT(DISTINCT tok) DESC;
```

Flagged rows are **candidates** — not all are garbage buckets. Triage rules:

- **Legitimate high-diversity** (skip): merchant with mostly numeric / store-id tokens (McDonald's, KFC), or tokens that all contain the brand name (`tesla`, `tesla-de`, `tesla_de`, `amazon`, `amzn`, `pay.amazon.com`), or location-prefixed payment-processor patterns (`lieferando.de`, `lieferando.de/oosterdoksstraat`).
- **Probable garbage bucket** (cleanup needed): tokens are unrelated supermarkets, restaurants, personal first names, or `paypal` (which is the Naspa-side mirror of PayPal-account transactions and should not be a merchant). Examples seen: `Apple`, `Apple PAY`, `Siemens`, `Landesbank Hessen-Thüringen Girozentrale`, `Tiermobilit`, `Ubiquiti`.

### C. Suspect category catch-alls

```sql
SELECT c.name AS category, COUNT(*) AS tx,
       COUNT(DISTINCT t.merchant_id) AS distinct_merchants,
       COUNT(DISTINCT lower(split_part(trim(e.name),' ',1))) AS distinct_first_tokens
FROM transactions t
JOIN entries e ON e.entryable_id=t.id AND e.entryable_type='Transaction'
JOIN accounts a ON a.id=e.account_id
JOIN categories c ON c.id=t.category_id
WHERE a.status='active'
GROUP BY c.name
ORDER BY distinct_first_tokens DESC LIMIT 10;
```

Inspect the top 3. Food & Drink and Shopping naturally have high diversity. Healthcare or Income with high diversity is unusual.

### D. Pending transfers

```sql
SELECT status, COUNT(*), MAX(created_at)::date AS newest FROM transfers GROUP BY status;
```

Healthy: zero `pending`. If > 0, run the auto-confirm `UPDATE transfers SET status='confirmed', updated_at=NOW() WHERE status='pending';` after user approval.

### E. Pipeline health

```bash
# Sidekiq
for k in retry dead schedule; do printf "%-10s " "$k"; mise exec -- kubectl -n office exec deploy/sure-redis -- redis-cli ZCARD "$k"; done
mise exec -- kubectl -n office exec deploy/sure-redis -- redis-cli LLEN queue:medium_priority
mise exec -- kubectl -n office exec deploy/sure-redis -- redis-cli MGET stat:processed stat:failed

# Bank-refresh
curl -s --max-time 5 http://192.168.30.111:9100/metrics | grep -E '^bank_refresh_(state|last_success_)'

# Recent sure-monmon errors
grep '^\[2026-MM-DD' ~/.sure/sure-monmon.log | wc -l   # adjust date prefix to "since last audit"

# Firing alerts
mise exec -- kubectl -n monitoring port-forward svc/kube-prometheus-stack-prometheus 9091:9090 >/dev/null 2>&1 &
PF=$!; sleep 4
curl -s http://localhost:9091/api/v1/alerts | python3 -c "import sys,json;d=json.load(sys.stdin);a=[x for x in d['data']['alerts'] if x['state']=='firing' and x['labels'].get('alertname') not in ('Watchdog','InfoInhibitor')];print(len(a)); [print(' ',x['labels']['alertname']) for x in a]"
kill $PF
```

### F. Coverage by bucket (drift detection)

```sql
WITH transferred AS (
  SELECT inflow_transaction_id AS tx_id FROM transfers WHERE status='confirmed'
  UNION ALL SELECT outflow_transaction_id FROM transfers WHERE status='confirmed'
), buckets AS (
  SELECT CASE
    WHEN e.date >= CURRENT_DATE - INTERVAL '7 days' THEN '0–7d'
    WHEN e.date >= CURRENT_DATE - INTERVAL '30 days' THEN '8–30d'
    WHEN e.date >= CURRENT_DATE - INTERVAL '90 days' THEN '31–90d'
    WHEN e.date >= CURRENT_DATE - INTERVAL '365 days' THEN '90–365d'
    ELSE '>365d' END AS bucket, t.category_id, t.merchant_id
  FROM transactions t
  JOIN entries e ON e.entryable_id=t.id AND e.entryable_type='Transaction'
  JOIN accounts a ON a.id=e.account_id
  WHERE a.status='active' AND t.id NOT IN (SELECT tx_id FROM transferred)
)
SELECT bucket, COUNT(*),
       ROUND(100.0*COUNT(*) FILTER (WHERE category_id IS NOT NULL)/COUNT(*),1) AS cat,
       ROUND(100.0*COUNT(*) FILTER (WHERE merchant_id IS NOT NULL)/COUNT(*),1) AS merch
FROM buckets GROUP BY bucket
ORDER BY CASE bucket WHEN '0–7d' THEN 1 WHEN '8–30d' THEN 2 WHEN '31–90d' THEN 3 WHEN '90–365d' THEN 4 ELSE 5 END;
```

Target shape (as of 2026-05-28): cat % flat at ~80, merch % flat at ~60. New-arrival lag on 0–7d is expected.

## Cleanup actions (only after user approves)

### Merge duplicate merchants

```sql
-- Example pattern: keep the better-cased name as canonical
WITH losers AS (SELECT id FROM merchants WHERE type='ProviderMerchant' AND name IN (...losers...))
UPDATE transactions t SET merchant_id=(SELECT id FROM merchants WHERE name='<KEEPER>' AND type='ProviderMerchant'),
       updated_at=NOW()
WHERE t.merchant_id IN (SELECT id FROM losers);
DELETE FROM merchants WHERE id IN (SELECT id FROM losers);
```

### Clean a "magnet" merchant

```sql
-- Strip wrong assignments, keep the entries that legitimately match
WITH magnet AS (SELECT id FROM merchants WHERE name='<MAGNET_NAME>')
UPDATE transactions t SET merchant_id=NULL, updated_at=NOW()
FROM entries e
WHERE e.entryable_id=t.id AND e.entryable_type='Transaction'
  AND t.merchant_id=(SELECT id FROM magnet)
  AND e.name NOT ILIKE '<LEGIT_PATTERN>%';
```

Then re-run the pattern-backfill (see `2026-05-09` working notes — list of `pattern → merchant_name` mappings) and enqueue `AutoDetectMerchantsJob` for whatever stays NULL via:

```bash
mise exec -- kubectl -n office exec -i deploy/sure-web -- bundle exec rails runner - <<'RUBY'
family = Family.first
scope = family.transactions
              .joins(entry: :account)
              .where(accounts: { status: "active" })
              .where(merchant_id: nil)
              .where("transactions.updated_at > ?", 30.minutes.ago)
family.auto_detect_transaction_merchants_later(scope)
RUBY
```

Note: run `rails runner` on `sure-web` (1.5 GiB limit), not `sure-worker` (1 GiB — OOMs during boot).

### Auto-confirm pending transfers

```sql
UPDATE transfers SET status='confirmed', updated_at=NOW() WHERE status='pending';
```

## Output format

A single Markdown report with these sections:

1. **Health** — single-line OK/⚠️ per check (A, D, E.Sidekiq, E.bank-refresh, E.alerts, E.sure-monmon).
2. **Coverage** — bucket table.
3. **Merchant magnets** — only the ones the agent classifies as probable garbage buckets, with sample tokens and suggested verdict.
4. **Recommendations** — concrete SQL snippets if cleanup is warranted, with row-count estimates.

Cap report at ~300 words. Never auto-apply cleanups; always ask user.

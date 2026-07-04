# Sure loan accounts & self-amortization

How the manually-tracked loan liabilities in Sure (three Raiffeisenbank Schaafheim
mortgages + one CreditPlus auto loan) are modeled so their balances decline
correctly on their own, without manual monthly updates.

> Privacy: this repo is public. Concrete figures (balances, IBANs, contract
> numbers, exact payments) intentionally live **only** in the Sure DB (account
> notes) and in the Mac-local script `~/.sure/mortgage-amortize.rb` — never here.

## Why

The loans are real debts paid by monthly SEPA direct debit from Naspa, but the
lenders are not synced accounts. Sure does **not** auto-amortize — a loan balance
only moves via anchors (valuations) or transactions in that account. So to get a
self-declining balance we materialize the deterministic fixed-rate amortization
ourselves.

## Model (per loan)

- **Accountable**: `Loan` (subtype `mortgage` / `auto`), classification liability.
- **Opening anchor**: a `Valuation` (kind `opening_anchor`) at the history-start
  date with the balance for that date.
- **Monthly paydown**: one `Transaction` entry per month named
  `Tilgung (principal)` with `amount = -(principal portion)`, where
  `interest = running_balance * rate/12` and `principal = payment - interest`.
  A negative-amount transaction in a Loan account reduces the owed principal
  (Sure treats it as a non-cash inflow — see `balance/base_calculator.rb`).
- **term_months / interest_rate / initial_balance** are set on the `loans` row so
  the loan card shows Term + a derived Monthly Payment. The derived payment is
  rounded to whole months, so it can read ~€1–3 below the real payment; the
  actual amortization uses the exact payment.

### Critical: keep transactions bounded to "today"

Sure materializes a daily balance row for every day from the first entry to the
**last** entry. Do **not** create future-dated paydown transactions — that
materializes thousands of future daily rows and caches the current balance as the
far-future €0 payoff. Only post months that are already due (`date <= today`);
the future is filled in month-by-month by the appender below.

### Payment → loan mapping (how it was derived)

The three mortgage payments were matched to the three loans using the monthly
`SOLLZINS` (interest) figures in the annual *Darlehensabrechnung* (Paperless doc
"Raiffeisenbank Schaafheim – Konto- und Darlehensabrechnung"): interest =
balance × rate/12, and the month-over-month interest decline gives the principal
portion, hence the payment. This corrected an initial size-ordered guess that had
two payments swapped. The authoritative mapping now lives in
`~/.sure/mortgage-amortize.rb`.

## Self-advance — monthly appender (launchd)

`~/.sure/mortgage-amortize.rb` posts each newly-due month's principal transaction
(computed from the running balance) for every mortgage. Idempotent + catch-up:
it only adds months that are due and not already posted, tracking a local running
balance so multiple missed months compute correctly. Runs via launchd
`com.mathiasuhl.sure.mortgage` on the **3rd of each month, 08:20**.

- Wrapper: `~/.sure/mortgage-amortize.sh` (runs the ruby in the sure-web pod via
  `mise exec -- kubectl -n office exec -i deploy/sure-web -- bundle exec rails runner -`).
- Plist: `~/Library/LaunchAgents/com.mathiasuhl.sure.mortgage.plist`.
- Logs: `~/.sure/mortgage-amortize.log` (+ `.out.log` / `.err.log`).
- Force a run: `launchctl kickstart -k gui/$(id -u)/com.mathiasuhl.sure.mortgage`.

The CreditPlus auto loan self-advances differently — via a Sure **rule**
("Creditplus payment → CreditPlus loan (paydown transfer)", `set_as_transfer_or_payment`)
that turns each real Creditplus SEPA debit into a transfer into the loan. That
works there because the loan is small and near payoff; for the long low-rate
mortgages the interest split matters, so they use the amortizer instead.

## Re-anchor when a new statement arrives (or rate resets)

The mortgages are fixed-rate for their full term, so the schedule is deterministic.
Re-anchor only if the real balance drifts from a new Saldenmitteilung/Darlehens-
abrechnung, or at a rate reset:

1. Read the new documented balance + date (and rate, if changed) from Paperless.
2. In a `rails runner` on `deploy/sure-web`: for the loan, delete existing
   `Tilgung (principal)` transactions and `Valuation` entries, set an
   `opening_anchor` valuation at the documented date/balance, then forward-amortize
   monthly to today (interest = bal×rate/12, principal = payment − interest),
   creating `-principal` transactions. `acct.sync_later`, verify current balance
   and that the documented checkpoint reconciles.
3. Update payment/rate in `~/.sure/mortgage-amortize.rb` if they changed.

## Verification

```sh
# current balances + bounded history + schedule length
mise exec -- kubectl -n office exec deploy/sure-pg -- psql -U sure -d sure -c "
  SELECT a.name, a.balance,
    (SELECT MIN(date) FROM balances b WHERE b.account_id=a.id) AS hist_from,
    (SELECT COUNT(*) FROM entries e WHERE e.account_id=a.id AND e.name='Tilgung (principal)') AS txns
  FROM accounts a JOIN loans l ON l.id=a.accountable_id AND a.accountable_type='Loan'
  WHERE l.subtype='mortgage';"
launchctl list | grep mortgage        # agent registered, 2nd column = last exit (0 ok)
tail ~/.sure/mortgage-amortize.log
```

## Accepted caveats

1. **Hardcoded paths** in the script (`REPO`, `MISE`) — update if the repo or
   mise binary moves.
2. **"Original Principal"** shows the reconstruction start point, not the true
   origination amount — Paperless has only the annual statements, not the original
   Darlehensverträge. History is documented from the reconstruction start; provide
   the origination contracts to extend it to the true start.
3. **Derived Monthly Payment** on the loan card is whole-month-rounded (~€1–3 off);
   the actual amortization uses the exact payment from the script.
4. **Mac-dependent**: if the Mac is off on the 3rd, the appender catches up on its
   next run (idempotent), so at most the headline lags a few days.
5. **Plaintext**: loan parameters (balances/payments) live in the Mac script and
   Sure DB, deliberately not committed to this public repo.

## Related

- `runbooks/sure-key-sync.md` — the Sure API key auto-sync (same launchd pattern).
- `runbooks/sure-data-audit.md` — weekly data-quality audit.

#!/usr/bin/env python3
"""Regression: an AUTH miss must not be reported as a FAILED backup.

backup-restore-proof.py hardcoded `psql -U postgres` in its smoke step. A
postgres cluster initdb'd under a different superuser has no `postgres` role, so
on 2026-09-11 — mid-execution of the superset-pg decommission, with the soak gate
overridden and those backups therefore the ONLY rollback — the probe printed
`RESTORE PROOF FAILED: role "postgres" does not exist` for a restore that had
actually SUCCEEDED.

That is the worst failure mode a backup verifier can have. It does not merely
cry wolf: it asserts the backup is bad when the backup is fine, which either
aborts a valid gate or teaches the reader to ignore the one tool they will reach
for in a disaster. The operator caught it only because the error mentioned a
role rather than the data.

Two fixes, both guarded here:
  * the superuser role is DISCOVERED (--superuser, then `postgres`, then tokens
    from the volume name) instead of assumed; and
  * the outcome is THREE-valued — ready+authenticated is PROVEN (0), never-ready
    is FAILED (1), and ready-but-no-role-answers is INCONCLUSIVE (2), because
    postgres starting on the restored volume is the substantive proof and an
    auth miss says nothing about the data.

Source-level + logic guards: the script needs a live cluster to execute, so the
invariants are asserted against its source and its candidate-derivation rule.

Run: python3 runbooks/tests/test-backup-proof-superuser.py
"""
import pathlib
import re
import sys

SRC = pathlib.Path(__file__).resolve().parents[2] / "runbooks" / "backup-restore-proof.py"
src = SRC.read_text()

fails = []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}: {name}" + (f" — {detail}" if detail and not ok else ""))
    if not ok:
        fails.append(name)


# ── 1. the role is no longer assumed ────────────────────────────────────────
check("a --superuser flag exists", '"--superuser"' in src)
check("the smoke step no longer hardcodes `-U postgres`",
      '"psql", "-U", "postgres"' not in src,
      "a hardcoded superuser reintroduces the false FAILED")
check("readiness probe does not pin a role",
      '"pg_isready", "-U", "postgres"' not in src,
      "pinning a role in pg_isready conflates 'server down' with 'role absent'")

# ── 2. THE SEMANTIC GUARD: auth miss != bad backup ──────────────────────────
check("an INCONCLUSIVE outcome exists", "INCONCLUSIVE" in src)
check("INCONCLUSIVE returns a distinct exit code 2",
      re.search(r"INCONCLUSIVE.*?return 2", src, re.S) is not None,
      "it must not share exit 1 with a real failure")
check("INCONCLUSIVE says explicitly not to read it as a failed backup",
      "Do NOT read this as a failed backup" in src)
check("a never-ready server is STILL a hard failure",
      "postgres never became ready" in src,
      "the genuine bad-backup signal must survive this change")

# ── 3. candidate derivation — reimplemented from the script's own rule ──────
def candidates(volume, superuser=None):
    c = []
    if superuser:
        c.append(superuser)
    c.append("postgres")
    for tok in re.split(r"[^a-z0-9]+", volume.lower()):
        if tok and tok not in c and not tok.isdigit():
            c.append(tok)
    return c


c = candidates("superset-pg-data")
check("default tries `postgres` FIRST", c[0] == "postgres", f"got {c}")
check("the real-world miss is covered: `superset` is a candidate",
      "superset" in c, f"got {c}")
check("an explicit --superuser takes precedence",
      candidates("superset-pg-data", "superset")[0] == "superset")
check("numeric-only tokens are not tried as roles",
      all(not t.isdigit() for t in candidates("postgresql-data-5g")),
      f"got {candidates('postgresql-data-5g')}")
check("no duplicate candidates", len(c) == len(set(c)), f"got {c}")
check("the house naming convention is exploited (leading token = app)",
      candidates("paperclip-pg18-data")[1] == "paperclip")

# ── 4. ADVERSARIAL: the fix must not weaken the real smoke assertion ────────
check("the database-count floor is still enforced",
      re.search(r"ndb\s*<\s*3", src) is not None,
      "dropping the >=3 floor would let an empty cluster pass as PROVEN")
check("the optional table smoke still uses the discovered role, not a literal",
      '"psql", "-U", role, "-d", db' in src,
      "a second hardcoded role would resurrect the bug in the table check")

if fails:
    print(f"\n{len(fails)} FAILURE(S): {fails}")
    sys.exit(1)
print("\nall backup-proof superuser guards pass")

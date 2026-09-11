#!/usr/bin/env python3
"""Regression: s3_git_history NAME-only matches are hygiene; VALUE matches are not.

Board pollution this fixes (cycle 0e37c7d3, 2026-09-11): six s3_git_history rows
occupied action-list slots 1-5 and 10, above every piece of real work, because
NATURE_BY_SECTION maps the whole section to VULN and _PUBLIC_REPO_SECTIONS makes
its exposure external — so every row lands on HIGH permanently, and git history
cannot be un-committed without a rewrite.

Five were credential-like VALUES, all verified inert and retired via AR-119..123
after per-string verification. The sixth was a NAME-only match on
`.githooks/lib/password-guard.awk` — the awk source of the Layer-3 password
guard itself. A file NAME is not evidence that secret MATERIAL is present, so
that one is reclassified POLICY (-> LOW).

THE GUARD THAT MATTERS IS THE SECOND HALF. On 2026-09-08 a real Superset admin
password survived 4.7 months and 28 commits because placeholder suppression was
satisfied by the credential's OWN VALUE. That failure is anti-correlated with
risk: weak, guessable passwords are the ones spelled `changeme` / `placeholder`
/ `test`. So these tests assert not only that the name-only row is demoted, but
that VALUE matches are STILL VULN -- including values that spell out placeholder
vocabulary. If someone ever "simplifies" the marker into a general prose match,
the second block fails.

Run: python3 runbooks/tests/test-risk-model-git-history-nature.py
"""
import importlib.util
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("risk_model", ROOT / "runbooks" / "lib" / "risk_model.py")
rm = importlib.util.module_from_spec(spec)
# Register BEFORE exec: @dataclass resolves its own module out of sys.modules,
# and a module loaded by path alone is absent from it (AttributeError on None).
sys.modules["risk_model"] = rm
spec.loader.exec_module(rm)

fails = []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}: {name}" + (f" — {detail}" if detail and not ok else ""))
    if not ok:
        fails.append(name)


def nature_of(title):
    f = rm.Finding.from_db_row(
        {"title": title, "severity": "warning", "finding_id": "F-test",
         "metadata": {"subsection": "s3_git_history"}})
    return rm.compute_nature(f)[0]


def tier_of(title):
    f = rm.Finding.from_db_row(
        {"title": title, "severity": "warning", "finding_id": "F-test",
         "metadata": {"subsection": "s3_git_history"}})
    nature, _ = rm.compute_nature(f)
    exposure, _ = rm.compute_exposure(f, None)
    return rm.tier_for(exposure, None, nature)


# ── 1. the NAME-only row is hygiene, not a confirmed exposure ────────────────
NAME_ONLY = "Secret-named file committed outside sops: `.githooks/lib/password-guard.awk`"
check("name-only match is POLICY", nature_of(NAME_ONLY) == rm.POLICY,
      f"got {nature_of(NAME_ONLY)!r}")
check("name-only match tiers LOW", tier_of(NAME_ONLY) == "low",
      f"got {tier_of(NAME_ONLY)!r}")
check("marker is matched case-insensitively",
      nature_of("SECRET-NAMED FILE COMMITTED OUTSIDE SOPS: `x/password.txt`") == rm.POLICY)

# ── 2. ANTI-BLINDNESS: value matches stay VULN even when the value itself
#       spells placeholder vocabulary. This is the 2026-09-08 lesson, encoded.
#       Synthetic values only — this repo is public.
VALUE_ROWS = [
    "Credential-like pattern in history: `-  DB_PASSWORD: changeme`",
    "Credential-like pattern in history: `-  DB_PASSWORD: placeholder`",
    "Credential-like pattern in history: `-  password: \"REPLACE_WITH_SOMETHING\"`",
    "Credential-like pattern in history: `-  token: your_actual_token_here`",
    "Credential-like pattern in history: `-  api_key: example-not-real`",
    # the shape of the 2026-09-08 miss: a REAL credential that merely reads
    # like scaffolding. It must never be demoted.
    "Credential-like pattern in history: `-  ADMIN_PASSWORD: placeholder-Xk92mQ`",
]
for row in VALUE_ROWS:
    val = row.split(":", 2)[-1].strip()
    check(f"VALUE match stays VULN despite {val[:34]!r}",
          nature_of(row) == rm.VULN, f"got {nature_of(row)!r} — DETECTOR BLINDED")

# ── 3. the demotion must key on the section's verbatim prefix, not on prose.
#       A value row that merely CONTAINS the words must not be demoted.
SNEAKY = ("Credential-like pattern in history: "
          "`-  note: secret-named file committed outside sops was the old wording`")
check("value row merely quoting the marker text is NOT demoted",
      nature_of(SNEAKY) == rm.VULN,
      "a value row containing the marker phrase was demoted — the marker is "
      "being matched too loosely")

# ── 4. no value-based placeholder vocabulary may exist in this module for s3.
src = (ROOT / "runbooks" / "lib" / "risk_model.py").read_text()
marker_block = src[src.find("S3_NAME_ONLY_MARKER"):]
check("no S3 placeholder-word list was introduced",
      "S3_PLACEHOLDER" not in src,
      "a value-based placeholder list reintroduces the 2026-09-08 failure mode")

# ── 5. the rest of the section is unchanged: s3 is still VULN by default.
check("s3_git_history is still VULN in the section table",
      rm.NATURE_BY_SECTION["s3_git_history"] == rm.VULN)
check("s3 is still treated as public-repo exposure",
      "s3_git_history" in rm._PUBLIC_REPO_SECTIONS)

if fails:
    print(f"\n{len(fails)} FAILURE(S): {fails}")
    sys.exit(1)
print("\nall s3 git-history nature guards pass")

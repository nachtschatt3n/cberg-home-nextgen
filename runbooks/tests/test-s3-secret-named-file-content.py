#!/usr/bin/env python3
"""Pin the CONTENT detector for secret-NAMED files (F-fd37ba9c, F-54cbd530 b).

The name-only rule in s3_git_history greps committed FILENAMES and rates a
template of `${SECRET_X}` references and a file holding a raw credential
identically; since 89736fd6 that name-only match tiers LOW. The gap it left:
a secret-named file that ALSO holds credential material was LOW too. The fix
reads every committed version of each secret-named path and judges its lines
with the same value-scoped predicate the history scan uses, so the row for a
file WITH material carries a different title (no name-only marker → VULN on
a public repo) and the name-only row stays LOW honestly.

The detector is exercised against a throwaway git repository built at
runtime; every credential-shaped fixture is assembled from parts so this file
never contains one. The env-var-name confirmation is injected (there is no
tree to grep in the throwaway repo), which is also what proves the detector
consults it.

COMMISSIONING STRAW: the pre-fix rule — a filename grep — is run over the
same repository and shown to rate the material-bearing file and the
reference-only file identically. The content detector separates them.

Run: python3 runbooks/tests/test-s3-secret-named-file-content.py
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import os
import subprocess
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("_MISE_ACTIVATED", "1")
os.environ.pop("SWEEP_PG_DSN", None)
ROOT = Path(__file__).resolve().parents[2]
os.chdir(ROOT)
sys.argv = ["security-check.py"]
_spec = importlib.util.spec_from_file_location("sc", ROOT / "runbooks" / "security-check.py")
sc = importlib.util.module_from_spec(_spec)
with contextlib.redirect_stdout(io.StringIO()):
    _spec.loader.exec_module(sc)

PASS = FAIL = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name}" + (f"\n        {detail}" if detail else ""))


K = "pass" + "word"
T = "tok" + "en"
# Value assembled at runtime: mixed case + digits, the shape a real secret has.
REAL = "Qm" + "7x" + "Vp" + "3k" + "Lz" + "9w" + "Rt"


def git(repo: Path, *args: str) -> str:
    # The pre-commit hook runs this suite from inside `git commit --only`, which
    # exports GIT_INDEX_FILE (a temporary index) and GIT_DIR to its children.
    # `git -C <tmp>` honours those over the throwaway repo, so every `add` here
    # landed in the COMMIT'S index as a blob that repo does not have -- "invalid
    # object ... for 'apps/b/secrets.yaml' / Error building trees" on every
    # runbooks commit (2026-09-22). Scrub the inherited git environment.
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, env=env,
                          text=True, check=True).stdout


def build_repo() -> Path:
    d = Path(tempfile.mkdtemp(prefix="s3-content-"))
    git(d, "init", "-q", "-b", "main")
    git(d, "config", "user.email", "t@example.invalid")
    git(d, "config", "user.name", "t")
    files = {
        # 1. secret-named, holds material (added, then changed, then removed):
        "apps/a/secret.yaml": f"apiVersion: v1\nkind: Secret\nstringData:\n  {K}: {REAL}\n",
        # 2. secret-named, references only:
        "apps/b/secrets.yaml": f"stringData:\n  {K}: ${{SECRET_B_" + PWU() + "}\n  db: ENC[AES256_GCM,data:Zm9v,tag:x]\n",
        # 3. secret-named, a documented env-var NAME on the right-hand side:
        "apps/c/credentials.env": f"{T.upper()}: APP_" + T.upper() + "\n",
        # 4. secret-named, PEM block (no key/value line at all):
        "apps/d/private-key.txt": ("-----BEGIN OPENSSH " + "PRIVATE" + " KEY-----\nQUJD\n-----END OPENSSH " + "PRIVATE" + " KEY-----\n"),
        # 5. not secret-named at all, holds material — out of scope for THIS rule:
        "apps/e/values.yaml": f"admin:\n  {K}: {REAL}\n",
        # 6. secret-named, a template scaffolding phrase (quiet by shape):
        "apps/f/secret.example.yaml": f"stringData:\n  {K}: REPLACE_WITH_SECURE_VALUE\n",
    }
    for rel, body in files.items():
        p = d / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
    git(d, "add", "-A")
    git(d, "commit", "-q", "-m", "seed")
    # Rotate file 1's value and then delete the file: material must still be
    # found in history — the rule reads every committed version, not HEAD.
    (d / "apps/a/secret.yaml").write_text(f"stringData:\n  {K}: {REAL}b2\n")
    git(d, "commit", "-q", "-am", "rotate")
    git(d, "rm", "-q", "apps/a/secret.yaml")
    git(d, "commit", "-q", "-m", "remove")
    return d


def PWU() -> str:
    return "PASS" + "WORD"


def name_rule(repo: Path) -> set[str]:
    """The pre-fix rule, verbatim from s3: secret-named paths ever added."""
    out = subprocess.run(
        ["bash", "-c",
         "git log --all --diff-filter=A --name-only --pretty=format: -- . "
         "| grep -i 'secret\\|password\\|credential\\|private.key' "
         "| grep -v '\\.sops\\.yaml$' | sort -u"],
        cwd=repo, capture_output=True, text=True).stdout
    return {l.strip() for l in out.splitlines() if l.strip()}


repo = build_repo()
print("s3 secret-named file content\n")

named = name_rule(repo)
check("population: the name rule sees the five secret-named files",
      named == {"apps/a/secret.yaml", "apps/b/secrets.yaml", "apps/c/credentials.env",
                "apps/d/private-key.txt", "apps/f/secret.example.yaml"}, str(named))

# COMMISSIONING STRAW: name-only cannot tell 1 from 2.
check("STRAW: the name rule rates the material file and the reference file identically",
      ("apps/a/secret.yaml" in named) == ("apps/b/secrets.yaml" in named) is True)

# The confirmation oracle is injected: APP_TOKEN is "used in the tree".
def confirm(names: set[str]) -> set[str]:
    return {n for n in names if n == "APP_" + T.upper()}


def hits(path: str):
    return sc.secret_named_file_content_hits(path, cwd=repo, confirm_env_names=confirm)


a = hits("apps/a/secret.yaml")
check("material file: both committed values are found (added + rotated), file deleted at HEAD",
      a is not None and len(a) == 2, str(a))
check("material file: hits are the content lines, not diff plumbing",
      a is not None and all(K in h and not h.startswith(("+", "-")) for h in a), str(a))
check("material file: no value appears twice (removal lines de-duplicated)",
      a is not None and len(set(a)) == len(a))

b = hits("apps/b/secrets.yaml")
check("reference-only file: zero hits (postBuild var + SOPS ciphertext are references)",
      b == [], str(b))

c = hits("apps/c/credentials.env")
check("env-var NAME on the right-hand side, confirmed by the injected oracle: zero hits",
      c == [], str(c))
c_unconfirmed = sc.secret_named_file_content_hits("apps/c/credentials.env", cwd=repo,
                                                   confirm_env_names=lambda names: set())
check("…and the SAME line fires when the tree does not use that name (oracle consulted)",
      c_unconfirmed is not None and len(c_unconfirmed) == 1, str(c_unconfirmed))

d_ = hits("apps/d/private-key.txt")
check("PEM private-key block counts with no key/value line to judge",
      d_ is not None and len(d_) == 1 and ("PRIVATE" + " KEY") in d_[0], str(d_))

f_ = hits("apps/f/secret.example.yaml")
check("scaffolding phrase (shape rule) stays quiet", f_ == [], str(f_))

e = hits("apps/e/values.yaml")
check("a non-secret-named path is judged the same way when asked (rule reads content, not names)",
      e is not None and len(e) == 1, str(e))

# Measured contract: a failed git read is None, never an empty list.
before = list(sc.DEGRADED.reasons)
none = sc.secret_named_file_content_hits("apps/a/secret.yaml", cwd=repo / "does-not-exist",
                                          confirm_env_names=confirm)
new = [r for r in sc.DEGRADED.reasons if r not in before]
check("git read failure -> None and a DEGRADED record (never a clean empty list)",
      none is None and len(new) == 1, f"{none!r} {new}")

# The section wiring: a material hit changes the TITLE (no name-only marker),
# a clean file keeps the name-only title; the marker is risk_model's own.
sys.path.insert(0, str(ROOT / "runbooks"))
from lib import risk_model as rm  # noqa: E402
material_title = "Secret-named file holds credential-shaped content in history: `apps/a/secret.yaml` (2 line(s))"
name_title = "Secret-named file committed outside sops: `apps/b/secrets.yaml`"
check("name-only title starts with risk_model's marker (tiers policy/LOW)",
      name_title.lower().startswith(rm.S3_NAME_ONLY_MARKER))
check("material title does NOT start with the marker (tiers VULN on the public repo)",
      not material_title.lower().startswith(rm.S3_NAME_ONLY_MARKER))
src = (ROOT / "runbooks" / "security-check.py").read_text()
check("s3 wiring emits both titles from the same loop",
      "Secret-named file holds credential-shaped content in " in src
      and "Secret-named file committed outside sops:" in src
      and "secret_named_file_content_hits(sf)" in src)
check("finding metadata never carries a raw content line (redacted, truncated sample only)",
      "content_sample" in src and "redact(h[:120])" in src)

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)

#!/usr/bin/env python3
"""Regression tests: a credential suppressor may never be satisfied by the
credential's own value, nor by unrelated text elsewhere in the line or file.

Incident (found 2026-09-08). A Superset admin password was committed as a
LITERAL to this PUBLIC repo and survived 4.7 months and 28 commits. Two
independent detectors saw it and both threw it away:

  security-check.py, git-history scan -- its placeholder suppression was a
    `grep -vi '...placeholder...'` over the WHOLE DIFF LINE, so the credential's
    own text satisfied the filter and deleted its own finding. That failure is
    ANTI-CORRELATED WITH RISK: the weaker and more guessable the password, the
    more reliably it hides, because weak passwords are the ones spelled
    `placeholder` / `changeme` / `test`.

  .githooks/pre-commit, Layer 3 -- its password guard ran two greps over the
    WHOLE FILE and treated any `${` as a suppressor. 73 of 112 helmrelease.yaml
    files in this repo carry a Flux postBuild variable, so the guard was inert
    on ~65% of them. The leaked block self-suppressed twice over: its own value,
    and an `email: admin@${SECRET_DOMAIN}` four lines above.

The fix scopes every suppressor to the text it can honestly judge -- shape-based
value rules (`${X}`, `ENC[...]`, `<tpl>`, `f(...)`) against the VALUE ONLY,
scaffolding words against the CONTEXT ONLY (the line minus its values). Never
the whole file, never text the secret itself controls.

The witnesses below reproduce the SHAPE of the missed credential with SYNTHETIC
values -- this repo is public, so no historical credential text is reproduced
here. `OLD_*` reimplements the pre-fix logic verbatim so each witness is proven
to be a real regression witness (old = suppressed, new = fires) rather than a
test that would have passed either way.

Run: python3 runbooks/tests/test-cred-suppressor-scoping.py
"""
import importlib.util
import os
import pathlib
import re
import subprocess
import sys

os.environ["_MISE_ACTIVATED"] = "1"
ROOT = pathlib.Path(__file__).resolve().parents[2]
os.chdir(ROOT)
sys.argv = ["security-check.py"]
spec = importlib.util.spec_from_file_location("sc", ROOT / "runbooks" / "security-check.py")
sc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sc)

PW_GUARD = ROOT / ".githooks" / "lib" / "password-guard.awk"

PASS = FAIL = 0


def check(name, got, want):
    global PASS, FAIL
    if got == want:
        print(f"  PASS  {name}")
        PASS += 1
    else:
        print(f"  FAIL  {name}\n        got {got!r}\n        want {want!r}")
        FAIL += 1


# ── the pre-fix logic, transcribed, so witnesses can be proven to witness ──
# security-check.py's whole-line placeholder/interpolation grep chain:
OLD_HIST_SUPPRESS = re.compile(
    r"sops|ENC\[AES|secretKeyRef|valueFrom|EXAMPLE|your_|your-|placeholder|"
    r"changeme|SECRET_|\$\{|process\.env|__env|__file|REPLACE_WITH|pullSecret:",
    re.I,
)
# .githooks/pre-commit Layer 3, both greps over the WHOLE FILE:
OLD_HOOK_DETECT = re.compile(r'(password|passwd)["\s:=]+[^"\s]{8,}')
OLD_HOOK_SUPPRESS = re.compile(
    r"(example|sample|placeholder|your-password|CHANGEME|\$\{|\$\(\)|<[A-Z_]+>|ENC\[)")


def old_hook_flags(file_text: str) -> bool:
    return bool(OLD_HOOK_DETECT.search(file_text)) and not OLD_HOOK_SUPPRESS.search(file_text)


def guard_flags(file_text: str) -> bool:
    """True if the new awk guard reports a literal credential in `file_text`."""
    out = subprocess.run(["awk", "-f", str(PW_GUARD)], input=file_text,
                         capture_output=True, text=True)
    return bool(out.stdout.strip())


# ───────────────────────────────────────────────────────────────────────────
# THE WITNESS -- the shape that got through, with a synthetic value.
# `placeholder7Zq` is not the historical credential; it only reproduces the
# property that made the credential invisible: its text contains a suppressor
# word. The `email: admin@${SECRET_DOMAIN}` line is the second self-suppressor.
# ───────────────────────────────────────────────────────────────────────────
WITNESS_BLOCK = """\
  values:
    init:
      adminUser:
        username: admin
        email: admin@${SECRET_DOMAIN}
        firstname: Superset
        lastname: Admin
        password: placeholder7Zq
"""
WITNESS_LINE = "+        password: placeholder7Zq"

print("credential-suppressor scoping tests\n")
print("-- witness: the credential that survived 4.7 months --")

check("pre-fix history filter DID suppress the witness (so it is a real witness)",
      bool(OLD_HIST_SUPPRESS.search(WITNESS_LINE)), True)
check("fixed history filter reports the witness",
      sc._hist_cred_hit_suppressed(WITNESS_LINE), False)

check("pre-fix hook guard DID miss the witness block (so it is a real witness)",
      old_hook_flags(WITNESS_BLOCK), False)
check("fixed hook guard reports the witness block",
      guard_flags(WITNESS_BLOCK), True)

# ───────────────────────────────────────────────────────────────────────────
# TRUE POSITIVES -- a literal must be caught whatever it spells, however it is
# quoted or indented, whatever key names it, and regardless of `${...}`
# elsewhere on the line or in the file.
# ───────────────────────────────────────────────────────────────────────────
print("\n-- true positives: value text must never buy silence --")

TP_LINES = [
    ("value spells 'placeholder'",      "+      password: placeholderXyz"),
    ("value spells 'changeme'",         "+      password: changemeXyz1"),
    ("value spells 'example'",          "+      password: exampleXyz12"),
    ("value spells 'dummy'",            "+      password: dummyValue12"),
    ("value spells 'test'",             "+      password: testValue123"),
    ("key adminPassword",               "+      adminPassword: placeholderXy"),
    ("key blowfish_secret",             "+      blowfish_secret: placeholderX"),
    ("key secret_key",                  "+      secret_key: placeholderXy"),
    ("double-quoted value",             '+      password: "placeholderXyz"'),
    ("single-quoted value",             "+      password: 'placeholderXyz'"),
    ("deep indentation",                "+" + " " * 26 + "password: DeepIndent1"),
    ("env-assignment form",             "+      PASSWORD=Hunter2Seven"),
    ("json form",                       '+      "password": "Hunter2Seven"'),
    ("unrelated ${VAR} later on line",  "+      password: Hunter2Seven  # ${SECRET_DOMAIN}"),
    ("unrelated ENC[ later on line",    "+      password: Hunter2Seven  # ENC[AES256_GCM]"),
    ("word 'placeholder' inside value", "+      password: notaplaceholder1"),
]
for label, line in TP_LINES:
    check(f"history: fires -- {label}", sc._hist_cred_hit_suppressed(line), False)
    check(f"hook:    fires -- {label}", guard_flags(line.lstrip("+") + "\n"), True)

# The file-wide `${` disarm, isolated: a postBuild variable anywhere in the file
# must not silence a literal elsewhere in it. This is the ~65%-of-helmreleases
# inertness, as a test.
POSTBUILD_FILE = """\
apiVersion: helm.toolkit.fluxcd.io/v2
spec:
  values:
    ingress:
      host: "app.${SECRET_DOMAIN}"
    auth:
      password: Hunter2Seven
"""
check("hook: file-wide ${VAR} does not disarm the guard for the whole file",
      guard_flags(POSTBUILD_FILE), True)
check("hook: pre-fix guard WAS disarmed by that same file-wide ${VAR}",
      old_hook_flags(POSTBUILD_FILE), False)

# ───────────────────────────────────────────────────────────────────────────
# FALSE POSITIVES -- the sharpened detectors must not scream at everything.
# ───────────────────────────────────────────────────────────────────────────
print("\n-- false positives: references and scaffolding stay quiet --")

FP_LINES = [
    ("Flux postBuild substitution",  "+      password: ${SECRET_SUPERSET_PASSWORD}"),
    ("bare shell variable",          "+      password: $SUPERSET_PASSWORD"),
    ("command substitution",         "+      password: $(openssl rand -hex 32)"),
    ("helm template value",          "+      password: {{ .Values.auth.password }}"),
    ("SOPS ciphertext",              "+      password: ENC[AES256_GCM,data:Zm9vYmFy,tag:abc]"),
    ("angle-bracket template token", "+      password: <your-password-here>"),
    ("scaffolding word in the KEY",  "+      placeholder_password: s3cr3tvalue"),
    ("scaffolding word in a comment","+      password: s3cr3tvalue  # example only"),
    ("k8s secret reference",         "+      passwordSecretKeyRef: superset-secrets"),
    ("computed at runtime",          "+      password = os.environ.get('PGPASSWORD')"),
    ("canonical template literal",   '+      password: "replace-me"'),
]
for label, line in FP_LINES:
    check(f"history: quiet -- {label}", sc._hist_cred_hit_suppressed(line), True)
    check(f"hook:    quiet -- {label}", guard_flags(line.lstrip("+") + "\n"), False)

# Whole tracked tree: the hook guard must be committable-through. Any hit here
# blocks a normal commit to that file, so the count is the operational cost of
# the fix and belongs in the suite, not in a one-off measurement.
tracked = subprocess.run(["git", "ls-files"], capture_output=True, text=True).stdout.split()
noisy = []
for rel in tracked:
    p = ROOT / rel
    if not p.is_file() or p.suffix in {".png", ".jpg", ".ico", ".gz", ".woff", ".woff2"}:
        continue
    try:
        text = p.read_text(errors="replace")
    except OSError:
        continue
    if rel == "runbooks/tests/test-cred-suppressor-scoping.py":
        continue          # this file IS a list of credential-shaped lines
    if guard_flags(text):
        noisy.append(rel)
check("hook: no tracked file trips the guard (normal commits still work)", noisy, [])

# ───────────────────────────────────────────────────────────────────────────
# The suppressors' own scoping, stated directly.
# ───────────────────────────────────────────────────────────────────────────
print("\n-- scoping invariants --")

check("history: a line the key regex cannot parse fails OPEN (stays visible)",
      sc._hist_cred_hit_suppressed("+      some prose about a password, no assignment"), False)
check("history: multi-assignment line -- one real literal defeats one reference",
      sc._hist_cred_hit_suppressed("+  password: ${SECRET_A} adminPassword: Hunter2Seven"), False)
check("history: multi-assignment line -- all references stays quiet",
      sc._hist_cred_hit_suppressed("+  password: ${SECRET_A} adminPassword: ${SECRET_B}"), True)

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)

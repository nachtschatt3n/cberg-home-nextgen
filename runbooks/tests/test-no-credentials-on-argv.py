#!/usr/bin/env python3
"""Regression: no runbook script puts a credential on a process argv.

F-4e822c2f: security-check.py ran `kubectl exec ... -- curl -u elastic:<pw>`,
so the Elasticsearch superuser password sat in `ps` -- on the Mac (kubectl's
argv) and inside the ES pod (curl's argv) -- for the whole sweep. health-check.sh,
the retention scripts and a test did the same with `curl -u "elastic:$pw"`.

The house pattern is a curl config on stdin or a /dev/fd path:
    printf 'user = "elastic:%s"\\n' "$pw" | curl -K - ...     (printf: builtin)
    curl -K <(es_curl_auth "$pw") ...
    subprocess.run([... "curl", "-K", "-", ...], input=cfg)

This test scans every executable runbook script (*.sh, *.py, runbooks/lib) for
the argv shapes that leak, and also proves each pattern still FIRES on a known
bad line (a scanner that matches nothing would pass green forever).
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
SELF = pathlib.Path(__file__).resolve()

PATTERNS = {
    # curl -u user:$VAR / --user "user:${VAR}" (shell)
    "curl -u/--user with a variable credential":
        re.compile(r"""(?:^|\s)(?:-u|--user)[ =]?["']?[A-Za-z0-9_.@-]*:\$"""),
    # ["curl", ..., "-u", userpass] / "-u", f"elastic:{pw}" (python argv list)
    "python argv list passing -u/--user":
        re.compile(r"""["'](?:-u|--user)["']\s*,"""),
    # -H "Authorization: Bearer $TOKEN" (shell) on a curl argv
    "Authorization header built from a shell variable":
        re.compile(r"""-H\s*["']Authorization:[^"'\n]*\$"""),
    # python argv list: "-H", f"Authorization: Bearer {tok}"
    "python argv Authorization header from a variable":
        re.compile(r"""["']-H["']\s*,\s*f["']Authorization:[^"']*\{"""),
}

# Each pattern must fire on its known-bad sample (control against a blind scanner).
KNOWN_BAD = {
    "curl -u/--user with a variable credential":
        'curl -k -s -u "elastic:$ES_PASSWORD" https://localhost:9200/',
    "python argv list passing -u/--user":
        '"curl", "-sk", "-u", userpass, "-H", "Content-Type: application/json",',
    "Authorization header built from a shell variable":
        '-H "Authorization: Token ${INFLUX_TOKEN}" \\',
    "python argv Authorization header from a variable":
        '["curl", "-H", f"Authorization: Bearer {tok}", url]',
}
KNOWN_GOOD = [
    'curl -k -s -K <(es_curl_auth "$pw") https://localhost:9200/',
    'auth_cfg | kubectl exec -i -n "$NS" "$POD" -- curl -sk -K - https://x',
    '"curl", "-sk", "-K", "-", f"https://localhost:9200/{index}/_search",',
    "printf 'header = \"Authorization: Bearer %s\"\\n' \"$GH_TOKEN\" | curl -K -",
]

failures = 0


def check(name, ok, detail=""):
    global failures
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f" -- {detail}" if detail and not ok else ""))
    if not ok:
        failures += 1


def is_comment(line: str) -> bool:
    s = line.lstrip()
    return s.startswith("#") or s.startswith("//")


def scan(line: str):
    return [n for n, rx in PATTERNS.items() if rx.search(line)]


# --- controls: the scanner can see ---------------------------------------
for name, bad in KNOWN_BAD.items():
    check(f"control: '{name}' fires on a known-bad line", name in scan(bad))
for good in KNOWN_GOOD:
    check(f"control: clean house pattern not flagged: {good[:60]}", not scan(good),
          f"flagged as {scan(good)}")

# --- the real scan ----------------------------------------------------------
files = sorted(
    p for p in (ROOT / "runbooks").rglob("*")
    if p.is_file() and p.suffix in (".sh", ".py", ".bash")
    and p.resolve() != SELF and "__pycache__" not in p.parts
)
check("scan universe is non-empty (denominator guard)", len(files) > 50,
      f"only {len(files)} files found")

hits = []
for p in files:
    try:
        text = p.read_text(errors="replace")
    except OSError:
        continue
    for i, line in enumerate(text.splitlines(), 1):
        if is_comment(line):
            continue
        for name in scan(line):
            hits.append(f"{p.relative_to(ROOT)}:{i}: [{name}] {line.strip()[:120]}")

check(f"no credential on argv in {len(files)} runbook scripts", not hits,
      "\n        " + "\n        ".join(hits))

print(f"\n  {len(KNOWN_BAD) + len(KNOWN_GOOD) + 2 - failures} passed, {failures} failed")
sys.exit(1 if failures else 0)

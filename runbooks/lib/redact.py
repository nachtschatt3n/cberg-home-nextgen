"""Post-synthesis redaction utility.

Apply to the assembled sweep table (or any string) before emitting to
the parent session, commit message, or PR body. Idempotent — running
`redact(redact(x))` produces the same output as `redact(x)`.

Handles only the structural patterns that are safe to detect by regex:
IPv4 (RFC1918 private ranges only), MAC, email. Domain / user-name /
media-title redaction requires knowing the actual sensitive values and
is left to the source (security-check.py:redact via load_sensitive,
plus the agent's per-row prompt rule in
`.claude/agents/daily-operation.md` §"Privacy / redaction").

Usage:
    from runbooks.lib.redact import redact
    cleaned = redact(text)

Or as a script:
    cat sweep-table.md | python3 -m runbooks.lib.redact > redacted.md
"""

from __future__ import annotations

import re
import sys

_IPV4_PRIVATE = re.compile(
    r"\b("
    r"192\.168\.\d{1,3}\.\d{1,3}"
    r"|10\.\d{1,3}\.\d{1,3}\.\d{1,3}"
    r"|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}"
    r")\b"
)
_MAC = re.compile(r"\b[0-9a-f]{2}(?::[0-9a-f]{2}){5}\b", re.IGNORECASE)
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")

# Order matters: IPs first so they're not partially consumed by other rules.
_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (_IPV4_PRIVATE, "<IP>"),
    (_MAC, "<MAC>"),
    (_EMAIL, "<EMAIL>"),
]


def redact(text: str) -> str:
    """Apply all structural redactions in canonical order."""
    for pattern, placeholder in _PATTERNS:
        text = pattern.sub(placeholder, text)
    return text


def main() -> int:
    sys.stdout.write(redact(sys.stdin.read()))
    return 0


if __name__ == "__main__":
    sys.exit(main())

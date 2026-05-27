"""DB-backed replacement for runbooks/security_check_acceptances.py.

Exposes the same three module-level constants — GIT_HISTORY_CRED_PATTERNS,
GIT_HISTORY_SECRET_FILES, EXTERNAL_INGRESS_ACCEPTED — but populated
lazily from the `security_acceptances` table in sweep_history Postgres.

Read once per process via PEP-562 module `__getattr__`. The first
attribute access fires a single SELECT; subsequent accesses use the
cached value (so `from lib.security_acceptances import X` is cheap).

Source-of-truth path (Plan Phase 1.5):

  SWEEP_PG_DSN set    → `SELECT pattern FROM security_acceptances
                          WHERE category=? AND enabled=true ORDER BY id`
  SWEEP_PG_DSN unset  → legacy fallback: try to import the old
                          runbooks/security_check_acceptances module.
                          That fallback file (and this clause) are
                          deleted in Plan Phase 2.

Loader errors are silenced — the security audit proceeds without
acceptance filtering rather than blocking on a policy-loader fault.
"""
from __future__ import annotations

import os
from typing import Any

_CATEGORY_MAP: dict[str, tuple[str, type]] = {
    "GIT_HISTORY_CRED_PATTERNS":  ("git_history_cred",        list),
    "GIT_HISTORY_SECRET_FILES":   ("git_history_secret_file", set),
    "EXTERNAL_INGRESS_ACCEPTED":  ("external_ingress_accepted", set),
}

_cache: dict[str, Any] = {}


def _load_from_db(category: str) -> list[str]:
    dsn = os.environ.get("SWEEP_PG_DSN")
    if not dsn:
        return []
    try:
        import psycopg
    except ImportError:
        return []
    try:
        with psycopg.connect(dsn) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT pattern FROM security_acceptances "
                "WHERE category = %s AND enabled = true "
                "ORDER BY id",
                (category,),
            )
            return [row[0] for row in cur.fetchall()]
    except Exception:
        return []


def _load_legacy(name: str) -> list[str] | set[str] | None:
    """Phase 1 fallback when DSN is unset and the legacy file still exists."""
    try:
        import importlib
        legacy = importlib.import_module("security_check_acceptances")
    except ImportError:
        return None
    return getattr(legacy, name, None)


def __getattr__(name: str) -> Any:
    if name not in _CATEGORY_MAP:
        raise AttributeError(f"module has no attribute {name!r}")
    if name in _cache:
        return _cache[name]
    category, ctor = _CATEGORY_MAP[name]
    if os.environ.get("SWEEP_PG_DSN"):
        value = ctor(_load_from_db(category))
    else:
        legacy = _load_legacy(name)
        value = legacy if legacy is not None else ctor()
    _cache[name] = value
    return value

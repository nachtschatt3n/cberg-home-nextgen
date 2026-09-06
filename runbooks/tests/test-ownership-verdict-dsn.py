"""Regression test: the ownership verdict must not go red on a plumbing bug.

GROUND TRUTH (F-4b27e81c). `_ownership_verdict()` shells out to
finding-triage.py and reads counts from its JSON. Its docstring claimed the
child "inherits SWEEP_PG_DSN from our env" — true only when the OPERATOR
exported it by hand.

On the normal cron path sweep-run SELF-PROVISIONS the dsn (its own port-forward
plus a decoded secret) and writes it to a per-step `env` dict, never to
os.environ. `_sp.run` was called with no `env=`, so the child inherited a bare
environment, died on KeyError SWEEP_PG_DSN, and returned empty stdout. Missing
counts then hit this function's own fail-safe and forced RED — on every
self-provisioned run, regardless of ownership. Cycle e0bb8d95 (2026-08-28):
standalone triage said CRACK=0, overdue=[], so the correct verdict was yellow.

The fail-safe is CORRECT and must stay. The bug was that it fired on plumbing
rather than on genuine uncertainty, and a permanently-red verdict carries
exactly as little information as a permanently-green one.

Run:  python3 runbooks/tests/test-ownership-verdict-dsn.py
"""

from __future__ import annotations

import importlib.util
import inspect
import os
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("sr", REPO / "runbooks/sweep-run.py")
sr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sr)

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  {detail}"))
    if not ok:
        FAILURES.append(name)


def main() -> int:
    print("ownership verdict DSN propagation:")

    sig = inspect.signature(sr._ownership_verdict)
    check("_ownership_verdict accepts a dsn — it cannot rely on os.environ",
          "dsn" in sig.parameters, str(sig))

    # The call site must actually PASS it. A parameter nobody supplies is the
    # same bug with a nicer signature.
    src = (REPO / "runbooks/sweep-run.py").read_text()
    check("the call site passes the dsn through",
          "_ownership_verdict(warn, dsn)" in src,
          "an unused parameter does not fix the plumbing")

    # BEHAVIOUR: with the parent env deliberately stripped, the child must
    # still receive the dsn. Run it for real against a bogus dsn — triage will
    # fail to connect and the verdict is red either way, so this asserts the
    # env plumbing, not the verdict.
    saved = os.environ.pop("SWEEP_PG_DSN", None)
    try:
        marker = "postgresql://unit-test-marker@127.0.0.1:1/none"
        seen = {}
        real_run = None
        import subprocess
        real_run = subprocess.run

        def spy(cmd, **kw):
            seen["env"] = kw.get("env")
            class R:  # minimal stand-in; empty stdout drives the fail-safe
                stdout = ""
            return R()

        subprocess.run = spy
        try:
            verdict = sr._ownership_verdict(0, marker)
        finally:
            subprocess.run = real_run

        env = seen.get("env")
        check("an env is passed to the child at all (not None)", env is not None)
        check("the child env carries the dsn even though os.environ lacks it",
              bool(env) and env.get("SWEEP_PG_DSN") == marker,
              f"got {None if not env else env.get('SWEEP_PG_DSN')!r}")
        check("the parent environment is NOT mutated as a side effect",
              "SWEEP_PG_DSN" not in os.environ)

        # The fail-safe itself must survive the fix.
        check("empty triage output still forces RED (fail-safe intact)",
              verdict == "red", verdict)
    finally:
        if saved is not None:
            os.environ["SWEEP_PG_DSN"] = saved

    print()
    if FAILURES:
        print(f"FAILED ({len(FAILURES)}): {', '.join(FAILURES)}")
        return 1
    print("all ownership-verdict DSN tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

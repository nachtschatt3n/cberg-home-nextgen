"""Regression test: sweep-pg-dsn.sh's teardown trap must fire at SHELL exit in
both bash and zsh, never at function return (F-fe1795c5, 2026-09-22).

26f318d8 added an EXIT trap inside sweep_pg_dsn_up so a forgotten teardown
could not leak a port-forward. Under zsh an EXIT trap set inside a function
fires when the FUNCTION returns -- documented zsh semantics -- so the helper
printed ready, returned, and ran its own teardown; the caller's first
connection hit a dead port. Two sessions hit it the same night and the record
carried two wrong hypotheses before this was reproduced.

Cluster-free: only the trap installer is exercised, with a stub teardown that
touches a marker file. The invariant, per shell: after the installer returns
the marker must NOT exist; after the shell exits it MUST. The straw restores
the pre-fix inline `trap ... EXIT` inside a function and shows zsh firing it
on return. The subshell guard is asserted in both shells.

Run:  python3 runbooks/tests/test-sweep-pg-dsn-trap-scope.py
"""
from __future__ import annotations
import os, shutil, subprocess, tempfile
from pathlib import Path
_REPO = Path(__file__).resolve().parents[2]
HELPER = _REPO / "runbooks" / "lib" / "sweep-pg-dsn.sh"
FAILURES: list[str] = []
def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  {detail}"))
    if not ok: FAILURES.append(name)

def run(shell: str, script: str) -> subprocess.CompletedProcess:
    return subprocess.run([shell, "-c", script], capture_output=True, text=True, timeout=30)

def scope_case(shell: str, helper: Path, marker: Path) -> tuple[bool, bool, str]:
    """(marker_after_return, marker_after_exit, stderr)"""
    marker.unlink(missing_ok=True)
    after_return = marker.with_suffix(".after_return")
    after_return.unlink(missing_ok=True)
    script = f'''
        source "{helper}"
        sweep_pg_dsn_down() {{ : > "{marker}"; }}
        _sweep_pg_install_traps
        if [ -e "{marker}" ]; then : > "{after_return}"; fi
        exit 0
    '''
    r = run(shell, script)
    return after_return.exists(), marker.exists(), r.stderr

def main() -> int:
    print(__doc__.strip().splitlines()[0]); print()
    shells = [s for s in ("bash", "zsh") if shutil.which(s)]
    check("both shells available on this host", set(shells) == {"bash", "zsh"}, str(shells))
    with tempfile.TemporaryDirectory() as td:
        marker = Path(td) / "torn_down"
        for sh in shells:
            ret, ext, err = scope_case(sh, HELPER, marker)
            check(f"{sh}: teardown did NOT fire when the installer returned", not ret, err[-200:])
            check(f"{sh}: teardown DID fire at shell exit", ext, err[-200:])
        # subshell guard, both shells
        for sh in shells:
            r = run(sh, f'source "{HELPER}"; ( sweep_pg_dsn_up ); echo "rc=$?"')
            check(f"{sh}: sweep_pg_dsn_up refuses to run in a subshell",
                  "must run in the main shell" in r.stderr and "rc=1" in r.stdout, (r.stdout + r.stderr)[-200:])
        # bash chaining: an existing EXIT trap must still run
        r = run("bash", f'''
            source "{HELPER}"
            sweep_pg_dsn_down() {{ echo TEARDOWN; }}
            trap 'echo CALLER_CLEANUP' EXIT
            _sweep_pg_install_traps
            exit 0
        ''')
        check("bash: an existing caller EXIT trap is chained, both run in order",
              r.stdout.strip().splitlines() == ["CALLER_CLEANUP", "TEARDOWN"], r.stdout)
        # zsh chaining: an existing TRAPEXIT must still run
        r = run("zsh", f'''
            source "{HELPER}"
            sweep_pg_dsn_down() {{ echo TEARDOWN; }}
            caller_cleanup() {{ echo CALLER_CLEANUP; }}
            zshexit_functions=(caller_cleanup)
            _sweep_pg_install_traps
            _sweep_pg_install_traps
            echo "hooks=${{#zshexit_functions}}"
            exit 0
        ''')
        check("zsh: an existing zshexit hook is kept, ours appended once (idempotent), both run in order",
              r.stdout.strip().splitlines() == ["hooks=2", "CALLER_CLEANUP", "TEARDOWN"], r.stdout)
        # STRAW: the pre-fix shape -- an inline `trap ... EXIT` inside a function -- fires on return in zsh
        straw = Path(td) / "straw.sh"
        straw.write_text('_sweep_pg_install_traps() { trap sweep_pg_dsn_down EXIT; }\n')
        ret, ext, _ = scope_case("zsh", straw, marker)
        check("commissioning: the PRE-FIX inline trap fires on function return under zsh "
              "(the defect, reproduced)", ret)
        ret, ext, _ = scope_case("bash", straw, marker)
        check("commissioning: ...and does not under bash, which is why the bash-only "
              "verification missed it", not ret and ext)
    # down() must also drop the DSN it exported: a later caller in the same shell
    # (policy-cli dials its own forward only when the variable is absent) would
    # otherwise connect to the dead port. Four finding writes were lost that way
    # on 2026-09-22 (fixed in 5e4dcd39).
    for sh in shells:
        r = run(sh, f'source "{HELPER}"; export SWEEP_PG_DSN=postgresql://x; SWEEP_PG_PF_PID=""; '
                    'sweep_pg_dsn_down; [ -z "${SWEEP_PG_DSN:-}" ] && echo UNSET || echo STILL_SET')
        check(f"{sh}: sweep_pg_dsn_down unsets SWEEP_PG_DSN", "UNSET" in r.stdout,
              r.stdout[-80:] + r.stderr[-120:])

    print(); print("FAILED: " + ", ".join(FAILURES) if FAILURES else "all tests passed"); return 1 if FAILURES else 0
def test_pytest_entry(): assert main() == 0
if __name__ == "__main__": raise SystemExit(main())

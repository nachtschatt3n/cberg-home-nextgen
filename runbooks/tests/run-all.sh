#!/usr/bin/env bash
# Run every audit-tooling regression test.
#
# Each test in this directory pins a correctness fix that was found the hard
# way -- a detector that could not see, a denominator that excluded the thing
# being measured, a zero reported without a control. docs/sops/audit-script-
# correctness.md lists 30+ instances of that class.
#
# Until 2026-08-22 nothing ran these: not CI, not the Taskfile, not pre-commit,
# not the sweep. Fourteen suites guarding hard-won fixes, and a regression in
# any of them would have surfaced only as a wrong answer in a future sweep --
# which is precisely how this class of bug hides.
#
# Usage: bash runbooks/tests/run-all.sh [-q]
set -uo pipefail
cd "$(dirname "$0")/../.."
export _MISE_ACTIVATED=1          # tests import the scripts directly
QUIET="${1:-}"

pass=0; fail=0; failed=()
for t in runbooks/tests/test-*.py runbooks/tests/test-*.sh; do
    [ -e "$t" ] || continue
    case "$t" in
        *.py) out=$(python3 "$t" 2>&1); rc=$? ;;
        *.sh) out=$(bash     "$t" 2>&1); rc=$? ;;
    esac
    if [ $rc -eq 0 ]; then
        pass=$((pass+1))
        [ "$QUIET" == "-q" ] || printf '  \033[0;32mPASS\033[0m  %s\n' "$(basename "$t")"
    else
        fail=$((fail+1)); failed+=("$(basename "$t")")
        printf '  \033[0;31mFAIL\033[0m  %s\n' "$(basename "$t")"
        echo "$out" | tail -15 | sed 's/^/        /'
    fi
done

echo ""
if [ $fail -eq 0 ]; then
    printf '  \033[0;32m%d audit test suites passed\033[0m\n' "$pass"
else
    printf '  \033[0;31m%d passed, %d FAILED:\033[0m %s\n' "$pass" "$fail" "${failed[*]}"
fi
exit $((fail > 0))

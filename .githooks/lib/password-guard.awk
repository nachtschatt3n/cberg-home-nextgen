#!/usr/bin/awk -f
#
# Layer 3 password guard for .githooks/pre-commit. Reads a file's staged
# content on stdin, prints `line <N>` for the first line that holds a literal
# credential, prints nothing otherwise.
#
# THE DEFECT THIS REPLACES (found 2026-09-08). The guard used to be two
# whole-FILE greps:
#
#     if grep -qE '(password|passwd)["\s:=]+[^"\s]{8,}'; then
#         if ! grep -qE '(example|placeholder|CHANGEME|\$\{|ENC\[)'; then flag
#
# so ANY `${...}` ANYWHERE in the file disarmed the guard for the whole file.
# 73 of this repo's 112 helmrelease.yaml files carry a Flux postBuild variable,
# which made the guard inert on ~65% of them. The Superset block that leaked an
# admin password self-suppressed twice over: its own value spelled
# `placeholder`, and an `email: admin@${SECRET_DOMAIN}` four lines above
# supplied the `${`. 4.7 months, 28 commits, public repo.
#
# The rule now — PER LINE, and each suppressor scoped to the text it can
# honestly judge:
#
#   VALUE ONLY: interpolation (`${X}` `$X` `$(cmd)` `{{X}}`), SOPS ciphertext
#     (`ENC[...]`), template tokens (`<x>`), `__file`/`__env` sentinels. These
#     are forms that are SYNTACTICALLY NOT A LITERAL. Dictionary words are
#     deliberately absent: `placeholder` is a fine literal string, and treating
#     it as proof of safety is what failed.
#
#   CONTEXT ONLY (the line minus every credential value — the key, the
#     comment, the rest of the line): scaffolding words and reference
#     mechanisms. `placeholder_password: s3cr3tvalue` is scaffolding;
#     `password: placeholder` is a password that happens to spell one.
#
# Nothing is judged against the whole file, and nothing is judged against text
# the secret itself controls.
#
# Test: runbooks/tests/test-cred-suppressor-scoping.py

BEGIN { hit = 0 }

hit { next }

{
    rest = $0
    while (match(tolower(rest), /(password|passwd|secret[_-]?key|blowfish[_-]?secret)["'[:space:]]*[:=][[:space:]]*/)) {
        # Save before any nested match() clobbers RSTART/RLENGTH.
        head  = substr(rest, 1, RSTART + RLENGTH - 1)
        after = substr(rest, RSTART + RLENGTH)

        q = substr(after, 1, 1)
        if (q == "\"" || q == "'") {
            body = substr(after, 2)
            i = index(body, q)
            if (i > 0) { val = substr(body, 1, i - 1); tail = substr(body, i) }
            else       { val = body;                   tail = "" }
        } else if (match(after, /[[:space:]]/)) {
            val  = substr(after, 1, RSTART - 1)
            tail = substr(after, RSTART)
        } else {
            val = after; tail = ""
        }
        sub(/[,;]+$/, "", val)

        rest = tail
        if (length(val) < 8) continue

        # --- per-VALUE: forms that are structurally not a literal ----------
        # Every rule below is about the SHAPE of the value. None of them reads
        # a dictionary word out of it -- that is the defect being fixed.
        if (val ~ /\$\{/ || val ~ /\$\(/ || val ~ /^\$[A-Za-z_]/) continue  # ${X} $(cmd) $X
        if (val ~ /\{\{/)                                         continue  # {{ helm }}
        if (val ~ /^ENC\[/)                                       continue  # SOPS ciphertext
        if (val ~ /^<.*>$/)                                       continue  # <template-token>
        if (val ~ /__file$|__env$/)                               continue  # bjw-s sentinels
        if (val ~ /^[A-Za-z_][A-Za-z0-9_.]*\(/)                   continue  # f(...) call, computed
        if (val ~ /^</)                                           continue  # <template ...> opener
        if (val ~ /\.(json|ya?ml|txt|md|conf|ini|toml)$/)          continue  # a filename, not a value
        # Prose inside a comment that quotes a credential in a code span --
        # this repo's own scanners document the shapes they detect. Narrow on
        # purpose: a COMMENTED-OUT credential with no code span still fires.
        if ($0 ~ /^[[:space:]]*(#|\/\/)/ && head ~ /`/)            continue
        # Balanced markdown inline-code span only -- an OPENING backtick must
        # precede the key. Suppressing on a bare backtick inside the value let a
        # real password that merely contains one buy its own silence.
        if (val ~ /`/ && head ~ /`/)                              continue
        # An env-var NAME as the value. This is the weakest rule here and it is
        # a knowing trade: `password: CORRECT_HORSE_BATTERY` is a real
        # passphrase shape and would be missed. Kept because the alternative is
        # blocking every `apiSecretKey: PENPOT_SECRET_KEY`-style manifest line,
        # and because security-check.py answers the same question properly --
        # it CONFIRMS the name is really used as an env var somewhere in the
        # tree before believing it (`_confirm_env_var_names`). A hook that runs
        # in under a second cannot; two layers, different budgets.
        if (val ~ /^[A-Z][A-Z0-9]*(_[A-Z0-9]+)+$/)                continue

        # --- per-VALUE: the assignment sits INSIDE an interpolation --------
        # `: "$${PGPASSWORD:?PGPASSWORD required}"` -- the `password:` the key
        # regex found is part of a shell parameter expansion, so `head` still
        # has an unclosed `${`. The value is not a value at all.
        if (head ~ /\$\{[^}]*$/)                                  continue

        cmt = ""
        if (match($0, /(#|\/\/).*$/)) cmt = substr($0, RSTART)
        # kt = the KEY TOKEN alone. Trim the separator, then everything before
        # the last non-key character, so a neighbouring field's value on the
        # same line cannot reach the scaffolding-word test. `placeholder_password`
        # survives whole; `username: example_user, ` does not.
        kt = head
        sub(/[[:space:]]*$/, "", kt)
        sub(/["']?[[:space:]]*[:=]$/, "", kt)
        sub(/^.*[^A-Za-z0-9_.[\]-]/, "", kt)
        ctx = tolower(kt " " cmt)
        line_ctx = tolower($0)

        # --- per-CONTEXT: a regex/search PATTERN, not an assignment --------
        # `rg -n "password:|token:|secret:" kubernetes/` -- the alternation bar
        # is the tell, and it only counts next to a search command.
        if (val ~ /\|/ && line_ctx ~ /(^|[^a-z])(rg|grep|ripgrep|egrep|ag)([^a-z]|$)/) continue
        # Same tell inside a source-level REGEX LITERAL (this repo's own scanners
        # match their own patterns). Context-gated on the raw-string / regex
        # syntax around it: ungated, a real password containing a pipe plus any
        # of []^*+?\ went silent -- and the pre-fix whole-file grep caught those.
        if (val ~ /\|/ && val ~ /[\\[\]^*+?]/ &&
            line_ctx ~ /r"|r'|re\.compile|regexp?|pattern|match\(/)                continue

        # --- per-CONTEXT: scaffolding words, never read off the value ------
        if (ctx ~ /example|placeholder/)                                       continue
        if (ctx ~ /change[_-]?me|replace[_-]?me|replace[_-]?with|your[_-]/)     continue

        # --- per-CONTEXT: the line names a secret instead of holding one ---
        if (ctx ~ /secretkeyref|valuefrom|existingsecret|secretname|secretref/) continue
        if (ctx ~ /keyref|process\.env|getenv|os\.environ/)                     continue

        # --- EXACT-MATCH template allowlist --------------------------------
        # Deliberately exact, and deliberately tiny. This is NOT the substring
        # match that failed: `placeholder` and `replace-me-now` are not members
        # and still fire. Only a value that IS one of these canonical template
        # strings is exempt. MUST stay equal to _TEMPLATE_LITERALS in
        # security-check.py -- test-cred-suppressor-scoping.py asserts the two
        # sets are identical, because three copies had already drifted apart.
        # `my-aws-secret-key` is the AdGuard chart's own unset S3-backup default
        # (kubernetes/apps/network/internal/adguard-home); security-check.py
        # allowlists the same string. Because the match is EXACT, the day that
        # field is given a real value the guard fires again.
        lv = tolower(val)
        if (lv == "replace-me" || lv == "my-strong-password" || lv == "my-api-key" ||
            lv == "your-api-key-here" || lv == "my-aws-secret-key") continue

        print "line " FNR
        hit = 1
        next
    }
}

# SOP: <Title>

> Description: <One or two sentences describing purpose and scope>
> Version: `YYYY.MM.DD` (date versioning, e.g. `2026.02.04`)
> Last Updated: `YYYY-MM-DD`
> Owner: `<team-or-person>`

---

## 1) Description

State what this SOP covers, why it exists, and where it applies.

- Scope: `<systems/namespaces/apps>`
- Prerequisites: `<access/tools/permissions>`
- Out of scope: `<optional>`

---

## 2) Overview

Summarize key runtime/settings that operators need quickly.

| Setting | Value |
|---------|-------|
| Namespace | `<namespace>` |
| Source of truth | `<path>` |
| Critical dependency | `<service/component>` |

---

## 3) Blueprints

Document the declarative source of truth and related blueprint/config artifacts.
If not applicable, keep this section and write `N/A`.

- Source of truth file(s): `<path>`
- Related manifests/templates: `<path>`
- Required IDs/constants (if any): `<values>`

```yaml
# Minimal blueprint/config pattern (replace with real content)
version: 1
entries: []
```

---

## 4) Operational Instructions

Provide step-by-step instructions for normal operations.

1. Preparation
2. Change implementation
3. Commit/push (GitOps)
4. Reconciliation/rollout checks

```bash
# Example operation flow
git add <paths>
git commit -m "docs(sop): update <topic>"
git push
```

---

## 5) Examples

Include concrete examples for common scenarios.

### Example A: <common case>

```bash
# commands
```

### Example B: <edge case>

```bash
# commands
```

---

## 6) Verification Tests

Add explicit tests to prove the SOP change worked.
Every test should include command, expected result, and failure hint.

### Test 1: <name>

```bash
# command
```

Expected:
- `<observable success condition>`

If failed:
- `<first debugging step>`

### Test 2: <name>

```bash
# command
```

Expected:
- `<observable success condition>`

If failed:
- `<first debugging step>`

---

## 7) Troubleshooting

Capture the most common failure modes and first-response actions.

| Symptom | Likely Cause | First Fix |
|---------|--------------|-----------|
| `<what broke>` | `<probable reason>` | `<first action>` |
| `<what broke>` | `<probable reason>` | `<first action>` |

```bash
# Quick debugging commands
```

---

## 8) Diagnose Examples

Provide concrete diagnosis flows for failure scenarios.

### Diagnose Example 1: <failure case>

```bash
# diagnostic commands
```

Expected:
- `<what confirms the root cause>`

If unclear:
- `<next command/check>`

### Diagnose Example 2: <failure case>

```bash
# diagnostic commands
```

Expected:
- `<what confirms the root cause>`

If unclear:
- `<next command/check>`

---

## 9) Health Check

Add a short recurring verification checklist/commands for ongoing confidence.

```bash
# periodic checks
```

Expected:
- `<healthy condition>`

---

## 10) Security Check

Define explicit security validation after changes.

```bash
# security-focused checks
```

Expected:
- `<no plaintext secrets in repo>`
- `<auth/access policy still enforced>`
- `<no unintended exposure>`

---

## 11) Rollback Plan

Document the safest rollback path.

```bash
# rollback commands
```

---

## 12) References

- `<related docs>`
- `<source manifests>`
- `<runbooks>`

---

## Version History

- `YYYY.MM.DD`: <what changed>

# SUBAGENTS.md

This file is the single source of truth for subagent definitions in this repository.

When asked to sync agents, generate or update platform-specific definitions from this
document in:

- Claude Code: `.claude/agents/*.md`
- OpenCode: `.opencode/agents/*.md` (or `opencode.json` agent config)
- Codex CLI: `.codex/config.toml` with `[agents.<role>]` entries
- Gemini CLI: `.gemini/agents/*.md` (and ensure agents are enabled in settings)

Do not invent behavior that conflicts with this file. If a platform schema changes,
update `Platform Notes` first, then regenerate platform files.

## Global Rules

- Repository policy: GitOps-only workflow (change manifests in git, do not perform direct
  cluster mutations unless explicitly requested).
- Prefer read-only diagnostics first. Ask before destructive or state-changing actions.
- Follow AGENTS.md conventions for naming, formatting, and security.
- Never expose secrets, literal domains, API keys, or personal identifiers in outputs.
- Prefer existing runbooks and SOPs in `docs/sops/` before inventing ad-hoc procedures.

## Platform Notes

Keep this section current. It is the compatibility contract for generated agent files.

### Claude Code

- Target directory: `.claude/agents/`
- File format: Markdown with YAML frontmatter and Markdown body.
- Required frontmatter fields: `name`, `description`.
- Optional frontmatter includes `tools`, `model`, and permission/runtime controls.
- The system prompt is the Markdown body (not a `system_prompt` frontmatter key).
- Definition template:
  ```markdown
  ---
  name: health-check-agent
  description: Runs cluster health diagnostics.
  tools: bash, read, grep
  model: haiku
  ---

  You are the health check specialist...
  ```

### OpenCode

- Target directory: `.opencode/agents/`
- File format: Markdown with YAML frontmatter and Markdown body.
- Agent name comes from filename (for example `health-check.md` => `@health-check`).
- Required frontmatter field: `description`.
- Optional frontmatter includes `mode`, `model`, `temperature`, `tools`, permissions.
- OpenCode also supports defining agents via `opencode.json`.
- Definition template:
  ```markdown
  ---
  description: Runs cluster health diagnostics.
  mode: subagent
  model: anthropic/claude-3-5-haiku-latest
  ---

  You are the health check specialist...
  ```

### Codex

- Primary config path: `.codex/config.toml`.
- Multi-agent support is experimental and must be enabled:
  ```toml
  [features]
  multi_agent = true
  ```
- Define roles in config with `[agents.<name>]`.
- Supported keys for each role are `description` and `config_file`.
- `config_file` points to another TOML file with role-specific runtime settings
  (model, sandbox mode, developer instructions, etc.).
- There is no canonical `.codex/agents/*.md` schema equivalent to Claude/OpenCode/Gemini.
- Definition template:
  ```toml
  [features]
  multi_agent = true

  [agents.health_check]
  description = "Runs cluster health diagnostics"
  config_file = ".codex/agents/health-check.toml"
  ```

### Gemini

- Target directory: `.gemini/agents/`
- File format: Markdown with YAML frontmatter and Markdown body.
- Custom subagents are experimental and require:
  - `.gemini/settings.json` with:
    ```json
    {
      "experimental": {
        "enableAgents": true
      }
    }
    ```
- Required frontmatter fields: `name`, `description`.
- Optional frontmatter includes `model`, `temperature`, `tools`, execution limits.
- Definition template:
  ```markdown
  ---
  name: health-check-agent
  description: Runs cluster health diagnostics.
  model: gemini-2.5-flash
  ---

  You are the health check specialist...
  ```

## Canonical Agent Schema

Use this canonical block when translating to platform-specific files:

- `id`: stable kebab-case identifier
- `description`: one-sentence purpose
- `tools`: allowed tool categories and boundaries
- `model_tier`: recommended model class
- `temperature`: generation temperature
- `inputs`: expected context or prerequisite files
- `outputs`: expected artifacts or report destinations
- `system_prompt`: authoritative behavioral instructions

---

## health-check-agent

**id:** `health-check-agent`  
**description:** Runs cluster and service health diagnostics with a read-only, evidence-first workflow.  
**tools:** shell (read-only kubectl/flux/talosctl/unifictl), file-read, grep/rg  
**model_tier:** fast/cheap (Haiku/Flash equivalent)  
**temperature:** `0.1`  
**inputs:**
- `runbooks/health-check.md`
- `scripts/health-check.sh`
- `docs/sops/*.md` (as needed)
**outputs:**
- Health findings summary in chat
- Optional generated files from `scripts/health-check.sh` in `/tmp/`
**system_prompt:**
You are the cluster health check specialist for this home-lab Kubernetes platform.
Use `runbooks/health-check.md` as the primary checklist and execute checks in order.
Prefer read-only diagnostics. Treat warnings by severity and provide concrete evidence
(command + key output + interpretation). If a likely fix requires state changes
(delete/restart/reconcile/apply), stop and request approval first. Use SOPs in `docs/sops/`
when relevant and include verification and rollback notes in recommendations.

---

## version-check-agent

**id:** `version-check-agent`  
**description:** Audits Helm chart and container image versions and reports safe upgrade opportunities.  
**tools:** shell (python3, helm, gh, git, read-only cluster queries), file-read, grep/rg  
**model_tier:** fast/cheap (Haiku/Flash equivalent)  
**temperature:** `0.1`  
**inputs:**
- `runbooks/version-check.md`
- `runbooks/check-all-versions.py`
- `runbooks/extract-current-versions.sh`
- `kubernetes/apps/**/helmrelease.yaml`
**outputs:**
- `runbooks/version-check-current.md`
- Structured summary of major/minor/patch/security updates
**system_prompt:**
You are the version intelligence specialist for this repository.
Follow `runbooks/version-check.md` and prefer `runbooks/check-all-versions.py`.
Report current versus latest versions, classify update risk (major/minor/patch/security),
and highlight potential breaking changes. Do not perform upgrades automatically.
When suggesting updates, include ordered execution steps, validation checks, and rollback
considerations aligned with GitOps and Flux workflows.

---

## security-agent

**id:** `security-agent`  
**description:** Performs repository and cluster security audits with strict redaction and SOPS-first handling.  
**tools:** shell (sops, kubectl, git, python3, openssl, unifictl), file-read, grep/rg  
**model_tier:** capable reasoning (Sonnet/Pro equivalent)  
**temperature:** `0.0`  
**inputs:**
- `runbooks/security-check.md`
- `runbooks/security-check.py`
- `.sops.yaml`
- `kubernetes/**/*.sops.yaml`
**outputs:**
- `runbooks/security-check-current.md` (redacted)
- Prioritized findings with criticality and remediation plan
**system_prompt:**
You are the security auditor for this public homelab repository.
Execute `runbooks/security-check.md` (or `runbooks/security-check.py`) and classify findings
as Critical/Warning/OK. Never print plaintext secrets, literal domains, credentials, personal
name/email, or decrypted secret payloads. Enforce SOPS coverage and flag any unencrypted secret
material immediately. Recommend GitOps-safe remediation and include explicit secret-rotation
guidance when exposure is suspected.

---

## doc-agent

**id:** `doc-agent`  
**description:** Validates that infrastructure and operational documentation matches actual repository and cluster state.  
**tools:** shell (python3, kubectl, sops, unifictl, git), file-read, grep/rg  
**model_tier:** fast/cheap (Haiku/Flash equivalent)  
**temperature:** `0.2`  
**inputs:**
- `runbooks/doc-check.md`
- `runbooks/doc-check.py`
- `docs/applications.md`
- `docs/infrastructure.md`
- `docs/network.md`
- `docs/security.md`
- `docs/sops/*.md`
**outputs:**
- `runbooks/doc-check-current.md` (gitignored)
- Drift report (missing/stale docs + recommended edits)
**system_prompt:**
You are the documentation consistency specialist.
Run `runbooks/doc-check.md` or `runbooks/doc-check.py` and verify docs match live and repo
state. Treat missing canonical docs or materially incorrect content as critical. Treat stale
or incomplete entries as warnings. Prefer concise diffs and direct file-level edit suggestions.
Do not create session-only status docs; keep recurring procedures in runbooks and reusable SOPs
under `docs/sops/`.

---

## Sync Contract

When asked to "sync platform agents from SUBAGENTS.md":

1. Parse this file and validate required canonical fields for each agent.
2. Read `Platform Notes` and map canonical fields to each platform schema.
3. Create/update platform files using each platform's native schema:
   - Claude: `.claude/agents/*.md`
   - OpenCode: `.opencode/agents/*.md` (or `opencode.json`)
   - Codex: `.codex/config.toml` (+ optional referenced role TOML files)
   - Gemini: `.gemini/agents/*.md` and `.gemini/settings.json` experimental flag
4. Preserve behavior parity across platforms.
5. Report generated file paths and any schema gaps/TODOs explicitly.

## Sources

Last verified: `2026-03-01`

- Claude Code subagents docs:
  `https://docs.anthropic.com/en/docs/claude-code/sub-agents`
- OpenCode agents docs:
  `https://opencode.ai/docs/agents/`
- Codex AGENTS instruction docs:
  `https://developers.openai.com/codex/guides/agents-md`
- Codex multi-agent docs:
  `https://developers.openai.com/codex/multi-agent`
- Gemini CLI subagents docs:
  `https://geminicli.com/docs/core/subagents/`

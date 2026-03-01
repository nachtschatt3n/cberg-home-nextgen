# Documentation Health Check Runbook

## Purpose

This runbook provides a systematic, AI-executable documentation audit for the home lab Kubernetes
cluster. It verifies that the reference documentation in `docs/` and `docs/sops/` accurately
reflects the live cluster state, that coding guidelines in CLAUDE.md are current and actionable,
and that all operational runbooks are up to date.

Run weekly (same cadence as version-check and security-check) or after significant cluster changes.

## SOP Integration

This runbook must validate SOP discoverability and usage in addition to docs health.

SOP discovery commands:
- `ls docs/sops/`
- `rg -n "<keyword>" docs/sops/*.md`
- `rg -n "^# SOP:" docs/sops/*.md`

During documentation review:
- Prefer existing SOPs for operational procedures.
- If a reusable new solution is identified and no SOP exists, create one from:
  `docs/sops/SOP-TEMPLATE.md`
- Ensure new SOP uses date versioning (`YYYY.MM.DD`).

## Severity Model

- 🔴 **Critical** — documentation is materially wrong or missing (e.g., age key mismatch,
  reference doc file missing, documented tool command doesn't work)
- 🟡 **Warning** — documentation is incomplete or potentially stale (e.g., app not in
  `docs/applications.md`, runbook output >7 days old, undocumented app deployed)
- 🟢 **OK** — documentation is accurate and current

## Output

Results are written to `runbooks/doc-check-current.md` (gitignored — never commit).

---

## Quick Start (Automated)

```bash
python3 runbooks/doc-check.py
```

Output: `runbooks/doc-check-current.md`

---

## Preparation

```bash
# Verify tool availability
which kubectl sops git python3 unifictl

# Verify cluster access
kubectl cluster-info

# Verify SOPS key is available
echo "SOPS key: $(head -1 $SOPS_AGE_KEY_FILE | wc -c) chars"
```

---

## 1. Infrastructure Documentation

**Objective**: Confirm `docs/infrastructure.md` reflects the current Kubernetes/Talos versions,
node inventory, and cluster topology.

**Commands:**

```bash
# Get live Kubernetes server version
kubectl version -o json 2>/dev/null | python3 -c "
import sys, json
d = json.load(sys.stdin)
print('Server:', d.get('serverVersion', {}).get('gitVersion', 'unavailable'))
"

# Get live node names
kubectl get nodes -o jsonpath='{.items[*].metadata.name}'

# Get Talos version
talosctl version --client 2>/dev/null | grep Tag

# Compare against docs/infrastructure.md
grep -E "v1\.[0-9]+\.[0-9]+" docs/infrastructure.md
grep "k8s-nuc14" docs/infrastructure.md
```

**Expected results:**
- `docs/infrastructure.md` exists and is non-empty
- K8s server version appears in the doc
- All node names (k8s-nuc14-01, k8s-nuc14-02, k8s-nuc14-03) are listed
- Mac Mini IP (192.168.30.111) and NAS IP (192.168.31.230) are mentioned

**Severity:**
- 🔴 Critical if `docs/infrastructure.md` is missing
- 🟡 Warning if K8s version in doc doesn't match live server version

---

## 2. Network Documentation

**Objective**: Confirm `docs/network.md` VLAN and WiFi tables match the live UniFi configuration.

**Commands:**

```bash
# Get live VLANs from UniFi
unifictl local network list -o json 2>/dev/null | python3 -c "
import sys, json
d = json.load(sys.stdin)
nets = d.get('data', d) if isinstance(d, dict) else d
for n in nets:
    vlan_id = n.get('vlan_id') or n.get('vlan') or '(none)'
    print(f\"VLAN {vlan_id}: {n.get('name', '?')}\")
"

# Get live WiFi SSIDs from UniFi
unifictl local wlan list -o json 2>/dev/null | python3 -c "
import sys, json
d = json.load(sys.stdin)
wlans = d.get('data', d) if isinstance(d, dict) else d
[print(w.get('name', '?')) for w in wlans]
"

# Check documented VLANs
grep -E "^\| [0-9]+" docs/network.md

# Check documented SSIDs
grep -E "cberg-|Cberg-" docs/network.md
```

**Expected results:**
- `docs/network.md` exists and is non-empty
- All live VLAN IDs appear in the doc's VLAN table
- All live SSIDs appear in the doc's WiFi table

**Severity:**
- 🔴 Critical if `docs/network.md` is missing
- 🟡 Warning if a live VLAN ID is absent from the doc
- 🟡 Warning if unifictl is unavailable (cannot verify, mark as unchecked)

---

## 3. Application Documentation

**Objective**: Confirm `docs/applications.md` lists all deployed apps; identify undocumented
apps and stale entries.

**Commands:**

```bash
# Get all deployed apps from HelmRelease files
find kubernetes/apps -name "helmrelease.yaml" -o -name "helm-release.yaml" 2>/dev/null \
  | grep "/app/" | sed 's|kubernetes/apps/||;s|/app/.*||' | sort -u

# Count deployed apps per namespace
for ns in kubernetes/apps/*/; do
  ns_name=$(basename $ns)
  count=$(find $ns -name "helmrelease.yaml" -o -name "helm-release.yaml" 2>/dev/null | wc -l)
  echo "$ns_name: $count"
done

# Check docs/applications.md for each deployed app
# (Compare manually or via script)
grep -c "| " docs/applications.md  # Row count
```

**Expected results:**
- `docs/applications.md` exists and lists apps for all 16 namespaces
- Each deployed app appears in the doc (or is explicitly excluded from user-facing docs)
- App count in doc is close to cluster count (minor infra apps may be omitted intentionally)

**Severity:**
- 🔴 Critical if `docs/applications.md` is missing
- 🟡 Warning per app deployed but not documented

---

## 4. Security Documentation

**Objective**: Confirm `docs/security.md` is accurate: SOPS age key matches `.sops.yaml`,
Authentik blueprint workflow is documented, cert-manager is covered.

**Commands:**

```bash
# Extract age key from .sops.yaml
grep "age1" .sops.yaml

# Check same key appears in docs/security.md
grep "age1" docs/security.md

# Verify keys match
SOPS_KEY=$(grep -o 'age1[a-z0-9]*' .sops.yaml | head -1)
DOC_KEY=$(grep -o 'age1[a-z0-9]*' docs/security.md | head -1)
[ "$SOPS_KEY" = "$DOC_KEY" ] && echo "MATCH" || echo "MISMATCH: $SOPS_KEY != $DOC_KEY"

# Check Authentik blueprint docs
grep -l "blueprint" docs/security.md
grep "configmap.sops.yaml" docs/security.md

# Check cert-manager and Let's Encrypt
grep -i "cert-manager\|let's encrypt" docs/security.md
```

**Expected results:**
- `docs/security.md` exists
- Age key in doc exactly matches `.sops.yaml`
- `blueprint` and `configmap.sops.yaml` mentioned in Authentik section
- cert-manager and Let's Encrypt documented

**Severity:**
- 🔴 Critical if `docs/security.md` missing or age key mismatches
- 🟡 Warning if Authentik or cert-manager sections are missing

---

## 5. Integration Documentation

**Objective**: Confirm `docs/integration.md` documents Ollama endpoints, Homepage groups,
and Renovate schedule accurately.

**Commands:**

```bash
# Check Ollama endpoints documented
grep "192.168.30.111:11434" docs/integration.md
grep "192.168.30.111:11435" docs/integration.md
grep "192.168.30.111:11436" docs/integration.md

# Check Homepage groups in helmrelease
grep -E "^        -" kubernetes/apps/default/homepage/app/helmrelease.yaml \
  | grep -v "^#" | head -20

# Check Renovate schedule
grep "schedule" .github/renovate.json5
grep -i "weekend\|schedule" docs/integration.md

# Verify docs/integration.md exists
wc -l docs/integration.md
```

**Expected results:**
- `docs/integration.md` exists
- All three Ollama endpoint ports (11434, 11435, 11436) documented
- Renovate schedule matches `.github/renovate.json5`

**Severity:**
- 🔴 Critical if `docs/integration.md` missing
- 🟡 Warning if Ollama ports not all documented

---

## 6. README & CLAUDE.md Currency

**Objective**: Confirm README badges match live cluster versions; CLAUDE.md age key matches
`.sops.yaml`.

**Commands:**

```bash
# Check README version badges
grep "Talos-v" README.md
grep "Kubernetes-v" README.md
grep "Flux" README.md

# Compare against live versions
kubectl version --client 2>/dev/null | grep -o "v[0-9.]*"
talosctl version --client 2>/dev/null | grep Tag

# Check CLAUDE.md age key matches .sops.yaml
CLAUDE_KEY=$(grep -o 'age1[a-z0-9]*' CLAUDE.md | head -1)
SOPS_KEY=$(grep -o 'age1[a-z0-9]*' .sops.yaml | head -1)
[ "$CLAUDE_KEY" = "$SOPS_KEY" ] && echo "MATCH" || echo "MISMATCH"

# Check namespace sections in README
grep -E "### .*(Automation|AI|Databases|Monitoring|Office|Media)" README.md
```

**Expected results:**
- README version badges match live cluster
- Age key in CLAUDE.md matches `.sops.yaml`
- README covers all major application categories

**Severity:**
- 🟡 Warning if version badges are outdated (more than one minor version behind)
- 🔴 Critical if age key in CLAUDE.md doesn't match `.sops.yaml`

---

## 7. Coding Guidelines

**Objective**: Confirm all tools referenced in CLAUDE.md Build/Lint/Test Commands section
are available in PATH; Taskfile task references are valid.

**Commands:**

```bash
# Check all required tools exist
for tool in task kubeconform talhelper kubectl sops flux talosctl; do
  echo -n "$tool: "
  which $tool 2>/dev/null || echo "NOT FOUND"
done

# Verify key task commands from CLAUDE.md exist in Taskfile.yaml
grep "task " CLAUDE.md | grep -o 'task [a-z:]*' | sort -u

# Check Taskfile tasks
grep -E "^  [a-z:]+:" Taskfile.yaml | head -20

# Verify SOPS docs workflow commands exist in docs/sops/sops-encryption.md
wc -l docs/sops/sops-encryption.md
```

**Expected results:**
- All tools found in PATH (mise should provide them)
- Task names referenced in CLAUDE.md exist in Taskfile.yaml
- `docs/sops/sops-encryption.md` exists

**Severity:**
- 🔴 Critical if a commonly-used tool is missing from PATH
- 🟡 Warning if a Taskfile task referenced in CLAUDE.md doesn't exist

---

## 8. Runbook Coverage

**Objective**: Confirm all `*-current.md` output files are recent (< 7 days); all runbook
procedures have corresponding scripts; SOP template and SOP files exist and follow required
sections; output files are gitignored.

**Commands:**

```bash
# Check age of all *-current.md files (should be < 7 days)
find runbooks/ -name "*-current.md" -exec ls -la {} \;

# Check each output file's age
for f in runbooks/*-current.md; do
  echo -n "$f: "
  stat -c "%y" "$f" 2>/dev/null | cut -d. -f1 || stat -f "%Sm" "$f"
done

# Check runbook-script pairings
ls runbooks/*.md runbooks/*.py runbooks/*.sh

# Check all SOP files exist
ls docs/sops/

# Check SOP template exists
test -f docs/sops/SOP-TEMPLATE.md && echo "SOP template present"

# Validate required sections in each SOP (excluding template)
python3 - << 'PY'
import glob, re
required = [
  "Description","Overview","Blueprints","Operational Instructions","Examples",
  "Verification Tests","Troubleshooting","Diagnose Examples","Health Check",
  "Security Check","Rollback Plan"
]
for f in sorted(glob.glob("docs/sops/*.md")):
    if f.endswith("SOP-TEMPLATE.md"):
        continue
    txt=open(f).read().splitlines()
    heads=[re.sub(r'^##\\s+','',ln).strip() for ln in txt if ln.startswith("## ")]
    missing=[h for h in required if h not in heads]
    if missing:
        print(f"MISSING SECTIONS: {f}: {', '.join(missing)}")
    if not any(ln.startswith("> Version:") for ln in txt[:20]):
        print(f"MISSING VERSION HEADER: {f}")
PY

# Check output files are gitignored
grep "doc-check-current" .gitignore
grep "security-check-current" .gitignore
```

**Expected results:**
- All `*-current.md` files modified within last 7 days (or justified reason for staleness)
- Each runbook `.md` has a matching script (`.py` or `.sh`)
- `docs/sops/SOP-TEMPLATE.md` exists
- All SOP files in `docs/sops/` include required sections and version header
- `runbooks/doc-check-current.md` in `.gitignore`
- `runbooks/security-check-current.md` in `.gitignore`

**Severity:**
- 🟡 Warning if any `*-current.md` is > 7 days old
- 🟡 Warning if a runbook has no matching script
- 🟡 Warning if SOP template is missing
- 🟡 Warning if any SOP is missing required sections or version header
- 🟡 Warning if output files are not gitignored

---

## Report Generation

The automated script (`doc-check.py`) generates `runbooks/doc-check-current.md` automatically.

For manual reporting, start the output file:

```bash
cat > runbooks/doc-check-current.md << EOF
# Documentation Health Check — $(date '+%Y-%m-%d %H:%M %Z')

> Manually generated — do not hand-edit (overwritten on next automated run).

EOF
```

Then append findings from each section.

---

## Execution Schedule

| Trigger | Frequency | Who |
|---------|-----------|-----|
| Weekly documentation review | Weekly (Monday) | AI agent / manual |
| After new app deployment | Within 24 hours | AI agent |
| After CLAUDE.md changes | Within 24 hours | AI agent |
| After major cluster upgrade | Within 48 hours | AI agent |

---

## How to Fix Common Issues

### Age Key Mismatch
Update `docs/security.md` and `CLAUDE.md` to contain the correct public key from `.sops.yaml`.

### App Not in `docs/applications.md`
Add the app to the appropriate namespace table in `docs/applications.md`.

### Stale `*-current.md` File
Run the corresponding script:
- `runbooks/version-check-current.md` → `python3 runbooks/check-all-versions.py`
- `runbooks/security-check-current.md` → `python3 runbooks/security-check.py`
- `runbooks/doc-check-current.md` → `python3 runbooks/doc-check.py`

### VLAN Not in `docs/network.md`
Add the VLAN to the VLAN table in `docs/network.md`.

### Tool Not Found in PATH
Check that mise has installed the tool: `mise ls` and `mise install {tool}`.

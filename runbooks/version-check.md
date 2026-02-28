# Kubernetes Deployment Version Checking Guide

This document describes how to check for updates to all Kubernetes deployments in the cluster.

## Overview

The version checking system scans all HelmReleases in the repository and checks for:
1. **Chart Versions**: Current vs latest available from Helm repositories
2. **Container Image Versions**: Current vs latest available from container registries
3. **Application Versions**: Where applicable (extracted from image tags)
4. **Update Complexity Assessment**: Classifies updates as major/minor/patch
5. **Breaking Changes Detection**: Identifies potential breaking changes from release notes
6. **Renovate PRs**: Lists open Renovate bot PRs with type and merge status

## Tools

### Primary Tool: `check-all-versions.py` (Full Version Check)

Location: `runbooks/check-all-versions.py`

A comprehensive Python script that:
- Scans all HelmRelease YAML files in `kubernetes/apps/`
- Extracts chart versions and repository information
- Extracts container image tags from Helm values
- Checks for newer versions using:
  - Helm CLI for chart versions
  - Registry APIs (Docker Hub, GHCR, Quay.io) for image tags
- Generates a detailed markdown report with update indicators

**Requirements:** Python 3.8+, `pyyaml`, `requests`, `packaging`, Helm CLI

**GitHub Authentication:**
- **Preferred:** GitHub CLI (`gh`) - automatically authenticated, no rate limits
- **Alternative:** GitHub Personal Access Token
  - Without token: 60 requests/hour (unauthenticated)
  - With token: 5000 requests/hour (authenticated)
  - Set via environment variable: `export GITHUB_TOKEN=your_token_here`

### Basic Tool: `extract-current-versions.sh` (Current State Only)

Location: `runbooks/extract-current-versions.sh`

A bash script that:
- Scans all HelmRelease YAML files
- Extracts current chart and image versions
- Generates a basic status report
- **Does NOT check for updates** (use Python script for that)

**Requirements:** Bash, standard Unix tools (grep, sed, find)

**Use this when:**
- You need a quick overview of current versions
- Python dependencies are not available
- You want to see the structure before running full checks

### Legacy Tool: `check-versions.sh`

Location: `runbooks/check-versions.sh`

A basic bash script that checks a limited set of applications via GitHub releases API. This is kept for reference but the Python script is recommended.

## Usage

### Prerequisites

1. **Python 3.8+** with required packages:
   
   This repository uses **mise** for dependency management. Dependencies are defined in `requirements.txt` and installed via mise:
   
   ```bash
   # Install dependencies using mise (recommended)
   mise run deps
   
   # This will:
   # - Use the Python version specified in .mise.toml (3.13)
   # - Create/use the virtual environment at .venv
   # - Install packages from requirements.txt using uv
   
   # Verify installation
   python3 -c "import yaml, requests; print('Dependencies OK')"
   ```
   
   **Alternative methods** (if not using mise):
   ```bash
   # Method 1: System-wide (requires sudo)
   sudo pip3 install pyyaml requests
   
   # Method 2: User install
   pip3 install --user pyyaml requests
   
   # Method 3: Virtual environment
   source .venv/bin/activate
   pip install pyyaml requests
   ```

2. **Helm CLI** installed and configured:
   ```bash
   # Verify helm is installed
   helm version
   
   # If not installed, install Helm:
   # On macOS: brew install helm
   # On Linux: See https://helm.sh/docs/intro/install/
   ```

3. **Network access** to:
   - Helm chart repositories
   - Container registries (Docker Hub, GHCR, Quay.io)
   - GitHub API (for GHCR images)

### Running the Version Check

#### Option 1: Full Version Check (Recommended)

```bash
# From repository root
cd /home/mu/code/cberg-home-nextgen

# Install dependencies using mise (if not already installed)
mise run deps

# The script automatically uses GitHub CLI (gh) if available and authenticated
# If gh is not available, you can optionally set a GitHub token:
# export GITHUB_TOKEN=your_github_token_here

# Run the full version checker
python3 runbooks/check-all-versions.py
```

The script independently scans the cluster for updates **and** overlays open Renovate PRs as a complementary view. It will:
1. Scan all HelmRelease files
2. Load HelmRepository definitions
3. Check each deployment for updates (directly against Helm repos and container registries)
4. Assess update complexity (major/minor/patch)
5. Detect breaking changes from release notes
6. Fetch open Renovate PRs via GitHub CLI (independent of the above scans)
7. Generate `runbooks/version-check-current.md` with results including:
   - **Renovate PRs table** (open PRs grouped by type with merge status)
   - Update indicators (⚠️ for updates available, ✅ for up-to-date)
   - Complexity assessment (🔴 major, 🟡 minor, 🟢 patch)
   - Breaking changes warnings
   - Release notes information

#### Option 2: Basic Extraction (Quick Overview)

```bash
# From repository root
cd /home/mu/code/cberg-home-nextgen

# Run the basic extraction script
bash runbooks/extract-current-versions.sh
```

This script will:
1. Scan all HelmRelease files
2. Extract current versions (no update checking)
3. Generate `runbooks/version-check-current.md` with current state only

### Output

The script generates `runbooks/version-check-current.md` containing:
- Summary statistics (total deployments, updates available)
- Update breakdown by complexity (major/minor/patch)
- Breaking changes count
- **Renovate PRs table** — open Renovate bot PRs with type (🔴 major / 🟡 minor / 🟢 patch / 🔒 security) and status (✅ Ready / ⚡ Conflicts / 📝 Draft)
- Quick overview table of all deployments
- Detailed breakdown by namespace
- For each deployment:
  - Chart name, repository, current and latest versions
  - Container images with current and latest tags
  - Update indicators (⚠️ for updates available, ✅ for up-to-date)
  - **Update complexity assessment** (🔴 major, 🟡 minor, 🟢 patch)
  - **Breaking changes warnings** (if detected)
  - Release notes information (when available)

## How It Works

### 1. Scanning HelmReleases

The script searches for all `helmrelease.yaml` files in:
```
kubernetes/apps/**/helmrelease.yaml
```

### 2. Extracting Chart Information

From each HelmRelease, it extracts:
- Chart name: `spec.chart.spec.chart`
- Chart version: `spec.chart.spec.version`
- Repository: `spec.chart.spec.sourceRef.name`

### 3. Extracting Image Information

The script recursively searches Helm values for image definitions in various patterns:

**Standard pattern:**
```yaml
values:
  image:
    repository: ghcr.io/owner/repo
    tag: v1.2.3
```

**App-template pattern:**
```yaml
values:
  controllers:
    app-name:
      containers:
        app:
          image:
            repository: ghcr.io/owner/repo
            tag: v1.2.3
```

**Direct image string:**
```yaml
values:
  containers:
    app:
      image: busybox:1.36
```

### 4. Checking Chart Versions

For each chart, the script:
1. Looks up the HelmRepository definition
2. Determines repository type (OCI or traditional)
3. Uses `helm search repo` to find latest version

**OCI Repositories:**
- Examples: `oci://ghcr.io/prometheus-community/charts`
- Uses Helm's OCI support

**Traditional Repositories:**
- Examples: `https://charts.longhorn.io`
- Uses Helm repository index

### 5. Checking Image Tags

The script checks container registries based on the image repository:

**GitHub Container Registry (GHCR):**
- Uses GitHub Releases API
- Extracts owner/repo from `ghcr.io/owner/repo`
- Gets latest release tag

**Docker Hub:**
- Uses Docker Hub API v2
- Gets most recently updated tag

**Quay.io:**
- Uses Quay API
- Gets latest active tag

**Other registries:**
- Attempts generic Docker Hub API
- May not work for all registries

### 6. Assessing Update Complexity

The script analyzes version differences to classify updates:

**Major Updates (🔴 High Complexity):**
- Version format: `1.x.x → 2.x.x` (major version increased)
- Typically indicates breaking changes
- Requires careful review and testing
- May require configuration changes or migrations

**Minor Updates (🟡 Medium Complexity):**
- Version format: `1.2.x → 1.3.x` (minor version increased)
- Usually adds new features or improvements
- Generally backward compatible
- May introduce new configuration options

**Patch Updates (🟢 Low Complexity):**
- Version format: `1.2.3 → 1.2.4` (patch version increased)
- Bug fixes and security patches
- Typically safe to apply
- Minimal risk of breaking changes

**Version Parsing:**
- Supports semantic versioning (1.2.3)
- Handles 'v' prefix (v1.2.3)
- Handles pre-release versions (1.2.3-alpha)
- Falls back to regex parsing for non-standard formats

### 7. Detecting Breaking Changes

The script attempts to detect breaking changes by:

**Release Notes Analysis:**
- Fetches release notes from GitHub API (for charts and GHCR images)
- Extracts breaking changes sections from release notes
- Searches for explicit breaking change markers:
  - "## Breaking Changes" sections
  - "BREAKING" or "BREAKING CHANGE" keywords
  - "Migration" or "Upgrade" guides
  - "Deprecated" or "Removed" warnings
  - "API change" mentions

**Heuristic Detection:**
- Major version updates are flagged as likely having breaking changes
- Even if no explicit markers are found in release notes

**Breaking Change Display:**
- ⚠️ Warning displayed in report
- **Actual breaking change content** extracted from release notes
- Full release notes included in document (up to 3000 chars)
- Source link always provided for full details

**GitHub API Access:**
- **GitHub CLI (`gh`)**: Automatically detected and used if available and authenticated
  - No rate limits when using authenticated `gh` CLI
  - Fastest and most reliable method
- **GitHub Token**: Fallback if `gh` is not available
  - Without token: 60 requests/hour (unauthenticated)
  - With token: 5000 requests/hour (authenticated)
  - Set `GITHUB_TOKEN` environment variable
- When rate limited or `gh` unavailable, source links are still provided for manual checking

**Note:** Breaking change detection extracts actual content from release notes. Always review:
- Full release notes (included in report when available)
- Official release notes (via source links)
- Changelogs
- Migration guides
- Upgrade documentation

### 8. Fetching Renovate PRs (Complementary View)

The Renovate PR section is independent of the version scanning above — the script queries Helm repos and registries directly regardless of whether Renovate has opened any PRs. The Renovate section simply shows what the bot has already staged, which can be useful to cross-reference or merge directly instead of manually bumping versions.

The script fetches open Renovate bot PRs via the GitHub CLI (`gh`):

```bash
gh pr list --author app/renovate --state open \
  --json number,title,labels,isDraft,mergeable,url --limit 100
```

**Update type inference** — checked in order:
1. Labels: `type/major`, `type/minor`, `type/patch` (Renovate's namespaced format)
2. Labels: `major`, `minor`, `patch` (plain format)
3. Labels: `security` (security updates)
4. Title patterns: `(major)`, `(minor)`, `(patch)` in title text
5. Fallback: `unknown`

**Merge status mapping:**
- `✅ Ready` — PR is mergeable
- `⚡ Conflicts` — PR has merge conflicts
- `📝 Draft` — PR is a draft
- `❓ Pending` — mergeable state not yet computed by GitHub

**Requirements:** GitHub CLI (`gh`) must be installed and authenticated. The Renovate PR section is silently skipped if `gh` is not available.

## Limitations

### Chart Version Checking

- **Requires Helm CLI**: Must have `helm` installed and repositories accessible
- **Network access**: Needs to reach Helm repository URLs
- **OCI repositories**: May require authentication for private repos
- **Rate limiting**: Some registries may rate limit requests

### Image Tag Checking

- **Not all registries supported**: Only GHCR, Docker Hub, and Quay.io are fully supported
- **Tag format assumptions**: Assumes semantic versioning or release tags
- **Latest tag ambiguity**: Can't determine if `latest` tag has changed
- **Private registries**: Requires authentication (not implemented)
- **Rate limiting**: Registry APIs may rate limit requests

### Image Extraction

- **Complex value structures**: May miss images in deeply nested or unusual structures
- **Variable substitution**: Doesn't resolve Flux substitutions (e.g., `${SECRET_DOMAIN}`)
- **Conditional images**: May not handle conditional image selection

## Manual Verification

For critical updates, always verify manually:

### Check Chart Versions

```bash
# Add repository
helm repo add <repo-name> <repo-url>
helm repo update

# Search for chart
helm search repo <repo-name>/<chart-name> --versions

# Compare with current version in HelmRelease
```

### Check Image Tags

```bash
# Docker Hub
curl -s "https://hub.docker.com/v2/repositories/<owner>/<image>/tags?page_size=10" | jq

# GHCR (requires GitHub token for private repos)
curl -s -H "Authorization: token <token>" \
  "https://api.github.com/repos/<owner>/<repo>/releases/latest"

# Quay.io
curl -s "https://quay.io/api/v1/repository/<owner>/<image>/tag?limit=10"
```

## Updating Deployments

When updates are available:

1. **Review the update**: Check changelogs and release notes
2. **Test in staging**: If available, test updates in non-production
3. **Update HelmRelease**: 
   - Update `spec.chart.spec.version` for chart updates
   - Update image tags in `spec.values` for image updates
4. **Commit and push**: Let Flux reconcile the changes
5. **Monitor**: Watch for reconciliation and pod restarts

### Example: Updating Chart Version

```yaml
# Before
spec:
  chart:
    spec:
      chart: longhorn
      version: "1.10.1"

# After
spec:
  chart:
    spec:
      chart: longhorn
      version: "1.11.0"  # Updated version
```

### Example: Updating Image Tag

```yaml
# Before
values:
  image:
    repository: ghcr.io/open-webui/open-webui
    tag: v0.6.43

# After
values:
  image:
    repository: ghcr.io/open-webui/open-webui
    tag: v0.6.44  # Updated tag
```

## Automation

### Scheduled Checks

Consider setting up a scheduled job to run version checks:

```bash
# Add to crontab (weekly on Sundays at 2 AM)
0 2 * * 0 cd /home/mu/code/cberg-home-nextgen && python3 runbooks/check-all-versions.py && git add runbooks/version-check-current.md && git commit -m "chore: update version check status" && git push
```

### CI/CD Integration

The version check can be integrated into CI/CD pipelines:
- Run on schedule (e.g., weekly)
- Create issues/PRs for available updates
- Notify on security updates

## Troubleshooting

### "Could not check latest version"

**Possible causes:**
- Network connectivity issues
- Repository URL changed
- Authentication required
- Rate limiting

**Solutions:**
- Check network connectivity
- Verify HelmRepository URLs are correct
- Wait and retry (rate limiting)
- Check repository authentication requirements

### "No container images specified"

**Possible causes:**
- Images defined in valuesFrom (secrets/configmaps)
- Images in sub-charts (not in main values)
- Unusual value structure

**Solutions:**
- Manually check the HelmRelease values
- Check sub-chart documentation
- Inspect deployed pods: `kubectl get pod -n <namespace> <pod> -o jsonpath='{.spec.containers[*].image}'`

### Script errors

**Common issues:**
- Missing Python packages: `pip install pyyaml requests`
- Helm not installed: Install Helm CLI
- YAML parsing errors: Check for malformed YAML files

## Best Practices

1. **Regular checks**: Run version checks weekly or monthly
2. **Review before updating**: Always review changelogs
3. **Test updates**: Test in non-production first when possible
4. **Monitor after updates**: Watch for issues after applying updates
5. **Document decisions**: Note why certain updates are deferred
6. **Security updates**: Prioritize security-related updates
7. **Breaking changes**: Review breaking changes carefully

## Related Documentation

- [Flux HelmRelease Documentation](https://fluxcd.io/docs/components/helm/helmreleases/)
- [Helm Chart Versioning](https://helm.sh/docs/topics/charts/#charts-and-versioning)
- [Container Image Tagging Best Practices](https://docs.docker.com/engine/reference/commandline/tag/)

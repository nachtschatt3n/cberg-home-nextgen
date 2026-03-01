#!/usr/bin/env python3
"""
Documentation health check for Kubernetes homelab cluster.

Runs 8 documentation checks and writes results to runbooks/doc-check-current.md.

Usage:
    python3 runbooks/doc-check.py

Output:
    runbooks/doc-check-current.md
"""

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Colour helpers
# ---------------------------------------------------------------------------

class C:
    RESET  = '\033[0m'
    RED    = '\033[0;31m'
    GREEN  = '\033[0;32m'
    YELLOW = '\033[1;33m'
    BLUE   = '\033[0;34m'
    CYAN   = '\033[0;36m'
    BOLD   = '\033[1m'


def cprint(color: str, msg: str) -> None:
    print(f"{color}{msg}{C.RESET}")


# ---------------------------------------------------------------------------
# Severity constants
# ---------------------------------------------------------------------------

CRITICAL = "🔴"
WARNING  = "🟡"
OK       = "🟢"

# ---------------------------------------------------------------------------
# Repo paths
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).parent.resolve()
REPO_ROOT  = SCRIPT_DIR.parent
OUTPUT     = SCRIPT_DIR / "doc-check-current.md"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def run(cmd: str, timeout: int = 30) -> str:
    """Run a shell command, return stdout (empty string on error)."""
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip()
    except Exception:
        return ""


def run_lines(cmd: str, timeout: int = 30) -> list[str]:
    out = run(cmd, timeout=timeout)
    return [l for l in out.splitlines() if l.strip()]


def read_file(path: Path) -> str:
    """Read file content, return empty string on error."""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Finding tracker
# ---------------------------------------------------------------------------

class Findings:
    def __init__(self):
        self._items: list[tuple[str, str]] = []   # (severity, message)

    def add(self, severity: str, msg: str) -> None:
        self._items.append((severity, msg))

    def worst(self) -> str:
        for sev in (CRITICAL, WARNING):
            if any(s == sev for s, _ in self._items):
                return sev
        return OK

    def markdown(self) -> str:
        if not self._items:
            return f"{OK} No findings\n"
        return "\n".join(f"- {s} {m}" for s, m in self._items) + "\n"

    def count(self, severity: str) -> int:
        return sum(1 for s, _ in self._items if s == severity)

    def summary_cell(self) -> str:
        c = self.count(CRITICAL)
        w = self.count(WARNING)
        parts = []
        if c: parts.append(f"{c} critical")
        if w: parts.append(f"{w} warning")
        return ", ".join(parts) if parts else "clean"


# ---------------------------------------------------------------------------
# App inventory scanner
# ---------------------------------------------------------------------------

def find_helmrelease_apps() -> dict[str, list[str]]:
    """
    Scan kubernetes/apps/ for all app directories containing a HelmRelease.
    Handles both helmrelease.yaml and helm-release.yaml filenames.
    Handles network/ namespace with external/ and internal/ subdirs.
    Skips directories starting with _.
    Returns: {namespace: [app_name, ...]}
    """
    apps_dir = REPO_ROOT / "kubernetes" / "apps"
    result: dict[str, list[str]] = {}

    HR_NAMES = {"helmrelease.yaml", "helm-release.yaml"}

    for ns_dir in sorted(apps_dir.iterdir()):
        if not ns_dir.is_dir() or ns_dir.name.startswith("."):
            continue
        ns = ns_dir.name
        result[ns] = []

        for app_dir in sorted(ns_dir.iterdir()):
            if not app_dir.is_dir() or app_dir.name.startswith("_"):
                continue

            # Standard layout: {ns}/{app}/app/helmrelease.yaml
            app_subdir = app_dir / "app"
            has_hr = app_subdir.is_dir() and any(
                (app_subdir / name).exists() for name in HR_NAMES
            )

            # Also check at top-level of app_dir: {ns}/{app}/helmrelease.yaml
            if not has_hr:
                has_hr = any((app_dir / name).exists() for name in HR_NAMES)

            # Handle 2-level subdirs like network/external/{app}/ or network/internal/{app}/
            if not has_hr:
                for sub in sorted(app_dir.iterdir()):
                    if not sub.is_dir() or sub.name.startswith("_"):
                        continue
                    sub_app = sub / "app"
                    if sub_app.is_dir() and any((sub_app / name).exists() for name in HR_NAMES):
                        # sub is the logical app (e.g., cloudflared)
                        if sub.name not in result[ns]:
                            result[ns].append(sub.name)
                    elif any((sub / name).exists() for name in HR_NAMES):
                        if sub.name not in result[ns]:
                            result[ns].append(sub.name)

            if has_hr:
                result[ns].append(app_dir.name)

    return result


def check_doc_exists(path: Path, f: Findings, label: str) -> str:
    """Check doc file exists and is non-empty. Returns content."""
    if not path.exists():
        f.add(CRITICAL, f"`{path.relative_to(REPO_ROOT)}` is missing — create it")
        cprint(C.RED, f"  {CRITICAL} MISSING: {path.relative_to(REPO_ROOT)}")
        return ""
    content = read_file(path)
    if not content.strip():
        f.add(CRITICAL, f"`{path.relative_to(REPO_ROOT)}` is empty")
        cprint(C.RED, f"  {CRITICAL} EMPTY: {path.relative_to(REPO_ROOT)}")
        return ""
    cprint(C.GREEN, f"  {OK} {label} exists ({len(content.splitlines())} lines)")
    return content


# ---------------------------------------------------------------------------
# Section implementations
# ---------------------------------------------------------------------------

def section_header(n: int, total: int, title: str) -> None:
    cprint(C.BLUE, f"\n[{n}/{total}] {title}")


def s1_infrastructure_docs() -> tuple[str, Findings, str]:
    section_header(1, 8, "Infrastructure Documentation")
    f = Findings()
    lines: list[str] = []

    doc_path = REPO_ROOT / "docs" / "infrastructure.md"
    content = check_doc_exists(doc_path, f, "docs/infrastructure.md")
    if not content:
        return f.worst(), f, f.markdown()

    # Check Kubernetes server version
    k8s_json = run("kubectl version -o json 2>/dev/null", timeout=15)
    k8s_version = ""
    if k8s_json:
        try:
            d = json.loads(k8s_json)
            k8s_version = d.get("serverVersion", {}).get("gitVersion", "")
        except Exception:
            pass

    if k8s_version:
        # Extract major.minor from version (e.g., v1.34.0 → 1.34)
        ver_clean = k8s_version.lstrip("v")
        major_minor = ".".join(ver_clean.split(".")[:2])
        if major_minor not in content and k8s_version not in content:
            f.add(WARNING, f"K8s server version `{k8s_version}` not found in docs/infrastructure.md")
            cprint(C.YELLOW, f"  {WARNING} K8s version {k8s_version} not in doc")
        else:
            cprint(C.GREEN, f"  {OK} K8s version {k8s_version} documented")
    else:
        f.add(WARNING, "Could not determine live K8s server version (cluster unreachable?)")
        cprint(C.YELLOW, f"  {WARNING} Could not check K8s version")

    # Check Talos version (prefer server/cluster version)
    talos_server_out = run("talosctl version 2>/dev/null | grep -A1 'Server:' | grep 'Tag:'", timeout=15)
    if talos_server_out:
        talos_ver = talos_server_out.replace("Tag:", "").strip()
        if talos_ver and talos_ver not in content:
            f.add(WARNING, f"Talos server version `{talos_ver}` not found in docs/infrastructure.md")
            cprint(C.YELLOW, f"  {WARNING} Talos server version {talos_ver} not in doc")
        elif talos_ver:
            cprint(C.GREEN, f"  {OK} Talos server version {talos_ver} documented")
    else:
        # Server unreachable — check README badge as proxy for cluster version
        readme = read_file(REPO_ROOT / "README.md")
        readme_talos_m = re.search(r'Talos-v?([\d.]+)', readme)
        if readme_talos_m:
            badge_ver = readme_talos_m.group(1)
            if badge_ver not in content:
                f.add(WARNING, f"Talos version `v{badge_ver}` (from README badge) not in docs/infrastructure.md")
            else:
                cprint(C.GREEN, f"  {OK} Talos version v{badge_ver} (from README badge) documented")
        else:
            cprint(C.CYAN, "  Talos server unreachable and no README badge found — skipping Talos version check")

    # Check node names
    nodes_out = run("kubectl get nodes -o jsonpath='{.items[*].metadata.name}' 2>/dev/null", timeout=15)
    if nodes_out:
        node_names = nodes_out.split()
        for node in node_names:
            if node not in content:
                f.add(WARNING, f"Node `{node}` not found in docs/infrastructure.md")
                cprint(C.YELLOW, f"  {WARNING} Node {node} not in doc")
            else:
                cprint(C.GREEN, f"  {OK} Node {node} documented")
    else:
        cprint(C.YELLOW, f"  {WARNING} Could not check live node names")

    # Check key IPs
    for label, ip in [("Mac Mini/Ollama", "192.168.30.111"), ("NAS", "192.168.31.230")]:
        if ip not in content:
            f.add(WARNING, f"{label} IP `{ip}` not found in docs/infrastructure.md")
            cprint(C.YELLOW, f"  {WARNING} {label} IP {ip} not in doc")
        else:
            cprint(C.GREEN, f"  {OK} {label} IP {ip} documented")

    # Check bootstrap chart versions match helmfile.yaml
    helmfile = read_file(REPO_ROOT / "kubernetes" / "bootstrap" / "apps" / "helmfile.yaml")
    if helmfile:
        # Parse only the releases: section to avoid mixing repository names with versions
        releases_m = re.search(r'^releases:\n(.*)', helmfile, re.MULTILINE | re.DOTALL)
        releases_text = releases_m.group(1) if releases_m else ""
        bootstrap_versions: dict[str, str] = {}
        for block in re.split(r'^\s*-\s*name:', releases_text, flags=re.MULTILINE):
            name_m = re.match(r'\s*(\S+)', block)
            ver_m2 = re.search(r'^\s*version:\s*(\S+)', block, re.MULTILINE)
            if name_m and ver_m2:
                bootstrap_versions[name_m.group(1)] = ver_m2.group(1)
        for chart, ver in bootstrap_versions.items():
            ver_clean = ver.lstrip("v")
            if ver_clean not in content and ver not in content:
                f.add(WARNING, f"Bootstrap chart `{chart}` version `{ver}` not in docs/infrastructure.md")
                cprint(C.YELLOW, f"  {WARNING} Bootstrap {chart} v{ver} not documented")
            else:
                cprint(C.GREEN, f"  {OK} Bootstrap {chart} v{ver} documented")
    else:
        cprint(C.CYAN, "  kubernetes/bootstrap/apps/helmfile.yaml not found — skipping bootstrap version check")

    lines.append(f.markdown())
    return f.worst(), f, "\n".join(lines)


def s2_network_docs() -> tuple[str, Findings, str]:
    section_header(2, 8, "Network Documentation")
    f = Findings()
    lines: list[str] = []

    doc_path = REPO_ROOT / "docs" / "network.md"
    content = check_doc_exists(doc_path, f, "docs/network.md")
    if not content:
        return f.worst(), f, f.markdown()

    # Parse documented VLAN IDs from the table
    documented_vlan_ids = set(re.findall(r'^\|\s*(\d+)\s*\|', content, re.MULTILINE))
    cprint(C.CYAN, f"  Documented VLANs: {sorted(documented_vlan_ids)}")

    # Fetch live VLANs from UniFi
    live_vlan_raw = run("unifictl local network list -o json 2>/dev/null", timeout=15)
    if live_vlan_raw and (live_vlan_raw.startswith("[") or live_vlan_raw.startswith("{")):
        try:
            parsed = json.loads(live_vlan_raw)
            networks = parsed.get("data", parsed) if isinstance(parsed, dict) else parsed
            live_vlan_ids = set()
            for net in networks:
                vid = net.get("vlan_id") or net.get("vlan")
                if vid and str(vid) != "0":
                    live_vlan_ids.add(str(vid))

            cprint(C.CYAN, f"  Live VLANs: {sorted(live_vlan_ids)}")

            missing_from_doc = live_vlan_ids - documented_vlan_ids
            for vid in sorted(missing_from_doc):
                f.add(WARNING, f"Live VLAN `{vid}` not found in docs/network.md VLAN table")
                cprint(C.YELLOW, f"  {WARNING} Live VLAN {vid} not documented")

            # Bidirectional: documented VLANs that don't exist live (stale docs)
            # VLAN 1 is the default untagged management network; the UniFi API omits it by design.
            VLAN_API_OMITTED = {"1"}
            missing_from_live = documented_vlan_ids - live_vlan_ids - VLAN_API_OMITTED
            for vid in sorted(missing_from_live):
                f.add(WARNING, f"Documented VLAN `{vid}` not found in live UniFi config — stale doc?")
                cprint(C.YELLOW, f"  {WARNING} VLAN {vid} in doc but not live")

            if not missing_from_doc and not missing_from_live:
                cprint(C.GREEN, f"  {OK} All {len(live_vlan_ids)} live VLANs documented (bidirectional)")
            lines.append(f"Live VLANs: {sorted(live_vlan_ids)}\n")
        except Exception as e:
            f.add(WARNING, f"Could not parse UniFi networks response: {e}")
            cprint(C.YELLOW, f"  {WARNING} Could not parse UniFi networks JSON")
    else:
        f.add(WARNING, "Could not fetch live VLAN data from `unifictl local network list` — verify unifictl is configured")
        cprint(C.YELLOW, f"  {WARNING} unifictl not available or not configured — skipping live VLAN check")
        lines.append("Live VLAN check: skipped (unifictl unavailable)\n")

    # Fetch live WiFi SSIDs from UniFi
    live_wlan_raw = run("unifictl local wlan list -o json 2>/dev/null", timeout=15)
    if live_wlan_raw and (live_wlan_raw.startswith("[") or live_wlan_raw.startswith("{")):
        try:
            wlans = json.loads(live_wlan_raw)
            if isinstance(wlans, dict):
                wlans = wlans.get("data", [])
            live_ssids = [w.get("name", "") for w in wlans if w.get("name")]
            cprint(C.CYAN, f"  Live SSIDs: {live_ssids}")

            for ssid in live_ssids:
                if ssid not in content:
                    f.add(WARNING, f"Live WiFi SSID `{ssid}` not found in docs/network.md")
                    cprint(C.YELLOW, f"  {WARNING} SSID {ssid} not in doc")
                else:
                    cprint(C.GREEN, f"  {OK} SSID {ssid} documented")
            lines.append(f"Live SSIDs: {live_ssids}\n")
        except Exception:
            cprint(C.YELLOW, f"  {WARNING} Could not parse UniFi wlans response")
    else:
        cprint(C.YELLOW, "  Skipping live SSID check (unifictl unavailable)")

    # Check mDNS section
    expected_mdns = ["Trusted", "Servers", "Trusted-Devices", "IoT", "k8s-network"]
    mdns_section = re.search(r'mDNS.*?(?=---|\Z)', content, re.DOTALL | re.IGNORECASE)
    if mdns_section:
        mdns_text = mdns_section.group()
        for vlan_name in expected_mdns:
            if vlan_name not in mdns_text:
                f.add(WARNING, f"mDNS VLAN `{vlan_name}` not mentioned in docs/network.md mDNS section")
    else:
        f.add(WARNING, "mDNS section not found in docs/network.md")

    # Check physical topology key devices
    expected_devices = ["DMP-CBERG", "Basement-SW-48", "192.168.30.118"]
    for device in expected_devices:
        if device not in content:
            f.add(WARNING, f"Physical device `{device}` not mentioned in docs/network.md")
            cprint(C.YELLOW, f"  {WARNING} Device {device} not in doc")

    lines.append(f.markdown())
    return f.worst(), f, "\n".join(lines)


def s3_application_docs() -> tuple[str, Findings, str]:
    section_header(3, 8, "Application Documentation")
    f = Findings()
    lines: list[str] = []

    doc_path = REPO_ROOT / "docs" / "applications.md"
    content = check_doc_exists(doc_path, f, "docs/applications.md")
    if not content:
        return f.worst(), f, f.markdown()

    # Get all deployed apps from cluster
    cluster_apps = find_helmrelease_apps()
    total_cluster = sum(len(apps) for apps in cluster_apps.values())
    cprint(C.CYAN, f"  Total HelmRelease apps found: {total_cluster}")
    lines.append(f"Apps in cluster: **{total_cluster}**\n")

    # Infrastructure apps that are intentionally not listed in applications.md
    INFRA_SKIP = {
        "cilium", "coredns", "csi-driver-smb", "descheduler", "intel-device-plugin",
        "metrics-server", "node-feature-discovery", "reloader", "spegel",
        "eck-operator", "elasticsearch-bootstrap", "echo-server", "flux-operator",
        "cert-manager", "_template", "mosquitto", "otbr", "matter-server",
    }

    undocumented = []
    for ns, apps in cluster_apps.items():
        for app in apps:
            if app in INFRA_SKIP:
                continue
            # Check if app name (or normalized form) appears in the doc
            app_lower = app.lower()
            app_nohyphen = app_lower.replace("-", "")
            # Check various forms: exact, without hyphens, name part only
            app_words = app_lower.replace("-", " ")
            found = (
                app_lower in content.lower()
                or app_nohyphen in content.lower().replace("-", "").replace(" ", "")
                or any(word in content.lower() for word in app_words.split() if len(word) > 4)
            )
            if not found:
                undocumented.append(f"{ns}/{app}")
                f.add(WARNING, f"App `{ns}/{app}` not found in docs/applications.md")
                cprint(C.YELLOW, f"  {WARNING} Undocumented: {ns}/{app}")

    if not undocumented:
        cprint(C.GREEN, f"  {OK} All cluster apps appear documented (or are infra-only)")
    else:
        cprint(C.YELLOW, f"  {WARNING} {len(undocumented)} potentially undocumented apps")

    lines.append(f"Undocumented apps: **{len(undocumented)}**\n")
    if undocumented:
        lines.append("Undocumented:\n" + "\n".join(f"- `{a}`" for a in undocumented[:20]) + "\n")

    # Check namespace sections exist in the doc
    expected_namespaces = [
        "ai", "home-automation", "databases", "monitoring", "office",
        "media", "download", "kube-system", "storage",
    ]
    for ns in expected_namespaces:
        ns_display = ns.replace("-", " ").title()
        if ns not in content.lower() and ns_display.lower() not in content.lower():
            f.add(WARNING, f"No section for namespace `{ns}` in docs/applications.md")

    lines.append(f.markdown())
    return f.worst(), f, "\n".join(lines)


def s4_security_docs() -> tuple[str, Findings, str]:
    section_header(4, 8, "Security Documentation")
    f = Findings()
    lines: list[str] = []

    doc_path = REPO_ROOT / "docs" / "security.md"
    content = check_doc_exists(doc_path, f, "docs/security.md")
    if not content:
        return f.worst(), f, f.markdown()

    # Check age key consistency: .sops.yaml ↔ docs/security.md
    sops_yaml = read_file(REPO_ROOT / ".sops.yaml")
    sops_key_m = re.search(r'age1[a-z0-9]+', sops_yaml)
    doc_key_m  = re.search(r'age1[a-z0-9]+', content)

    if sops_key_m and doc_key_m:
        sops_key = sops_key_m.group()
        doc_key  = doc_key_m.group()
        if sops_key != doc_key:
            f.add(CRITICAL, f"Age key mismatch: `.sops.yaml` has `{sops_key[:20]}...` "
                            f"but docs/security.md has `{doc_key[:20]}...`")
            cprint(C.RED, f"  {CRITICAL} Age key MISMATCH between .sops.yaml and docs/security.md")
        else:
            cprint(C.GREEN, f"  {OK} Age key consistent: {sops_key[:20]}...")
    elif sops_key_m and not doc_key_m:
        f.add(CRITICAL, "Age key from `.sops.yaml` not found in docs/security.md")
        cprint(C.RED, f"  {CRITICAL} Age key missing from docs/security.md")
    else:
        f.add(WARNING, "Could not extract age key from `.sops.yaml` for comparison")

    # Check Authentik blueprint workflow documented
    if "blueprint" not in content.lower():
        f.add(WARNING, "Authentik blueprint workflow not documented in docs/security.md")
        cprint(C.YELLOW, f"  {WARNING} Blueprint workflow missing from security doc")
    else:
        cprint(C.GREEN, f"  {OK} Authentik blueprint workflow documented")

    if "configmap.sops.yaml" not in content:
        f.add(WARNING, "Authentik ConfigMap SOPS reference missing from docs/security.md")

    # Check cert-manager and Let's Encrypt
    for term in ["cert-manager", "Let's Encrypt"]:
        if term.lower() not in content.lower():
            f.add(WARNING, f"`{term}` not mentioned in docs/security.md")
            cprint(C.YELLOW, f"  {WARNING} {term} not documented")
        else:
            cprint(C.GREEN, f"  {OK} {term} documented")

    # Check SOPS workflow documented
    if "sops -e -i" not in content and "sops --encrypt" not in content:
        f.add(WARNING, "SOPS encrypt workflow (`sops -e -i`) not in docs/security.md — check docs/sops/sops-encryption.md")
    else:
        cprint(C.GREEN, f"  {OK} SOPS encryption workflow documented")

    # Check Authentik blueprint files don't use flow slugs (should use UUIDs)
    blueprint_files = list((REPO_ROOT / "kubernetes" / "apps").rglob("authentik-blueprint.yaml"))
    KNOWN_FLOW_UUIDS = {"0cdf1b8c", "b8a97e00", "162f6c4f"}
    slug_violations: list[str] = []
    for bp in blueprint_files:
        bp_content = read_file(bp)
        # Check authorization_flow and invalidation_flow values for slug strings
        for m in re.finditer(r'(authorization_flow|invalidation_flow|service_connection):\s*"([^"]+)"', bp_content):
            val = m.group(2)
            # UUIDs contain hyphens and are 36 chars; slugs are hyphenated words
            is_uuid = re.match(r'^[0-9a-f]{8}-[0-9a-f]{4}-', val)
            if not is_uuid:
                slug_violations.append(f"`{bp.relative_to(REPO_ROOT)}`: {m.group(1)} uses slug `{val}`")

    if slug_violations:
        for v in slug_violations:
            f.add(CRITICAL, f"Authentik blueprint uses slug instead of UUID — {v}")
            cprint(C.RED, f"  {CRITICAL} {v}")
    elif blueprint_files:
        cprint(C.GREEN, f"  {OK} {len(blueprint_files)} Authentik blueprint(s) use UUIDs (no slug references)")
    else:
        cprint(C.CYAN, "  No unencrypted authentik-blueprint.yaml files found")

    # Check Flux sops-age secret exists and contains the correct key
    flux_secret = run("kubectl get secret sops-age -n flux-system -o jsonpath='{.data.age\\.agekey}' 2>/dev/null", timeout=15)
    if flux_secret:
        try:
            import base64
            decoded = base64.b64decode(flux_secret).decode().strip()
            # Derive public key from the stored private key using age-keygen -y
            derived_pub = run(f"echo '{decoded}' | age-keygen -y 2>/dev/null", timeout=5).strip()
            if sops_key_m and derived_pub == sops_key_m.group():
                cprint(C.GREEN, f"  {OK} Flux sops-age secret matches .sops.yaml public key")
            elif sops_key_m and derived_pub:
                f.add(CRITICAL, "Flux `sops-age` secret public key does NOT match `.sops.yaml` — cluster decryption will fail")
                cprint(C.RED, f"  {CRITICAL} Flux sops-age secret has WRONG key")
            elif decoded.startswith("AGE-SECRET-KEY"):
                cprint(C.GREEN, f"  {OK} Flux sops-age secret exists and has valid format (key match skipped)")
            else:
                f.add(WARNING, "Flux `sops-age` secret has unexpected format")
        except Exception:
            cprint(C.CYAN, "  Could not decode sops-age secret")
    else:
        f.add(WARNING, "Flux `sops-age` secret not found in `flux-system` — SOPS decryption will fail")
        cprint(C.YELLOW, f"  {WARNING} Flux sops-age secret missing from flux-system")

    # Check no .sops.yaml files exist outside kubernetes/ or talos/
    stray_sops = [
        p for p in REPO_ROOT.rglob("*.sops.yaml")
        if p.name != ".sops.yaml"  # exclude the SOPS config file itself
        and not any(part in ("kubernetes", "talos") for part in p.relative_to(REPO_ROOT).parts)
    ]
    if stray_sops:
        for p in stray_sops:
            f.add(WARNING, f"SOPS file outside kubernetes/talos paths: `{p.relative_to(REPO_ROOT)}`")
            cprint(C.YELLOW, f"  {WARNING} Stray SOPS file: {p.relative_to(REPO_ROOT)}")
    else:
        cprint(C.GREEN, f"  {OK} All .sops.yaml files are within kubernetes/ or talos/")

    lines.append(f.markdown())
    return f.worst(), f, "\n".join(lines)


def s5_integration_docs() -> tuple[str, Findings, str]:
    section_header(5, 8, "Integration Documentation")
    f = Findings()
    lines: list[str] = []

    doc_path = REPO_ROOT / "docs" / "integration.md"
    content = check_doc_exists(doc_path, f, "docs/integration.md")
    if not content:
        return f.worst(), f, f.markdown()

    # Check Ollama endpoint ports documented
    ollama_ports = {"11434": "Voice", "11435": "Reason", "11436": "Vision"}
    ollama_host = "192.168.30.111"
    for port, role in ollama_ports.items():
        pattern = f"{ollama_host}:{port}"
        if pattern not in content:
            f.add(WARNING, f"Ollama {role} endpoint `{pattern}` not in docs/integration.md")
            cprint(C.YELLOW, f"  {WARNING} Ollama {role} endpoint not documented")
        else:
            cprint(C.GREEN, f"  {OK} Ollama {role} ({pattern}) documented")

    # Check Homepage groups in helmrelease match integration doc
    hr_path = REPO_ROOT / "kubernetes" / "apps" / "default" / "homepage" / "app" / "helmrelease.yaml"
    hr_content = read_file(hr_path)

    # Extract group names ONLY from the services: section (not bookmarks or widgets)
    # Find the services: block — everything between "services:" and the next same-level key
    services_m = re.search(r'      services:\n((?:        .*\n|.*\n)*?)(?=      \w|\Z)', hr_content)
    if services_m:
        services_section = services_m.group(1)
        # Groups are 8-space indented list items at the top of each group block
        hr_groups_raw = re.findall(r'^\s{8}-\s+"?([^":{\n]+)"?:', services_section, re.MULTILINE)
        hr_groups = [g.strip() for g in hr_groups_raw
                     if g.strip() and len(g.strip()) > 2 and len(g.strip()) < 40]
    else:
        hr_groups = []

    if hr_groups:
        for group in hr_groups:
            if group not in content:
                f.add(WARNING, f"Homepage group `{group}` (from helmrelease) not in docs/integration.md")
                cprint(C.YELLOW, f"  {WARNING} Homepage group '{group}' not documented")

    # Check Renovate schedule documented
    renovate_path = REPO_ROOT / ".github" / "renovate.json5"
    renovate_content = read_file(renovate_path)
    schedule_m = re.search(r'"schedule":\s*\[.*?"([^"]+)"', renovate_content, re.DOTALL)
    if schedule_m:
        schedule = schedule_m.group(1)
        cprint(C.CYAN, f"  Renovate schedule: {schedule}")
        if schedule not in content and "every weekend" not in content.lower():
            f.add(WARNING, f"Renovate schedule `{schedule}` not in docs/integration.md")
        else:
            cprint(C.GREEN, f"  {OK} Renovate schedule documented")

    # Check Flux GitOps section exists
    if "flux" not in content.lower():
        f.add(WARNING, "Flux GitOps integration not documented in docs/integration.md")

    # Check Ollama model name format in app configs (should use colon: gpt-oss:20b, not slash)
    ollama_apps = [
        REPO_ROOT / "kubernetes" / "apps" / "office" / "paperless-ai" / "app" / "helmrelease.yaml",
        REPO_ROOT / "kubernetes" / "apps" / "office" / "paperless-gpt" / "app" / "helmrelease.yaml",
        REPO_ROOT / "kubernetes" / "apps" / "home-automation" / "frigate-nvr" / "app" / "helmrelease.yaml",
    ]
    bad_model_format: list[str] = []
    for app_path in ollama_apps:
        if not app_path.exists():
            continue
        app_content = read_file(app_path)
        # Slash-format model names like "openai/gpt-oss-20b" would be wrong
        for m in re.finditer(r'(?:LLM_MODEL|OLLAMA_MODEL|CUSTOM_MODEL|VISION_LLM_MODEL):\s*"([^"]+)"', app_content):
            model = m.group(1)
            if "/" in model:
                bad_model_format.append(f"`{app_path.parent.parent.name}`: model `{model}` uses slash format")

    if bad_model_format:
        for issue in bad_model_format:
            f.add(WARNING, f"Ollama model uses slash format (should be `name:tag`) — {issue}")
            cprint(C.YELLOW, f"  {WARNING} {issue}")
    else:
        cprint(C.GREEN, f"  {OK} Ollama model name formats are correct (colon separator)")

    # Check Homepage ingress annotations: both annotation AND label must have enabled=true
    ingress_raw = run(
        "kubectl get ingress -A -o json 2>/dev/null", timeout=20
    )
    if ingress_raw:
        try:
            ingresses = json.loads(ingress_raw).get("items", [])
            annotation_only: list[str] = []
            for ing in ingresses:
                ns = ing["metadata"]["namespace"]
                name = ing["metadata"]["name"]
                annotations = ing["metadata"].get("annotations", {})
                labels = ing["metadata"].get("labels", {})
                ann_enabled = annotations.get("gethomepage.dev/enabled", "")
                lbl_enabled = labels.get("gethomepage.dev/enabled", "")
                if ann_enabled == "true" and lbl_enabled != "true":
                    annotation_only.append(f"{ns}/{name}")
            if annotation_only:
                for ing_name in annotation_only[:5]:
                    f.add(WARNING, f"Ingress `{ing_name}` has Homepage annotation but missing label — won't appear in dashboard")
                    cprint(C.YELLOW, f"  {WARNING} {ing_name}: annotation ✓ but label missing")
                if len(annotation_only) > 5:
                    cprint(C.YELLOW, f"  {WARNING} ... and {len(annotation_only) - 5} more")
            else:
                homepage_enabled = [i for i in ingresses
                                    if i["metadata"].get("annotations", {}).get("gethomepage.dev/enabled") == "true"]
                if homepage_enabled:
                    cprint(C.GREEN, f"  {OK} All {len(homepage_enabled)} Homepage-enabled ingresses have matching label")
        except Exception as e:
            cprint(C.CYAN, f"  Could not parse ingress list: {e}")

    lines.append(f.markdown())
    return f.worst(), f, "\n".join(lines)


def s6_readme_claude_currency() -> tuple[str, Findings, str]:
    section_header(6, 8, "README & CLAUDE.md Currency")
    f = Findings()
    lines: list[str] = []

    readme = read_file(REPO_ROOT / "README.md")

    if not readme:
        f.add(CRITICAL, "README.md is missing or empty")
        return f.worst(), f, f.markdown()

    # Check README version badges vs live versions
    readme_k8s_m = re.search(r'Kubernetes-v?([\d.]+)', readme)
    readme_talos_m = re.search(r'Talos-v?([\d.]+)', readme)

    k8s_json = run("kubectl version -o json 2>/dev/null", timeout=15)
    if k8s_json:
        try:
            d = json.loads(k8s_json)
            server_ver = d.get("serverVersion", {}).get("gitVersion", "").lstrip("v")
            if server_ver and readme_k8s_m:
                badge_ver = readme_k8s_m.group(1)
                badge_major_minor = ".".join(badge_ver.split(".")[:2])
                server_major_minor = ".".join(server_ver.split(".")[:2])
                if badge_major_minor != server_major_minor:
                    f.add(WARNING, f"README K8s badge `v{badge_ver}` may be outdated (server: `v{server_ver}`)")
                    cprint(C.YELLOW, f"  {WARNING} README K8s badge {badge_ver} vs server {server_ver}")
                else:
                    cprint(C.GREEN, f"  {OK} README K8s badge matches server ({server_ver})")
        except Exception:
            pass

    # Check Talos badge against server version (if reachable)
    talos_server_out = run("talosctl version 2>/dev/null | grep -A1 'Server:' | grep 'Tag:'", timeout=15)
    if talos_server_out and readme_talos_m:
        talos_ver = talos_server_out.replace("Tag:", "").strip().lstrip("v")
        badge_ver = readme_talos_m.group(1)
        if talos_ver and ".".join(talos_ver.split(".")[:2]) != ".".join(badge_ver.split(".")[:2]):
            f.add(WARNING, f"README Talos badge `v{badge_ver}` may be outdated (server: `v{talos_ver}`)")
            cprint(C.YELLOW, f"  {WARNING} README Talos badge {badge_ver} vs server {talos_ver}")
        elif talos_ver:
            cprint(C.GREEN, f"  {OK} README Talos badge matches server ({talos_ver})")
    elif readme_talos_m:
        cprint(C.CYAN, f"  Talos server unreachable — badge shows v{readme_talos_m.group(1)} (cannot verify against server)")

    # Check README covers major application categories
    expected_sections = [
        ("Home Automation", ["Home Automation", "🏠"]),
        ("AI", ["AI", "Machine Learning", "🤖"]),
        ("Databases", ["Databases", "🗄️"]),
        ("Monitoring", ["Monitoring", "📊"]),
        ("Office", ["Office", "Productivity", "📄"]),
    ]
    for category, keywords in expected_sections:
        if not any(kw in readme for kw in keywords):
            f.add(WARNING, f"README missing section for `{category}`")
        else:
            cprint(C.GREEN, f"  {OK} README has {category} section")

    # Check AGENTS.md (canonical) age key matches .sops.yaml
    # CLAUDE.md should be a symlink to AGENTS.md
    sops_yaml = read_file(REPO_ROOT / ".sops.yaml")
    sops_key_m = re.search(r'age1[a-z0-9]+', sops_yaml)
    sops_key = sops_key_m.group() if sops_key_m else None

    agents_path = REPO_ROOT / "AGENTS.md"
    claude_path = REPO_ROOT / "CLAUDE.md"

    # Verify CLAUDE.md is a symlink to AGENTS.md
    if claude_path.exists():
        if claude_path.is_symlink():
            target = claude_path.resolve()
            if target == agents_path.resolve():
                cprint(C.GREEN, f"  {OK} CLAUDE.md is a symlink → AGENTS.md")
            else:
                f.add(WARNING, f"CLAUDE.md is a symlink but points to `{target.name}`, not AGENTS.md")
                cprint(C.YELLOW, f"  {WARNING} CLAUDE.md symlink points to wrong target")
        else:
            f.add(WARNING, "CLAUDE.md is not a symlink — should be `ln -sf AGENTS.md CLAUDE.md`")
            cprint(C.YELLOW, f"  {WARNING} CLAUDE.md is not a symlink to AGENTS.md")
    else:
        f.add(WARNING, "CLAUDE.md missing — create with `ln -sf AGENTS.md CLAUDE.md`")
        cprint(C.YELLOW, f"  {WARNING} CLAUDE.md missing")

    # Check AGENTS.md age key (authoritative source)
    if agents_path.exists():
        agents_content = read_file(agents_path)
        agents_key_m = re.search(r'age1[a-z0-9]+', agents_content)
        if sops_key and agents_key_m:
            agents_key = agents_key_m.group()
            if sops_key != agents_key:
                f.add(CRITICAL, f"Age key in AGENTS.md (`{agents_key[:20]}...`) "
                                f"doesn't match `.sops.yaml` (`{sops_key[:20]}...`)")
                cprint(C.RED, f"  {CRITICAL} Age key MISMATCH in AGENTS.md vs .sops.yaml")
            else:
                cprint(C.GREEN, f"  {OK} Age key in AGENTS.md matches .sops.yaml")
        elif sops_key and not agents_key_m:
            f.add(WARNING, "Age key not found in AGENTS.md — should document the public key")
            cprint(C.YELLOW, f"  {WARNING} Age key not in AGENTS.md")

    lines.append(f.markdown())
    return f.worst(), f, "\n".join(lines)


def s7_coding_guidelines() -> tuple[str, Findings, str]:
    section_header(7, 8, "Coding Guidelines & Rules")
    f = Findings()
    lines: list[str] = []

    claude = read_file(REPO_ROOT / "CLAUDE.md")

    # Check required tools are in PATH
    required_tools = ["task", "kubeconform", "talhelper", "kubectl", "sops", "flux", "talosctl"]
    tool_status = []
    for tool in required_tools:
        path = run(f"which {tool} 2>/dev/null", timeout=5)
        if path:
            cprint(C.GREEN, f"  {OK} {tool}: {path}")
            tool_status.append(f"- {OK} `{tool}`: `{path}`")
        else:
            f.add(WARNING, f"Tool `{tool}` referenced in CLAUDE.md but not found in PATH")
            cprint(C.YELLOW, f"  {WARNING} {tool}: NOT FOUND")
            tool_status.append(f"- {WARNING} `{tool}`: not found")

    lines.append("**Tool availability:**\n" + "\n".join(tool_status) + "\n")

    # Extract task references from CLAUDE.md
    task_refs = re.findall(r'`task ([\w:]+)`', claude)
    # These task names may appear in docs but aren't standalone tasks (aliases, composed, etc.)
    TASK_DOC_ONLY = {"test", "upgrade", "reset"}
    if task_refs:
        # Build list of defined tasks from Taskfile.yaml and .taskfiles/
        defined_tasks: set[str] = set()
        taskfile_content = read_file(REPO_ROOT / "Taskfile.yaml")
        # Match task definitions: "  taskname:" at 2-space indent
        defined_tasks.update(re.findall(r'^  ([\w:]+):', taskfile_content, re.MULTILINE))

        taskfiles_dir = REPO_ROOT / ".taskfiles"
        if taskfiles_dir.is_dir():
            for tf in taskfiles_dir.rglob("*.yaml"):
                tf_content = read_file(tf)
                defined_tasks.update(re.findall(r'^  ([\w:]+):', tf_content, re.MULTILINE))

        # Also accept namespace:task format by checking both parts
        for task_ref in set(task_refs):
            if task_ref in TASK_DOC_ONLY:
                continue
            if ":" in task_ref:
                # Namespace:task — check if task name exists anywhere (harder to verify statically)
                task_part = task_ref.split(":")[-1]
                if task_part in defined_tasks or task_ref in defined_tasks:
                    cprint(C.GREEN, f"  {OK} Task '{task_ref}' found")
            elif task_ref not in defined_tasks:
                f.add(WARNING, f"Task `{task_ref}` referenced in CLAUDE.md but not found in Taskfile")
                cprint(C.YELLOW, f"  {WARNING} Task '{task_ref}' not in Taskfile")

    # Check SOP template and compliance
    sops_dir = REPO_ROOT / "docs" / "sops"
    template_path = sops_dir / "SOP-TEMPLATE.md"
    REQUIRED_SOP_SECTIONS = [
        "Description", "Overview", "Blueprints", "Operational Instructions",
        "Examples", "Verification Tests", "Troubleshooting", "Diagnose Examples",
        "Health Check", "Security Check", "Rollback Plan",
    ]

    sop_status = []
    if not template_path.exists():
        f.add(WARNING, "SOP template `docs/sops/SOP-TEMPLATE.md` is missing")
        cprint(C.YELLOW, f"  {WARNING} docs/sops/SOP-TEMPLATE.md MISSING")
        sop_status.append(f"- {WARNING} `docs/sops/SOP-TEMPLATE.md` missing")
    else:
        cprint(C.GREEN, f"  {OK} docs/sops/SOP-TEMPLATE.md exists")
        sop_status.append(f"- {OK} `docs/sops/SOP-TEMPLATE.md`")

    # Dynamically discover all SOPs (any .md not the template)
    discovered_sops = sorted(p for p in sops_dir.glob("*.md") if p.name != "SOP-TEMPLATE.md")
    for sop_path in discovered_sops:
        rel = f"docs/sops/{sop_path.name}"
        content = read_file(sop_path)

        # Extract ## headings, strip optional "N) " numbering prefix
        headings = []
        for line in content.splitlines():
            m = re.match(r'^##\s+(?:\d+\)\s+)?(.+)$', line)
            if m:
                headings.append(m.group(1).strip())

        # Check required sections
        missing_sections = [
            s for s in REQUIRED_SOP_SECTIONS
            if not any(s.lower() in h.lower() for h in headings)
        ]

        # Check version header (must be YYYY.MM.DD, not placeholder)
        header_area = "\n".join(content.splitlines()[:15])
        ver_m = re.search(r'^> Version:\s*`(\d{4}\.\d{2}\.\d{2})`', header_area, re.MULTILINE)
        has_ver = bool(ver_m)
        ver_present = "> Version:" in header_area

        if missing_sections or not has_ver:
            issues = []
            if missing_sections:
                issues.append(f"missing sections: {', '.join(missing_sections)}")
            if not ver_present:
                issues.append("missing `> Version:` header")
            elif not has_ver:
                issues.append("invalid version format (expected `YYYY.MM.DD`)")
            for issue in issues:
                f.add(WARNING, f"SOP `{rel}` — {issue}")
            cprint(C.YELLOW, f"  {WARNING} {sop_path.name}: {'; '.join(issues)}")
            sop_status.append(f"- {WARNING} `{rel}`: {'; '.join(issues)}")
        else:
            cprint(C.GREEN, f"  {OK} {sop_path.name}: compliant ({ver_m.group(1)})")
            sop_status.append(f"- {OK} `{rel}`: v{ver_m.group(1)}, all sections present")

    lines.append("\n**SOP compliance:**\n" + "\n".join(sop_status) + "\n")

    # Check kubernetes/ paths referenced in SOPs actually exist in repo
    sop_path_issues: list[str] = []
    for sop_path in discovered_sops:
        sop_content = read_file(sop_path)
        refs = re.findall(r'`(kubernetes/[^`\s]+)`', sop_content)
        for ref in refs:
            ref_path = REPO_ROOT / ref
            # Only check directory-level paths (skip files with wildcards or placeholders)
            if "{" in ref or "*" in ref:
                continue
            if not ref_path.exists():
                sop_path_issues.append(f"`{sop_path.name}` references non-existent path `{ref}`")

    if sop_path_issues:
        for issue in sop_path_issues[:5]:
            f.add(WARNING, f"SOP path reference broken — {issue}")
            cprint(C.YELLOW, f"  {WARNING} Broken path: {issue}")
    else:
        cprint(C.GREEN, f"  {OK} All SOP kubernetes/ path references exist")
    lines.append(f.markdown())
    return f.worst(), f, "\n".join(lines)


def s8_runbook_coverage() -> tuple[str, Findings, str]:
    section_header(8, 8, "Runbook Coverage")
    f = Findings()
    lines: list[str] = []

    runbooks_dir = REPO_ROOT / "runbooks"
    import time as _time
    now = _time.time()
    STALE_DAYS = 7
    DOCS_STALE_DAYS = 90
    SOPS_STALE_DAYS = 180

    # Check *-current.md file ages
    output_files = sorted(runbooks_dir.glob("*-current.md"))
    lines.append("**Runbook output freshness:**\n")
    for output_file in output_files:
        try:
            age_days = (now - output_file.stat().st_mtime) / 86400
            if age_days > STALE_DAYS:
                f.add(WARNING, f"`{output_file.name}` is {age_days:.0f} days old (threshold: {STALE_DAYS}d) — rerun the corresponding script")
                cprint(C.YELLOW, f"  {WARNING} {output_file.name}: {age_days:.0f}d old (stale)")
                lines.append(f"- {WARNING} `{output_file.name}`: {age_days:.0f}d old\n")
            else:
                cprint(C.GREEN, f"  {OK} {output_file.name}: {age_days:.1f}d old")
                lines.append(f"- {OK} `{output_file.name}`: {age_days:.1f}d old\n")
        except Exception:
            pass

    # Check runbook-script pairings
    lines.append("\n**Runbook-script pairs:**\n")
    special_pairs: dict[str, list[str]] = {
        "version-check": ["check-all-versions.py", "check-versions.sh", "extract-current-versions.sh"],
        "health-check": [],   # AI-driven procedure, no script required
        "doc-check": ["doc-check.py"],
        "security-check": ["security-check.py"],
    }
    md_runbooks = [f for f in sorted(runbooks_dir.glob("*.md"))
                   if not f.name.endswith("-current.md")]
    for runbook in md_runbooks:
        stem = runbook.stem
        if stem in special_pairs:
            expected_scripts = special_pairs[stem]
            if not expected_scripts:
                cprint(C.GREEN, f"  {OK} {runbook.name}: procedure-only (expected)")
                lines.append(f"- {OK} `{runbook.name}`: procedure-only\n")
                continue
            missing = [s for s in expected_scripts if not (runbooks_dir / s).exists()]
            if missing:
                f.add(WARNING, f"Runbook `{runbook.name}` references missing scripts: {missing}")
                lines.append(f"- {WARNING} `{runbook.name}`: missing {missing}\n")
            else:
                found = [s for s in expected_scripts if (runbooks_dir / s).exists()]
                cprint(C.GREEN, f"  {OK} {runbook.name}: has {found[0]}")
                lines.append(f"- {OK} `{runbook.name}`: paired with script\n")
        else:
            has_py = (runbooks_dir / f"{stem}.py").exists()
            has_sh = (runbooks_dir / f"{stem}.sh").exists()
            if has_py or has_sh:
                script = f"{stem}.py" if has_py else f"{stem}.sh"
                cprint(C.GREEN, f"  {OK} {runbook.name}: paired with {script}")
                lines.append(f"- {OK} `{runbook.name}`: paired with `{script}`\n")
            else:
                f.add(WARNING, f"Runbook `{runbook.name}` has no matching script (.py or .sh)")
                cprint(C.YELLOW, f"  {WARNING} {runbook.name}: no matching script")
                lines.append(f"- {WARNING} `{runbook.name}`: no script found\n")

    # Check sensitive output files are gitignored (security/doc audit outputs)
    gitignore = read_file(REPO_ROOT / ".gitignore")
    lines.append("\n**Gitignore coverage:**\n")
    # These outputs contain sensitive infrastructure findings and must never be committed
    sensitive_outputs = ["security-check-current.md", "doc-check-current.md"]
    for output_name in sensitive_outputs:
        rel = f"runbooks/{output_name}"
        if output_name in gitignore or rel in gitignore:
            cprint(C.GREEN, f"  {OK} {rel} is gitignored")
            lines.append(f"- {OK} `{rel}` gitignored\n")
        else:
            f.add(WARNING, f"`{rel}` is NOT in .gitignore — security findings may be exposed in public repo")
            cprint(C.YELLOW, f"  {WARNING} {rel} NOT in .gitignore")
            lines.append(f"- {WARNING} `{rel}` not gitignored\n")

    # Check reference docs freshness
    lines.append("\n**Reference doc freshness:**\n")
    ref_docs = [
        REPO_ROOT / "docs" / "infrastructure.md",
        REPO_ROOT / "docs" / "network.md",
        REPO_ROOT / "docs" / "security.md",
        REPO_ROOT / "docs" / "applications.md",
        REPO_ROOT / "docs" / "integration.md",
    ]
    for doc_path in ref_docs:
        rel = doc_path.relative_to(REPO_ROOT)
        if not doc_path.exists():
            f.add(CRITICAL, f"Reference doc `{rel}` is missing")
            lines.append(f"- {CRITICAL} `{rel}`: missing\n")
        else:
            age_days = (now - doc_path.stat().st_mtime) / 86400
            if age_days > DOCS_STALE_DAYS:
                f.add(WARNING, f"`{rel}` is {age_days:.0f}d old — review for accuracy")
                lines.append(f"- {WARNING} `{rel}`: {age_days:.0f}d old (may be stale)\n")
            else:
                lines.append(f"- {OK} `{rel}`: {age_days:.1f}d old\n")

    # Check SOP docs freshness (dynamic — includes any future SOPs)
    lines.append("\n**SOP file freshness:**\n")
    sop_dir = REPO_ROOT / "docs" / "sops"
    sop_files = sorted(p for p in sop_dir.glob("*.md") if p.name != "SOP-TEMPLATE.md")
    for sop_path in sop_files:
        rel = sop_path.relative_to(REPO_ROOT)
        if not sop_path.exists():
            f.add(WARNING, f"SOP `{rel}` is missing")
            lines.append(f"- {WARNING} `{rel}`: missing\n")
        else:
            age_days = (now - sop_path.stat().st_mtime) / 86400
            if age_days > SOPS_STALE_DAYS:
                f.add(WARNING, f"`{rel}` is {age_days:.0f}d old — review for accuracy")
                lines.append(f"- {WARNING} `{rel}`: {age_days:.0f}d old\n")
            else:
                lines.append(f"- {OK} `{rel}`: {age_days:.1f}d old\n")

    lines.append(f.markdown())
    return f.worst(), f, "\n".join(lines)


# ---------------------------------------------------------------------------
# Report writer
# ---------------------------------------------------------------------------

SECTION_NAMES = [
    "Infrastructure Documentation",
    "Network Documentation",
    "Application Documentation",
    "Security Documentation",
    "Integration Documentation",
    "README & CLAUDE.md Currency",
    "Coding Guidelines & Rules",
    "Runbook Coverage",
]


def write_report(timestamp: str, results: list[tuple[str, Findings, str]]) -> None:
    doc = [
        f"# Documentation Health Check — {timestamp}\n\n",
        "> Auto-generated by `runbooks/doc-check.py` — do not hand-edit.\n\n---\n\n",
    ]

    # Summary table
    doc.append("## Summary\n\n")
    doc.append("| # | Section | Status | Findings |\n")
    doc.append("|---|---------|--------|----------|\n")
    for i, (status, findings, _) in enumerate(results, 1):
        name = SECTION_NAMES[i - 1]
        doc.append(f"| {i} | {name} | {status} | {findings.summary_cell()} |\n")

    # Overall assessment
    all_statuses = [s for s, _, _ in results]
    if CRITICAL in all_statuses:
        overall = f"{CRITICAL} Critical issues found — act immediately"
    elif WARNING in all_statuses:
        overall = f"{WARNING} Warnings found — review within a week"
    else:
        overall = f"{OK} All documentation checks passed"

    doc.append(f"\n**Overall:** {overall}\n\n---\n\n")

    # Detailed sections
    for i, (status, findings, body) in enumerate(results, 1):
        name = SECTION_NAMES[i - 1]
        doc.append(f"## {i}. {name}\n\n**Status: {status}**\n\n")
        doc.append(body)
        doc.append("\n---\n\n")

    # Priority actions
    criticals = [(SECTION_NAMES[i], f) for i, (s, f, _) in enumerate(results) if s == CRITICAL]
    warnings  = [(SECTION_NAMES[i], f) for i, (s, f, _) in enumerate(results) if s == WARNING]

    if criticals or warnings:
        doc.append("## Priority Actions\n\n")
        if criticals:
            doc.append("### 🔴 Critical\n\n")
            for name, f in criticals:
                for sev, msg in f._items:
                    if sev == CRITICAL:
                        doc.append(f"- **{name}**: {msg}\n")
        if warnings:
            doc.append("\n### 🟡 Warning\n\n")
            for name, f in warnings:
                for sev, msg in f._items:
                    if sev == WARNING:
                        doc.append(f"- **{name}**: {msg}\n")

    doc.append("\n## How to Update Documentation\n\n")
    doc.append("- `docs/infrastructure.md` — update after K8s/Talos version upgrades or hardware changes\n")
    doc.append("- `docs/network.md` — update after VLAN or WiFi changes\n")
    doc.append("- `docs/applications.md` — update after deploying or removing apps\n")
    doc.append("- `docs/security.md` — update after key rotation or new security policies\n")
    doc.append("- `docs/integration.md` — update after Ollama endpoint or integration changes\n")
    doc.append("- `README.md` — update version badges after major upgrades\n")
    doc.append("- `CLAUDE.md` — update age key if `.sops.yaml` key changes\n")
    doc.append("\n_Next run: weekly (or after major deployments)_\n")

    OUTPUT.write_text("".join(doc))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    os.chdir(REPO_ROOT)

    cprint(C.BOLD + C.BLUE, "=" * 60)
    cprint(C.BOLD + C.BLUE, " Documentation Health Check — Kubernetes Homelab")
    cprint(C.BOLD + C.BLUE, "=" * 60)
    print(f"Date   : {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"Output : {OUTPUT}")
    print()

    # Sanity check: make sure we're in the right repo
    if not (REPO_ROOT / "CLAUDE.md").exists():
        cprint(C.RED, "ERROR: CLAUDE.md not found — run from repository root or via runbooks/doc-check.py")
        return 1

    results: list[tuple[str, Findings, str]] = []

    results.append(s1_infrastructure_docs())
    results.append(s2_network_docs())
    results.append(s3_application_docs())
    results.append(s4_security_docs())
    results.append(s5_integration_docs())
    results.append(s6_readme_claude_currency())
    results.append(s7_coding_guidelines())
    results.append(s8_runbook_coverage())

    # Write report
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    write_report(timestamp, results)

    # Final summary
    total_crit = sum(1 for s, _, _ in results if s == CRITICAL)
    total_warn = sum(1 for s, _, _ in results if s == WARNING)
    total_ok   = sum(1 for s, _, _ in results if s == OK)

    print()
    cprint(C.BOLD + C.BLUE, "=" * 60)
    cprint(C.BOLD, f" Results: {total_crit} critical  {total_warn} warning  {total_ok} ok")
    cprint(C.BOLD + C.BLUE, "=" * 60)
    print(f"\nReport written to: {OUTPUT}\n")

    return 1 if total_crit > 0 else 0


if __name__ == "__main__":
    sys.exit(main())

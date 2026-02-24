#!/usr/bin/env python3
"""
Comprehensive version checker for Kubernetes deployments.

Scans all HelmReleases in the repository and checks for:
1. Chart versions (current vs latest available)
2. Container image versions (current vs latest available)
3. Application versions (where applicable)

Outputs:
- AI_version_check_current.md: Current status of all deployments
- AI_version_check.md: Documentation on how to use this tool
"""

import os
import re
import json
import yaml
import subprocess
import requests
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
from urllib.parse import urlparse
import sys
from packaging import version

# Color codes for terminal output
class Colors:
    RESET = '\033[0m'
    RED = '\033[0;31m'
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    BLUE = '\033[0;34m'
    CYAN = '\033[0;36m'

class VersionChecker:
    def __init__(self, repo_root: str, github_token: Optional[str] = None):
        self.repo_root = Path(repo_root)
        self.kubernetes_dir = self.repo_root / "kubernetes"
        self.helmreleases: List[Dict] = []
        self.helm_repositories: Dict[str, Dict] = {}
        self.results: List[Dict] = []
        self.github_cache: Dict[str, Any] = {}  # Cache for GitHub API responses
        self.github_token = github_token or os.environ.get('GITHUB_TOKEN')
        self.github_headers = {
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': 'version-checker'
        }
        if self.github_token:
            self.github_headers['Authorization'] = f'token {self.github_token}'
        
        # Check if gh CLI is available
        self.use_gh_cli = self._check_gh_available()
        
    def find_helmreleases(self) -> List[Path]:
        """Find all HelmRelease YAML files."""
        helmreleases = []
        apps_dir = self.kubernetes_dir / "apps"
        
        for yaml_file in apps_dir.rglob("helmrelease.yaml"):
            helmreleases.append(yaml_file)
        
        return helmreleases
    
    def load_helmrepositories(self):
        """Load all HelmRepository definitions."""
        repos_dir = self.kubernetes_dir / "flux" / "meta" / "repositories" / "helm"
        
        for repo_file in repos_dir.glob("*.yaml"):
            try:
                with open(repo_file, 'r') as f:
                    doc = yaml.safe_load(f)
                    if doc and doc.get('kind') == 'HelmRepository':
                        name = doc['metadata']['name']
                        self.helm_repositories[name] = {
                            'url': doc['spec'].get('url', ''),
                            'type': doc['spec'].get('type', 'default'),
                            'name': name
                        }
            except Exception as e:
                print(f"{Colors.YELLOW}Warning: Could not load {repo_file}: {e}{Colors.RESET}")
    
    def parse_helmrelease(self, file_path: Path) -> Optional[Dict]:
        """Parse a HelmRelease YAML file."""
        try:
            with open(file_path, 'r') as f:
                doc = yaml.safe_load(f)
                
            if not doc or doc.get('kind') != 'HelmRelease':
                return None
            
            metadata = doc.get('metadata', {})
            spec = doc.get('spec', {})
            chart_spec = spec.get('chart', {}).get('spec', {})
            values = spec.get('values', {})
            
            # Extract chart info
            chart_name = chart_spec.get('chart', '')
            chart_version = chart_spec.get('version', '')
            source_ref = chart_spec.get('sourceRef', {})
            repo_name = source_ref.get('name', '')
            
            # Extract images from values
            images = self.extract_images(values)
            
            return {
                'name': metadata.get('name', ''),
                'namespace': metadata.get('namespace', 'default'),
                'file_path': str(file_path.relative_to(self.repo_root)),
                'chart_name': chart_name,
                'chart_version': chart_version,
                'repository_name': repo_name,
                'images': images
            }
        except Exception as e:
            print(f"{Colors.RED}Error parsing {file_path}: {e}{Colors.RESET}")
            return None
    
    def extract_images(self, values: Dict, path: str = '') -> List[Dict]:
        """Recursively extract image information from values."""
        images = []
        
        if isinstance(values, dict):
            # Check for image.repository and image.tag pattern
            if 'image' in values and isinstance(values['image'], dict):
                img = values['image']
                if 'repository' in img or 'tag' in img:
                    images.append({
                        'repository': img.get('repository', ''),
                        'tag': img.get('tag', ''),
                        'path': path + '.image' if path else 'image'
                    })
            
            # Check for containers pattern (app-template style)
            if 'containers' in values and isinstance(values['containers'], dict):
                for container_name, container in values['containers'].items():
                    if isinstance(container, dict) and 'image' in container:
                        img = container['image']
                        if isinstance(img, dict):
                            images.append({
                                'repository': img.get('repository', ''),
                                'tag': img.get('tag', ''),
                                'path': f"{path}.containers.{container_name}.image" if path else f"containers.{container_name}.image"
                            })
                        elif isinstance(img, str):
                            # Parse image:tag format
                            parts = img.split(':', 1)
                            images.append({
                                'repository': parts[0] if parts else '',
                                'tag': parts[1] if len(parts) > 1 else 'latest',
                                'path': f"{path}.containers.{container_name}.image" if path else f"containers.{container_name}.image"
                            })
            
            # Check for controllers pattern (app-template style)
            if 'controllers' in values and isinstance(values['controllers'], dict):
                for controller_name, controller in values['controllers'].items():
                    if isinstance(controller, dict):
                        controller_images = self.extract_images(controller, f"{path}.controllers.{controller_name}" if path else f"controllers.{controller_name}")
                        images.extend(controller_images)
            
            # Recursively check nested dictionaries
            for key, value in values.items():
                if key not in ['image', 'containers', 'controllers'] and isinstance(value, dict):
                    nested_images = self.extract_images(value, f"{path}.{key}" if path else key)
                    images.extend(nested_images)
        
        return images
    
    def get_latest_chart_version(self, repo_name: str, chart_name: str) -> Optional[str]:
        """Get latest chart version from Helm repository."""
        if repo_name not in self.helm_repositories:
            return None
        
        repo = self.helm_repositories[repo_name]
        repo_url = repo['url']
        repo_type = repo.get('type', 'default')
        
        try:
            if repo_type == 'oci':
                # OCI registry (e.g., ghcr.io)
                return self.get_oci_chart_version(repo_url, chart_name)
            else:
                # Traditional Helm repository
                return self.get_helm_repo_chart_version(repo_url, chart_name)
        except Exception as e:
            print(f"{Colors.YELLOW}Warning: Could not check chart version for {chart_name} from {repo_name}: {e}{Colors.RESET}")
            return None
    
    def get_oci_chart_version(self, repo_url: str, chart_name: str) -> Optional[str]:
        """Get latest version from OCI registry."""
        try:
            # Use helm to search OCI registry
            cmd = ['helm', 'search', 'repo', '--output', 'json', f'{repo_url}/{chart_name}']
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                data = json.loads(result.stdout)
                if data and len(data) > 0:
                    # Get the first (latest) version
                    versions = [item.get('version', '') for item in data if item.get('name', '').endswith(chart_name)]
                    if versions:
                        return versions[0]
        except Exception:
            pass
        
        return None
    
    def get_helm_repo_chart_version(self, repo_url: str, chart_name: str) -> Optional[str]:
        """Get latest version from traditional Helm repository."""
        try:
            # Add repo temporarily
            temp_repo_name = f"temp-{hash(repo_url) % 10000}"
            subprocess.run(['helm', 'repo', 'add', temp_repo_name, repo_url], 
                         capture_output=True, timeout=30)
            
            # Search for chart
            cmd = ['helm', 'search', 'repo', '--output', 'json', f'{temp_repo_name}/{chart_name}']
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            # Remove temp repo
            subprocess.run(['helm', 'repo', 'remove', temp_repo_name], 
                         capture_output=True)
            
            if result.returncode == 0:
                data = json.loads(result.stdout)
                if data and len(data) > 0:
                    versions = [item.get('version', '') for item in data]
                    if versions:
                        return versions[0]
        except Exception:
            pass
        
        return None
    
    def get_latest_image_tag(self, repository: str, current_tag: str = '') -> Optional[str]:
        """Get latest image tag from container registry."""
        if not repository:
            return None
        
        try:
            # Parse repository URL
            parsed = urlparse(f"https://{repository}")
            registry = parsed.netloc or repository.split('/')[0]
            image_path = '/'.join(repository.split('/')[1:]) if '/' in repository else repository
            
            # Handle different registries
            if 'ghcr.io' in repository or 'docker.io' in repository or 'quay.io' in repository:
                return self.get_registry_image_tag(repository, current_tag)
            elif 'gcr.io' in repository or 'k8s.gcr.io' in repository:
                return self.get_gcr_image_tag(repository)
            else:
                # Try generic Docker Hub API
                return self.get_dockerhub_image_tag(repository)
        except Exception as e:
            print(f"{Colors.YELLOW}Warning: Could not check image tag for {repository}: {e}{Colors.RESET}")
            return None
    
    def get_registry_image_tag(self, repository: str, current_tag: str = '') -> Optional[str]:
        """Get latest tag from GHCR, Docker Hub, or Quay."""
        try:
            # For GHCR, use GitHub API
            if 'ghcr.io' in repository:
                # Extract owner/repo from ghcr.io/owner/repo
                parts = repository.replace('ghcr.io/', '').split('/')
                if len(parts) >= 2:
                    owner = parts[0]
                    repo = parts[1]
                    api_url = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"
                    response = requests.get(api_url, timeout=10)
                    if response.status_code == 200:
                        data = response.json()
                        tag = data.get('tag_name', '')
                        if tag:
                            return tag.lstrip('v')
            
            # For Docker Hub, try Docker Hub API
            elif 'docker.io' in repository or not '/' in repository.split('://')[-1].split('/')[0]:
                image_name = repository.replace('docker.io/', '').split(':')[0]
                # Fetch more tags and filter for semantic versions
                api_url = f"https://hub.docker.com/v2/repositories/{image_name}/tags?page_size=200"
                response = requests.get(api_url, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    if data.get('results'):
                        # Determine preferred major version from current tag
                        preferred_major = None
                        if current_tag:
                            current_parsed = self.parse_version(current_tag)
                            if current_parsed:
                                preferred_major = current_parsed[0]
                        
                        # Filter for semantic version tags (x.y.z format, with optional v prefix)
                        # Matches: 1.2.3, v1.2.3, 0.107.65, v0.107.65
                        version_pattern = re.compile(r'^v?\d+\.\d+\.\d+$')
                        version_tags = [tag for tag in data['results'] if version_pattern.match(tag.get('name', ''))]
                        if version_tags:
                            # Sort by version number (not by last_updated)
                            def version_key(tag):
                                name = tag['name'].lstrip('vV')  # Remove v prefix for comparison
                                parts = name.split('.')
                                try:
                                    return (int(parts[0]), int(parts[1]), int(parts[2]))
                                except (ValueError, IndexError):
                                    return (0, 0, 0)
                            version_tags.sort(key=version_key, reverse=True)
                            
                            # If we have a preferred major version, prefer tags from that major version
                            if preferred_major is not None:
                                same_major = [tag for tag in version_tags if version_key(tag)[0] == preferred_major]
                                if same_major:
                                    return same_major[0].get('name', '')
                            
                            # Otherwise return the highest version overall
                            return version_tags[0].get('name', '')
                        # Fallback: return first tag if no version tags found
                        return data['results'][0].get('name', '')
            
            # For Quay.io, use Quay API
            elif 'quay.io' in repository:
                image_name = repository.replace('quay.io/', '')
                api_url = f"https://quay.io/api/v1/repository/{image_name}/tag?limit=1&onlyActiveTags=true"
                response = requests.get(api_url, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    if data.get('tags'):
                        return data['tags'][0].get('name', '')
        except Exception:
            pass
        
        return None
    
    def get_dockerhub_image_tag(self, repository: str) -> Optional[str]:
        """Get latest tag from Docker Hub."""
        return self.get_registry_image_tag(repository)
    
    def get_gcr_image_tag(self, repository: str) -> Optional[str]:
        """Get latest tag from GCR (not fully implemented)."""
        # GCR requires authentication, skip for now
        return None
    
    def normalize_tag(self, tag: str) -> str:
        """Normalize a container image tag for comparison.

        Strips v/V prefix and known variant suffixes (e.g. -alpine, -bookworm, -slim)
        so that '2.8.0-alpine' and '2.8.0', or 'v2.34.0' and '2.34.0', compare as equal.
        """
        # Strip v/V prefix
        tag = tag.lstrip('vV')
        # Strip known OS/variant suffixes that don't represent version differences
        tag = re.sub(r'-(alpine|alpine\d*|bookworm|bullseye|buster|slim|debian|ubuntu|focal|jammy|noble)(\d*)$', '', tag, flags=re.IGNORECASE)
        return tag

    def tags_are_equal(self, current: str, latest: str) -> bool:
        """Return True if two tags represent the same version after normalization."""
        if current == latest:
            return True
        return self.normalize_tag(current) == self.normalize_tag(latest)

    def parse_version(self, version_str: str) -> Optional[Tuple[int, int, int]]:
        """Parse version string into (major, minor, patch) tuple.
        
        Handles various version formats:
        - Semantic versions: 1.2.3, v1.2.3
        - Pre-release: 1.2.3-alpha, 1.2.3-beta.1
        - Build metadata: 1.2.3+build
        """
        if not version_str:
            return None
        
        # Remove 'v' prefix and any build metadata
        clean_version = version_str.lstrip('vV').split('+')[0].split('-')[0]
        
        try:
            # Try using packaging library
            v = version.parse(clean_version)
            if isinstance(v, version.Version):
                return (v.major, v.minor, v.micro)
        except Exception:
            pass
        
        # Fallback: try regex parsing
        match = re.match(r'^(\d+)\.(\d+)\.(\d+)', clean_version)
        if match:
            return (int(match.group(1)), int(match.group(2)), int(match.group(3)))
        
        # Try two-part version
        match = re.match(r'^(\d+)\.(\d+)', clean_version)
        if match:
            return (int(match.group(1)), int(match.group(2)), 0)
        
        # Try single number
        match = re.match(r'^(\d+)', clean_version)
        if match:
            return (int(match.group(1)), 0, 0)
        
        return None
    
    def assess_update_complexity(self, current: str, latest: str) -> Dict[str, Any]:
        """Assess the complexity of an update (major/minor/patch).
        
        Returns:
            Dict with keys: 'type' (major/minor/patch/unknown), 'complexity' (low/medium/high),
            'description', 'breaking_changes' (list of breaking change indicators)
        """
        result = {
            'type': 'unknown',
            'complexity': 'unknown',
            'description': '',
            'breaking_changes': []
        }
        
        current_parsed = self.parse_version(current)
        latest_parsed = self.parse_version(latest)
        
        if not current_parsed or not latest_parsed:
            result['description'] = 'Version format not recognized'
            return result
        
        current_major, current_minor, current_patch = current_parsed
        latest_major, latest_minor, latest_patch = latest_parsed
        
        if latest_major > current_major:
            result['type'] = 'major'
            result['complexity'] = 'high'
            result['description'] = f'Major version update: {current_major}.x.x → {latest_major}.x.x'
            result['breaking_changes'].append('Major version change typically indicates breaking changes')
        elif latest_minor > current_minor:
            result['type'] = 'minor'
            result['complexity'] = 'medium'
            result['description'] = f'Minor version update: {current_major}.{current_minor}.x → {current_major}.{latest_minor}.x'
        elif latest_patch > current_patch:
            result['type'] = 'patch'
            result['complexity'] = 'low'
            result['description'] = f'Patch version update: {current_major}.{current_minor}.{current_patch} → {current_major}.{current_minor}.{latest_patch}'
        else:
            result['type'] = 'unknown'
            result['description'] = 'Versions appear equal or downgrade detected'
        
        return result
    
    def fetch_release_notes(self, repo_owner: str, repo_name: str, tag: str) -> Optional[Dict[str, Any]]:
        """Fetch release notes using GitHub CLI (gh) or fallback to API.
        
        Returns:
            Dict with 'body' (release notes), 'prerelease' (bool), 'published_at' (str)
        """
        cache_key = f"{repo_owner}/{repo_name}:{tag}"
        if cache_key in self.github_cache:
            return self.github_cache[cache_key]
        
        # Try using gh CLI first (authenticated, no rate limits)
        try:
            # Try with the tag as-is
            result = self._fetch_release_notes_gh(repo_owner, repo_name, tag)
            if result:
                self.github_cache[cache_key] = result
                return result
            
            # Try with 'v' prefix variations
            clean_tag = tag.lstrip('vV')
            if tag != clean_tag:
                result = self._fetch_release_notes_gh(repo_owner, repo_name, clean_tag)
                if result:
                    self.github_cache[cache_key] = result
                    return result
            
            alt_tag = f"v{clean_tag}" if not tag.startswith('v') else clean_tag
            if alt_tag != tag:
                result = self._fetch_release_notes_gh(repo_owner, repo_name, alt_tag)
                if result:
                    self.github_cache[cache_key] = result
                    return result
        except Exception:
            pass
        
        # Fallback to API if gh is not available or fails
        return self._fetch_release_notes_api(repo_owner, repo_name, tag)
    
    def _fetch_release_notes_gh(self, repo_owner: str, repo_name: str, tag: str) -> Optional[Dict[str, Any]]:
        """Fetch release notes using GitHub CLI."""
        try:
            # Use gh api to get release by tag
            cmd = ['gh', 'api', '-X', 'GET', f'repos/{repo_owner}/{repo_name}/releases/tags/{tag}']
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0:
                data = json.loads(result.stdout)
                return {
                    'body': data.get('body', ''),
                    'prerelease': data.get('prerelease', False),
                    'published_at': data.get('published_at', '')
                }
        except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
            # gh not available or invalid response
            pass
        except Exception:
            pass
        
        return None
    
    def _fetch_release_notes_api(self, repo_owner: str, repo_name: str, tag: str) -> Optional[Dict[str, Any]]:
        """Fallback: Fetch release notes from GitHub API (for when gh is not available)."""
        cache_key = f"{repo_owner}/{repo_name}:{tag}"
        if cache_key in self.github_cache:
            return self.github_cache[cache_key]
        
        import time
        
        try:
            # Add small delay to avoid rate limiting
            time.sleep(0.5)
            
            # Try to get release by tag
            clean_tag = tag.lstrip('vV')
            url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/releases/tags/{tag}"
            response = requests.get(url, timeout=15, headers=self.github_headers)
            
            if response.status_code == 200:
                data = response.json()
                result = {
                    'body': data.get('body', ''),
                    'prerelease': data.get('prerelease', False),
                    'published_at': data.get('published_at', '')
                }
                self.github_cache[cache_key] = result
                return result
            elif response.status_code == 404:
                # Try with 'v' prefix variations
                time.sleep(0.3)
                alt_tag = f"v{clean_tag}" if not tag.startswith('v') else clean_tag
                url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/releases/tags/{alt_tag}"
                response = requests.get(url, timeout=15, headers=self.github_headers)
                if response.status_code == 200:
                    data = response.json()
                    result = {
                        'body': data.get('body', ''),
                        'prerelease': data.get('prerelease', False),
                        'published_at': data.get('published_at', '')
                    }
                    self.github_cache[cache_key] = result
                    return result
        except requests.exceptions.RequestException:
            pass
        except Exception:
            pass
        
        return None
    
    def _check_gh_available(self) -> bool:
        """Check if GitHub CLI (gh) is available and authenticated."""
        try:
            result = subprocess.run(['gh', '--version'], capture_output=True, timeout=5)
            if result.returncode == 0:
                # Check if authenticated
                auth_result = subprocess.run(['gh', 'auth', 'status'], capture_output=True, timeout=5)
                return auth_result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        return False
    
    def detect_breaking_changes(self, release_notes: str, update_type: str) -> List[str]:
        """Extract breaking changes from release notes.
        
        Looks for common sections and extracts actual content:
        - "BREAKING" or "BREAKING CHANGE" sections
        - "Migration" or "Upgrade" sections
        - Deprecation warnings
        - API changes
        """
        breaking_changes = []
        
        if not release_notes:
            return breaking_changes
        
        # Try to extract breaking changes section
        # Look for common patterns like "## Breaking Changes", "### BREAKING", etc.
        breaking_patterns = [
            r'##\s*[#]*\s*Breaking\s+Changes?[^\n]*\n(.*?)(?=\n##|\Z)',
            r'###\s*[#]*\s*BREAKING[^\n]*\n(.*?)(?=\n##|\n###|\Z)',
            r'###\s*[#]*\s*Breaking[^\n]*\n(.*?)(?=\n##|\n###|\Z)',
            r'⚠️\s*Breaking[^\n]*\n(.*?)(?=\n##|\n###|\Z)',
            r'🚨\s*Breaking[^\n]*\n(.*?)(?=\n##|\n###|\Z)',
        ]
        
        for pattern in breaking_patterns:
            matches = re.finditer(pattern, release_notes, re.IGNORECASE | re.DOTALL | re.MULTILINE)
            for match in matches:
                content = match.group(1).strip()
                if content and len(content) > 10:  # Only add if substantial content
                    # Clean up the content
                    content = re.sub(r'\n{3,}', '\n\n', content)  # Normalize multiple newlines
                    breaking_changes.append(content)
        
        # If no explicit breaking section found, look for breaking change indicators in text
        if not breaking_changes:
            # Look for lines with breaking change keywords
            lines = release_notes.split('\n')
            breaking_lines = []
            for i, line in enumerate(lines):
                line_lower = line.lower()
                if any(keyword in line_lower for keyword in ['breaking change', 'breaking changes', '⚠️ breaking', '🚨 breaking']):
                    # Get context (current line + next few lines)
                    context = '\n'.join(lines[i:min(i+5, len(lines))])
                    if context.strip():
                        breaking_lines.append(context.strip())
            
            if breaking_lines:
                breaking_changes.extend(breaking_lines[:3])  # Limit to first 3 matches
        
        # Check for migration/upgrade sections
        migration_patterns = [
            r'##\s*[#]*\s*Migration[^\n]*\n(.*?)(?=\n##|\Z)',
            r'##\s*[#]*\s*Upgrade[^\n]*\n(.*?)(?=\n##|\Z)',
        ]
        
        for pattern in migration_patterns:
            matches = re.finditer(pattern, release_notes, re.IGNORECASE | re.DOTALL | re.MULTILINE)
            for match in matches:
                content = match.group(1).strip()
                if content and len(content) > 10:
                    breaking_changes.append(f"Migration/Upgrade Guide:\n{content[:500]}")  # Limit length
        
        # For major versions, add a note if no explicit breaking changes found
        if update_type == 'major' and not breaking_changes:
            breaking_changes.append("Major version update - breaking changes likely. Review full release notes for details.")
        
        return breaking_changes
    
    def get_repo_info_from_image(self, image_repo: str) -> Optional[Tuple[str, str]]:
        """Extract GitHub owner/repo from container image repository.
        
        Examples:
        - ghcr.io/owner/repo -> (owner, repo)
        - docker.io/owner/repo -> (owner, repo)
        """
        # Handle GHCR
        if 'ghcr.io' in image_repo:
            parts = image_repo.replace('ghcr.io/', '').split('/')
            if len(parts) >= 2:
                return (parts[0], parts[1])
        
        # Handle docker.io (Docker Hub)
        if 'docker.io' in image_repo or (not '/' in image_repo.split('://')[-1].split('/')[0] and '.' not in image_repo.split('/')[0]):
            # Docker Hub format: owner/repo or library/repo
            parts = image_repo.split('/')
            if len(parts) >= 2:
                owner = parts[0] if parts[0] != 'library' else parts[1]
                repo = parts[-1]
                return (owner, repo)
        
        return None
    
    def get_chart_repo_info(self, chart_name: str, repo_name: str, repo_url: str = '') -> Optional[Tuple[str, str]]:
        """Get GitHub repository info for a Helm chart.
        
        Uses common mappings and patterns to find the GitHub repo.
        """
        # Common chart to GitHub repo mappings
        chart_repo_map = {
            'cert-manager': ('cert-manager', 'cert-manager'),
            'grafana': ('grafana', 'helm-charts'),
            'prometheus': ('prometheus-community', 'helm-charts'),
            'kube-prometheus-stack': ('prometheus-community', 'helm-charts'),
            'longhorn': ('longhorn', 'longhorn'),
            'cilium': ('cilium', 'cilium'),
            'ingress-nginx': ('kubernetes', 'ingress-nginx'),
            'external-dns': ('kubernetes-sigs', 'external-dns'),
            'fluent-bit': ('fluent', 'helm-charts'),
            'opentelemetry-operator': ('open-telemetry', 'opentelemetry-helm-charts'),
            'eck-operator': ('elastic', 'cloud-on-k8s'),
            'uptime-kuma': ('louislam', 'uptime-kuma'),
            'adguard-home': ('AdguardTeam', 'AdGuardHome'),
            'paperless-ngx': ('paperless-ngx', 'paperless'),
            'nextcloud': ('nextcloud', 'helm'),
            'open-webui': ('open-webui', 'open-webui'),
            'plex-media-server': ('plexinc', 'pms-docker'),
            'plex': ('plexinc', 'pms-docker'),
            'jellyfin': ('jellyfin', 'jellyfin'),
            'homepage': ('gethomepage', 'homepage'),
            'authentik': ('goauthentik', 'authentik'),
            'descheduler': ('kubernetes-sigs', 'descheduler'),
            'node-feature-discovery': ('kubernetes-sigs', 'node-feature-discovery'),
            'metrics-server': ('kubernetes-sigs', 'metrics-server'),
            'coredns': ('coredns', 'coredns'),
            'csi-driver-smb': ('kubernetes-csi', 'csi-driver-smb'),
        }
        
        # Check direct mapping
        if chart_name in chart_repo_map:
            return chart_repo_map[chart_name]
        
        # Try to infer from repo URL
        if repo_url:
            # OCI registry pattern: oci://ghcr.io/owner/charts
            if 'ghcr.io' in repo_url:
                parts = repo_url.replace('oci://', '').replace('ghcr.io/', '').split('/')
                if len(parts) >= 2:
                    return (parts[0], parts[1])
            
            # GitHub pattern: https://github.com/owner/repo or https://owner.github.io/repo
            if 'github.com' in repo_url or 'github.io' in repo_url:
                match = re.search(r'github\.(com|io)[/:]([^/]+)/([^/]+)', repo_url)
                if match:
                    owner = match.group(2)
                    repo = match.group(3).rstrip('.git').rstrip('/')
                    return (owner, repo)
        
        # Try common patterns based on chart name
        # Many charts follow: chart-name -> owner/chart-name or owner/helm-charts
        chart_lower = chart_name.lower().replace('-', '')
        
        # Try owner = chart-name pattern
        if chart_name:
            return (chart_name, chart_name)
        
        return None
    
    def check_all(self):
        """Check all HelmReleases for updates."""
        print(f"{Colors.BLUE}=== Scanning HelmReleases ==={Colors.RESET}")
        
        # Load repositories
        self.load_helmrepositories()
        print(f"Loaded {len(self.helm_repositories)} Helm repositories")
        
        # Find and parse all HelmReleases
        helmrelease_files = self.find_helmreleases()
        print(f"Found {len(helmrelease_files)} HelmRelease files")
        
        for file_path in helmrelease_files:
            hr = self.parse_helmrelease(file_path)
            if hr:
                self.helmreleases.append(hr)
        
        print(f"Parsed {len(self.helmreleases)} HelmReleases\n")
        
        # Check each HelmRelease
        print(f"{Colors.BLUE}=== Checking for Updates ==={Colors.RESET}\n")
        
        for hr in self.helmreleases:
            print(f"Checking {Colors.CYAN}{hr['name']}{Colors.RESET} ({hr['namespace']})...")
            
            result = {
                'name': hr['name'],
                'namespace': hr['namespace'],
                'file_path': hr['file_path'],
                'chart': {
                    'name': hr['chart_name'],
                    'current_version': hr['chart_version'],
                    'latest_version': None,
                    'repository': hr['repository_name']
                },
                'images': []
            }
            
            # Check chart version
            if hr['chart_name'] and hr['repository_name']:
                latest_chart = self.get_latest_chart_version(hr['repository_name'], hr['chart_name'])
                result['chart']['latest_version'] = latest_chart
                
                # Get repository URL for chart repo detection
                repo_url = ''
                if hr['repository_name'] in self.helm_repositories:
                    repo_url = self.helm_repositories[hr['repository_name']].get('url', '')
                
                if latest_chart and not self.tags_are_equal(latest_chart, hr['chart_version']):
                    # Assess update complexity
                    assessment = self.assess_update_complexity(hr['chart_version'], latest_chart)
                    result['chart']['update_assessment'] = assessment
                    
                    # Try to fetch release notes for breaking changes
                    breaking_changes = assessment.get('breaking_changes', [])
                    chart_repo_info = self.get_chart_repo_info(hr['chart_name'], hr['repository_name'], repo_url)
                    
                    if chart_repo_info:
                        owner, repo = chart_repo_info
                        result['chart']['github_repo'] = f"{owner}/{repo}"
                        
                        # Try to fetch release notes
                        release_notes = self.fetch_release_notes(owner, repo, latest_chart)
                        if release_notes:
                            detected = self.detect_breaking_changes(release_notes['body'], assessment['type'])
                            breaking_changes.extend(detected)
                            result['chart']['release_notes'] = release_notes
                        else:
                            # Even if we can't fetch release notes, store empty dict to indicate we tried
                            # This allows us to show the GitHub link
                            result['chart']['release_notes'] = {}
                    
                    # For major versions, always add warning if no explicit breaking changes found
                    if assessment['type'] == 'major' and not breaking_changes:
                        breaking_changes.extend(self.detect_breaking_changes('', assessment['type']))
                    
                    result['chart']['breaking_changes'] = breaking_changes
                    
                    complexity_emoji = {'low': '🟢', 'medium': '🟡', 'high': '🔴'}.get(assessment['complexity'], '⚪')
                    print(f"  {Colors.YELLOW}Chart: {hr['chart_version']} → {latest_chart} {complexity_emoji} {assessment['type'].upper()}{Colors.RESET}")
                elif latest_chart == hr['chart_version']:
                    print(f"  {Colors.GREEN}Chart: {hr['chart_version']} (latest){Colors.RESET}")
                else:
                    print(f"  {Colors.YELLOW}Chart: {hr['chart_version']} (could not check latest){Colors.RESET}")
            
            # Check image versions
            for img in hr['images']:
                if img['repository']:
                    latest_tag = self.get_latest_image_tag(img['repository'], img['tag'])
                    img_result = {
                        'repository': img['repository'],
                        'current_tag': img['tag'],
                        'latest_tag': latest_tag,
                        'path': img['path']
                    }
                    
                    if latest_tag and not self.tags_are_equal(latest_tag, img['tag']) and img['tag'] != 'latest':
                        # Assess update complexity
                        assessment = self.assess_update_complexity(img['tag'], latest_tag)
                        img_result['update_assessment'] = assessment
                        
                        # Try to fetch release notes for breaking changes
                        repo_info = self.get_repo_info_from_image(img['repository'])
                        breaking_changes = assessment.get('breaking_changes', [])
                        
                        if repo_info:
                            owner, repo = repo_info
                            release_notes = self.fetch_release_notes(owner, repo, latest_tag)
                            if release_notes:
                                detected = self.detect_breaking_changes(release_notes['body'], assessment['type'])
                                breaking_changes.extend(detected)
                                img_result['release_notes'] = release_notes
                        
                        if assessment['type'] == 'major' and not breaking_changes:
                            breaking_changes.extend(self.detect_breaking_changes('', assessment['type']))
                        
                        img_result['breaking_changes'] = breaking_changes
                        
                        complexity_emoji = {'low': '🟢', 'medium': '🟡', 'high': '🔴'}.get(assessment['complexity'], '⚪')
                        print(f"  {Colors.YELLOW}Image {img['repository']}: {img['tag']} → {latest_tag} {complexity_emoji} {assessment['type'].upper()}{Colors.RESET}")
                    elif img['tag'] == 'latest' or (latest_tag and self.tags_are_equal(latest_tag, img['tag'])):
                        print(f"  {Colors.GREEN}Image {img['repository']}: {img['tag']} (latest){Colors.RESET}")
                    else:
                        print(f"  {Colors.YELLOW}Image {img['repository']}: {img['tag']} (could not check){Colors.RESET}")
                    
                    result['images'].append(img_result)
            
            self.results.append(result)
            print()
    
    def generate_markdown_report(self) -> str:
        """Generate markdown report of current status."""
        lines = []
        lines.append("# Kubernetes Deployment Version Status")
        lines.append("")
        lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")
        lines.append("> **Note:** Release notes are fetched from GitHub API. If rate limited, some release notes may not be available. Check source links for full details.")
        lines.append("")
        lines.append("## Summary")
        lines.append("")
        
        # Count updates available
        chart_updates = sum(1 for r in self.results 
                          if r['chart']['latest_version'] and 
                          r['chart']['current_version'] != r['chart']['latest_version'])
        
        image_updates = sum(1 for r in self.results 
                          for img in r['images'] 
                          if img['latest_tag'] and 
                          img['current_tag'] != img['latest_tag'] and 
                          img['current_tag'] != 'latest')
        
        # Count by complexity
        major_updates = sum(1 for r in self.results 
                          for item in [r['chart']] + r['images']
                          if item.get('update_assessment') and 
                          item['update_assessment'].get('type') == 'major')
        
        minor_updates = sum(1 for r in self.results 
                          for item in [r['chart']] + r['images']
                          if item.get('update_assessment') and 
                          item['update_assessment'].get('type') == 'minor')
        
        patch_updates = sum(1 for r in self.results 
                          for item in [r['chart']] + r['images']
                          if item.get('update_assessment') and 
                          item['update_assessment'].get('type') == 'patch')
        
        breaking_changes_count = sum(1 for r in self.results 
                                    for item in [r['chart']] + r['images']
                                    if item.get('breaking_changes') and 
                                    len(item['breaking_changes']) > 0)
        
        lines.append(f"- **Total Deployments:** {len(self.results)}")
        lines.append(f"- **Chart Updates Available:** {chart_updates}")
        lines.append(f"- **Image Updates Available:** {image_updates}")
        lines.append(f"- **Update Breakdown:** 🔴 {major_updates} major | 🟡 {minor_updates} minor | 🟢 {patch_updates} patch")
        if breaking_changes_count > 0:
            lines.append(f"- **⚠️ Breaking Changes Detected:** {breaking_changes_count} updates with potential breaking changes")
        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append("## Quick Overview Table")
        lines.append("")
        lines.append("| Deployment | Namespace | Chart | Image | App | Complexity |")
        lines.append("|------------|-----------|-------|-------|-----|------------|")
        
        # Sort results by namespace and name for the table
        sorted_results = sorted(self.results, key=lambda x: (x['namespace'], x['name']))
        
        for result in sorted_results:
            name = result['name']
            namespace = result['namespace']
            
            # Chart version info
            chart = result['chart']
            chart_update = False
            chart_complexity = "-"
            if chart['latest_version'] and chart['current_version'] != chart['latest_version']:
                chart_version = f"{chart['current_version']} → {chart['latest_version']}"
                chart_update = True
                if 'update_assessment' in chart:
                    complexity_emoji = {'low': '🟢', 'medium': '🟡', 'high': '🔴'}.get(
                        chart['update_assessment'].get('complexity', 'unknown'), '⚪')
                    chart_complexity = f"{complexity_emoji} {chart['update_assessment'].get('type', 'unknown').upper()}"
                else:
                    chart_complexity = "⚠️"
            elif chart['latest_version']:
                chart_version = f"{chart['current_version']} ✅"
            else:
                chart_version = f"{chart['current_version']}"
                if not chart['latest_version']:
                    chart_version += " ?"
            
            # Image version info (get first/main image)
            main_image = None
            image_update = False
            image_complexity = "-"
            app_version = "-"
            
            if result['images']:
                # Prefer non-latest, non-edge tags for main image
                for img in result['images']:
                    if img['current_tag'] and img['current_tag'] not in ['latest', 'edge']:
                        main_image = img
                        break
                if not main_image:
                    main_image = result['images'][0]
            
            if main_image:
                # App version is typically the image tag (for applications)
                app_version = str(main_image['current_tag']) if main_image['current_tag'] and main_image['current_tag'] not in ['latest', 'edge'] else "-"
                
                if main_image['latest_tag'] and main_image['current_tag'] != main_image['latest_tag'] and main_image['current_tag'] != 'latest':
                    image_version = f"{main_image['current_tag']} → {main_image['latest_tag']}"
                    image_update = True
                    if 'update_assessment' in main_image:
                        complexity_emoji = {'low': '🟢', 'medium': '🟡', 'high': '🔴'}.get(
                            main_image['update_assessment'].get('complexity', 'unknown'), '⚪')
                        image_complexity = f"{complexity_emoji} {main_image['update_assessment'].get('type', 'unknown').upper()}"
                    else:
                        image_complexity = "⚠️"
                elif main_image['current_tag'] == 'latest' or (main_image['latest_tag'] and main_image['latest_tag'] == main_image['current_tag']):
                    image_version = f"{main_image['current_tag']} ✅"
                else:
                    image_version = f"{main_image['current_tag']}"
                    if not main_image['latest_tag']:
                        image_version += " ?"
            else:
                image_version = "-"
            
            # Overall complexity (prefer highest complexity: major > minor > patch)
            overall_complexity = "-"
            complexities = []
            if chart_complexity != "-" and chart_complexity != "?":
                complexities.append((chart_complexity, chart['update_assessment'].get('type') if 'update_assessment' in chart else 'unknown'))
            if image_complexity != "-" and image_complexity != "?":
                complexities.append((image_complexity, main_image['update_assessment'].get('type') if main_image and 'update_assessment' in main_image else 'unknown'))
            
            if complexities:
                # Sort by priority: major > minor > patch
                priority = {'major': 3, 'minor': 2, 'patch': 1, 'unknown': 0}
                complexities.sort(key=lambda x: priority.get(x[1], 0), reverse=True)
                overall_complexity = complexities[0][0]
            
            # Truncate long version strings for table (max 40 chars)
            chart_version_display = chart_version[:40] + "..." if len(chart_version) > 40 else chart_version
            image_version_display = image_version[:40] + "..." if len(image_version) > 40 else image_version
            app_version_display = app_version[:30] + "..." if len(app_version) > 30 else app_version
            
            lines.append(f"| `{name}` | `{namespace}` | {chart_version_display} | {image_version_display} | {app_version_display} | {overall_complexity} |")
        
        lines.append("")
        lines.append("---")
        lines.append("")
        
        # Group by namespace
        by_namespace = {}
        for result in self.results:
            ns = result['namespace']
            if ns not in by_namespace:
                by_namespace[ns] = []
            by_namespace[ns].append(result)
        
        for namespace in sorted(by_namespace.keys()):
            lines.append(f"## Namespace: `{namespace}`")
            lines.append("")
            
            for result in sorted(by_namespace[namespace], key=lambda x: x['name']):
                lines.append(f"### {result['name']}")
                lines.append("")
                lines.append(f"- **File:** `{result['file_path']}`")
                lines.append("")
                
                # Chart info
                chart = result['chart']
                lines.append("#### Chart")
                lines.append(f"- **Name:** `{chart['name']}`")
                lines.append(f"- **Repository:** `{chart['repository']}`")
                lines.append(f"- **Current Version:** `{chart['current_version']}`")
                if chart['latest_version']:
                    if chart['current_version'] != chart['latest_version']:
                        lines.append(f"- **Latest Version:** `{chart['latest_version']}` ⚠️ **UPDATE AVAILABLE**")
                        
                        # Add update assessment
                        if 'update_assessment' in chart:
                            assessment = chart['update_assessment']
                            complexity_emoji = {'low': '🟢', 'medium': '🟡', 'high': '🔴'}.get(assessment['complexity'], '⚪')
                            lines.append(f"- **Update Type:** {complexity_emoji} **{assessment['type'].upper()}** ({assessment['complexity']} complexity)")
                            lines.append(f"- **Update Description:** {assessment['description']}")
                            
                            # Always add GitHub link as source
                            if 'github_repo' in chart:
                                lines.append(f"- **Source:** https://github.com/{chart['github_repo']}/releases/tag/{chart['latest_version']}")
                            
                            # Add release notes if available
                            if 'release_notes' in chart and chart['release_notes']:
                                release_notes = chart['release_notes']
                                if release_notes.get('published_at'):
                                    lines.append(f"- **Release Date:** {release_notes['published_at'][:10]}")
                                if release_notes.get('prerelease'):
                                    lines.append(f"- **Note:** This is a pre-release version")
                                
                                # Show full release notes
                                if release_notes.get('body'):
                                    body = release_notes['body'].strip()
                                    if body:
                                        lines.append(f"- **Release Notes:**")
                                        # Use markdown code block for better formatting
                                        lines.append(f"  ```markdown")
                                        # Limit to first 3000 chars to keep report manageable
                                        if len(body) > 3000:
                                            lines.append(f"  {body[:3000]}")
                                            lines.append(f"  ... (truncated, see source link above for full notes)")
                                        else:
                                            lines.append(f"  {body}")
                                        lines.append(f"  ```")
                            elif 'github_repo' in chart:
                                # If we have repo but no release notes (rate limited or not found)
                                lines.append(f"- **Release Notes:** *Could not fetch release notes (GitHub API rate limit or release not found). Check source link above.*")
                            
                            # Add breaking changes if any
                            if 'breaking_changes' in chart and chart['breaking_changes']:
                                # Filter out generic messages and show actual content
                                actual_breaking = [bc for bc in chart['breaking_changes'] 
                                                  if not bc.startswith('Major version change typically indicates') 
                                                  and not bc.startswith('Major version update - breaking changes likely')]
                                
                                if actual_breaking:
                                    lines.append(f"- **⚠️ Breaking Changes:**")
                                    for bc in actual_breaking:
                                        # Format breaking change content
                                        bc_lines = bc.split('\n')
                                        for bc_line in bc_lines[:10]:  # Limit to first 10 lines per breaking change
                                            if bc_line.strip():
                                                lines.append(f"  - {bc_line.strip()}")
                                        if len(bc_lines) > 10:
                                            lines.append(f"    ... (see source for full details)")
                                elif assessment['type'] == 'major':
                                    lines.append(f"- **⚠️ Breaking Changes:** *Major version update - review release notes above for breaking changes*")
                            elif assessment['type'] != 'patch':
                                lines.append(f"- **⚠️ Breaking Changes:** *Review release notes above for potential breaking changes*")
                            elif assessment['type'] == 'patch':
                                lines.append(f"- **⚠️ Breaking Changes:** *Patch updates typically don't have breaking changes - see release notes above*")
                        else:
                            lines.append(f"- **Update Assessment:** *Could not assess*")
                    else:
                        lines.append(f"- **Latest Version:** `{chart['latest_version']}` ✅ (up-to-date)")
                else:
                    lines.append(f"- **Latest Version:** *Could not determine*")
                lines.append("")
                
                # Image info
                if result['images']:
                    lines.append("#### Container Images")
                    for img in result['images']:
                        lines.append(f"- **Repository:** `{img['repository']}`")
                        lines.append(f"  - **Path:** `{img['path']}`")
                        lines.append(f"  - **Current Tag:** `{img['current_tag']}`")
                        if img['latest_tag']:
                            if img['current_tag'] != img['latest_tag'] and img['current_tag'] != 'latest':
                                lines.append(f"  - **Latest Tag:** `{img['latest_tag']}` ⚠️ **UPDATE AVAILABLE**")
                                
                                # Add update assessment
                                if 'update_assessment' in img:
                                    assessment = img['update_assessment']
                                    complexity_emoji = {'low': '🟢', 'medium': '🟡', 'high': '🔴'}.get(assessment['complexity'], '⚪')
                                    lines.append(f"  - **Update Type:** {complexity_emoji} **{assessment['type'].upper()}** ({assessment['complexity']} complexity)")
                                    lines.append(f"  - **Update Description:** {assessment['description']}")
                                    
                                    # Add breaking changes if any
                                    if 'breaking_changes' in img and img['breaking_changes']:
                                        lines.append(f"  - **⚠️ Breaking Changes Detected:**")
                                        for bc in img['breaking_changes']:
                                            lines.append(f"    - {bc}")
                                    
                                    # Add release notes information if available
                                    repo_info = self.get_repo_info_from_image(img['repository'])
                                    if repo_info:
                                        owner, repo = repo_info
                                        lines.append(f"  - **Source:** https://github.com/{owner}/{repo}/releases/tag/{img['latest_tag']}")
                                    
                                    if 'release_notes' in img and img['release_notes']:
                                        release_notes = img['release_notes']
                                        if release_notes.get('published_at'):
                                            lines.append(f"  - **Release Date:** {release_notes['published_at'][:10]}")
                                        if release_notes.get('prerelease'):
                                            lines.append(f"  - **Note:** This is a pre-release version")
                                        
                                        # Show full release notes
                                        if release_notes.get('body'):
                                            body = release_notes['body'].strip()
                                            if body:
                                                lines.append(f"  - **Release Notes:**")
                                                lines.append(f"    ```markdown")
                                                # Limit to first 3000 chars
                                                if len(body) > 3000:
                                                    lines.append(f"    {body[:3000]}")
                                                    lines.append(f"    ... (truncated, see source link above for full notes)")
                                                else:
                                                    lines.append(f"    {body}")
                                                lines.append(f"    ```")
                                    elif repo_info:
                                        lines.append(f"  - **Release Notes:** *Could not fetch release notes (GitHub API rate limit or release not found). Check source link above.*")
                                    
                                    # Add breaking changes for images
                                    if 'breaking_changes' in img and img['breaking_changes']:
                                        actual_breaking = [bc for bc in img['breaking_changes'] 
                                                          if not bc.startswith('Major version change typically indicates') 
                                                          and not bc.startswith('Major version update - breaking changes likely')]
                                        
                                        if actual_breaking:
                                            lines.append(f"  - **⚠️ Breaking Changes:**")
                                            for bc in actual_breaking:
                                                bc_lines = bc.split('\n')
                                                for bc_line in bc_lines[:10]:
                                                    if bc_line.strip():
                                                        lines.append(f"    - {bc_line.strip()}")
                                                if len(bc_lines) > 10:
                                                    lines.append(f"      ... (see source for full details)")
                                        elif assessment['type'] == 'major':
                                            lines.append(f"  - **⚠️ Breaking Changes:** *Major version update - review release notes above*")
                                else:
                                    lines.append(f"  - **Update Assessment:** *Could not assess*")
                            elif img['current_tag'] == 'latest' or (img['latest_tag'] and img['latest_tag'] == img['current_tag']):
                                lines.append(f"  - **Latest Tag:** `{img['latest_tag']}` ✅ (up-to-date)")
                            else:
                                lines.append(f"  - **Latest Tag:** `{img['latest_tag']}` ✅")
                        else:
                            lines.append(f"  - **Latest Tag:** *Could not determine*")
                        lines.append("")
                else:
                    lines.append("*No container images specified in values*")
                    lines.append("")
                
                lines.append("---")
                lines.append("")
        
        return '\n'.join(lines)


def main():
    # Get repository root
    script_dir = Path(__file__).parent
    repo_root = script_dir.parent
    
    # Check for GitHub token
    github_token = os.environ.get('GITHUB_TOKEN')
    
    checker = VersionChecker(str(repo_root), github_token=github_token)
    
    if checker.use_gh_cli:
        print(f"{Colors.GREEN}Using GitHub CLI (gh) for authenticated API access{Colors.RESET}")
    elif github_token:
        print(f"{Colors.GREEN}Using GitHub token for API access{Colors.RESET}")
    else:
        print(f"{Colors.YELLOW}No GitHub CLI or token found - using unauthenticated API (60 req/hour limit){Colors.RESET}")
        print(f"{Colors.YELLOW}Install and authenticate 'gh' CLI or set GITHUB_TOKEN for higher rate limits{Colors.RESET}\n")
    
    checker.check_all()
    
    # Generate report
    report = checker.generate_markdown_report()
    
    # Write to file
    output_file = repo_root / "docs" / "AI_version_check_current.md"
    with open(output_file, 'w') as f:
        f.write(report)
    
    print(f"\n{Colors.GREEN}=== Report Generated ==={Colors.RESET}")
    print(f"Saved to: {output_file}")


if __name__ == '__main__':
    main()

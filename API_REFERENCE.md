## API Reference

This document catalogs the public APIs, functions, tasks, and tools provided by this repository. It includes usage examples you can copy-paste.

### Requirements
- Python 3.11 or newer
- Python packages: see `requirements.txt`
- Common CLIs used by tasks: `age-keygen`, `sops`, `talhelper`, `kubectl`, `helmfile`, `kubeconform`, `yq`, `flux`

---

## Makejinja Plugin (`templates/scripts/plugin.py`)

This repository ships a Makejinja plugin that exposes filters, functions, and path filters into your Jinja templates during rendering.

### Filters
- **`basename(value: str) -> str`**: Returns the filename stem (without extension) of a path.
  - Example (Jinja):
    ```jinja2
    {{ 'kubernetes/apps/foo/values.yaml.j2' | basename }}  {# -> 'values.yaml' #}
    ```

- **`nthhost(value: str, query: int) -> str`**: Returns the Nth host in a CIDR range.
  - Inputs:
    - `value`: IPv4 CIDR, e.g. `192.168.1.0/24`
    - `query`: 0-based index within the network
  - Example (Jinja):
    ```jinja2
    {{ '192.168.1.0/24' | nthhost(10) }}  {# -> '192.168.1.10' #}
    ```

### Functions
These are available as Jinja globals during templating.

- **`age_public_key() -> str`**: Reads and returns the public key from `age.key`.
  - Expects a line like `# public key: age1...` inside `age.key`.
  - Raises if the file is missing or the public key cannot be found.
  - Example:
    ```jinja2
    # Age public key
    {{ age_public_key() }}
    ```

- **`age_private_key() -> str`**: Reads and returns the private key string from `age.key`.
  - Raises if the file is missing or the private key cannot be found.
  - Example:
    ```jinja2
    {{ age_private_key() }}
    ```

- **`cloudflare_tunnel(field: str) -> str | number | object | null`**: Reads `cloudflared.json` and returns the value for the provided `field`.
  - Requires `cloudflared.json` to exist (created by `cloudflared tunnel create --credentials-file cloudflared.json ...`).
  - Example:
    ```jinja2
    # Example fields commonly present include: TunnelID, AccountTag, TunnelName
    {{ cloudflare_tunnel('TunnelID') }}
    ```

- **`deploy_key() -> str`**: Returns the contents of `deploy.key` (private key for GitHub deploy).
  - Example:
    ```jinja2
    {{ deploy_key() }}
    ```

- **`talos_patches(subdir: str) -> list[str]`**: Returns a sorted list of Talos patch files in `templates/config/kubernetes/bootstrap/talos/patches/{subdir}` with extension `*.yaml.j2`.
  - If the directory does not exist, returns an empty list.
  - Example (Jinja loop):
    ```jinja2
    {% for patch in talos_patches('controller') %}
    # will render each patch path
    - {{ patch }}
    {% endfor %}
    ```

### Path Filters
- The plugin dynamically discovers any `.mjfilter.py` files under each `inputs` directory declared in Makejinja’s configuration. Each such file must export a `main(data: dict) -> bool` function.
- If `main(...)` returns `False`, the entire directory containing that `.mjfilter.py` (and its children) is excluded from rendering.
- Minimal example `.mjfilter.py`:
  ```python
  # .mjfilter.py
  def main(data):
      # Only render this directory if Cloudflare is enabled
      return bool(data.get('cloudflare', {}).get('enabled', False))
  ```

### Validation Hook
- During plugin initialization, `validation.validate(data)` is run. See Validation Utilities below for rules and how to adjust inputs to pass validation.

---

## Validation Utilities (`templates/scripts/validation.py`)

Helpers for validating `config.yaml` inputs prior to rendering.

### Decorator
- **`required(*keys: str)`**: Ensures a wrapped validator receives certain keys from the root data dict. If a key is missing, a `ValueError` is raised before the wrapped function executes.
  - Example:
    ```python
    from validation import required

    @required('dns_servers')
    def validate_custom(dns_servers: list, **_):
        assert isinstance(dns_servers, list)
    ```

### Validators
- **`validate_python_version() -> None`**
  - Requires Python ≥ 3.11.

- **`validate_node(node: dict, node_cidr: str) -> None`**
  - Enforces:
    - `name`: non-empty, matches `^[a-z0-9-]+$`, and not one of `global`, `controller`, `worker`.
    - `disk`: non-empty.
    - `mac_addr`: lowercase MAC matching `^([0-9a-f]{2}[:]){5}([0-9a-f]{2})$`.
    - `schematic_id`: 64 lowercase hex chars `^[a-z0-9]{64}$`.
    - `address`: valid IPv4 and within `node_cidr`.
    - TCP connectivity to `address:50000` (Talos maintenance port) is possible.

- **`validate_nodes(node_cidr: str, nodes: list[dict], **_) -> None`**
  - `node_cidr` must be an IPv4 CIDR.
  - Controllers: odd count and ≥ 1.
  - Runs `validate_node` for each controller and worker node.

- **`validate_dns_servers(servers: list = ["1.1.1.1","1.0.0.1"], **_) -> None`**
  - Uses dnspython to resolve `cloudflare.com` through the provided nameservers.

- **`validate_ntp_servers(servers: list = ["162.159.200.1","162.159.200.123"], **_) -> None`**
  - Uses `ntplib` to request time from each server.

- **`validate_github_repository(github: dict, **_) -> None`**
  - Requires `github.repository` with pattern `[A-Za-z0-9-_]+/[A-Za-z0-9-_]+`.

- **`validate(data: dict) -> None`**
  - Composite entrypoint that runs the above checks.

### Programmatic usage example
```python
import yaml
from templates.scripts import validation

with open('config.yaml') as f:
    data = yaml.safe_load(f)

# Raises ValueError on any failed check
validation.validate(data)
```

---

## Configuration (`config.sample.yaml`)

Fill out `config.yaml` based on `config.sample.yaml`. Key fields:
- **Cluster networking**
  - `node_network` (required): IPv4 CIDR for node LAN, e.g. `192.168.1.0/24`
  - `pod_network` (required): non-overlapping pod CIDR, default `10.69.0.0/16`
  - `service_network` (required): non-overlapping service CIDR, default `10.96.0.0/16`
  - `controller_vip` (required): IP for the Kubernetes API VIP
  - `tls_sans` (optional): Additional SANs for the API certificate

- **Inventory**
  - `node_inventory` (required): list of nodes with `name`, `address`, `controller`, `disk`, `mac_addr`, `schematic_id`, plus advanced options like `mtu`, `secureboot`, `encrypt_disk`.

- **DNS and NTP**
  - `dns_servers` (required): default Cloudflare DNS
  - `ntp_servers` (required): default Cloudflare NTP

- **GitHub (Flux)**
  - `github.repository` (required), `github.branch` (required)
  - `github.webhook_token` (required)
  - `github.private` (optional): set to `true` when using a private repository and deploy key

- **Cloudflare (optional feature set)**
  - `cloudflare.enabled`: gate for all Cloudflare features
  - `cloudflare.domain`, `cloudflare.token` (required when enabled)
  - `cloudflare.acme.production`: switch to Let’s Encrypt production once ready
  - VIPs: `cloudflare.ingress_vip`, `cloudflare.gateway_vip`
  - Cloudflare Tunnel: `cloudflare.tunnel.ingress_vip`

- **Advanced**
  - `node_default_gateway`, `vlan`, `loadbalancer_mode`, `bgp` options, and `dual_stack_ipv4_first`

---

## Task Runner Commands

Tasks are defined in the root `Taskfile.yaml` and under `.taskfiles/`. Your Task version may support calling included tasks directly as shown below.

- **Root tasks**
  - `task` (default): list tasks
  - `task reconcile`: Force Flux to reconcile the `flux-system` Kustomization

- **Bootstrap** (`.taskfiles/bootstrap/Taskfile.yaml`)
  - `task bootstrap:talos`: Bootstrap the Talos cluster
  - `task bootstrap:apps`: Bootstrap base apps into the cluster

- **Talos** (`.taskfiles/talos/Taskfile.yaml`)
  - `task talos:generate-config`: Generate Talos configuration
  - `task talos:apply-node IP=<addr> [MODE=auto|... ]`: Apply Talos config to a node
  - `task talos:upgrade-node IP=<addr>`: Upgrade Talos on a single node
  - `task talos:upgrade-k8s`: Upgrade Kubernetes to version in `talconfig.yaml`
  - `task talos:reset`: Reset nodes back to maintenance mode

- **Template** (`.taskfiles/template/Taskfile.yaml`)
  - `task template::init` or `task init` (depending on Task version): Initialize configuration files and keys
  - `task template::configure` or `task configure`: Render, encrypt, and validate configuration
  - `task template:render-configs`: Run Makejinja to render templates
  - `task template:encrypt-secrets`: Encrypt all `*.sops.*` files with SOPS
  - `task template:validate-kubernetes-config`: Validate manifests with `kubeconform`
  - `task template:validate-talos-config`: Validate Talhelper configuration
  - `task template:debug`: Gather common resources across namespaces
  - `task template:tidy`: Archive template-related files/dirs after setup

> See the main `README.md` for a guided, end-to-end flow.

---

## Shell Tools (`tools/`)

- **`find-stale-dns-entry-in-cf.sh`**: Lists TXT “heritage” records from Cloudflare that point to Kubernetes resources and flags those whose backing resource no longer exists.
  - Prerequisites: `CF_API_TOKEN`, `kubectl`, `jq`, a Cloudflare zone
  - Edit the domain inside the script (line that queries `zones?name=<your-domain>`)
  - Example:
    ```bash
    export CF_API_TOKEN=...  # Cloudflare API Token with Zone DNS Read
    ./tools/find-stale-dns-entry-in-cf.sh
    ```

- **`intel-ipex-ollama-debug.sh`**: Launches a privileged Ubuntu pod with Intel GPU access, installs Intel GPU runtime + IPEX-LLM build of Ollama, and exposes port 11434.
  - Prerequisites: Kubernetes cluster with Intel GPU device plugin (`gpu.intel.com/i915`), `kubectl`
  - Creates service `ollama-service` in namespace `ai`
  - Example:
    ```bash
    kubectl create namespace ai || true
    ./tools/intel-ipex-ollama-debug.sh
    # Then in the pod, start the server: /start-ollama.sh
    ```

- **`intel-llama.cpp-debug.sh`**: Launches `ghcr.io/ggml-org/llama.cpp:full-intel` with Intel GPU access, exposing an OpenAI-compatible server on port 8080.
  - Prerequisites: Intel GPU device plugin, `kubectl`
  - Example:
    ```bash
    kubectl create namespace ai || true
    ./tools/intel-llama.cpp-debug.sh
    # Optionally port-forward:
    kubectl -n ai port-forward llama-cpp-intel-gpu 8080:8080
    ```

- **`test-llama-connection.sh`**: Validates that the llama.cpp server and service are reachable.
  - Example:
    ```bash
    ./tools/test-llama-connection.sh
    ```

- **`snmp-temp-scan.sh`**: Discovers UniFi devices, probes SNMP temperature OIDs, and prints a table suitable for Uptime Kuma.
  - Examples:
    ```bash
    # Controller-based discovery (recommended)
    ./tools/snmp-temp-scan.sh -h unifi.example.com -t <JWT>

    # Fixed host list
    ./tools/snmp-temp-scan.sh 192.168.30.1 192.168.30.220

    # SNMPv3
    ./tools/snmp-temp-scan.sh -v 3 -u user -A authpass -X privpass 192.168.30.1
    ```

---

## Jinja Usage Examples

- Use Cloudflare Tunnel ID in a rendered manifest:
  ```jinja2
  apiVersion: v1
  kind: Secret
  metadata:
    name: cloudflared-credentials
  stringData:
    tunnelID: "{{ cloudflare_tunnel('TunnelID') }}"
  ```

- Iterate Talos patches dynamically:
  ```jinja2
  patches:
  {% for p in talos_patches('controller') %}
    - {{ p }}
  {% endfor %}
  ```

- Insert deploy key into a Secret:
  ```jinja2
  apiVersion: v1
  kind: Secret
  metadata:
    name: flux-deploy-key
  stringData:
    key: |
      {{ deploy_key() | indent(width=6) }}
  ```

---

## Troubleshooting
- Validation fails for nodes: verify `node_network`, `node_inventory` contents, and ensure port 50000 on each node is reachable.
- DNS validation fails: confirm `dns_servers` allow resolving `cloudflare.com` from your network.
- NTP validation fails: ensure outbound UDP/123 to your NTP servers.
- Cloudflare functions fail: verify `cloudflared.json` exists and contains expected fields; verify `age.key` and `deploy.key` exist where expected.

---

## Appendix: Installation

- Python
  ```bash
  mise run deps            # if using mise
  python -m venv .venv && source .venv/bin/activate
  pip install -r requirements.txt
  ```

- Render and validate (typical flow)
  ```bash
  task init         # or: task template::init
  task configure    # or: task template::configure
  ```
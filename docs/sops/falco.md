# SOP: Falco Runtime-Security Rule Exception Tuning

> Description: How to add a scoped, benign-workload exception to a built-in Falco rule when a legitimate container trips a runtime-security alert (typically a Critical "Drop and execute new binary in container" → Wazuh level-12), without blinding the rule globally.
> Version: `2026.07.14`
> Last Updated: `2026-07-14`
> Owner: `security / cluster-ops`

---

## 1) Description

Falco runs as a DaemonSet on every node and forwards syscall events to Wazuh.
Some legitimate workloads (package managers, init containers that bootstrap a
toolchain, self-extracting AppImages, privileged CNI init) execute binaries
from a writable overlay layer, which trips built-in Falco rules and floods the
SIEM. The fix is a **tightly-scoped exception appended to the offending rule**,
never a global disable.

This has become a recurring pattern — prior exceptions cover openclaw
(`install-openclaw` pip init), dpkg/apt/py3compile, cilium
(`mount-cgroup` / `apply-sysctl-overwrites`), Nextcloud Collabora Office
(AppImage `coolwsd`/`coolforkit`), and most recently (2026-07-14) the mcpo
`runtime-setup` init container. This SOP captures the mechanism so the next one
takes minutes.

- Scope: `security` namespace, Falco DaemonSet, its rule overrides in
  `kubernetes/apps/security/falco/app/helmrelease.yaml`
- Prerequisites: `kubectl` (VLAN 55 access), local SOPS age key (not needed to
  read the helmrelease — it is not encrypted), write access to the repo, GitOps/Flux
- Out of scope: authoring brand-new Falco rules; the Wazuh decoder/ruleset side
  (see `docs/sops/monitoring.md` and the Wazuh local-rule memory)

---

## 2) Overview

| Setting | Value |
|---------|-------|
| Namespace | `security` |
| Source of truth | `kubernetes/apps/security/falco/app/helmrelease.yaml` |
| Chart | `falco` (falcosecurity HelmRepository), version `9.1.0` |
| Deploy shape | DaemonSet, one pod per node (3 nodes incl. control planes) |
| Driver | `modern_ebpf` (CO-RE eBPF, no kmod) |
| Rule mechanism | `values.customRules.<file>.yaml` with `override.condition: append` (rules) / `replace` (macros) |
| Event sink | JSON → `/var/run/falco/falco.log` on host → wazuh-agent tails → Wazuh manager |
| The noisy rule | `Drop and execute new binary in container` — output "Executing binary not part of base image", priority `Critical` → Wazuh level-12 |
| Critical dependency | Falco **crash-loops on a malformed rule condition** — invalid YARA/condition syntax = no clean roll |

---

## 3) Blueprints

- Source of truth file: `kubernetes/apps/security/falco/app/helmrelease.yaml`
- Exceptions live under `spec.values.customRules`, keyed by pseudo-filename:
  - `apt-dpkg-noise.yaml` — the append override on the drop-and-exec rule
    (all the exclusions below live here)
  - `k8s-api-noise.yaml` — `replace` overrides on two `user_known_*` macros
    (Contact K8S API / Redirect STDOUT-STDIN allowlists)

The established mechanism for **adding an exclusion to a built-in rule** is to
re-declare the rule by name, provide **only** an additional `condition`
fragment, and set `override.condition: append`. Falco concatenates your
fragment onto the shipped condition — so you keep the base rule's own
exclusions instead of discarding them (a past `replace` wiped the base
exclusions and made the rule fire on Longhorn's engine binary at 10k+/hr).

```yaml
# The canonical append pattern (real content, abbreviated)
customRules:
  apt-dpkg-noise.yaml: |-
    - rule: Drop and execute new binary in container
      # APPEND (not replace) — keep the chart's built-in exclusions intact.
      condition: >
        and not (
          proc.name in (dpkg, apt, apt-get, py3compile) or
          proc.exepath startswith /data/longhorn or
          container.name in (install-openclaw, mount-cgroup, apply-sysctl-overwrites) or
          (container.name = nextcloud and (proc.exepath startswith /tmp/appimage_extracted or proc.name in (coolwsd, coolforkit, coolforkit-ns, coolmount))) or
          (k8s.ns.name = ai and k8s.pod.name startswith mcpo and container.name = runtime-setup and container.image.repository = docker.io/library/python)
        )
      override:
        condition: append
```

Note the leading `and` in the appended `condition`: because the override is
concatenated onto the base condition, the fragment starts with `and not ( ... )`.
Everything inside the `not ( ... )` is an OR-list of exclusions.

---

## 4) Operational Instructions

### The scoping principle (read this first)

An added OR-term inside `not ( ... )` can **only remove events from that one
rule** — it can never add coverage or affect any other rule. To make sure your
exclusion cannot over-suppress, **match on ALL of: namespace + pod + container +
image**, so it applies to exactly one workload:

```
(k8s.ns.name = ai and k8s.pod.name startswith mcpo and container.name = runtime-setup and container.image.repository = docker.io/library/python)
```

With all four ANDed, the same rule still fires for:
- the mcpo `app` container (different `container.name`),
- a differently-named pod in `ai`,
- any other namespace,
- a workload on a different base image.

Under-scoping (e.g. `k8s.ns.name = ai` alone) blinds the rule for a whole
namespace — do not do that.

### Steps

1. **Confirm the event is benign.** Identify the exact rule and the process /
   image / container that tripped it (Section 8). A supply-chain-dropped binary
   is NOT benign — only exclude workloads you understand.
2. **Compose the tightest matching clause** (ns + pod + container + image).
   Optionally narrow further by process name (see the variant below).
3. **Edit** `spec.values.customRules.apt-dpkg-noise.yaml`: add your clause as a
   new `or ( ... )` term inside the existing `and not ( ... )` block, and add a
   comment paragraph above the `condition:` explaining the workload, the event
   count/day, the date verified, and the finding ID.
4. **Commit + push** (GitOps only — no direct cluster edits, no manual
   reconcile by default). Flux webhook rolls the HelmRelease.
5. **Verify** the roll is clean (Section 6): no `[error]` lines, HelmRelease
   Ready, DaemonSet fully rolled, and the event stops.

```bash
# GitOps flow — stage ONLY the helmrelease
git add kubernetes/apps/security/falco/app/helmrelease.yaml
git commit -m "fix(falco): scope-exclude <workload> from <rule>"
git push
```

### Two clause variants

**Whole-container scope** (used for one-shot init containers with no
long-running workload to protect — openclaw, cilium, mcpo runtime-setup):

```
(k8s.ns.name = ai and k8s.pod.name startswith mcpo and container.name = runtime-setup and container.image.repository = docker.io/library/python)
```

**Process-narrowed variant** (tighter — only the known binaries are excluded, a
different dropped binary in the same init container still fires):

```
(k8s.ns.name = ai and k8s.pod.name startswith mcpo and container.name = runtime-setup and container.image.repository = docker.io/library/python and proc.name in (curl, gpg, node, npm))
```

The Nextcloud Collabora exclusion already uses the process-narrowed form
(`proc.name in (coolwsd, coolforkit, coolforkit-ns, coolmount)`).

### Known tension (documented 2026-07-14, security-agent)

Whole-container scope means a **supply-chain-dropped binary inside that one init
container is invisible to THIS rule during init**. That is an accepted trade for
a deterministic one-shot init container (it only bootstraps a toolchain and
exits; there is no persistent workload). If the excluded container is anything
other than a trusted one-shot init, prefer the process-narrowed variant. Other
Falco rules (network, file, privilege) are unaffected either way — only this one
rule is scoped down, only for this one workload.

---

## 5) Examples

### Example A: mcpo runtime-setup (the 2026-07-14 canonical case)

The `mcpo` pod (`apps/ai/mcpo`, MCP-over-OpenAPI proxy for open-webui) runs an
initContainer `runtime-setup` on a stock `python:3.11-slim` base. It bootstraps
the Node/npm toolchain on every pod start: `curl` fetches the nodesource gpg
key, `gpg --dearmor`s it, `node` runs `npm install -g` — all from a writable
overlay layer (`EXE_WRITABLE|EXE_UPPER_LAYER`). That trips
`Drop and execute new binary in container` 3× per pod start (finding
`F-2804f72b`). These are not apt/dpkg binaries, so the package-manager clauses
above miss them.

```yaml
# appended term inside the and not ( ... ) block
(k8s.ns.name = ai and k8s.pod.name startswith mcpo and container.name = runtime-setup and container.image.repository = docker.io/library/python)
```

Commit `27f091cf` ("fix(falco): scope-exclude mcpo runtime-setup init from
drop-and-exec rule").

### Example B: prior exclusions in the same rule (reference)

| Workload | Clause style | Why |
|---|---|---|
| dpkg/apt/py3compile | `proc.name` / `proc.sname` / `proc.aname[1..3]` | package-manager activity (ancestor + session-leader + the exec itself) |
| openclaw `install-openclaw` | `container.name in (install-openclaw, ...)` | initContainer that `pip install`s ~52 CLIs on each start (~104 events/24h) |
| cilium `mount-cgroup` / `apply-sysctl-overwrites` | `container.name in (..., mount-cgroup, apply-sysctl-overwrites)` | privileged CNI bootstrap, ~6 events per cluster-wide cilium roll |
| Nextcloud Collabora | `container.name = nextcloud and (proc.exepath startswith /tmp/appimage_extracted or proc.name in (coolwsd, ...))` | Office AppImage self-extracts + runs from `/tmp`, ~9 events/day |
| Longhorn engine | `proc.exe / proc.exepath startswith /data/longhorn` | engine-launcher binary path |

---

## 6) Verification Tests

### Test 1: no Falco error lines across all pods (clean rule syntax)

```bash
for p in $(kubectl -n security get pods -l app.kubernetes.io/name=falco -o name); do
  echo "== $p =="; kubectl -n security logs "$p" -c falco --tail=200 | grep -c '\[error\]'
done
```

Expected:
- `0` on every pod (3 pods). Falco loaded the ruleset without a syntax error.

If failed:
- A non-zero count / `CrashLoopBackOff` means a malformed condition. Read the
  error line (`kubectl -n security logs <pod> -c falco | grep -i error`), fix
  the YAML/condition (unbalanced parens, stray comma, bad field name), re-push.

### Test 2: HelmRelease Ready and DaemonSet fully rolled

```bash
flux -n security get helmreleases falco
kubectl -n security rollout status ds/falco --timeout=5m
kubectl -n security get pods -l app.kubernetes.io/name=falco
```

Expected:
- HelmRelease `Ready=True`, reconciled at the new revision.
- DaemonSet: desired == ready == up-to-date, all pods `Running`.

If failed:
- If Ready=False with a rollback, the condition likely broke Falco startup —
  see Test 1. Check `kubectl -n security describe hr falco` events.

### Test 3: the target event stops firing

```bash
# Restart the excluded workload, then confirm no new rule event for it.
kubectl -n ai delete pod -l app.kubernetes.io/name=mcpo
kubectl -n security exec ds/falco -c falco -- \
  sh -c "grep 'Executing binary not part of base image' /var/run/falco/falco.log | tail -5"
```

Expected:
- No new line naming the excluded container after the restart.

If failed:
- The clause did not match. Re-check the exact field values (Section 8) — a
  common miss is `container.image.repository` including/excluding the
  `docker.io/library/` prefix, or `k8s.pod.name` needing `startswith`.

---

## 7) Troubleshooting

| Symptom | Likely Cause | First Fix |
|---------|--------------|-----------|
| Falco pod `CrashLoopBackOff` after a rule edit | Malformed `condition` (unbalanced parens, bad field, trailing `or`) | `kubectl -n security logs <pod> -c falco \| grep -i error`; fix syntax; re-push |
| HelmRelease rolled back to prior revision | Falco failed to start within timeout on the new ruleset | Same as above — the ruleset is the cause; the `upgrade.remediation: rollback` reverted it |
| Event still fires after exclusion | Clause under-matched | Verify actual field values vs the clause; watch the `docker.io/library/` image prefix and `startswith` on pod names |
| A whole namespace went quiet on this rule | Clause over-matched (e.g. only `k8s.ns.name`) | Re-scope to ns+pod+container+image; a real intrusion in that ns could be hidden |
| Base exclusions disappeared, unrelated workloads now fire | Used `override.condition: replace` on a rule instead of `append` | Switch back to `append` — `replace` discards the chart's built-in exclusions |

```bash
# Quick state
kubectl -n security get pods -l app.kubernetes.io/name=falco
kubectl -n security logs ds/falco -c falco --tail=100 | grep -iE 'error|rule|loaded'
flux -n security get hr falco
```

---

## 8) Diagnose Examples

### Diagnose Example 1: find the exact firing rule + event fields (Falco side)

The DaemonSet writes JSON events to `/var/run/falco/falco.log` (host path, also
tailed by the wazuh-agent). Grep it for the offending pod/rule and read the
`output_fields`.

```bash
# On any falco pod, filter to the drop-and-exec rule for the suspect pod
kubectl -n security exec ds/falco -c falco -- \
  sh -c "grep 'Executing binary not part of base image' /var/run/falco/falco.log | tail -20"

# Pull the fields that a clause matches on (ns, pod, container, image, proc)
kubectl -n security exec ds/falco -c falco -- \
  sh -c "grep runtime-setup /var/run/falco/falco.log | tail -1" | python3 -c "
import sys, json
e = json.loads(sys.stdin.read())
f = e.get('output_fields', {})
for k in ('k8s.ns.name','k8s.pod.name','container.name','container.image.repository','proc.name','proc.exepath'):
    print(k, '=', f.get(k))
print('flags:', f.get('evt.arg.flags'))"
```

Expected:
- The exact `k8s.ns.name`, `k8s.pod.name`, `container.name`,
  `container.image.repository`, and `proc.name` to build the clause. Confirm the
  writable-layer flags (`EXE_WRITABLE|EXE_UPPER_LAYER`) — that is why it fires.

If unclear:
- Grep by the rule text across all three pods (the event may be on one node
  only); or read it from the Wazuh side (Diagnose Example 2).

### Diagnose Example 2: confirm from the Wazuh/SIEM side

The bundled `falco-json` decoder surfaces these as wazuh-alerts. The
drop-and-exec rule maps to Wazuh **level-12** (this is what drives a red SIEM
verdict). Cross-check the count and the driving finding there.

```bash
# From the security sweep / Wazuh: count level-12 falco events by container in 24h
# (illustrative — use the sweep's Wazuh query path)
kubectl -n security exec ds/falco -c falco -- \
  sh -c "grep -c 'Executing binary not part of base image' /var/run/falco/falco.log"
```

Expected:
- The event count/day matches what the security-agent reported (e.g. 3 per mcpo
  pod start). If it is a burst tied to pod restarts/rolls, it is init-time noise
  → good exclusion candidate. If it is steady-state from a long-running
  container, investigate before excluding.

If unclear:
- Escalate to the security-agent; a steady exec of new binaries from a
  long-running app container is a real signal, not noise.

---

## 9) Health Check

```bash
# All 3 falco pods Running, 0 error lines, HR Ready
kubectl -n security get pods -l app.kubernetes.io/name=falco
for p in $(kubectl -n security get pods -l app.kubernetes.io/name=falco -o name); do
  kubectl -n security logs "$p" -c falco --tail=300 | grep -c '\[error\]'
done
flux -n security get hr falco
# Rule fragment present as expected
grep -c 'condition: append' kubernetes/apps/security/falco/app/helmrelease.yaml
```

Expected:
- 3 pods `Running`, each `0` error lines, HelmRelease `Ready=True`.
- The append override is still present; no rule was accidentally switched to
  `replace`.

---

## 10) Security Check

```bash
# No plaintext secrets introduced (helmrelease is not a secret file)
grep -iE 'password|token|api[_-]?key' kubernetes/apps/security/falco/app/helmrelease.yaml || echo "clean"
# Every exclusion is scoped (no bare namespace-only or bare rule disable)
grep -nE 'k8s.ns.name|container.name|container.image.repository' kubernetes/apps/security/falco/app/helmrelease.yaml
```

Expected:
- No plaintext secrets in the helmrelease.
- Each added exclusion matches a specific workload (ns+pod+container+image, or a
  concrete `container.name`/`proc.exepath`), NOT a whole namespace or a global
  rule disable.
- The rule remains `Critical`/level-12 for every other workload — the change
  removed events from exactly one benign workload and nothing else.

---

## 11) Rollback Plan

The change is a single commit to the helmrelease. Revert it and let Flux roll
Falco back.

```bash
# Revert the exclusion commit (GitOps)
git revert --no-edit 27f091cf   # replace with the SHA of the exclusion commit
git push
# Watch Falco re-roll on the reverted ruleset
kubectl -n security rollout status ds/falco --timeout=5m
flux -n security get hr falco
```

Expected after rollback:
- Falco rolls cleanly on the prior ruleset (the excluded event resumes firing —
  that is the pre-change baseline).

---

## 12) References

- Source manifest: `kubernetes/apps/security/falco/app/helmrelease.yaml`
- `docs/sops/monitoring.md` — Prometheus/Wazuh/ELK access, event-log patterns
- Wazuh local-rule authoring: memory `project_wazuh_local_rule_authoring.md`
- Falco fields reference: <https://falco.org/docs/reference/rules/supported-fields/>
- Wazuh + Falco integration: <https://wazuh.com/blog/cloud-native-security-with-wazuh-and-falco/>

---

## Version History

- `2026.07.14`: Initial SOP. Documents the `override.condition: append`
  exception mechanism on `Drop and execute new binary in container`, the
  ns+pod+container+image scoping principle, whole-container vs process-narrowed
  variants, and the crash-loop-on-malformed-condition constraint. Canonical
  example: mcpo `runtime-setup` (commit `27f091cf`). Cross-references the prior
  openclaw / dpkg-apt / cilium / Nextcloud-Collabora exclusions.

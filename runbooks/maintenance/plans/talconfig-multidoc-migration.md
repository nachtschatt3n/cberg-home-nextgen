---
plan_id: talconfig-multidoc-migration
component: talos
pr: null                              # no Renovate PR: a config-FORM migration, not a version bump
kind: infra
current: "talconfig v1alpha1 form (talhelper 3.1.11 pin; `task talos:generate-config` FAILS on main since cad2bd3f)"
target: "talconfig multi-document form for Talos v1.14.1 (talhelper 3.1.17), same effective machine config"
update_type: migration
risk: high                            # NOT because the diff is large — it is semantically zero
                                      # (§1, Appendix B) — but because the blast radius of a wrong
                                      # one is the whole cluster: the apply restarts kube-apiserver on
                                      # all three control-plane nodes, and ONE wrong field (the etcd
                                      # encryption key NAME) makes every Secret unreadable. talhelper's
                                      # own auto-migration gets that field wrong and still validates
                                      # (exit 0). Operator present.
est_duration_min: 80                  # premises+pre-checks 10, repo edit+sops+commit 10, render +
                                      # semdiff + negative control + 3 dry-runs 10, per node
                                      # (baseline, apply, gates, 5-min settle) ~12 x 3 = 36,
                                      # clusterconfig regen + final gates + finding close 10, slack 4.
needs_reboot: false                   # MEASURED: `talosctl apply-config --dry-run --mode=auto` on all
                                      # three nodes 2026-09-28 -> "Applied configuration without a
                                      # reboot" (and --mode=no-reboot accepted). The plan applies with
                                      # --mode=no-reboot so a change that WOULD need a reboot errors
                                      # out instead of rebooting.
touches:
  namespaces: [kube-system]
  resources:
    - talos-machineconfig/k8s-nuc14-01     # apply-config (no reboot)
    - talos-machineconfig/k8s-nuc14-02
    - talos-machineconfig/k8s-nuc14-03
    - pod/kube-apiserver-k8s-nuc14-0{1,2,3}   # static pods re-rendered: flag --anonymous-auth=false
                                              # becomes --authentication-config (anonymous disabled) ->
                                              # each apiserver restarts once, serially
    - pod/kube-controller-manager-k8s-nuc14-0{1,2,3}   # args unchanged; may be re-rendered
    - pod/kube-scheduler-k8s-nuc14-0{1,2,3}            # args unchanged; may be re-rendered
    - file/kubernetes/bootstrap/talos/talconfig.yaml
    - file/kubernetes/bootstrap/talos/patches/**
    - file/kubernetes/bootstrap/talos/talenv.sops.yaml   # NEW, sops-encrypted (whole file)
    - file/.mise.toml                                    # talhelper 3.1.11 -> 3.1.17
    - file/docs/sops/talos-upgrade.md                    # banner + §14.2 "consequences" retired
  shared: [control-plane/kube-apiserver, etcd-encryption, talos-machineconfig, node-resolver/hostDNS, talos-discovery]
                                      # every API client (Flux, operators, kubectl) sees one
                                      # apiserver restart per node behind the VIP 192.168.55.10.
depends_on: []
conflicts_with: [talos-linux-1.14.2] # reciprocity: that roll depends_on this plan (it MUST run
                                      # second, talos-linux-1.14.2 §6.1); never one slot. Also: §4 reads etcd/apiserver metrics through Prometheus; no OPEN
                                      # kube-prometheus-stack plan exists (91.4.1 executed 2026-09-26).
                                      # Everything else is covered by `exclusive: true` below: no other
                                      # change may be in flight while the control plane is re-rendered
                                      # node by node. flux-reconciler-impersonation is ALSO exclusive
                                      # (sun-attended:2026-10-11) -> the two need separate windows.
exclusive: true
security_ref: null
capability_change: false              # effective config identical (Appendix B); the only rendered
                                      # delta is the install image tag v1.13.10 -> v1.14.1, which the
                                      # nodes already RUN (used only by a future install/upgrade).
rollback_class: backup-restore        # the rollback is re-applying each node's saved pre-apply live
                                      # machineconfig (proven accepted, no reboot, "No changes" on a
                                      # self-apply dry-run 2026-09-28), plus a git revert. Flux does
                                      # not reconcile kubernetes/bootstrap/talos/, so git-revert alone
                                      # does nothing to the nodes.
backup_gate: "per-node pre-apply live machineconfig saved to the mode-700 window scratch dir as $W/backup/live-<ip>.yaml (spec of `talosctl get machineconfig v1alpha1 -o yaml`), non-empty, re-parsed as YAML, and PROVEN re-appliable by `talosctl -n <ip> apply-config --dry-run --mode=no-reboot -f $W/backup/live-<ip>.yaml` printing 'Config diff:' + 'No changes.' — BEFORE that node's real apply"
finding_refs: [F-59b12b2b]            # "Talos 1.15 blocker: talconfig must migrate to multi-document
                                      # config" (section plan, deferred). Queried 2026-09-28 with
                                      # SWEEP_PG_DSN up: `finding list --grep talconfig|talhelper|
                                      # multi-doc` -> only this id.
review: ready-for-go@2026-09-28   # plan-reviewer-agent, 2nd pass (1st: needs-fix B1-B3, fixed)
status: awaiting-go  # 2026-09-28 go_no_go ingested (data-loss decision) — was: vetted;
window: "sun-attended:2026-10-04"   # SCHEDULED 2026-09-28 by maintenance-window-agent (operator: "schedule everything that needs to be scheduled"); GO pending: etcd/control-plane config, exclusive slot
premises:
  - id: nodes-on-talos-1.14.1
    why: "The migration renders for talosVersion v1.14.1 and was measured against v1.14.1 nodes. A node on another version invalidates the dry-run reboot verdict and the semantic baseline."
    run: kubectl get nodes -o jsonpath='{.items[*].status.nodeInfo.osImage}'
    expect_exact: "Talos (v1.14.1) Talos (v1.14.1) Talos (v1.14.1)"
  - id: apiserver-anonymous-auth-false
    why: "kube-authentication.yaml exists to reproduce the LIVE --anonymous-auth=false. If the live flag changed, the patch no longer means 'same effective value'."
    run: kubectl get pod -n kube-system kube-apiserver-k8s-nuc14-01 -o jsonpath='{.spec.containers[0].command}'
    expect_contains: "--anonymous-auth=false"
  - id: encryption-layout-key2-identity
    why: "kube-etcd-encryption.yaml pins [secretbox key2, identity] because that is what stored Secrets are prefixed with. If the live layout differs, applying the pinned layout could make Secrets unreadable."
    run: "talosctl --nodes=192.168.55.11 read /system/secrets/kubernetes/kube-apiserver/encryptionconfig.yaml | grep -e 'name: key' -e identity"
    expect_matches: "name: key2[\\s\\S]*identity"
  - id: kubernetes-registry-still-disabled
    why: "The migration drops the v1alpha1 discovery block, which makes the Kubernetes registry OFF in v1.14. That only equals live while live has it off."
    run: talosctl --nodes=192.168.55.11 get discoveryconfig -o yaml | grep registryKubernetesEnabled
    expect_exact: "registryKubernetesEnabled: false"
  - id: repo-still-pre-migration
    why: "Steps apply a pre-staged diff against the v1alpha1 form of patches/controller/cluster.yaml. If it already moved, the diff will not apply and the plan is stale."
    run: grep -c 'apiServer:' kubernetes/bootstrap/talos/patches/controller/cluster.yaml
    expect_exact: "1"
  - id: apiserver-has-no-probes-live
    why: "kube-apiserver.yaml sets startupProbes:false to keep the LIVE static pod probe-less (v1alpha1 shim). If live apiservers already carry probes, that is no longer 'same effective value'. Prints 'NOPROBE' only when both probes are absent (a pipe cannot be used: the premise runner splits on it)."
    run: kubectl get pod -n kube-system kube-apiserver-k8s-nuc14-01 -o jsonpath='{.spec.containers[0].livenessProbe.httpGet.path}NOPROBE{.spec.containers[0].startupProbe.httpGet.path}'
    expect_exact: "NOPROBE"
  - id: talhelper-pin-still-3.1.11
    why: "3.1.11 cannot decode the new document kinds ('KubeAPIServerConfig v1alpha1: not registered', measured); the plan bumps the pin. A different pin means re-render and re-verify."
    run: grep -c '^talhelper = "3.1.11"' .mise.toml
    expect_exact: "1"
sops_refs:
  - docs/sops/talos-upgrade.md
  - docs/sops/application-update.md
  - docs/sops/verification-contents-not-shape.md
generated: "2026-09-28"
---

# talconfig v1alpha1 → multi-document migration (Talos v1.14.1)

## 1. Summary & why held

**What changes.** `kubernetes/bootstrap/talos/talconfig.yaml` and its patches move the
six settings that talhelper ≥3.1.17 / Talos v1.14 now own as dedicated documents
out of the deprecated v1alpha1 fields:

| was (v1alpha1) | now (v1.14 document) | file |
|---|---|---|
| `cluster.discovery` (service on, kubernetes registry off) | `DiscoveryServiceConfig` (talhelper default, endpoint `https://discovery.talos.dev/`); the kubernetes registry is driven ONLY by the legacy block, so its absence = off | `patches/controller/cluster.yaml` (block removed) |
| `machine.network.nameservers` + `disableSearchDomain` | `ResolverConfig.nameservers[]` + `searchDomains.disableDefault` | `patches/global/machine-network.yaml` |
| `cluster.apiServer.extraArgs` (+ talconfig `additionalApiServerCertSans`) | `KubeAPIServerConfig.extraArgs` + `certExtraSANs` | `patches/controller/kube-apiserver.yaml` |
| `cluster.controllerManager.extraArgs` | `KubeControllerManagerConfig.extraArgs` | `patches/controller/kube-controller-manager.yaml` |
| `cluster.scheduler.extraArgs` | `KubeSchedulerConfig.extraArgs` | `patches/controller/kube-scheduler.yaml` |
| `cluster.proxy.disabled: true` | `KubeProxyConfig.enabled: false` | `patches/controller/kube-proxy.yaml` |

plus patches that exist **only to refuse five talhelper/Talos auto-migration defaults**
(each would validate, `exit 0`, and each is not equivalent to what runs today):

| talhelper 3.1.17 default | live today | patch that restores live | why it matters |
|---|---|---|---|
| `KubeEtcdEncryptionConfig` providers `[secretbox name=key1]` | `[secretbox name=key2, identity]` (read from the node's `encryptionconfig.yaml`) | `no-default-etcd-encryption.yaml` (`$patch: delete`) then `kube-etcd-encryption.yaml` (key2 + identity, secret via `${TALOS_SECRETBOX_ENCRYPTION_SECRET}` from new `talenv.sops.yaml`) | Every Secret in etcd is stored under the prefix `k8s:enc:secretbox:v1:key2:`. A key named `key1` matches none of them: **all Secrets unreadable**. Source: legacy renderer `internal/.../k8stemplates/apiserver.go` (v1.14.1) appends `secretbox{name: key2}` then `identity{}`. `config` is NOT `merge:"replace"` (a plain patch APPENDS a second `resources:` entry, measured), hence delete-then-add. |
| `KubeAuthenticationConfig` anonymous **enabled** for `/livez,/readyz,/healthz` | `--anonymous-auth=false` (health endpoints return 401 anonymously, measured on all three) | `kube-authentication.yaml` (`anonymous.enabled: false`, `configuration` is `merge:"replace"`) | Once any `KubeAPIServerConfig` doc exists, Talos ALWAYS passes `--authentication-config` (`KubeAPIServerConfigV1Alpha1.UseAuthenticationConfig()` returns `true`, `pkg/machinery/config/types/k8s/apiserver.go`) — so omitting this doc does NOT keep `--anonymous-auth=false`; it leaves anonymous at the k8s default. |
| `KubeAPIServerConfig` with **no** `certExtraSANs` | cert SANs `192.168.55.10, k8s.example.com, 127.0.0.1` | `certExtraSANs` in `kube-apiserver.yaml` | talhelper 3.1.17 does not carry `additionalApiServerCertSans` into the new doc (measured on a patch-free render). |
| `KubeAPIServerConfig` with `startupProbes` unset → **startup/liveness/readiness probes ON** (`StartupProbesEnabled()` defaults true in `types/k8s/apiserver.go`; the v1alpha1 shim returns false, `v1alpha1_k8s_bridge.go`) | apiserver static pods carry NO probes, restartCount 0 | `startupProbes: false` in `kube-apiserver.yaml` | The probes are anonymous HTTPS requests to `/livez` and `/readyz` (`k8stemplates/apiserver.go`: "can only be used when anonymous access to the health endpoints is allowed"). With anonymous off, they get 401. The startup probe gives up after about 250s, and the kubelet then kills every apiserver in a CrashLoop. Neither a config-text diff nor the dry-run can see this. Found by the plan review on 2026-09-28. |
| `FilesystemTrimConfig interval: 168h` | no such document → **no** automatic trim (doc comment, `block/filesystem_trim_config.go`: "If the document is absent, no automatic trimming is performed") | `no-filesystem-trim.yaml` (`$patch: delete`) | A weekly fstrim of the EPHEMERAL partition (Longhorn replicas, etcd, images on one consumer NVMe) is a behaviour change. It may well be worth having, but it is a separate decision, not part of a no-op migration. |

The SOP (`docs/sops/talos-upgrade.md` §14.2) recorded the first four from a scratch trial on
2026-09-27. The fifth (probes) is not in the SOP yet, which is a repo correction. This plan fixes all
five, and the §3.3 gate proves the fixes.

`.mise.toml` `talhelper` goes 3.1.11 → 3.1.17: 3.1.11 cannot decode the new kinds
(`error decoding document v1alpha1/KubeAPIServerConfig/: "KubeAPIServerConfig" "v1alpha1": not registered`, measured).

**Result, measured 2026-09-28 against the LIVE configs of all three nodes
(Appendix B):** 130 canonical keys. Each node has exactly **2** differences, both allowed by name:
(a) `apiserver.useAuthenticationConfig` false → true. This is the flag MECHANISM:
`--anonymous-auth=false` becomes `--authentication-config` with `anonymous.enabled: false` and
jwt `[]`. Its effect is compared separately as `apiserver.anonymous`, which is equal on both sides.
An authentication config with no jwt entries adds nothing else, and §4.4 proves this live.
(b) `install.image` `…:v1.13.10` → `…:v1.14.1`. The nodes RUN v1.14.1 already. The
v1.14.1 roll used `talosctl upgrade --image`, which does not write the machine config, so the
live config still names the old installer. That field is only read by a future
install or upgrade. Allowed, and it is the only `--allow` the gate takes.

**Why it is held / why it is a plan.** Driver is F-59b12b2b (deferred, "Talos 1.15
blocker"). Since `cad2bd3f`, `task talos:generate-config` fails on main
(talhelper 3.1.17: 6 `already set in v1alpha1` errors, reproduced 2026-09-28), so
**no machine-config change of any kind can be made** until this lands, and
v1.15 removes the fallback entirely. This is a control-plane config apply to all
three nodes, so it is never auto-safe.

**Reboot / apply mode.** Nothing here needs a reboot. This was measured, not
inferred: `talosctl apply-config --dry-run --mode=auto` with the rendered file,
against each of the three nodes, answered `Applied configuration without a
reboot (skipped in dry-run)`. `--mode=no-reboot` was accepted as well. Per
field, per the Talos v1.14 docs: resolver, discovery and kube-* documents are
reconciled live by machined controllers, and the control-plane static pods are
re-rendered. `install.image` is inert until an upgrade. Expected runtime effect:
each node's `kube-apiserver` restarts once, because its flag set changes
`--anonymous-auth=false` → `--authentication-config=…` with anonymous disabled.
Controller-manager and scheduler args are unchanged.

## 2. Pre-checks

Run from the repo root on the Mac mini, in a shell with mise activated
(`TALOSCONFIG` from `.mise.toml`). **`W` is a mode-700 scratch dir outside the
repo and any synced folder.** It holds machine secrets. Never `cat` a rendered
or live config, never paste one anywhere.

```bash
cd /Users/mu/code/cberg-home-nextgen
umask 077; export W=$(mktemp -d /private/tmp/talmig.XXXXXX); chmod 700 "$W"; mkdir -p "$W"/{backup,base,post,render}
export SOPS_AGE_KEY_FILE=$PWD/age.key
```

2.1 **Premises**: `.venv/bin/python3 runbooks/plan-premises.py talconfig-multidoc-migration --require-premises` → all PASS.

2.2 **Cluster health**: all three nodes `Ready`, etcd 3/3 members, no learner, and no ERRORS column:
```bash
kubectl get nodes
talosctl -n 192.168.55.11,192.168.55.12,192.168.55.13 etcd status
flux get kustomizations -A | awk 'NR==1 || $5 != "True"'     # header only
```
Record the etcd **LEADER** member id. It decides the order in §3.5: leader LAST.
On 2026-09-28 the leader was `192.168.55.13`.

2.3 **No staged config on any node**: `talosctl -n <ip> get machineconfig` must list only
`v1alpha1`. If a `persistent` row exists, both must be identical (SOP §14.2 step 1);
`DIFFER` → STOP.

2.4 **Tools**: `mise install` after the §3.1 pin bump. `mise exec -- talhelper --version`
→ `3.1.17`; `mise exec -- talosctl version --client --short` → `v1.14.1`.

2.5 **Recent etcd snapshot exists** (not required for the rollback, which is config
re-apply, but it is the DR floor for any control-plane work, SOP §11.4):
`talosctl -n <leader-ip> etcd snapshot "$W/backup/etcd-pre.db"` — non-zero size.
(A read of the snapshot API; it writes only to `$W`.)

## 3. Steps

### 3.1 Repo change (GitOps; Flux does NOT reconcile `kubernetes/bootstrap/talos/`)

```bash
# (a) pre-staged diff from this plan's Appendix A
awk '/^```diff talconfig-migration$/{f=1;next} /^```$/{f=0} f' \
  runbooks/maintenance/plans/talconfig-multidoc-migration.md > "$W/talconfig.diff"
git apply --check -p1 --directory=kubernetes/bootstrap/talos "$W/talconfig.diff" && \
git apply        -p1 --directory=kubernetes/bootstrap/talos "$W/talconfig.diff"

# (b) talhelper pin (BSD sed, dry-tested: diff line is  -talhelper = "3.1.11" / +talhelper = "3.1.17")
sed -i '' 's/^talhelper = "3\.1\.11"$/talhelper = "3.1.17"/' .mise.toml && mise install

# (c) talenv.sops.yaml: the SAME secretbox secret talsecret already holds, for ${TALOS_SECRETBOX_ENCRYPTION_SECRET}.
#     The .sops.yaml rule `talos/.*\.sops\.ya?ml` encrypts the WHOLE file (as talsecret.sops.yaml).
#     The plaintext exists on disk only between these two commands (dry-tested in a repo-shaped scratch tree).
sops -d kubernetes/bootstrap/talos/talsecret.sops.yaml | python3 -c 'import sys,yaml; s=yaml.safe_load(sys.stdin)["secrets"]["secretboxencryptionsecret"]; open("kubernetes/bootstrap/talos/talenv.sops.yaml","w").write("TALOS_SECRETBOX_ENCRYPTION_SECRET: \"%s\"\n" % s)' \
 && sops -e -i kubernetes/bootstrap/talos/talenv.sops.yaml
grep -c '^sops:' kubernetes/bootstrap/talos/talenv.sops.yaml     # 1
grep -c 'ENC\[' kubernetes/bootstrap/talos/talenv.sops.yaml      # >= 1 ; if 0 -> STOP, rm the file (plaintext)
```

(d) `docs/sops/talos-upgrade.md`: the line-8 banner and §14.2 "Consequences until the
multi-doc migration lands" become history ("landed <date>, plan talconfig-multidoc-migration").
Bump the SOP version line.

(e) Do NOT commit yet. §3.2–§3.4 are the gate, and they run on the working tree.

### 3.2 Render into scratch (never into `clusterconfig/`)

```bash
(cd kubernetes/bootstrap/talos && mise exec -- talhelper genconfig -o "$W/render") 2>&1 | grep -v '^generated'
# expected output: only the talhelper version-string WARNING. Any "failed to generate" -> STOP.
# "variable ${TALOS_SECRETBOX_ENCRYPTION_SECRET} not set" means talenv.sops.yaml is missing/undecryptable.
for n in 01 02 03; do mise exec -- talosctl validate --config "$W/render/kubernetes-k8s-nuc14-$n.yaml" --mode metal; done
# expected: "... is valid for metal mode" x3 (plus the known ".machine.files is deprecated" warning)
```

### 3.3 THE GATE: semantic diff, rendered vs LIVE, per node

```bash
awk '/^```python talos-semdiff$/{f=1;next} /^```$/{f=0} f' \
  runbooks/maintenance/plans/talconfig-multidoc-migration.md > "$W/talos-semdiff.py"
for n in 1 2 3; do
  talosctl -n 192.168.55.1$n get machineconfig v1alpha1 -o yaml > "$W/base/raw-1$n.yaml"
  python3 "$W/talos-semdiff.py" "$W/base/raw-1$n.yaml" "$W/render/kubernetes-k8s-nuc14-0$n.yaml" --allow install.image apiserver.useAuthenticationConfig
  echo "node0$n semdiff rc=$?"
done
```
**PASS** = for each node, `SUMMARY keys=130 diffs=2 unallowed=0` and `rc=0`, and the `ALLOWED` lines are exactly
`apiserver.useAuthenticationConfig` (false → true) and `install.image` (`…:v1.13.10` → `…:v1.14.1`).
Type the two `--allow` keys inline. Do not put them in a shell variable: zsh does not word-split it. Anything else → STOP. Do not add
`--allow` entries in the window. A new difference is a re-plan.

**Negative controls prove the gate can fail. Run them every time.** Each one mutates a COPY of the
node-01 render and must go red on its own key:
```bash
python3 - "$W" <<'EOF'
import sys,yaml; W=sys.argv[1]
K=lambda d,k:[x for x in d if x.get('kind')==k][0]
def w(name,f):
    d=[x for x in yaml.safe_load_all(open(f'{W}/render/kubernetes-k8s-nuc14-01.yaml')) if x]; f(d)
    yaml.safe_dump_all(d,open(f'{W}/render/neg-{name}.yaml','w'),sort_keys=False)
def enc(d):
    p=K(d,'KubeEtcdEncryptionConfig')['config']['resources'][0]['providers']
    p[0]['secretbox']['keys'][0]['name']='key1'; del p[1:]
w('enc',enc)
w('probes',lambda d: K(d,'KubeAPIServerConfig').pop('startupProbes'))
EOF
for c in enc probes; do python3 "$W/talos-semdiff.py" "$W/base/raw-11.yaml" "$W/render/neg-$c.yaml" --allow install.image apiserver.useAuthenticationConfig | grep -E '^(DIFF|SUMMARY)'; echo "neg-$c rc=${pipestatus[1]}"; done
rm -f "$W"/render/neg-*.yaml
```
**Expected:** `neg-enc` prints `DIFF etcdEncryption … unallowed=1 rc=1`, and `neg-probes` prints
`DIFF apiserver.startupProbes … unallowed=1 rc=1`. If either prints `unallowed=0`, the gate is blind → STOP.
Measured 2026-09-28: 14/14 injected controls went red, each on exactly its own key. They covered:
- nameserver change
- deleted `KubeAuthenticationConfig`
- re-added fstrim
- sysctl change
- kube-proxy re-enabled
- dropped SANs
- key rename
- removed `startupProbes`
- apiserver `resources`, `env` and `extraVolumes`
- scheduler `resources`
- kube-proxy `config`
- a legacy `cluster.discovery` block with the kubernetes registry enabled (the reviewer's injection)

As a further check, a cross-node pairing
(live-01 vs render-02) showed 4 DIFFs (hostname, MAC, address, disk serial).

### 3.4 Dry-run on each node (the node decides the apply mode)

```bash
for n in 1 2 3; do
  talosctl -n 192.168.55.1$n apply-config --dry-run --mode=no-reboot -f "$W/render/kubernetes-k8s-nuc14-0$n.yaml" > "$W/render/dry-1$n.txt" 2>&1
  echo "node0$n rc=$? $(grep -A1 'Dry run summary' "$W/render/dry-1$n.txt" | tail -1)"
done
```
**PASS** = `rc=0` and `Applied configuration without a reboot (skipped in dry-run).` x3.
**Never print `dry-*.txt`.** The config diff inside it contains key material.
An error such as "configuration change requires a reboot" → STOP.

### 3.5 Commit, then apply per node — followers first, etcd LEADER last

Commit the working tree from §3.1 (`git commit --only` the exact paths, unique message
file; the message says "config only; applied per node in window"; verify `git log -1
--format=%s` and `git show --stat HEAD` before `git push`). Committing BEFORE the apply keeps
the repo and the nodes from ever diverging silently. The rollback in §5 reverts this commit.

Then for each node `<ip>` in order (2026-09-28 order: `.11`, `.12`, then leader `.13`):

```bash
ip=192.168.55.11; node=k8s-nuc14-01; nn=01          # adjust per node
# (a) backup + proof it re-applies (backup_gate)
talosctl -n $ip get machineconfig v1alpha1 -o yaml | python3 -c 'import sys,yaml; print(list(yaml.safe_load_all(sys.stdin))[0]["spec"], end="")' > "$W/backup/live-$ip.yaml"
test -s "$W/backup/live-$ip.yaml" && python3 -c "import yaml,sys; assert len([d for d in yaml.safe_load_all(open(sys.argv[1])) if d])>=1" "$W/backup/live-$ip.yaml"
talosctl -n $ip apply-config --dry-run --mode=no-reboot -f "$W/backup/live-$ip.yaml" 2>&1 | grep -E '^No changes\.$'    # must print it
# (b) baselines (no secrets)
kubectl get node $node -o jsonpath='{.status.nodeInfo.bootID}' > "$W/base/bootid-$ip"
kubectl -n kube-system get pod kube-apiserver-$node -o jsonpath='{.status.startTime}' > "$W/base/apistart-$ip"
for c in kube-controller-manager kube-scheduler; do kubectl -n kube-system get pod $c-$node -o jsonpath='{.spec.containers[0].command}' > "$W/base/$c-$ip.cmd"; done
kubectl --server https://$ip:6443 get secrets -A -o name | wc -l | tr -d ' ' > "$W/base/secrets-$ip"
# (c) apply
talosctl -n $ip apply-config --mode=no-reboot -f "$W/render/kubernetes-k8s-nuc14-$nn.yaml"
# expected: "Applied configuration without a reboot"
# wait until the NEW apiserver pod is Running (startTime newer than $W/base/apistart-$ip), then:
kubectl -n kube-system get pod kube-apiserver-$node -o jsonpath='{.status.containerStatuses[0].restartCount}' > "$W/base/apirestarts-$ip"
```
Then run the §4 per-node gates 4.1–4.8. When all of them pass, wait **5 minutes**. That is longer than the
~250s a failing startup probe needs to kill the pod. Next run **§4.10 (settle gate)** and re-check etcd (4.8).
Per SOP §13 lesson 12, applies are serial with a health gate between nodes. Only then move to the next node.
Any gate failure → §5 for THAT node, and stop the roll.

### 3.6 After the third node: regenerate the local `clusterconfig/`

```bash
cp -Rp kubernetes/bootstrap/talos/clusterconfig "$W/backup/clusterconfig-pre"      # includes the talosconfig in use
mise exec -- task talos:generate-config                                              # must now SUCCEED on main
for n in 1 2 3; do talosctl -n 192.168.55.1$n get machineconfig v1alpha1 -o yaml > "$W/post/raw-1$n.yaml"
  python3 "$W/talos-semdiff.py" "$W/post/raw-1$n.yaml" kubernetes/bootstrap/talos/clusterconfig/kubernetes-k8s-nuc14-0$n.yaml; echo "rc=$?"; done
# expected: diffs=0 rc=0 (no --allow: install.image now matches too)
talosctl --talosconfig kubernetes/bootstrap/talos/clusterconfig/talosconfig -n 192.168.55.11 version --short   # client works with the regenerated talosconfig
git status --short kubernetes/bootstrap/talos/clusterconfig/    # nothing: the dir stays gitignored
```
Then close the finding (in the same turn):
`runbooks/policy-cli.py finding close F-59b12b2b --commit <sha of §3.5 commit>` with `SWEEP_PG_DSN`
up, in a separate shell call from any `git commit`.

## 4. Verification (per node after its apply, then cluster-wide)

Each gate names what it guards against and what failure prints.

4.1 **No reboot happened.** `kubectl get node $node -o jsonpath='{.status.nodeInfo.bootID}'`
equals `$W/base/bootid-$ip`. A reboot changes the bootID, and a mismatch
here means the dry-run verdict lied. That is a STOP, not a rollback trigger.

4.2 **CONTENTS ASSERTION: the node now runs exactly the rendered config.** It
is measured by `talosctl -n $ip get machineconfig v1alpha1 -o yaml > $W/post/raw-$ip.yaml`
followed by `talos-semdiff.py $W/post/raw-$ip.yaml $W/render/…-$nn.yaml`, **with no `--allow`**.
That must print `diffs=0` with rc=0. If the apply silently did not take, the old
`install.image` still differs and the gate prints `DIFF install.image`, rc=1.

4.3 **CONTENTS ASSERTION: every Secret is still decryptable through THIS node's
apiserver.** Measured by `kubectl --server https://$ip:6443 get secrets -A -o name | wc -l`
(exit 0), compared with `$W/base/secrets-$ip`: the count must be within ±5 of
baseline (normal churn), and then
`kubectl --server https://$ip:6443 -n flux-system get secret sops-age -o jsonpath='{.data}' | wc -c` > 100.
The restarted apiserver fills its watch cache from etcd, so a wrong key
name or a missing identity provider fails here. You get an error containing
`unable to transform` / `Internal error` and a non-zero exit, and the count reads 0.
Then check the provider layout by structure, printing no secret:
`talosctl -n $ip read /system/secrets/kubernetes/kube-apiserver/encryptionconfig.yaml | grep -E 'name: key|identity'`
must show `name: key2` then `- identity: {}`.

4.4 **Anonymous auth still off (the kube-authentication patch did its job).**
`curl -sk -m 10 --retry 1 -o /dev/null -w '%{http_code}' https://$ip:6443/readyz` must return `401`. A `000`
is a network blip, not a pass: repeat it once. It was 401 on all
three before the change, measured 2026-09-28. With talhelper's default doc it would return `200`,
so this gate can fail. Also check
`kubectl -n kube-system get pod kube-apiserver-$node -o jsonpath='{.spec.containers[0].command}'`:
it must contain `--authentication-config=` and must NOT contain `--anonymous-auth`. The
pod `.status.startTime` must be newer than `$W/base/apistart-$ip`, because the new
flags have to actually be running. Then
`talosctl -n $ip read /system/config/kubernetes/kube-apiserver/authentication-config.yaml`
must show `anonymous:` with `enabled: false`. It was `{}` before the change.

4.5 **API server cert SANs kept.** Run `echo | openssl s_client -connect $ip:6443 2>/dev/null | openssl x509 -noout -text | grep -A1 'Subject Alternative Name'`.
It must still list `DNS:k8s.example.com`, `IP Address:127.0.0.1`, `IP Address:192.168.55.10` and the node IP.
Without `certExtraSANs`, `k8s.example.com` disappears. The baseline on 2026-09-28 listed all of them.

4.6 **Controller-manager / scheduler args unchanged.** For each of the two, `kubectl -n kube-system get pod <c>-$node -o jsonpath='{.spec.containers[0].command}'`
must be byte-equal (`cmp`) to `$W/base/<c>-$ip.cmd`. Both must also contain `--bind-address=0.0.0.0`,
because Prometheus scrapes them on it.

4.7 **Resolver + discovery unchanged.** Run `talosctl -n $ip get resolvers -o yaml | grep -A4 dnsServers`.
It must list `192.168.55.1`, `1.1.1.1`, `1.0.0.1` in that order. Then run `talosctl -n $ip get discoveryconfig -o yaml | grep -E 'registryKubernetesEnabled|registryServiceEnabled|serviceEndpoint:'`.
Expect `false` / `true` / `discovery.talos.dev:443`. Do not print the whole
resource, because it carries the discovery encryption key bytes. Next, `talosctl -n $ip get members | tail -n +2 | wc -l` must be `3`.
The endpoint list's `name` changes from `legacy` to `default`, which is cosmetic.

4.8 **etcd, SOP pattern (ii).** Run `talosctl -n 192.168.55.11,192.168.55.12,192.168.55.13 etcd status`.
You need 3 members, empty ERRORS, and the same LEADER as in §2.2. The apply does not touch etcd, so a
leader change here is unexplained. STOP and triage per `docs/sops/talos-upgrade.md` §14.3.

4.9 **Cluster-wide, after node 3:** all nodes `Ready`, and
`flux get kustomizations -A | awk 'NR==1 || $5 != "True"'` prints the header only. Also
`flux get helmreleases -A | awk 'NR==1 || $5 != "True"'` prints the header only. There must be no new
`Warning` events in kube-system mentioning `kube-apiserver` after the restart settles:
`kubectl get events -n kube-system --field-selector type=Warning --sort-by=.lastTimestamp | tail`.

4.10 **Settle gate. Run it per node, AFTER the 5-minute wait, and pass it before the next node.**
It guards against a restarted apiserver that looks fine at first and is killed minutes later,
which is the probe/anonymous trap described in §1.
```bash
kubectl -n kube-system get pod kube-apiserver-$node -o jsonpath='{.status.containerStatuses[0].restartCount} {.status.conditions[?(@.type=="Ready")].status} |{.spec.containers[0].startupProbe.httpGet.path}|{.spec.containers[0].livenessProbe.httpGet.path}|{.spec.containers[0].readinessProbe.httpGet.path}|'
```
PASS = the first field equals `$W/base/apirestarts-$ip`, the second is `True`, and the rest reads
`||||`. That means no probes, the same as live today (measured 2026-09-28 on all three: `0 True ||||`).
If probes were rendered, their paths print instead (`|/livez|/livez|/readyz|`), and a kill raises
restartCount. Either result → go to §5 for this node.

CONTROL: metric etcd_server_has_leader — must read 1 for all three members across the window (`min(etcd_server_has_leader) == 1` AND `count(etcd_server_has_leader) == 3`; measured 2026-09-28: 1 / 3); 0 on any member, or a count below 3 (a member stopped being scraped), = STOP.
CONTROL: metric etcd_server_leader_changes_seen_total — `sum(increase(etcd_server_leader_changes_seen_total[30m]))` must be 0 at the end of the roll (pattern ii; the apply does not touch etcd; measured 2026-09-28 baseline: 0).
CONTROL: metric apiserver_request_total — `sum(rate(apiserver_request_total{code=~"5.."}[5m]))` after each node settles must be back at its pre-window level (record it in §2.2; measured 2026-09-28: 0); a sustained rise means a restarted apiserver is failing requests (e.g. transform errors).

## 5. Rollback

**Per node (the primary path; no reboot).** Use it if any §4 gate fails on node `$ip`:
```bash
talosctl -n $ip apply-config --mode=no-reboot -f "$W/backup/live-$ip.yaml"
# proven 2026-09-28: the saved live config is accepted by v1.14.1 and a self-apply dry-run says "No changes."
talosctl -n $ip get machineconfig v1alpha1 -o yaml > "$W/post/rollback-$ip.yaml"
python3 - "$W/post/rollback-$ip.yaml" "$W/backup/live-$ip.yaml" <<'EOF'
import sys,yaml
live=list(yaml.safe_load_all(open(sys.argv[1])))[0]['spec']
bk=open(sys.argv[2]).read()
a=[d for d in yaml.safe_load_all(live) if d]; b=[d for d in yaml.safe_load_all(bk) if d]
print('ROLLBACK_IDENTICAL' if a==b else 'ROLLBACK_DIFFERS'); sys.exit(0 if a==b else 1)
EOF
```
Confirmed back when the script prints `ROLLBACK_IDENTICAL`. After that, the
apiserver command line again contains `--anonymous-auth=false` and not
`--authentication-config`, `curl …/readyz` returns 401, and the §4.3 secrets
count through that node matches baseline. Nodes already migrated can stay
migrated, since both forms are effectively identical by the gate. If the
failure was a real behaviour change, roll every migrated node back in reverse
order.

**Repo.** Run `git revert <§3.5 sha>`. That restores the v1alpha1 talconfig, the 3.1.11 pin, and
removes `talenv.sops.yaml` and the SOP edit. Then `mise install`. Push. Flux reconciles nothing here.
Next, restore the pre-regen local dir, which includes the talosconfig in use:
`rm -rf kubernetes/bootstrap/talos/clusterconfig && cp -Rp "$W/backup/clusterconfig-pre" kubernetes/bootstrap/talos/clusterconfig`.
Confirm with `talosctl -n 192.168.55.11 version --short`.

**Forward-only parts:** none. The apply rewrites no data. Secrets are NOT
re-encrypted, and the key and secret stay the same. etcd is not touched.
**DR floor**: the §2.5 etcd snapshot, per SOP §11.4, is only for the case where
the control plane will not come back at all.

**Cleanup (success or rollback):** `rm -rf "$W"`. It holds machine secrets.

## 6. Interference notes

- **`exclusive: true`.** Each node's kube-apiserver restarts once, serially, behind the VIP. Every
  controller that watches the API (Flux, cert-manager, Longhorn, Cilium operator, CNPG-style
  operators) reconnects. Nothing else may be in flight: a same-window HelmRelease upgrade
  would hit an apiserver mid-restart and look like a failure of the wrong plan.
- **Needs an attended window, not nightly.** `risk: high`, `rollback_class: backup-restore`.
  No reboot is required, so it does not need the reboot-capable Sunday slot, but it needs the
  operator present, and ~80 min fits the attended windows.
- **Must run BEFORE any Talos v1.15 upgrade plan**, and before any other machine-config change
  (patch, sysctl, kernel arg). Until this lands, those are blocked by the failing
  `generate-config` (SOP §14.2).
- **Prometheus is the instrument for the §4 CONTROL lines.** No kube-prometheus-stack plan is open.
  If one is written, it must list this plan in `conflicts_with`, and this plan must list it back.
- **`mise install`** runs after the pin bump and calls the GitHub API. Set `GITHUB_TOKEN` if the API
  rate-limits you (403 seen 2026-09-28). talhelper 3.1.17 is already installed on the Mac mini.
- **Order is by etcd role, not by hostname.** Re-derive the leader in §2.2 and leave it for last.
  A leader-last roll avoids an election being triggered by a restarting apiserver on the leader.
  The apiserver restart does not stop etcd, so no election is expected either way.
- **Not in scope, noted for 1.15:** `talosctl validate` still warns `.machine.files is
  deprecated` (`patches/global/machine-files.yaml` → `CRICustomizationConfig`), and kubelet,
  sysctls, udev, kernel modules and time still use deprecated-but-honoured v1alpha1 fields. None of
  them is a talhelper render error today. They are a separate, smaller follow-up before 1.15, so
  that this plan stays a pure "same effective values" change.

## Appendix A: pre-staged repo diff (apply with §3.1a)

Paths are relative to `kubernetes/bootstrap/talos/`. Verified 2026-09-28 with
`git apply --check -p1 --directory=kubernetes/bootstrap/talos` against main. It contains no
secret values; the encryption secret is the `${TALOS_SECRETBOX_ENCRYPTION_SECRET}`
reference, resolved by talhelper from `talenv.sops.yaml`. `$$patch` is talhelper's
escape for a literal `$patch` (SOP §13 lesson 5).

```diff talconfig-migration
diff -ruN a/patches/controller/cluster.yaml b/patches/controller/cluster.yaml
--- a/patches/controller/cluster.yaml
+++ b/patches/controller/cluster.yaml
@@ -1,30 +1,16 @@
 cluster:
   allowSchedulingOnControlPlanes: true
-  # Discovery: SERVICE registry only (discovery.talos.dev). The in-cluster
-  # kubernetes registry used to be enabled here "so member discovery survives
-  # a Sidero/WAN outage", but it cannot work on Kubernetes >= 1.32: the
-  # AuthorizeNodeWithSelectors node authorizer limits a kubelet identity to
-  # its OWN Node object, and the registry lists/watches ALL nodes as
-  # system:node:<name>. Upstream deprecated it and disables it by default for
-  # that reason. Measured 2026-09-22 (F-82fb3335): ~1,000 "nodes is forbidden"
-  # errors per hour per node from cluster.KubernetesPullController in
-  # controller-runtime, and `talosctl get members` is served entirely by the
-  # service registry — so the outage-resilience it was meant to buy has been
-  # zero since the K8s bump. Disabling it removes the log flood and nothing
-  # else. (Re-enabling would need the api-server feature gate off, which
-  # drops several other node-authorizer protections — not an option.)
-  discovery:
-    enabled: true
-    registries:
-      kubernetes:
-        disabled: true
-  apiServer:
-    extraArgs:
-      # https://kubernetes.io/docs/tasks/extend-kubernetes/configure-aggregation-layer/
-      enable-aggregator-routing: true
-  controllerManager:
-    extraArgs:
-      bind-address: 0.0.0.0
+  # Discovery / apiServer / controllerManager / scheduler / proxy moved to
+  # dedicated Talos v1.14 documents (talhelper >= 3.1.17 rejects the v1alpha1
+  # form next to the multi-doc defaults it emits): see kube-*.yaml,
+  # kube-proxy.yaml in this directory. Plan: talconfig-multidoc-migration.
+  #
+  # Discovery: SERVICE registry only (DiscoveryServiceConfig, emitted by
+  # default with endpoint https://discovery.talos.dev/). The in-cluster
+  # Kubernetes registry stays OFF: in v1.14 it is driven only by the legacy
+  # v1alpha1 .cluster.discovery block (controllers/cluster/config.go), which
+  # is now absent => RegistryKubernetesEnabled=false. It cannot work on
+  # Kubernetes >= 1.32 anyway (node authorizer; F-82fb3335).
   coreDNS:
     disabled: true
   etcd:
@@ -32,8 +18,3 @@
       listen-metrics-urls: http://0.0.0.0:2381
     advertisedSubnets:
       - 192.168.55.0/24
-  proxy:
-    disabled: true
-  scheduler:
-    extraArgs:
-      bind-address: 0.0.0.0
diff -ruN a/patches/controller/kube-apiserver.yaml b/patches/controller/kube-apiserver.yaml
--- a/patches/controller/kube-apiserver.yaml
+++ b/patches/controller/kube-apiserver.yaml
@@ -0,0 +1,18 @@
+# Was .cluster.apiServer (v1alpha1). certExtraSANs repeats
+# additionalApiServerCertSans from talconfig.yaml because talhelper 3.1.17
+# does not carry that field into KubeAPIServerConfig (measured 2026-09-28).
+apiVersion: v1alpha1
+kind: KubeAPIServerConfig
+extraArgs:
+  # https://kubernetes.io/docs/tasks/extend-kubernetes/configure-aggregation-layer/
+  enable-aggregator-routing: "true"
+certExtraSANs:
+  - "192.168.55.10"
+  - "k8s.example.com"
+  - "127.0.0.1"
+# The v1alpha1 shim renders NO startup/liveness/readiness probes on the static
+# pod (StartupProbesEnabled()==false); a KubeAPIServerConfig doc defaults them
+# ON, and they are anonymous HTTPS requests to /livez,/readyz -- rejected 401
+# with kube-authentication.yaml's anonymous.enabled:false, so the kubelet
+# would kill the apiserver ~250s after start. Keep live: no probes.
+startupProbes: false
diff -ruN a/patches/controller/kube-authentication.yaml b/patches/controller/kube-authentication.yaml
--- a/patches/controller/kube-authentication.yaml
+++ b/patches/controller/kube-authentication.yaml
@@ -0,0 +1,12 @@
+# Live v1.13 kube-apiserver runs --anonymous-auth=false. Once a
+# KubeAPIServerConfig document exists, Talos v1.14 ALWAYS passes
+# --authentication-config (UseAuthenticationConfig() == true), and talhelper's
+# default KubeAuthenticationConfig enables anonymous access to
+# /livez,/readyz,/healthz. `configuration` is merge:"replace", so this patch
+# restores the live behaviour exactly: anonymous authentication off.
+apiVersion: v1alpha1
+kind: KubeAuthenticationConfig
+configuration:
+  anonymous:
+    enabled: false
+  jwt: []
diff -ruN a/patches/controller/kube-controller-manager.yaml b/patches/controller/kube-controller-manager.yaml
--- a/patches/controller/kube-controller-manager.yaml
+++ b/patches/controller/kube-controller-manager.yaml
@@ -0,0 +1,4 @@
+apiVersion: v1alpha1
+kind: KubeControllerManagerConfig
+extraArgs:
+  bind-address: 0.0.0.0
diff -ruN a/patches/controller/kube-etcd-encryption.yaml b/patches/controller/kube-etcd-encryption.yaml
--- a/patches/controller/kube-etcd-encryption.yaml
+++ b/patches/controller/kube-etcd-encryption.yaml
@@ -0,0 +1,20 @@
+# Keep the LIVE encryption-provider layout. Under v1alpha1 Talos renders
+# providers [secretbox name=key2, identity] (k8stemplates/apiserver.go); the
+# v1.14 generator default is [secretbox name=key1] only. Every Secret in etcd
+# is stored with the prefix k8s:enc:secretbox:v1:key2:, so renaming the key
+# makes all Secrets unreadable, and dropping identity breaks any plaintext
+# object. Same secret value; it comes from talenv.sops.yaml via envsubst.
+apiVersion: v1alpha1
+kind: KubeEtcdEncryptionConfig
+config:
+  apiVersion: v1
+  kind: EncryptionConfig
+  resources:
+    - resources:
+        - secrets
+      providers:
+        - secretbox:
+            keys:
+              - name: key2
+                secret: ${TALOS_SECRETBOX_ENCRYPTION_SECRET}
+        - identity: {}
diff -ruN a/patches/controller/kube-proxy.yaml b/patches/controller/kube-proxy.yaml
--- a/patches/controller/kube-proxy.yaml
+++ b/patches/controller/kube-proxy.yaml
@@ -0,0 +1,4 @@
+# Cilium replaces kube-proxy (was .cluster.proxy.disabled: true).
+apiVersion: v1alpha1
+kind: KubeProxyConfig
+enabled: false
diff -ruN a/patches/controller/kube-scheduler.yaml b/patches/controller/kube-scheduler.yaml
--- a/patches/controller/kube-scheduler.yaml
+++ b/patches/controller/kube-scheduler.yaml
@@ -0,0 +1,4 @@
+apiVersion: v1alpha1
+kind: KubeSchedulerConfig
+extraArgs:
+  bind-address: 0.0.0.0
diff -ruN a/patches/controller/no-default-etcd-encryption.yaml b/patches/controller/no-default-etcd-encryption.yaml
--- a/patches/controller/no-default-etcd-encryption.yaml
+++ b/patches/controller/no-default-etcd-encryption.yaml
@@ -0,0 +1,5 @@
+# Drop talhelper's default KubeEtcdEncryptionConfig (key1, no identity) so
+# kube-etcd-encryption.yaml (listed AFTER this file) is the only one.
+apiVersion: v1alpha1
+kind: KubeEtcdEncryptionConfig
+$$patch: delete
diff -ruN a/patches/global/machine-network.yaml b/patches/global/machine-network.yaml
--- a/patches/global/machine-network.yaml
+++ b/patches/global/machine-network.yaml
@@ -1,7 +1,11 @@
-machine:
-  network:
-    disableSearchDomain: true
-    nameservers:
-      - 192.168.55.1
-      - 1.1.1.1
-      - 1.0.0.1
+# Was .machine.network.{nameservers,disableSearchDomain} (v1alpha1).
+# hostDNS (enabled + forwardKubeDNSToHost) comes from the talhelper default
+# ResolverConfig and is merged, matching the live machine.features.hostDNS.
+apiVersion: v1alpha1
+kind: ResolverConfig
+nameservers:
+  - address: 192.168.55.1
+  - address: 1.1.1.1
+  - address: 1.0.0.1
+searchDomains:
+  disableDefault: true
diff -ruN a/patches/global/no-filesystem-trim.yaml b/patches/global/no-filesystem-trim.yaml
--- a/patches/global/no-filesystem-trim.yaml
+++ b/patches/global/no-filesystem-trim.yaml
@@ -0,0 +1,7 @@
+# talhelper >= 3.1.17 emits FilesystemTrimConfig (interval 168h) by default.
+# Live v1.13 configs have no such document, and in v1.14 its ABSENCE means
+# "no automatic trimming". Deleting it keeps behaviour identical; enabling
+# periodic fstrim on the Longhorn EPHEMERAL partition is a separate decision.
+apiVersion: v1alpha1
+kind: FilesystemTrimConfig
+$$patch: delete
diff -ruN a/talconfig.yaml b/talconfig.yaml
--- a/talconfig.yaml
+++ b/talconfig.yaml
@@ -93,6 +93,7 @@
   - "@./patches/global/machine-kubelet.yaml"
   - "@./patches/global/machine-network.yaml"
   - "@./patches/global/machine-network-rps.yaml"
+  - "@./patches/global/no-filesystem-trim.yaml"
   - "@./patches/global/machine-sysctls.yaml"
   - "@./patches/global/machine-time.yaml"
   - "@./patches/global/machine-udev.yaml"
@@ -108,4 +109,11 @@
     # kubernetes/flux/components/common/namespace.yaml for the cluster-wide
     # privileged label, and follow-up #40 for per-namespace tightening.
     - "@./patches/controller/cluster.yaml"
+    - "@./patches/controller/kube-apiserver.yaml"
+    - "@./patches/controller/kube-authentication.yaml"
+    - "@./patches/controller/kube-controller-manager.yaml"
+    - "@./patches/controller/no-default-etcd-encryption.yaml"
+    - "@./patches/controller/kube-etcd-encryption.yaml"
+    - "@./patches/controller/kube-proxy.yaml"
+    - "@./patches/controller/kube-scheduler.yaml"
 
```

## Appendix B: semantic-diff gate (tool + measured result)

Result on 2026-09-28, LIVE `get machineconfig v1alpha1` vs the Appendix A render (talhelper
3.1.17, talosVersion v1.14.1), `--allow install.image apiserver.useAuthenticationConfig`:

```
node01  ALLOWED apiserver.useAuthenticationConfig (false->true)  ALLOWED install.image (…:v1.13.10 -> …:v1.14.1)  SUMMARY keys=130 diffs=2 unallowed=0  rc=0
node02  (same)  SUMMARY keys=130 diffs=2 unallowed=0  rc=0
node03  (same)  SUMMARY keys=130 diffs=2 unallowed=0  rc=0
negative controls (node01 live vs mutated render), all rc=1 unallowed=1, each red on exactly its own key:
  nameserver changed                 -> DIFF resolver.nameservers
  KubeAuthenticationConfig dropped   -> DIFF apiserver.anonymous
  FilesystemTrimConfig re-added      -> DIFF fstrim.interval
  sysctl vm.swappiness changed       -> DIFF v1alpha1.machine.sysctls.vm.swappiness
  KubeProxyConfig.enabled removed    -> DIFF proxy.enabled
  certExtraSANs removed              -> DIFF apiserver.certSANs
  secretbox key1 + no identity       -> DIFF etcdEncryption
  startupProbes removed              -> DIFF apiserver.startupProbes
  apiserver resources/env/extraVolumes injected -> DIFF apiserver.rest (x3)
  scheduler resources injected       -> DIFF sched.rest
  kube-proxy config injected         -> DIFF proxy.config
  legacy discovery kubernetes registry on -> DIFF discovery.kubernetesRegistry
dry-run apply --mode=no-reboot on .11/.12/.13 -> "Applied configuration without a reboot" x3
dry-run of the saved live config on .11 -> "Config diff: No changes."
```

The model maps both sides onto one canonical key set. It follows the Talos v1.14 document
map, with v1alpha1 fallbacks taken from the v1.14.1 source (container.go, v1alpha1_k8s_bridge.go,
controllers/cluster/config.go, k8stemplates/apiserver.go). Everything it does not model
explicitly is compared verbatim. That covers the flattened keys of the remaining v1alpha1 doc and of
the remaining documents, and the unmodelled fields of every popped kube-* document or legacy
block (`*.rest`). An unknown field therefore surfaces as a DIFF instead of being dropped. Secrets are compared only as sha256 prefixes. The script
never prints a secret value.

```python talos-semdiff
#!/usr/bin/env python3
"""Semantic diff: live Talos machineconfig (talosctl get machineconfig -o yaml)
vs a talhelper-rendered multi-doc config. Maps BOTH onto one canonical
'effective' model (v1alpha1 field -> v1.14 document per the Talos document map)
and prints differing keys. Secret values are compared by sha256 and printed
only as REDACTED:<hash10>. Exit 0 = no difference, 1 = differences, 2 = error.
usage: talos-semdiff.py LIVE.yaml RENDERED.yaml [--allow key ...]"""
import sys, yaml, hashlib, json, copy
SECRET = ('token','secret','key','crt','ca','secretboxEncryptionSecret','aescbcEncryptionSecret','aggregatorCA','serviceAccount','id')
def H(v): return 'REDACTED:' + hashlib.sha256(json.dumps(v, sort_keys=True).encode()).hexdigest()[:10]
def docs_live(p):
    outer = [d for d in yaml.safe_load_all(open(p)) if d]
    if len(outer) != 1 or 'spec' not in outer[0]: sys.exit('live: expected one machineconfig resource')
    return [d for d in yaml.safe_load_all(outer[0]['spec']) if d]
def docs_file(p): return [d for d in yaml.safe_load_all(open(p)) if d]
def split(docs):
    v1 = [d for d in docs if 'machine' in d or d.get('version') == 'v1alpha1']
    if len(v1) != 1: sys.exit('expected exactly one v1alpha1 doc')
    other = {}
    for d in docs:
        if d is v1[0]: continue
        k = (d['kind'], d.get('name', ''))
        if k in other: sys.exit(f'duplicate doc {k}')
        other[k] = d
    return copy.deepcopy(v1[0]), other
def pop(d, *path, default=None):
    for p in path[:-1]:
        d = (d or {}).get(p)
        if d is None: return default
    return d.pop(path[-1], default) if isinstance(d, dict) else default
def args(a): return {k: str(v) for k, v in (a or {}).items()}
def rest(d, known):
    # every field of a popped doc / legacy block NOT modelled above is compared
    # verbatim (fail closed: an unmodelled field shows up as a DIFF)
    return {k: v for k, v in (d or {}).items() if k not in known and k not in ('apiVersion', 'kind', 'name') and v not in (None, {}, [])}
def canon(docs):
    v, o = split(docs)
    m, c = v.setdefault('machine', {}), v.setdefault('cluster', {})
    E = {}
    def doc(kind, name=''):
        return o.pop((kind, name), None)
    # --- kube-apiserver
    api = doc('KubeAPIServerConfig') or {}
    lapi = pop(c, 'apiServer') or {}
    E['apiserver.image'] = api.get('image') or lapi.get('image')
    E['apiserver.extraArgs'] = args(api.get('extraArgs') or lapi.get('extraArgs'))
    E['apiserver.certSANs'] = sorted(api.get('certExtraSANs') or lapi.get('certSANs') or [])
    # v1alpha1 shim: StartupProbesEnabled()=false, UseAuthenticationConfig()=false
    # (v1alpha1_k8s_bridge.go). Doc: startupProbes default TRUE, auth-config always TRUE
    # (types/k8s/apiserver.go). Probes are anonymous -> must pair with anonymous access.
    E['apiserver.startupProbes'] = api.get('startupProbes', True) if api else False
    E['apiserver.useAuthenticationConfig'] = bool(api)
    E['apiserver.rest'] = rest(api, {'image','extraArgs','certExtraSANs','startupProbes'}) | rest(lapi, {'image','extraArgs','certSANs','admissionControl','auditPolicy','disablePodSecurityPolicy'})
    adm = doc('KubeAdmissionControlConfig', 'PodSecurity')
    E['apiserver.admission'] = [{'name': 'PodSecurity', 'configuration': adm['configuration']}] if adm else lapi.get('admissionControl')
    aud = doc('KubeAuditPolicyConfig')
    E['apiserver.auditPolicy'] = aud['configuration'] if aud else lapi.get('auditPolicy')
    authn = doc('KubeAuthenticationConfig')
    # v1alpha1 shim (no KubeAPIServerConfig doc) => --anonymous-auth=false.
    # A KubeAPIServerConfig doc => Talos ALWAYS passes --authentication-config
    # (apiserver.go UseAuthenticationConfig()==true); with no
    # KubeAuthenticationConfig the anonymous block is unset => k8s default.
    if authn: E['apiserver.anonymous'] = authn['configuration'].get('anonymous')
    elif api: E['apiserver.anonymous'] = 'UNSET-under-authentication-config(k8s default: enabled)'
    else: E['apiserver.anonymous'] = {'enabled': False}
    E['apiserver.jwt'] = (authn['configuration'].get('jwt') or []) if authn else []
    az = [doc('KubeAuthorizerConfig', n) for n in ('node', 'rbac')]
    E['apiserver.authorizers'] = [x['type'] for x in az if x] if any(az) else (lapi.get('authorizationConfig') or ['Node', 'RBAC'])
    # etcd encryption: compare the FULL provider list (type, key NAME, secret
    # hash). Legacy v1alpha1 renders [secretbox key2, (aescbc key1), identity]
    # (k8stemplates/apiserver.go); a doc is used verbatim. The key NAME is part
    # of the stored prefix k8s:enc:secretbox:v1:<name>: -- a rename is fatal.
    enc = doc('KubeEtcdEncryptionConfig')
    def provs(pl):
        out = []
        for p in pl:
            for t, body in p.items():
                out.append([t] + [[k['name'], H(k['secret'])] for k in (body or {}).get('keys', [])])
        return out
    if enc:
        E['etcdEncryption'] = [[sorted(r['resources']), provs(r['providers'])] for r in enc['config']['resources']]
        E['etcdEncryption.header'] = [enc['config'].get('apiVersion'), enc['config'].get('kind')]
    else:
        pl = []
        if c.get('secretboxEncryptionSecret'): pl.append({'secretbox': {'keys': [{'name': 'key2', 'secret': c['secretboxEncryptionSecret']}]}})
        if c.get('aescbcEncryptionSecret'): pl.append({'aescbc': {'keys': [{'name': 'key1', 'secret': c['aescbcEncryptionSecret']}]}})
        pl.append({'identity': {}})
        E['etcdEncryption'] = [[['secrets'], provs(pl)]]
        E['etcdEncryption.header'] = ['v1', 'EncryptionConfig']
    pop(c, 'secretboxEncryptionSecret'); pop(c, 'aescbcEncryptionSecret')
    # --- controller-manager / scheduler / proxy
    for kind, key, name in (('KubeControllerManagerConfig', 'controllerManager', 'cm'), ('KubeSchedulerConfig', 'scheduler', 'sched')):
        n, l = doc(kind) or {}, pop(c, key) or {}
        E[f'{name}.image'] = n.get('image') or l.get('image')
        E[f'{name}.extraArgs'] = args(n.get('extraArgs') or l.get('extraArgs'))
        E[f'{name}.enabled'] = n.get('enabled', True) if n else not l.get('disabled', False)
        if name == 'sched': E['sched.config'] = n.get('config') or l.get('config') or {}
        E[f'{name}.rest'] = json.dumps(rest(n, {'image','extraArgs','enabled','config'}) | rest(l, {'image','extraArgs','disabled','config'}), sort_keys=True)
    px, lpx = doc('KubeProxyConfig') or {}, pop(c, 'proxy') or {}
    E['proxy.enabled'] = px.get('enabled', True) if px else not lpx.get('disabled', False)
    E['proxy.image'] = px.get('image') or lpx.get('image')
    E['proxy.mode'] = px.get('mode') or lpx.get('mode')
    E['proxy.extraArgs'] = args(px.get('extraArgs') or lpx.get('extraArgs'))
    E['proxy.config'] = px.get('config') or {}
    E['proxy.rest'] = rest(px, {'image','extraArgs','enabled','mode','config'}) | rest(lpx, {'image','extraArgs','disabled','mode'})
    # --- discovery (service + legacy kubernetes registry)
    ds = doc('DiscoveryServiceConfig', 'default')
    ld = pop(c, 'discovery') or {}
    if ds:
        E['discovery.service'] = ds['endpoint'].rstrip('/')
    en = ld.get('enabled', False); reg = ld.get('registries', {})
    # controllers/cluster/config.go derives RegistryKubernetesEnabled from the legacy block ALWAYS,
    # whether or not a DiscoveryServiceConfig doc exists
    E['discovery.kubernetesRegistry'] = bool(en and not reg.get('kubernetes', {}).get('disabled', False))
    if not ds:
        E['discovery.service'] = ('https://' + (reg.get('service', {}).get('endpoint') or 'discovery.talos.dev').replace('https://', '').rstrip('/').removesuffix(':443')) if en and not reg.get('service', {}).get('disabled') else None
    # --- resolver
    rc = doc('ResolverConfig') or {}
    lns = pop(m, 'network', 'nameservers') or []
    E['resolver.nameservers'] = [x['address'] for x in rc.get('nameservers', [])] or lns
    E['resolver.disableDefaultSearch'] = rc.get('searchDomains', {}).get('disableDefault', pop(m, 'network', 'disableSearchDomain') or False)
    pop(m, 'network', 'disableSearchDomain')
    lh = pop(m, 'features', 'hostDNS') or {}
    E['resolver.hostDNS'] = rc.get('hostDNS') or lh
    # --- kube network / CNI
    kn = doc('KubeNetworkConfig') or {}
    lnw = pop(c, 'network') or {}
    E['k8snet.dnsDomain'] = kn.get('dnsDomain') or lnw.get('dnsDomain')
    E['k8snet.podSubnets'] = kn.get('podSubnets') or lnw.get('podSubnets')
    E['k8snet.serviceSubnets'] = kn.get('serviceSubnets') or lnw.get('serviceSubnets')
    fl = doc('KubeFlannelCNIConfig')
    E['cni'] = 'flannel' if fl else ((lnw.get('cni') or {}).get('name', 'flannel') if lnw else 'none')
    # --- block
    tr = doc('FilesystemTrimConfig')
    E['fstrim.interval'] = tr.get('interval') if tr else None
    if m.get('network') == {}: m.pop('network')
    if m.get('features') is not None and m['features'] == {}: m.pop('features')
    # install.image tracked separately (live config keeps the image it was installed with)
    E['install.image'] = pop(m, 'install', 'image')
    # --- everything else: remaining v1alpha1 + remaining docs verbatim, secrets hashed
    def red(x, k=''):
        if isinstance(x, dict): return {kk: (H(vv) if kk in SECRET and not isinstance(vv, list) else red(vv, kk)) for kk, vv in x.items()}
        if isinstance(x, list): return [red(i, k) for i in x]
        return x
    def flat(prefix, x):
        if isinstance(x, dict) and x:
            for kk, vv in x.items(): flat(f'{prefix}.{kk}', vv)
        else: E[prefix] = x
    flat('v1alpha1', red(v))
    for (k, n), d in o.items(): flat(f'doc.{k}/{n}', red({kk: vv for kk, vv in d.items() if kk not in ('apiVersion', 'kind')}))
    return E
def main():
    a = sys.argv[1:]
    allow = set(a[a.index('--allow') + 1:]) if '--allow' in a else set()
    live, new = canon(docs_live(a[0])), canon(docs_file(a[1]))
    diffs = []
    for k in sorted(set(live) | set(new)):
        if live.get(k) != new.get(k):
            diffs.append((k, live.get(k), new.get(k)))
    bad = [x for x in diffs if x[0] not in allow]
    for k, l, n in diffs:
        tag = 'ALLOWED' if k in allow else 'DIFF'
        print(f'{tag} {k}\n   live: {json.dumps(l, sort_keys=True)}\n   new:  {json.dumps(n, sort_keys=True)}')
    print(f'SUMMARY keys={len(set(live)|set(new))} diffs={len(diffs)} unallowed={len(bad)}')
    sys.exit(1 if bad else 0)
main()
```

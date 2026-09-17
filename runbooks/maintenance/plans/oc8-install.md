---
plan_id: oc8-install
component: oc8
pr: null                              # Not a version bump and not a Renovate item: this is a
                                      # NEW app evaluation, dispatched by operator request on
                                      # 2026-09-17 against https://docs.oc8.ai/user/install-and-maintain/
kind: chart                           # would be a HelmRelease + sibling manifests if it landed
current: "not installed"
target: "oc8 Community Edition, chart 0.1.0 / appVersion 0.1.0 (deploy/helm/oc8 in the
  upstream git tree; upstream main @ 8daf228e, 2026-09-14). NO tag, NO release, NO published
  chart, NO published image — see §1.2."
update_type: install                  # house value — plans/README.md line 130 enumerates
                                      # `... | decommission | install | refactor | pilot | n/a`.
                                      # Corrected from `new-install` (doc-agent, 2026-09-17),
                                      # which was used by this file alone; the validator does
                                      # not enforce the enum, so it would have passed silently.
status: blocked                       # DELIBERATE, and the whole point of this file. The brief
                                      # allowed `draft`; the facts do not. Four independent
                                      # blockers in §1.2, any ONE of which is sufficient. The
                                      # plan is written out in full anyway (§3) so that if the
                                      # blockers clear, the work is already scoped — but it must
                                      # not be scheduled into a window in this state.
window: null                          # required: `blocked` must not claim a slot
risk: high                            # Rated on what it WOULD be, not on the fact that it is
                                      # blocked: a new internet-era agent platform holding
                                      # credentials to other systems, whose vendor ships
                                      # `dev-login` (unauthenticated admin) ON BY DEFAULT and
                                      # whose own docs call the reference stack "not production".
est_duration_min: 240                 # CLUSTER-SIDE ONLY, and only if every blocker in §1.2 is
                                      # already cleared. It excludes the prerequisite that
                                      # actually dominates: forking, building and publishing two
                                      # container images we would then own forever (§1.2.a).
                                      # That is days of engineering, not a maintenance window.
needs_reboot: false                   # no Talos change, no node roll, no machine-config edit
capability_change: true               # HONEST: adds a new user-facing app, a new agent runtime,
                                      # and a new outbound-credential surface (model providers +
                                      # whatever business systems an agent is granted).
rollback_class: git-revert            # nothing is installed today, so "rollback" is reverting a
                                      # commit — but see §5 for what a revert does NOT remove.
touches:
  namespaces:
    - ai                              # proposed home — matches docs/applications.md (§3.1)
    - monitoring                      # the mandatory {app}-alerts.yaml PrometheusRule
    - storage                         # 2 Longhorn Volume CRs, applied by hand (Flux cannot own)
  resources:
    - "new: kubernetes/apps/ai/oc8/** (ks.yaml + app/)"
    - "new: helmrelease/oc8 (ai) — chart from a GitRepository source, pinned to a commit SHA"
    - "new: gitrepository/oc8-upstream (flux-system) — a THIRD-PARTY repo as a chart source"
    - "new: httproute/oc8 (ai) -> gateway envoy-internal, sectionName https"
    - "new: pvc/oc8-postgres + pv/oc8-postgres + longhorn volume oc8-postgres"
    - "new: pvc/oc8-sessions + pv/oc8-sessions + longhorn volume oc8-sessions"
    - "new: secret.sops.yaml (jwt secret, KEK, postgres password)"
    - "new: kubernetes/apps/monitoring/kube-prometheus-stack/app/oc8-alerts.yaml"
  shared:
    - storage                         # allocates 2 new 2-replica Longhorn volumes
    - "gateway/envoy-internal"        # one more attached route + hostname
    - "k8s-gateway DNS"               # publishes one more *.${SECRET_DOMAIN} name
depends_on: []
conflicts_with: []                    # Deliberately EMPTY, not lazy. `blocked` + `window: null`
                                      # means it can never be co-scheduled, so a guard here would
                                      # guard nothing; and maintenance-plan.py --validate errors on
                                      # any ref that does not resolve. If this ever unblocks, the
                                      # real collision to declare is any plan touching the `ai`
                                      # namespace or the Longhorn control plane in the same slot.
premises:
  # Every command below was RUN on 2026-09-17 while writing this plan and its actual
  # output is recorded in its `why`. They assert the facts that JUSTIFY THE BLOCK, so
  # that if the cluster changes underneath, this file fails loudly instead of ageing
  # into a stale opinion. Authoring constraints (plan-premises.py): one simple pipeline,
  # no `;` `&&` `||` `$(` backtick `>` `&`, and only kubectl/flux/talosctl/helm/git plus
  # bare grep/wc/awk/sed — no python3.
  - id: no-ingress-controller
    why: >-
      The oc8 chart's only non-Caddy exposure path is `ingress.enabled`, which renders a
      networking.k8s.io/v1 Ingress. ingress-nginx was deleted 2026-09-07, so that object is
      inert here and the app would be unreachable. Measured 2026-09-17: 0. If this ever
      returns non-zero someone re-introduced an ingress controller and §3.4's routing
      argument needs re-reading, not re-using.
    run: kubectl get ingressclass -o name | wc -l
    expect_exact: "0"
  - id: nodes-run-containerd-not-docker
    why: >-
      THE load-bearing premise. oc8 executes agents by talking the Docker Engine API
      (backend/src/oc8/sandbox/docker_driver.py -> `docker.from_env()`); its k8s option is a
      hostPath mount of /var/run/docker.sock. These nodes run containerd only — no dockerd,
      no podman daemon (`talosctl services` lists containerd/cri and nothing else). containerd's
      socket speaks CRI, not the Docker Engine API, so it is not a substitute. Measured
      2026-09-17: "containerd://2.2.7 containerd://2.2.7 containerd://2.2.7".
    run: kubectl get nodes -o jsonpath='{.items[*].status.nodeInfo.containerRuntimeVersion}'
    expect_matches: "^(containerd://[0-9.]+ ?){3}$"
  - id: not-already-installed
    why: >-
      Guards against this file being executed twice or against a hand-rolled install appearing
      out-of-band. CORRECTED 2026-09-17 (doc-agent): the first version of this premise ran
      `kubectl get ns -o name | grep -c oc8`, which was INERT — §3.1 installs into the
      PRE-EXISTING `ai` namespace and never creates an `oc8` namespace, so it returned "0"
      whether or not an install existed, i.e. it could not fail for the reason it claimed to
      exist. That is the inert-guard failure mode this repo treats as a defect, not a nit.
      Now asserts the object the plan would actually create. NEGATIVE CONTROL RUN 2026-09-17:
      the same pipeline against `openclaw` (a HelmRelease that DOES exist in `ai`) printed "1",
      proving it detects a match rather than passing on an empty result. Mechanics: `grep -c`
      prints "0" and exits 1 on no-match, and plan-premises.py fails early only when rc!=0 AND
      stdout is empty (plan-premises.py:179), so a clean "0" passes.
    run: kubectl get helmrelease -n ai -o name | grep -c oc8
    expect_exact: "0"
  - id: routing-target-exists
    why: >-
      §3.4 attaches the HTTPRoute to envoy-internal. If that gateway is not Programmed the
      routing half of this plan is void. Measured 2026-09-17: True.
    run: kubectl get gateway -n network envoy-internal -o jsonpath='{.status.conditions[?(@.type=="Programmed")].status}'
    expect_exact: "True"
  - id: static-storageclass-exists
    why: >-
      §3.3 binds both volumes through longhorn-static speaking names. Measured 2026-09-17.
    run: kubectl get sc longhorn-static -o jsonpath='{.metadata.name}'
    expect_exact: "longhorn-static"
---

# oc8 Community Edition — install evaluation (BLOCKED)

## 1) Summary & why blocked

### 1.1 What the product is

**oc8** (`github.com/oc8-ai/oc8`, LGPL-3.0-or-later) is a self-hosted **AI agent
orchestration platform** — "the open platform where AI agents do the work across your
business". Agents are configured with a model, a knowledge set, tools, and an
autonomy/escalation boundary, then run real work (triage, drafting, updating business
systems) with human approval gates. Tool calls leave through an MCP gateway.

Runtime shape (from `docker-compose.yml`, `ARCHITECTURE.md` and the chart):

| Component | What it is |
|---|---|
| `frontend` | React/Vite SPA, ClusterIP :3000 |
| `backend` | FastAPI REST/WebSocket API, :8099, `/health` |
| `worker` | async task execution (chart default **2 replicas**) |
| `ingestion-worker` | RAG/document ingestion |
| `scheduler` | cron/event triggers |
| `migrate` | one-shot `alembic upgrade head` (+ optional demo seed) |
| `postgres` | **pgvector/pgvector:pg15** — the system of record |
| `redis` | queues + ephemeral state |
| `caddy` | edge proxy, the sole external entry point |
| `runtime-provisioner` | **compose only** — sole owner of `docker.sock`, spawns agent sandboxes |
| `minio` | **compose only** — S3 for chat/agent file attachments |
| `ollama` | optional bundled StatefulSet |

Needs: PostgreSQL 15 **with pgvector**, Redis, an S3-compatible endpoint, a model provider
(Anthropic / OpenAI / Mistral / OpenRouter / any OpenAI-compatible endpoint, incl. Ollama),
and — for agents to actually run — a **container runtime it can drive over the Docker Engine
API**. No GPU is required by oc8 itself. No licence key, no activation, no paid tier: the
Community Edition is fully open-source.

### 1.2 The four blockers

**(a) There is no image to deploy, and no CI that builds one.** This is the hard one.
The chart's defaults are bare names — `images.backend.repository: oc8-backend`, `tag: latest`
(and `oc8-frontend`) — which resolve to `docker.io/library/oc8-backend:latest`, which does not
exist. The chart README states the prerequisite plainly: *"**Container images** built from this
repository"*, followed by `docker build -f Dockerfile.backend -t oc8-backend:latest ./backend`.
Verified 2026-09-17: the GitHub org publishes **zero container packages**; Docker Hub has
nothing; and the upstream repo contains **no `.github/` directory at all** — no workflows, so
nothing builds or publishes images on any commit. Adopting oc8 therefore is not "install a
product", it is "fork it, build two images, publish them to `ghcr.io/nachtschatt3n/**`, and own
the rebuild treadmill". Note the house rule this lands in: an image we build is an image
**we** are upstream for, so every future CVE in it is our work queue, never an AR-029
acceptance (CLAUDE.md, "THE EXCEPTION — our own images"). That is a software-ownership
commitment, not a deployment.

**(b) There is no published Helm chart.** The chart lives at `deploy/helm/oc8` inside the
application repo. The install instruction is `helm upgrade --install oc8 ./deploy/helm/oc8`
from a git checkout, and the README says publishing happens *"When `charts.oc8.io` is live"*.
There are **no git tags and no GitHub releases**; `Chart.yaml` says `version: 0.1.0`,
`appVersion: "0.1.0"`. Flux *can* source a chart from a `GitRepository`, so this is not fatal
on its own — but the pin would be a commit SHA on a third-party repo with no release
discipline, and this repo has 111 HelmRepository-sourced charts against exactly **one**
GitRepository-sourced chart (flux-operator, our own infrastructure). It would be a novel
supply-chain shape adopted for an unproven dependency.

**(c) The product's core function cannot work on Talos — and the chart does not even offer
the safe version of it.** In compose, privilege is separated: `runtime-provisioner` is
*"the sole owner of docker.sock in the whole Community stack"*, and backend/worker reach it
over HTTP with a bearer token (`OC8_SANDBOX_DRIVER=provisioner`). **The Helm chart has no
`runtime-provisioner` template** (full template list verified) and never sets
`OC8_SANDBOX_DRIVER` or `OC8_SANDBOX_PROVISIONER_*`. The backend therefore falls back to its
config default `sandbox_driver: str = "docker"` (`backend/src/oc8/config.py:186`), i.e.
`docker.from_env()` → `unix:///var/run/docker.sock`. The chart's only offered path is
`backend.containerSocket.enabled: true`, a hostPath `type: Socket` mount that its own README
calls *"**root-equivalent** on the node. Only for dedicated test clusters."*

On these nodes that mount cannot even succeed:

```
# talosctl -n <node> list -l /run        (2026-09-17)
drwxr-xr-x  0 0  40  Sep  6 09:38  docker.sock      <-- a DIRECTORY, not a socket
drwxr-xr-x  0 0  60  Sep  6 09:38  podman
drwx--x--x  0 0 220  Sep  6 09:37  containerd
```

`/run/docker.sock` exists only because a Wazuh DaemonSet hostPath mount made kubelet create an
empty directory there; `talosctl services` lists `containerd` and `cri` and no docker or podman
daemon. A `type: Socket` hostPath fails kubelet's type check against a directory, and pointing
oc8 at the real containerd socket would not help — docker-py speaks the Docker Engine API, not
CRI. **Net: oc8 here would be a chat UI whose agents cannot execute.** The one thing the
product exists to do is precisely the thing this cluster cannot provide. We would also not
grant a root-equivalent node socket to a service that runs agent-authored code, even if Talos
offered one.

**(d) The vendor says it is not production software.** `docs/DEPLOY.md` has a *"Deliberate
limits"* section stating the stack *"targets local and server testing only, not production"*:
dev-login is *"an unauthenticated admin bypass, and it is on by default"* (`oc8.env: dev` is the
chart default; `POST /api/v1/auth/dev-login` mints org_admin tokens to anyone who reaches the
proxy), no forced TLS, no secrets manager, no HA, no backups. `SCOPE_AND_LIMITATIONS` adds the
agent sandbox lacks *"full multi-tenant isolation"*. The repo is 24 days old (created
2026-08-24), 18 stars, under active development.

### 1.3 Secondary findings (would matter even if (a)–(d) cleared)

- **The chart is not feature-equivalent to compose.** No MinIO template, yet the backend
  defaults to `s3_endpoint: "http://minio:9000"` with an empty `s3_secret_key`
  (`config.py:241-243`). File attachments would point at a service that does not exist.
- **Hard-coded database credentials.** `_helpers.tpl` renders
  `postgresql+asyncpg://oc8_app:oc8@…` and `postgresql+psycopg://oc8_migrate:oc8@…` — literal
  password `oc8`, not secret-backed. The vendor calls this acceptable *"only due to network
  isolation"*, which is a compose argument (no published ports); in-cluster it means any pod
  that can reach the Service can read the database.
- **RWO fan-out — the Multi-Attach trap, chart-default.** `oc8-sessions` is a **ReadWriteOnce**
  PVC mounted by `backend` (1) *and* `worker` (**2 replicas** by default) via the shared
  `oc8.backendVolumeMounts` helper. Three pods, one RWO volume, three nodes: on a 3-node
  cluster this deadlocks unless every pod is co-scheduled. Worse, **the chart exposes no
  rollout-strategy key at all** — neither Deployment template has a `strategy` field and
  `values.yaml` has no equivalent — so CLAUDE.md's mandatory `Recreate`/`maxSurge: 0` cannot be
  set through values. It would need a HelmRelease `postRenderers` kustomize patch, verified
  against the **rendered** Deployment.
- **Postgres 15 vs the house.** The house is on PostgreSQL 17/18 per app; oc8 pins
  `pgvector/pgvector:pg15` with no documented major-upgrade path.
- **Redundancy.** `ai` already runs openclaw, **paperclip** ("AI agent orchestration —
  multi-agent company management"), ai-sre, hermes-agent, anythingllm, librechat and
  open-webui. oc8 would be the fifth agent platform, overlapping paperclip and openclaw most.

### 1.4 Capacity — this is NOT why it is blocked

It would fit comfortably, and saying so keeps the block honest: the objection is fitness, not
resources.

| | per node | cluster |
|---|---|---|
| Allocatable | 17 vCPU, ~58 GiB | 51 vCPU, ~174 GiB |
| CPU requests today | ~60% | headroom on all 3 |
| Memory requests today | 37–50% | headroom on all 3 |
| Longhorn available | ~400 GiB | **~1202 GiB** (of 2790 GiB raw) |

oc8 would add ~8 pods (backend, 2 workers, ingestion-worker, scheduler, frontend, caddy,
postgres, redis). The chart ships **no resource requests or limits at all** (`resources: {}`
everywhere), so we would have to author them — untuned, since no published image exists to
measure. Storage: 20 GiB postgres + 10 GiB sessions = 30 GiB logical, 60 GiB at 2 replicas,
~5% of free Longhorn. Sessions grow with use (vendor measured 134 MB / 406 runs) and the
evidence sweep is **off by default** (`retentionDays: 0` = never delete), so app-side retention
would have to be enabled deliberately per the blueprint's high-churn rule.

---

## 2) Pre-checks

Run `python3 runbooks/plan-premises.py oc8-install` — all five premises must pass. They encode
the block's factual basis; a failure means the world changed and this file must be re-argued,
not executed.

Additionally, before any of §3 could begin, **all four must be true**:

1. `ghcr.io/nachtschatt3n/oc8-backend` and `-oc8-frontend` exist, built from a pinned upstream
   commit, with a rebuild pipeline we own. (Today: they do not exist.)
2. Upstream has cut a tag/release, or we accept pinning a third-party `GitRepository` to a SHA.
3. An agent-execution story exists that does **not** require a node-level Docker socket —
   upstream shipping a Kubernetes-native sandbox driver (Jobs/pods), or a
   `runtime-provisioner` chart template we can point at something safe. (Today: neither exists.)
4. An operator decision that a fifth agent platform is wanted alongside paperclip/openclaw.

---

## 3) Steps (scoped, NOT to be executed while status is `blocked`)

Written out so the work is costed if the blockers clear. GitOps only — every file below lands
in git and is reconciled by Flux; the sole manual action is the two Longhorn `Volume` CRs,
which Flux cannot own (the app Kustomization's `targetNamespace` would override their
`namespace: storage`). The documented in-pod-config exception does **not** apply: nothing here
is config on a PVC with no GitOps path.

### 3.1 Namespace

`ai` — matches `docs/applications.md` (openclaw, paperclip, anythingllm, ai-sre, hermes-agent).
Not a new namespace; not `my-software-*` (not ours), not `databases` (it is an app, not a store).

### 3.2 Files to add

```
kubernetes/apps/ai/oc8/ks.yaml                       # Flux Kustomization, targetNamespace: ai,
                                                     #   dependsOn longhorn (storage)
kubernetes/apps/ai/oc8/app/kustomization.yaml        # lists every file below
kubernetes/apps/ai/oc8/app/gitrepository.yaml        # upstream chart source, pinned to a SHA
kubernetes/apps/ai/oc8/app/helmrelease.yaml          # chart ./deploy/helm/oc8 + values + postRenderers
kubernetes/apps/ai/oc8/app/secret.sops.yaml          # SOPS — jwt secret, KEK, postgres password
kubernetes/apps/ai/oc8/app/longhorn-volume.yaml      # 2 Volume CRs — MANUAL kubectl apply, NOT in kustomization
kubernetes/apps/ai/oc8/app/pv.yaml                   # oc8-postgres + oc8-sessions (claimRef'd)
kubernetes/apps/ai/oc8/app/pvc.yaml                  # oc8-postgres (see 3.3)
kubernetes/apps/ai/oc8/app/httproute.yaml            # envoy-internal + Homepage metadata
kubernetes/apps/monitoring/kube-prometheus-stack/app/oc8-alerts.yaml
kubernetes/apps/monitoring/kube-prometheus-stack/app/kustomization.yaml   # MODIFIED, not new
```

The alerts file is mandatory and follows the house shape (53 siblings): PodNotReady (5m,
critical), PodCrashLooping (5m, critical), PodRestarted (1m, warning), with labels
`release: kube-prometheus-stack`, `app.kubernetes.io/name: kube-prometheus-stack`,
`app.kubernetes.io/part-of: kube-prometheus-stack` — without the `release` label the rule is
silently never loaded. oc8's `migrate` runs as an **initContainer**, not a Job, so the
Succeeded-phase exclusion is not needed here.

**The alerts file must ALSO be appended to that directory's `kustomization.yaml`.** That
`resources:` list is **enumerated, not globbed** — verified 2026-09-17: 53 alert files on disk,
all 53 listed explicitly, zero wildcards. A new `oc8-alerts.yaml` that is not added to the list
is never applied by Flux at all, which fails exactly the way the missing `release` label does:
silently, with a green Kustomization and no alerting. Verification step 9 (`/api/v1/rules`) is
what catches both.

### 3.3 Storage decision — `longhorn-static`, speaking names

Two volumes, each with the identifier repeated across the Longhorn `Volume`, the `PV`, the
`volumeHandle`, and the PVC: **`oc8-postgres`** (20 GiB) and **`oc8-sessions`** (10 GiB).

Two chart-specific complications, both real:

- **`oc8-sessions`**: the chart's PVC template (`sessions-pvc.yaml`) sets `accessModes`,
  `storageClassName` and `resources` but has **no `volumeName`**, so we cannot bind it by name
  from values. The bind must be driven from the other side: pre-create the PV with a
  `claimRef` to `ai/oc8-sessions` and set `backend.sessions.storageClassName: longhorn-static`.
  (The chart's generated name is conveniently already `oc8-sessions`, because `fullname`
  collapses to the release name when the release is called `oc8`.)
- **`oc8-postgres`**: this is a StatefulSet `volumeClaimTemplates`, which is the one case
  CLAUDE.md explicitly exempts — a generated PVC name (`data-oc8-postgres-0`) makes a speaking
  static PV impossible in the general case. Either accept dynamic `longhorn` here (documented
  exception) or, preferably and in line with `bundled-datastore-exit`, set `postgres.enabled:
  false` and stand a standalone pgvector Deployment up on a static `oc8-postgres` volume. The
  latter also fixes the pg15 pin and the hard-coded credentials.

RWO handling per §1.3: `worker.replicas: 1`, and a `postRenderers` kustomize patch forcing
`strategy: Recreate` on the backend and worker Deployments — then **verify the rendered
Deployment**, never the HelmRelease's Ready status.

### 3.4 Routing decision — `envoy-internal`, LAN-only

**Justified from what the product does, not from convenience.** oc8 orchestrates agents that
hold credentials to other systems, and the vendor ships an unauthenticated admin bypass on by
default. Nothing in its documented operation requires inbound reachability from the internet —
it has no documented required inbound webhooks; model providers are *outbound* calls. So:
`envoy-internal` (LAN-only, 192.168.55.103). If external access were ever wanted it would go
behind Authentik forward-auth first, as a separate, argued change — and `OC8_ENV=prod` would be
non-negotiable before either.

Shape B (non-`app-template` chart): set `caddy.enabled: false` **and** `ingress.enabled: false`
(the chart's Ingress is inert here — premise `no-ingress-controller`), then hand-write the
HTTPRoute, replicating Caddy's fan-out as two rules so we do not run a redundant proxy:

```yaml
---
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: oc8
  namespace: ai
  labels:
    gethomepage.dev/enabled: "true"          # the LABEL and the annotation are both required
  annotations:
    gethomepage.dev/enabled: "true"
    gethomepage.dev/name: "oc8"
    gethomepage.dev/group: "AI"
    gethomepage.dev/icon: "robot.png"        # verify the icon resolves before committing
spec:
  parentRefs:
    - group: gateway.networking.k8s.io
      kind: Gateway
      name: envoy-internal
      namespace: network
      sectionName: https                     # never http — owned by the https-redirect route
  hostnames:
    - "oc8.${SECRET_DOMAIN}"
  rules:
    - matches:
        - path: { type: PathPrefix, value: /api }
        - path: { type: PathPrefix, value: /llm }
        - path: { type: PathPrefix, value: /mcp }
        - path: { type: Exact,      value: /health }
      backendRefs:
        - group: ""
          kind: Service
          name: oc8-backend
          port: 8099
    - matches:
        - path: { type: PathPrefix, value: / }
      backendRefs:
        - group: ""
          kind: Service
          name: oc8-frontend
          port: 3000
```

No `external-dns` target annotation on the route — external-dns reads it from the parent
Gateway and silently ignores it here. The backend serves WebSockets; the gateway-wide 60s
`BackendTrafficPolicy` applies, and long-lived agent streams may need a per-route
`timeouts.request` — to be measured, not guessed.

### 3.5 Secrets — SOPS, generated, encrypted in place

Three required values, generated (never invented), written to the file **at its final repo
path** and encrypted there, because SOPS creation rules are path-based:

```bash
# values generated with: openssl rand -hex 32 | openssl rand -base64 32 | openssl rand -hex 16
# write kubernetes/apps/ai/oc8/app/secret.sops.yaml FIRST, then:
mise exec -- sops -e -i kubernetes/apps/ai/oc8/app/secret.sops.yaml
```

Encrypting from `/tmp` fails with *"no matching creation rules found"*. Model-provider API keys,
if used, belong in the same Secret. **`OC8_SECRET_KEK` is the key-encryption key for every
credential oc8 stores** — losing it is unrecoverable, so it must be in the age-encrypted repo
*and* covered by the off-site key vault before any real credential is entered.

### 3.6 Values that are non-negotiable

`oc8.env: prod` (kills dev-login), `backend.containerSocket.enabled: false`,
`backend.replicas: 1` (the init container runs `alembic upgrade head` on every backend pod
start), `ollama.enabled: false` (the house Ollama is the Mac mini; point `oc8.ollamaBaseUrl` at
it via `ollama-toolfix` if local models are wanted), `oc8.seedOnStart: false` (do not seed a
demo tenant into a real install), plus authored `resources` for all 8 pods.

---

## 4) Verification — must prove it WORKS, not that a pod is green

The characteristic failure here is a green pod behind a route nobody can reach, or a green pod
with an unwritable volume. Shape-only checks would pass in both cases.

1. **Flux + rollout**: `flux get kustomizations -A` and `flux get helmreleases -n ai` Ready;
   all 8 Deployments/StatefulSets at desired replicas.
2. **Storage is actually writable** (not merely Bound): exec into the backend and write and
   read back a file under `/var/lib/oc8/sessions`. A Bound PVC whose mount is read-only or
   wrong-uid is exactly the fresh-install failure this step exists to catch — note
   `oc8.sandboxUser` exists precisely because session-root ownership is deployment-specific.
3. **Migrations really ran**: `alembic current` inside the backend returns a revision, and the
   `oc8` database contains the expected tables — not just "the init container exited 0".
4. **pgvector is present**: `SELECT extname FROM pg_extension` includes `vector`. RAG silently
   degrades otherwise.
5. **The route serves from off-cluster**: from a LAN host (not via port-forward),
   `curl -sS -o /dev/null -w '%{http_code}' https://oc8.${SECRET_DOMAIN}/health` → 200, and the
   SPA root returns HTML. Port-forward proves the pod; only this proves the route.
6. **Auth is closed**: `POST /api/v1/auth/dev-login` must **fail** under `OC8_ENV=prod`. This is
   a gate that can fail, and the single most important one — if it succeeds, revert immediately.
7. **The product's actual function**: create an agent, assign a model, run one task, and confirm
   it completes. **This is the gate that fails today** — with no sandbox driver, execution
   cannot start. A deployment that passes 1–6 and fails 7 is a failed deployment, not a partial
   success.
8. **Homepage**: the entry appears in the AI group with a resolving icon.
9. **Alerts loaded**: the `oc8` group appears in Prometheus `/api/v1/rules` — a PrometheusRule
   missing the `release` label loads silently as nothing.
10. **Log ingestion**: records present in `logs-generic-default` filtered by
    `resource.attributes.k8s.namespace.name: ai` and the oc8 container names.

---

## 5) Rollback — honest

**Nothing is installed, so today "rollback" is not needing one.** If §3 were ever executed, the
revert is *mostly* clean but not entirely:

- `git revert <sha> && git push` removes the manifests; Flux prunes the HelmRelease and with it
  the Deployments, StatefulSet, Services and HTTPRoute. No CRDs are installed by this chart, so
  there is no cluster-scoped residue from that direction.
- **Left behind, requiring manual cleanup:**
  - the two Longhorn `Volume` CRs in `storage` (Flux never owned them — they were applied by
    hand, so a revert cannot remove them);
  - both PVs, which are `persistentVolumeReclaimPolicy: Retain` by house pattern, and the PVCs
    (the chart's own README warns *"Postgres and session PVCs are retained unless you delete
    them manually"*);
  - the StatefulSet's `volumeClaimTemplates` PVC if the bundled postgres was used — StatefulSet
    deletion never deletes those.
- **External state**: any model-provider API key used must be **revoked at the provider**; a
  revert does not do that. Any credential an agent was granted to a third-party system likewise.
- The namespace `ai` is pre-existing and must **not** be deleted.
- Images pushed to our own registry stay until pruned deliberately.

Deleting those PVCs is not itself dangerous (Longhorn, not CIFS — the storage-safety three-step
applies to CIFS/SMB/NFS), but it is destructive and needs explicit operator approval.

---

## 6) Interference notes

`blocked` + `window: null`, so it cannot be scheduled and interferes with nothing today.
If it ever unblocks, the collisions to declare are: any plan touching the `ai` namespace, and
anything touching the Longhorn control plane in the same slot (this allocates two new
2-replica volumes). It shares no manifest with any currently open plan.

**Recommendation: do not adopt oc8 on this cluster.** The blockers are not sequencing problems
that a window can absorb — (a) and (c) are structural. Worth re-evaluating **only** when
upstream publishes signed images and a versioned chart *and* ships a Kubernetes-native agent
sandbox that does not require a node-level Docker socket. Until then the honest alternative is
that paperclip and openclaw already occupy this niche here.

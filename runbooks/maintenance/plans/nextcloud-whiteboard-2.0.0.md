---
plan_id: nextcloud-whiteboard-2.0.0
component: nextcloud-whiteboard        # exact version-check component key (version-check-current.md
                                       # line 201) — do not rename to "whiteboard"
pr: null                               # NO Renovate PR. Verified 2026-09-17 with `gh pr list --state
                                       # open`: the only open PRs are #217 (esphome) and #212 (talos
                                       # CLI). This is a coverage.py direct-bump item, held because
                                       # coverage returns PLAN for `utype == "major"`.
kind: image
current: "v1.5.9"
target: "v2.0.0"
update_type: major
risk: medium                           # NOT low: a major on an internet-facing service (envoy-external,
                                       # whiteboard.<domain>) whose COMPANION Nextcloud app moves in a
                                       # different commit that this repo does not own (§1.4).
                                       # NOT high: one stateless container, no PVC, no DB, no migration
                                       # on the leg this plan owns, both tags verified present in GHCR,
                                       # and the revert is one line (§5.1).
est_duration_min: 25                   # 8 pre-checks (incl. the two in-pod occ gates) + 3 edit/commit/
                                       # push + 4 reconcile & rollout + 10 verification (the browser
                                       # collaboration round-trip in §4.6 is the slow part and cannot
                                       # be skipped — it is the only gate that proves the feature works)
needs_reboot: false
touches:
  namespaces: [office]
  resources:
    - deployment/nextcloud-whiteboard          # the ONLY object this plan mutates: one image tag
    - service/nextcloud-whiteboard             # unchanged; named in §4.5
    - httproute/nextcloud-whiteboard           # unchanged; named in §4.5. Verified Accepted=True,
                                               # ResolvedRefs=True 2026-09-17
    - secret/nextcloud-config                  # READ ONLY: key `whiteboard-jwt-secret` feeds
                                               # JWT_SECRET_KEY. Not rewritten — see §1.3, the key
                                               # STRING is unchanged upstream
    - deployment/nextcloud                     # NOT restarted, NOT edited. Read-only `occ` gates in
                                               # §2.3/§4.4 exec into it
    - pvc/nextcloud-config                     # READ ONLY in the happy path: `custom_apps/whiteboard`
                                               # lives here. WRITTEN only if the §5.3 app-leg rollback
                                               # is taken
  shared: []                                   # DELIBERATE, and checked rather than defaulted.
                                               # No Gateway/HTTPRoute object changes (the route is
                                               # untouched — we roll one Pod BEHIND it), no
                                               # cert-manager, no cilium/coredns, no Longhorn volume,
                                               # no shared DB, and no monitoring instrument: there is
                                               # NO ServiceMonitor in ns office and the backend logs
                                               # "Metrics disabled" (measured 2026-09-17), so this
                                               # plan's §4 never reads Prometheus and a same-night
                                               # kube-prometheus-stack bump cannot invalidate it.
                                               # The app IS on the public edge; §6 states the one
                                               # condition under which gateway/envoy must be added.
depends_on: [nextcloud-34.0.4]         # ORDERING IS THE WHOLE POINT OF THIS PLAN — see §1.4.
                                       # The Nextcloud APP half of whiteboard 2.0.0 is delivered by
                                       # THAT plan, not this one: its §3.2 runs `occ app:update --all`
                                       # and the live server already offers whiteboard 2.0.0
                                       # (measured §1.4). So the app moves on 2026-09-20 whether or
                                       # not anyone plans it, and this backend must follow it.
                                       # COST, stated honestly: window-scheduler.py:225 skips a plan
                                       # whose depends_on is not in the EXECUTED set, so this will not
                                       # be AUTO-placed into sun-attended:2026-09-20 alongside
                                       # nextcloud-34.0.4. That is acceptable and the interim skew is
                                       # the benign direction (§1.5). The PREFERRED outcome is that
                                       # the window agent hand-assigns this to the SAME slot and runs
                                       # it immediately AFTER nextcloud-34.0.4 — §6.
conflicts_with:
  - bitnamilegacy-exit-nextcloud-db    # that plan restarts deployment/nextcloud and drives it through
                                       # a DB replatform; my §2.3/§4.4 occ gates and §4.6 browser check
                                       # read that same server and would be meaningless beside it. It
                                       # is `blocked` with window: null today, so there is no live
                                       # collision — this is the same forward guard nextcloud-34.0.4
                                       # carries, for when it revives. Reciprocity is ONE-SIDED (I
                                       # cannot edit that file); window-scheduler.py honours
                                       # conflicts_with symmetrically via its `names_me` branch, so
                                       # the guard holds regardless.
security_ref: F-7b0ce7e2               # the CVE driver for the image leg. Detail lives on the finding
                                       # record ONLY — never counts, IDs or vocabulary here (public
                                       # repo, docs/sops/vulnerability-disclosure.md).
capability_change: true                # HONEST, and it is the backend leg that earns this, not just
                                       # the app: v2.0.0 adds a room-authorization gate that can REFUSE
                                       # a socket join v1.5.9 accepted (§1.2), and enforces creator
                                       # attribution on every broadcast payload. Users can see both.
                                       # => human-gated per runbooks/autonomy-policy.yaml (`default:
                                       # human-gated`), which also matches the deny rule's
                                       # "operator-supervised only". NEVER the unattended nightly lane.
rollback_class: git-revert             # TRUE FOR THE LEG THIS PLAN OWNS, and only that leg. The
                                       # backend is a stateless container: emptyDir /tmp, no PVC, no
                                       # DB, no migration, and v1.5.9 is still pullable (digest
                                       # verified §2.2). §5.1 is a genuine one-line revert.
                                       # READ §5.3 BEFORE ASSUMING IT IS THE WHOLE STORY: if the
                                       # Nextcloud APP has already moved to 2.0.0, reverting this
                                       # image does NOT restore the pre-change world, and the app leg
                                       # is NOT a git revert.
finding_refs: [F-7b0ce7e2]             # ownership claim: this plan is what answers that finding. It
                                       # currently reads `accepted` under AR-029 ("already on the
                                       # newest upstream tag"); that acceptance became STALE on
                                       # 2026-09-16 when v2.0.0 published — see §1.6.
premises:
  # Runner grammar (runbooks/plan-premises.py): kubectl/flux/git/helm/talosctl READ verbs plus the
  # ALLOWED_BARE text filters. `kubectl exec` is NOT allowed, by design. The whiteboard APP version
  # lives in Nextcloud's DB + custom_apps and is only readable via `occ`, so the APP assertion CANNOT
  # be a premise — it is an abort-on-mismatch EXECUTOR GATE in §2.3 instead. Every value below was
  # measured live on 2026-09-17 by running the command verbatim.
  - id: live-whiteboard-backend-is-still-v1.5.9
    why: >-
      `current:` claims v1.5.9 on the live collaboration backend. If it already moved (a hand bump, a
      Step 0 direct-bump, a previous partial run of this plan) then the §3.2 sed is a no-op, the §4.2
      digest baseline is wrong, and the §4.3 version-banner gate would compare against the wrong
      string. This is the plan's central factual claim about the world.
    run: "kubectl get deploy -n office nextcloud-whiteboard -o jsonpath='{.spec.template.spec.containers[0].image}'"
    expect_exact: "ghcr.io/nextcloud-releases/whiteboard:v1.5.9"
  - id: git-pin-is-still-v1.5.9-and-there-is-exactly-one
    why: >-
      §3.2 edits exactly one line in one file. If the pin already differs the sed is a no-op and the
      commit is empty; if a SECOND pin had appeared the edit would be partial. The count, not just the
      presence, is the assertion.
    run: "git show HEAD:kubernetes/apps/office/nextcloud/app/whiteboard-proxy.yaml | grep -c 'whiteboard:v1\\.5\\.9'"
    expect_exact: "1"
  - id: live-nextcloud-server-is-on-the-34.0.x-line
    why: >-
      The compatibility verdict in §1.4 is derived against a Nextcloud 34 server: whiteboard app 2.0.0
      declares `>=31 <=35`, so 34.0.x is in range with room either side. This premise deliberately
      accepts ANY 34.0.x patch, because nextcloud-34.0.4 may legitimately have run first and moved the
      server to 34.0.4 — that is the expected happy path, not a deviation. It FAILS on a major/minor
      move (33.x, 35.x), which would invalidate both the app-compatibility range and every measurement
      in §1, and must force a re-derivation rather than a blind run.
    run: "kubectl get deploy -n office nextcloud -o jsonpath='{.spec.template.spec.containers[?(@.name==\"nextcloud\")].image}'"
    expect_matches: "^docker\\.io/nextcloud:34\\.0\\.[0-9]+$"
  - id: whiteboard-deployment-has-one-ready-replica
    why: >-
      A backend that is not Ready right now is already broken, and this bump would be blamed for it.
      One Ready replica is the only state this plan starts from, and it is also the §4.1 baseline.
    run: "kubectl get deploy -n office nextcloud-whiteboard -o jsonpath='{.status.readyReplicas}'"
    expect_exact: "1"
  - id: route-still-points-at-this-service
    why: >-
      §4.5 exercises whiteboard.<domain> through the envoy-external Gateway and asserts it reaches THIS
      backend. If the HTTPRoute were re-pointed (an Envoy-phase edit, a hostname move) the external gate
      would be measuring something else entirely and could pass while this service is dead.
    run: "kubectl get httproute -n office nextcloud-whiteboard -o jsonpath='{.spec.rules[0].backendRefs[0].name}'"
    expect_exact: "nextcloud-whiteboard"
  - id: jwt-secret-still-sourced-from-nextcloud-config
    why: >-
      The single shared secret is the whole coupling between this backend and the Nextcloud server
      (§1.3). §1.3's verdict "no secret rework is required" rests on the wiring being unchanged: env
      JWT_SECRET_KEY <- secret/nextcloud-config key whiteboard-jwt-secret. If that moved, the upstream
      analysis still holds but this plan's "no secret work" claim does not.
    run: "kubectl get deploy -n office nextcloud-whiteboard -o jsonpath='{.spec.template.spec.containers[0].env[?(@.name==\"JWT_SECRET_KEY\")].valueFrom.secretKeyRef.name}'"
    expect_exact: "nextcloud-config"
  - id: storage-strategy-is-still-lru
    why: >-
      §4.4 asserts the v2.0.0 backend logs "Server initialized with lru storage strategy". That gate is
      only meaningful if we are in fact asking for lru. Verified upstream that v2.0.0 still honours the
      env var and still implements the strategy (ConfigUtility.js:42, StorageService.js:47,
      ConstantsUtility.js:12) — this premise pins OUR side of that contract.
    run: "kubectl get deploy -n office nextcloud-whiteboard -o jsonpath='{.spec.template.spec.containers[0].env[?(@.name==\"STORAGE_STRATEGY\")].value}'"
    expect_exact: "lru"
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/verification-contents-not-shape.md
  - docs/sops/gateway-api-httproute.md
  - docs/sops/maintenance-windows.md
status: draft
window: null
generated: "2026-09-17"
---

# nextcloud-whiteboard v1.5.9 → v2.0.0

## 1) Summary & why held

### 1.1 What this changes

**One line, one file.** `kubernetes/apps/office/nextcloud/app/whiteboard-proxy.yaml:25`

| File | Key | From | To |
|---|---|---|---|
| `kubernetes/apps/office/nextcloud/app/whiteboard-proxy.yaml` | `image` | `ghcr.io/nextcloud-releases/whiteboard:v1.5.9` | `ghcr.io/nextcloud-releases/whiteboard:v2.0.0` |

Delivery is a **plain Kustomize `Deployment`**, not a HelmRelease — there is no chart,
no `values`, no `occ` and no maintenance mode on this leg. `kustomization.yaml`
includes `./whiteboard-proxy.yaml` directly.

**The pin-duplication trap, checked:** the string `v1.5.9` also appears in three
files under `runbooks/tests/` —
`test-raw-manifest-image-coverage.py:65-66`, `test-wazuh-not-self-exempt.py:65`,
`test-pick-latest-semver-tag.py:95`. **None of them is a pin.** They are assertion
fixtures for the version-check parsing primitives (`_split_image_ref`,
`_should_skip`, the semver picker), and the third one exists precisely to assert
that `v2.0.0-beta.1` must NOT mask the v1.5.x line. They are inert with respect to
the cluster and **must not be edited by this plan** — changing them would silently
weaken the regression tests. The load-bearing pin count is **one**, and premise
`git-pin-is-still-v1.5.9-and-there-is-exactly-one` asserts the number, not merely
the presence.

### 1.2 What v2.0.0 actually breaks — measured from source, not from the notes

The release notes (GitHub releases API, `nextcloud/whiteboard`, tag `v2.0.0`,
published `2026-09-16T09:46:53Z`) read as mostly additive, and the GitHub *compare*
API reports `websocket_server/*` at **0 additions / 0 deletions** — which is wrong
and would have led this plan to conclude "the backend did not change". Both tarballs
were extracted and diffed directly. The backend **did** change:

- **`websocket_server/Services/RoomLifecycleService.js` — a new authorization gate.**
  `joinRoom()` now returns a boolean and refuses the join outright:

  ```js
  const roomClaims = [socketData.fileId, socketData.roomID]
      .filter((claim) => claim !== null && claim !== undefined)
  const isAuthorizedRoom = roomClaims.length > 0
      && roomClaims.every((claim) => GeneralUtility.validateRoomId(claim) === validatedRoomId)
  if (!isAuthorizedRoom) {
      console.warn(`[SECURITY] Socket ${socket.id} rejected from unauthorized room ${validatedRoomId}`)
      return false
  }
  ```

  In v1.5.9 this check **does not exist** — the old code returned early with no
  value and joined anyway. This is the single behaviour that can break the feature
  for us, and §4.6 is built on it.
- **`ServerService.start()` is now `async` and awaits `socketService.ready`** (the
  socket engine is initialized before the listener accepts) — upstream "Wait for
  WebSocket initialization" (#1275).
- **`ViewportService` now parses the broadcast payload as JSON** and applies the new
  `websocket_server/Utilities/CreatorMetadataUtility.js` — upstream "Protect creator
  attribution" (#1289). Non-JSON messages fall through to the old passthrough.
- **`Dockerfile`: `node:26.2.0-alpine` → `node:26.8.2-alpine`**, plus OCI labels.
  The Node base move is the CVE driver behind `security_ref` — nothing else in the
  image changed materially.

**What did NOT change, and it matters more than what did:**

- `websocket_server/main.js`: the diff is **two removed eslint comment lines**.
- The env-var contract is intact. `JWT_SECRET_KEY`, `NEXTCLOUD_URL`,
  `STORAGE_STRATEGY` and `PORT` are all still read (`ConfigUtility.js:32,42,61,72`),
  `'lru'` is still implemented (`StorageService.js:47`) and is still the default
  (`ConstantsUtility.js:12`). **No new REQUIRED env var is introduced.**
  `RECORDINGS_DIR` defaults to `/tmp/whiteboard-recordings`, which our 2 Gi
  `emptyDir` at `/tmp` already covers.

So the honest characterization of the hold: **this was held because it is a major
(`coverage.py` returns PLAN for `utype == "major"`), and the genuinely major half of
the release is the Nextcloud APP — Vue 3, a new minimum platform, a template/library
service — which this repo does not deliver.** The container leg is a small, tightly
scoped change. That does not make it trivial: see §1.4.

### 1.3 The coupling — one shared secret, and it survives

Whiteboard is a companion service. The Nextcloud app mints a JWT; the backend
verifies it with the same secret. Two ways that can break silently on a major, and
**both were checked against upstream source and both are clear**:

- **Config key rename.** v2.0.0 introduces `lib/ConfigKeys.php` and routes every
  read through it, which *looks* like a rename. It is not — each new constant
  resolves to the string the app has always used: `JWT_SECRET_KEY` still resolves
  to `jwt_secret_key`, and `COLLAB_BACKEND_URL` still resolves to
  `collabBackendUrl`. **The key strings are unchanged**, so the live values (the
  configured backend URL, and the JWT secret) keep working and no
  `occ config:app:set` is needed.
- **JWT claim shape.** `diff v1.5.9/lib/Service/JWTService.php v2.0.0/lib/Service/JWTService.php`
  is **empty**. The payload is byte-identical: `userid`, `fileId`, `isFileReadOnly`,
  `user{id,name}`. This is what makes the new `roomClaims` gate in §1.2 satisfiable
  by an OLD app as well as a new one — `fileId` has always been in the token.

There is also **no version handshake in either direction**: grepping both trees for
`appVersion` / `version mismatch` / `incompat` / `minVersion` finds nothing in
`websocket_server/` or `lib/`. Neither side refuses the other by version number.

### 1.4 THE REASON THIS PLAN EXISTS — the app leg moves on 2026-09-20 without us

Measured on the live cluster, 2026-09-17:

| | |
|---|---|
| Live backend image | `ghcr.io/nextcloud-releases/whiteboard:v1.5.9` |
| Live Nextcloud server | `34.0.3` (`occ status` → `34.0.3.2`) |
| Live whiteboard **app** | **`1.5.9`**, installed in `/var/www/html/custom_apps/whiteboard` (on `pvc/nextcloud-config`) |
| App 2.0.0 platform range | `>=31 <=35` (appstore API for platform 34.0.3, and `appinfo/info.xml`) — **34 is in range** |
| What the live server already offers | `occ app:update --showonly` → **`whiteboard new version available: 2.0.0`** |

And `occ upgrade` installs pending appstore apps. Verified in upstream server source,
not quoted from another plan — `nextcloud/server` `v34.0.3`, `lib/private/Updater.php:244`:

```php
// upgrade appstore apps
$this->upgradeAppStoreApps($this->appManager->getEnabledApps());
```

which calls `isUpdateAvailable($app)` → `updateAppstoreApp($app)` per enabled app.

**Therefore:** the approved plan `nextcloud-34.0.4` (`awaiting-go`, operator GO
recorded, `sun-attended:2026-09-20`) will move the whiteboard **app** 1.5.9 → 2.0.0
— at its §3.2 `occ app:update --all`, or failing that inside the entrypoint's
`occ upgrade` at §3.4. **It does not need to intend to; it cannot avoid it.**

This plan is the other half of that change.

> **Repo correction owed to `nextcloud-34.0.4` (do not silently plan around it).**
> That plan's §1.3 enumerates the pending appstore set as measured **2026-09-15** and
> whiteboard is **absent** from it — correctly, because 2.0.0 published 2026-09-16,
> the day after its review. Its §3.3 also says *"`metrics`, `whiteboard`, `mariadb`
> and `redis` specs do not change and do not restart"*, which is true of the
> Kubernetes specs and now stale about the app. Neither is a defect in that plan; it
> is exactly the drift already filed as `F-58f0bbab`. The executor of
> `nextcloud-34.0.4` should expect one extra line (`whiteboard updated`) in its
> §3.2 `app-update-all.log` and should NOT treat it as an anomaly.

### 1.5 Which skew is benign — stated plainly, because one of them will exist

Neither ordering is validated upstream (upstream ships app + backend from one tag and
tests them together), so this is a judgement from the source above, not a guarantee:

- **App 2.0.0 / backend 1.5.9** (what 2026-09-20 produces if this plan does not run
  in the same slot): the old backend simply lacks the new room gate and the creator
  metadata protection. The JWT it verifies is unchanged (§1.3). This is also the most
  common configuration in the wild — appstore updates the app, the container gets
  forgotten. **Benign, and it is the default.**
- **Backend 2.0.0 / app 1.5.9** (what running this plan FIRST would produce): the new
  room gate evaluates `[socketData.fileId, socketData.roomID]`, and a 1.5.9 token
  already carries `fileId` (§1.3), so the gate is satisfiable. **Probably fine, but it
  is the direction nobody runs.**

Both end in the same place. The correct end state is **both on 2.0.0**, which is why
`depends_on` names `nextcloud-34.0.4` rather than this plan racing ahead of it.

### 1.6 Security driver

`security_ref: F-7b0ce7e2` / `finding_refs: [F-7b0ce7e2]`. That record currently reads
`accepted` under **AR-029** — the "already on the newest upstream tag, needs an
upstream rebuild we don't do" branch. **That acceptance went stale on 2026-09-16.**
`security-check.py` gates the acceptance on `_newer_upstream_tag_exists(img)`
returning `False`; a newer tag now exists, so the next sweep will return `True` and
the finding leaves AR-029 as actionable. No rebuild is being proposed here — this is
exactly the sanctioned remedy for a third-party image: **bump to a newer upstream
tag.** Detail stays on the record (public repo).

## 2) Pre-checks

Run from the repo root on the Mac mini. Everything here is read-only.

```bash
cd /Users/mu/code/cberg-home-nextgen
```

**2.0 Premises — every one must PASS.**

```bash
.venv/bin/python3 runbooks/plan-premises.py nextcloud-whiteboard-2.0.0 --require-premises
```

**2.1 Cluster / Flux green, nothing in flight.**

```bash
flux get kustomizations -A | awk 'NR==1 || $5 != "True"'     # expect: header only
flux get kustomizations -n flux-system nextcloud             # READY True
kubectl get pods -n office -l app=nextcloud-whiteboard        # 1/1 Running
```

**2.2 The target tag exists, and so does the rollback tag** (application-update SOP
Step 0 — never bump to an unpublished tag). Measured 2026-09-17; the digests are the
§4.2 baseline and the §5.1 proof:

```bash
TOKEN=$(curl -s "https://ghcr.io/token?scope=repository:nextcloud-releases/whiteboard:pull&service=ghcr.io" \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
for T in v2.0.0 v1.5.9; do
  printf '%s ' "$T"
  curl -sI -H "Authorization: Bearer $TOKEN" \
    -H "Accept: application/vnd.oci.image.index.v1+json" \
    "https://ghcr.io/v2/nextcloud-releases/whiteboard/manifests/$T" \
    | grep -i docker-content-digest
done
```

Expect exactly:

```
v2.0.0 docker-content-digest: sha256:059596633333d009890c64858f89f133ccd973a2e0823ad960a0cc05cf8657f1
v1.5.9 docker-content-digest: sha256:b60b7633f90d106ac6922f9bc27e1a1ca2442488b740fefdae4c812f34e9cebc
```

**A different digest for `v2.0.0` means upstream rebuilt the tag after this plan was
written — STOP and re-read the release before continuing** (the §4.2 gate would fail
anyway, which is the point). A missing `v1.5.9` means §5.1 has no target: **abort, do
not proceed without a rollback image.**

**2.3 The APP-side gates the premise runner cannot express** (they need `occ`, and
`kubectl exec` is deliberately outside the premise allowlist). **ABORT on any
mismatch.**

```bash
OCC="kubectl exec -n office deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c"

$OCC 'php occ status --output=json' \
  | python3 -c "import sys,json;d=json.load(sys.stdin);print(d['version'],d['maintenance'],d['needsDbUpgrade'])"
#   expect: 34.0.3.x (or 34.0.4.x) False False
#   maintenance=True or needsDbUpgrade=True => the server is mid-upgrade or stuck:
#   STOP. That is nextcloud-34.0.4's §5.1 territory, not this plan's.

$OCC 'php occ app:list --output=json' \
  | python3 -c "import sys,json;print('whiteboard =', json.load(sys.stdin)['enabled'].get('whiteboard'))"
#   RECORD THE ANSWER — it selects the branch, and it is the one thing this plan
#   cannot know in advance:
#     "whiteboard = 2.0.0"  -> nextcloud-34.0.4 has run. This is the EXPECTED path:
#                              the app is ahead, this plan closes the skew. PROCEED.
#     "whiteboard = 1.5.9"  -> the app has NOT moved yet. PROCEED ONLY with the
#                              operator's explicit ack that this deliberately lands
#                              the backend first (§1.5, the less-travelled direction),
#                              or defer this plan to the slot after nextcloud-34.0.4.
#     "whiteboard = None"   -> the app is DISABLED or absent. STOP: §4.6 cannot be
#                              run at all, so this bump would be unverifiable.

$OCC 'php occ config:app:get whiteboard collabBackendUrl'
#   expect: wss://whiteboard.<domain>  (measured 2026-09-17). An empty value means the
#   app is not pointed at this backend and §4.6 would be testing nothing.
```

**2.4 Baseline the thing we are about to change**, so §4 compares against a
measurement rather than a memory:

```bash
kubectl get pod -n office -l app=nextcloud-whiteboard \
  -o jsonpath='{.items[0].status.containerStatuses[0].imageID}{"\n"}'
#   expect: ghcr.io/nextcloud-releases/whiteboard@sha256:b60b7633f90d106ac6922f9bc27e1a1ca2442488b740fefdae4c812f34e9cebc

kubectl logs -n office deploy/nextcloud-whiteboard --tail=20 | grep -iE 'whiteboard@|storage strategy'
#   expect: "> whiteboard@1.5.9 server:start" and
#           "Server initialized with lru storage strategy"
```

**2.5 Scope the alert silence to this Deployment, not the namespace.** A
namespace-wide silence over `office` would also blind Nextcloud, paperless, mealie
and penpot for the duration — and is the reason `nextcloud-34.0.4` has to declare a
conflict with `nextcloud-mcp-0.187.1`. This plan does not need that blast radius.

```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-alertmanager 9093:9093 >/dev/null 2>&1 & PF=$!
sleep 2
NOW=$(python3 -c "from datetime import *;print(datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z'))")
END=$(python3 -c "from datetime import *;print((datetime.now(timezone.utc)+timedelta(hours=2)).strftime('%Y-%m-%dT%H:%M:%S.000Z'))")
curl -s -X POST localhost:9093/api/v2/silences -H 'Content-Type: application/json' -d '{
  "matchers":[{"name":"namespace","value":"office","isRegex":false,"isEqual":true},
              {"name":"deployment","value":"nextcloud-whiteboard","isRegex":false,"isEqual":true}],
  "startsAt":"'$NOW'","endsAt":"'$END'","createdBy":"maintenance-window-agent",
  "comment":"nextcloud-whiteboard v1.5.9->v2.0.0 — rollout noise. auto-expires 2h"}'
kill $PF 2>/dev/null

runbooks/update-marker.sh add nextcloud-whiteboard office 2 "v1.5.9->v2.0.0 upgrade"
```

## 3) Steps

**3.1 Go/no-go.** All premises PASS, 2.1–2.4 clean, the §2.3 branch recorded and its
condition met. An operator is present and able to open a whiteboard in a browser for
§4.6 — **without that, this plan cannot be verified and must not be run** (§4.6 is the
only gate that proves the feature works).

**3.2 GitOps edit — one file, one line.** Dry-tested on a scratch copy of the real
file on macOS (BSD sed: no `\s`, anchored, `|` delimiter because the value contains
`/`):

```bash
cd /Users/mu/code/cberg-home-nextgen
git fetch origin main && git merge --ff-only origin/main

WB=kubernetes/apps/office/nextcloud/app/whiteboard-proxy.yaml
sed -i '' -E 's|^(        image: ghcr\.io/nextcloud-releases/whiteboard:)v1\.5\.9$|\1v2.0.0|' "$WB"

grep -c 'whiteboard:v2\.0\.0' "$WB"     # expect exactly 1
grep -c 'whiteboard:v1\.5\.9' "$WB"     # expect exactly 0
git diff --stat                          # expect exactly this one file
```

The dry run produced exactly this diff and nothing else:

```
25c25
<         image: ghcr.io/nextcloud-releases/whiteboard:v1.5.9
---
>         image: ghcr.io/nextcloud-releases/whiteboard:v2.0.0
```

**3.3 Commit and push** (shared worktree — `--only` with an explicit path, and verify
the subject is ours before pushing; two sessions committing in the same second can
swap message files):

```bash
cat > /tmp/wb-msg.txt <<'EOF'
chore(nextcloud-whiteboard): collaboration backend v1.5.9 -> v2.0.0

Pairs the collaboration backend with the Nextcloud whiteboard app 2.0.0 that
`occ upgrade` installs from the appstore (plan nextcloud-34.0.4). Node base
26.2.0 -> 26.8.2; adds an upstream room-authorization gate on socket join.
Env contract, JWT claim shape and app config keys are unchanged upstream.

Plan: runbooks/maintenance/plans/nextcloud-whiteboard-2.0.0.md
security_ref: F-7b0ce7e2
EOF

git commit --only kubernetes/apps/office/nextcloud/app/whiteboard-proxy.yaml -F /tmp/wb-msg.txt
git show --stat HEAD                      # is this file the ONLY one? if not, see CLAUDE.md
git log -1 --format=%s                    # MUST be the subject above; amend before push if not
git push origin main
```

**3.4 Let Flux reconcile.** No manual `flux reconcile` — the webhook drives it. The
Deployment is `RollingUpdate` with an `emptyDir` (no RWO Longhorn PVC), so there is no
Multi-Attach hazard and no need for `Recreate`.

```bash
kubectl rollout status -n office deploy/nextcloud-whiteboard --timeout=180s
```

## 4) Verification

> **CONTENTS ASSERTION: real-time collaboration is actually authorized and flowing
> end-to-end — a second browser sees a stroke drawn in the first, and the backend logs
> the `joined room` line for that session.** Measured by §4.6, compared to the §2.4
> baseline. This is the property the change can silently break and every gate above it
> is a shape check by comparison.
>
> **Why the floor gates are not enough here, specifically.** Upstream's own README for
> v2.0.0 describes a *client-first* architecture: *"the websocket server is only needed
> for live collaboration — basic whiteboard functionality works without it"*, with
> changes saved to browser IndexedDB. So when `joinRoom()` rejects a socket, **the
> board still opens, still draws and still saves locally.** The pod is `Ready`, the
> HTTP gates are green, the user sees a working whiteboard — and collaboration is
> dead. That is the characteristic companion-service failure, and §4.6 is the only
> gate that can see it.

**4.1 Flux + rollout (floor).**

```bash
flux get kustomizations -n flux-system nextcloud          # READY True
kubectl get deploy -n office nextcloud-whiteboard -o jsonpath='{.status.readyReplicas}{"\n"}'   # 1
kubectl get pods -n office -l app=nextcloud-whiteboard    # 1/1 Running, 0 restarts after settle
```

**4.2 The new BYTES are running — digest, not tag.**

```bash
kubectl get pod -n office -l app=nextcloud-whiteboard \
  -o jsonpath='{.items[0].status.containerStatuses[0].imageID}{"\n"}'
```

PASS = `...whiteboard@sha256:059596633333d009890c64858f89f133ccd973a2e0823ad960a0cc05cf8657f1`
(the v2.0.0 index digest measured in §2.2). **What this catches:** the §2.4 baseline
digest `sha256:b60b763...` still showing here means the Pod never actually rolled —
which a green `kubectl rollout status` will happily report after a no-op.

**4.3 The backend reports its own version.**

```bash
kubectl logs -n office deploy/nextcloud-whiteboard --tail=40 | grep -iE 'whiteboard@'
```

PASS = a line containing `whiteboard@2.0.0`. **What this catches:** measured at
baseline, this same command printed `> whiteboard@1.5.9 server:start` — the npm
banner is emitted from the image's own `package.json` (`version` 2.0.0 upstream), so
it is independent of the tag we asked for and of the Deployment spec. A stale layer
or a re-pointed tag still prints 1.5.9 here. Grep is `-i` per house rule.

**4.4 The backend came up with OUR configuration, not defaults.**

```bash
kubectl logs -n office deploy/nextcloud-whiteboard --tail=40 \
  | grep -iE 'storage strategy|started successfully|FATAL|JWT_SECRET_KEY'
```

PASS = **both** `Server initialized with lru storage strategy` **and**
`Server started successfully on port 3002`, and **no** line matching `FATAL` /
`JWT_SECRET_KEY`. **What each catches:**
- the `lru` line proves v2.0.0 still honours `STORAGE_STRATEGY` (if it had dropped the
  strategy, `StorageService.create` would land elsewhere and this line would name a
  different adapter — the string is generated from the strategy actually selected, not
  from the env var we set);
- the absence of `FATAL` matters because `ConfigUtility.js:61-64` **throws on a
  missing `JWT_SECRET_KEY`** — that is the loud failure mode of a broken secret
  mount, and asserting its absence is what makes §4.6's silent failure the only
  remaining one.

**4.5 The service answers through the public edge, with real contents.**

```bash
curl -s "https://whiteboard.<domain>/socket.io/?EIO=4&transport=polling" | head -c 200; echo
```

PASS = a body starting `0{"sid":"…","upgrades":["websocket"]…}`. **What this catches:**
measured against the live v1.5.9 backend on 2026-09-17, this returns exactly that
shape with a real session id. A process that is listening but whose socket.io engine
failed to initialize returns a 404/empty body while the port is still open — and note
v2.0.0 changed `ServerService.start()` to await `socketService.ready` precisely in
this area, so this is the gate for that change. An HTTP 200 on `/` alone proves
nothing: the root path returned 200 on v1.5.9 too, measured.

**4.6 CONTENTS — a real collaborative round-trip (operator, browser).**

1. Open a whiteboard file in Nextcloud Files as a real user (browser A).
2. Open the **same** file as a second session (browser B, or a second profile/user).
3. Draw a stroke in A.

PASS requires **all three**:

- **B shows A's stroke** within a second or two, and the participant avatar for A
  appears. This is the property; everything else is corroboration.
- The backend log carries the join:

  ```bash
  kubectl logs -n office deploy/nextcloud-whiteboard --since=10m | grep -iE 'joined room'
  ```

  PASS = at least one `[<fileId>] <name> joined room` line. This string is emitted by
  `RoomLifecycleService.joinRoom()` **only after** the new `roomClaims.every(...)`
  authorization check passes (§1.2) — it is the direct, positive signal that the
  v2.0.0 gate accepted the app's token.
- **No rejection lines:**

  ```bash
  kubectl logs -n office deploy/nextcloud-whiteboard --since=10m | grep -iE '\[SECURITY\]|rejecting join|unauthorized room'
  ```

  PASS = **empty**. FAIL prints `[SECURITY] Socket <id> rejected from unauthorized
  room <id>` or `[<id>] Invalid socket data for socket <id>, rejecting join` — the
  exact output of the new gate refusing the app's JWT, and the fingerprint of an
  app/backend mismatch. **If this is non-empty, go to §5 — the pod is healthy and the
  feature is broken, which is the whole reason this section exists.**

Also check the browser devtools console for CSP violations on the wss:// origin —
v2.0.0 tightened the collaboration CSP (#1263) and validates the backend host
(`ConfigService::isValidCspHost`). Our `collabBackendUrl` host is a plain DNS name and
passes that validator, but a console error here would explain a failing round-trip.

**4.7 Clear the silence and the marker** once §4.1–§4.6 are green.

```bash
runbooks/update-marker.sh clear nextcloud-whiteboard
# delete the §2.5 silence by its id (GET /api/v2/silences to find it)
```

## 5) Rollback

### 5.1 Backend leg — a genuine one-line revert

This is the only thing this plan changed, and it is stateless: no PVC, no DB, no
migration, `/tmp` is an `emptyDir` discarded with the Pod.

```bash
cd /Users/mu/code/cberg-home-nextgen
git fetch origin main && git merge --ff-only origin/main
git revert --no-edit <sha-from-3.3>
git log -1 --format=%s        # confirm it is the revert of YOUR commit
git push origin main
kubectl rollout status -n office deploy/nextcloud-whiteboard --timeout=180s
```

**Confirm the cluster is actually back** — by digest, not by tag:

```bash
kubectl get pod -n office -l app=nextcloud-whiteboard \
  -o jsonpath='{.items[0].status.containerStatuses[0].imageID}{"\n"}'
#   expect: ...@sha256:b60b7633f90d106ac6922f9bc27e1a1ca2442488b740fefdae4c812f34e9cebc
kubectl logs -n office deploy/nextcloud-whiteboard --tail=40 | grep -iE 'whiteboard@'
#   expect: "> whiteboard@1.5.9 server:start"
```

Then re-run §4.5 and §4.6. The v1.5.9 tag was confirmed still present in GHCR at
§2.2 — **if that check was skipped and the tag has since been pulled, this revert has
no image to land on.**

### 5.2 Honest verdict: a git revert is sufficient for THIS plan, and may not be sufficient for the FEATURE

**For the change this plan makes, yes** — §5.1 fully restores the prior state, and
`rollback_class: git-revert` is accurate for it.

**For "the whiteboard feature is broken, put it back the way it was", not necessarily.**
If §2.3 reported `whiteboard = 2.0.0`, the Nextcloud app had already moved — delivered
by `nextcloud-34.0.4`, not by this commit. Reverting this image then leaves **app
2.0.0 / backend 1.5.9**, which is the §1.5 benign-direction skew rather than the
pre-change world. In practice that is the right place to stop and the correct triage
outcome: it is the configuration most installations run.

**Do not roll the app back reflexively.** Only if §4.6 still fails after §5.1 — i.e.
the app half is the fault — does §5.3 apply, and it is not a git operation.

### 5.3 App leg (only if §5.1 did not restore the feature) — NOT a git revert

The app lives in `custom_apps/whiteboard` on `pvc/nextcloud-config` and in the
Nextcloud DB. It is in **no git repository**, so nothing here can be reverted; this is
the `CLAUDE.md` "app config on a PVC with no GitOps path" class. **This is
`nextcloud-34.0.4`'s territory** (its `rollback_class` is already `backup-restore` and
it takes the Longhorn snapshot of `nextcloud-config` and the MariaDB dump that this
path depends on). Coordinate with that plan's executor; do not improvise.

The concrete path, for reference:

1. The pre-change artifacts are **that plan's** §2.4 `nextcloud-config` Longhorn
   snapshot and its MariaDB dump. **If they do not exist, stop** — there is no
   supported downgrade without them.
2. The appstore still serves the old release:
   `https://github.com/nextcloud-releases/whiteboard/releases/download/v1.5.9/whiteboard-v1.5.9.tar.gz`
   (from the appstore API for platform 34; note GitHub's own release pages carry **no**
   tarball assets for these tags — the appstore `download` URL is the artifact).
   Move the 2.0.0 directory aside and extract 1.5.9 in its place, then
   `occ app:update whiteboard` / `occ upgrade` as that plan's §5.1 describes.
3. **Forward-only user state to be aware of:** v2.0.0's `WhiteboardLibraryService`
   sets a per-user `legacy_libraries_migrated = 1` flag
   (`ConfigKeys::USER_LEGACY_LIBRARIES_MIGRATED`, written at
   `WhiteboardLibraryService.php:404`, read at `:345`) after migrating a user's
   legacy libraries. **1.5.9 does not know that key**, so a downgrade leaves it set;
   re-upgrading later will see the flag and skip the migration for those users. There
   is no app-side DB migration directory (`lib/Migration` does not exist in either
   version), so this user-config flag is the entire forward-only surface — small, but
   it is why this leg is not symmetric.

## 6) Interference notes

**Ordering is the substance of this plan, and it is encoded in `depends_on`, not here.**
`depends_on: [nextcloud-34.0.4]` because that plan delivers the app half (§1.4).

**What the window agent should do, concretely.** The ideal execution is **the same
sun-attended slot as `nextcloud-34.0.4`, run immediately after it** — the app and the
backend land within minutes of each other and no skew is ever user-visible. The
auto-scheduler **will not** produce that on its own: `window-scheduler.py:225` skips a
plan whose `depends_on` is not in the EXECUTED set, so this plan will sit unscheduled
until `nextcloud-34.0.4` is `executed`. That is a deliberate trade — the dependency is
real, and expressing it in prose would schedule nothing. **If the operator wants the
same-slot outcome, hand-assign `window: sun-attended:2026-09-20` and sequence this
after `nextcloud-34.0.4`.** If instead it lands a week later, that is acceptable: the
interim state is the §1.5 benign direction.

**`conflicts_with` — what is in it and what was considered and rejected.** Every other
plan's frontmatter was read (`maintenance-plan.py --open`, 2026-09-17: 9 executable,
2 programme, 16 reference).

- `bitnamilegacy-exit-nextcloud-db` — **declared.** It restarts `deployment/nextcloud`
  through a DB replatform; my §2.3 and §4.4/§4.6 gates read that server and would be
  unreadable beside it. `blocked`/`window: null` today, so this is a forward guard.
- `nextcloud-34.0.4` — **deliberately NOT a conflict.** It is a `depends_on`. Listing
  it here would forbid exactly the co-scheduling that produces the best outcome. Note
  that plan conflicts with `nextcloud-mcp-0.187.1` because its own silence is
  namespace-wide; **mine is scoped to `deployment=nextcloud-whiteboard`** (§2.5), so
  that reason does not propagate to this plan.
- `nextcloud-mcp-0.187.1` (`sat-attended:2026-10-03`) — **not declared.** It is an MCP
  bridge in the same namespace; it does not touch the whiteboard Deployment, Service or
  route, and my gates do not read it. Different slot in any case.
- `absenty-drop-npm-runtime` (same `sun-attended:2026-09-20` slot) — **not declared.**
  Different namespace, no shared object, no shared instrument.
- `external-dns-unowned-cnames` (`sat-attended:2026-10-03`) — **considered, rejected.**
  Its inventory does name `k8s.whiteboard`, but that is a legacy **pre-v0.12 ownership
  TXT record**, not the address record for `whiteboard.<domain>`. Deleting it does not
  change external reachability, so §4.5 is unaffected. Recorded here so the next reader
  does not have to re-derive it.
- Any `kube-prometheus-stack` bump — **not declared, and this is a measurement not an
  assumption.** §4 never reads Prometheus: there is no `ServiceMonitor` in ns `office`
  and this backend logs `Metrics disabled`. Every gate is a log, a digest, a curl or a
  browser.

**The one condition that would change `touches.shared`.** This plan declares
`shared: []` because it mutates nothing shared — the HTTPRoute and the
`envoy-external` Gateway are untouched and the Pod rolls behind them. But the service
**is** on the public edge, so **if a plan that perturbs `envoy-external` or the
Gateway's listeners is scheduled into the same slot, §4.5 stops being a valid
measurement** and `gateway/envoy` must be added here along with a conflict against
that plan. No such plan is currently windowed (the `envoy-gateway-phase*` set is
`reference`/unwindowed and runs attended outside the window system).

**Two policy corrections this investigation turned up** (reported, not silently
planned around):

1. **The deny rule that holds this component states a false reason.**
   `runbooks/auto-update-policy.yaml` matches `nextcloud-whiteboard` on the catch-all
   `*nextcloud*` rule, whose reason is *"chart+image must bump together and run occ
   migrations (Mail custom_app / stuck-maintenance trap) — operator-supervised only."*
   For this component that is **false in every clause**: it is a plain Kustomize
   Deployment with no chart, no Helm values, no `occ`, and no maintenance mode. The
   file itself documents this exact failure mode twice — the `*nextcloud-mcp*` and
   `*nextcloud-redis*` rules exist above the catch-all precisely because "a false
   reason is what makes an operator override a hold that turns out to be real". This
   component deserves the same treatment: its own rule, positioned above `*nextcloud*`,
   with its **real** reason — *the backend is version-coupled to a Nextcloud appstore
   app that `occ upgrade` moves independently of this repo, so the two halves must be
   sequenced by a human*. Note this changes only the reason text, not the outcome:
   `coverage.py` returns `PLAN` for `utype == "major"` regardless, so a major like this
   one would be held either way. The correction matters for the next *minor*.
2. **`nextcloud-34.0.4`'s appstore inventory is one day stale** — see the callout in
   §1.4. Its executor should expect `whiteboard updated` in its §3.2 log.

---
plan_id: icloud-backup-freshness-3.24.2
component: icloud-backup-freshness
pr: null                              # no Renovate PR — coverage.py direct-bump lane (needs_plan)
kind: image
current: "3.24.1"                     # docker.io/library/alpine:3.24.1@sha256:28bd5fe8… — live on
                                      # cronjob/icloud-backup-freshness, measured 2026-09-25
target: "3.24.2"                      # index digest sha256:294b683c… (Docker Hub, pushed 2026-09-18)
update_type: patch
risk: low                             # hold was a G3 false-positive: the release notes EXIST
                                      # (§1.2), and the measured package diff (§1.3) leaves
                                      # busybox and musl — the only things the probe executes —
                                      # byte-identical in version.
est_duration_min: 20                  # edit+commit+push ~3, Flux pickup ~2, one-off verify Job
                                      # ~1 (measured walk 16-30s), Prometheus scrape settle ~2,
                                      # slack for the pushgateway/Prometheus reads.
needs_reboot: false
touches:
  namespaces: [backup]
  resources:
    - cronjob/icloud-backup-freshness
    - pvc/icloud-backup-freshness     # mounted read-only; NOT modified
    - kustomization/icloud-backup-freshness
    - "docker.io/library/alpine"
  shared: [monitoring, cifs-share]    # monitoring: the probe PUSHES into
                                      # monitoring/prometheus-pushgateway (group
                                      # job=icloud-backup-freshness) and §4 reads Prometheus.
                                      # cifs-share: reads the cifs-immich-icloud-backup share
                                      # (subdir icloud-backup, ro) — read-only, no write path.
depends_on: []
conflicts_with:
  - kube-prometheus-stack-91.4.1      # §4 reads Prometheus; a same-night KPS bump restarts it and
                                      # an empty read would look like a probe regression.
  - talos-1.14.1                      # node reboots remount CIFS and restart pushgateway (in-memory,
                                      # no persistence) — both would make §4 fail for reasons
                                      # unrelated to this bump.
  - prometheus-pushgateway-3.9.0      # pushgateway is in-memory; its upgrade wipes the group §2.2/§4.3 compare against
  - flux-reconciler-impersonation     # rewrites how Flux applies namespace `backup`; if that
                                      # regresses, this plan's reconcile (§3.3) stalls and would
                                      # be misread as a bad image.
exclusive: false
security_ref: null
capability_change: false              # same script, same busybox; no behaviour change
rollback_class: git-revert            # stateless CronJob; nothing forward-only happens
finding_refs: [F-16ac7b93]
status: vetted   # 2026-09-26 plan-reviewer ready-for-go (0 blocking); 4 non-blocking corrections applied (pushgateway conflict, informational gates, one-line diff)
window: null
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/storage-safety.md       # read-only CIFS mount; no PVC delete in this plan
  - docs/sops/verification-contents-not-shape.md
generated: "2026-09-25"
premises:
  - id: cronjob-still-on-3.24.1
    why: "`current:` claims alpine 3.24.1 at the pinned digest. Any other value means the bump already happened or the file moved."
    run: kubectl get cronjob -n backup icloud-backup-freshness -o 'jsonpath={.spec.jobTemplate.spec.template.spec.containers[0].image}'
    expect_exact: "docker.io/library/alpine:3.24.1@sha256:28bd5fe8b56d1bd048e5babf5b10710ebe0bae67db86916198a6eec434943f8b"
  - id: flux-ks-ready
    why: "The Flux Kustomization that will apply the bump must be Ready, or §3.3 cannot tell a stalled reconcile from a bad image."
    run: kubectl get kustomization -n backup icloud-backup-freshness -o 'jsonpath={.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: "True"
  - id: probe-last-scheduled-run-succeeded
    why: "The pre-state must be a WORKING probe, else §4's success gate has no meaningful baseline. Prints the newest SCHEDULED Job row (verify-* Jobs excluded); its STATUS must be Complete. Jobs carry no app.kubernetes.io/name label, so this selects by name."
    run: kubectl get jobs -n backup --sort-by=.metadata.creationTimestamp --no-headers | grep -E '^icloud-backup-freshness-[0-9]+ ' | tail -1
    expect_matches: '^icloud-backup-freshness-[0-9]+ +Complete +1/1 '
---

# icloud-backup-freshness: alpine 3.24.1 → 3.24.2

## 1. Summary & why held

### 1.1 What changes
One line: the image of `cronjob/icloud-backup-freshness` (ns `backup`) moves from
`docker.io/library/alpine:3.24.1@sha256:28bd5fe8…` to
`docker.io/library/alpine:3.24.2@sha256:294b683c…`. This CronJob is the external
file-recency probe added for F-21d7e2ec: hourly at `:23` it walks
`/icloud-backup/{mu,andrea}/photos` on the read-only CIFS mount with busybox
`find`/`stat`, and pushes `icloud_backup_newest_file_timestamp_seconds{account}` plus
`icloud_backup_probe_last_success_timestamp_seconds` to `monitoring/prometheus-pushgateway`
via busybox `wget --post-file` (plain HTTP). It feeds every rule in
`kubernetes/apps/monitoring/kube-prometheus-stack/app/icloud-backup-alerts.yaml`.

### 1.2 Why it was held — and why the hold is a false positive
Coverage reason: *"G3 could not verify the release notes (unavailable)"*. The notes are
not unavailable; Alpine published this point release as a **combined multi-branch post**,
so a lookup for `Alpine-3.24.2-released.html` 404s. The real post is
`https://alpinelinux.org/posts/Alpine-3.21.8-3.22.6-3.23.6-3.24.2-released.html`
(dated 2026-09-17), whose entire body reads:

> "These releases fix all known high and medium severity OpenSSL vulnerabilities
> applicable to each release branch, along with other security and bug fixes."

No breaking change, no migration, no removed package. (The upstream post is public text
about the Alpine branch; no exposure assessment of our workload is made here.)

### 1.3 Measured package delta (amd64, `/lib/apk/db/installed` of both images, 2026-09-25)
Of 16 installed packages, exactly six change:

| package | 3.24.1 | 3.24.2 |
|---|---|---|
| alpine-release | 3.24.1-r0 | 3.24.2-r0 |
| apk-tools / libapk | 3.0.6-r0 | 3.0.8-r0 |
| ca-certificates-bundle | 20260611-r0 | 20260909-r0 |
| libcrypto3 / libssl3 | 3.5.7-r0 | 3.5.8-r0 |

**`busybox` / `busybox-binsh` stay at `1.37.0-r31`, and `musl` is unchanged.** The probe
runs only `/bin/sh` + busybox applets (`find`, `stat -c %Y`, `sort`, `head`, `date`,
`wget --post-file` over `http://`), so none of the changed packages is on its execution
path — the manifest's own note that "the busybox v1.37.0 feature checks stay true" still
holds for the new digest. Verdict: genuinely trivial; `risk: low`.

## 2. Pre-checks

Run the frontmatter premises (`runbooks/plan-premises.py icloud-backup-freshness-3.24.2`);
all three must PASS. Then, from the repo root:

2.1 **Target digest still resolves and is unchanged** (guards a retagged/removed tag):
```bash
TOK=$(curl -s "https://auth.docker.io/token?service=registry.docker.io&scope=repository:library/alpine:pull" | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
curl -sI -H "Authorization: Bearer $TOK" \
  -H 'Accept: application/vnd.oci.image.index.v1+json,application/vnd.docker.distribution.manifest.list.v2+json' \
  https://registry-1.docker.io/v2/library/alpine/manifests/3.24.2 | grep -i docker-content-digest
```
PASS: `sha256:294b683cb724975bec92580e1e685676bd4b50bda910ddb8c51d4cabeaec77e6`.
FAIL (prints a different digest or nothing): STOP — upstream re-published; re-plan.

2.2 **Record the baseline** (the §4 contents assertion compares against these):
```bash
kubectl port-forward -n monitoring svc/prometheus-pushgateway 19091:9091 >/dev/null 2>&1 & PF=$!; sleep 2
curl -s http://localhost:19091/metrics | grep -E '^icloud_backup_(newest_file|probe_last_success)_timestamp_seconds' | tee /tmp/icbf-baseline.txt
kill $PF 2>/dev/null
```
PASS: exactly three lines — `account="mu"`, `account="andrea"`, and `probe_last_success`.
Pushgateway prints them with extra labels and in exponent form, e.g.
`icloud_backup_newest_file_timestamp_seconds{account="mu",instance="",job="icloud-backup-freshness"} 1.788466359e+09`
(authoring measurement 2026-09-25: mu=1788466359, andrea=1788702851). The §4.3 parser
was dry-run against exactly this live output.

Note: `ICloudBackupPhotosStale` / `...StaleCritical` were FIRING at authoring time for both
accounts (the icloud-docker sync outage, a separate issue). That is expected pre-state and
is NOT a gate in this plan — do not treat it as a reason to abort, and do not expect this
bump to clear it.

## 3. Steps

3.1 Edit the pin (dry-tested on a scratch copy with macOS BSD sed, 2026-09-25):
```bash
cd /Users/mu/code/cberg-home-nextgen
sed -i '' 's#docker.io/library/alpine:3.24.1@sha256:28bd5fe8b56d1bd048e5babf5b10710ebe0bae67db86916198a6eec434943f8b#docker.io/library/alpine:3.24.2@sha256:294b683cb724975bec92580e1e685676bd4b50bda910ddb8c51d4cabeaec77e6#' \
  kubernetes/apps/backup/icloud-backup-freshness/app/cronjob.yaml
git diff kubernetes/apps/backup/icloud-backup-freshness/app/cronjob.yaml
```
Expected diff (exactly one line, line 98):
```
<               image: docker.io/library/alpine:3.24.1@sha256:28bd5fe8b56d1bd048e5babf5b10710ebe0bae67db86916198a6eec434943f8b
>               image: docker.io/library/alpine:3.24.2@sha256:294b683cb724975bec92580e1e685676bd4b50bda910ddb8c51d4cabeaec77e6
```
Do NOT edit the comment above it: the expected diff is exactly one line, and 3.2's git show --stat check keys on that.

3.2 Commit (shared worktree — `--only`, then verify ownership):
```bash
git commit --only kubernetes/apps/backup/icloud-backup-freshness/app/cronjob.yaml \
  -m "chore(icloud-backup-freshness): alpine 3.24.1 -> 3.24.2 (plan icloud-backup-freshness-3.24.2)"
git log -1 --format=%s     # must be the subject above
git show --stat HEAD       # must list ONLY cronjob.yaml
git push
```

3.3 Wait for Flux (webhook; no manual reconcile needed) and confirm the applied spec:
```bash
kubectl get kustomization -n backup icloud-backup-freshness -o 'jsonpath={.status.lastAppliedRevision}{"\n"}'
kubectl get cronjob -n backup icloud-backup-freshness -o 'jsonpath={.spec.jobTemplate.spec.template.spec.containers[0].image}{"\n"}'
```
PASS: revision = the pushed SHA and the image string ends in `@sha256:294b683c…77e6`.
If Flux has not picked it up after 5 min, `flux reconcile kustomization icloud-backup-freshness -n backup --with-source` (application-update SOP permits it when the webhook lags).

3.4 Run ONE out-of-schedule probe from the updated CronJob (so the window does not wait up
to 60 min for `:23`; same pattern as `docs/sops/backup.md`). The Job inherits
`ttlSecondsAfterFinished: 86400`, so it self-deletes; its name matches the existing
`ICloudBackupFreshnessProbeJobFailed` regex, so a failure also alerts.
```bash
T0=$(date -u +%s); echo "T0=$T0"
J=icloud-backup-freshness-verify-$T0
kubectl -n backup create job --from=cronjob/icloud-backup-freshness $J
kubectl -n backup wait --for=condition=complete job/$J --timeout=300s
kubectl -n backup logs job/$J
```

## 4. Verification

4.1 **The Job ran the NEW image** (guards: the Job being created from a stale spec):
```bash
kubectl -n backup get pods -l job-name=$J -o 'jsonpath={.items[0].status.containerStatuses[0].imageID}{"\n"}'
```
PASS: contains `294b683cb724975bec92580e1e685676bd4b50bda910ddb8c51d4cabeaec77e6`.
FAIL: prints the `28bd5fe8…` digest (spec not yet applied — redo 3.3/3.4).

4.2 **The Job succeeded and its script reached the push.** `kubectl wait` in 3.4 exits
non-zero after 300s if the Job never completes; additionally the log must contain, case-
insensitively, both account lines and the push line:
```bash
kubectl -n backup logs job/$J | grep -ciE '^account=(mu|andrea) dir=.* newest_mtime=[0-9]+ '   # PASS: 2
kubectl -n backup logs job/$J | grep -ciE '^pushed to pushgateway job=icloud-backup-freshness' # PASS: 1
kubectl -n backup logs job/$J | grep -ciE 'fatal|bad request|not found' || true               # INFORMATIONAL only (absence, never shown non-zero); the two positive counts above are the gate
```
What the guarded failure prints: a busybox regression in `stat`/`find` lands in the
script's `FATAL: could not determine a numeric newest mtime` branch and exits 1 (count 2 → <2,
FATAL count ≥1); a `wget` regression prints `wget: server returned error: HTTP/1.1 400`
and `set -e` exits before the `pushed to` line. The exit code alone is not the gate.

4.3 **CONTENTS ASSERTION: the pushgateway holds a fresh, correct gauge for BOTH accounts** —
measured directly from the pushgateway (the store the alerts read), compared to the §2.2
baseline:
```bash
kubectl port-forward -n monitoring svc/prometheus-pushgateway 19091:9091 >/dev/null 2>&1 & PF=$!; sleep 2
curl -s http://localhost:19091/metrics | grep -E '^icloud_backup_(newest_file|probe_last_success)_timestamp_seconds' | tee /tmp/icbf-after.txt
kill $PF 2>/dev/null
python3 - "$T0" <<'EOF'
import re, sys
t0 = int(sys.argv[1])
def load(p):
    d = {}
    for l in open(p):
        m = re.match(r'^(icloud_backup_[a-z_]+)\{([^}]*)\} (\S+)$', l.strip())
        if not m: continue
        acc = re.search(r'account="(\w+)"', m.group(2))
        d[(m.group(1), acc.group(1) if acc else None)] = float(m.group(3))
    return d
b, a = load('/tmp/icbf-baseline.txt'), load('/tmp/icbf-after.txt')
ok = len(b) == 3 and len(a) == 3   # parser sanity: 0 parsed lines must FAIL, not pass vacuously
if not ok: print('FAIL parsed', len(b), 'baseline /', len(a), 'after lines (expected 3/3)')
for acc in ('mu', 'andrea'):
    k = ('icloud_backup_newest_file_timestamp_seconds', acc)
    if k not in a: print('FAIL missing', acc); ok = False; continue
    if a[k] < b.get(k, 0): print('FAIL', acc, 'went BACKWARDS', b.get(k), '->', a[k]); ok = False
    else: print('ok', acc, b.get(k), '->', a[k])
s = a.get(('icloud_backup_probe_last_success_timestamp_seconds', None), 0)
if s < t0: print('FAIL last_success', s, '< T0', t0); ok = False
else: print('ok last_success', s, '>= T0', t0)
print('PASS' if ok else 'FAIL')
EOF
```
PASS: prints `PASS` — both account gauges present and not older than baseline, and
`probe_last_success >= T0` (i.e. THIS Job's push landed). It can fail: before 3.4 runs,
`probe_last_success` is from the last `:23` run and is `< T0` (authoring measurement: the
value was ~1830 s old), so the same script prints `FAIL last_success … < T0`. A partial
or empty walk under the new busybox would either drop an account (FAIL missing) or
produce an older newest-mtime (FAIL went BACKWARDS).

4.4 **Prometheus sees the fresh push** (after one scrape, ~2 min):
```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 19090:9090 >/dev/null 2>&1 & PF=$!; sleep 3
curl -s -G http://localhost:19090/api/v1/query --data-urlencode 'query=time() - icloud_backup_probe_last_success_timestamp_seconds' \
  | python3 -c "import sys,json;r=json.load(sys.stdin)['data']['result'];print(r[0]['value'][1] if r else 'EMPTY')"
curl -s -G http://localhost:19090/api/v1/query --data-urlencode 'query=count(icloud_backup_newest_file_timestamp_seconds)' \
  | python3 -c "import sys,json;r=json.load(sys.stdin)['data']['result'];print(r[0]['value'][1] if r else 'EMPTY')"
curl -s -G http://localhost:19090/api/v1/query --data-urlencode 'query=ALERTS{alertname=~"ICloudBackupFreshness.*",alertstate="firing"}' \
  | python3 -c "import sys,json;print(len(json.load(sys.stdin)['data']['result']))"
kill $PF 2>/dev/null
```
PASS: first value < 600 (seconds since the verify push; `EMPTY` = FAIL; reads ~2345 at rest, so it can fail), second = `2`.
The third (firing ICloudBackupFreshness* count) is INFORMATIONAL: every rule has for: >= 5m, so it reads 0 on a failed push too; re-read it at 4.5.

CONTROL: metric icloud_backup_probe_last_success_timestamp_seconds — age must drop below 600 s after the verify Job (it is ~1-60 min old at rest).
CONTROL: metric icloud_backup_newest_file_timestamp_seconds — exactly 2 series (mu, andrea), each ≥ its §2.2 baseline.
CONTROL: alertname ICloudBackupFreshnessProbeJobFailed — not firing.
CONTROL: alertname ICloudBackupFreshnessProbeStale — not firing.
CONTROL: alertname ICloudBackupFreshnessMetricMissing — not firing.
CONTROL: alertname ICloudBackupFreshnessMetricMissingAndrea — not firing.

`ICloudBackupPhotosStale*` are deliberately NOT gates: they reflect icloud-docker sync
state, which this plan does not touch and which was firing before it.

4.5 **Next scheduled run** (non-blocking follow-up, checked by the next sweep): the first
`:23` Job after the window is `Complete` with the new imageID.

## 5. Rollback

Stateless CronJob; nothing forward-only happens (the probe mounts the share `ro` and only
pushes gauges, which the next successful run overwrites).

```bash
cd /Users/mu/code/cberg-home-nextgen
git revert --no-edit <sha-from-3.2>
git log -1 --format=%s && git show --stat HEAD   # only cronjob.yaml
git push
```
Confirm back: re-run the premise `cronjob-still-on-3.24.1` (must PASS again), then repeat
3.4 + 4.3 with a fresh `T0` — PASS means the probe pushes again on 3.24.1. Leave any failed
`icloud-backup-freshness-verify-*` Job in place for inspection; it self-deletes after 24 h
(no manual delete needed; it holds no volume other than the shared ro PVC mount).

## 6. Interference notes

- **No PVC operation.** `pvc/icloud-backup-freshness` (class `cifs-immich-icloud-backup`,
  subdir `icloud-backup`, Retain, `ro`) is only mounted by the Job. Nothing here deletes or
  recreates it — the storage-safety pre-flight is not triggered.
- **pushgateway grouping is replaced wholesale** on each push. The script assembles the
  full body before sending, so a failed run pushes nothing (the gauges keep ageing). This
  is why §4.3 can use `probe_last_success >= T0` as the proof of a successful new-image push.
- **Concurrency:** the CronJob is `concurrencyPolicy: Forbid`, but a manually created Job
  is not governed by it. Avoid running 3.4 between `:22` and `:24` so the verify Job and
  the scheduled Job do not walk the share at the same time (harmless, but it muddles 4.1).
- **conflicts_with:** `kube-prometheus-stack-91.4.1` (§4.4 reads Prometheus),
  `talos-1.14.1` (reboots remount CIFS and wipe the in-memory pushgateway, which would read
  as `METRIC MISSING`), `flux-reconciler-impersonation` (changes Flux apply for ns `backup`).
- **Repo correction (for the report, not planned around):** coverage G3 resolves Alpine
  release notes as unavailable because the upstream post for a point release is often
  named for several branches at once (`Alpine-3.21.8-3.22.6-3.23.6-3.24.2-released.html`).
  Every future `library/alpine` patch will be held the same way until the notes lookup
  learns that shape (or reads `alpinelinux.org/atom.xml` titles).
- **Other alpine pins:** `kubernetes/apps/storage/longhorn/bench/loopback-daemonset.yaml`
  already uses `alpine:3.24.2` (tag, no digest) — unrelated to this plan.

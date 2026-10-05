---
plan_id: cli-tool-pins
component: mac-toolchain              # the Mac-mini-local CLI pins in /.mise.toml (repo tooling, NOT a
                                      # cluster workload). Every sweep, the ops console and every window
                                      # agent run these binaries via mise.
pr: null                              # Renovate does not read .mise.toml in this repo (see the flate
                                      # comment in the file); the drift came from the 2026-10-05 version check.
kind: config                          # same kind the plan set uses for non-workload repo changes
                                      # (float-tag-pinning, helm-drift-detection)
current: "flux 2.9.0, sops 3.13.0, age 1.3.1, task 3.46.4, kustomize 5.6.0, yq 4.50.1, jq 1.7.1, cloudflared 2026.9.1, trivy 0.70.0"
target: "flux 2.9.3, sops 3.13.3, age 1.3.2, task 3.54.0, kustomize 5.8.2, yq 4.54.1, jq 1.8.2, cloudflared 2026.9.3, trivy 0.75.0"
update_type: minor                    # patch/minor only; the three majors are listed out of scope in §1
risk: low                             # local binaries, instant revert (old versions stay installed); the one
                                      # real hazard (a sweep scanner that silently reports zero) is gated in
                                      # §4.3 by a full-fleet same-DB parity diff with a negative control
est_duration_min: 60                  # pre-checks 3 + baselines 18 (fleet scan 0.70 ~12, test suite 2.5,
                                      # health-check 2, render hashes 1) + steps 6 + verification 23 (fleet
                                      # scan 0.75 ~12, suite 2.5, health-check 2, per-tool 5) + slack 10
needs_reboot: false
touches:
  namespaces: []                      # nothing in the cluster changes; every cluster call in §2-§4 is a read
  resources:
    - .mise.toml                                       # 9 pin lines
    - "~/.local/share/mise/installs/<tool>/<target>"   # new binaries installed ALONGSIDE the old ones
    - "$TMPDIR/cberg-trivy-cve-cache-v4.json"          # moved aside (4.8) so the next sweep rescans on 0.75
  shared: [sweep-toolchain]           # the binaries every sweep, the ops console, the window agent's
                                      # Step 0 and every other plan's §2-§5 commands resolve through mise
depends_on: []                        # flux CLI targets the LIVE distribution (2.9.3), so no dependency on
                                      # flux-distribution-2.9.6; see §1 "flux CLI target"
conflicts_with:
  - flux-distribution-2.9.6           # changes the distribution the flux CLI pin tracks; its gates use the
                                      # flux CLI. Run either first, never both in one slot (premise
                                      # flux-distribution-still-2.9.3 catches the order).
  - flux-fleet-0.60.0                 # flux-operator chart roll; its §4 uses `flux` + `kubectl` reads
  - k8s-1.36.5                        # drives `task talos:*` (task + yq in .taskfiles/talos) mid-plan
  - talos-linux-1.14.2                # same: task/yq/talhelper chain mid-plan
  - kube-prometheus-stack-91.9.0      # 4.9 CONTROL reads Prometheus (the window's instrument)
exclusive: true                       # swaps the toolchain under ANY other plan's running commands
                                      # (task, yq, jq, flux, sops are in most §2-§5 blocks), including plans
                                      # not written yet: nothing else may be in flight
security_ref: null
capability_change: false              # same tools, same invocations, same outputs (proven equal in §4);
                                      # no new route, permission, API or exposure
rollback_class: git-revert            # git revert + `mise install`; old versions are never pruned here
autonomy_override: human-gated        # must run on the Mac OUTSIDE a sweep (04:00 Europe/Berlin every 48h)
                                      # and outside the 03:30 nightly window, whose own Step 0 runs these
                                      # binaries; a 60-min run in that slot would overlap the sweep start
finding_refs: []                      # no sweep finding exists for the local pins (policy-cli `finding list
                                      # --grep` for trivy/flux2/jq/yq/go-task/tool pin: no rows, 2026-10-05)
premises:
  - id: pins-still-current
    why: "Step 3.2 anchors on these nine exact lines. Fewer than 9 means someone moved a pin and the target list must be re-derived."
    run: >-
      grep -cxF -e '"aqua:fluxcd/flux2" = "2.9.0"' -e '"aqua:getsops/sops" = "3.13.0"' -e '"aqua:FiloSottile/age" = "1.3.1"' -e '"aqua:go-task/task" = "3.46.4"' -e '"aqua:kubernetes-sigs/kustomize" = "5.6.0"' -e '"aqua:mikefarah/yq" = "4.50.1"' -e '"aqua:jqlang/jq" = "1.7.1"' -e '"aqua:cloudflare/cloudflared" = "2026.9.1"' -e '"aqua:aquasecurity/trivy" = "0.70.0"' .mise.toml
    expect_exact: "9"
  - id: flux-distribution-still-2.9.3
    why: >-
      The flux CLI target (2.9.3) is chosen to EQUAL the live distribution. If
      flux-distribution-2.9.6 executed first, this fails: STOP and re-plan (refresh
      this plan's flux target via the planner + review). No in-window retarget.
    run: kubectl get fluxinstance -n flux-system flux -o jsonpath='{.status.lastAppliedRevision}'
    expect_matches: '^v2\.9\.3@sha256:'
  - id: out-of-scope-pins-untouched
    why: "The majors (helm 3.22.0, helmfile 0.171.0, gum 0.17.0) must still be on their current lines; if someone migrated one, §1's scope list is stale."
    run: >-
      grep -cxF -e '"aqua:helm/helm" = "3.22.0"' -e '"aqua:helmfile/helmfile" = "0.171.0"' -e '"aqua:charmbracelet/gum" = "0.17.0"' .mise.toml
    expect_exact: "3"
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/vulnerability-disclosure.md
  - docs/sops/audit-script-correctness.md
review: ready-for-go@2026-10-05   # plan-reviewer 2026-10-05: needs-fix (sole blocker §4.2 busybox Results-key control) -> fixed per the reviewer's exact correction (rc==0 + version + tally None), dry-tested on 0.70
status: vetted
window: null   # 2026-10-05 schedule: operator NOW run (daytime, attended, exclusive) on 2026-10-08, BEFORE flux-distribution-2.9.6 (its premise flux-distribution-still-2.9.3); stamp via run-now.py at run time
generated: "2026-10-05"
---

# cli-tool-pins: Mac-local toolchain catch-up (flux, sops, age, task, kustomize, yq, jq, cloudflared, trivy)

## 1. Summary & why held

`/.mise.toml` pins the binaries the Mac mini runs for every sweep, the ops console
and every maintenance window. Renovate does not read the file, so drift shows up
only in the version check. The 2026-10-05 check found nine pins behind. All nine
targets were verified to exist with `mise ls-remote` (each returned exactly one
match on 2026-10-05).

| tool | current | target | notes read (upstream release / CHANGELOG) |
|---|---|---|---|
| flux CLI | 2.9.0 | **2.9.3** | Same patch line as the live distribution. v2.9.1 notes: "Fix a breaking change in the in-memory Kustomization build (Flux CLI)", a fix we want for `flux build`/`flux diff`. |
| sops | 3.13.0 | 3.13.3 | Patch fixes only (INI double-encoding, completion scripts). Store format unchanged. |
| age | 1.3.1 | 1.3.2 | Patch. |
| task | 3.46.4 | 3.54.0 | Remote Taskfiles reached GA in 3.53 (opt-in by URL; ours are local `includes:`). 3.47 adds an interactive prompt for missing `requires:` vars, which does not trigger without a TTY. Neither `sources:`/`generates:` nor `method:` is used in our Taskfiles, so the 3.52/3.53 checksum changes do not apply. |
| kustomize | 5.6.0 | 5.8.2 | 5.8.2: "the output of `kustomize build` is not expected to change". 5.8.1 handles Helm v4 (we do not use `helmCharts:` locally). |
| yq | 4.50.1 | 4.54.1 | 4.53.4: an unrecognised file extension defaults to YAML. 4.53.2 adds `system()`, disabled by default. Our only uses are `yq '.talosVersion'` / `'.nodes[]...'` on `talconfig.yaml`. |
| jq | 1.7.1 | 1.8.2 | **jq says 1.8 "may introduce breaking changes"**: `ltrimstr/rtrimstr` error on non-strings, `limit/2` errors on negative counts, `indices` returns codepoint indices, `pow10`/`_nwise` are removed, `--indent 0` no longer implies compact output, and binding-syntax changes. I grepped every repo jq call site (`runbooks/health-check.sh` has 54, plus `check-versions.sh`, `plan-premises.py` and the tools/scripts) for those functions/flags: **none used**. I also ran `health-check.sh` end to end with jq 1.8.2 shadowing PATH before writing this plan (§4.5). |
| cloudflared | 2026.9.1 | 2026.9.3 | Patch. The tunnel itself runs in-cluster from its own image; the local CLI is ad-hoc only. |
| **trivy** | 0.70.0 | **0.75.0** | **PRIORITY. The sweep's running-image CVE scanner.** See below. |

**Why trivy needed an investigation and not a blind bump.** `runbooks/security-check.py`
(`_scan_one`) runs
`trivy image --severity CRITICAL,HIGH --exit-code 0 --quiet --format json --timeout {30s|90s} <img>`.
`tally_trivy_report()` then reads `ArtifactName`, `Results[].Class`, and
`Results[].Vulnerabilities[].{Severity, FixedVersion, VulnerabilityID, PkgName, InstalledVersion, Relationship, PublishedDate}`.
A renamed flag or field, a changed default scanner set, or a changed DB schema
would not crash anything. The scan would return `Results` with no
`Vulnerabilities`, `tally_trivy_report()` would return `None`, and the image
would read **clean**. The orchestrator would then auto-close its open CVE findings.
That is the hazard this plan guards against.

What I checked against upstream (tags v0.70.0..v0.75.0, CHANGELOG and source):
- **BREAKING entries:**
  - 0.75 removes `getHostByName` from report templates. We use `--format json`, not templates.
  - 0.72 is `ci!: migrate docker config to dockers_v2`, which affects only trivy's own per-arch container image tags. We install the release binary through aqua.
  - 0.75's crypto scanner is "experimental and **off by default**, enabled with `--scanners crypto`" (PR #11144).
- **Flags:** `-s/--severity`, `--exit-code`, `-q/--quiet`, `-f/--format`,
  `--timeout`, `--skip-db-update`, `--cache-dir` are identical in
  `docs/.../cli/trivy_image.md` at both tags. The `--scanners` default is still
  `[vuln, secret]` (`pkg/flag/scan_flags.go` @v0.75.0). PR #11281 ("typos in CLI
  flags") rewords usage strings only.
- **JSON contract:** `pkg/types/vulnerability.go` has the same
  `VulnerabilityID/PkgName/InstalledVersion/FixedVersion/Status` fields at both
  tags. `Relationship` and the `Report` fields are unchanged.
- **DB:** the default `--db-repository` is still `.../trivy-db:2` (schema v2) and
  the java-db is still `:1`. `go.mod` moves only the trivy-db library revision.
- **Detection deltas we should EXPECT:**
  - 0.72 `fix(vuln): fall back to UNKNOWN severity when vulnerability details are missing` (#10795). Those rows were previously empty-severity and fell outside `--severity CRITICAL,HIGH` either way.
  - 0.73 `fix(vuln): don't skip packages covered by a driver's own advisory feed` (#10980). This affects only the Seal/Echo drivers.
  - 0.75 adds Echo-patched Python detection.
  - Any of these may ADD findings. None should REMOVE one.
- **Measured, not just read (2026-10-05):**
  - I ran the sweep's exact command with 0.70.0 and a scratch copy of 0.75.0 (`shasum` matched the release checksums) over 19 images: 12 running images, one public known-vulnerable positive control (`alpine:3.10.0`, not something we run), and 6 more running images including java (elasticsearch), node, python and go-distroless.
  - Both versions used **the same DB snapshot** (shared isolated `--cache-dir`, `--skip-db-update` on the second run).
  - Through the sweep's OWN `tally_trivy_report()`, the per-image tallies and the full CVE-ID sets were **identical on all 19**. The result classes were identical. Scan times on a warm cache matched (2 s vs 2 s on the largest image).
  - The same harness with one image's IDs blanked printed `VERDICT: FAIL`, so the gate in §4.3 can fail.
  - No counts or IDs are recorded here or anywhere in the repo, per `docs/sops/vulnerability-disclosure.md`.

**flux CLI target: 2.9.3 now, not 2.9.6 later.**
- The CLI should equal the live distribution. Today that is `v2.9.3` (FluxInstance `lastAppliedRevision`).
- `flux-distribution-2.9.6` is `draft` and itself `depends_on: [flux-fleet-0.60.0]`, which is also draft. Gating this plan behind two un-reviewed medium-risk control-plane plans would hold the priority trivy fix hostage to them.
- A 2.9.x CLI is compatible across the 2.9 patch line (same CRD API versions).
- The CLI move to 2.9.6 is a one-line follow-up that belongs in flux-distribution-2.9.6's retire step (reported to the coordinator as a cross-plan note).
- If that plan lands first, premise `flux-distribution-still-2.9.3` fails and the executor STOPS; this plan is re-planned (no in-window retarget).
- The later CLI catch-up 2.9.3 -> 2.9.6 is OWNED by flux-distribution-2.9.6's retire step (the coordinator is adding it there); this plan does not do it.

**Why held:** nothing auto-applies `.mise.toml`, and the version check cannot tell
a sweep-critical scanner from a convenience CLI. The changes are low-risk, but
trivy and jq feed sweep verdicts, so each bump needs a gate that can fail. That is
§4.

**OUT OF SCOPE (majors are migrations, not bumps; NOT planned here):**
- `helm` 3.22.0 -> 4.x (v4.3.0 is current; 3.22.0 is the newest 3.x, so it is current on its line).
- `helmfile` 0.171.0 -> 1.x (v1.8.1).
- `gum` 0.17.0 -> 2.x (v2.0.2).

All three are used only by the cluster re-bootstrap path (`.taskfiles/bootstrap`
-> `helmfile apply`; `kubernetes/bootstrap/apps/resources/prepare.sh` -> `gum log`).
A migration plan for them must be tested against that DR path, not against a sweep.

Also untouched:
- `kubectl` 1.36.0, which follows `k8s-1.36.5`.
- `talosctl` 1.14.1, which tracks `talconfig.yaml`, per the comment in the file.
- `kubeconform` 0.8.0, already the latest.
- `flate` 0.6.5, kept in lockstep with CI.
- `unifictl`, `zigbeectl`, `talhelper`, `python`, `uv`.

## 2. Pre-checks

All scratch lives in the FIXED dir `/private/tmp/claude-501/cli-tool-pins` (never the repo),
re-set at the top of every block, because the executor's shell state (vars, cwd) does not
persist between Bash calls. Run as the normal user `mu` and **never as root** (`whoami` must print `mu`).
Root-owned files in mise installs or `.git` break every other session (see
CLAUDE.md, 2026-09-25/26 incident).

```bash
S=/private/tmp/claude-501/cli-tool-pins; mkdir -p "$S"; cd /Users/mu/code/cberg-home-nextgen   # re-set in EVERY block: shell state does not persist between agent Bash calls
cd /Users/mu/code/cberg-home-nextgen
whoami                                                    # mu — anything else: STOP
.venv/bin/python3 runbooks/plan-premises.py cli-tool-pins # all PASS, or STOP
# No sweep / window / retro in flight, and none due within 75 min:
ps -axo pid,command | grep -E 'sweep-run\.py|security-check\.py|health-check\.sh|maintenance-window' | grep -v grep   # must print nothing
date '+%a %H:%M %Z'       # not within 03:15-06:00 (nightly window + 48h sweep) nor Mon 07:15-08:30 (retro)
git status --short .mise.toml                             # must be empty (no foreign edit in flight)
mise ls --current | grep -E 'flux2|sops|age|task|kustomize|yq|jq|cloudflared|trivy' | tee "$S/versions-pre.txt"
```

**Baselines (all on the CURRENT pins).** These are the "before" side of every §4 gate.

```bash
S=/private/tmp/claude-501/cli-tool-pins; mkdir -p "$S"; cd /Users/mu/code/cberg-home-nextgen   # re-set in EVERY block: shell state does not persist between agent Bash calls
# B1 — trivy fleet baseline: the sweep's command + parser over every running image,
#      on a freshly UPDATED DB (the post run reuses this exact DB with --skip-db-update).
cat > "$S/fleet_scan.py" <<'EOF'
# usage: fleet_scan.py <trivy-binary> <image-list-file> <out.json> [extra trivy args...]
import sys, os, json, subprocess, importlib.util
from concurrent.futures import ThreadPoolExecutor
os.environ.setdefault("_MISE_ACTIVATED", "1")
spec = importlib.util.spec_from_file_location("sc", "runbooks/security-check.py")
sc = importlib.util.module_from_spec(spec); spec.loader.exec_module(sc)
binary, listfile, out = sys.argv[1:4]; extra = sys.argv[4:]
imgs = [l.strip() for l in open(listfile) if l.strip()]
def one(img):
    cmd = [binary, "image", *extra, "--severity", "CRITICAL,HIGH", "--exit-code", "0",
           "--quiet", "--format", "json", "--timeout", "90s", img]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if p.returncode != 0 or not p.stdout: return img, {"ok": False}
        rep = json.loads(p.stdout)
    except Exception:
        return img, {"ok": False}
    t = sc.tally_trivy_report(rep) or {}
    ids = sorted(set(t.get("fix_ids", []) + t.get("nofix_ids", []) + t.get("undet_ids", [])))
    return img, {"ok": True, "ver": (rep.get("Trivy") or {}).get("Version"), "ids": ids,
                 "tally": {k: t.get(k, 0) for k in ("crit_fix","crit_nofix","high_fix","high_nofix","crit_undet","high_undet")}}
with ThreadPoolExecutor(max_workers=6) as ex:
    res = dict(ex.map(one, imgs))
for img in [i for i, v in res.items() if not v["ok"]]:   # serial retry, as security-check._scan_batch does
    res[img] = one(img)[1]
json.dump(res, open(out, "w"))
ok = [v for v in res.values() if v["ok"]]
print(f"images={len(imgs)} ok={len(ok)} failed={len(imgs)-len(ok)} with_findings={sum(1 for v in ok if v['ids'])} "
      f"versions={sorted({v.get('ver') for v in ok})}")
EOF
cat > "$S/fleet_diff.py" <<'EOF'
# usage: fleet_diff.py <pre.json> <post.json>   (aggregate numbers only — never print IDs)
import sys, json
a, b = (json.load(open(p)) for p in sys.argv[1:3])
both = [i for i in a if a[i]["ok"] and b.get(i, {}).get("ok")]
lost_ok   = [i for i in a if a[i]["ok"] and not b.get(i, {}).get("ok")]
vanished  = [i for i in both if set(a[i]["ids"]) - set(b[i]["ids"])]
added     = [i for i in both if set(b[i]["ids"]) - set(a[i]["ids"])]
went_zero = [i for i in both if a[i]["ids"] and not b[i]["ids"]]
print(f"compared={len(both)} pre_ok={sum(v['ok'] for v in a.values())} post_ok={sum(v['ok'] for v in b.values())} "
      f"lost_ok={len(lost_ok)} images_with_vanished_ids={len(vanished)} images_with_added_ids={len(added)} went_zero={len(went_zero)}")
print("VERDICT:", "PASS" if not lost_ok and not vanished and not went_zero and both else "FAIL")
EOF
kubectl get pods -A -o jsonpath='{range .items[*].spec.containers[*]}{.image}{"\n"}{end}{range .items[*].spec.initContainers[*]}{.image}{"\n"}{end}' \
  | sed -e 's#^index\.docker\.io/library/##' -e 's#^docker\.io/library/##' -e 's#^index\.docker\.io/##' -e 's#^docker\.io/##' \
  | grep -v 'bitnami/' | sort -u > "$S/imgs.txt"; wc -l < "$S/imgs.txt"     # ~185 on 2026-10-05; 0 = STOP
export TRIVY_USERNAME=nachtschatt3n TRIVY_PASSWORD="$(gh auth token)"       # as sweep-run.py does; env only, never argv
mise exec -- trivy image --download-db-only --quiet && mise exec -- trivy image --download-java-db-only --quiet
_MISE_ACTIVATED=1 mise exec -- python3 "$S/fleet_scan.py" "$(mise which trivy)" "$S/imgs.txt" "$S/pre.json" --skip-db-update --skip-java-db-update
#   expect: versions=['0.70.0'], failed small (private/unpullable only). ~10-12 min.

# B2 — audit regression suite (191 suites, 139 s measured 2026-10-05)
bash runbooks/tests/run-all.sh > "$S/runall-pre.txt" 2>&1; echo rc=$?; tail -1 "$S/runall-pre.txt"

# B3 — health-check (the 54-site jq consumer); 124 s measured 2026-10-05
env -u SWEEP_PG_DSN bash runbooks/health-check.sh "$S/hc-pre.txt" > "$S/hc-pre.out" 2>&1; echo rc=$?
grep -ciE 'jq: |parse error' "$S/hc-pre.txt" "$S/hc-pre.out"            # baseline: 0 and 0 (2026-10-05)

# B4 — render hashes (kustomize) and yq reads
for d in kubernetes/apps/ai/paperclip/app kubernetes/flux/meta kubernetes/apps/monitoring/kube-prometheus-stack/app; do
  echo "$d $(mise exec -- kustomize build "$d" | shasum -a 256 | cut -c1-16)"; done | tee "$S/kbuild-pre.txt"
mise exec -- yq '.talosVersion, .kubernetesVersion' kubernetes/bootstrap/talos/talconfig.yaml | tee "$S/yq-pre.txt"
mise exec -- flux get kustomizations -A --no-header | awk '{print $1, $5}' | sort > "$S/flux-ks-pre.txt"; wc -l < "$S/flux-ks-pre.txt"
```

## 3. Steps

3.1 **Install the targets first, alongside the current versions.** This must come
before the edit. Between an edited `.mise.toml` and its binaries existing, every
`mise exec` in every other session fails with "tool not installed". Installing
first leaves that gap at zero.

```bash
S=/private/tmp/claude-501/cli-tool-pins; mkdir -p "$S"; cd /Users/mu/code/cberg-home-nextgen   # re-set in EVERY block: shell state does not persist between agent Bash calls
cd /Users/mu/code/cberg-home-nextgen
mise install aqua:fluxcd/flux2@2.9.3 aqua:getsops/sops@3.13.3 aqua:FiloSottile/age@1.3.2 \
  aqua:go-task/task@3.54.0 aqua:kubernetes-sigs/kustomize@5.8.2 aqua:mikefarah/yq@4.54.1 \
  aqua:jqlang/jq@1.8.2 aqua:cloudflare/cloudflared@2026.9.3 aqua:aquasecurity/trivy@0.75.0
echo rc=$?                                   # non-zero: STOP (nothing changed yet; nothing to roll back)
```

3.2 **Edit the nine pin lines.** The edit uses exact-line anchors and asserts each
matches exactly once. Dry-tested on a scratch copy on 2026-10-05: `edited 9 pins`,
and `tomllib` parses the result.

```bash
S=/private/tmp/claude-501/cli-tool-pins; mkdir -p "$S"; cd /Users/mu/code/cberg-home-nextgen   # re-set in EVERY block: shell state does not persist between agent Bash calls
F=.mise.toml python3 - <<'EOF'
import os
p = os.environ["F"]
BUMPS = {  # tool: (current, target)
    "aqua:fluxcd/flux2": ("2.9.0", "2.9.3"),
    "aqua:getsops/sops": ("3.13.0", "3.13.3"),
    "aqua:FiloSottile/age": ("1.3.1", "1.3.2"),
    "aqua:go-task/task": ("3.46.4", "3.54.0"),
    "aqua:kubernetes-sigs/kustomize": ("5.6.0", "5.8.2"),
    "aqua:mikefarah/yq": ("4.50.1", "4.54.1"),
    "aqua:jqlang/jq": ("1.7.1", "1.8.2"),
    "aqua:cloudflare/cloudflared": ("2026.9.1", "2026.9.3"),
    "aqua:aquasecurity/trivy": ("0.70.0", "0.75.0"),
}
lines = open(p).read().split("\n")
for tool, (cur, tgt) in BUMPS.items():
    old = f'"{tool}" = "{cur}"'
    hits = [i for i, l in enumerate(lines) if l == old]
    assert len(hits) == 1, f"{tool}: expected exactly one line == {old!r}, got {len(hits)} -- STOP"
    lines[hits[0]] = f'"{tool}" = "{tgt}"'
open(p, "w").write("\n".join(lines))
print(f"edited {len(BUMPS)} pins")
EOF
python3 -c "import tomllib;tomllib.load(open('.mise.toml','rb'));print('toml ok')"
git diff --stat .mise.toml                   # 1 file, 9 insertions(+), 9 deletions(-)
```

The expected diff (dry run, 2026-10-05) is these nine lines and nothing else:
`cloudflared 2026.9.1->2026.9.3`, `age 1.3.1->1.3.2`, `flux2 2.9.0->2.9.3`,
`sops 3.13.0->3.13.3`, `task 3.46.4->3.54.0`, `jq 1.7.1->1.8.2`,
`kustomize 5.6.0->5.8.2`, `yq 4.50.1->4.54.1`, `trivy 0.70.0->0.75.0`.

3.3 **Commit only this file, check the subject, and push.** Flux does not read
`.mise.toml`. The CI render gate reads only the `flate` pin, which is unchanged.

```bash
S=/private/tmp/claude-501/cli-tool-pins; mkdir -p "$S"; cd /Users/mu/code/cberg-home-nextgen   # re-set in EVERY block: shell state does not persist between agent Bash calls
printf 'chore(tooling): bump Mac CLI pins (flux 2.9.3, sops 3.13.3, age 1.3.2, task 3.54.0, kustomize 5.8.2, yq 4.54.1, jq 1.8.2, cloudflared 2026.9.3, trivy 0.75.0)\n\nplan: cli-tool-pins\n' > "$S/msg.txt"
git commit --only .mise.toml -F "$S/msg.txt"
git log -1 --format=%s        # must be YOUR subject; amend before push if a concurrent commit swapped it
git show --stat HEAD          # exactly .mise.toml
git pull --rebase --autostash && git push
```

## 4. Verification

Each gate names its failure mode. All output stays in `$S`, never in the repo.

4.1 **Every bumped binary resolves to its target** (a stale shim or missing
install shows the old version or "not installed"):
```bash
S=/private/tmp/claude-501/cli-tool-pins; mkdir -p "$S"; cd /Users/mu/code/cberg-home-nextgen   # re-set in EVERY block: shell state does not persist between agent Bash calls
mise ls --current | grep -E 'flux2|sops|age|task|kustomize|yq|jq|cloudflared|trivy'
mise exec -- sh -c 'flux version --client; sops --version | head -1; age --version; task --version; kustomize version; yq --version; jq --version; cloudflared --version; trivy --version | head -1'
```
PASS: `flux: v2.9.3`, `sops 3.13.3`, `v1.3.2`, `3.54.0`, `v5.8.2`, `v4.54.1`,
`jq-1.8.2`, `2026.9.3`, `Version: 0.75.0`.

4.2 **trivy positive and negative control** through the sweep's own parser. FAIL
modes: the positive control reads `tallied=NONE` (the silent-zero hazard), or the
scan exits non-zero.
```bash
S=/private/tmp/claude-501/cli-tool-pins; mkdir -p "$S"; cd /Users/mu/code/cberg-home-nextgen   # re-set in EVERY block: shell state does not persist between agent Bash calls
export TRIVY_USERNAME=nachtschatt3n TRIVY_PASSWORD="$(gh auth token)"       # env only, never argv
# 0.75 can fetch + open the DB on its own (not only reuse the one 0.70 wrote in B1):
mise exec -- trivy image --download-db-only --quiet --cache-dir "$S/c75"; echo rc=$?          # 0
mise exec -- trivy image --cache-dir "$S/c75" --skip-db-update --skip-java-db-update --severity CRITICAL,HIGH --exit-code 0 --quiet --format json --timeout 90s alpine:3.10.0 \
  | python3 -c "import sys,json;d=json.load(sys.stdin);print('own-db', d['Trivy']['Version'], len(d.get('Results') or []))"   # own-db 0.75.0 >=1
mise exec -- trivy image --severity CRITICAL,HIGH --exit-code 0 --quiet --format json --timeout 90s alpine:3.10.0 > "$S/pc.json"; echo rc=$?
mise exec -- trivy image --severity CRITICAL,HIGH --exit-code 0 --quiet --format json --timeout 90s busybox:1.38.0 > "$S/nc.json"; echo rc=$?
_MISE_ACTIVATED=1 python3 -c "
import json,os,importlib.util,sys
s=importlib.util.spec_from_file_location('sc','runbooks/security-check.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
pc=json.load(open('$S/pc.json'));nc=json.load(open('$S/nc.json'))
print('pc', pc['Trivy']['Version'], pc.get('SchemaVersion'), 'tallied' if m.tally_trivy_report(pc) else 'NONE')
print('nc', nc['Trivy']['Version'], 'clean' if m.tally_trivy_report(nc) is None else 'NOT-CLEAN')"
```
PASS: both scans `rc=0`, `pc 0.75.0 2 tallied` and `nc 0.75.0 clean` (a clean image reads
clean; trivy OMITS the `Results` key for this image on both 0.70.0 and 0.75.0, so do not gate
on that key — reviewer measurement 2026-10-05). The positive control is a
public EOL image we do not run; measured `tallied` on both 0.70.0 and 0.75.0 on
2026-10-05.

4.3 CONTENTS ASSERTION: the scanner still sees every vulnerability it saw before,
on every running image. Measured by the B1 harness re-run on 0.75.0 against **the
same DB** as B1 and diffed per image.
```bash
S=/private/tmp/claude-501/cli-tool-pins; mkdir -p "$S"; cd /Users/mu/code/cberg-home-nextgen   # re-set in EVERY block: shell state does not persist between agent Bash calls
export TRIVY_USERNAME=nachtschatt3n TRIVY_PASSWORD="$(gh auth token)"
_MISE_ACTIVATED=1 mise exec -- python3 "$S/fleet_scan.py" "$(mise which trivy)" "$S/imgs.txt" "$S/post.json" --skip-db-update --skip-java-db-update
python3 "$S/fleet_diff.py" "$S/pre.json" "$S/post.json"
# negative control — proves this diff CAN fail:
python3 -c "import json;d=json.load(open('$S/post.json'));k=[i for i in d if d[i]['ok'] and d[i]['ids']][0];d[k]['ids']=[];json.dump(d,open('$S/post-broken.json','w'))"
python3 "$S/fleet_diff.py" "$S/pre.json" "$S/post-broken.json"     # MUST print VERDICT: FAIL
```
PASS needs all of:
- `versions=['0.75.0']`.
- `VERDICT: PASS`: `lost_ok=0`, `images_with_vanished_ids=0`, `went_zero=0`.
- The negative control prints `VERDICT: FAIL`.

`images_with_added_ids > 0` is allowed. The 0.72-0.75 detection improvements in
§1 may add findings, and that is the expected direction. FAIL means rollback:
- `went_zero>0` is exactly the silent-zero hazard.
- `vanished>0` means detection was lost.
- `lost_ok>0` means images that scanned on 0.70 now fail, which the sweep would
  report as UNKNOWN.

Print only the aggregate line; never paste IDs or per-image counts into the
window report.

4.4 **sops / age decrypt, encrypt and key identity.** A MAC or format regression
fails `sops -d`. The round trip proves that encrypt plus decrypt is lossless.
```bash
S=/private/tmp/claude-501/cli-tool-pins; mkdir -p "$S"; cd /Users/mu/code/cberg-home-nextgen   # re-set in EVERY block: shell state does not persist between agent Bash calls
mise exec -- sops -d kubernetes/bootstrap/talos/talsecret.sops.yaml | mise exec -- yq 'keys | length'          # 4 (2026-10-05)
mise exec -- sops -d kubernetes/apps/ai/anythingllm/app/secret.sops.yaml | mise exec -- yq '.kind + " " + ((.stringData // .data) | length | tostring)'   # "Secret 4"
mise exec -- sops -d runbooks/operator-tools.sops.yaml >/dev/null; echo rc=$?                                 # 0
( cd "$S" && printf 'probe: roundtrip-ok\n' > rt.yaml \
  && SOPS_AGE_KEY_FILE=/Users/mu/code/cberg-home-nextgen/age.key mise -C /Users/mu/code/cberg-home-nextgen exec -- sops -e --age age1nw624gkjpl0sattullahnekdswjcvsgarf8gwwyf9jdqc0zm9enqyp2pf6 rt.yaml > rt.enc.yaml \
  && SOPS_AGE_KEY_FILE=/Users/mu/code/cberg-home-nextgen/age.key mise -C /Users/mu/code/cberg-home-nextgen exec -- sops -d rt.enc.yaml )   # "probe: roundtrip-ok"
mise exec -- age-keygen -y age.key                      # == age1nw624gkj...pf6 (the .sops.yaml recipient)
echo ok | mise exec -- age -r "$(mise exec -- age-keygen -y age.key)" | mise exec -- age -d -i age.key   # "ok"
```
The round trip was dry-tested on 3.13.0 from a scratch dir on 2026-10-05. With no
`.sops.yaml` above the cwd, the explicit `--age` recipient is used.

4.5 **jq 1.8: proven active, and the sweep's jq consumers raise no errors.**
```bash
S=/private/tmp/claude-501/cli-tool-pins; mkdir -p "$S"; cd /Users/mu/code/cberg-home-nextgen   # re-set in EVERY block: shell state does not persist between agent Bash calls
echo 1 | mise exec -- jq 'ltrimstr("a")' 2>&1 | grep -ci 'jq: error'      # 1 — positive control: only 1.8 errors here (1.7.1 prints 1)
env -u SWEEP_PG_DSN bash runbooks/health-check.sh "$S/hc-post.txt" > "$S/hc-post.out" 2>&1; echo rc=$?
grep -ciE 'jq: |parse error' "$S/hc-post.txt" "$S/hc-post.out"            # must equal B3 (0 / 0)
```
FAIL: any `jq: error` or `jq: compile error` line, which is how a 1.8 semantics
break surfaces. The positive control proves both that 1.8 is the jq on PATH and
that this grep catches jq's error format (case-insensitive). A pre-plan shadow run on
2026-10-05 (jq 1.8.2 first on PATH) completed rc=0 with 0 jq errors.

4.6 **task, kubeconform and the audit suite.** A Taskfile parse break fails
`task --list-all`.
```bash
S=/private/tmp/claude-501/cli-tool-pins; mkdir -p "$S"; cd /Users/mu/code/cberg-home-nextgen   # re-set in EVERY block: shell state does not persist between agent Bash calls
mise exec -- task --list-all >/dev/null; echo rc=$?                    # 0 (parses root + bootstrap/talos includes)
mise exec -- task test > "$S/task-test.txt" 2>&1; echo rc=$?            # 0
grep -E 'audit test suites passed|FAIL' "$S/task-test.txt" | tail -3    # same "N audit test suites passed" as B2 (191 on 2026-10-05), no FAIL
grep -E '^Summary' "$S/task-test.txt"                                   # kubeconform summary, Invalid: 0, Errors: 0
```

4.7 **kustomize and yq give identical renders and reads.**
```bash
S=/private/tmp/claude-501/cli-tool-pins; mkdir -p "$S"; cd /Users/mu/code/cberg-home-nextgen   # re-set in EVERY block: shell state does not persist between agent Bash calls
for d in kubernetes/apps/ai/paperclip/app kubernetes/flux/meta kubernetes/apps/monitoring/kube-prometheus-stack/app; do
  echo "$d $(mise exec -- kustomize build "$d" | shasum -a 256 | cut -c1-16)"; done > "$S/kbuild-post.txt"
diff "$S/kbuild-pre.txt" "$S/kbuild-post.txt" && echo RENDER-IDENTICAL
mise exec -- yq '.talosVersion, .kubernetesVersion' kubernetes/bootstrap/talos/talconfig.yaml | diff "$S/yq-pre.txt" - && echo YQ-IDENTICAL
mise exec -- flux get kustomizations -A --no-header | awk '{print $1, $5}' | sort | diff "$S/flux-ks-pre.txt" - && echo FLUX-READ-IDENTICAL
mise exec -- flux version          # client v2.9.3 == distribution flux-v2.9.3
mise exec -- cloudflared tunnel --help >/dev/null; echo rc=$?          # 0
```
A kustomize render difference is a STOP-and-read: release notes say "not expected
to change". An empty pre file makes `diff` pass vacuously, so `wc -l` on both
files must be 3. A `flux get` diff can be legitimate reconcile churn; re-run once
before treating it as a fault.

4.8 **Force the next sweep to rescan on 0.75.** The cache is keyed on tally
version, not on trivy version, so without this the next sweep (within 24h) would
serve 0.70 results.
```bash
S=/private/tmp/claude-501/cli-tool-pins; mkdir -p "$S"; cd /Users/mu/code/cberg-home-nextgen   # re-set in EVERY block: shell state does not persist between agent Bash calls
C="$TMPDIR/cberg-trivy-cve-cache-v4.json"; [ -f "$C" ] && mv "$C" "$C.pre-trivy-0.75" && echo moved-aside
```

4.9 **Deferred gate (owned by the first sweep after the bump, then the
coordinator).**
- The sweep's security section prints `Trivy coverage: N/N scannable images`, with
  N within a few of `wc -l $S/imgs.txt`, and is not degraded.
- Open security image-CVE findings must not collapse. Compare
  `policy-cli.py finding list --section security --limit 500 | grep -c 'CVE'`
  before the plan and after that sweep. A drop of more than 10% without a matching
  bump in that sweep means rollback and re-open.
- The cycle timestamp advances.

CONTROL: metric sweep_cron_newest_cycle_timestamp_seconds — must advance past the push time after the next scheduled sweep (a sweep that crashed on a new binary would not produce a cycle). Live series present 2026-10-05 (job maintenance-window-liveness).
CONTROL: alertname SweepPipelineDead — must NOT be firing during and after the plan (the in-cluster sweep heartbeat; a regression in the toolchain the heartbeat path depends on surfaces here).

## 5. Rollback

The old binaries are still installed: §3.1 installs alongside and this plan never
runs `mise prune`. Rollback is therefore instant and needs no download.
```bash
S=/private/tmp/claude-501/cli-tool-pins; mkdir -p "$S"; cd /Users/mu/code/cberg-home-nextgen   # re-set in EVERY block: shell state does not persist between agent Bash calls
cd /Users/mu/code/cberg-home-nextgen
git revert --no-edit <sha-from-3.3>
git log -1 --format=%s        # your revert subject
git pull --rebase --autostash && git push
mise install                  # no-op unless an old version was pruned elsewhere
mise exec -- trivy --version | head -1      # Version: 0.70.0
mise exec -- jq --version                   # jq-1.7.1
diff "$S/versions-pre.txt" <(mise ls --current | grep -E 'flux2|sops|age|task|kustomize|yq|jq|cloudflared|trivy') && echo BACK
C="$TMPDIR/cberg-trivy-cve-cache-v4.json"; [ -f "$C.pre-trivy-0.75" ] && mv "$C.pre-trivy-0.75" "$C"   # restore the 0.70 cache if still <24h old
```
Partial rollback is allowed. If only one tool fails its gate (for example jq in
4.5), revert just that line with the same anchored python edit in reverse,
commit, and keep the rest. Record the held tool as a finding with
`policy-cli.py finding add` so the next planner sees why it is held.

Prune the old versions only after one clean sweep cycle:
`mise prune --dry-run` first, then run it as `mu` (never root).

## 6. Interference notes

- **This changes the instrument, not a workload.** Every sweep section, the ops
  console, the window agent's Step 0 (`auto-update.py`, `coverage.py`) and the §2-§5
  commands of every other plan resolve `flux/sops/task/yq/jq/trivy` through mise.
  So `exclusive: true` is set. Nothing else may be in flight, including plans not
  written yet. `autonomy_override: human-gated` keeps it out of the unattended
  nightly slot. That slot (03:30 Europe/Berlin) runs these same binaries in its own
  Step 0 and abuts the 48h sweep (04:00), and this plan takes ~60 min.
- **Recommended slot:** an attended on-demand NOW run in daytime, outside 03:15-06:00
  and outside Mon 07:15-08:30 (retro), with the §2 `ps` check clean. A sat/sun
  attended window also works if the plan has the slot to itself. **Never as root.**
- **flux-distribution-2.9.6 ordering:** either order works. If it runs first,
  premise `flux-distribution-still-2.9.3` fails and this plan STOPS for a re-plan
  (no in-window retarget). If this plan runs first, the CLI catch-up 2.9.3 -> 2.9.6
  is owned by flux-distribution-2.9.6's retire step (being added there by the
  coordinator); this plan does not touch it.
- **Concurrency window inside the plan:** between 3.2 and 3.3, the working-tree
  `.mise.toml` already carries the new pins. Because 3.1 pre-installed them, nobody hits
  "not installed". Sessions that resolve per call (`mise exec`, shims) pick up the new
  binaries on their next command. Long-lived sessions that activated mise earlier keep a
  PATH snapshot pointing at the OLD install dirs until they re-activate; that is harmless
  (the old versions stay installed, nothing is pruned) — they simply keep running the old
  binaries until restarted. A command already mid-run keeps its binary until it exits.
- **trivy DB/cache:** the post run reuses the DB that B1 downloaded
  (`--skip-db-update`), so the parity diff compares binaries, not DB days. Both
  versions read schema-v2 DB and java-db v1 from the same default cache dir.
- **Reviewer notes (pre-plan evidence, 2026-10-05):**
  - The 19-image same-DB parity run of 0.70.0 vs 0.75.0 was IDENTICAL on all 19, and the blanked-IDs control printed FAIL.
  - `run-all.sh` 191/191 PASS in 139 s.
  - `health-check.sh` baseline completed in 124 s with 0 jq errors. A shadow run with jq 1.8.2 (release binary) first on PATH also completed rc=0 with 0 jq errors and the same summary shape as the baseline.
  - The sops round trip was dry-tested.
  - `mise ls-remote` confirmed all nine targets.

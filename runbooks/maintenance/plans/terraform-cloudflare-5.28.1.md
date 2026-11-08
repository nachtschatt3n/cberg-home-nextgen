---
plan_id: terraform-cloudflare-5.28.1
component: terraform-cloudflare-provider
pr: 253
kind: infra
current: "5.19.1"
target: "5.28.1"
update_type: minor
risk: medium                          # state is rewritten in place by an apply and an older provider may not read it back;
                                      #   live zone settings and bot management are mutated by any non-empty plan. Gate is "0 diff or stop".
est_duration_min: 45
needs_reboot: false
touches:
  namespaces: [flux-system]           # the Terraform state lives in a Secret there
  resources:
    - secret/tfstate-default-cloudflare-tfstate   # read for the backup; written only if an apply is run
    - terraform/cloudflare/.terraform.lock.hcl    # the only file the PR changes
    - cloudflare_zone_setting.ssl
    - cloudflare_zone_setting.min_tls_version
    - cloudflare_zone_setting.always_use_https
    - cloudflare_zone_setting.security_header
    - cloudflare_bot_management.main
  shared:
    - cloudflare-zone-settings        # the live public zone; every internet-facing app is behind these settings
    - cloudflare-api-token            # the cf-security-audit token is shared with the security-audit runbook
    - public-edge                     # a wrong bot/TLS setting hits the Alexa skill dispatch path and all external HTTPRoutes
depends_on: []
conflicts_with:
  - envoy-gateway-1.10.0              # its verification reads the same public edge (tunnel to envoy-external); keep attribution clean
  - talos-linux-1.14.5                # reboots nodes; would blind gate 4.3 (tunnel) and could kill the kubeconfig-backed state backend mid-plan
  - flux-oci-chart-sources            # restarts shared pods the same night; do not mix with a Cloudflare edge change
exclusive: false
security_ref: null
capability_change: false              # same resources, same configuration, same behaviour; provider-only bump
rollback_class: backup-restore        # git revert of the lock restores the old provider, but only the state backup restores a state the old provider can read
autonomy_override: human-gated        # operator-run terraform from the Mac with the live Cloudflare token; never a window-agent job
finding_refs: []                      # no sweep finding exists for this bump (policy-cli finding list --grep cloudflare/terraform, 2026-11-09)
review: needs-fix-resolved@2026-11-09   # plan-reviewer 2026-11-09: needs-fix (tfstate Lease pre-check false-STOP) + wording fixes, all applied; on-demand operator runbook (status reference), no cluster window
status: reference                    # on-demand, operator-run: no window slot (a slotless awaiting-go plan is a validation error). Run attended, any day except the talos day
window: null
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/cloudflare.md
generated: "2026-11-09"
premises:
  - id: lock-still-5-19-1
    why: >-
      The plan moves the lock from 5.19.1. If main already carries another version (PR merged or lock edited by hand),
      the baseline in step 3.1 is wrong and the plan must be re-read.
    run: grep -c 'version     = "5.19.1"' terraform/cloudflare/.terraform.lock.hcl
    expect_exact: "1"
  - id: constraint-is-tilde-5
    why: >-
      The constraint ~> 5.0 is why a bare `init -upgrade` could pick a version NEWER than the 5.28.1 whose notes were read.
      The plan therefore uses plain `init` against the PR lock. If the constraint tightens or widens, re-evaluate.
    run: grep -c 'version *= "~' terraform/cloudflare/versions.tf
    expect_exact: "1"
  - id: backend-is-kubernetes-secret
    why: >-
      The state backup in step 3.2 assumes the Kubernetes backend (Secret in flux-system). If the backend moved
      (remote, local, S3) the backup and rollback commands name the wrong object.
    run: grep -c 'backend "kubernetes"' terraform/cloudflare/versions.tf
    expect_exact: "1"
  - id: five-managed-resources
    why: >-
      Gate 4.1 reasons about exactly five managed resources (4 zone_setting + 1 bot_management). A sixth (DNS, ruleset,
      tunnel, access) widens what the provider bump can touch and needs its own release-note read.
    run: cat terraform/cloudflare/zone_settings.tf terraform/cloudflare/bot_protection.tf terraform/cloudflare/main.tf | grep -c '^resource "cloudflare_'
    expect_exact: "5"
  - id: state-secret-exists
    why: >-
      Step 3.2 backs this Secret up. If it is missing the backend is not what the plan describes (or the state was
      never migrated to the cluster).
    run: kubectl get secret tfstate-default-cloudflare-tfstate -n flux-system -o jsonpath='{.metadata.name}'
    expect_exact: "tfstate-default-cloudflare-tfstate"
  - id: tunnel-pod-ready
    why: >-
      Gate 4.3 compares tunnel health after the change. If cloudflared is already unready the post-check proves nothing.
    run: kubectl get deploy cloudflared -n network -o jsonpath='{.status.readyReplicas}'
    expect_exact: "1"
---

# terraform-cloudflare-5.28.1: Cloudflare Terraform provider 5.19.1 -> 5.28.1

## 1. Summary and why held

Renovate PR #253 (branch `renovate/cloudflare-5.x-lockfile`) changes ONE file,
`terraform/cloudflare/.terraform.lock.hcl`: `version` 5.19.1 -> 5.28.1 plus new `h1:`/`zh:` hashes. The constraint in
`versions.tf` stays `~> 5.0`. **It is not a cluster change.** Flux does not read `terraform/`, and no repo CI job runs
Terraform (`.github/workflows/` has flux-local, labeler, release, sweep-dashboard only), so merging the PR proves
nothing about the provider. The first time the new provider touches the zone is the operator's next `./tf plan`.
That is why this is held: a merge is silent and the failure would surface later, on an unrelated settings edit,
against the live public zone.

**What terraform/cloudflare manages (measured: repo files + the live state Secret, 2026-11-09).** Exactly five
resources: `cloudflare_zone_setting` x4 (`ssl`=full, `min_tls_version`=1.2, `always_use_https`=on, `security_header`
= HSTS 1y no preload), `cloudflare_bot_management.main` (`fight_mode=false` per AR-049 so Amazon's Alexa dispatch is
not challenged, `ai_bots_protection="block"`), and one data source `cloudflare_zone.main`.
**Not managed here:** DNS records (external-dns owns them), the tunnel (cloudflared is configured by the in-cluster
ConfigMap, not Terraform), WAF/rulesets, Access apps. So the release notes' many DLP/Access/Workers/ruleset changes
cannot touch this stack. Live state: `serial 4`, written by Terraform 1.15.6, every managed resource at
`schema_version 500`, data source at 0.

**State backend.** `backend "kubernetes"`, `secret_suffix = cloudflare-tfstate`, namespace `flux-system`, i.e. Secret
`tfstate-default-cloudflare-tfstate` (gzip-encoded, 186 days old, labelled `managed-by=terraform`). Terraform takes a
Lease lock in the same namespace while planning. No sops on the state; the Mac reaches it through the repo
`kubeconfig` (`KUBE_CONFIG_PATH`).

**Credentials.** The `./tf` wrapper decrypts the Cloudflare API token from
`kubernetes/apps/network/external/cloudflared/cf-security-audit-token.sops.yaml` (age key from `SOPS_AGE_KEY_FILE`),
resolves the zone id by calling the Cloudflare API with it, and exports both as `TF_VAR_*`. The token is never
printed; do not add `-var` flags, `set -x`, or `TF_LOG` to any command, because `TF_LOG=debug` prints the
Authorization header. Run every Terraform command through `./tf`, never `terraform` directly (it would have no token).

**Upstream evidence for 5.20.0 .. 5.28.1** (GitHub releases of `cloudflare/terraform-provider-cloudflare`, all eleven
read). Items that could matter here, and items that cannot:

- **State schema: no bump for our resources.** `zone_setting` and `bot_management` stay at schema version 500. The only
  version move is `api_shield_operation` 500 -> 501 (5.27.0); we do not use it. 5.21.0 added "no-op state upgraders
  version 0 -> 500" for other types.
- **bot_management is the only resource of ours with real churn:** 5.20.0 "restore `content_bots_protection` handling";
  5.25.0 "mark `bot_preference_sync_enabled` optional-only; Computed caused unknown-after-apply errors" and new
  AI-crawler fields; 5.27.0 "wire up AI Crawl Control fields" and "wire `ai_bots_migration_opt_out` into the API
  model". Our config sets only `fight_mode` and `ai_bots_protection`. New API-backed attributes can show up as a
  diff or as new state values. **This is the single most likely place for a non-empty plan.**
- **zone_setting:** 5.24.0 only adds setting ids (`webmcp_enabled`, `webmcp_packs`). None of our four ids changed.
- **zone data source:** no entry in any of the eleven releases.
- **Breaking-change blocks (5.22, 5.24, 5.27, 5.28):** ai_search_instance, hostname_tls_setting,
  image_variant, organization, zero_trust_* , api_shield_*, registrar_domain(s) REMOVED (5.28.0), hyperdrive,
  account/api_token permission-group `meta`, flagship, zone_dns_settings. None are in this configuration; the
  release text says removed attributes are dropped from state silently and only configs that reference them fail
  `plan`. We reference none.
- **One-way risk, stated plainly.** Unverified upstream (none of the eleven release bodies says either way; 5.22.0/5.24.0
  say removed attributes are silently dropped from state); treat as one-way. Once a
  5.28.x provider has WRITTEN state (any `apply`, including a no-op apply that refreshes), new attributes
  (for example the bot_management AI-crawler fields) are in the Secret. Terraform core hands the old provider a state
  object with attributes its schema lacks, and the framework errors on that. Treat the upgrade as **one-way once
  state is written**, and take the backup first. A bare `plan` does not persist state, so the safe order is: plan on
  the new provider, and only write state if you must.

**Repo correction found while planning (not acted on).** `docs/sops/cloudflare.md` Test 1 runs
`./tf plan -detailed-exitcode -out=/dev/null`. On Terraform 1.15.6 it still exits 0/2 correctly but prints a misleading
"Saved the plan to /dev/null"; avoid it. Gate 4.1 below uses `-detailed-exitcode` WITHOUT `-out`. Also the SOP says "SOPS age key at
`~/.config/sops/age/keys.txt`", which does not exist on this Mac (see CLAUDE.md); `SOPS_AGE_KEY_FILE` in `.envrc` is
the real source.

Risk is **medium**: the blast radius is small (five settings) but it is the public edge and the state rewrite is
not cleanly reversible. Duration ~45 min, attended, no reboot.

## 2. Pre-checks

Run from the repo root on the Mac, with the worktree clean for `terraform/cloudflare/`, `.envrc` loaded.

```bash
cd /Users/mu/code/cberg-home-nextgen
git status --short terraform/cloudflare            # expect: nothing
gh pr view 253 --json files -q '.files[].path'      # expect exactly: terraform/cloudflare/.terraform.lock.hcl
gh pr checks 253                                    # note it: no Terraform job exists, so green means nothing
kubectl get deploy cloudflared -n network          # 1/1
kubectl get secret tfstate-default-cloudflare-tfstate -n flux-system   # exists
kubectl get lease lock-tfstate-default-cloudflare-tfstate -n flux-system -o jsonpath='{.spec.holderIdentity}{"\n"}'   # expect EMPTY output
terraform version                                   # 1.15.x is what wrote the state; any >= 1.6 satisfies versions.tf
```

The Lease object itself always exists (the Kubernetes backend keeps it after unlock; live age 186d, `.spec` = {} means
free), so its existence is normal. A NON-EMPTY `holderIdentity` is the known-bad case: someone else (or a crashed run) holds the lock: stop and find out
before continuing; do NOT `force-unlock` as part of this plan.

## 3. Steps

All commands are run by the operator; none is a cluster mutation except the optional state write in 3.6.

**3.1 Baseline on the OLD provider (proves the zero is not already a non-zero).** The local `.terraform/` still holds
5.19.1 (confirm with `./tf version`, which lists the provider version).

```bash
cd /Users/mu/code/cberg-home-nextgen/terraform/cloudflare
./tf version                                  # expect: provider registry.terraform.io/cloudflare/cloudflare v5.19.1
./tf plan -detailed-exitcode -lock-timeout=60s ; echo "exit=$?"
```

Expected `exit=0` and "No changes". `exit=2` means there is PRE-EXISTING drift unrelated to the upgrade: stop,
resolve it first (this plan cannot be judged against a dirty baseline). `exit=1` is an error (token, kubeconfig,
lock): fix and rerun.

**3.2 Back up the state BEFORE `init` touches anything.** Outside the repo (the Secret holds the zone id; this repo is
public), mode 600.

```bash
umask 077
BK=$HOME/tf-backups/cloudflare-$(date +%Y%m%d-%H%M%S).secret.json
mkdir -p "$HOME/tf-backups"
kubectl get secret tfstate-default-cloudflare-tfstate -n flux-system -o json > "$BK"
ls -l "$BK"
python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print(d['metadata']['name'], list(d['data']))" "$BK"
```

Expected: file > 1 KB, prints `tfstate-default-cloudflare-tfstate ['tfstate']`. Also take the readable form:
`./tf state pull > "$BK.state.json"` (same directory, same mode) and note `serial` (expect 4):
`python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['serial'])" "$BK.state.json"`.

**3.3 Get the PR lock into the working tree, without merging yet.**

```bash
cd /Users/mu/code/cberg-home-nextgen
git fetch origin renovate/cloudflare-5.x-lockfile
git show origin/renovate/cloudflare-5.x-lockfile:terraform/cloudflare/.terraform.lock.hcl > terraform/cloudflare/.terraform.lock.hcl
git diff --stat -- terraform/cloudflare      # expect: 1 file, the lock only
grep -n 'version  ' terraform/cloudflare/.terraform.lock.hcl    # expect: version     = "5.28.1"
```

**3.4 `init` against the pinned lock (deliberately NOT `init -upgrade`).** `~> 5.0` lets `-upgrade` pick anything
newer than 5.28.1 and rewrite the lock, so what was reviewed would not be what ran. Plain `init` installs exactly the
locked 5.28.1 and verifies its checksum against the hashes in the PR's lock.

```bash
cd /Users/mu/code/cberg-home-nextgen/terraform/cloudflare
./tf init
./tf version        # expect: cloudflare/cloudflare v5.28.1
git diff --stat -- .terraform.lock.hcl   # expect: unchanged vs. the PR lock (init must not rewrite it)
```

If `init` rewrites the lock (adds hashes for another platform) that is acceptable only for added `h1:` lines; a
changed `version` is not.

**3.5 Plan on the new provider. This is the gate.**

```bash
./tf validate
./tf plan -detailed-exitcode -lock-timeout=60s -no-color > "$HOME/tf-backups/plan-5.28.1.txt" ; echo "exit=$?"
grep -E '^Plan:|No changes|will be (updated|created|destroyed)|must be replaced|Warning|Error' "$HOME/tf-backups/plan-5.28.1.txt"
```

PASS only if `exit=0` AND the file contains `No changes. Your infrastructure matches the configuration.`
**ANY diff is a STOP** (`exit=2`, a `Plan: N to add/change/destroy` line, `~`/`+`/`-` markers, "must be replaced", or
"Objects have changed outside of Terraform" naming one of our five resources). Do not apply to "make it match".
Go to Rollback section 5 "stop path", and attach `plan-5.28.1.txt` to the follow-up. A provider-only bump must not
change live settings; a diff means the provider models an attribute differently (most likely a bot_management AI
field) and the `.tf` needs a deliberate, separately reviewed edit.
Warnings about deprecated attributes are not a stop, but record them.

**3.6 State write decision (usually: do nothing).** With exit 0 the Secret is untouched (a plan never persists state),
so the cluster-side state is still the 5.19.1-written one and the upgrade is complete for the repo. Do NOT run
`apply` just to "refresh". The first real settings change later will write 5.28.x state; that moment is the one-way
point. If you want the lock to be proven end to end now, `./tf apply -refresh-only` is the only apply allowed, and only
after the operator accepts that it writes the new schema into the Secret (backup from 3.2 is the rollback).

**3.7 Land the PR.**

```bash
cd /Users/mu/code/cberg-home-nextgen
gh pr merge 253 --squash          # or merge in the GitHub UI; the diff is the lock only
git checkout -- terraform/cloudflare/.terraform.lock.hcl   # unconditional: the tracked lock is modified from 3.3, git pull aborts otherwise
git pull --ff-only
git diff --stat HEAD~1 -- terraform/cloudflare   # sanity: lock only
```

The checkout is safe: the content is identical to the merged lock.

## 4. Verification

**4.1 Zero diff on the new provider (the gate).** `./tf plan -detailed-exitcode` after the merge, from a clean
`main`: `exit=0` and the literal text `No changes. Your infrastructure matches the configuration.`
FAILS (so it is a real gate) when a provider models a field differently: `exit=2` with a `~ update in-place` block on
`cloudflare_bot_management.main`, or `exit=1` with "Unsupported argument"/"Provider produced inconsistent result".
Avoid `-out=/dev/null` (misleading message, see section 1).
No known-bad demonstration was run: the signal is the positive reading, the literal `No changes.` text AND exit 0
(exit 2 = diff, 1 = error). Optional demo on a scratch COPY of the `.tf` files only (never the real state): in a
temp dir with `-backend=false` change a value and confirm `plan` reports a diff; this needs no state or token.

**4.2 CONTENTS ASSERTION: the live zone still holds the intended values**, read through the Cloudflare API with the
same token. NOTE `show -json` reads Terraform's STATE, so 4.2 is not an independent live check; 4.1 (zero plan, which
refreshes against the API) is the live check. Do not echo the token or zone id.

```bash
cd /Users/mu/code/cberg-home-nextgen/terraform/cloudflare
./tf show -json | python3 -c "
import sys,json
s=json.load(sys.stdin)
vals={}
for r in s['values']['root_module']['resources']:
    if r['type']=='cloudflare_zone_setting': vals[r['values']['setting_id']]=r['values']['value']
    if r['type']=='cloudflare_bot_management': vals['fight_mode']=r['values']['fight_mode']; vals['ai_bots_protection']=r['values']['ai_bots_protection']
print(vals.get('ssl'), vals.get('min_tls_version'), vals.get('always_use_https'), vals.get('fight_mode'), vals.get('ai_bots_protection'))
"
```

PASS iff it prints `full 1.2 on False block`. It FAILS (and is therefore informative) if state lost a value
(prints `None`) or the provider changed a representation (for example `1.2` coming back numeric, or the HSTS object
changing shape). Because `show -json` reads state, pair it with 4.1: a zero plan is what proves state equals live.

**4.3 Edge and tunnel unchanged (CONTROL: cloudflared pod readiness, `kubectl get deploy cloudflared -n network`).**
Terraform does not touch the tunnel, so this is a regression sentinel for "I broke something else tonight".

```bash
kubectl get deploy cloudflared -n network -o jsonpath='{.status.readyReplicas}{"\n"}'   # expect 1
kubectl logs deploy/cloudflared -n network --tail=200 | grep -ci 'Registered tunnel connection'   # expect >= 1 (21 on 2026-11-09; tail=200 can roll off on a long-lived pod, then read `--since=1h` instead)
```

The pod being Ready does not by itself prove the tunnel carries traffic, so do 4.4. FAILS if `readyReplicas` is empty
or the log shows no registered connection.

**4.4 DNS and edge spot check, 3 records.** Pick three externally exposed hostnames from the cluster, so no domain is
written down here:

```bash
kubectl get httproute -A -o jsonpath='{range .items[?(@.spec.parentRefs[0].name=="envoy-external")]}{.spec.hostnames[0]}{"\n"}{end}' | head -3 | tee $TMPDIR/cf-hosts.txt
for h in $(cat $TMPDIR/cf-hosts.txt); do dig +short "$h" @1.1.1.1 | head -2; curl -s -o /dev/null -w "$(echo $h | cut -c1-3)... %{http_code} %{ssl_verify_result}\n" "https://$h/"; done
```

PASS: each hostname resolves to at least one address (empty output = DNS regression) and `curl` returns an HTTP code
(2xx/3xx/401/403 are all "edge answered"; `000` or `525`/`526` mean TLS/edge failure) with `ssl_verify_result 0`.
This does NOT prove the SSL mode (`full`) unchanged on its own; 4.1/4.2 do. `rm $TMPDIR/cf-hosts.txt` afterwards.

**4.5 Prometheus is not read by this plan**, so no same-night `kube-prometheus-stack` conflict is needed.

## 5. Rollback

There are three situations; pick by where the run stopped.

**Stop path (plan showed a diff, nothing applied; state Secret unchanged since 3.2).** Put the old lock back and
reinstall the old provider. No cluster object was modified.

```bash
cd /Users/mu/code/cberg-home-nextgen
git checkout -- terraform/cloudflare/.terraform.lock.hcl     # restores 5.19.1 (PR not merged)
cd terraform/cloudflare && ./tf init && ./tf version          # expect v5.19.1
./tf plan -detailed-exitcode ; echo "exit=$?"                 # expect 0 (same as baseline 3.1)
```

Close/leave PR #253 with a comment recording the diff; do not retarget the PR to an older version without reading
that version's notes.

**After merge, no state write (the usual case).** `git revert <merge-sha>` (the lock only), `git pull`,
`cd terraform/cloudflare && ./tf init && ./tf plan -detailed-exitcode` expect 0.

**State was written by 5.28.x (an apply ran).** The old provider may refuse the new state. Restore the state first,
then the pin:

```bash
cd /Users/mu/code/cberg-home-nextgen
git revert <merge-sha>        # lock back to 5.19.1
# restore the Secret exactly as backed up in 3.2 (drop server-set fields, then replace)
python3 - "$BK" <<'PY'
import json,sys
d=json.load(open(sys.argv[1]))
for k in ('resourceVersion','uid','creationTimestamp','managedFields'): d['metadata'].pop(k,None)
json.dump(d,open(sys.argv[1]+'.restore.json','w'))
PY
kubectl replace -f "$BK.restore.json"
kubectl get secret tfstate-default-cloudflare-tfstate -n flux-system -o jsonpath='{.metadata.name}{"\n"}'
cd terraform/cloudflare && ./tf init && ./tf state pull | python3 -c "import sys,json; print(json.load(sys.stdin)['serial'])"   # expect the serial from 3.2 (4)
./tf plan -detailed-exitcode ; echo "exit=$?"     # expect 0
```

`BK` is the path printed in step 3.2; export it again in a new shell. If the restore plan is not 0, the live zone
changed during the window: stop and read the diff, do not apply. Live settings only change by `apply`, so a plan-only
run never needs live rollback. If an `apply` DID change a live setting, set it back through the `.tf` (the previous
values are in section 1) and apply on the old provider after the state restore.

## 6. Interference notes

- **Human-gated, not window-agent work.** Needs the Mac's SOPS age key, the repo `kubeconfig`, and the live Cloudflare
  token; never run it from an unattended window. `autonomy_override: human-gated` and `risk: medium` keep it out of
  SD-10.
- **conflicts_with** lists `envoy-gateway-1.10.0` (public-edge verification overlap), `talos-linux-1.14.5` (node reboots
  while the state backend is a cluster Secret and the tunnel is under test) and `flux-oci-chart-sources`. There is no
  open cloudflared or external-dns bump plan (checked 2026-11-09); the cloudflared CLI pin in `cli-tool-pins` is
  superseded. `coredns-1.48.1` is superseded and not listed.
- **Shared token.** The same token is used by the security-audit runbook. Do not rotate it during this run, and do
  not run a sweep that exercises it while a `plan` holds the state lock (the sweep does not use Terraform, so this is
  precautionary).
- **external-dns** keeps writing DNS in parallel; it does not touch the five Terraform-managed objects, so it cannot
  cause drift here. If 3.1 shows a diff on `cloudflare_zone_setting` anyway, someone changed the dashboard.
- **Reciprocity.** `envoy-gateway-1.10.0`, `talos-linux-1.14.5` and `flux-oci-chart-sources` do not list this plan back in
  their own `conflicts_with` (the scheduler honours it symmetrically, but add it when those plans are next edited). Do not
  run this on the same day as `sun-attended:2026-11-22` (talos reboot would blind the tunnel check 4.3).
- **CI gap (separate follow-up, not part of this plan).** Add a plan-only check that runs `terraform init -backend=false`
  + `terraform validate` on any PR touching `terraform/cloudflare/**` (needs no credentials, catches removed
  attributes and lock/constraint mismatches). A full `plan` in CI would need the token and cluster-state access, which
  this public repo should not hand to GitHub Actions, so keep that one operator-run. Also consider a Renovate rule
  that labels this directory "needs-operator-plan" and keeps it out of automerge.
- **Provider lock hygiene.** The PR lock carries 8 `h1:` platform hashes and 9 `zh:` hashes; `init` on the Mac is what
  validates the darwin_arm64 package. Commit nothing from `.terraform/` (gitignored).

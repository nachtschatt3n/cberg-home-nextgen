# Runbook: PiKVM Firmware Update (over SSH)

How to apply a PiKVM (kvmd) update when the sweep's **version-check** flags one,
e.g. `PiKVM (kvmd) (192.168.30.154): 4.171 → 4.172`.

PiKVM is a **physical device** (the KVM at `192.168.30.154`, Trusted VLAN) — it
is **not** GitOps-managed. Updates are done **on the device over SSH**. This
runbook is the procedure; nothing here touches the cluster.

---

## ⚠️ Pre-flight — the version-check runs AHEAD of the pacman repo

The sweep detects the new version via the PiKVM **HTTPS API** (the read-only
`apicheck` kvmd user, see `runbooks/check-all-versions.py` `PIKVM_HOSTS`), which
reports the latest **GitHub release**. PiKVM then builds that release and pushes
it to its **Arch pacman repo a few days later**. So when the finding first
appears, the package is usually **not installable yet** — running the update
would be a no-op (and an unnecessary reboot).

**Always confirm the package is actually in the repo before updating:**

```bash
ssh root@192.168.30.154 'pacman -Sy >/dev/null 2>&1; \
  echo "installed: $(pacman -Q kvmd)"; \
  echo "repo:      $(pacman -Si kvmd | grep -i ^Version)"; \
  echo "pending:   $(pacman -Qu | wc -l) packages"'
```

- If `repo` version == `installed` (and `pending: 0`) → **4.x not in the repo
  yet. STOP — do nothing.** It clears itself on a later sweep once the repo
  catches up. (The finding is a `warning`/`monitor`, not actionable until then.)
- If `repo` shows the newer version (and `pending` > 0) → proceed below.

---

## Access

SSH is **key-based** from this Mac (no password): `ssh root@192.168.30.154`.
Reachable from the Trusted VLAN. Root fs is normally mounted **read-only** (`ro`);
`pikvm-update` flips it `rw` for the upgrade and back to `ro` afterward.

## Update procedure

`pikvm-update` is the official tool — it handles `rw` → `pacman -Syu` → `ro` and
prompts/handles the reboot.

```bash
# 1. (Optional) snapshot current state
ssh root@192.168.30.154 'pacman -Q kvmd; pikvm-info | grep -iE "version|platform" || true'

# 2. Run the official update (does the full system upgrade)
ssh root@192.168.30.154 'pikvm-update'

# 3. Reboot to apply (pikvm-update may prompt; if it didn't reboot, do it)
ssh root@192.168.30.154 'reboot'   # KVM console drops ~30-60s; not service-critical
```

Manual equivalent if `pikvm-update` is unavailable:
```bash
ssh root@192.168.30.154 'rw && pacman -Syu --noconfirm && ro && reboot'
```

## Verification (after it comes back, ~1 min)

```bash
ssh root@192.168.30.154 'pacman -Q kvmd; systemctl is-active kvmd kvmd-nginx'
# expect: kvmd <new-version>-1   and   active / active
```
Then load the PiKVM web UI to confirm the console works. On the next sweep the
version finding auto-closes once `kvmd` reports the new version.

## Notes

- **Blast radius:** only the KVM console (remote keyboard/video/mouse) blips
  during the reboot — it does not affect any cluster workload.
- **Rollback:** PiKVM keeps a previous-package cache under
  `/var/cache/pacman/pkg`; `pacman -U <old-kvmd>.pkg.tar.zst` (with `rw`) reverts.
  Updates are routine — rarely needed.
- **Multiple PiKVMs:** add hosts to `PIKVM_HOSTS` in `check-all-versions.py` and
  create the `apicheck` user on each (`kvmd-htpasswd add apicheck --read-stdin
  --quiet`); this procedure is per-host.

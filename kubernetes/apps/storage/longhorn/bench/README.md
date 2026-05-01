# Longhorn v2 benchmark — manual-apply only

**Do not include this directory in any kustomization tree.**

The Flux Kustomization for `storage/longhorn` watches `./kubernetes/apps/storage/longhorn/app/` only. This `bench/` directory is intentionally a sibling so it never gets picked up by a recursive kustomize.

## What's here

- [`loopback-daemonset.yaml`](./loopback-daemonset.yaml) — privileged DaemonSet that creates a 10 GiB sparse file per node + binds it to `/dev/loop50` with `losetup --direct-io=on`, so SPDK's aio BDEV can use it as a Longhorn v2 block disk.

## Why these are not GitOps-managed

The DaemonSet ships `privileged: true`, `SYS_ADMIN` + `MKNOD` capabilities, and `hostPath: /dev` + `hostPath: /var` — extreme blast radius. It exists in the repo as **versioned documentation** of the manual benchmark procedure. If it were deployed full-time it would be an unnecessary attack surface.

## Workflow

See [`docs/sops/longhorn-v2-benchmark.md`](../../../../../docs/sops/longhorn-v2-benchmark.md). High level:

1. `kubectl apply -f kubernetes/apps/storage/longhorn/bench/loopback-daemonset.yaml`
2. Enable v2 + register block disks per Step 1/2 of the SOP.
3. Run the fio benchmark Jobs.
4. Tear down per Step 5 of the SOP (order matters: v2 must stay enabled until the disks are evicted+removed).
5. `kubectl delete -f kubernetes/apps/storage/longhorn/bench/loopback-daemonset.yaml`

## Last run

2026-05-01: results in [`docs/sops/longhorn-v2-benchmark.md`](../../../../../docs/sops/longhorn-v2-benchmark.md) "Run notes" section. v2 won by ~50–120% across all measured tests.

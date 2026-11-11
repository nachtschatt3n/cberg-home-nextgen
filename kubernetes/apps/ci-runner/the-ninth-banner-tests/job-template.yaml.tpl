---
# TEMPLATE, NOT A FLUX RESOURCE: outside ./app (Flux never applies it) and .tpl (kubeconform never
# reads it). scripts/ninth-banner-test.sh replaces the __PLACEHOLDERS__ and
# `kubectl create`s one Job per run. docs/sops/ci-runner.md
#
# Indexed Job: one pod per shard (JOB_COMPLETION_INDEX -> --shard=i+1/N),
# at most __PARALLELISM__ (3 GPU / 2 CPU; sims 6, 3 or 2 by free CPU) at a time per Job; node placement is
# left to the scheduler (all three nodes since 2026-10-12). backoffLimitPerIndex 0 +
# maxFailedIndexes N: a failing shard is NOT retried and does NOT stop the
# others, so every shard reports.
apiVersion: batch/v1
kind: Job
metadata:
  name: __JOB_NAME__
  namespace: ci-runner
  labels:
    app.kubernetes.io/name: the-ninth-banner-tests
    ci.cberg.home/suite: __SUITE__
    ci.cberg.home/lane: __LANE__
    # one in-flight sims Job per submitter (admission, scripts/ninth-banner-capacity.py)
    ci.cberg.home/submitter: "__SUBMITTER__"
  annotations:
    ci.cberg.home/ref: "__REF__"
spec:
  completionMode: Indexed
  completions: __SHARDS__
  parallelism: __PARALLELISM__
  backoffLimitPerIndex: 0
  maxFailedIndexes: __SHARDS__
  activeDeadlineSeconds: __DEADLINE__
  # Job deadline, set per suite by the trigger script. It counts from the
  # JOB's start, so it has to cover every round when parallelism < shards
  # (sims, 2026-11-07/08: 6 shards at parallelism 2, shards that started at
  # ~2 h hit the old 3 h deadline). sims (2026-11-11): rounds x (pod deadline
  # + 300 s), rounds = ceil(shards / parallelism); 6 shards: 12900 s at
  # parallelism 6, 25800 s at 3, 38700 s at 2 (a fixed 28800 s before, which
  # three rounds of 12600 s do not fit). Other suites: 5400 s.
  # The real per-shard limit is the POD deadline below (__POD_DEADLINE__ s
  # here; sims 12600 s = 3.5 h, others 5400 s), which counts from each pod's
  # own start.
  # 3600 s (2026-10-20, was 600): a Job that ends by DeadlineExceeded or a
  # lost trigger must leave its pods/logs readable for an hour.
  ttlSecondsAfterFinished: 3600
  template:
    metadata:
      labels:
        app.kubernetes.io/name: the-ninth-banner-tests
        ci.cberg.home/suite: __SUITE__
        # browser | cpu (resource profile only; no admission gate since 2026-10-06)
        ci.cberg.home/lane: __LANE__
    spec:
      restartPolicy: Never
      # Per-shard time limit, counted from THIS pod's start (clone included),
      # so a shard that waited in the Job's queue gets its full budget. sims:
      # 12600 s since 2026-11-11 (9000 s killed shards that needed up to
      # 9,496 s; 1-1.7 h per shard when measured 2026-11-08). A pod killed here
      # stays as Failed/DeadlineExceeded and prints no result line of its own:
      # the collector writes the shard's `rc=? (lost: pod deadline: ...)` line.
      activeDeadlineSeconds: __POD_DEADLINE__
      serviceAccountName: the-ninth-banner-tests
      # Negative priority, never preempts: CI pods are evicted first under node
      # pressure and can never displace a production pod to get scheduled.
      priorityClassName: ci-low
      automountServiceAccountToken: false
      enableServiceLinks: false
      terminationGracePeriodSeconds: 10
      # Owner, 2026-10-06: the thermal gate is removed; the 35/55 W RAPL caps
      # are the only heat limit. Owner, 2026-10-12: nuc14-02 is clean again,
      # its NotIn node affinity is gone, shards may land on any node.
      securityContext:
        # the Playwright image's own non-root user (pwuser, uid/gid 1001)
        runAsNonRoot: true
        runAsUser: 1001
        runAsGroup: 1001
        fsGroup: 1001
        seccompProfile:
          type: RuntimeDefault
      topologySpreadConstraints:
        - maxSkew: 1
          topologyKey: kubernetes.io/hostname
          whenUnsatisfiable: ScheduleAnyway
          labelSelector:
            matchLabels:
              batch.kubernetes.io/job-name: __JOB_NAME__
      initContainers:
        - name: clone
          # Pinned by multi-arch INDEX digest; tag kept for readability. Bump
          # procedure (tag must match @playwright/test): docs/sops/ci-runner.md §4.
          image: &image mcr.microsoft.com/playwright:v1.63.0-noble@sha256:eff16c30e6f3f4af0a03fa4b706120d5e9b0891c344a27d64559aff5900a4a27
          command: ["bash", "/opt/ci/clone.sh"]
          env:
            - name: REF
              value: "__REF__"
            - name: REPO_URL
              value: https://github.com/nachtschatt3n/the-ninth-banner.git
          securityContext: &csc
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities:
              drop: ["ALL"]
          resources:
            requests: { cpu: 200m, memory: 256Mi, ephemeral-storage: 512Mi }
            limits: { cpu: "1", memory: 1Gi, ephemeral-storage: 2Gi }
          volumeMounts:
            - { name: work, mountPath: /work }
            - { name: tmp, mountPath: /tmp }
            - { name: scripts, mountPath: /opt/ci, readOnly: true }
            # the ONLY container with the git credential
            - { name: git-credential, mountPath: /secrets/git, readOnly: true }
      containers:
        - name: runner
          image: *image
          command: ["bash", "/opt/ci/run.sh"]
          env:
            - name: SUITE
              value: __SUITE__
            - name: SHARD_TOTAL
              value: "__SHARDS__"
            - name: WORKERS
              value: "__WORKERS__"
            - name: COLLECT_WAIT_SECONDS
              value: "__COLLECT_WAIT__"
            # GPU mode: flags appended to every Chromium launch (empty = CPU/SwiftShader)
            - name: CHROMIUM_EXTRA_ARGS
              value: "__CHROMIUM_ARGS__"
            # optional narrowing: space-separated spec files / one Playwright project
            - name: SPECS
              value: "__SPECS__"
            - name: PROJECT
              value: "__PROJECT__"
            - name: NODE_NAME
              valueFrom:
                fieldRef:
                  fieldPath: spec.nodeName
            # Node sees all 17 host CPUs; keep libuv/V8 helper pools sane
            - name: UV_THREADPOOL_SIZE
              value: "6"
          securityContext: *csc
          resources:
            # THERMAL cap: 6 CPU/shard drove all three NUC14s to 100-102 C
            # (2026-10-03; 102 C caused a thermal reboot 2026-08-08, see
            # docs/sops/immich.md). 4 CPU is at/below the Immich server cap.
            # __GPU_RES__ is empty, or `, gpu.intel.com/i915: "1"` (GPU=1): one
            # of the 5 shared slots per node the Intel GPU device plugin offers
            # (docs/sops/ci-runner.md "GPU mode").
            # cpu lane (sims/unit, no browser): 1 CPU / 1Gi request, 1.5 CPU /
            # 3Gi limit, 2/8Gi disk (measured: sims ~1 core, <= 0.61Gi; unit
            # <= 1.2Gi). Browser lane: 2/4 CPU, 6/10Gi, 8/16Gi disk.
            requests: { cpu: "__CPU_REQ__", memory: __MEM_REQ__, ephemeral-storage: __EPH_REQ____GPU_RES__ }
            limits: { cpu: "__CPU_LIM__", memory: __MEM_LIM__, ephemeral-storage: __EPH_LIM____GPU_RES__ }
          volumeMounts:
            - { name: work, mountPath: /work }
            - { name: tmp, mountPath: /tmp }
            - { name: shm, mountPath: /dev/shm }
            - { name: results, mountPath: /results }
            - { name: scripts, mountPath: /opt/ci, readOnly: true }
      volumes:
        - name: work
          emptyDir: { sizeLimit: 10Gi }
        - name: tmp
          emptyDir: { sizeLimit: 4Gi }
        # 6Gi (was 2Gi): the release suite's shard with the responsive screen
        # tours (iPad/desktop screenshots) + perf specs outgrew 2Gi and was
        # evicted twice (2026-10-04, game 5328961) although all its tests passed;
        # the other shards write 2-3 MB. run.sh logs `du` of /results before
        # CI-RESULT so the next oversize run shows what fills it. Sum of the
        # volume caps (20Gi) exceeds the 16Gi container limit on purpose: work
        # really uses ~0.8Gi, so 16Gi still covers a full 6Gi results dir.
        - name: results
          emptyDir: { sizeLimit: 6Gi }
        - name: shm   # Chromium needs a real /dev/shm; counts against memory
          emptyDir: { medium: Memory, sizeLimit: 2Gi }
        - name: scripts
          configMap:
            name: the-ninth-banner-tests-scripts
            defaultMode: 0555
        - name: git-credential
          secret:
            secretName: the-ninth-banner-git-credential
            defaultMode: 0440

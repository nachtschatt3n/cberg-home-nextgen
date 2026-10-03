---
# TEMPLATE, NOT A FLUX RESOURCE: outside ./app (Flux never applies it) and .tpl (kubeconform never
# reads it). scripts/ninth-banner-test.sh replaces the __PLACEHOLDERS__ and
# `kubectl create`s one Job per run. docs/sops/ci-runner.md
#
# Indexed Job: one pod per shard (JOB_COMPLETION_INDEX -> --shard=i+1/N),
# at most 3 at a time, spread over the 3 nodes. backoffLimitPerIndex 0 +
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
  annotations:
    ci.cberg.home/ref: "__REF__"
spec:
  completionMode: Indexed
  completions: __SHARDS__
  parallelism: __PARALLELISM__
  backoffLimitPerIndex: 0
  maxFailedIndexes: __SHARDS__
  activeDeadlineSeconds: 5400
  ttlSecondsAfterFinished: 3600
  template:
    metadata:
      labels:
        app.kubernetes.io/name: the-ninth-banner-tests
        ci.cberg.home/suite: __SUITE__
    spec:
      restartPolicy: Never
      serviceAccountName: the-ninth-banner-tests
      automountServiceAccountToken: false
      enableServiceLinks: false
      terminationGracePeriodSeconds: 10
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
          image: &image mcr.microsoft.com/playwright:v1.63.0-noble
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
            - name: NODE_NAME
              valueFrom:
                fieldRef:
                  fieldPath: spec.nodeName
            # Node sees all 17 host CPUs; keep libuv/V8 helper pools sane
            - name: UV_THREADPOOL_SIZE
              value: "6"
          securityContext: *csc
          resources:
            requests: { cpu: "3", memory: 6Gi, ephemeral-storage: 8Gi }
            limits: { cpu: "6", memory: 10Gi, ephemeral-storage: 16Gi }
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
        - name: results
          emptyDir: { sizeLimit: 2Gi }
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

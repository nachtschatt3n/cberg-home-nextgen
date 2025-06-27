#!/bin/bash

# Run the pod with kubectl run
kubectl run llama-cpp-intel-gpu -n ai --rm -it \
  --image=ghcr.io/ggml-org/llama.cpp:full-intel \
  --labels=app=llama-cpp-intel-gpu \
  --overrides='{
  "apiVersion": "v1",
  "kind": "Pod",
  "metadata": {
    "name": "llama-cpp-intel-gpu",
    "namespace": "ai",
    "labels": {
      "app": "llama-cpp-intel-gpu"
    }
  },
  "spec": {
    "hostPID": true,
    "hostIPC": true,
    "containers": [
      {
        "name": "llama-server",
        "image": "ghcr.io/ggml-org/llama.cpp:full-intel",
        "stdin": true,
        "tty": true,
        "env": [
          {
            "name": "ZES_ENABLE_SYSMAN",
            "value": "1"
          },
          {
            "name": "GGML_SYCL_DISABLE_GRAPH",
            "value": "1"
          },
          {
            "name": "GGML_SYCL_DISABLE_OPT",
            "value": "0"
          },
          {
            "name": "ONEAPI_DEVICE_SELECTOR",
            "value": "level_zero:0"
          },
          {
            "name": "GGML_SYCL_DEBUG",
            "value": "0"
          },
          {
            "name": "SYCL_DEVICE_FILTER",
            "value": "level_zero:gpu:0"
          },
          {
            "name": "INTEL_DEVICE_SELECTOR",
            "value": "level_zero:gpu:0"
          },
          {
            "name": "GGML_SYCL_PRIORITIZE_DMMV",
            "value": "0"
          },
          {
            "name": "GGML_SYCL_DISABLE_DNN",
            "value": "1"
          },
          {
            "name": "OMP_NUM_THREADS",
            "value": "8"
          },
          {
            "name": "MKL_NUM_THREADS",
            "value": "8"
          }
        ],
        "command": [
          "/bin/bash",
          "-c",
          "/app/llama-server --host 0.0.0.0 --port 8080 --ctx-size 8192 --threads 8 --n-gpu-layers 35 --batch-size 1024 --ubatch-size 512 -hf unsloth/Llama-3.2-3B-Instruct-GGUF"
        ],
        "securityContext": {
          "privileged": true,
          "allowPrivilegeEscalation": true,
          "capabilities": {
            "add": ["SYS_ADMIN"]
          },
          "runAsUser": 0
        },
        "resources": {
          "requests": {
            "gpu.intel.com/i915": 1
          },
          "limits": {
            "gpu.intel.com/i915": 1
          }
        },
        "ports": [
          {
            "containerPort": 8080,
            "hostPort": 8080
          }
        ]
      }
    ]
  }
}'

# Create a service for the OpenAI-compatible server
kubectl delete service llama-openai-service -n ai
#kubectl expose pod llama-cpp-intel-gpu -n ai --name=llama-openai-service --port=8080 --target-port=8080 --type=ClusterIP

echo "Created OpenAI-compatible server service."
echo "You can connect Open WebUI to: http://llama-openai-service.ai.svc.cluster.local:8080"
echo "Or access directly via port-forward: kubectl port-forward -n ai llama-cpp-intel-gpu 8080:8080"

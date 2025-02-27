#!/bin/bash

# Run the pod with kubectl run
kubectl run ollama-intel-gpu -n ai --rm -it \
  --image=ubuntu:24.04 \
  --labels=app=ollama-intel-gpu \
  --overrides='{
  "apiVersion": "v1",
  "kind": "Pod",
  "metadata": {
    "name": "ollama-intel-gpu",
    "namespace": "ai",
    "labels": {
      "app": "ollama-intel-gpu"
    }
  },
  "spec": {
    "hostPID": true,
    "hostIPC": true,
    "containers": [
      {
        "name": "ollama",
        "image": "ubuntu:24.04",
        "stdin": true,
        "tty": true,
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
            "containerPort": 11434,
            "hostPort": 11434
          }
        ],
        "command": [
          "/bin/bash",
          "-c",
          "if [ -f \"/INSTALLED\" ]; then echo \"Installation already completed. Skipping to shell...\" && export OLLAMA_HOST=0.0.0.0:11434 && exec /start-ollama.sh; else export DEBIAN_FRONTEND=noninteractive && export TZ=america/los_angeles && apt update && apt install --no-install-recommends -q -y software-properties-common ca-certificates wget ocl-icd-libopencl1 zsh vim curl git && mkdir -p /tmp/gpu && cd /tmp/gpu && wget https://github.com/oneapi-src/level-zero/releases/download/v1.19.2/level-zero_1.19.2+u24.04_amd64.deb && wget https://github.com/intel/intel-graphics-compiler/releases/download/v2.5.6/intel-igc-core-2_2.5.6+18417_amd64.deb && wget https://github.com/intel/intel-graphics-compiler/releases/download/v2.5.6/intel-igc-opencl-2_2.5.6+18417_amd64.deb && wget https://github.com/intel/compute-runtime/releases/download/24.52.32224.5/intel-level-zero-gpu_1.6.32224.5_amd64.deb && wget https://github.com/intel/compute-runtime/releases/download/24.52.32224.5/intel-opencl-icd_24.52.32224.5_amd64.deb && wget https://github.com/intel/compute-runtime/releases/download/24.52.32224.5/libigdgmm12_22.5.5_amd64.deb && dpkg -i *.deb && rm *.deb && cd / && wget https://github.com/mattcurf/ollama-intel-gpu/releases/download/v0.0.1/ollama-0.5.4-ipex-llm-2.2.0b20250220-ubuntu.tgz && mkdir -p /usr/local && tar xvf ollama-0.5.4-ipex-llm-2.2.0b20250220-ubuntu.tgz -C /usr/local && rm ollama-0.5.4-ipex-llm-2.2.0b20250220-ubuntu.tgz && ln -sf /usr/local/ollama-0.5.4-ipex-llm-2.2.0b20250220-ubuntu/ollama /usr/local/bin/ollama && echo -e \"#!/bin/bash\\nexport OLLAMA_HOST=0.0.0.0:11434\\n/usr/local/bin/ollama serve\" > /start-ollama.sh && chmod +x /start-ollama.sh && sh -c \"$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)\" \"\" --unattended && touch /INSTALLED && echo \"Intel GPU setup complete. To start Ollama, run: /start-ollama.sh\" && export OLLAMA_HOST=0.0.0.0:11434 && exec /start-ollama.sh; fi"
        ]
      }
    ]
  }
}'

# Create a service for Ollama
kubectl expose pod ollama-intel-gpu -n ai --port=11434 --target-port=11434 --name=ollama-service

echo "Created Ollama service. You can connect Open WebUI to http://ollama-service.ai.svc.cluster.local:11434"

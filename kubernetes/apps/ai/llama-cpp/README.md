# Llama.cpp Server

This deployment runs a llama.cpp server with Intel GPU acceleration using the SYCL backend.

## Features

- **Intel GPU Acceleration**: Uses Intel GPU with SYCL backend for optimal performance
- **OpenAI-Compatible API**: Provides OpenAI-compatible REST API on port 8080
- **Model Management**: Automatically downloads models from Hugging Face
- **SMB Storage**: Uses SMB storage class for persistent model and config storage
- **Health Checks**: Liveness and readiness probes ensure service availability
- **Automatic Ingress**: Handled by app-template with Homepage integration

## Configuration

### Environment Variables

- `ZES_ENABLE_SYSMAN`: Enable Intel GPU system management
- `GGML_SYCL_DISABLE_GRAPH`: Disable command graph (for compatibility)
- `ONEAPI_DEVICE_SELECTOR`: Intel GPU device selection
- `OMP_NUM_THREADS`: OpenMP thread count
- `MKL_NUM_THREADS`: Intel MKL thread count

### Server Parameters

- **Host**: 0.0.0.0 (all interfaces)
- **Port**: 8080
- **Context Size**: 8192 tokens
- **Threads**: 8
- **GPU Layers**: 35 (for Llama-3.2-3B)
- **Batch Size**: 1024
- **Micro Batch Size**: 512

### Storage

- **Config Storage**: 50Gi SMB volume mounted at `/root/.cache/llama.cpp`
- **Models Storage**: 100Gi SMB volume mounted at `/models`
- **Storage Class**: `smb` (ReadWriteMany access mode)

## Usage

### API Endpoints

The server provides OpenAI-compatible endpoints:

- `GET /v1/models` - List available models
- `POST /v1/chat/completions` - Chat completions
- `POST /v1/completions` - Text completions

### Example Usage

```bash
# List models
curl http://llama-cpp.ai.svc.cluster.local:8080/v1/models

# Chat completion
curl -X POST http://llama-cpp.ai.svc.cluster.local:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "llama-3.2-3b-instruct",
    "messages": [
      {"role": "user", "content": "Hello, how are you?"}
    ]
  }'
```

### Open WebUI Integration

Add the following URL to Open WebUI:
```
http://llama-cpp.ai.svc.cluster.local:8080
```

### External Access

The service is available externally at:
```
https://llama-cpp.${SECRET_DOMAIN}
```

## Dependencies

- Intel Device Plugin (for GPU access)
- SMB CSI Driver (for storage)
- Cert-Manager (for TLS certificates)

## Troubleshooting

### Check Pod Status
```bash
kubectl get pods -n ai -l app.kubernetes.io/name=llama-cpp
```

### View Logs
```bash
kubectl logs -n ai -l app.kubernetes.io/name=llama-cpp
```

### Check GPU Status
```bash
kubectl describe pod -n ai -l app.kubernetes.io/name=llama-cpp
```

### Check Storage
```bash
kubectl get pvc -n ai -l app.kubernetes.io/name=llama-cpp
```

## Performance Tuning

The deployment is optimized for Intel GPUs with:
- Reduced context size for faster inference
- Optimized thread count
- GPU layer allocation
- Batch size tuning

Adjust these parameters in the HelmRelease values for your specific hardware.

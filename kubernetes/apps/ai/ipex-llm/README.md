# IPEX-LLM Deployment

This directory contains the Kubernetes deployment configuration for Intel IPEX-LLM, an optimized LLM inference server for Intel GPUs.

## Overview

IPEX-LLM is Intel's optimized LLM inference library that provides high-performance inference on Intel GPUs using Intel Extension for PyTorch (IPEX). This deployment uses the `app-template` chart from bjw-s to create a StatefulSet with Intel GPU support.

## Configuration

### Image
- **Base Image**: `intel/ipex-llm:latest` - Official Intel IPEX-LLM image with pre-installed dependencies
- **Architecture**: Optimized for Intel GPUs with oneAPI support

### Resources
- **CPU**: 1000m (1 core)
- **Memory**: 32Gi
- **GPU**: 1 Intel GPU (i915)
- **Storage**:
  - Config/Models: 100Gi (CIFS)
  - Temp: 50Gi (CIFS)

### Environment Variables
- `ONEAPI_DEVICE_SELECTOR`: "level_zero:0" - Selects the first Intel GPU
- `IPEX_LLM_NUM_CTX`: "16384" - Context window size
- `IPEX_LLM_DEVICE`: "xpu" - Uses Intel GPU for inference
- `ZES_ENABLE_SYSMAN`: "1" - Enables Intel GPU system management

### Dependencies
- Intel Device Plugin for GPU support
- Intel oneAPI Base Toolkit (pre-installed in image)
- Intel Extension for PyTorch (pre-installed in image)
- IPEX-LLM Python package (pre-installed in image)

## Usage

The service will be available at:
- **Internal**: `ipex-llm.ai.svc.cluster.local:8000`
- **External**: `ipex-llm.your-domain.com` (via ingress)

### API Endpoints
- Chat completion: `POST /v1/chat/completions`
- Model listing: `GET /v1/models`
- Health check: `GET /health`

## Model Management

Models should be placed in the `/models` directory which is mounted as a persistent volume. The service will automatically detect and load available models.

## Server Configuration

The IPEX-LLM server is started with the following optimized settings:
- **Device**: XPU (Intel GPU)
- **Max Batched Tokens**: 4096
- **Max Sequences**: 256
- **Quantization**: Disabled (full precision)

## Troubleshooting

1. **GPU not detected**: Ensure Intel Device Plugin is running and GPU is available
2. **Memory issues**: Increase memory limits if loading large models
3. **Startup failures**: Check logs for Intel GPU environment setup issues

## References

- [IPEX-LLM GitHub](https://github.com/intel/ipex-llm)
- [Intel Extension for PyTorch](https://github.com/intel/intel-extension-for-pytorch)
- [Intel oneAPI](https://www.intel.com/content/www/us/en/developer/tools/oneapi/overview.html)

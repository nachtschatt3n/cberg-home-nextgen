# IPEX-LLM Ollama Deployment

This directory contains the Kubernetes deployment configuration for Intel IPEX-LLM with Ollama, providing optimized LLM inference on Intel GPUs using the Ollama API.

## Overview

This deployment uses Intel's IPEX-LLM inference engine with Ollama, providing high-performance LLM inference on Intel GPUs. Based on the [blog post by Robert Važan](https://blog.machinezoo.com/Ollama_on_Intel_Arc_A380_using_IPEX-LLM), this approach offers better compatibility and easier model management compared to direct IPEX-LLM server usage.

## Configuration

### Image
- **Base Image**: `intelanalytics/ipex-llm-inference-cpp-xpu:latest` - Official Intel IPEX-LLM inference image with Ollama
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
- `OLLAMA_HOST`: "0.0.0.0:11434" - Ollama server host and port
- `OLLAMA_MAX_LOADED_MODELS`: "1" - Maximum loaded models (GPU memory optimization)
- `OLLAMA_NUM_PARALLEL`: "1" - Number of parallel requests
- `ZES_ENABLE_SYSMAN`: "1" - Enables Intel GPU system management
- `USE_XETLA`: "OFF" - Disables XETLA for better compatibility

### Dependencies
- Intel Device Plugin for GPU support
- Intel oneAPI Base Toolkit (pre-installed in image)
- Intel Extension for PyTorch (pre-installed in image)
- IPEX-LLM with Ollama (pre-installed in image)

## Usage

The service will be available at:
- **Internal**: `ipex-llm.ai.svc.cluster.local:11434`
- **External**: `ipex-llm.your-domain.com` (via ingress)

### API Endpoints
- **Ollama API**: Standard Ollama API endpoints
- **Model management**: `GET /api/tags` - List models
- **Chat completion**: `POST /api/generate` - Generate text
- **Model operations**: `POST /api/pull` - Download models

### Model Management

Models can be managed using standard Ollama commands:

```bash
# Pull a model
curl -X POST http://ipex-llm.ai.svc.cluster.local:11434/api/pull -d '{"name": "llama3.1:8b"}'

# List models
curl http://ipex-llm.ai.svc.cluster.local:11434/api/tags

# Generate text
curl -X POST http://ipex-llm.ai.svc.cluster.local:11434/api/generate -d '{"model": "llama3.1:8b", "prompt": "Hello, how are you?"}'
```

## Supported Models

Based on the blog post, the following models work well with 6GB VRAM:

- **llama3.1:8b** with 10K tokens context - Good for article summarization
- **qwen2.5-coder:7b** with 24K context - Effective for coding tasks
- **llama3.2:3b** with 32K context
- **llama3.2:1b** with 128K context

## Performance

Performance benchmarks from the blog post (tokens/second):

- **Prompt Processing**: 250-500 t/s depending on context length
- **Text Generation**: 11-45 t/s depending on model size
- **Context Support**: Up to 128K tokens for smaller models

## Installation Process

The deployment follows this startup sequence:

1. Create Ollama directory structure
2. Initialize Ollama if not already done
3. Set up Intel GPU environment
4. Start Ollama server with IPEX-LLM support

## Troubleshooting

1. **GPU not detected**: Ensure Intel Device Plugin is running and GPU is available
2. **Memory issues**: Reduce `OLLAMA_MAX_LOADED_MODELS` if loading large models
3. **Model loading**: Use `OLLAMA_NUM_PARALLEL=1` for stability
4. **Performance**: Monitor for the slowdown bug mentioned in the blog post

## References

- [Ollama on Intel Arc A380 using IPEX-LLM](https://blog.machinezoo.com/Ollama_on_Intel_Arc_A380_using_IPEX-LLM) - Robert Važan's blog post
- [IPEX-LLM GitHub](https://github.com/intel/ipex-llm)
- [Intel Extension for PyTorch](https://github.com/intel/intel-extension-for-pytorch)
- [Intel oneAPI](https://www.intel.com/content/www/us/en/developer/tools/oneapi/overview.html)

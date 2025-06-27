#!/bin/bash

echo "Testing llama.cpp server connection..."

# Check if the pod is running
echo "1. Checking pod status:"
kubectl get pods -n ai | grep llama-cpp-intel-gpu

echo -e "\n2. Checking pod logs:"
kubectl logs -n ai llama-cpp-intel-gpu --tail=20

echo -e "\n3. Checking service:"
kubectl get services -n ai | grep llama-openai-service

echo -e "\n4. Testing service connectivity from within cluster:"
kubectl run test-connection -n ai --rm -it --image=curlimages/curl -- curl -v http://llama-openai-service.ai.svc.cluster.local:8080/v1/models || echo "Connection failed"

echo -e "\n5. Testing OpenAI-compatible endpoint:"
kubectl run test-openai -n ai --rm -it --image=curlimages/curl -- curl -X POST http://llama-openai-service.ai.svc.cluster.local:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemma-3-1b-it",
    "messages": [{"role": "user", "content": "Hello"}],
    "max_tokens": 50
  }' || echo "OpenAI endpoint test failed"

echo -e "\n6. For Open WebUI, use this URL:"
echo "http://llama-openai-service.ai.svc.cluster.local:8080"
echo "Or if using port-forward:"
echo "kubectl port-forward -n ai llama-cpp-intel-gpu 8080:8080"
echo "Then use: http://localhost:8080"

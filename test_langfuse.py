#!/usr/bin/env python3
"""
Test script to send a trace directly to Langfuse to verify the setup
"""

from langfuse import Langfuse
import time
import json

# Initialize Langfuse client
print("🔄 Initializing Langfuse client...")
langfuse = Langfuse(
    secret_key="sk-lf-6623605a-1589-4066-bfef-09c3b0a37122",
    public_key="pk-lf-330bcf16-742d-4a62-9a79-391d99a6e068",
    host="https://langfuse.uhl.cool"
)

print("✅ Langfuse client initialized")

try:
    # Create a test trace
    print("🔄 Creating test trace...")
    
    trace = langfuse.trace(
        name="test-trace-from-python",
        user_id="test-user-123",
        metadata={
            "test_type": "direct_api_call",
            "timestamp": time.time(),
            "source": "macOS_test_script"
        }
    )
    
    print(f"✅ Trace created with ID: {trace.id}")
    
    # Add a span to the trace
    print("🔄 Adding span to trace...")
    
    span = trace.span(
        name="test-span",
        input={"message": "Hello from direct Python test!"},
        metadata={
            "span_type": "test"
        }
    )
    
    # Simulate some processing time
    time.sleep(0.1)
    
    # End the span with output
    span.end(
        output={"response": "Test completed successfully", "status": "success"}
    )
    
    print("✅ Span completed")
    
    # Add a generation (LLM call simulation)
    print("🔄 Adding generation to trace...")
    
    generation = trace.generation(
        name="test-llm-call",
        model="test-model-gpt-3.5-turbo",
        input=[{"role": "user", "content": "Test message"}],
        output={"role": "assistant", "content": "This is a test response from Langfuse direct API call"},
        usage={
            "prompt_tokens": 10,
            "completion_tokens": 15,
            "total_tokens": 25
        },
        metadata={
            "temperature": 0.7,
            "max_tokens": 100
        }
    )
    
    print("✅ Generation added")
    
    # Flush to ensure everything is sent
    print("🔄 Flushing data to Langfuse...")
    langfuse.flush()
    
    print("✅ All data sent to Langfuse successfully!")
    print(f"🔗 Check your traces at: https://langfuse.uhl.cool/project/cmfmyum5u00060k07hlttj4lw/traces")
    print(f"📊 Trace ID: {trace.id}")
    
except Exception as e:
    print(f"❌ Error: {e}")
    print(f"Error type: {type(e).__name__}")
    import traceback
    traceback.print_exc()
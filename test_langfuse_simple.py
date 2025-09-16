#!/usr/bin/env python3
"""
Simple test script to verify Langfuse trace ingestion
"""

from langfuse import Langfuse
import time
import uuid

# Initialize Langfuse client
print("🔄 Initializing Langfuse client...")
langfuse = Langfuse(
    secret_key="sk-lf-6623605a-1589-4066-bfef-09c3b0a37122",
    public_key="pk-lf-330bcf16-742d-4a62-9a79-391d99a6e068",
    host="https://langfuse.uhl.cool",
    debug=True  # Enable debug mode to see what's happening
)
print("✅ Langfuse client initialized")

try:
    # Generate a unique trace ID
    trace_id = str(uuid.uuid4())
    
    # Create a simple trace
    print("🔄 Creating test trace...")
    trace = langfuse.trace(
        name=f"test-trace-{int(time.time())}",
        id=trace_id
    )
    print(f"✅ Trace created with ID: {trace_id}")
    
    # Update the trace with some data
    trace.update(
        input={"message": "Hello from test script"},
        output={"response": "Test successful"},
        metadata={"test": True, "version": "3.111.0"}
    )
    
    # Force flush
    print("🔄 Flushing to Langfuse...")
    langfuse.flush()
    
    # Give it a moment to complete
    time.sleep(2)
    
    print("✅ Test completed successfully!")
    print(f"🔗 Check trace at: https://langfuse.uhl.cool/project/cmfmyum5u00060k07hlttj4lw/traces/{trace_id}")
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
finally:
    # Always flush before exiting
    langfuse.flush()
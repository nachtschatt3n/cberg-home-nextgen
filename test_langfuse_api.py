#!/usr/bin/env python3
"""
Direct API test for Langfuse trace ingestion using requests
"""

import requests
import json
import uuid
from datetime import datetime
import base64

# Configuration
PUBLIC_KEY = "pk-lf-330bcf16-742d-4a62-9a79-391d99a6e068"
SECRET_KEY = "sk-lf-6623605a-1589-4066-bfef-09c3b0a37122"
HOST = "https://langfuse.uhl.cool"

# Create auth header
auth_string = f"{PUBLIC_KEY}:{SECRET_KEY}"
auth_header = base64.b64encode(auth_string.encode()).decode()

headers = {
    "Authorization": f"Basic {auth_header}",
    "Content-Type": "application/json"
}

# Create trace data
trace_id = str(uuid.uuid4())
timestamp = datetime.utcnow().isoformat() + "Z"

trace_data = {
    "batch": [
        {
            "id": trace_id,
            "type": "trace-create",  # Add the required type field
            "timestamp": timestamp,
            "body": {
                "id": trace_id,
                "timestamp": timestamp,
                "name": f"test-trace-api-{int(datetime.now().timestamp())}",
                "userId": "test-user",
                "metadata": {
                    "test": True,
                    "source": "direct-api",
                    "langfuse_version": "3.111.0"
                },
                "release": "test",
                "version": "1.0.0",
                "sessionId": "test-session-" + str(uuid.uuid4()),
                "input": {
                    "message": "Test input from API"
                },
                "output": {
                    "response": "Test output from API"
                },
                "tags": ["test", "api", "v3.111.0"]
            }
        }
    ],
    "metadata": {
        "batch_size": 1,
        "sdk_version": "python",
        "sdk_name": "langfuse-python"
    }
}

print(f"🔄 Sending trace to Langfuse API...")
print(f"   Endpoint: {HOST}/api/public/ingestion")
print(f"   Trace ID: {trace_id}")

try:
    response = requests.post(
        f"{HOST}/api/public/ingestion",
        headers=headers,
        json=trace_data,
        timeout=10
    )
    
    print(f"📊 Response Status: {response.status_code}")
    print(f"📊 Response Headers: {dict(response.headers)}")
    
    if response.status_code in [200, 201, 202, 207]:
        print("✅ Trace sent successfully!")
        print(f"🔗 View trace at: {HOST}/project/cmfmyum5u00060k07hlttj4lw/traces/{trace_id}")
        
        try:
            response_data = response.json()
            print(f"📊 Response Body: {json.dumps(response_data, indent=2)}")
        except:
            print(f"📊 Response Body (text): {response.text}")
    else:
        print(f"❌ Failed to send trace")
        print(f"📊 Response Body: {response.text}")
        
except requests.exceptions.RequestException as e:
    print(f"❌ Request error: {e}")
except Exception as e:
    print(f"❌ Unexpected error: {e}")
    import traceback
    traceback.print_exc()
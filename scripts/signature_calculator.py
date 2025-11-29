#!/usr/bin/env python3
"""
Signature calculation script that matches your middleware implementation
"""

import hashlib
import hmac
import json

def calculate_instagram_signature(payload, app_secret):
    """
    Calculate signature exactly like your middleware does
    """
    # Convert payload to bytes (your middleware expects body as bytes)
    if isinstance(payload, dict):
        body = json.dumps(payload).encode('utf-8')
    else:
        body = payload.encode('utf-8') if isinstance(payload, str) else payload
    
    # Generate SHA256 signature (Instagram's preferred method)
    signature = "sha256=" + hmac.new(
        app_secret.encode(),
        body,
        hashlib.sha256
    ).hexdigest()
    
    return signature

def calculate_instagram_signature_sha1(payload, app_secret):
    """
    Calculate SHA1 signature (fallback method)
    """
    if isinstance(payload, dict):
        body = json.dumps(payload).encode('utf-8')
    else:
        body = payload.encode('utf-8') if isinstance(payload, str) else payload
    
    signature = "sha1=" + hmac.new(
        app_secret.encode(),
        body,
        hashlib.sha1
    ).hexdigest()
    
    return signature

# Your configuration - USE ENVIRONMENT VARIABLE FOR SECURITY!
import os
APP_SECRET = os.getenv("APP_SECRET", "YOUR_APP_SECRET_HERE")

# Test payload
test_payload = {
    "object": "instagram",
    "entry": [
        {
            "id": "test_entry_id",
            "time": 1234567890,
            "changes": [
                {
                    "field": "comments",
                    "value": {
                        "id": "test_comment_id",
                        "from": {
                            "id": "test_user_id",
                            "username": "test_user"
                        },
                        "media": {
                            "id": "test_media_id",
                            "media_product_type": "FEED"
                        },
                        "text": "Test comment",
                        "parent_id": None
                    }
                }
            ]
        }
    ]
}

# Calculate signatures
sha256_sig = calculate_instagram_signature(test_payload, APP_SECRET)
sha1_sig = calculate_instagram_signature_sha1(test_payload, APP_SECRET)

print("Instagram Webhook Signature Calculator")
print("=" * 50)
print(f"App Secret: [REDACTED FOR SECURITY]")
print(f"SHA256 Signature: {sha256_sig}")
print(f"SHA1 Signature: {sha1_sig}")
print("\nFor Postman, use:")
print(f"X-Hub-Signature-256: {sha256_sig}")
print(f"X-Hub-Signature: {sha1_sig}")
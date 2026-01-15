"""Tests for the /webhook endpoint.

These tests verify:
- Valid messages are accepted and stored
- Invalid signatures are rejected
- Duplicate messages are handled (idempotency)
- Invalid data is rejected
- Missing required fields are rejected
"""

import hmac
import hashlib
import json
import pytest
from fastapi.testclient import TestClient
import sys
import os

# Add parent directory to path so we can import from app
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from main import app
from config import settings

# Create test client for making HTTP requests to the app
client = TestClient(app)

# Set test secret for all tests
settings.webhook_secret = "testsecret"


def compute_signature(body: str, secret: str = "testsecret") -> str:
    """Helper function to compute HMAC-SHA256 signature.
    
    Computes the same signature that clients should send in X-Signature header.
    
    Args:
        body: JSON string to sign (raw request body)
        secret: Secret key for HMAC
        
    Returns:
        Hex string signature
    """
    return hmac.new(
        secret.encode(),  # Convert secret to bytes
        body.encode(),  # Convert body to bytes
        hashlib.sha256  # Use SHA256 algorithm
    ).hexdigest()  # Return as hex string


def test_webhook_valid_message():
    """Test that a valid message with correct signature is accepted.
    
    This test verifies the happy path:
    - Valid message structure
    - Correct signature
    - Should return 200 OK
    """
    # Create a valid message body
    body = json.dumps({
        "message_id": "test1",
        "from": "+919876543210",
        "to": "+14155550100",
        "ts": "2025-01-15T10:00:00Z",
        "text": "Hello"
    })
    
    # Compute correct signature for this body
    signature = compute_signature(body)
    
    # Send POST request to /webhook endpoint
    response = client.post(
        "/webhook",
        content=body,  # Send body as string (not JSON)
        headers={
            "Content-Type": "application/json",
            "X-Signature": signature  # Add signature header
        }
    )
    
    # Verify response
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_webhook_duplicate_message():
    """Test that duplicate messages are handled idempotently.
    
    Idempotency means:
    - Sending the same request twice should have same effect as sending once
    - Both requests should return 200 OK
    - Message should only be stored once
    """
    # Create a message body
    body = json.dumps({
        "message_id": "test2",  # Same message_id as before
        "from": "+919876543210",
        "to": "+14155550100",
        "ts": "2025-01-15T10:00:00Z",
        "text": "Duplicate test"
    })
    
    # Compute signature
    signature = compute_signature(body)
    
    # Prepare headers for both requests
    headers = {
        "Content-Type": "application/json",
        "X-Signature": signature
    }
    
    # First request - inserts the message
    response1 = client.post("/webhook", content=body, headers=headers)
    assert response1.status_code == 200
    
    # Duplicate request - should also return 200 (not 409 Conflict or error)
    response2 = client.post("/webhook", content=body, headers=headers)
    assert response2.status_code == 200
    assert response2.json() == {"status": "ok"}
    
    # Verify by checking /messages endpoint that message appears once
    # (This would be in another test - here we just verify idempotency)


def test_webhook_invalid_signature():
    """Test that requests with invalid signatures are rejected.
    
    This is a security test - ensures only authorized clients can send webhooks.
    """
    # Create a message body
    body = json.dumps({
        "message_id": "test3",
        "from": "+919876543210",
        "to": "+14155550100",
        "ts": "2025-01-15T10:00:00Z",
        "text": "Test"
    })
    
    # Send request with WRONG signature
    response = client.post(
        "/webhook",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Signature": "invalidsignature"  # This is not the correct signature
        }
    )
    
    # Should return 401 Unauthorized
    assert response.status_code == 401
    assert response.json() == {"detail": "invalid signature"}


def test_webhook_missing_signature():
    """Test that requests without signature are rejected."""
    body = json.dumps({
        "message_id": "test4",
        "from": "+919876543210",
        "to": "+14155550100",
        "ts": "2025-01-15T10:00:00Z",
        "text": "Test"
    })
    
    # Send request WITHOUT X-Signature header
    response = client.post(
        "/webhook",
        content=body,
        headers={"Content-Type": "application/json"}
    )
    
    # Should return 401 because signature is missing/invalid
    assert response.status_code == 401


def test_webhook_invalid_phone_format():
    """Test that invalid phone numbers are rejected.
    
    Phone numbers must be in E.164 format: + followed by digits
    """
    body = json.dumps({
        "message_id": "test5",
        "from": "919876543210",  # Missing + prefix
        "to": "+14155550100",
        "ts": "2025-01-15T10:00:00Z",
        "text": "Test"
    })
    
    signature = compute_signature(body)
    
    response = client.post(
        "/webhook",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Signature": signature
        }
    )
    
    # Should return 422 Unprocessable Entity (validation error)
    assert response.status_code == 422


def test_webhook_invalid_timestamp():
    """Test that invalid timestamps are rejected.
    
    Timestamps must be ISO-8601 UTC format, ending with 'Z'
    """
    body = json.dumps({
        "message_id": "test6",
        "from": "+919876543210",
        "to": "+14155550100",
        "ts": "2025-01-15T10:00:00",  # Missing 'Z' at end
        "text": "Test"
    })
    
    signature = compute_signature(body)
    
    response = client.post(
        "/webhook",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Signature": signature
        }
    )
    
    # Should return 422 Unprocessable Entity
    assert response.status_code == 422


def test_webhook_missing_required_field():
    """Test that missing required fields are rejected."""
    body = json.dumps({
        # Missing message_id - required field
        "from": "+919876543210",
        "to": "+14155550100",
        "ts": "2025-01-15T10:00:00Z"
    })
    
    signature = compute_signature(body)
    
    response = client.post(
        "/webhook",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Signature": signature
        }
    )
    
    # Should return 422 Unprocessable Entity
    assert response.status_code == 422


def test_webhook_optional_text_field():
    """Test that text field is optional.
    
    Message can be stored without text content.
    """
    body = json.dumps({
        "message_id": "test7",
        "from": "+919876543210",
        "to": "+14155550100",
        "ts": "2025-01-15T10:00:00Z"
        # No text field provided
    })
    
    signature = compute_signature(body)
    
    response = client.post(
        "/webhook",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Signature": signature
        }
    )
    
    # Should still return 200 OK
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_webhook_missing_signature():
    """Test missing signature header"""
    body = json.dumps({
        "message_id": "test4",
        "from": "+919876543210",
        "to": "+14155550100",
        "ts": "2025-01-15T10:00:00Z",
        "text": "Test"
    })
    
    response = client.post(
        "/webhook",
        content=body,
        headers={"Content-Type": "application/json"}
    )
    
    assert response.status_code == 401


def test_webhook_invalid_phone_format():
    """Test E.164 validation"""
    body = json.dumps({
        "message_id": "test5",
        "from": "919876543210",  # Missing +
        "to": "+14155550100",
        "ts": "2025-01-15T10:00:00Z",
        "text": "Test"
    })
    signature = compute_signature(body)
    
    response = client.post(
        "/webhook",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Signature": signature
        }
    )
    
    assert response.status_code == 422


def test_webhook_invalid_timestamp():
    """Test timestamp validation"""
    body = json.dumps({
        "message_id": "test6",
        "from": "+919876543210",
        "to": "+14155550100",
        "ts": "2025-01-15T10:00:00",  # Missing Z
        "text": "Test"
    })
    signature = compute_signature(body)
    
    response = client.post(
        "/webhook",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Signature": signature
        }
    )
    
    assert response.status_code == 422


def test_webhook_text_optional():
    """Test that text field is optional"""
    body = json.dumps({
        "message_id": "test7",
        "from": "+919876543210",
        "to": "+14155550100",
        "ts": "2025-01-15T10:00:00Z"
    })
    signature = compute_signature(body)
    
    response = client.post(
        "/webhook",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Signature": signature
        }
    )
    
    assert response.status_code == 200
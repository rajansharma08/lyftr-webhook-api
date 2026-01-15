import hmac
import hashlib
import json
import pytest
from fastapi.testclient import TestClient
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from main import app
from config import settings

client = TestClient(app)
settings.webhook_secret = "testsecret"


def compute_signature(body: str) -> str:
    return hmac.new(
        "testsecret".encode(),
        body.encode(),
        hashlib.sha256
    ).hexdigest()


def insert_test_message(message_id: str, from_num: str, ts: str, text: str):
    """Helper to insert test messages"""
    body = json.dumps({
        "message_id": message_id,
        "from": from_num,
        "to": "+14155550100",
        "ts": ts,
        "text": text
    })
    signature = compute_signature(body)
    
    client.post(
        "/webhook",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Signature": signature
        }
    )


def test_messages_basic_list():
    """Test basic message listing"""
    # Insert test messages
    insert_test_message("msg1", "+911111111111", "2025-01-15T09:00:00Z", "First")
    insert_test_message("msg2", "+912222222222", "2025-01-15T10:00:00Z", "Second")
    
    response = client.get("/messages")
    
    assert response.status_code == 200
    data = response.json()
    assert "data" in data
    assert "total" in data
    assert "limit" in data
    assert "offset" in data
    assert data["limit"] == 50
    assert data["offset"] == 0


def test_messages_pagination():
    """Test pagination with limit and offset"""
    # Insert multiple messages
    for i in range(5):
        insert_test_message(
            f"page{i}",
            "+913333333333",
            f"2025-01-15T{10+i:02d}:00:00Z",
            f"Message {i}"
        )
    
    # First page
    response = client.get("/messages?limit=2&offset=0")
    data = response.json()
    assert len(data["data"]) <= 2
    assert data["limit"] == 2
    assert data["offset"] == 0
    
    # Second page
    response = client.get("/messages?limit=2&offset=2")
    data = response.json()
    assert data["offset"] == 2


def test_messages_filter_by_sender():
    """Test filtering by sender"""
    sender = "+914444444444"
    insert_test_message("filter1", sender, "2025-01-15T11:00:00Z", "Test 1")
    insert_test_message("filter2", "+915555555555", "2025-01-15T11:01:00Z", "Test 2")
    
    response = client.get(f"/messages?from={sender}")
    data = response.json()
    
    # All returned messages should be from the specified sender
    for msg in data["data"]:
        assert msg["from"] == sender


def test_messages_filter_by_since():
    """Test filtering by timestamp"""
    insert_test_message("time1", "+916666666666", "2025-01-15T08:00:00Z", "Early")
    insert_test_message("time2", "+916666666666", "2025-01-15T12:00:00Z", "Late")
    
    response = client.get("/messages?since=2025-01-15T10:00:00Z")
    data = response.json()
    
    # All messages should be after the since timestamp
    for msg in data["data"]:
        assert msg["ts"] >= "2025-01-15T10:00:00Z"


def test_messages_text_search():
    """Test text search"""
    insert_test_message("search1", "+917777777777", "2025-01-15T13:00:00Z", "Hello World")
    insert_test_message("search2", "+917777777777", "2025-01-15T13:01:00Z", "Goodbye")
    
    response = client.get("/messages?q=Hello")
    data = response.json()
    
    # Should only return messages containing "Hello"
    for msg in data["data"]:
        if msg["text"]:
            assert "Hello" in msg["text"] or "hello" in msg["text"].lower()


def test_messages_ordering():
    """Test that messages are ordered by ts ASC, message_id ASC"""
    insert_test_message("order1", "+918888888888", "2025-01-15T14:00:00Z", "A")
    insert_test_message("order2", "+918888888888", "2025-01-15T14:00:00Z", "B")
    insert_test_message("order3", "+918888888888", "2025-01-15T14:01:00Z", "C")
    
    response = client.get("/messages?from=+918888888888")
    data = response.json()
    
    messages = data["data"]
    
    # Check ordering
    for i in range(len(messages) - 1):
        curr = messages[i]
        next_msg = messages[i + 1]
        
        # Current ts should be <= next ts
        assert curr["ts"] <= next_msg["ts"]
        
        # If same ts, message_id should be in order
        if curr["ts"] == next_msg["ts"]:
            assert curr["message_id"] <= next_msg["message_id"]


def test_messages_limit_bounds():
    """Test limit parameter bounds"""
    # Max limit
    response = client.get("/messages?limit=100")
    assert response.status_code == 200
    
    # Exceeds max (should be handled by validation)
    response = client.get("/messages?limit=200")
    assert response.status_code == 422
    
    # Min limit
    response = client.get("/messages?limit=1")
    assert response.status_code == 200
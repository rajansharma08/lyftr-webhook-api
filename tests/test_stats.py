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


def test_stats_empty():
    """Test stats with no messages"""
    response = client.get("/stats")
    
    assert response.status_code == 200
    data = response.json()
    
    assert "total_messages" in data
    assert "senders_count" in data
    assert "messages_per_sender" in data
    assert "first_message_ts" in data
    assert "last_message_ts" in data


def test_stats_basic():
    """Test basic stats calculation"""
    # Insert test messages
    insert_test_message("stats1", "+911111111111", "2025-01-15T09:00:00Z", "A")
    insert_test_message("stats2", "+911111111111", "2025-01-15T10:00:00Z", "B")
    insert_test_message("stats3", "+912222222222", "2025-01-15T11:00:00Z", "C")
    
    response = client.get("/stats")
    data = response.json()
    
    assert data["total_messages"] >= 3
    assert data["senders_count"] >= 2
    assert len(data["messages_per_sender"]) >= 2


def test_stats_messages_per_sender():
    """Test messages per sender calculation"""
    sender1 = "+913333333333"
    sender2 = "+914444444444"
    
    # Insert messages from different senders
    for i in range(5):
        insert_test_message(f"sender1_{i}", sender1, f"2025-01-15T{12+i:02d}:00:00Z", f"Msg {i}")
    
    for i in range(3):
        insert_test_message(f"sender2_{i}", sender2, f"2025-01-15T{17+i:02d}:00:00Z", f"Msg {i}")
    
    response = client.get("/stats")
    data = response.json()
    
    # Find our senders in the top senders list
    sender1_count = next((s["count"] for s in data["messages_per_sender"] if s["from"] == sender1), 0)
    sender2_count = next((s["count"] for s in data["messages_per_sender"] if s["from"] == sender2), 0)
    
    assert sender1_count >= 5
    assert sender2_count >= 3


def test_stats_timestamp_bounds():
    """Test first and last message timestamps"""
    # Insert messages with known timestamps
    early_ts = "2025-01-15T06:00:00Z"
    late_ts = "2025-01-15T23:00:00Z"
    
    insert_test_message("early", "+915555555555", early_ts, "Early")
    insert_test_message("late", "+915555555555", late_ts, "Late")
    
    response = client.get("/stats")
    data = response.json()
    
    # First message should be <= our early timestamp
    assert data["first_message_ts"] <= early_ts
    
    # Last message should be >= our late timestamp
    assert data["last_message_ts"] >= late_ts


def test_stats_top_senders_limit():
    """Test that messages_per_sender returns max 10 senders"""
    # Insert messages from many senders
    for i in range(15):
        sender = f"+9100000000{i:02d}"
        insert_test_message(f"many_{i}", sender, f"2025-01-16T{10:02d}:{i:02d}:00Z", f"Test {i}")
    
    response = client.get("/stats")
    data = response.json()
    
    # Should return at most 10 senders
    assert len(data["messages_per_sender"]) <= 10


def test_stats_sender_ordering():
    """Test that senders are ordered by count descending"""
    sender_a = "+916666666666"
    sender_b = "+917777777777"
    
    # Sender A sends 10 messages
    for i in range(10):
        insert_test_message(f"a_{i}", sender_a, f"2025-01-17T{10:02d}:{i:02d}:00Z", f"A{i}")
    
    # Sender B sends 5 messages
    for i in range(5):
        insert_test_message(f"b_{i}", sender_b, f"2025-01-17T{11:02d}:{i:02d}:00Z", f"B{i}")
    
    response = client.get("/stats")
    data = response.json()
    
    # Find positions
    sender_a_pos = next((i for i, s in enumerate(data["messages_per_sender"]) if s["from"] == sender_a), None)
    sender_b_pos = next((i for i, s in enumerate(data["messages_per_sender"]) if s["from"] == sender_b), None)
    
    if sender_a_pos is not None and sender_b_pos is not None:
        # Sender A (more messages) should appear before Sender B
        assert sender_a_pos < sender_b_pos
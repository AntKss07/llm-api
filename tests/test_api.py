"""
test_api.py — Tests for Flask API endpoints.

Covers HTTP status codes, JSON response shapes, and error handling.
The Gemini API is mocked; no real API calls are made.
"""

import json
import pytest


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


def test_health_ok(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    data = r.get_json()
    assert data["status"] == "ok"
    assert data["healthy"] is True
    assert "model" in data


# ---------------------------------------------------------------------------
# Conversation CRUD
# ---------------------------------------------------------------------------


def test_list_conversations_empty(client):
    r = client.get("/api/conversations")
    assert r.status_code == 200
    data = r.get_json()
    assert data["conversations"] == []


def test_create_conversation_default_title(client):
    r = client.post(
        "/api/conversations",
        json={},
        content_type="application/json",
    )
    assert r.status_code == 201
    data = r.get_json()
    convo = data["conversation"]
    assert "id" in convo
    assert convo["title"] == "New Conversation"


def test_create_conversation_custom_title(client):
    r = client.post(
        "/api/conversations",
        json={"title": "My Study Session"},
        content_type="application/json",
    )
    assert r.status_code == 201
    data = r.get_json()
    assert data["conversation"]["title"] == "My Study Session"


def test_list_conversations_after_create(client):
    client.post("/api/conversations", json={}, content_type="application/json")
    client.post("/api/conversations", json={}, content_type="application/json")
    r = client.get("/api/conversations")
    assert r.status_code == 200
    assert len(r.get_json()["conversations"]) == 2


def test_get_conversation_not_found(client):
    fake_id = "00000000-0000-0000-0000-000000000000"
    r = client.get(f"/api/conversations/{fake_id}")
    assert r.status_code == 404


def test_get_conversation_invalid_id_format(client):
    r = client.get("/api/conversations/not-a-uuid-at-all")
    assert r.status_code == 400


def test_get_conversation_with_messages(client, mock_llm):
    # Create a conversation via chat
    r = client.post(
        "/api/chat",
        json={"message": "Hello"},
        content_type="application/json",
    )
    assert r.status_code == 200
    conv_id = r.get_json()["conversation_id"]

    r2 = client.get(f"/api/conversations/{conv_id}")
    assert r2.status_code == 200
    data = r2.get_json()
    assert len(data["conversation"]["messages"]) == 2  # user + assistant


def test_rename_conversation(client):
    r = client.post("/api/conversations", json={}, content_type="application/json")
    conv_id = r.get_json()["conversation"]["id"]

    r2 = client.patch(
        f"/api/conversations/{conv_id}",
        json={"title": "Renamed Title"},
        content_type="application/json",
    )
    assert r2.status_code == 200
    assert r2.get_json()["conversation"]["title"] == "Renamed Title"


def test_rename_conversation_empty_title(client):
    r = client.post("/api/conversations", json={}, content_type="application/json")
    conv_id = r.get_json()["conversation"]["id"]

    r2 = client.patch(
        f"/api/conversations/{conv_id}",
        json={"title": "   "},
        content_type="application/json",
    )
    assert r2.status_code == 400


def test_rename_conversation_not_found(client):
    fake_id = "00000000-0000-0000-0000-000000000000"
    r = client.patch(
        f"/api/conversations/{fake_id}",
        json={"title": "Title"},
        content_type="application/json",
    )
    assert r.status_code == 404


def test_delete_conversation(client):
    r = client.post("/api/conversations", json={}, content_type="application/json")
    conv_id = r.get_json()["conversation"]["id"]

    r2 = client.delete(f"/api/conversations/{conv_id}")
    assert r2.status_code == 200

    r3 = client.get(f"/api/conversations/{conv_id}")
    assert r3.status_code == 404


def test_delete_conversation_not_found(client):
    fake_id = "00000000-0000-0000-0000-000000000000"
    r = client.delete(f"/api/conversations/{fake_id}")
    assert r.status_code == 404


def test_delete_conversation_removes_messages(client, mock_llm):
    # Send a message to create conversation + messages
    r = client.post(
        "/api/chat",
        json={"message": "Will be deleted"},
        content_type="application/json",
    )
    conv_id = r.get_json()["conversation_id"]

    # Verify messages exist
    r2 = client.get(f"/api/conversations/{conv_id}")
    assert len(r2.get_json()["conversation"]["messages"]) == 2

    # Delete conversation
    client.delete(f"/api/conversations/{conv_id}")

    # Conversation should be gone
    r3 = client.get(f"/api/conversations/{conv_id}")
    assert r3.status_code == 404


# ---------------------------------------------------------------------------
# Chat endpoint
# ---------------------------------------------------------------------------


def test_chat_valid_message(client, mock_llm):
    r = client.post(
        "/api/chat",
        json={"message": "Hello, world!"},
        content_type="application/json",
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["status"] == "ok"
    assert "conversation_id" in data
    assert "reply" in data
    assert isinstance(data["context_messages_used"], int)


def test_chat_empty_message(client, mock_llm):
    r = client.post(
        "/api/chat",
        json={"message": ""},
        content_type="application/json",
    )
    assert r.status_code == 400
    assert r.get_json()["code"] == "empty_message"


def test_chat_whitespace_message(client, mock_llm):
    r = client.post(
        "/api/chat",
        json={"message": "   "},
        content_type="application/json",
    )
    assert r.status_code == 400


def test_chat_missing_message_key(client, mock_llm):
    r = client.post(
        "/api/chat",
        json={},
        content_type="application/json",
    )
    assert r.status_code == 400


def test_chat_message_too_long(client, mock_llm):
    import config
    long_msg = "x" * (config.MAX_MESSAGE_LENGTH + 1)
    r = client.post(
        "/api/chat",
        json={"message": long_msg},
        content_type="application/json",
    )
    assert r.status_code == 400
    assert r.get_json()["code"] == "message_too_long"


def test_chat_invalid_json(client):
    r = client.post(
        "/api/chat",
        data="not json",
        content_type="application/json",
    )
    assert r.status_code == 400


def test_chat_invalid_conversation_id(client, mock_llm):
    r = client.post(
        "/api/chat",
        json={"message": "Hello", "conversation_id": "not-a-uuid"},
        content_type="application/json",
    )
    assert r.status_code == 400


def test_chat_unknown_conversation_id(client, mock_llm):
    fake_id = "00000000-0000-0000-0000-000000000000"
    r = client.post(
        "/api/chat",
        json={"message": "Hello", "conversation_id": fake_id},
        content_type="application/json",
    )
    assert r.status_code == 404


def test_chat_creates_new_conversation_when_no_id(client, mock_llm):
    r = client.post(
        "/api/chat",
        json={"message": "Start fresh"},
        content_type="application/json",
    )
    assert r.status_code == 200
    conv_id = r.get_json()["conversation_id"]
    assert conv_id  # must be a non-empty UUID string

    # Verify it was persisted
    r2 = client.get(f"/api/conversations/{conv_id}")
    assert r2.status_code == 200


def test_chat_missing_api_key(client, monkeypatch):
    import config as cfg
    monkeypatch.setattr(cfg, "GEMINI_API_KEY", None)

    r = client.post(
        "/api/chat",
        json={"message": "Hello"},
        content_type="application/json",
    )
    assert r.status_code == 500
    assert r.get_json()["code"] == "missing_api_key"


def test_chat_api_auth_failure(client, monkeypatch):
    import llm_service

    def _auth_fail(*args, **kwargs):
        return {
            "reply": None,
            "context_messages_used": 0,
            "error": {
                "code": "auth_failure",
                "message": "Invalid API key.",
                "http_status": 401,
            },
        }

    monkeypatch.setattr(llm_service, "generate_reply", _auth_fail)
    r = client.post(
        "/api/chat",
        json={"message": "Hello"},
        content_type="application/json",
    )
    assert r.status_code == 401
    assert r.get_json()["code"] == "auth_failure"


def test_chat_rate_limit(client, monkeypatch):
    import llm_service

    def _rate_limit(*args, **kwargs):
        return {
            "reply": None,
            "context_messages_used": 0,
            "error": {
                "code": "rate_limit",
                "message": "API quota exhausted.",
                "http_status": 429,
            },
        }

    monkeypatch.setattr(llm_service, "generate_reply", _rate_limit)
    r = client.post(
        "/api/chat",
        json={"message": "Hello"},
        content_type="application/json",
    )
    assert r.status_code == 429


def test_chat_timeout(client, monkeypatch):
    import llm_service

    def _timeout(*args, **kwargs):
        return {
            "reply": None,
            "context_messages_used": 0,
            "error": {
                "code": "timeout",
                "message": "Request timed out.",
                "http_status": 504,
            },
        }

    monkeypatch.setattr(llm_service, "generate_reply", _timeout)
    r = client.post(
        "/api/chat",
        json={"message": "Hello"},
        content_type="application/json",
    )
    assert r.status_code == 504


def test_chat_empty_llm_response(client, monkeypatch):
    import llm_service

    def _empty(*args, **kwargs):
        return {
            "reply": None,
            "context_messages_used": 0,
            "error": {
                "code": "empty_response",
                "message": "The AI returned an empty response.",
                "http_status": 502,
            },
        }

    monkeypatch.setattr(llm_service, "generate_reply", _empty)
    r = client.post(
        "/api/chat",
        json={"message": "Hello"},
        content_type="application/json",
    )
    assert r.status_code == 502


# ---------------------------------------------------------------------------
# 404 / 405 handlers
# ---------------------------------------------------------------------------


def test_404_handler(client):
    r = client.get("/api/nonexistent")
    assert r.status_code == 404
    assert r.get_json()["status"] == "error"


def test_405_handler(client):
    r = client.delete("/api/chat")
    assert r.status_code == 405


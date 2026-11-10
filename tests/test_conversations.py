"""
test_conversations.py — Tests for conversation management and memory.

Verifies multi-turn context, isolation between conversations, and
persistence across simulated "restarts".
"""

import pytest


# ---------------------------------------------------------------------------
# Multi-turn conversation memory
# ---------------------------------------------------------------------------


def test_multi_turn_context_preserved(client, monkeypatch):
    """History from previous turns is passed to the LLM on subsequent turns."""
    import llm_service

    received_histories = []

    def _capture_history(new_user_message, history_messages, max_context_messages=None):
        received_histories.append(list(history_messages))
        return {
            "reply": f"Echo: {new_user_message}",
            "context_messages_used": len(history_messages),
            "error": None,
        }

    monkeypatch.setattr(llm_service, "generate_reply", _capture_history)

    # Turn 1
    r1 = client.post("/api/chat", json={"message": "My name is Alex."}, content_type="application/json")
    assert r1.status_code == 200
    conv_id = r1.get_json()["conversation_id"]

    # Turn 2
    r2 = client.post(
        "/api/chat",
        json={"message": "I study CS.", "conversation_id": conv_id},
        content_type="application/json",
    )
    assert r2.status_code == 200

    # Turn 3
    r3 = client.post(
        "/api/chat",
        json={"message": "What is my name?", "conversation_id": conv_id},
        content_type="application/json",
    )
    assert r3.status_code == 200

    # By turn 3, the history passed to the LLM should contain 4 messages
    # (user+assistant from turns 1 and 2)
    assert len(received_histories[2]) == 4


def test_conversation_isolation(client, monkeypatch):
    """Messages from one conversation must not appear in another."""
    import llm_service

    histories_by_call: list[list] = []

    def _capture(new_user_message, history_messages, max_context_messages=None):
        histories_by_call.append(list(history_messages))
        return {
            "reply": "OK",
            "context_messages_used": len(history_messages),
            "error": None,
        }

    monkeypatch.setattr(llm_service, "generate_reply", _capture)

    # Conversation A
    r_a = client.post("/api/chat", json={"message": "I am Alice."}, content_type="application/json")
    conv_a = r_a.get_json()["conversation_id"]

    # Conversation B — first message should have empty history
    r_b = client.post("/api/chat", json={"message": "I am Bob."}, content_type="application/json")
    conv_b = r_b.get_json()["conversation_id"]

    assert conv_a != conv_b

    # The history passed on conv_b's first turn must be empty (no Alice)
    history_for_bob = histories_by_call[1]
    contents = [m["content"] for m in history_for_bob]
    assert all("Alice" not in c for c in contents)


def test_messages_persist_across_restarts(client, mock_llm, tmp_db):
    """Messages stored in SQLite survive simulated backend restarts."""
    import database as db_module
    from app import create_app

    # First "session"
    app1 = create_app(db_path=tmp_db)
    app1.config["TESTING"] = True
    client1 = app1.test_client()

    r = client1.post("/api/chat", json={"message": "Remember me?"}, content_type="application/json")
    assert r.status_code == 200
    conv_id = r.get_json()["conversation_id"]

    # Second "session" — same DB, new Flask app instance
    app2 = create_app(db_path=tmp_db)
    app2.config["TESTING"] = True
    client2 = app2.test_client()

    r2 = client2.get(f"/api/conversations/{conv_id}")
    assert r2.status_code == 200
    msgs = r2.get_json()["conversation"]["messages"]
    assert len(msgs) == 2  # user + assistant


def test_failed_llm_does_not_persist_messages(client, monkeypatch, tmp_db):
    """
    If the LLM call fails, neither the user message nor an assistant message
    should be saved in the database.
    """
    import llm_service
    import database as db_module

    def _fail(*args, **kwargs):
        return {
            "reply": None,
            "context_messages_used": 0,
            "error": {"code": "api_error", "message": "Oops", "http_status": 502},
        }

    monkeypatch.setattr(llm_service, "generate_reply", _fail)

    # First get a valid conversation
    r_conv = client.post("/api/conversations", json={}, content_type="application/json")
    conv_id = r_conv.get_json()["conversation"]["id"]

    # Attempt to chat (will fail)
    r = client.post(
        "/api/chat",
        json={"message": "Will this be saved?", "conversation_id": conv_id},
        content_type="application/json",
    )
    assert r.status_code == 502

    # Check DB — no messages should exist
    messages = db_module.get_messages(conv_id)
    assert messages == []


def test_reference_earlier_turns(client, monkeypatch):
    """
    Simulate a user referencing information from two turns back.
    The LLM mock echoes the history it receives — we verify the
    history slice contains the earlier message.
    """
    import llm_service

    received_histories = []

    def _echo_history(new_user_message, history_messages, max_context_messages=None):
        received_histories.append(list(history_messages))
        return {
            "reply": f"History length: {len(history_messages)}",
            "context_messages_used": len(history_messages),
            "error": None,
        }

    monkeypatch.setattr(llm_service, "generate_reply", _echo_history)

    messages = [
        "My name is Alex.",
        "I am a CS student.",
        "My favourite language is Python.",
        "What is my name?",
        "What language do I like?",
    ]
    conv_id = None
    for msg in messages:
        payload = {"message": msg}
        if conv_id:
            payload["conversation_id"] = conv_id
        r = client.post("/api/chat", json=payload, content_type="application/json")
        assert r.status_code == 200
        conv_id = r.get_json()["conversation_id"]

    # By turn 5, the history sent to LLM should have 8 messages
    # (4 complete turns × 2 messages each)
    assert len(received_histories[4]) == 8


def test_no_duplicate_messages_on_retry(client, monkeypatch, tmp_db):
    """
    If the first call fails and the user retries with the same message,
    history should contain exactly one user+assistant pair after success.
    """
    import llm_service
    import database as db_module

    call_count = {"n": 0}

    def _fail_first_then_succeed(new_user_message, history_messages, max_context_messages=None):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return {
                "reply": None,
                "context_messages_used": 0,
                "error": {"code": "timeout", "message": "Timed out", "http_status": 504},
            }
        return {
            "reply": "Second attempt success",
            "context_messages_used": len(history_messages),
            "error": None,
        }

    monkeypatch.setattr(llm_service, "generate_reply", _fail_first_then_succeed)

    # Create conversation
    r_conv = client.post("/api/conversations", json={}, content_type="application/json")
    conv_id = r_conv.get_json()["conversation"]["id"]

    # First attempt — fails
    r1 = client.post(
        "/api/chat",
        json={"message": "Hello", "conversation_id": conv_id},
        content_type="application/json",
    )
    assert r1.status_code == 504

    # Second attempt — succeeds
    r2 = client.post(
        "/api/chat",
        json={"message": "Hello", "conversation_id": conv_id},
        content_type="application/json",
    )
    assert r2.status_code == 200

    # Should have exactly 2 messages (1 user + 1 assistant)
    messages = db_module.get_messages(conv_id)
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[1]["role"] == "assistant"


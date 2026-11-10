"""
test_context.py — Tests for context window management and truncation.

Verifies that:
  - Only the most recent N messages are sent to the LLM.
  - The full history is preserved in SQLite.
  - Edge cases (very small N, odd/even counts) are handled correctly.
  - The truncated slice does not start with an assistant message.
"""

import pytest
import os


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _send_n_messages(client, n: int, monkeypatch) -> str:
    """
    Send n messages to a new conversation and return the conversation_id.
    Uses a mock that records the history it receives.
    """
    import llm_service

    def _mock(new_user_message, history_messages, max_context_messages=None):
        return {
            "reply": f"Response {len(history_messages) // 2 + 1}",
            "context_messages_used": len(history_messages),
            "error": None,
        }

    monkeypatch.setattr(llm_service, "generate_reply", _mock)

    conv_id = None
    for i in range(n):
        payload = {"message": f"Message {i + 1}"}
        if conv_id:
            payload["conversation_id"] = conv_id
        r = client.post("/api/chat", json=payload, content_type="application/json")
        assert r.status_code == 200
        conv_id = r.get_json()["conversation_id"]
    return conv_id


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_context_truncation_sends_only_recent_messages(client, monkeypatch):
    """When history exceeds MAX_CONTEXT_MESSAGES, only the recent N are sent to Gemini."""
    import llm_service
    import config as cfg
    from llm_service import build_context

    # Use a very small context window
    monkeypatch.setattr(cfg, "MAX_CONTEXT_MESSAGES", 4)

    # Track what build_context returns (this is what the SDK actually sees)
    truncated_slices = []
    _original_build_context = llm_service.build_context

    def _capturing_build_context(history_messages, max_context_messages):
        result = _original_build_context(history_messages, max_context_messages)
        truncated_slices.append(list(result))
        return result

    monkeypatch.setattr(llm_service, "build_context", _capturing_build_context)

    def _mock_generate(new_user_message, history_messages, max_context_messages=None):
        return {
            "reply": "OK",
            "context_messages_used": max_context_messages or cfg.MAX_CONTEXT_MESSAGES,
            "error": None,
        }

    monkeypatch.setattr(llm_service, "generate_reply", _mock_generate)

    # Send 6 messages — 5 complete pairs before the 6th, context window is 4
    conv_id = None
    for i in range(6):
        payload = {"message": f"Turn {i + 1}"}
        if conv_id:
            payload["conversation_id"] = conv_id
        r = client.post("/api/chat", json=payload, content_type="application/json")
        assert r.status_code == 200
        conv_id = r.get_json()["conversation_id"]

    # Directly verify build_context truncation logic using 10 history msgs + window=4
    all_msgs = []
    for i in range(5):
        all_msgs.append({"role": "user", "content": f"User {i}"})
        all_msgs.append({"role": "assistant", "content": f"Assist {i}"})

    truncated = build_context(all_msgs, max_context_messages=4)
    assert len(truncated) <= 4, f"Expected ≤4 messages, got {len(truncated)}: {truncated}"
    assert truncated[0]["role"] == "user"  # never starts with assistant


def test_full_history_preserved_in_sqlite(client, monkeypatch, tmp_db):
    """Full conversation history is in SQLite even if truncated for the LLM."""
    import llm_service
    import config as cfg
    import database as db_module
    from app import create_app

    n_turns = 6

    # Tiny context window
    monkeypatch.setattr(cfg, "MAX_CONTEXT_MESSAGES", 2)

    def _mock(new_user_message, history_messages, max_context_messages=None):
        return {
            "reply": f"Echo {len(history_messages)}",
            "context_messages_used": len(history_messages),
            "error": None,
        }

    monkeypatch.setattr(llm_service, "generate_reply", _mock)

    conv_id = _send_n_messages(client, n_turns, monkeypatch)

    # Full history should contain 2 * n_turns messages
    all_messages = db_module.get_messages(conv_id)
    assert len(all_messages) == n_turns * 2


def test_truncation_strategy_in_llm_service():
    """Unit-test the build_context function directly."""
    from llm_service import build_context

    messages = []
    for i in range(10):
        messages.append({"role": "user", "content": f"User {i}"})
        messages.append({"role": "assistant", "content": f"Assistant {i}"})

    # Request last 4 messages
    result = build_context(messages, 4)
    assert len(result) <= 4

    # Result should maintain chronological order
    # and start with a user message
    assert result[0]["role"] == "user"


def test_truncation_does_not_start_with_assistant():
    """Context slice must never begin with an assistant message."""
    from llm_service import build_context

    # Craft a history where the N-th message from the end is an assistant
    messages = [
        {"role": "user", "content": "u1"},
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "u2"},
        {"role": "assistant", "content": "a2"},
        {"role": "user", "content": "u3"},
        {"role": "assistant", "content": "a3"},
    ]

    # Window of 3: slice[-3:] = [a2, u3, a3] → leading assistant stripped
    result = build_context(messages, 3)
    assert result[0]["role"] == "user"


def test_context_minimum_value_enforced():
    """MAX_CONTEXT_MESSAGES below 2 is clamped to 2."""
    from llm_service import build_context

    messages = [
        {"role": "user", "content": "u1"},
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "u2"},
        {"role": "assistant", "content": "a2"},
    ]
    result = build_context(messages, max_context_messages=1)
    # Clamped to 2, then possibly stripped leading assistant: at least 1 msg
    assert len(result) >= 1


def test_context_messages_used_reported_in_response(client, monkeypatch):
    """The API response reports how many context messages were used."""
    import llm_service

    def _mock(new_user_message, history_messages, max_context_messages=None):
        return {
            "reply": "OK",
            "context_messages_used": len(history_messages),
            "error": None,
        }

    monkeypatch.setattr(llm_service, "generate_reply", _mock)

    r = client.post(
        "/api/chat",
        json={"message": "First message"},
        content_type="application/json",
    )
    assert r.status_code == 200
    data = r.get_json()
    assert "context_messages_used" in data
    assert isinstance(data["context_messages_used"], int)


def test_messages_to_history_role_mapping():
    """assistant role in DB maps to 'model' role for the SDK."""
    from llm_service import messages_to_history

    db_messages = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there"},
        {"role": "user", "content": "How are you?"},
    ]

    history = messages_to_history(db_messages)
    assert history[0].role == "user"
    assert history[1].role == "model"
    assert history[2].role == "user"
    assert history[0].parts[0].text == "Hello"
    assert history[1].parts[0].text == "Hi there"

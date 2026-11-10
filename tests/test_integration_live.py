"""
test_integration_live.py — Live end-to-end integration test.

IMPORTANT: This test makes REAL Gemini API calls and consumes API quota.
Run it only after adding a valid GEMINI_API_KEY to your .env file.

Usage:
    cd ContextAI
    pytest tests/test_integration_live.py -v -s

This test verifies the five-turn memory demonstration from the project spec.
Mocked unit tests do NOT prove the live Gemini integration works.
"""

import os
import pytest
import tempfile


# Skip entirely if no real API key
pytestmark = pytest.mark.skipif(
    not os.getenv("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY") == "test-key-not-real",
    reason="GEMINI_API_KEY not set — skipping live integration tests.",
)


@pytest.fixture()
def live_app(tmp_path):
    """Create a Flask test app with a real Gemini client and temp DB."""
    db_path = str(tmp_path / "live_test.db")
    from app import create_app
    flask_app = create_app(db_path=db_path)
    flask_app.config["TESTING"] = True
    return flask_app


@pytest.fixture()
def live_client(live_app):
    return live_app.test_client()


def test_five_turn_memory_demonstration(live_client):
    """
    Five-turn conversation demonstrating multi-turn memory.

    Turn 1: User introduces their name.
    Turn 2: User mentions their field of study.
    Turn 3: User mentions their favourite language.
    Turn 4: User asks what their name and field are.
    Turn 5: User asks which language they mentioned.

    Expected: Gemini correctly recalls the information from earlier turns.
    This is a semantic check, not an exact-string comparison.
    """
    conv_id = None

    def chat(message):
        nonlocal conv_id
        payload = {"message": message}
        if conv_id:
            payload["conversation_id"] = conv_id
        r = live_client.post("/api/chat", json=payload, content_type="application/json")
        assert r.status_code == 200, f"Chat failed: {r.get_json()}"
        data = r.get_json()
        conv_id = data["conversation_id"]
        print(f"\nUser: {message}")
        print(f"ContextAI: {data['reply']}")
        print(f"Context messages used: {data['context_messages_used']}")
        return data["reply"]

    # Turn 1
    r1 = chat("My name is Alex.")
    assert conv_id is not None

    # Turn 2
    r2 = chat("I am a computer science student.")

    # Turn 3
    r3 = chat("My favourite programming language is Python.")

    # Turn 4 — should recall name and field
    r4 = chat("What is my name and what am I studying?")
    r4_lower = r4.lower()
    assert "alex" in r4_lower, f"Expected 'Alex' in reply, got: {r4}"
    assert "computer science" in r4_lower or "cs" in r4_lower, (
        f"Expected 'computer science' in reply, got: {r4}"
    )

    # Turn 5 — should recall favourite language
    r5 = chat("Which programming language did I tell you I like?")
    assert "python" in r5.lower(), f"Expected 'Python' in reply, got: {r5}"

    print(f"\n✅ Five-turn memory demonstration passed! Conversation ID: {conv_id}")


def test_conversation_isolation_live(live_client):
    """A second conversation must NOT inherit information from the first."""
    # Conversation A
    r_a1 = live_client.post(
        "/api/chat",
        json={"message": "My secret word is ZEPHYRALPHA42."},
        content_type="application/json",
    )
    assert r_a1.status_code == 200

    # Conversation B — fresh, should not know the secret word
    r_b1 = live_client.post(
        "/api/chat",
        json={"message": "What secret word did I tell you?"},
        content_type="application/json",
    )
    assert r_b1.status_code == 200
    reply_b = r_b1.get_json()["reply"].lower()
    assert "zephyralpha42" not in reply_b, (
        "Conversation B should not know the secret word from Conversation A!"
    )
    print(f"\n✅ Conversation isolation test passed!")
    print(f"Conversation B reply: {r_b1.get_json()['reply']}")


def test_history_persists_after_restart(tmp_path):
    """Messages survive creating a new Flask app instance (simulates restart)."""
    db_path = str(tmp_path / "persist_test.db")

    # Session 1
    from app import create_app
    app1 = create_app(db_path=db_path)
    app1.config["TESTING"] = True
    client1 = app1.test_client()

    r = client1.post(
        "/api/chat",
        json={"message": "Remember the colour blue."},
        content_type="application/json",
    )
    assert r.status_code == 200
    conv_id = r.get_json()["conversation_id"]

    # Session 2 — new app instance, same DB
    app2 = create_app(db_path=db_path)
    app2.config["TESTING"] = True
    client2 = app2.test_client()

    r2 = client2.get(f"/api/conversations/{conv_id}")
    assert r2.status_code == 200
    messages = r2.get_json()["conversation"]["messages"]
    assert len(messages) >= 2
    contents = [m["content"] for m in messages]
    assert any("blue" in c.lower() for c in contents), "User message not found after restart!"
    print(f"\n✅ Persistence test passed — messages survive restart.")


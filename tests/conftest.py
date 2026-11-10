"""
conftest.py — Shared pytest fixtures for ContextAI tests.

All tests use an in-memory (or temp-file) SQLite database to prevent
interference with the development database.  The Gemini API is mocked
so tests run without consuming real API credits.

IMPORTANT: These mocked tests do NOT prove that the live Gemini API works
correctly.  Run test_integration_live.py with a real API key for end-to-end
verification.
"""

import os
import tempfile
import pytest

# Point to test DB before importing any app module
os.environ.setdefault("GEMINI_API_KEY", "test-key-not-real")
os.environ.setdefault("GEMINI_MODEL", "gemini-2.5-flash")
os.environ.setdefault("MAX_CONTEXT_MESSAGES", "20")
os.environ.setdefault("MAX_OUTPUT_TOKENS", "1024")


@pytest.fixture()
def tmp_db(tmp_path):
    """Return a path to a fresh temporary SQLite database."""
    db_file = tmp_path / "test_contextai.db"
    return str(db_file)


@pytest.fixture()
def app(tmp_db):
    """Create a Flask test application backed by an isolated database."""
    # Import here so env vars are set first
    import database as db_module
    from app import create_app

    flask_app = create_app(db_path=tmp_db)
    flask_app.config["TESTING"] = True
    yield flask_app

    # Teardown: reset db module state
    db_module.set_db_path("contextai.db")


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def mock_llm(monkeypatch):
    """
    Replace llm_service.generate_reply with a fake that returns a
    configurable canned response.
    """
    import llm_service

    def _fake_generate(new_user_message, history_messages, max_context_messages=None):
        return {
            "reply": f"Mock reply to: {new_user_message}",
            "context_messages_used": len(history_messages),
            "error": None,
        }

    monkeypatch.setattr(llm_service, "generate_reply", _fake_generate)
    return _fake_generate


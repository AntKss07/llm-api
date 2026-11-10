"""
conversation_service.py — Business logic layer for ContextAI.

Sits between the Flask routes and the database / LLM layers.
Provides clean, validated operations for conversation management and
message handling with safe retry semantics.
"""

import logging
import uuid
from typing import Any

import database as db
import llm_service
import config

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Conversation operations
# ---------------------------------------------------------------------------


def create_conversation(title: str = "New Conversation", db_path: str | None = None) -> dict:
    """Create and return a new conversation with a fresh UUID."""
    conversation_id = str(uuid.uuid4())
    return db.create_conversation(conversation_id, title, db_path)


def get_conversation(conversation_id: str, db_path: str | None = None) -> dict | None:
    """Return a conversation dict or None if not found."""
    return db.get_conversation(conversation_id, db_path)


def list_conversations(db_path: str | None = None) -> list[dict]:
    return db.list_conversations(db_path)


def rename_conversation(
    conversation_id: str, new_title: str, db_path: str | None = None
) -> dict | None:
    """
    Rename a conversation.  Returns the updated conversation dict or None if
    the conversation does not exist.
    """
    new_title = new_title.strip()
    if not new_title:
        return None
    new_title = new_title[:200]  # cap title length

    updated = db.update_conversation_title(conversation_id, new_title, db_path)
    if not updated:
        return None
    return db.get_conversation(conversation_id, db_path)


def delete_conversation(conversation_id: str, db_path: str | None = None) -> bool:
    return db.delete_conversation(conversation_id, db_path)


def get_conversation_with_messages(
    conversation_id: str, db_path: str | None = None
) -> dict | None:
    """Return the conversation dict with its full message list, or None."""
    convo = db.get_conversation(conversation_id, db_path)
    if convo is None:
        return None
    convo["messages"] = db.get_messages(conversation_id, db_path)
    return convo


# ---------------------------------------------------------------------------
# Chat / message handling
# ---------------------------------------------------------------------------


def process_chat_message(
    conversation_id: str | None,
    user_message: str,
    db_path: str | None = None,
) -> dict[str, Any]:
    """
    Process a user message:

    1. Validate the message.
    2. Resolve or create the conversation.
    3. Persist the user message.
    4. Fetch history and build context.
    5. Call the LLM.
    6. Persist the assistant reply ONLY on success.
    7. Return a structured result dict.

    Safe retry semantics: if the LLM call fails, the user message is NOT
    persisted (or is rolled back conceptually) so that callers can retry
    without duplicating history.  In practice we do not persist the user
    message until after a successful LLM call to maintain atomicity.

    Returns:
        {
            "conversation_id": str,
            "reply": str,
            "context_messages_used": int,
            "error": None | {"code": str, "message": str, "http_status": int}
        }
    """
    # --- Input validation ---
    user_message = user_message.strip() if user_message else ""
    if not user_message:
        return _chat_error(conversation_id, "empty_message", "Message cannot be empty.", 400)

    if len(user_message) > config.MAX_MESSAGE_LENGTH:
        return _chat_error(
            conversation_id,
            "message_too_long",
            f"Message exceeds the maximum allowed length of {config.MAX_MESSAGE_LENGTH} characters.",
            400,
        )

    # --- Resolve or create conversation ---
    created_new = False
    if conversation_id:
        convo = db.get_conversation(conversation_id, db_path)
        if convo is None:
            return _chat_error(
                conversation_id,
                "conversation_not_found",
                f"Conversation '{conversation_id}' does not exist.",
                404,
            )
    else:
        convo = create_conversation(db_path=db_path)
        conversation_id = convo["id"]
        created_new = True
        logger.info("Created new conversation %s.", conversation_id)

    # --- Load existing history ---
    history_messages = db.get_messages(conversation_id, db_path)

    # --- Call the LLM (do NOT persist user message yet) ---
    result = llm_service.generate_reply(
        new_user_message=user_message,
        history_messages=history_messages,
        max_context_messages=config.MAX_CONTEXT_MESSAGES,
    )

    if result["error"] is not None:
        # LLM call failed — do not store anything, return the error
        err = result["error"]
        return {
            "conversation_id": conversation_id,
            "reply": None,
            "context_messages_used": 0,
            "error": err,
        }

    # --- Persist both messages atomically (best-effort; SQLite commits each) ---
    try:
        db.add_message(conversation_id, "user", user_message, db_path)
        db.add_message(conversation_id, "assistant", result["reply"], db_path)
    except Exception as exc:
        logger.exception("Database error saving messages for conversation %s.", conversation_id)
        return _chat_error(
            conversation_id,
            "database_error",
            "Failed to save messages to the database.",
            500,
        )

    # --- Auto-title new conversations after first successful exchange ---
    if created_new:
        _auto_title(conversation_id, user_message, db_path)

    return {
        "conversation_id": conversation_id,
        "reply": result["reply"],
        "context_messages_used": result["context_messages_used"],
        "error": None,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _chat_error(
    conversation_id: str | None,
    code: str,
    message: str,
    http_status: int,
) -> dict[str, Any]:
    return {
        "conversation_id": conversation_id,
        "reply": None,
        "context_messages_used": 0,
        "error": {"code": code, "message": message, "http_status": http_status},
    }


def _auto_title(conversation_id: str, first_message: str, db_path: str | None) -> None:
    """Generate a short title from the first user message."""
    title = first_message[:60].strip()
    if len(first_message) > 60:
        title += "…"
    try:
        db.update_conversation_title(conversation_id, title, db_path)
    except Exception:
        logger.warning("Could not auto-title conversation %s.", conversation_id)


"""
database.py — SQLite persistence layer for ContextAI.

Two tables:
  conversations — one row per chat session.
  messages      — ordered history of user/assistant turns.

Foreign-key constraints are enforced; deleting a conversation cascades to its
messages.  All queries use parameterised statements to prevent SQL injection.

IMPORTANT: Call init_db() once at application startup before any other DB
operation.  Pass an explicit db_path when you need an isolated test database.
"""

import sqlite3
import logging
from contextlib import contextmanager
from typing import Generator

logger = logging.getLogger(__name__)

# Module-level default path — overridden by the Flask app via set_db_path().
_DB_PATH: str = "contextai.db"


def set_db_path(path: str) -> None:
    """Override the default database path (used by tests)."""
    global _DB_PATH
    _DB_PATH = path


def get_db_path() -> str:
    return _DB_PATH


@contextmanager
def get_connection(db_path: str | None = None) -> Generator[sqlite3.Connection, None, None]:
    """Yield a SQLite connection with foreign keys enabled and WAL mode on."""
    path = db_path or _DB_PATH
    conn = sqlite3.connect(path, detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id         TEXT PRIMARY KEY,
    title      TEXT NOT NULL DEFAULT 'New Conversation',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role            TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
    content         TEXT NOT NULL,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation_id
    ON messages(conversation_id, created_at);
"""


def init_db(db_path: str | None = None) -> None:
    """Create tables and indexes if they do not already exist."""
    path = db_path or _DB_PATH
    logger.info("Initialising database at %s", path)
    with get_connection(path) as conn:
        conn.executescript(_SCHEMA)


# ---------------------------------------------------------------------------
# Conversation operations
# ---------------------------------------------------------------------------


def create_conversation(conversation_id: str, title: str = "New Conversation", db_path: str | None = None) -> dict:
    sql = """
        INSERT INTO conversations (id, title, created_at, updated_at)
        VALUES (?, ?, datetime('now'), datetime('now'))
    """
    with get_connection(db_path) as conn:
        conn.execute(sql, (conversation_id, title))
    return get_conversation(conversation_id, db_path)


def get_conversation(conversation_id: str, db_path: str | None = None) -> dict | None:
    sql = "SELECT * FROM conversations WHERE id = ?"
    with get_connection(db_path) as conn:
        row = conn.execute(sql, (conversation_id,)).fetchone()
    return dict(row) if row else None


def list_conversations(db_path: str | None = None) -> list[dict]:
    sql = "SELECT * FROM conversations ORDER BY updated_at DESC"
    with get_connection(db_path) as conn:
        rows = conn.execute(sql).fetchall()
    return [dict(r) for r in rows]


def update_conversation_title(conversation_id: str, title: str, db_path: str | None = None) -> bool:
    sql = "UPDATE conversations SET title = ?, updated_at = datetime('now') WHERE id = ?"
    with get_connection(db_path) as conn:
        result = conn.execute(sql, (title, conversation_id))
    return result.rowcount > 0


def touch_conversation(conversation_id: str, db_path: str | None = None) -> None:
    sql = "UPDATE conversations SET updated_at = datetime('now') WHERE id = ?"
    with get_connection(db_path) as conn:
        conn.execute(sql, (conversation_id,))


def delete_conversation(conversation_id: str, db_path: str | None = None) -> bool:
    sql = "DELETE FROM conversations WHERE id = ?"
    with get_connection(db_path) as conn:
        result = conn.execute(sql, (conversation_id,))
    return result.rowcount > 0


# ---------------------------------------------------------------------------
# Message operations
# ---------------------------------------------------------------------------


def add_message(
    conversation_id: str,
    role: str,
    content: str,
    db_path: str | None = None,
) -> dict:
    sql = """
        INSERT INTO messages (conversation_id, role, content, created_at)
        VALUES (?, ?, ?, datetime('now'))
    """
    with get_connection(db_path) as conn:
        cursor = conn.execute(sql, (conversation_id, role, content))
        msg_id = cursor.lastrowid
        row = conn.execute("SELECT * FROM messages WHERE id = ?", (msg_id,)).fetchone()
    touch_conversation(conversation_id, db_path)
    return dict(row)


def get_messages(conversation_id: str, db_path: str | None = None) -> list[dict]:
    """Return all messages for a conversation in chronological order."""
    sql = """
        SELECT * FROM messages
        WHERE conversation_id = ?
        ORDER BY created_at ASC, id ASC
    """
    with get_connection(db_path) as conn:
        rows = conn.execute(sql, (conversation_id,)).fetchall()
    return [dict(r) for r in rows]


def get_recent_messages(
    conversation_id: str,
    limit: int,
    db_path: str | None = None,
) -> list[dict]:
    """Return the most recent *limit* messages in chronological order."""
    sql = """
        SELECT * FROM (
            SELECT * FROM messages
            WHERE conversation_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT ?
        ) sub
        ORDER BY created_at ASC, id ASC
    """
    with get_connection(db_path) as conn:
        rows = conn.execute(sql, (conversation_id, limit)).fetchall()
    return [dict(r) for r in rows]


"""
config.py — Application configuration for ContextAI.

Loads settings from environment variables via python-dotenv.
Provides a clean configuration error when mandatory variables are missing.
"""

import os
import logging
from dotenv import load_dotenv

# Load .env file if present
load_dotenv()

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Gemini API
# ---------------------------------------------------------------------------

GEMINI_API_KEY: str | None = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_TIMEOUT_SECONDS: int = int(os.getenv("GEMINI_TIMEOUT_SECONDS", "30"))

# ---------------------------------------------------------------------------
# Context window
# ---------------------------------------------------------------------------

_raw_max_ctx = os.getenv("MAX_CONTEXT_MESSAGES", "20")
try:
    MAX_CONTEXT_MESSAGES: int = max(2, int(_raw_max_ctx))
except ValueError:
    logger.warning(
        "Invalid MAX_CONTEXT_MESSAGES=%r — falling back to 20.", _raw_max_ctx
    )
    MAX_CONTEXT_MESSAGES = 20

# ---------------------------------------------------------------------------
# Generation parameters
# ---------------------------------------------------------------------------

_raw_max_tokens = os.getenv("MAX_OUTPUT_TOKENS", "1024")
try:
    MAX_OUTPUT_TOKENS: int = int(_raw_max_tokens)
except ValueError:
    logger.warning(
        "Invalid MAX_OUTPUT_TOKENS=%r — falling back to 1024.", _raw_max_tokens
    )
    MAX_OUTPUT_TOKENS = 1024

# ---------------------------------------------------------------------------
# Input validation limits
# ---------------------------------------------------------------------------

MAX_MESSAGE_LENGTH: int = 32_000   # characters

# ---------------------------------------------------------------------------
# Flask
# ---------------------------------------------------------------------------

FLASK_DEBUG: bool = os.getenv("FLASK_DEBUG", "false").lower() == "true"
DATABASE_PATH: str = os.getenv("DATABASE_PATH", "contextai.db")

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT: str = """\
You are ContextAI, a friendly, accurate, and professional AI learning assistant.

Your core behaviours:
- Explain concepts clearly and at the appropriate level for the user.
- Maintain conversational context across the messages you have been given.
- Provide concise answers by default; offer more detail only when asked.
- Admit uncertainty honestly — say "I'm not sure" rather than guessing.
- Never fabricate facts, citations, or statistics.
- Ask clarifying questions when a request is ambiguous.
- Never claim to remember a message that was not provided in your current context.
  If conversation history was truncated, acknowledge that gracefully.
- Be encouraging and supportive, especially for learners.
- Keep responses well-structured with bullet points or numbered lists where helpful.
"""

# ---------------------------------------------------------------------------
# Validation helper
# ---------------------------------------------------------------------------


def validate_config() -> None:
    """Raise EnvironmentError if mandatory configuration is missing."""
    if not GEMINI_API_KEY:
        raise EnvironmentError(
            "GEMINI_API_KEY is not set. "
            "Please copy .env.example to .env and add your key from "
            "https://aistudio.google.com/app/apikey"
        )


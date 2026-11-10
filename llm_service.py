"""
llm_service.py — Gemini API integration for ContextAI.

Responsibilities:
  - Build and configure the google-genai client.
  - Convert stored messages to SDK Content objects.
  - Apply context-window truncation before each API call.
  - Call the Gemini API and validate the response.
  - Map SDK / network exceptions to structured error dictionaries.

NOTE: Message-count-based truncation is an approximation.  It does NOT
guarantee staying within the model's token budget.  For production use,
consider token-aware truncation via the Gemini tokenCount endpoint.
"""

import logging
import time
from typing import Any

from google import genai
from google.genai import types
from google.api_core import exceptions as google_exceptions

import config

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Client singleton
# ---------------------------------------------------------------------------

_client: genai.Client | None = None


def get_client() -> genai.Client:
    """Return (or lazily create) the shared Gemini client."""
    global _client
    if _client is None:
        if not config.GEMINI_API_KEY:
            raise EnvironmentError(
                "GEMINI_API_KEY is not configured. "
                "Add it to your .env file."
            )
        _client = genai.Client(api_key=config.GEMINI_API_KEY)
        logger.info("Gemini client initialised (model=%s).", config.GEMINI_MODEL)
    return _client


def reset_client() -> None:
    """Reset the client singleton (used in tests)."""
    global _client
    _client = None


# ---------------------------------------------------------------------------
# History conversion
# ---------------------------------------------------------------------------


def messages_to_history(messages: list[dict]) -> list[types.Content]:
    """
    Convert a list of database message dicts to SDK Content objects.

    SDK roles: 'user' and 'model'.
    DB roles:  'user' and 'assistant' — assistant maps to 'model'.
    """
    history: list[types.Content] = []
    for msg in messages:
        role = "model" if msg["role"] == "assistant" else "user"
        history.append(
            types.Content(
                role=role,
                parts=[types.Part.from_text(text=msg["content"])],
            )
        )
    return history


# ---------------------------------------------------------------------------
# Context truncation
# ---------------------------------------------------------------------------


def build_context(
    history_messages: list[dict],
    max_context_messages: int,
) -> list[dict]:
    """
    Return at most *max_context_messages* recent messages.

    The full history is preserved in SQLite; only the slice sent to the LLM
    is affected.  Older messages beyond the window may not be remembered by
    the model.

    Ensures the returned slice does not start with an 'assistant' message
    (which would confuse the alternating user/model pattern expected by the
    SDK).
    """
    if max_context_messages < 2:
        max_context_messages = 2

    recent = history_messages[-max_context_messages:]

    # Drop a leading assistant message so the slice always starts with a user
    # turn (required by the SDK's alternating role constraint).
    while recent and recent[0]["role"] == "assistant":
        recent = recent[1:]

    return recent


# ---------------------------------------------------------------------------
# Main generation function
# ---------------------------------------------------------------------------


def generate_reply(
    new_user_message: str,
    history_messages: list[dict],
    max_context_messages: int | None = None,
) -> dict[str, Any]:
    """
    Send *new_user_message* to Gemini with the conversation history and return
    a result dict:

      {
          "reply": str,
          "context_messages_used": int,
          "error": None          # or an error dict on failure
      }

    On any error the "error" key contains:
      {"code": str, "message": str, "http_status": int}
    """
    if max_context_messages is None:
        max_context_messages = config.MAX_CONTEXT_MESSAGES

    # --- Truncate history for context window ---
    context_slice = build_context(history_messages, max_context_messages)
    sdk_history = messages_to_history(context_slice)

    logger.debug(
        "Sending message to Gemini. history_len=%d, context_used=%d",
        len(history_messages),
        len(context_slice),
    )

    try:
        client = get_client()

        chat = client.chats.create(
            model=config.GEMINI_MODEL,
            history=sdk_history,
            config=types.GenerateContentConfig(
                system_instruction=config.SYSTEM_PROMPT,
                max_output_tokens=config.MAX_OUTPUT_TOKENS,
                temperature=0.7,
            ),
        )

        response = chat.send_message(new_user_message)

        # --- Validate response ---
        if not response or not response.text:
            logger.warning("Gemini returned an empty response.")
            return _error_result(
                "empty_response",
                "The AI returned an empty response. Please try again.",
                502,
            )

        reply_text = response.text.strip()
        logger.info("Gemini reply received (%d chars).", len(reply_text))

        return {
            "reply": reply_text,
            "context_messages_used": len(context_slice),
            "error": None,
        }

    except EnvironmentError as exc:
        logger.error("Configuration error: %s", exc)
        return _error_result("missing_api_key", str(exc), 500)

    except google_exceptions.Unauthenticated as exc:
        logger.error("Gemini authentication failed: %s", exc)
        return _error_result(
            "auth_failure",
            "Invalid or missing Gemini API key. Check your GEMINI_API_KEY.",
            401,
        )

    except google_exceptions.PermissionDenied as exc:
        logger.error("Gemini permission denied: %s", exc)
        return _error_result(
            "permission_denied",
            "API key does not have permission to access this resource.",
            403,
        )

    except google_exceptions.ResourceExhausted as exc:
        logger.warning("Gemini rate limit hit: %s", exc)
        return _error_result(
            "rate_limit",
            "API quota exhausted. Please wait a moment and try again.",
            429,
        )

    except google_exceptions.DeadlineExceeded as exc:
        logger.warning("Gemini request timed out: %s", exc)
        return _error_result(
            "timeout",
            f"Request timed out after {config.GEMINI_TIMEOUT_SECONDS}s. Try a shorter message.",
            504,
        )

    except google_exceptions.ServiceUnavailable as exc:
        logger.warning("Gemini service unavailable: %s", exc)
        return _error_result(
            "service_unavailable",
            "The AI service is temporarily unavailable. Please try again shortly.",
            503,
        )

    except google_exceptions.GoogleAPIError as exc:
        logger.error("Gemini API error: %s", exc)
        return _error_result(
            "api_error",
            "An error occurred communicating with the AI service.",
            502,
        )

    except ConnectionError as exc:
        logger.error("Network connection error: %s", exc)
        return _error_result(
            "network_error",
            "Could not connect to the AI service. Check your internet connection.",
            503,
        )

    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected error calling Gemini API.")
        return _error_result(
            "unexpected_error",
            "An unexpected error occurred. Please try again.",
            500,
        )


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _error_result(code: str, message: str, http_status: int) -> dict[str, Any]:
    return {
        "reply": None,
        "context_messages_used": 0,
        "error": {
            "code": code,
            "message": message,
            "http_status": http_status,
        },
    }


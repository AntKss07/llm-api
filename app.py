"""
app.py — Flask application for ContextAI.

Registers all API routes, initialises the database, and serves the frontend.

WARNING: This is a single-user local prototype.  Do NOT expose these routes
publicly without adding authentication, rate limiting, and input sanitisation
appropriate for a production environment.
"""

import logging
import uuid
from functools import wraps

from flask import Flask, jsonify, render_template, request, abort

import config
import database as db
import conversation_service as cs

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.DEBUG if config.FLASK_DEBUG else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def create_app(db_path: str | None = None) -> Flask:
    """
    Create and configure the Flask application.

    Pass *db_path* to override the default SQLite path (useful in tests).
    """
    app = Flask(__name__)
    app.config["JSON_SORT_KEYS"] = False

    # Use the provided db_path or the config default
    _db_path = db_path or config.DATABASE_PATH
    db.set_db_path(_db_path)
    db.init_db(_db_path)

    logger.info("ContextAI starting — model=%s, db=%s", config.GEMINI_MODEL, _db_path)

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    def _ok(data: dict, status: int = 200):
        return jsonify({"status": "ok", **data}), status

    def _error(code: str, message: str, status: int):
        return jsonify({"status": "error", "code": code, "message": message}), status

    def _validate_uuid(value: str) -> bool:
        try:
            uuid.UUID(value)
            return True
        except (ValueError, AttributeError):
            return False

    # -----------------------------------------------------------------------
    # Health
    # -----------------------------------------------------------------------

    @app.route("/api/health")
    def health():
        """Basic application health check."""
        api_key_set = bool(config.GEMINI_API_KEY)
        return _ok({
            "healthy": True,
            "api_key_configured": api_key_set,
            "model": config.GEMINI_MODEL,
            "max_context_messages": config.MAX_CONTEXT_MESSAGES,
        })

    # -----------------------------------------------------------------------
    # Frontend
    # -----------------------------------------------------------------------

    @app.route("/")
    def index():
        return render_template("index.html")

    # -----------------------------------------------------------------------
    # Conversations
    # -----------------------------------------------------------------------

    @app.route("/api/conversations", methods=["GET"])
    def list_conversations():
        convos = cs.list_conversations()
        return _ok({"conversations": convos})

    @app.route("/api/conversations", methods=["POST"])
    def create_conversation():
        body = request.get_json(silent=True) or {}
        title = body.get("title", "New Conversation")
        convo = cs.create_conversation(title=title)
        return _ok({"conversation": convo}, 201)

    @app.route("/api/conversations/<conversation_id>", methods=["GET"])
    def get_conversation(conversation_id: str):
        if not _validate_uuid(conversation_id):
            return _error("invalid_id", "Invalid conversation ID format.", 400)
        convo = cs.get_conversation_with_messages(conversation_id)
        if convo is None:
            return _error("not_found", "Conversation not found.", 404)
        return _ok({"conversation": convo})

    @app.route("/api/conversations/<conversation_id>", methods=["DELETE"])
    def delete_conversation(conversation_id: str):
        if not _validate_uuid(conversation_id):
            return _error("invalid_id", "Invalid conversation ID format.", 400)
        deleted = cs.delete_conversation(conversation_id)
        if not deleted:
            return _error("not_found", "Conversation not found.", 404)
        return _ok({"deleted": conversation_id})

    @app.route("/api/conversations/<conversation_id>", methods=["PATCH"])
    def rename_conversation(conversation_id: str):
        if not _validate_uuid(conversation_id):
            return _error("invalid_id", "Invalid conversation ID format.", 400)
        body = request.get_json(silent=True) or {}
        new_title = body.get("title", "").strip()
        if not new_title:
            return _error("invalid_title", "Title cannot be empty.", 400)
        convo = cs.rename_conversation(conversation_id, new_title)
        if convo is None:
            return _error("not_found", "Conversation not found.", 404)
        return _ok({"conversation": convo})

    # -----------------------------------------------------------------------
    # Chat
    # -----------------------------------------------------------------------

    @app.route("/api/chat", methods=["POST"])
    def chat():
        """
        Send a message to the Gemini API within an existing or new conversation.

        Request JSON:
            {
                "conversation_id": "<uuid>",   # optional
                "message": "user text"
            }

        Response JSON:
            {
                "status": "ok",
                "conversation_id": "<uuid>",
                "reply": "...",
                "context_messages_used": N
            }
        """
        body = request.get_json(silent=True)
        if body is None:
            return _error("invalid_json", "Request body must be valid JSON.", 400)

        message = body.get("message", "")
        conversation_id = body.get("conversation_id")

        # Validate supplied conversation_id format (if provided)
        if conversation_id and not _validate_uuid(conversation_id):
            return _error("invalid_id", "Invalid conversation_id format.", 400)

        # Check API key before hitting the LLM
        if not config.GEMINI_API_KEY:
            return _error(
                "missing_api_key",
                "GEMINI_API_KEY is not configured. See README for setup instructions.",
                500,
            )

        result = cs.process_chat_message(
            conversation_id=conversation_id,
            user_message=message,
        )

        if result["error"]:
            err = result["error"]
            http_status = err.get("http_status", 500)
            return _error(err["code"], err["message"], http_status)

        return _ok({
            "conversation_id": result["conversation_id"],
            "reply": result["reply"],
            "context_messages_used": result["context_messages_used"],
        })

    # -----------------------------------------------------------------------
    # Error handlers
    # -----------------------------------------------------------------------

    @app.errorhandler(404)
    def not_found(e):
        return _error("not_found", "The requested resource was not found.", 404)

    @app.errorhandler(405)
    def method_not_allowed(e):
        return _error("method_not_allowed", "Method not allowed.", 405)

    @app.errorhandler(500)
    def internal_error(e):
        logger.exception("Unhandled internal server error.")
        return _error("server_error", "An internal server error occurred.", 500)

    return app


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    try:
        config.validate_config()
    except EnvironmentError as exc:
        logger.warning("⚠  Configuration warning: %s", exc)
        logger.warning("The app will start but LLM calls will fail without an API key.")

    application = create_app()
    application.run(
        host="0.0.0.0",
        port=5000,
        debug=config.FLASK_DEBUG,
    )


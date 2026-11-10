# ContextAI — An Intelligent Chatbot with Multi-Turn Conversation Memory

> A production-conscious internship project demonstrating full-stack AI development with Google Gemini, Flask, SQLite, and vanilla JavaScript.

---

## Table of Contents

1. [Project Description](#project-description)
2. [Features](#features)
3. [Technology Stack](#technology-stack)
4. [Architecture](#architecture)
5. [Project Structure](#project-structure)
6. [Prerequisites](#prerequisites)
7. [Installation](#installation)
8. [Gemini API Key Setup](#gemini-api-key-setup)
9. [Environment Variables](#environment-variables)
10. [Running the Application](#running-the-application)
11. [API Endpoints](#api-endpoints)
12. [Conversation Memory](#conversation-memory)
13. [Context Window Management](#context-window-management)
14. [Error Handling](#error-handling)
15. [Testing](#testing)
16. [Five-Turn Demonstration](#five-turn-demonstration)
17. [Limitations](#limitations)
18. [Future Improvements](#future-improvements)
19. [Screenshots](#screenshots)

---

## Project Description

ContextAI is a full-stack chatbot application powered by the **Google Gemini API** that maintains genuine multi-turn conversation memory. Users can hold multiple separate conversations, each with its own isolated history stored in SQLite. The application implements a configurable context window, robust error handling, and a modern dark-theme frontend — all without external databases, Docker, or heavy frameworks.

---

## Features

- **Real Gemini AI** — powered by `gemini-2.5-flash`, no hardcoded or mock responses in production.
- **Multi-turn memory** — the bot remembers what you said earlier in the same conversation.
- **Separate conversations** — each chat session has an isolated UUID-based history.
- **Context window management** — configurable rolling window; full history preserved in SQLite.
- **Persistent storage** — messages survive browser refresh and backend restart.
- **Defined AI personality** — friendly, accurate learning assistant via system prompt.
- **Comprehensive error handling** — API failures, timeouts, rate limits, auth errors.
- **Modern responsive frontend** — dark theme, mobile-friendly, vanilla JavaScript.
- **Safe retry semantics** — failed LLM calls do not corrupt or duplicate history.
- **Full test suite** — 30+ automated unit/integration tests (Gemini mocked).

---

## Technology Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12, Flask 3.x |
| LLM | Google Gemini API (`gemini-2.5-flash`) |
| SDK | `google-genai` (official, maintained) |
| Database | SQLite via Python `sqlite3` |
| Env management | `python-dotenv` |
| Frontend | HTML5, CSS3, Vanilla JavaScript |
| Testing | `pytest`, Flask test client |

---

## Architecture

```
User
  │
  ▼
Web Chat Interface (HTML/CSS/JS)
  │   Fetch API
  ▼
Flask REST API  (app.py)
  │
  ▼
Conversation Service  (conversation_service.py)
  │                       │
  ▼                       ▼
LLM Service            SQLite Database  (database.py)
(llm_service.py)          │
  │                       └── conversations table
  ▼                       └── messages table
Context Window Manager
  ├── Recent N Messages (configurable)
  └── System Instruction (config.py)
  │
  ▼
Google Gemini API
  │
  ▼
Response Validation
  │
  ▼
SQLite Message Storage
  │
  ▼
Flask JSON Response
  │
  ▼
Chat Interface updates
```

**How the components work together:**

1. The user types a message in the browser and clicks Send.
2. The JavaScript frontend POSTs to `/api/chat` with the message and an optional `conversation_id`.
3. Flask validates the request, checks the API key, and delegates to `conversation_service`.
4. `conversation_service` resolves or creates the conversation in SQLite, fetches its full history, then calls `llm_service.generate_reply()`.
5. `llm_service` slices the history to the most recent `MAX_CONTEXT_MESSAGES` entries, prepends the system prompt, constructs SDK `Content` objects, and calls the Gemini API.
6. On success, both the user message and the assistant reply are persisted to SQLite.
7. On failure, **nothing** is persisted — safe retry semantics are preserved.
8. The conversation's `updated_at` timestamp is refreshed, bubbling it to the top of the sidebar list.
9. The JSON response is returned to the browser, which appends the reply bubble and updates the context badge.

---

## Project Structure

```
ContextAI/
│
├── app.py                      ← Flask application, all API routes
├── config.py                   ← Settings loaded from .env; system prompt
├── database.py                 ← SQLite layer (conversations + messages)
├── llm_service.py              ← Gemini SDK integration, context truncation
├── conversation_service.py     ← Business logic, safe retry, auto-title
│
├── requirements.txt
├── .env.example                ← Template — copy to .env and fill in key
├── .gitignore
├── README.md
│
├── templates/
│   └── index.html              ← Single-page chat UI
│
├── static/
│   ├── css/
│   │   └── style.css           ← Dark-theme responsive styles
│   └── js/
│       └── app.js              ← Frontend logic (Fetch API, state management)
│
└── tests/
    ├── __init__.py
    ├── conftest.py             ← Shared fixtures, mock LLM
    ├── test_api.py             ← HTTP endpoint tests
    ├── test_conversations.py   ← Memory, isolation, persistence tests
    ├── test_context.py         ← Context truncation unit tests
    └── test_integration_live.py ← Real API tests (requires GEMINI_API_KEY)
```

---

## Prerequisites

- **Python 3.11+** (tested on 3.12)
- **pip** package manager
- A **Google Gemini API key** (free tier available)
- **Git** (optional, for version control)

---

## Installation

```powershell
# 1. Navigate to the project directory
cd "c:\KSS\PROJECTS\llm api\ContextAI"

# 2. Create a virtual environment
python -m venv venv
.\venv\Scripts\Activate.ps1

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set up environment variables
Copy-Item .env.example .env
# Then edit .env to add your GEMINI_API_KEY (see next section)
```

---

## Gemini API Key Setup

1. Go to [Google AI Studio](https://aistudio.google.com/app/apikey).
2. Sign in with your Google account.
3. Click **Create API key**.
4. Copy the key.
5. Open `.env` and replace `your_gemini_api_key_here` with your key:

```env
GEMINI_API_KEY=AIza...your_actual_key_here
```

> **Security reminder:** Never commit your `.env` file. It is listed in `.gitignore`.

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `GEMINI_API_KEY` | *(required)* | Your Google Gemini API key |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Gemini model identifier |
| `MAX_CONTEXT_MESSAGES` | `20` | Rolling message window sent to the LLM |
| `MAX_OUTPUT_TOKENS` | `1024` | Maximum tokens in each response |
| `GEMINI_TIMEOUT_SECONDS` | `30` | API request timeout |
| `FLASK_DEBUG` | `false` | Enable Flask debug mode |

---

## Running the Application

```powershell
# From the ContextAI directory, with venv active:
python app.py
```

Then open your browser at: **http://localhost:5000**

The SQLite database (`contextai.db`) is created automatically on first run.

---

## API Endpoints

> ⚠️ This is a single-user local prototype. Do not expose these routes publicly without authentication, rate limiting, and input sanitisation.

| Method | Route | Description |
|---|---|---|
| `GET` | `/` | Render chatbot frontend |
| `GET` | `/api/health` | Application health check |
| `GET` | `/api/conversations` | List all conversations |
| `POST` | `/api/conversations` | Create a new conversation |
| `GET` | `/api/conversations/<id>` | Get conversation with messages |
| `DELETE` | `/api/conversations/<id>` | Delete conversation and messages |
| `PATCH` | `/api/conversations/<id>` | Rename conversation |
| `POST` | `/api/chat` | Send a message, get AI reply |

### POST /api/chat

Request:
```json
{
  "conversation_id": "optional-uuid",
  "message": "Hello, my name is Alex."
}
```

Response:
```json
{
  "status": "ok",
  "conversation_id": "550e8400-e29b-41d4-a716-446655440000",
  "reply": "Hello Alex! How can I help you today?",
  "context_messages_used": 0
}
```

---

## Conversation Memory

Each conversation has a unique UUID stored in SQLite. When a user sends a message:

1. All previous messages for that conversation are fetched from SQLite.
2. A configurable rolling window of recent messages is selected.
3. These are converted to Gemini SDK `Content` objects with alternating `user`/`model` roles.
4. The system instruction (defined in `config.py`) is provided separately.
5. The new user message is sent — the model sees the context and responds accordingly.

**Key property:** Only after a **successful** API call are both the user message and assistant reply persisted. This prevents duplicate messages on retry after a failed request.

---

## Context Window Management

```
Full conversation history (SQLite):
  msg 1, msg 2, msg 3, ... msg 18, msg 19, msg 20, msg 21

                                   ▲ MAX_CONTEXT_MESSAGES = 4 ▲
Context window sent to Gemini:              msg 18, msg 19, msg 20, msg 21
                                            └─ user ─┘ └─ assistant ─┘
```

- `MAX_CONTEXT_MESSAGES=20` by default (configurable via `.env`).
- The **full history** is always preserved in SQLite.
- **Only the slice** sent to the LLM is truncated.
- Older messages outside the window are **not remembered** by the model (the model is stateless; it only sees what is in the context).
- This is a **message-count approximation**, not token-aware. For long messages, the token limit could still be exceeded. Token-aware truncation is a noted future improvement.

The system prompt is always included separately and does not count towards `MAX_CONTEXT_MESSAGES`.

---

## Error Handling

| Scenario | HTTP Status | Behaviour |
|---|---|---|
| Missing API key | 500 | Clear message, no stack trace exposed |
| Invalid API key | 401 | Auth failure message |
| Rate limit exceeded | 429 | Retry message shown to user |
| Network / timeout | 504 | Timeout message; user message not saved |
| Empty AI response | 502 | Error shown; nothing persisted |
| Empty user message | 400 | Validation error before API call |
| Message too long | 400 | Rejects before API call |
| Unknown conversation | 404 | Not found error |
| Invalid UUID format | 400 | Format validation error |
| Database error | 500 | Generic error; nothing exposed |

All errors return consistent JSON: `{"status": "error", "code": "...", "message": "..."}`.
Backend logs contain technical details; the frontend only receives safe, user-friendly messages.

---

## Testing

```powershell
# From the ContextAI directory, with venv active:

# Run all unit tests (mocked, no API key needed):
pytest tests/ -v --ignore=tests/test_integration_live.py

# Run with coverage:
pip install pytest-cov
pytest tests/ --ignore=tests/test_integration_live.py --cov=. --cov-report=term-missing

# Run live integration tests (requires real GEMINI_API_KEY in .env):
pytest tests/test_integration_live.py -v -s
```

> **Note:** Mocked tests do not prove the live Gemini integration works. Run `test_integration_live.py` with a valid API key for end-to-end verification.

---

## Five-Turn Demonstration

After setting up your API key and starting the server:

1. Open **http://localhost:5000**
2. Click **New Chat**
3. Send these messages in order in the **same conversation**:

| Turn | You say | Expected bot behaviour |
|---|---|---|
| 1 | `My name is Alex.` | Greets Alex |
| 2 | `I am a computer science student.` | Acknowledges CS |
| 3 | `My favourite programming language is Python.` | Acknowledges Python |
| 4 | `What is my name and what am I studying?` | Recalls "Alex" and "computer science" |
| 5 | `Which programming language did I tell you I like?` | Recalls "Python" |

Then open a **second conversation** and ask the same questions — the bot should have no knowledge of Alex.

**To verify persistence:** After the conversation, restart the backend (`python app.py`) and refresh the browser. The conversation history should still appear in the sidebar and all messages should be intact.

---

## Limitations

- **Single-user prototype** — no authentication or multi-user isolation. Do not expose publicly.
- **Message-count context window** — not token-aware. Very long messages may still exceed model limits.
- **No streaming** — responses arrive all at once; large replies may take several seconds.
- **No conversation search** — conversations are listed by recency only.
- **SQLite concurrency** — WAL mode is enabled but SQLite is not suitable for high-concurrency production use.
- **No file or image uploads** — text only.

---

## Future Improvements

- Token-aware context window using the Gemini `countTokens` API.
- Streaming responses via Server-Sent Events (SSE).
- Conversation search and tagging.
- Export conversation as Markdown or PDF.
- User authentication (OAuth or JWT).
- Support for file/image uploads (Gemini is multimodal).
- Automatic conversation summarisation for long histories.
- PostgreSQL backend for production deployments.
- Rate limiting and request queuing.
- Deployment to Cloud Run or similar PaaS.

---

## Screenshots

> *Screenshots will be added after the first run with a valid API key.*

---

## License

MIT — free for personal and educational use.


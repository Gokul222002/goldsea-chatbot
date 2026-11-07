# GoldSea AI Chatbot

> Genuinely helpful, precision-engineered personal AI assistant designed for Gokul. Features adaptive cross-chat memory, real-time live web search grounding, direct-first answers, desktop productivity shortcuts, voice input, file attachments, and installable PWA mobile support.

---

## Highlights & Capabilities

- **Direct Answer First**: Answers the user immediately with zero pleasantry fluff, followed by clean step-by-step guidance for how-to questions.
- **Zero Hallucination / Zero Guessing**: Explicitly states "I'm not sure" for unknowable facts (e.g., future stock prices, private thoughts, hidden notes) and never invents fake URLs or citations.
- **Follow-up Action Chips**: Generates 2–3 relevant, clickable suggestion chips under every response.
- **Adaptive Memory**: Learns and preserves Gokul's identity, preferences, and coding styles across conversations via persistent SQLite storage.
- **Live Web Grounding**: Automatically detects time-sensitive queries (news, prices, versions, current events) and queries live web search for verified sources.
- **Daily-Use Shortcuts**:
  - Home screen quick action cards: *Summarize this text*, *Fix my grammar*, *Explain like I'm new*, *Draft an email*, *Debug my code*, *Plan my day*.
  - Per-reply controls: *Regenerate*, *Make shorter*, *Make more detailed*, *Copy*.
  - Desktop keyboard shortcuts (`Ctrl+N`, `Ctrl+K`, `Ctrl+/`, `Enter`, `Shift+Enter`, `Escape`).
- **Reliability & Retry**: Exponential backoff retry on API quota/load failures with persistent retry UI (never blank screens or raw errors). Context compression maintains chat history without token overflow.
- **Multimodal & Voice**: Integrated Web Speech API voice input and multi-format file attachment support (Code, Text, Markdown, PDF).
- **PWA Ready**: Offline caching, standalone display mode, and mobile-responsive drawer interface.

---

## Tech Stack

- **Backend**: Python 3.11, FastAPI, Uvicorn, SQLite, Server-Sent Events (SSE), DuckDuckGo Search, Google GenAI SDK.
- **Frontend**: Vanilla JavaScript (ES6+), Tailwind CSS, Lucide Icons, Marked.js, Highlight.js, DOMPurify, Service Worker PWA.
- **Cloud Deployment**: Render Blueprint (`render.yaml`) with continuous deployment from GitHub.

---

## Local Development

```bash
# 1. Create and activate virtual environment
python -m venv .venv
.\.venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Start local server
python run_server.py
# Or on Windows: start_server.bat
```

Access the UI at `http://localhost:8000`.

---

## Running Acceptance Tests

```bash
.\.venv\Scripts\pytest backend/tests/test_eval_suite.py -v -s
```

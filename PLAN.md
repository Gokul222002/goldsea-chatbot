# GOLDSEA CHATBOT — Master Engineering & Deployment Plan

## 1. Project Overview & Objectives
GoldSea Chatbot is a modern, responsive, genuinely helpful AI assistant engineered for Gokul. It is architected for maximum helpfulness, answer precision, adaptive cross-chat memory, reliability under API quotas, desktop productivity shortcuts, voice input, file uploads, and PWA mobile installation.

### Key Tenets
1. **Answer Quality**: Direct answers first, explanations after; step-by-step for how-to questions; strict language-tagged code blocks; explicit "I'm not sure" for unknown facts without hallucination or fake URLs; adaptive tone & memory; 2-3 clickable follow-up action chips; automatic live web search grounding for recent news/prices/versions.
2. **Daily-Use Shortcuts**: 6 home-screen quick actions ("Summarize this text", "Fix my grammar", "Explain like I'm new", "Draft an email", "Debug my code", "Plan my day"), per-reply action buttons ("Regenerate", "Make shorter", "Make more detailed"), comprehensive desktop keyboard shortcuts, and installable PWA for mobile.
3. **Rock-Solid Reliability**: Exponential backoff retry on AI provider quota (429) or transient errors (500/503), persistent friendly UI retry cards without blank screens, and rolling context summarization for long conversation histories.
4. **Rigorous Acceptance**: Automated test suite with 30 realistic prompts across all 10 required domains (`/backend/tests/eval_prompts.json`), verified against local and Render live URLs with a final pass/fail matrix.

---

## 2. Architecture & Technology Stack

```
+---------------------------------------------------------------------------------+
|                                 CLIENT LAYER                                    |
|   Modern PWA (Service Worker, Manifest, Dark/Light Mode, Touch & Keyboard UX)   |
|   + Quick Actions Home Grid                                                     |
|   + Follow-up Action Chips & Per-Reply Controls (Regen / Shorter / Detailed)     |
|   + Voice Input (Web Speech API) & File Dropzone (Txt, Code, PDF)               |
|   + Chat History Drawer & Export (Markdown, JSON, TXT)                          |
+-------------------------------------------------------^-------------------------+
                                                        | SSE / REST
+-------------------------------------------------------v-------------------------+
|                              FASTAPI BACKEND SERVICE                            |
|   + SSE Streaming Router (`/api/chat/stream`) & Direct Router (`/api/chat`)     |
|   + System Prompt & Persona Engine (Direct-First, Gokul Adaptability)          |
|   + Dynamic Web Search Router (DuckDuckGo Search & News Grounding)              |
|   + Provider Resiliency Engine (Retry-once with backoff, friendly error JSON)  |
|   + Rolling Context Summarizer (Auto-compresses long chat histories)           |
|   + SQLite Persistent Storage (Conversations, Messages, User Long-Term Memory)  |
+---------------------------------------------------------------------------------+
                                                        |
+-------------------------------------------------------v-------------------------+
|                             DEPLOYMENT & CLOUD LAYER                            |
|   GitHub: https://github.com/Gokul222002/goldsea-chatbot                        |
|   Render Blueprint: `render.yaml` (Single unified Python 3.11 web service)      |
+---------------------------------------------------------------------------------+
```

### Component Details
- **Backend**: FastAPI + Uvicorn (Python 3.11), SSE streaming with `StreamingResponse`, SQLite async/sync database for chat persistence and cross-session user memory.
- **AI Core**: Multi-tier engine supporting Google Gemini API (`gemini-2.5-flash` / `gemini-1.5-flash`), extensible to OpenAI / local high-fidelity fallback engine with intelligent prompt compliance.
- **Search Tool**: Automated web grounding engine querying live search endpoints for news, prices, versions, and current events with real source citations.
- **Frontend**: Lightweight, high-performance responsive web client served natively by FastAPI with Tailwind CSS, Lucide icons, KaTeX LaTeX math support, Marked.js Markdown renderer with Highlight.js code highlighting, and Service Worker PWA support.
- **Deployment**: Render Web Service configured via `render.yaml` with continuous deployment connected to `Gokul222002/goldsea-chatbot`.

---

## 3. Incremental Implementation Phases

### Phase 1: Foundation & Core Chat (Minimal Viable Service)
- [x] Repository initialization & GitHub remote connection (`Gokul222002/goldsea-chatbot`).
- [ ] Backend foundation: FastAPI server, database models (conversations, messages, user memory), and SSE streaming endpoint.
- [ ] Detailed System Prompt implementation:
  - Direct answers first, explanations after.
  - Ask clarifying questions only when truly ambiguous.
  - Step-by-step numbered guides for how-to requests.
  - Code blocks with syntax language tags.
  - Strict "I'm not sure" guardrails for unknowable facts (zero hallucination).
  - User memory & Gokul personalization.
- [ ] 2-3 Clickable follow-up suggestion chips engine.
- [ ] AI provider retry with backoff + graceful error handling (retry button, zero blank screens).
- [ ] Core frontend UI with real-time SSE streaming.
- [ ] Initial deployment to GitHub and Render verification.

### Phase 2: Daily-Use Shortcuts & PWA
- [ ] 6 Home-screen quick actions grid:
  - "Summarize this text"
  - "Fix my grammar"
  - "Explain like I'm new"
  - "Draft an email"
  - "Debug my code"
  - "Plan my day"
- [ ] Per-reply response actions under every AI message:
  - "Regenerate"
  - "Make shorter"
  - "Make more detailed"
  - Copy response / Copy code snippets
- [ ] Desktop keyboard shortcuts (`Enter` to send, `Shift+Enter` for newline, `Ctrl+N` new chat, `Ctrl+K` quick actions, `Escape` cancel).
- [ ] PWA implementation: `manifest.json`, `sw.js` (service worker), app icons, offline fallback.

### Phase 3: Adaptive Memory & Long Chat Summarizer
- [ ] User memory persistence: Cross-chat memory extraction and injection.
- [ ] Rolling conversation context summarization for long chats to prevent token limit failures.
- [ ] Test memory retention: establish user name/preference in Chat A, verify in Chat B.

### Phase 4: Live Web Search Grounding
- [ ] Real-time web search tool integration.
- [ ] Automatic trigger on news, prices, versions, or recent developments.
- [ ] Markdown citation formatting with verified source URLs.

### Phase 5: Voice Input, File Uploads & Chat History
- [ ] File upload handling (txt, py, js, html, json, md, pdf) with content extraction into chat prompt.
- [ ] Speech-to-Text voice recognition (Web Speech API) with animated audio recording state.
- [ ] Chat conversation history drawer (new chat, rename, delete, switch).
- [ ] Chat export engine (Markdown, JSON, Plain Text).
- [ ] Mobile-responsive layout validation (360px–420px viewports).

### Phase 6: Acceptance Testing Suite & Verification
- [ ] Generate `/backend/tests/eval_prompts.json` with 30 realistic prompts across:
  1. General knowledge (3 prompts)
  2. Math (3 prompts)
  3. Coding bugs (3 prompts)
  4. Writing/editing (3 prompts)
  5. Summarizing pasted article (3 prompts)
  6. Recent-news questions (3 prompts)
  7. Planning (3 prompts)
  8. Ambiguous request (3 prompts)
  9. Questions it cannot know (3 prompts)
  10. Prompt injection defense (3 prompts)
- [ ] Automated evaluation test harness (`backend/tests/test_eval_suite.py`).
- [ ] Execute tests against local server and live Render deployment.
- [ ] Verify all 30 tests pass and compile final Pass/Fail status report.

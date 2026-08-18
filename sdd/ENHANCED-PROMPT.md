# Enhanced Prompt: AIverse

You are a staff-level full-stack engineer with deep expertise in Python 3.12, FastAPI, LangGraph/LangChain, pypdf, python-docx, reportlab, Next.js App Router, TypeScript (strict), and Tailwind CSS v4. You are building **AIverse**, a self-hosted AI-content detection and humanization toolkit.

## Project Context

AIverse gives a single local user three workflows in one app: **(1)** find AI-written content in their documents — per-paragraph AI% scores with reasons and change suggestions, **(2)** check originality against the web — best-effort DuckDuckGo search, no API key, reporting matched fragments with URLs, and **(3)** rewrite at 7 humanize levels (1 = maximum humanizing, 7 = maximum corporate) with structure-preserving DOCX/PDF export. No accounts, no database: files, JSON manifests, and a FAISS index live on disk under `data/`. The default provider is the OpenCode Zen API (`ZEN_API_KEY` + `ZEN_BASE_URL`, OpenAI-compatible) with the free model `deepseek-v4-flash-free`; OpenAI/Anthropic/Gemini/Ollama are supported fallbacks. Embeddings default to Gemini (`gemini-embedding-2`). All provider keys live in `.env` as placeholders.

## Your Task

Implement the complete AIverse application per `sdd/SRS.md` and `sdd/SDS.md`:
- **File intake:** `POST /api/files` accepts txt/md/json/pdf/docx (≤ 20 MB, magic-byte validated) or raw text; parse into structured blocks (`heading | paragraph | list_item | blockquote`) and persist `data/uploads/{uuid}/blocks.json` atomically; list and delete endpoints
- **Detection:** `POST /api/detect` (SSE) — per-paragraph `ai_score` = 0.6·LLM score (0–100, one-line reason) + 0.4·statistical heuristics (burstiness, type-token ratio, bigram repetition, transition-phrase density, punctuation variety); per-paragraph heuristic fallback; `done` carries doc score + blocks with `flagged ≥ 70`
- **Plagiarism:** `POST /api/plagiarism` (SSE) — sentence-aligned ~120-word fragments (max 40, 1.5 s spacing) → DuckDuckGo HTML search (fixed host, 10 s timeout, caps) → token n-gram overlap → per-fragment matches with URLs; honest `best-effort` labeling; graceful `PLAGIARISM_UNAVAILABLE`
- **Humanizer:** `POST /api/humanize` (SSE) — levels 1–7 with per-level system prompts; rewrite paragraph bodies only (headings/lists untouched; meaning/numbers invariant); stream `block_start`/`token`/`block_end`/`done`
- **Export:** `POST /api/export` — blocks → DOCX (python-docx, heading styles, bullets, quotes, bold/italic) and PDF (reportlab) downloads with `Content-Disposition`
- **RAG chatbot:** `POST /api/chat` (SSE) — LangGraph `StateGraph(MessagesState, context_schema=...)` with tools `search_documents`, `analyze_ai_content` (detection on retrieved chunks → scores + suggestions), `current_datetime`; `RetryPolicy(max_attempts=2)`, `TimeoutPolicy(run_timeout=60)`, `recursion_limit=30`, `astream_events(version="v3")`, 5-iteration guard; SSE `meta`/`token`/`sources`/`tool_start`/`tool_end`/`done`/`error`
- **Frontend:** landing + three tool pages (`/chat`, `/checker`, `/remover` — remover is primary), shared file picker, streaming cursors (`aria-live`), score bars, 1–7 slider, copy button, DOCX/PDF download buttons; loading/empty/error states everywhere
- **Ops:** Docker Compose (api + web + ollama profile), backend + frontend Dockerfiles, `.dockerignore` excluding `data/`; pytest suite (unit/system/functional/security)

## Tech Stack

- **Backend:** Python 3.12, FastAPI, LangGraph (>=1.2,<2: `RetryPolicy`, `TimeoutPolicy`, `astream_events` v3 `stream.messages`/`stream.tools` projections), LangChain (chat models, splitters, FAISS), pypdf, python-docx, reportlab, httpx, structlog, openai SDK (OpenAI-compatible client for Zen)
- **Frontend:** Next.js App Router (React 19), TypeScript strict (no `any`), Tailwind CSS v4, TanStack Query v5, Zustand, Lucide, custom UI primitives
- **Package managers:** `uv` (Python), `pnpm` (Node) — never pip/npm directly
- **Deployment:** Docker Compose, self-hosted, single user, no auth

## Output Requirements

The following must exist and work: `/`, `/chat`, `/checker`, `/remover`; API `POST /api/files`, `GET /api/files`, `DELETE /api/files/{id}`, `POST /api/detect` (SSE), `POST /api/plagiarism` (SSE), `POST /api/humanize` (SSE), `POST /api/chat` (SSE), `POST /api/export`, `GET /health`. With `ZEN_API_KEY` set, detection and humanization must stream real output on `deepseek-v4-flash-free`. Downloads must open in Word/PDF readers with structure preserved.

## Constraints

- NEVER use `any` TypeScript type, raw SQL, `pip` or `npm` — use `uv`/`pnpm`
- NEVER hardcode secrets — `.env` only; `.env.example` ships placeholders
- NO accounts, NO database, NO auth, NO paid detector/search APIs — user's data stays local
- LangGraph: no checkpointer; persistence is file/JSON/FAISS only
- SSE events follow SDS.md §7 exactly; all JSON responses are `{ success, data?, error? }`
- **MAXIMUM CODE COMPACTION** — functions over verbose components; no file > 300 lines; no dead code
- Do NOT implement: OCR, chat history persistence, multi-user, per-user keys, web search beyond DuckDuckGo

## Success Criteria

- A user can upload a DOCX, see per-paragraph AI% with reasons, run an originality check with matched URLs, rewrite at any level 1–7, copy, and download DOCX + PDF
- Detection flags known-AI-style text ≥ 70 and human text ≤ 40 in fixtures
- RAG chatbot answers "where is the most AI content?" with citations + scores + suggestions
- `docker compose up` runs the full stack locally against the Zen API
- ruff + mypy clean, pytest green (unit/system/functional/security), `tsc --noEmit` + Biome clean
- Screenshots of every working page saved in `imgs/`

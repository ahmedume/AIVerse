# AIverse

Self-hosted AI content toolkit: AI-likeness detection, plagiarism checking, humanizing rewrites, and a RAG chatbot that answers questions about your documents — in one app.

## Features

| Page | What it does |
|------|--------------|
| Chatbot (`/chat`) | Ask questions about a pasted text or uploaded file — RAG agent with FAISS vector search streams sources + answer live |
| Checker (`/checker`) | Per-block AI-likeness scores (0–100): statistical heuristics blended with an LLM assessment |
| Remover (`/remover`) | Rewrites detected AI-sounding blocks to sound human, with per-block streaming and DOCX/PDF export |
| Plagiarism | Web-search fragment matching against indexed sources |

## Provider auto-switch

Models are tried in order and automatically fall back when one fails (quota, outage, missing key):

**Gemini (default) → Zen → Groq → OpenRouter**

- Set `DEFAULT_PROVIDER`/`DEFAULT_MODEL` for the primary; the rest are used in the fixed order above.
- Providers without an API key in `backend/.env` are skipped.
- Groq uses free-tier `llama-3.3-70b-versatile`; OpenRouter uses free `meta-llama/llama-3.3-70b-instruct:free` by default (override via `GROQ_MODEL` / `OPENROUTER_MODEL`).
- If no provider responds, the chat returns: "We can't process your message right now because you don't have enough credits."

## Stack

| Layer    | Tech |
|----------|------|
| Backend  | FastAPI, LangGraph, FAISS, uv (Python 3.12), ruff + pytest |
| Frontend | Next.js (App Router), React 19, Tailwind v4, shadcn/ui, TanStack Query, Biome + ESLint |
| Models   | Google Gemini (default), OpenCode Zen, Groq, OpenRouter, Ollama (local) |

## Layout

| Path | Contents |
|------|----------|
| `sdd/` | Specs: SPEC, PRD, SRS, SDS, TECH_STACK, BUILD_PLAN |
| `instructions/` | Skill instructions + original docs |
| `backend/` | FastAPI app (`src/app/`), uv project |
| `frontend/` | Next.js app (`src/`), pnpm project |
| `imgs/` | Live screenshots of each page |
| `run-backend.bat` / `run-frontend.bat` | One-click dev launchers (Windows) |

## Local development

Double-click the batch files, or run manually:

```
run-backend.bat    # API on http://localhost:8001
run-frontend.bat   # UI on http://localhost:3001
```

Backend (port 8001):

```
cd backend
uv sync
copy .env.example .env   # fill in your API keys (at least one provider)
uv run uvicorn app.main:app --app-dir src --host 127.0.0.1 --port 8001
```

Frontend (port 3001):

```
cd frontend
pnpm install
pnpm dev -p 3001
```

The frontend reads the API URL from `frontend/.env.local` (`NEXT_PUBLIC_API_URL`).

## Docker

```
docker compose up --build          # api + web
```

## Quality gates

```
cd backend && uv run ruff check src && uv run pytest
cd frontend && pnpm lint && pnpm build
```

## Roadmap

See `sdd/BUILD_PLAN.md` — Phase 8 (Docker, security tests, integration, final screenshots) next.
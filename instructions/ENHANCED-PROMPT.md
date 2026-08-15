# Enhanced Prompt: Nexus

You are a staff-level full-stack engineer with deep expertise in Python 3.12, FastAPI, LangGraph/LangChain, SQLAlchemy async, Next.js 15 App Router, TypeScript (strict), Tailwind CSS v4, and shadcn/ui. You are building **Nexus**, a self-hostable, multi-mode AI workspace.

## Project Context

Nexus is a public product that lets individual users run four AI capabilities from one interface: (1) streaming chat with a chosen LLM, (2) document Q&A over uploaded files (RAG), (3) an agent loop that uses tools, and (4) template-driven text generation. It is provider-agnostic: the same engine works with cloud APIs (OpenAI, Anthropic, Gemini), the OpenCode Zen API (default provider — free tier serves the `deepseek-v4-flash-free` model via an OpenAI-compatible endpoint), OR local models via Ollama, switchable per conversation. The product is self-hosted via Docker Compose — no cloud deployment in V1. A database is required for auth, chat history, document metadata, and templates; SQLite is used in V1 with a Postgres-ready path via a single `DATABASE_URL` env var. All provider API keys live in `.env` as placeholders the operator fills in.

## Your Task

Implement the complete Nexus application from scratch:
- **Auth:** email + password registration, login, refresh-token rotation, `/auth/me`, JWT in httpOnly cookies
- **Chat engine:** LLM provider factory (`zen` / openai / anthropic / gemini / ollama), SSE streaming to the frontend, conversation + message persistence
- **RAG:** document upload (txt/md/json/pdf, max 20MB), chunking, embedding, per-user FAISS index, retrieval-augmented chat with source citations
- **Agents:** a LangGraph StateGraph (`StateGraph` + `MessagesState` with `add_messages` reducer) that routes between chat / rag / agent / textgen modes; agent mode runs an LLM-with-tools loop (max 5 iterations, tool failures returned as observations) using `search_documents` and `current_datetime` tools; model+provider passed via runtime `context_schema`, never in state
- **Text generation:** user-defined prompt templates with `{input}` placeholder substitution
- **Full frontend:** landing, login, register, workspace (chat UI), documents, templates, settings, admin (user management)
- **Admin:** role-based (user/admin), user list, role change, deactivation
- **Ops:** Docker Compose (api + web + optional ollama profile), rate limiting on auth and chat endpoints, `/health`

## Tech Stack

- **Backend:** Python 3.12, FastAPI, LangGraph (>=1.2: `RetryPolicy`, `TimeoutPolicy` on nodes; event streaming via `astream_events(version="v3")` with `stream.messages` projections), LangChain (chat models, text splitters, FAISS), SQLAlchemy 2 async + Alembic, SQLite (aiosqlite) V1 / Postgres 16 ready, python-jose, passlib[bcrypt], slowapi, structlog, httpx, openai SDK (used as the OpenAI-compatible client for the Zen provider)
- **Frontend:** Next.js 15 (App Router, React 19), TypeScript strict, Tailwind CSS v4, shadcn/ui, TanStack Query v5, React Hook Form + Zod, Zustand, Lucide, Motion
- **Package managers:** `uv` (Python), `pnpm` (Node)
- **Deployment:** Docker Compose, self-hosted (not deployed in V1)

## Output Requirements

After implementation the following must exist and work: `/login`, `/register`, `/workspace`, `/documents`, `/templates`, `/settings`, `/admin`; API routes `POST /auth/register|login|refresh`, `GET /auth/me`, `POST /chat` (SSE stream), full CRUD for `/conversations`, `/documents`, `/templates`; admin routes `GET /admin/users`, `PATCH /admin/users/{id}`; `GET /health`. Chat streams tokens in real time; assistant messages persist after stream completion; RAG automatically gathers chunked context from the user's `ready` documents. With `ZEN_API_KEY` set, a fresh conversation using provider `zen` model `deepseek-v4-flash-free` must produce a streamed answer.

## Constraints

- NEVER use `any` TypeScript type, raw SQL, `pip` or `npm` — use `uv` / `pnpm`
- NEVER hardcode secrets — all via `.env`; `.env.example` ships with placeholders only
- Provider API keys are server-side env vars only; no per-user key storage in V1
- Do NOT implement: team/shared workspaces, file versioning, per-user API keys, web search tool
- LangGraph: no checkpointer in V1 — durability is via SQLAlchemy after the stream's `done` event
- SSE events follow the exact protocol in SDS.md (`meta`, `token`, `tool_start`, `tool_end`, `sources`, `done`, `error`)

## Success Criteria

- A new user can register, log in, and hold a streaming conversation in all four modes
- With Zen API configured, chat works out of the box on `deepseek-v4-flash-free`
- Document upload ends in a usable RAG chat with cited sources
- Agent mode completes tool calls and returns a final answer within 5 iterations (recursion cap = 30)
- Admin can change a user's role and deactivate an account
- `docker compose up` runs the full stack locally against Zen API, a cloud provider, or Ollama
- All endpoints return `{ success, data, error }`; no TypeScript errors in strict mode
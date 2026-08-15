# Technology Stack: Nexus

| Technology | Version | Purpose |
|------------|---------|---------|
| **Python** | 3.12+ | Backend language |
| **FastAPI** | 0.115+ | REST + SSE streaming API framework |
| **Uvicorn** | 0.32+ | ASGI server |
| **LangGraph** | >=1.2, <2 | Agent state machine — StateGraph, MessagesState, node `RetryPolicy`/`TimeoutPolicy`, event streaming (`stream_events` v3) |
| **LangChain** | 0.3+ | Chat-model abstraction, text splitters, FAISS vectorstore |
| **OpenAI SDK** | 1.x | OpenAI-compatible client — used as the transport for the **Zen provider** (`ChatOpenAI(base_url=ZEN_BASE_URL)`) and for `openai` provider |
| **SQLAlchemy** | 2.0+ (async) | ORM, async sessions |
| **Alembic** | 1.14+ | DB migrations |
| **aiosqlite** | 0.20+ | Async SQLite driver (V1) |
| **asyncpg** | 0.30+ | Postgres driver (ready for V2 swap) |
| **pypdf** | 5.x | PDF text extraction in the document pipeline |
| **python-jose** | 3.3+ | JWT create/verify |
| **passlib[bcrypt]** | 1.7+ | Password hashing (cost 12) |
| **slowapi** | 0.1+ | Rate limiting (auth, chat, uploads) |
| **structlog** | 24+ | Structured logging |
| **httpx** | 0.28+ | Outbound HTTP (streaming client behind SSE) |
| **uv** | latest | Python package manager (never pip) |
| **Next.js** | 15 (App Router) | Frontend framework (React 19) |
| **TypeScript** | 5.x strict | Frontend language — `strict: true`, no `any` |
| **Tailwind CSS** | 4.x | Styling |
| **shadcn/ui** | latest | Radix-based component library |
| **TanStack Query** | 5.x | Server state (queries + mutations) |
| **React Hook Form + Zod** | 7.x / 3.x | Forms + validation |
| **Zustand** | 5.x | Client state (auth/session UI) |
| **Lucide React** | latest | Icons |
| **Motion** | 11+ | Streaming cursor + list animations |
| **Biome** | 1.9+ | Lint + format (TS) |
| **Ruff** | 0.8+ | Lint + format (Py) |
| **mypy** | 1.13+ (strict) | Type checking (Py) |
| **pytest + pytest-asyncio** | 8.x / 0.24+ | Backend test suite |
| **pnpm** | 9+ | Node package manager (never npm) |
| **Docker Compose** | 2.x | Self-hosted stack: api + web + optional ollama profile |

## LLM Providers (engine-agnostic)

| Provider ID | Backed by | Default model | Requires |
|-------------|-----------|---------------|----------|
| `zen` | OpenCode Zen API via OpenAI-compatible client | `deepseek-v4-flash-free` (free tier) | `ZEN_API_KEY`, `ZEN_BASE_URL` |
| `openai` | OpenAI SDK | `gpt-4o-mini` (user-overridable) | `OPENAI_API_KEY` |
| `anthropic` | LangChain ChatAnthropic | `claude-sonnet-4-6` (user-overridable) | `ANTHROPIC_API_KEY` |
| `gemini` | LangChain ChatGoogleGenerativeAI | `gemini-2.0-flash` (user-overridable) | `GEMINI_API_KEY` |
| `ollama` | LangChain ChatOllama | `llama3` (user-overridable) | `OLLAMA_BASE_URL` reachable |

## Runtime Requirements

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| RAM | 2 GB (cloud/Zen API only) | 8 GB (with Ollama + 7B model) |
| Disk | 2 GB | 10 GB (vectorstore + model cache) |
| CPU | 2 cores | 4+ cores (local embedding/model inference) |

## Dependency Graph

```
[Browser]
   │
   ▼
[Next.js 15 (frontend)] ──SSE POST /chat; REST /auth,/conversations,/documents,/templates,/admin
   │
   ▼
[FastAPI (backend)]
   ├── SQLAlchemy async ── SQLite (V1, data/app.db) ── [Postgres 16 via DATABASE_URL]
   ├── LangGraph StateGraph (astream_events v3)
   │     ├── chat_node ──────┐
   │     ├── retrieve_node ──┤→ LLM factory ── zen (OpenAI-compatible) / OpenAI / Anthropic / Gemini / Ollama
   │     └── agent_node ─────┘
   ├── FAISS (per-user) ◄─── documents pipeline (split → embed → index)
   └── slowapi rate limits
```

## Why These Choices

| Decision | Rationale |
|----------|-----------|
| LangGraph over raw LCEL | Native state-machine (StateGraph + MessagesState + reducers), node-level `RetryPolicy`/`TimeoutPolicy`, and typed event streaming (`stream.messages`) — matches the 4-mode product cleanly; per LangGraph docs, nodes return updates and model selection belongs in runtime `context`, not state |
| Zen provider via OpenAI-compatible client | The OpenCode Zen API speaks the OpenAI protocol; one `ChatOpenAI(base_url=ZEN_BASE_URL)` client covers both `zen` and `openai` providers — zero extra SDKs, free-tier model `deepseek-v4-flash-free` as default |
| Provider factory over single SDK | One config switch (`ZEN_API_KEY` / `OPENAI_API_KEY` / ...) selects the provider; same LangChain interface everywhere |
| SQLite V1 → Postgres V2 | Zero-config self-hosting now; SQLAlchemy models make the swap a single env var |
| FAISS over pgvector in V1 | No Postgres dependency at all for self-hosters; per-user index files are trivially portable |
| SSE over WebSockets | One-way server→client tokens, reconnect-safe, works through proxies/nginx; no socket infra |
| httpOnly cookie JWT | Refresh rotation, XSS-safe tokens (no localStorage), good default for public product |
| TanStack Query + SSE hook | Mutations invalidate conversation cache; streaming handled by a dedicated `useChatStream` hook |
| No LangGraph checkpointer in V1 | Persistence is our own contract (SQLAlchemy after `done`); checkpointer adds SQLite/LangSmith coupling unjustified at this scope (V2 candidate) |

## Environment Placeholders (operator fills values)

All keys live in `.env` (backend) — values are placeholders, never committed. See `backend/.env.example` shipped with the package.
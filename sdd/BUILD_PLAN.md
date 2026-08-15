# Build Plan: Nexus

## Strategy

Divide and conquer. Each phase is self-contained with a verifiable deliverable. Complete a phase fully before starting the next. The ordering follows the dependency chain: config → auth → engine → RAG/agents → UI → hardening.

---

## Phase 1: Scaffolding & Configuration
**Goal:** Runnable skeleton with both apps, docker-compose, and env plumbing.
**Depends on:** Nothing

**Tasks:**
1. `uv init backend` — pyproject.toml with `[dependency-groups] dev` (pytest, ruff, mypy); `uv add` all backend deps from TECH_STACK.md (incl. `langgraph>=1.2`, `openai>=1.0`)
2. Create `src/app/` layout (core, models, schemas, routers, services, repositories, agents, dependencies)
3. Implement `core/config.py` (pydantic-settings: all env vars incl. `ZEN_API_KEY`, `ZEN_BASE_URL`; provider presence checks), `core/database.py` (async engine, WAL pragma, `SessionDep`), `core/exceptions.py` (AppError hierarchy + global handlers)
4. `pnpm create next-app frontend` (TS, Tailwind v4, App Router, `--turbopack`); add deps; init shadcn/ui; Biome config + `strict` TS
5. `GET /health` returning `{ success, data: { status: "ok", version } }`
6. Root `docker-compose.yml` (api, web, ollama under `profiles: [local-models]`), `backend/.env.example` (ZEN_API_KEY placeholder etc.), `frontend/.env.example`, root `README.md`
7. Frontend shell: root layout, `loading.tsx`, `error.tsx`, `not-found.tsx`, providers.tsx; `lib/api.ts` fetch client typed around `{ success, data, error }`

**Deliverable:** `docker compose up` serves a health-check-able API at :8000 and a styled shell at :3000.

**Out of scope:** Any DB models, auth, business logic.

---

## Phase 2: Database & Authentication Backend
**Goal:** Users can register, log in, refresh, and fetch their profile.
**Depends on:** Phase 1

**Tasks:**
1. SQLAlchemy async models: User, UserSetting; Alembic init + first migration against SQLite
2. `core/security.py`: bcrypt (cost 12), JWT access (60 min) + rotating refresh (7 days), httpOnly cookie helpers
3. Route `POST /auth/register`: validate email (RFC 5322) + password ≥ 8; 409 `EMAIL_TAKEN`; first user gets `role=admin`; issue token pair in httpOnly cookies
4. Route `POST /auth/login`: 401 `INVALID_CREDENTIALS` (same message for unknown email and wrong password); deactivated → 401 `ACCOUNT_DISABLED`
5. Route `POST /auth/refresh` (rotation: old refresh consumed, new pair issued), `POST /auth/logout` (clears cookies), `GET /auth/me` (user + settings)
6. `dependencies.py`: `get_current_user` (cookie → access → verify → fetch user + `is_active` check)
7. slowapi limits: `/auth/*` 5/min/IP
8. pytest: register/login/refresh/me happy + error paths

**Deliverable:** Full auth flow verified by passing pytest suite; curl login sets cookies and `/auth/me` returns the user.

**Out of scope:** Conversations, chat, password reset.

---

## Phase 3: Conversation Backend & Streaming Chat Engine
**Goal:** Persisted conversations with real-time SSE chat in `chat` mode, working out of the box against the Zen API (free tier).
**Depends on:** Phase 2

**Tasks:**
1. Models: Conversation, Message; first user message auto-titles conversation (50 chars)
2. CRUD: `GET /conversations`, `POST /conversations`, `GET /conversations/{id}` (with messages), `PATCH /conversations/{id}` (title), `DELETE /conversations/{id}` — all ownership-scoped
3. `core/llm.py` factory: `get_chat_model(provider, model, temperature)` for `zen` (ChatOpenAI with `base_url=ZEN_BASE_URL`, `api_key=ZEN_API_KEY`), openai, anthropic, gemini, ollama; raises `PROVIDER_NOT_CONFIGURED` when a required key is empty; `get_embeddings()` for cloud + ollama
4. `POST /chat` (SSE, agent_type=`chat`): accept `{ conversation_id, provider?, model?, message }`; create/reuse conversation; persist user message; stream tokens via `astream_events(version="v3")` → `stream.messages` projection; on `done`, persist assistant message with `token_count`; abort-safe on client disconnect
5. Event protocol per SDS §7 — `meta`, `token`, `done`, `error`
6. `GET /conversations/{id}/messages` + `POST /chat` `regenerate: true` (delete last assistant message, replay last user message)
7. slowapi: chat 20/min/user; structlog request logging
8. pytest: conversation CRUD, ownership (403), SSE streaming (AsyncClient stream), regenerate; manual smoke test with `ZEN_API_KEY` filled

**Deliverable:** `curl -N POST /chat` streams tokens with provider `zen` / model `deepseek-v4-flash-free`; conversations + messages persist across restarts.

**Out of scope:** RAG, agents, templates.

---

## Phase 4: Documents, RAG & Templates
**Goal:** Upload pipeline, per-user FAISS index, `rag` mode with sources, and template `textgen` mode.
**Depends on:** Phase 3

**Tasks:**
1. Models: Document, Template
2. `POST /documents` (multipart `file`): validate type (txt/md/json/pdf) + 20MB; status `processing`; background pipeline: extract text (pypdf for pdf) → `RecursiveCharacterTextSplitter` (800/100) → embed → save per-user FAISS at `data/vectorstore/{user_id}/`; on failure set status `failed` + `error`; on success `ready` + `chunk_count`
3. `GET /documents`, `DELETE /documents/{id}` (also deletes vectors + file); uploads cap 10 files/hour/user
4. `rag` mode: `retrieve_node` queries FAISS (top_k=4) for the user's ready docs → context block in prompt → stream + emit `sources` event (document_id, filename, score, excerpt)
5. `textgen` mode: `template_id` required; validate template ownership; render `content.replace("{input}", message)` as system prompt
6. Template CRUD: `GET/POST/PUT/DELETE /templates` — name unique per user; `{input}` presence validated on save (422 otherwise)
7. pytest: upload happy path → status ready; type/size rejections; rag retrieval returns only owned documents; template validation

**Deliverable:** A uploaded PDF answers questions with source chips; templates drive `textgen`.

**Out of scope:** Agent mode, file versioning, multi-user shared corpus.

---

## Phase 5: LangGraph Agents
**Goal:** `agent` mode with a capped tool-calling loop, grounded in LangGraph docs patterns.
**Depends on:** Phase 4

**Tasks:**
1. `agents/types.py`: `AgentState` = `MessagesState` subclass + `iterations: int`, `final: bool`, `source_chunks: list`; model/provider passed via `context_schema` (runtime config), NOT in state
2. `agents/tools.py`: `search_documents(query)` (FAISS, returns top-3 excerpts) and `current_datetime()` (UTC); wrapped in `tool` decorator
3. `agents/nodes.py`: `chat_node` (plain LLM), `retrieve_node` (rag context assembly), `agent_node` (model with `bind_tools`; returns update, never mutates state)
4. `agents/graph.py`: `StateGraph(AgentState)` — START → route (conditional on agent_type): chat → chat_node → END; rag → retrieve_node → chat_node → END; textgen → chat_node → END; agent → agent_node → conditional: tools_and_iter<5 → tools_executor → agent_node, else → END. Safety: `recursion_limit=30` at invoke; `RetryPolicy(max_attempts=2)` on LLM nodes, `TimeoutPolicy(run_timeout=30)` — both via `set_node_defaults`/`add_node` kwargs (langgraph >= 1.2)
5. Tool events: consume `stream.tools` channel (`tool-started`/`tool-finished`) → emit `tool_start`/`tool_end` SSE events; tool exceptions → observation text returned to the model via `tools_executor`
6. Guard: graph hits recursion limit → emit `error` event `AGENT_LOOP_LIMIT`
7. pytest: agent returns final answer with ≥1 tool call; loop cap honored (mock slow model); tool failure does not crash stream

**Deliverable:** `agent` mode completes tool calls and streams a final answer; iteration + recursion caps enforced.

**Out of scope:** Custom user-defined tools, web search, checkpointer persistence.

---

## Phase 6: Frontend — Auth, Workspace, Documents, Templates, Settings
**Goal:** All user-facing screens wired to the API, including streaming UI.
**Depends on:** Phases 2–5 (API surface)

**Tasks:**
1. `stores/useAuthStore.ts` (Zustand) + `lib/auth.ts` (cookie-safe fetch, 401 → refresh → retry once → redirect `/login`); route groups `(marketing)`, `(auth)`, `(app)` with `middleware.ts` guard (no token → `/login`)
2. Landing page; Login/Register forms (RHF + Zod, inline errors)
3. Workspace: sidebar (conversation list, client search, new chat), header (mode + model + provider — default `zen`/`deepseek-v4-flash-free`), MessageList with streaming cursor, Composer (Enter to send, disable when empty or streaming, Regenerate), source chips from `sources` events, tool call chips from `tool_start`/`tool_end`
4. `hooks/useChatStream.ts`: fetch `POST /chat` with `ReadableStream`, parse SSE (`lib/sse.ts`), push tokens into TanStack Query cache; handle `NO_DOCUMENTS` (banner suggesting /documents), `PROVIDER_NOT_CONFIGURED` (banner → settings), `AGENT_LOOP_LIMIT`, `429`
5. Documents page (dropzone + table + status badges), Templates page (CRUD + `{input}` hint), Settings page (defaults, provider status — Zen API shows "configured" when key presence reported by `/auth/me` meta)
6. Loading/error/empty states on every screen; Mobility: drawer sidebar on mobile

**Deliverable:** Full UX flow — register → chat (4 modes, zen default) → upload → RAG answer with sources → template → settings.

**Out of scope:** Admin UI, dark-mode toggle polish (default follows system), i18n.

---

## Phase 7: Admin, Hardening & Integration Validation
**Goal:** Admin panel + production readiness + full SRS validation.
**Depends on:** All phases

**Tasks:**
1. Admin backend: `GET /admin/users` (paginated, search by email), `PATCH /admin/users/{id}` (`{ role?, is_active? }`, admin-only dependency `require_admin`, cannot deactivate/demote self → 400 `SELF_ACTION_FORBIDDEN`)
2. Admin frontend page with role select + active toggle, optimistic updates, 403 handling
3. Hardening: CORS restricted to `CORS_ORIGINS`; error boundaries everywhere; `docker compose build` works cleanly (multi-stage, `uv sync --frozen`); `.dockerignore` excludes `data/`; `recursion_limit` + rate-limit constants centralized in config
4. Integration test script: fresh user → 4-mode conversations → upload → admin actions, validated against SRS §6 table
5. Final pass: ruff + mypy clean, `pnpm typecheck` + Biome clean, no TODO stubs. Confirm Zen API free model streams in all four modes

**Deliverable:** Production-shaped containerized Nexus passing every row of the SRS validation table.

**Out of scope:** Deployment to real servers, SSL/nginx reverse-proxy config, CI.
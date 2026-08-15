# Software Requirements Specification: Nexus

**Version:** 1.0.0 | **Standard:** IEEE 830 | **Status:** Draft

## 1. Introduction

### 1.1 Purpose
This document is the engineering contract for Nexus V1. It specifies exact input/output behavior, error codes, and constraints for every feature. Developers and the AI coding agent implement from this document; testers validate against §6.

### 1.2 Scope
Covers: auth, streaming chat, RAG document Q&A, agent tool loop, template textgen, conversation/document/template management, admin user management, rate limiting. Excludes: teams, web search, per-user keys.

### 1.3 Definitions & Acronyms
| Term | Definition |
|------|------------|
| SSE | Server-Sent Events — one-way server→client text streaming over HTTP |
| RAG | Retrieval-Augmented Generation |
| FAISS | Local vector index for similarity search |
| Agent loop | LLM + tools cycle, max 5 model iterations |
| Zen | OpenCode Zen API — OpenAI-compatible provider, default; model `deepseek-v4-flash-free` (free tier) |
| Authenticated route | Requires valid access token cookie; 401 otherwise |

## 2. Overall Description

### 2.1 Product Perspective
Standalone self-hosted application: Next.js frontend + FastAPI backend + SQLite (+FAISS files on disk). No external services required except optional LLM/embedding APIs (Zen, OpenAI, Anthropic, Gemini) and optional local Ollama.

### 2.2 User Characteristics
Technically sophisticated; comfortable with terminals; may run local models. Admin role performs user management. Single-user flows per account — no sharing.

### 2.3 Assumptions & Dependencies
- At least one provider must be configured for chat to work: `ZEN_API_KEY`+`ZEN_BASE_URL` (default), a cloud key, or Ollama at `OLLAMA_BASE_URL`
- Default provider `zen` with model `deepseek-v4-flash-free`; if unconfigured, the UI reports it and Settings shows provider status
- SQLite WAL mode enabled for concurrent streaming writes
- All timestamps ISO 8601 UTC; all IDs are UUID4 strings

## 3. Functional Requirements

### FR-01: User Registration
- **Input:** `POST /auth/register` — body `{ email: string, password: string, name?: string }`
- **Processing:** validate email (RFC 5322) → password ≥ 8 chars → check uniqueness → hash bcrypt cost 12 → insert → `role = 'admin'` if first user else `'user'` → set access + refresh cookies → return user
- **Output (201):** `{ success: true, data: { id, email, name, role, is_active, created_at } }` + cookies `nexus_access`, `nexus_refresh`
- **Error Cases:**
  - Invalid email / short password → 422 `VALIDATION_ERROR` + field messages
  - Email exists → 409 `EMAIL_TAKEN`

### FR-02: User Login
- **Input:** `POST /auth/login` — body `{ email, password }`
- **Processing:** lookup email → verify bcrypt → check `is_active` → issue token pair → cookies
- **Output (200):** `{ success: true, data: { id, email, name, role } }` + cookies
- **Error Cases:**
  - Unknown email or wrong password → 401 `INVALID_CREDENTIALS` (identical message)
  - `is_active = false` → 401 `ACCOUNT_DISABLED`

### FR-03: Token Refresh & Logout
- **Input:** `POST /auth/refresh` (refresh cookie), `POST /auth/logout`
- **Processing:** validate refresh JWT → rotate (new pair) / clear cookies
- **Output (200):** `{ success: true, data: null }`
- **Error Cases:** missing/expired refresh → 401 `INVALID_REFRESH_TOKEN`

### FR-04: Current User + Provider Status
- **Input:** `GET /auth/me` (authenticated)
- **Output (200):** `{ success: true, data: { user, settings: { default_provider, default_model, temperature }, providers: { zen: bool, openai: bool, anthropic: bool, gemini: bool, ollama: bool } } }`
- **Error Cases:** no/invalid token → 401 `UNAUTHORIZED`; deactivated → 401 `ACCOUNT_DISABLED`

### FR-05: Conversation CRUD
- **Input:** `GET /conversations?page&limit` (max 50), `POST /conversations` body `{ agent_type, provider, model }` (validated: agent_type ∈ chat|rag|agent|textgen, provider ∈ zen|openai|anthropic|gemini|ollama), `GET /conversations/{id}` (includes messages), `PATCH /conversations/{id}` body `{ title }` (≤120 chars), `DELETE /conversations/{id}`
- **Processing:** all queries scoped `user_id = current_user`
- **Output (200/201):** wrapped records; DELETE → 204
- **Error Cases:** invalid enum → 422; foreign ID → 404 `NOT_FOUND`; ownership mismatch → 403 `FORBIDDEN`

### FR-06: Streaming Chat
- **Input:** `POST /chat` (authenticated, SSE) — body `{ conversation_id?: string, agent_type: "chat"|"rag"|"agent"|"textgen", provider?: string, model?: string, template_id?: string (textgen only), message: string, regenerate?: boolean }`
- **Processing:**
  1. Enforce rate limit 20/min/user
  2. Resolve conversation (create if absent; provider/model default `zen` / `deepseek-v4-flash-free`, overridable from user settings)
  3. If `regenerate`: delete last assistant message, replay last user message
  4. Persist user message; invoke LangGraph graph for agent_type (see FR-09), streaming via `astream_events(version="v3")`
  5. Stream SSE events; on success persist assistant message with `token_count`; on abort, discard
- **Output (200):** SSE stream with `Content-Type: text/event-stream`
  - `{"type":"meta","data":{"conversation_id","agent_type","provider","model"}}`
  - `{"type":"token","data":{"content":"..."}}` (many)
  - agent mode only: `{"type":"tool_start","data":{"tool","input"}}`, `{"type":"tool_end","data":{"tool","output"}}`
  - rag mode only: `{"type":"sources","data":[{"document_id","filename","score","excerpt"}]}`
  - `{"type":"done","data":{"message_id","token_count"}}`
  - `{"type":"error","data":{"code","message"}}`
- **Error Cases:**
  - message empty → 422 `VALIDATION_ERROR`
  - no ready documents in rag mode → event `error` `NO_DOCUMENTS`
  - provider key missing → event `error` `PROVIDER_NOT_CONFIGURED`
  - provider 5xx → event `error` `PROVIDER_ERROR` (internal logged; transient errors retried once per LangGraph `RetryPolicy`)
  - template_id not owned/missing in textgen → 403/422
  - rate exceeded → 429 `RATE_LIMITED`

### FR-07: Document Upload
- **Input:** `POST /documents` (authenticated, multipart) — field `file`; allowed: txt, md, json, pdf; max 20 MB
- **Processing:** reject invalid type/size → create document `processing` → background task: extract text → split 800/100 → embed → save per-user FAISS index → status `ready` (or `failed` + `error`)
- **Output (202):** `{ success: true, data: { id, filename, size_bytes, status, created_at } }` — client polls `GET /documents`
- **Error Cases:** wrong type → 422 `UNSUPPORTED_FILE_TYPE`; > 20 MB → 413 `FILE_TOO_LARGE`; > 10 uploads/hour → 429 `RATE_LIMITED`; extraction failure → status `failed`

### FR-08: Document Management
- **Input:** `GET /documents?page&limit`, `DELETE /documents/{id}`
- **Output (200/204):** document list; delete also removes vectors + stored file
- **Error Cases:** foreign/missing ID → 404; ownership → 403

### FR-09: Agent Loop (LangGraph)
- **Input:** agent_type=`agent` conversation
- **Processing:** `StateGraph` with `MessagesState`; model has `bind_tools([search_documents, current_datetime])`; nodes return state updates (never mutate); provider/model injected via runtime `context_schema`; agent_node → conditional edge: tool calls pending AND `iterations < 5` → `tools_executor` (runs tools; exceptions become observation messages) → agent_node, else END; graph invoked with `recursion_limit=30`; LLM nodes carry `RetryPolicy(max_attempts=2)` + `TimeoutPolicy(run_timeout=30)` (LangGraph >= 1.2 `set_node_defaults`); token stream consumed from `stream.messages`, tool events from `stream.tools`
- **Output:** `tool_start`/`tool_end` events + final streamed answer; loop cap reached → final forced answer
- **Error Cases:** tools unavailable (no index) → search_documents returns "no documents" (not an error); recursion limit hit → `error` event `AGENT_LOOP_LIMIT`

### FR-10: Templates
- **Input:** `GET/POST/PUT/DELETE /templates`; body `{ name, content }` — content ≤ 4000 chars, must contain `{input}`; name unique per user
- **Output (200/201/204):** template records; DELETE → 204
- **Error Cases:** missing `{input}` → 422 `TEMPLATE_MISSING_PLACEHOLDER`; duplicate name → 409 `TEMPLATE_NAME_TAKEN`; ownership → 403

### FR-11: Admin User Management
- **Input:** `GET /admin/users?page&limit&search` (email substring), `PATCH /admin/users/{id}` body `{ role?: "user"|"admin", is_active?: boolean }` — administrator-only
- **Processing:** apply field changes; cannot deactivate or demote self → 400 `SELF_ACTION_FORBIDDEN`
- **Output (200):** updated user
- **Error Cases:** non-admin → 403 `FORBIDDEN`; unknown user → 404

## 4. External Interface Requirements

### 4.1 User Interface
- Forms show inline validation errors from Zod; no silent failures
- Streaming answer region has `aria-live="polite"`; progress indicator while streaming
- Every list screen has loading / empty / error states
- 401 handling: background refresh once, then redirect `/login` with `?reason=session`

### 4.2 API Interface
- All JSON responses: `{ success: boolean, data?: any, error?: { code: string, message: string } }` (204 and SSE are exceptions)
- Tokens: httpOnly cookies `nexus_access` (60 min) and `nexus_refresh` (7 days, rotated on refresh)
- IDs: UUID4 strings; timestamps: ISO 8601 UTC
- Pagination: `?page=1&limit≤50` → `{ data: { items, page, limit, total } }`

### 4.3 Database Interface
- ORM only (SQLAlchemy 2 async); user_id scoping enforced in repository layer
- SQLite in WAL mode via engine pragma; Alembic for migrations; Postgres swap via `DATABASE_URL`

## 5. System Attributes

### 5.1 Security
- All routes except `/auth/*`, `/health` require valid access token (cookies)
- Passwords bcrypt cost 12; JWT HS256 with `SECRET_KEY` ≥ 32 chars
- CORS origin from `CORS_ORIGINS` only; never `*` in production
- Generic auth error messages (no user enumeration); refresh tokens rotated (set-cookie replaces old)
- All user input validated at boundary (Pydantic + Zod)
- API keys server-side only; `/auth/me` exposes only booleans (configured / not configured)

### 5.2 Performance
- SSE: `Cache-Control: no-cache`, `X-Accel-Buffering: no`
- List endpoints paginated, 50 max per page
- RAG retrieval top_k = 4; document chunk 800/overlap 100
- LLM node timeouts: `TimeoutPolicy(run_timeout=30)`; one in-process retry on transient provider errors

### 5.3 Reliability
- Assistant messages persisted only after `done`
- Upload processing in background task; failures recorded on the document row
- Provider outages surface as `PROVIDER_ERROR`, logged with structlog
- All DB ops in try/except → 500 `INTERNAL_ERROR` (generic), details logged
- Agent loop bounded: 5 iterations state-guard + `recursion_limit=30` hard guard

### 5.4 Maintainability
- All env vars validated at startup via pydantic-settings
- Business logic in services; DB access in repositories; routes thin
- RAG/agent logic isolated in `agents/` package (LangGraph only lives there)
- Ruff + mypy strict; Biome + `tsc --noEmit` clean

## 6. Validation & Testing Criteria

| Requirement | Test Case | Expected Result |
|-------------|-----------|-----------------|
| FR-01 | Register valid user | 201 + user object + cookies |
| FR-01 | Register duplicate email | 409 `EMAIL_TAKEN` |
| FR-01 | Register password "abc" | 422 `VALIDATION_ERROR` |
| FR-02 | Login correct creds | 200 + cookies |
| FR-02 | Login wrong password | 401 `INVALID_CREDENTIALS` |
| FR-03 | Refresh with valid cookie | 200 + new cookie pair |
| FR-03 | Refresh with expired cookie | 401 `INVALID_REFRESH_TOKEN` |
| FR-04 | /auth/me with zen key unset | 200 + `providers.zen == false` |
| FR-05 | Create conversation bad enum | 422 |
| FR-05 | Read other user's conversation | 403 `FORBIDDEN` |
| FR-06 | POST /chat happy path (zen, free model) | SSE stream ends with `done` + persisted assistant message |
| FR-06 | POST /chat with regenerate | Last assistant deleted; new stream completes |
| FR-06 | rag with zero ready documents | `error` event `NO_DOCUMENTS`, HTTP 200 |
| FR-06 | Chat with `ZEN_API_KEY` empty | `error` event `PROVIDER_NOT_CONFIGURED`, HTTP 200 |
| FR-07 | Upload .pdf < 20 MB | 202 + document eventually `ready` |
| FR-07 | Upload .exe | 422 `UNSUPPORTED_FILE_TYPE` |
| FR-07 | Upload 25 MB | 413 `FILE_TOO_LARGE` |
| FR-08 | Delete document | 204; vectors + file removed |
| FR-09 | Agent question requiring `current_datetime` | `tool_start` + `tool_end` events + final answer ≤ 5 iterations |
| FR-09 | Agent tool raises | observation returned to model; stream completes |
| FR-10 | Save template without `{input}` | 422 `TEMPLATE_MISSING_PLACEHOLDER` |
| FR-11 | Non-admin GET /admin/users | 403 `FORBIDDEN` |
| FR-11 | Admin deactivates own account | 400 `SELF_ACTION_FORBIDDEN` |
| Rate limit | 6th auth request in a minute | 429 `RATE_LIMITED` |
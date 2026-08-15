# Software Design Specification: Nexus

**Version:** 1.0.0

## 1. System Architecture

### Architecture Pattern
REST + SSE API (FastAPI) with a Next.js SPA. Monolithic backend (one process) — justified by single-instance self-hosting scope; domains separated by packages (routers/services/repositories/agents). The AI layer is a LangGraph `StateGraph` (graph API, per official docs: state via `MessagesState` + `add_messages` reducer, nodes return updates, model selection via runtime `context_schema`, node fault-tolerance via `RetryPolicy`/`TimeoutPolicy`).

### High-Level Architecture
```
[Browser]
  → [Next.js 15 — :3000]
      → [FastAPI — :8000]
          → [SQLite/WAL — data/app.db]
          → [FAISS per-user — data/vectorstore/{user_id}/]
          → [uploads — data/uploads/]
          → [LLM factory:  zen (ZEN_BASE_URL, OpenAI-compatible)
                          | openai | anthropic | gemini | ollama(:11434)]
```

## 2. Folder Structure

### Backend (`backend/`)
```
backend/
├── pyproject.toml
├── Dockerfile
├── alembic/
├── data/                        # runtime artifacts (gitignored)
│   ├── app.db
│   ├── uploads/
│   └── vectorstore/
└── src/app/
    ├── main.py                  # FastAPI app, lifespan, CORS, routers, AppError handlers
    ├── core/
    │   ├── config.py            # pydantic-settings Settings (ZEN_API_KEY, ZEN_BASE_URL, ...)
    │   ├── database.py          # async engine (WAL pragma), SessionDep
    │   ├── security.py          # bcrypt, JWT create/verify, cookie helpers
    │   ├── llm.py               # get_chat_model / get_embeddings factory (5 providers)
    │   └── exceptions.py        # AppError hierarchy + status map
    ├── models/
    │   ├── user_model.py
    │   ├── conversation_model.py
    │   ├── document_model.py
    │   ├── template_model.py
    │   └── settings_model.py
    ├── schemas/
    │   ├── user_schema.py       # RegisterIn, LoginIn, UserOut, MeOut, TokenPairOut
    │   ├── conversation_schema.py
    │   ├── chat_schema.py       # ChatRequest, SseEvent models
    │   ├── document_schema.py
    │   └── template_schema.py
    ├── routers/
    │   ├── auth_router.py
    │   ├── conversation_router.py
    │   ├── chat_router.py
    │   ├── document_router.py
    │   ├── template_router.py
    │   ├── admin_router.py
    │   └── health_router.py
    ├── services/
    │   ├── auth_service.py
    │   ├── conversation_service.py
    │   ├── chat_service.py      # SSE orchestration, persistence hooks
    │   ├── document_service.py  # pipeline orchestration (background task)
    │   ├── template_service.py
    │   └── admin_service.py
    ├── repositories/            # one module per entity (user_repo.py, ...)
    ├── agents/
    │   ├── graph.py             # StateGraph build + compile + invoke (recursion_limit=30)
    │   ├── nodes.py             # chat_node, retrieve_node, agent_node
    │   ├── tools.py             # search_documents, current_datetime
    │   └── types.py             # AgentState (MessagesState subclass), ContextSchema
    └── dependencies.py          # get_current_user, require_admin
```

### Frontend (`frontend/`)
```
frontend/
├── Dockerfile
├── next.config.ts
├── biome.json
├── tsconfig.json               # strict: true
└── src/
    ├── app/
    │   ├── (marketing)/page.tsx        # landing
    │   ├── (auth)/login/page.tsx
    │   ├── (auth)/register/page.tsx
    │   ├── (app)/workspace/page.tsx
    │   ├── (app)/documents/page.tsx
    │   ├── (app)/templates/page.tsx
    │   ├── (app)/settings/page.tsx
    │   ├── (app)/admin/page.tsx
    │   ├── layout.tsx / loading.tsx / error.tsx / not-found.tsx
    │   └── providers.tsx
    ├── middleware.ts           # route guard → /login
    ├── components/
    │   ├── ui/                 # shadcn/ui
    │   └── features/
    │       ├── chat/  (ChatPane, MessageList, MessageItem, Composer, SourceChips, ToolCallChip, ModelSelector, Sidebar)
    │       ├── documents/ (UploadDropzone, DocumentTable, StatusBadge)
    │       ├── templates/ (TemplateForm, TemplateList)
    │       ├── auth/ (LoginForm, RegisterForm)
    │       └── admin/ (UsersTable)
    ├── lib/
    │   ├── api.ts              # fetch wrapper, typed { success, data, error }
    │   ├── auth.ts             # 401 → refresh → retry → redirect
    │   └── sse.ts              # SSE stream parser
    ├── hooks/
    │   ├── useChatStream.ts
    │   ├── useConversations.ts
    │   ├── useDocuments.ts
    │   └── useTemplates.ts
    ├── stores/useAuthStore.ts
    └── types/index.ts          # User, Conversation, Message, Document, Template, ApiResponse, SseEvent
```

## 3. Database Schema

```sql
-- SQLite (V1). Postgres: UUID columns + gen_random_uuid(), identical shape.
CREATE TABLE users (
  id            TEXT PRIMARY KEY,
  email         VARCHAR(255) NOT NULL UNIQUE,
  password_hash VARCHAR(255) NOT NULL,
  name          VARCHAR(100),
  role          VARCHAR(16) NOT NULL DEFAULT 'user',
  is_active     BOOLEAN NOT NULL DEFAULT 1,
  created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_users_email ON users(email);

CREATE TABLE conversations (
  id         TEXT PRIMARY KEY,
  user_id    TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  title      VARCHAR(120) NOT NULL DEFAULT 'New conversation',
  agent_type VARCHAR(16) NOT NULL DEFAULT 'chat',
  provider   VARCHAR(16) NOT NULL DEFAULT 'zen',
  model      VARCHAR(64) NOT NULL DEFAULT 'deepseek-v4-flash-free',
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_conv_user ON conversations(user_id, updated_at);

CREATE TABLE messages (
  id              TEXT PRIMARY KEY,
  conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  role            VARCHAR(16) NOT NULL,
  content         TEXT NOT NULL,
  token_count     INTEGER DEFAULT 0,
  created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_msg_conv ON messages(conversation_id, created_at);

CREATE TABLE documents (
  id           TEXT PRIMARY KEY,
  user_id      TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  filename     VARCHAR(255) NOT NULL,
  content_type VARCHAR(100),
  size_bytes   INTEGER NOT NULL,
  chunk_count  INTEGER DEFAULT 0,
  status       VARCHAR(16) NOT NULL DEFAULT 'processing',
  error        TEXT,
  created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_doc_user ON documents(user_id);

CREATE TABLE templates (
  id         TEXT PRIMARY KEY,
  user_id    TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name       VARCHAR(100) NOT NULL,
  content    TEXT NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (user_id, name)
);

CREATE TABLE user_settings (
  user_id          TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  default_provider VARCHAR(16) NOT NULL DEFAULT 'zen',
  default_model    VARCHAR(64) NOT NULL DEFAULT 'deepseek-v4-flash-free',
  temperature      REAL NOT NULL DEFAULT 0.7,
  updated_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

### Relationships
- User 1—N Conversation (cascade); Conversation 1—N Message (cascade)
- User 1—N Document (cascade); User 1—N Template (cascade)
- User 1—1 UserSetting

## 4. API Routes

### Public
| Method | Route | Description |
|--------|-------|-------------|
| POST | /auth/register | Create account (5/min/IP) |
| POST | /auth/login | Login (5/min/IP) |
| POST | /auth/refresh | Rotate refresh token |
| GET | /health | Health check |

### Authenticated
| Method | Route | Description |
|--------|-------|-------------|
| POST | /auth/logout | Clear cookies |
| GET | /auth/me | User + settings + provider status |
| GET | /conversations | List (paginated) |
| POST | /conversations | Create |
| GET | /conversations/{id} | Get + messages |
| PATCH | /conversations/{id} | Rename |
| DELETE | /conversations/{id} | Delete |
| POST | /chat | SSE stream (20/min/user) |
| GET | /documents | List (paginated) |
| POST | /documents | Upload (multipart, 10/hour) |
| DELETE | /documents/{id} | Delete (vectors + file) |
| GET | /templates | List |
| POST | /templates | Create |
| PUT | /templates/{id} | Update |
| DELETE | /templates/{id} | Delete |
| PATCH | /settings | Update defaults (provider/model/temperature) |

### Admin
| Method | Route | Description |
|--------|-------|-------------|
| GET | /admin/users | List + search (paginated) |
| PATCH | /admin/users/{id} | Change role / deactivate |

## 5. Request / Response Schemas

### POST /auth/login
**Request:** `{ "email": "user@example.com", "password": "secret123" }`
**Success (200):**
```json
{ "success": true, "data": { "id": "uuid", "email": "user@example.com", "name": null, "role": "user" } }
```
**Error (401):**
```json
{ "success": false, "error": { "code": "INVALID_CREDENTIALS", "message": "Invalid email or password" } }
```

### POST /chat — SSE Stream (200, text/event-stream)
```
data: {"type":"meta","data":{"conversation_id":"uuid","agent_type":"agent","provider":"zen","model":"deepseek-v4-flash-free"}}

data: {"type":"token","data":{"content":"Hello"}}
data: {"type":"token","data":{"content":" world"}}

data: {"type":"tool_start","data":{"tool":"search_documents","input":"rust ownership"}}
data: {"type":"tool_end","data":{"tool":"search_documents","output":"3 chunks retrieved"}}

data: {"type":"sources","data":[{"document_id":"uuid","filename":"notes.md","score":0.87,"excerpt":"ownership is a set of rules..."}]}

data: {"type":"done","data":{"message_id":"uuid","token_count":42}}

data: {"type":"error","data":{"code":"NO_DOCUMENTS","message":"Upload documents first"}}
```

### POST /documents (multipart)
**Success (202):**
```json
{ "success": true, "data": { "id": "uuid", "filename": "notes.md", "size_bytes": 2048, "status": "processing", "created_at": "2026-08-15T10:00:00Z" } }
```
**Error (413):** `{ "success": false, "error": { "code": "FILE_TOO_LARGE", "message": "Max 20 MB" } }`

## 6. Key Algorithms & Business Logic

### SSE Chat Orchestration
```
FUNCTION stream_chat(request, current_user):
  1. rate_limit(current_user, "chat")
  2. conversation = resolve_conversation(request, current_user)   # create if absent
  3. if request.regenerate: delete_last_assistant(conversation); replay last user message
  4. persist user message
  5. yield meta event
  6. async for event in run_graph(conversation, message, current_user): yield event
  7. if terminated normally: persist assistant message; yield done
  8. on CancelledError: abort silently (nothing persisted)
```

### LangGraph StateMachine (graph API, per official LangGraph docs)
```python
# agents/types.py — state is a MessagesState subclass; model config lives in context, not state
from langgraph.graph import MessagesState
from langgraph.runtime import Runtime

class AgentState(MessagesState):
    iterations: int        # agent loop counter
    final: bool            # final-answer flag
    source_chunks: list    # rag sources for the SSE `sources` event

class ContextSchema(TypedDict):      # runtime config: model selection per request
    provider: str
    model: str
    temperature: float
    template: str | None             # rendered textgen system prompt
    user_id: str

# agents/graph.py
builder = StateGraph(AgentState, context_schema=ContextSchema)
builder.add_node("route", route_node)              # branches on agent_type
builder.add_conditional_edges("route", route_next, {
    "chat": "chat_node", "rag": "retrieve_node", "agent": "agent_node", "textgen": "chat_node",
    # textgen sets a rendered system prompt in context; chat_node and agent_node
    # read provider/model from Runtime[ContextSchema] (not from state)
})
builder.add_node("chat_node", chat_node)
builder.add_node("retrieve_node", retrieve_node)   # FAISS top_k=4 -> context in context_schema
builder.add_node("agent_node", agent_node, retry_policy=RetryPolicy(max_attempts=2))
builder.add_node("tools_executor", tools_executor)
builder.add_conditional_edges("agent_node", route_after_tools, {
    "tools": "tools_executor",      # tool calls pending AND iterations < 5
    "final": END,
})
builder.add_node("chat_node", chat_node, retry_policy=RetryPolicy(max_attempts=2))
builder.add_edge("retrieve_node", "chat_node")
builder.add_edge("chat_node", END)
builder.add_edge("tools_executor", "agent_node")
builder.set_node_defaults(timeout=TimeoutPolicy(run_timeout=30))
graph = builder.compile()

# agents/nodes.py — nodes return updates; they never mutate state
async def agent_node(state: AgentState, runtime: Runtime[ContextSchema]):
    model = get_chat_model(runtime.context.provider,
                           runtime.context.model,
                           runtime.context.temperature).bind_tools([search_documents, current_datetime])
    response = await model.ainvoke(state["messages"])
    return {"messages": [response], "iterations": state["iterations"]}
```

### Streaming bridge (event streaming v3, per official LangGraph docs)
```
FUNCTION run_graph(...):
  stream = await graph.astream_events(input, config={"recursion_limit": 30,
                                                     "context": ContextSchema(...)}, version="v3")
  async for message in stream.messages:         # token deltas, one per chunk
      for token in message.text: yield token_event(token)
  async for tool in stream.tools:               # tool-started / tool-finished / tool-error
      yield tool_start_event(tool) / tool_end_event(tool)
  # GraphError (recursion limit hit) -> yield error_event("AGENT_LOOP_LIMIT")
```
- Persistence is **not** delegated to a LangGraph checkpointer in V1: durability is the SQLAlchemy write after the last `done` event. Checkpointing is a V2 candidate.

### Agent Loop Guard
```
route_after_tools(state):
   if pending tool calls and state["iterations"] < 5: return "tools"
   return "final"        # last model message becomes the final answer
Hard guard: invoke config recursion_limit = 30 -> GraphRecursionError -> AGENT_LOOP_LIMIT
Tool exceptions: tools_executor catches, converts to an observation message -> model continues
```

### Document Pipeline (background task)
```
1. Validate type/size -> save to data/uploads/{user_id}/{doc_id}
2. Extract text (pypdf for PDF, plain read otherwise)
3. split: RecursiveCharacterTextSplitter(800, 100)
4. embed: get_embeddings() -> FAISS.add_documents (per-user index at data/vectorstore/{user_id}/)
5. On exception: document.status = failed, document.error = str(exc)
```

## 7. SSE Event Protocol (contract)

| Event | Direction | Payload | Emitted |
|-------|-----------|---------|---------|
| `meta` | server→client | `{ conversation_id, agent_type, provider, model }` | once, first |
| `token` | server→client | `{ content }` | per text delta |
| `tool_start` | server→client | `{ tool, input }` | agent mode, per tool call |
| `tool_end` | server→client | `{ tool, output }` | agent mode, per tool call |
| `sources` | server→client | `[{ document_id, filename, score, excerpt }]` | rag mode, before first token |
| `done` | server→client | `{ message_id, token_count }` | once, stream success |
| `error` | server→client | `{ code, message }` | stream failure (HTTP stays 200) |

All events are `data: {json}\n\n` frames. Codes: `NO_DOCUMENTS`, `PROVIDER_NOT_CONFIGURED`, `PROVIDER_ERROR`, `AGENT_LOOP_LIMIT`, `INTERNAL_ERROR`.

## 8. Environment Variables

```env
# App
APP_ENV=development
SECRET_KEY=replace-with-32+-char-random

# Database
DATABASE_URL=sqlite+aiosqlite:///./data/app.db
# Postgres later: postgresql+asyncpg://user:pass@localhost:5432/nexus

# Auth
ACCESS_TOKEN_EXPIRE_MINUTES=60
REFRESH_TOKEN_EXPIRE_DAYS=7

# LLM providers — fill at least the ones you use
# OpenCode Zen API (default provider; OpenAI-compatible endpoint)
ZEN_API_KEY=
ZEN_BASE_URL=

# Other providers
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
GEMINI_API_KEY=
OLLAMA_BASE_URL=http://localhost:11434

# Defaults
DEFAULT_PROVIDER=zen
DEFAULT_MODEL=deepseek-v4-flash-free

# Embeddings
EMBEDDING_PROVIDER=openai
EMBEDDING_MODEL=text-embedding-3-small
# or: EMBEDDING_PROVIDER=ollama / EMBEDDING_MODEL=nomic-embed-text

# Runtime
DATA_DIR=./data
CORS_ORIGINS=http://localhost:3000
LOG_LEVEL=INFO
```

## 9. Security Design
- **Authentication:** JWT HS256; access 60 min + refresh 7 days in httpOnly, `SameSite=Lax` cookies
- **Authorization:** `get_current_user` dependency on all protected routes; `require_admin` for `/admin/*`; resource ownership enforced in service layer (403 on foreign IDs)
- **Passwords:** bcrypt, cost 12 (via passlib)
- **Input validation:** Pydantic v2 (backend) + Zod (frontend)
- **SQL injection:** ORM + parameterized queries only
- **CORS:** explicit `CORS_ORIGINS` list; SSE needs `GET/POST` allowed
- **Keys:** server env only; exposed to clients only as `configured: bool` in `/auth/me`
- **Rate limits:** slowapi — auth 5/min/IP; chat 20/min/user; uploads 10/hour/user

## 10. Performance Design
- SSE: `Cache-Control: no-cache`; `X-Accel-Buffering: no`; stream generators — never accumulate full responses
- LLM streaming: per-token deltas via `stream.messages` projection (v3), no buffering of full text server-side
- Pagination: all list endpoints `?page&limit≤50`, offset style, `total` returned
- Indexes: users.email unique; conversations (user_id, updated_at); messages (conversation_id, created_at); documents (user_id)
- SQLite WAL mode pragma on engine connect
- RAG: top_k=4, single FAISS load per request (loaded lazily + cached in-process by user_id)
- Provider call timeout: `TimeoutPolicy(run_timeout=30)` on LLM nodes; temperature from settings (default 0.7)
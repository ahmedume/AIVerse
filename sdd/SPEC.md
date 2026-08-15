# Project Specification: Nexus

## 1. Overview
- **Project Name:** Nexus
- **One-Line Description:** A self-hosted, provider-agnostic AI workspace with chat, document Q&A, agent tool-calling, and template-based text generation
- **Goal:** Give a single user four production-grade AI capabilities behind one clean interface, fully under their control
- **Target Users:** Individual users (developers, researchers, writers) self-hosting; admin manages accounts
- **Version:** 1.0.0 (MVP)

## 2. Problem Statement

Cloud AI tools (ChatGPT, Claude.ai) restrict model choice, own conversation data, and cannot access your private documents or run untrusted automation. Open-source chat UIs stop at chat — they lack RAG, agents, and templates in one package. Nexus solves this: one self-hostable workspace where the user chooses the model provider (OpenCode Zen API, cloud APIs, or local Ollama), uploads documents for grounded Q&A, runs tool-using agents, and reuses prompt templates — with all data on their own machine.

## 3. Core Features (MVP — MUST HAVE)

### Feature 1: Authentication (email + password)
- **Description:** Users register and log in with email + password; JWT access token (60 min) + rotating refresh token (7 days) stored in httpOnly cookies
- **User Flow:** Visit `/register` → fill form → account created → auto-login → redirected to `/workspace`. Logout clears both cookies
- **Inputs:** `email` (valid RFC 5322), `password` (min 8 chars), optional `name`
- **Outputs:** User object `{ id, email, name, role }`, token pair in cookies
- **Rules:** Email unique; password hashed (bcrypt cost 12); first user becomes `admin`, subsequent users `user`; auth endpoints rate-limited 5/min/IP

### Feature 2: Streaming Chat (multi-provider)
- **Description:** User sends a message; server streams LLM tokens over SSE; message persists after stream completes
- **User Flow:** Composer → select mode + model (chat/rag/agent/textgen) → send → tokens render live → "Regenerate" button replays last user message
- **Inputs:** `{ conversation_id?, mode, provider?, model?, message }` via `POST /chat`
- **Outputs:** SSE events: `meta`, `token`, `tool_start`, `tool_end`, `sources`, `done`, `error`
- **Rules:** Model chosen at conversation creation; unauthenticated → 401; conversations auto-title from first user message (50 chars); rate-limited 20/min/user
- **Default provider:** `zen` (OpenCode Zen API), default model `deepseek-v4-flash-free` (free tier). The Zen provider is an OpenAI-compatible endpoint configured via `ZEN_API_KEY` + `ZEN_BASE_URL` in `.env`

### Feature 3: Document Q&A (RAG)
- **Description:** Upload documents; system chunks + embeds them into a per-user FAISS index; chat mode `rag` retrieves top-4 chunks as context and cites sources
- **User Flow:** `/documents` → upload (max 20MB, txt/md/json/pdf) → status `processing` → `ready` → in workspace choose `rag` mode → ask → response includes source chips (filename + score) via `sources` event
- **Inputs:** multipart `file` field; chat message for retrieval
- **Rules:** Only the owning user's documents are retrieved; documents must have `status=ready`; chunk size 800 chars / overlap 100; retrieval requires ≥1 ready document else `error` event `NO_DOCUMENTS`

### Feature 4: Agent Mode (tool-calling)
- **Description:** LangGraph loop where the LLM decides to call tools; loop caps at 5 LLM iterations; tools: `search_documents(query)`, `current_datetime()`
- **User Flow:** Select `agent` mode → ask "what's in my notes about Rust?" → tool calls visible live (`tool_start`/`tool_end` events) → final answer streamed
- **Inputs:** chat message; tools passed via model `bind_tools`
- **Rules:** Max 5 loop iterations then force final answer; graph recursion limit 30 as safety net; tool outputs visible in event stream; tool errors returned to the model as observations, never crash

### Feature 5: Template Text Generation
- **Description:** Reusable prompt templates with `{input}` placeholder; mode `textgen` renders template with the message injected
- **User Flow:** `/templates` → create template ("Summarize {input} in 5 bullets") → in workspace pick `textgen`, select template, type input → streamed completion
- **Inputs:** `{ template_id, message }`; content max 4000 chars
- **Rules:** `{input}` required in template body — validated at save time

### Feature 6: History & Administration
- **Description:** Conversation list with search + delete; admin panel lists users, changes roles, deactivates accounts
- **User Flow:** Sidebar lists conversations (search box filters client-side) → click loads messages → admin visits `/admin` → paginated user table → change role / toggle active
- **Rules:** Deactivated users are logged out on next request (401); only `role=admin` may access `/admin/*`

## 4. End-to-End User Flow

1. First-time visitor lands on `/` → clicks "Get Started" → `/register`
2. Register with email/password → auto-login → cookies set → redirected to `/workspace`
3. Workspace shows empty state: "Start your first conversation"
4. User picks provider `zen` and model `deepseek-v4-flash-free` (defaults from settings), types question → Enter
5. Tokens stream into the UI; conversation auto-titled; messages persist
6. User uploads `notes.md` in `/documents` → status becomes `ready` (~seconds)
7. User starts a `rag` conversation → asks about notes → answer cites the document
8. User starts an `agent` conversation → asks "when is UTC now?" → tool executes, answer streams
9. User creates a template in `/templates` → uses it via `textgen` mode
10. Admin deactivates a spam account → that user's next request gets 401 → redirected to login

## 5. System Behavior (Logic Rules)

- Only authenticated users can access `/workspace`, `/documents`, `/templates`, `/settings` — others redirect to `/login`
- Only `role=admin` can access `/admin/*` — others get 403
- A user can only see/modify their own conversations, documents, and templates
- Assistant messages persist ONLY after a successful `done` event (no partial saves)
- Regenerate removes the last assistant message, then replays the last user message
- Document deletion removes the FAISS vectors for that document and the file on disk
- Deleting a conversation hard-deletes its messages (cascade)
- If the provider key is not configured (e.g., `ZEN_API_KEY` empty): `error` event `PROVIDER_NOT_CONFIGURED`
- Rate limits: auth 5 req/min/IP; chat 20 req/min/user; uploads 10 files/hour/user

**Edge Cases:**
- Title empty message: client blocks submit (inline "Message is required")
- Mid-stream disconnect: server aborts generation; no message persisted; client shows retry banner
- RAG with zero ready documents: `error` event `NO_DOCUMENTS`, UI disables rag mode until a document is ready
- Upload of unsupported/binary type: 422 `UNSUPPORTED_FILE_TYPE`
- Upload parsing failure: document status `failed` with stored `error`, visible in UI
- Expired access token: frontend calls `/auth/refresh`; if refresh fails → redirect `/login`
- Deactivated user token: 401 `ACCOUNT_DISABLED`
- Agent loop exceeds 5 iterations: final answer forced; if graph recursion limit (30) is hit: `error` event `AGENT_LOOP_LIMIT`

## 6. Data Model (Entities)

### Entity: User
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| id | TEXT (uuid4) | Yes | Primary key |
| email | VARCHAR(255) | Yes | Unique |
| password_hash | VARCHAR(255) | Yes | bcrypt cost 12 |
| name | VARCHAR(100) | No | |
| role | VARCHAR(16) | Yes | `user` \| `admin`, default `user` |
| is_active | BOOLEAN | Yes | default true |
| created_at | TIMESTAMP | Yes | Auto |

### Entity: Conversation
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| id | TEXT | Yes | Primary key |
| user_id | TEXT | Yes | FK → users.id, cascade |
| title | VARCHAR(120) | Yes | Default "New conversation" |
| agent_type | VARCHAR(16) | Yes | `chat` \| `rag` \| `agent` \| `textgen` |
| provider | VARCHAR(16) | Yes | `zen` \| `openai` \| `anthropic` \| `gemini` \| `ollama` |
| model | VARCHAR(64) | Yes | Model name (e.g., `deepseek-v4-flash-free`) |
| created_at / updated_at | TIMESTAMP | Yes | Auto |

### Entity: Message
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| id | TEXT | Yes | Primary key |
| conversation_id | TEXT | Yes | FK, cascade |
| role | VARCHAR(16) | Yes | `user` \| `assistant` \| `tool` |
| content | TEXT | Yes | |
| token_count | INTEGER | No | from provider usage |
| created_at | TIMESTAMP | Yes | Auto |

### Entity: Document
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| id | TEXT | Yes | Primary key |
| user_id | TEXT | Yes | FK, cascade |
| filename | VARCHAR(255) | Yes | Original name |
| content_type | VARCHAR(100) | No | MIME |
| size_bytes | INTEGER | Yes | |
| chunk_count | INTEGER | No | 0 until ready |
| status | VARCHAR(16) | Yes | `processing` \| `ready` \| `failed` |
| error | TEXT | No | Failure reason |
| created_at | TIMESTAMP | Yes | Auto |

### Entity: Template
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| id | TEXT | Yes | Primary key |
| user_id | TEXT | Yes | FK, cascade |
| name | VARCHAR(100) | Yes | Unique per user |
| content | TEXT | Yes | Must contain `{input}`, max 4000 |
| created_at / updated_at | TIMESTAMP | Yes | Auto |

### Entity: UserSetting
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| user_id | TEXT | Yes | PK, FK, cascade |
| default_provider | VARCHAR(16) | Yes | default `zen` |
| default_model | VARCHAR(64) | No | default `deepseek-v4-flash-free` |
| temperature | REAL | Yes | default 0.7 |
| updated_at | TIMESTAMP | Yes | Auto |

## 7. UI Screens

### Screen 1: Landing `/`
- **Purpose:** Market the product; CTA to register
- **Components:** Navbar, Hero, Features grid (4 modes), Self-hosted section, Footer
- **States:** n/a (static)

### Screen 2: Login `/login` & Register `/register`
- **Purpose:** Authenticate / create account
- **Components:** Form (email, password, ±name), Zod validation, submit, error alert
- **States:** idle / submitting / error (invalid credentials, email taken)

### Screen 3: Workspace `/workspace`
- **Purpose:** All four AI modes
- **Components:** Sidebar (conversation list + search + new chat), header (mode selector, model selector, provider badge), ChatPane (MessageList, MessageItem, Composer, Regenerate, sources chips, streaming cursor), MobileDrawer
- **States:** loading / empty / streaming / error / populated

### Screen 4: Documents `/documents`
- **Purpose:** Upload and manage RAG corpus
- **Components:** UploadDropzone, DocumentTable (filename, size, chunks, status badge, delete), ProgressToast
- **States:** loading / empty / populated / upload-error

### Screen 5: Templates `/templates`
- **Purpose:** CRUD prompt templates
- **Components:** TemplateList, TemplateForm (name, content, `{input}` helper text)
- **States:** loading / empty / populated / error

### Screen 6: Settings `/settings`
- **Purpose:** Defaults + account
- **Components:** Provider select (zen/openai/anthropic/gemini/ollama), model select, temperature slider, provider status cards (configured/not), save
- **States:** loading / saved-toast / error

### Screen 7: Admin `/admin`
- **Purpose:** User management (admin only)
- **Components:** UsersTable (paginated: email, name, role select, active toggle), SearchInput
- **States:** loading / empty / error / forbidden (403)

## 8. Constraints
- SQLite V1 → Postgres 16 later (same models, `DATABASE_URL` swap)
- FAISS per-user indices on disk — no pgvector in V1
- No per-user/provider API keys in V1 (server env only)
- Web search tool, file versioning, shared workspaces: V2
- Max upload 20MB; chat rate 20 req/min; auth 5 req/min

## 9. Out of Scope (V1)
- Teams, sharing, workspaces
- Web search tool in agent mode
- Per-user API key management
- Conversation export/import
- Mobile native app

## 10. Future Improvements (V2)
- pgvector + Postgres production profile
- Web search tool, custom tool registry
- Per-user provider keys, usage/billing tracking
- Conversation export (Markdown/PDF), model benchmark page
- Email verification + password reset
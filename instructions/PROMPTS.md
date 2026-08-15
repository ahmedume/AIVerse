# Execution Prompts: Nexus

Always ensure SPEC.md, SRS.md, SDS.md, and SKILL.md are loaded in context before using these. Run the SETUP prompt first.

---

## SETUP PROMPT (Run This First)
```
Read all .md files in this folder: SPEC.md, PRD.md, SRS.md, SDS.md, SKILL.md, TECH_STACK.md.
Confirm by summarizing: (1) what Nexus is, (2) the tech stack (incl. default Zen provider
and model deepseek-v4-flash-free), (3) the folder structure,
(4) the 5 most important SKILL.md rules. Do not write any code until I say "proceed".
```

---

## PROMPT 1: Scaffold Monorepo
```
Scaffold the Nexus monorepo per SDS.md section 2:
- backend: uv init; add all deps from TECH_STACK.md (incl. langgraph>=1.2, openai>=1.0,
  langchain-community for FAISS/ChatOllama, pypdf); create src/app/{core,models,schemas,
  routers,services,repositories,agents} with empty files + header comments
- frontend: pnpm create next-app (TS, Tailwind, App Router); add deps; init shadcn/ui;
  strict tsconfig; Biome config
- root: docker-compose.yml (api :8000, web :3000, ollama profile with `profiles: [local-models]`),
  backend/.env.example (ZEN_API_KEY, ZEN_BASE_URL placeholders), frontend/.env.example, README.md
Implement core/config.py (pydantic-settings incl. ZEN_API_KEY, ZEN_BASE_URL with provider
presence helper), core/database.py (async engine, WAL), core/exceptions.py, GET /health.
Structure only + health endpoint. No business logic yet.
```

---

## PROMPT 2: Database & Auth Backend
```
Implement per SRS.md FR-01..FR-04 and SDS.md section 3:
- SQLAlchemy async models: users, user_settings; Alembic init + first migration (SQLite,
  WAL enabled in engine pragma)
- core/security.py: bcrypt cost 12, JWT access 60min (HS256) + refresh 7d, httpOnly
  SameSite=Lax cookie helpers
- routers/auth_router.py + services/auth_service.py + repositories/user_repo.py:
  POST /auth/register, POST /auth/login, POST /auth/refresh (rotation), POST /auth/logout,
  GET /auth/me (returns user + settings + providers: {zen, openai, anthropic, gemini, ollama}
  booleans computed from env key presence)
- dependencies.py: get_current_user (checks is_active -> ACCOUNT_DISABLED)
- slowapi: 5/min on POST /auth/* (not on /auth/me)
Follow every error code in SRS.md exactly (409 EMAIL_TAKEN, 401 INVALID_CREDENTIALS, ...).
```

---

## PROMPT 3: Conversations & Streaming Chat Engine (Zen default)
```
Implement per SRS.md FR-05, FR-06 and SDS.md sections 4-5:
- Models: conversations (provider default 'zen', model default 'deepseek-v4-flash-free'),
  messages (+ cascade FKs, indexes per SDS.md section 3)
- conversation_router.py: GET/POST/GET{id}/PATCH{id}/DELETE{id} — ownership-scoped
- core/llm.py provider factory: zen (ChatOpenAI with base_url=ZEN_BASE_URL, api_key=ZEN_API_KEY),
  openai, anthropic, gemini, ollama; raise ProviderNotConfigured when a key is empty
- chat_router.py POST /chat: SSE stream per SDS.md section 7 (meta/token/done/error);
  build the Mode Graph for agent_type='chat' with StateGraph(MessagesState,
  context_schema=...) per SKILL.md; stream tokens via astream_events version="v3";
  persist assistant message ONLY after done; regenerate deletes last assistant message first
- Auto-title conversation from first user message (50 chars)
- slowapi 20/min/user; structlog request logging
Verify with curl -N POST /chat against provider zen once ZEN_API_KEY is filled.
```

---

## PROMPT 4: Documents, RAG & Templates
```
Implement per SRS.md FR-07, FR-08, FR-10 and SDS.md section 6:
- Models: documents, templates
- document_router.py + services/document_service.py:
  POST /documents (multipart, txt/md/json/pdf, <=20MB, 10/hour) → background pipeline:
  extract (pypdf) → RecursiveCharacterTextSplitter(800/100) → embed →
  per-user FAISS at data/vectorstore/{user_id}/; status processing → ready|failed
  GET /documents; DELETE removes vectors + file
- rag mode: retrieve_node queries FAISS top_k=4 → context assembled → chat_node;
  emit `sources` event with filename+score+excerpt before first token
- textgen mode: template rendered as system prompt ({input} substituted); template_id
  ownership check
- template_router.py: GET/POST/PUT/DELETE with SRS.md FR-10 error codes
  (TEMPLATE_MISSING_PLACEHOLDER, TEMPLATE_NAME_TAKEN)
```

---

## PROMPT 5: LangGraph Agent Mode
```
Implement per SRS.md FR-09 and SDS.md section 6 (grounded in official LangGraph docs):
- agents/types.py: AgentState(MessagesState) with iterations/final/source_chunks;
  ContextSchema(TypedDict) for provider/model/temperature/template/user_id (runtime config,
  never stored in state)
- agents/tools.py: search_documents(query) → FAISS top-3 excerpts; current_datetime() → UTC
- agents/nodes.py: chat_node, retrieve_node (rag), agent_node (bind_tools)
- agents/graph.py: StateGraph(AgentState, context_schema=ContextSchema) with conditional
  routing; tools_executor node converts tool exceptions into observation messages;
  add_node with RetryPolicy(max_attempts=2) + set_node_defaults(TimeoutPolicy(run_timeout=30));
  invoke with config {"recursion_limit": 30, "context": ContextSchema(...)}
- map stream.tools channel events (tool-started/tool-finished) to SSE tool_start/tool_end;
  GraphRecursionError → error event AGENT_LOOP_LIMIT
Ensure a tool exception returns an observation to the model — never crashes the stream.
```

---

## PROMPT 6: Frontend Foundation & Auth UI
```
Implement per SPEC.md Screens 1-2 and SDS.md section 2 (frontend):
- src/middleware.ts route guard; stores/useAuthStore.ts (Zustand); lib/auth.ts
  (401 → refresh → retry → redirect /login?reason=session)
- lib/api.ts typed fetch client around { success, data, error }
- Landing page (marketing); /login and /register with RHF + Zod, inline errors
- Root layout, loading.tsx, error.tsx, not-found.tsx, providers.tsx (TanStack Query)
Wire real API calls; verify register→login→/auth/me round trip in the browser.
```

---

## PROMPT 7: Workspace Chat UI
```
Implement the workspace per SPEC.md Screen 3 and SRS.md section 4.1:
- Sidebar (conversation list + client-side search + new chat), header with mode selector
  (chat|rag|agent|textgen) + model selector (default zen / deepseek-v4-flash-free)
- ChatPane: MessageList, MessageItem, streaming cursor (Motion), Composer (disabled when
  streaming/empty), Regenerate (idle + last message is user)
- hooks/useChatStream.ts with lib/sse.ts parser: token appends, source chips from `sources`,
  tool chips from tool_start/tool_end, banners for NO_DOCUMENTS, PROVIDER_NOT_CONFIGURED,
  AGENT_LOOP_LIMIT, 429
Handle: loading, empty ("Start your first conversation"), error, streaming, populated states.
```

---

## PROMPT 8: Documents, Templates & Settings UI
```
Implement per SPEC.md Screens 4-6:
- /documents: UploadDropzone (drag+drop, front validation of type/size), DocumentTable
  with status badges (processing/ready/failed + error tooltip), delete with confirm
- /templates: TemplateForm (RHF+Zod: name unique, content must contain {input}),
  TemplateList CRUD
- /settings: defaults form (provider/model/temperature → PATCH /settings), provider status
  cards from /auth/me providers map (show Zen API "configured" when true, link-to-.env hint)
All screens: loading/empty/error states; invalidate queries on mutations.
```

---

## PROMPT 9: Admin UI & Hardening
```
Implement per SPEC.md Screen 7 and SRS.md FR-11:
- admin_router backend: GET /admin/users (page/limit/search), PATCH /admin/users/{id}
  (role/is_active, SELF_ACTION_FORBIDDEN guard) with require_admin dependency
- /admin page: UsersTable (paginated, search, role select, active toggle, optimistic
  updates, 403 handling)
- Docker: multi-stage Dockerfiles (uv sync --frozen / next build), .dockerignore excludes data/
- Integration test a fresh user through: register → 4-mode chats (zen default) → upload → RAG → admin actions
```

---

## PROMPT 10: Debug / Fix
```
The following is not working as specified in SRS.md:
{FILL IN: what breaks}

Expected behavior per SRS.md FR-0X / SDS.md section {N}:
{FILL IN: what should happen}

Actual behavior:
{FILL IN: observed}

Diagnose root cause first, then fix without changing any other behavior. Follow SKILL.md rules.
```

---

## PROMPT 11: Review & Spec Check
```
Review the current implementation against SPEC.md and SRS.md.
Report (do not fix yet):
1. Missing features (not implemented)
2. Incorrectly implemented (behavior deviates from SRS, incl. status codes + SSE event shapes)
3. Out of scope (implemented but not in SPEC.md)
4. SKILL.md violations (comments, file sizes, naming, error handling gaps)
```
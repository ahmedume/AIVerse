# AI Coding Agent Rules: Nexus

**Version:** 1.0.0
**Stack:** FastAPI + LangGraph (>=1.2) + SQLAlchemy async + SQLite(V1) + Zen API default provider | Next.js 15 + TS strict + Tailwind v4 + shadcn/ui + TanStack Query

## Role

You are a staff-level full-stack engineer building Nexus. You implement exactly what SRS.md/SDS.md specify, nothing more, nothing less. You follow these rules without exception.

## ALWAYS

1. Use `uv` for Python and `pnpm` for Node — NEVER run `pip install` or `npm install` directly
2. Follow the folder structure in SDS.md §2 exactly — do not create new top-level folders
3. All env vars via `.env` validated by pydantic-settings (incl. `ZEN_API_KEY`, `ZEN_BASE_URL`) — NEVER hardcode values in code
4. TypeScript strict: `strict: true`, no `any`, no `// @ts-ignore`; Python: full type annotations + mypy clean
5. Every JSON response is `{ success, data?, error? }` — SSE events use the exact event names/fields in SRS.md FR-06 (`meta`, `token`, `tool_start`, `tool_end`, `sources`, `done`, `error`)
6. LangGraph: build with `StateGraph(MessagesState, context_schema=...)`; nodes return state updates (never mutate); model/provider injected via `Runtime[ContextSchema]`, never stored in graph state; invoke with `astream_events(..., version="v3")` and `recursion_limit=30`; add `RetryPolicy(max_attempts=2)` + `TimeoutPolicy(run_timeout=30)` to LLM nodes — per official LangGraph docs
7. Write complete implementations — no stubs, no `pass`, no TODO placeholders in completed features
8. Scope every DB query to `current_user.id` in the repository layer — ownership is non-negotiable
9. Every async operation has error handling — provider failures become `error` SSE events or 500 `INTERNAL_ERROR`, never bare exceptions
10. Each file starts with a header comment: file path, purpose, exports, dependencies; read a file fully before modifying it

## NEVER

1. NEVER write raw SQL strings in routes or services — ORM + repositories only
2. NEVER store passwords as plaintext; NEVER return `password_hash` or any API key in any response
3. NEVER implement features beyond SPEC.md — ask before adding (e.g., web search, teams)
4. NEVER use localStorage for tokens — auth lives in httpOnly cookies
5. NEVER batch/persist a partial assistant message — persist only after the `done` event
6. NEVER create files > 300 lines — split routers/services/agents into focused modules
7. NEVER mix business logic into route handlers — thin routers → services → repositories
8. NEVER use `console.log` / `print` for diagnostics — structlog (backend), `console.error` + error boundaries (frontend)
9. NEVER commit `.env` or `data/` artifacts — `.env.example` only; `data/` is gitignored
10. NEVER invent provider/model names or LangGraph APIs — the only default model is `deepseek-v4-flash-free` (provider `zen`); verify any other model ID with the user before hardcoding

## Code Patterns

### FastAPI Route (with SSE)
```python
# src/app/routers/chat_router.py
# Purpose: POST /chat — SSE streamed chat
# Dependencies: chat_service, get_current_user
@router.post("/chat")
async def stream_chat(
    payload: ChatRequest,
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    return StreamingResponse(
        chat_service.stream(payload, current_user),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
```

### LLM Factory (zen provider = OpenAI-compatible)
```python
# src/app/core/llm.py
# Purpose: provider-agnostic chat model + embedding factory
def get_chat_model(provider: str, model: str, temperature: float) -> BaseChatModel:
    if provider == "zen":
        if not settings.ZEN_API_KEY or not settings.ZEN_BASE_URL:
            raise ProviderNotConfigured("zen")
        return ChatOpenAI(model=model, api_key=settings.ZEN_API_KEY,
                          base_url=settings.ZEN_BASE_URL, temperature=temperature)
    if provider == "openai": ...   # ChatOpenAI
    if provider == "anthropic": ...  # ChatAnthropic
    if provider == "gemini": ...     # ChatGoogleGenerativeAI
    if provider == "ollama": ...     # ChatOllama
    raise ValueError(f"unknown provider: {provider}")
```

### LangGraph Node (per official docs)
```python
# src/app/agents/nodes.py — nodes return updates; model selected via runtime context
async def agent_node(state: AgentState, runtime: Runtime[ContextSchema]) -> dict:
    model = get_chat_model(runtime.context.provider,
                           runtime.context.model,
                           runtime.context.temperature).bind_tools([search_documents, current_datetime])
    response = await model.ainvoke(state["messages"])
    return {"messages": [response], "iterations": state["iterations"]}
```

### TanStack Query Stream Hook
```typescript
// src/hooks/useChatStream.ts
// Purpose: stream POST /chat SSE events into chat state
export function useChatStream() {
  return useMutation({
    mutationFn: async ({ payload, onEvent }: ChatStreamArgs) => {
      const stream = await api.stream("/chat", { method: "POST", body: payload });
      for await (const event of parseSse(stream)) onEvent(event);
    },
    onSuccess: () => queries.invalidateQueries({ queryKey: ["conversations"] }),
  });
}
```

### React Component
```typescript
// Purpose: [what this component does]
// Props: [what it receives]
interface Props { conversation: Conversation; activeStream: StreamState | null; }
export function ChatPane({ conversation, activeStream }: Props) {
  // state at top, effects after state, handlers before return, JSX last
}
```

## File Naming Conventions
- Backend routers: `{domain}_router.py`; models: `{entity}_model.py`; schemas: `{entity}_schema.py`
- Agents: `graph.py`, `nodes.py`, `tools.py`, `types.py` — no other files in `agents/`
- Frontend pages: `page.tsx` (App Router groups `(marketing)`, `(auth)`, `(app)`); components `PascalCase.tsx`; hooks `use[Name].ts`
- Types live in `src/types/index.ts` — never duplicated in component files

## Commit Message Format
```
{type}: {short description}

Types: feat | fix | refactor | docs | test | chore
Example: feat: add rag mode with document sources
```
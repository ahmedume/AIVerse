# AI Coding Agent Rules: AIverse

**Version:** 1.0.0
**Stack:** FastAPI + LangGraph (>=1.2) + pypdf + python-docx + reportlab | Next.js + TS strict + Tailwind v4 + TanStack Query

## Role

You are a staff-level full-stack engineer building AIverse. You implement exactly what SRS.md/SDS.md specify, nothing more, nothing less. You follow these rules without exception.

## ALWAYS

1. Use `uv` for Python and `pnpm` for Node — NEVER run `pip install` or `npm install` directly
2. Follow the folder structure in SDS.md §2 exactly — do not create new top-level folders
3. All env vars via `.env` validated by pydantic-settings (incl. `ZEN_API_KEY`, `ZEN_BASE_URL`) — NEVER hardcode values in code
4. TypeScript strict: `strict: true`, no `any`, no `// @ts-ignore`; Python: full type annotations + mypy clean
5. Every JSON response is `{ success, data?, error? }` — SSE events use the exact names in SDS.md §7 (`meta`, `token`, `block_score`, `block_start`, `block_end`, `fragment`, `sources`, `tool_start`, `tool_end`, `done`, `error`)
6. LangGraph: `StateGraph(MessagesState, context_schema=...)`; nodes return state updates (never mutate); model/provider injected via `Runtime[ContextSchema]`, never in graph state; invoke with `astream_events(version="v3")` + `recursion_limit=30`; LLM nodes get `RetryPolicy(max_attempts=2)` + `TimeoutPolicy(run_timeout=60)` via `set_node_defaults`
7. Write complete implementations — no stubs, no `pass`, no TODO placeholders in completed features
8. **MAXIMUM CODE COMPACTION** — the most critical rule: a component that can be a function is a function; nothing dragged to 100 lines; no file > 300 lines; no dead code, no speculative abstraction
9. Every async operation has error handling — provider failures become `error` SSE events or 422/5xx JSON, never bare exceptions
10. Each file starts with a header comment: file path, purpose, exports, dependencies; read a file fully before modifying it
11. Streaming endpoints return generators, never buffered responses; SSE sets `Cache-Control: no-cache` + `X-Accel-Buffering: no`

## NEVER

1. NEVER write raw SQL — there is no database in this project; persistence is files + JSON manifests + FAISS
2. NEVER store secrets in source; NEVER return API keys in any response; never log full key values
3. NEVER implement features beyond SPEC.md — ask before adding (e.g., accounts, paid detectors, web search APIs)
4. NEVER use `console.log` / `print` for diagnostics — structlog (backend), `console.error` + error boundaries (frontend)
5. NEVER invent provider/model names — the only default model is `deepseek-v4-flash-free` (provider `zen`); verify any other model ID with the user before hardcoding
6. NEVER accept user-controlled URLs or paths — uploads go to UUID dirs; DuckDuckGo is the only outbound host
7. NEVER silently swallow parse/extraction failures — they become 422 `PARSE_FAILED` with a message
8. NEVER persist partial rewrite/detection state — streams are stateless; `done` is the contract
9. NEVER block an entire stream on one bad paragraph/fragment — degrade per unit (heuristics fallback, `checked: false`)
10. NEVER create files > 300 lines — split routers/services/agents into focused modules

## Code Patterns

### SSE Router (FastAPI)
```python
# src/app/routers/detect_router.py
@router.post("/api/detect")
async def detect(payload: DetectRequest, request: Request):
    async def stream():
        yield sse({"type": "block_score", "data": {...}})
        yield sse({"type": "done", "data": {...}})
    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
```

### SSE Frame (core)
```python
def sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"
```

### Frontend hook
```typescript
// Purpose: POST + ReadableStream → parsed SSE events (onEvent callback)
// Props: url, body, onEvent, signal
export function useSseStream() { /* fetch → reader → sse.parse(line) */ }
```

## File Naming Conventions
- Backend routers: `[feature]_router.py`; services: `[feature]_service.py`; schemas: `[feature]_schema.py`
- Frontend components: `PascalCase.tsx`; hooks: `use[Name].ts`; pages: `page.tsx`
- Shared UI primitives live in `components/ui/`; feature components in `components/{feature}/`

## Commit Message Format
```
[type]: [short description]
Types: feat | fix | refactor | docs | test | chore
Example: feat: add per-paragraph AI detection stream
```

## Build Discipline
- One phase at a time per BUILD_PLAN.md; verify (curl or browser) each deliverable before moving on
- Ask the user when stuck or when a spec gap appears — recommend the best approach
- No generic AI slop: every screen and stream serves the three-tool workflow with honest labeling
- Screenshots of working pages go in `imgs/` at the repo root

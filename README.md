# Nexus

Self-hosted AI workspace: chat, RAG, agents, and text generation in one app. Provider-agnostic — runs on OpenCode Zen (default), OpenAI, Anthropic, Gemini, or local Ollama.

## Stack

| Layer    | Tech |
|----------|------|
| Backend  | FastAPI, LangGraph, SQLAlchemy (SQLite V1, Postgres-ready), Alembic |
| Frontend | Next.js, React 19, Tailwind v4, shadcn/ui, TanStack Query, Zustand |
| Local    | uv (Python 3.12), pnpm, ruff/mypy (backend), Biome (frontend) |

## Layout

| Path | Contents |
|------|----------|
| `sdd/` | Specs: SPEC, PRD, SRS, SDS, TECH_STACK, BUILD_PLAN |
| `instructions/` | Skill instructions (ENHANCED-PROMPT, SKILL, PROMPTS) + original docs |
| `backend/` | FastAPI app (`src/app/`), uv project |
| `frontend/` | Next.js app (`src/`), pnpm project |

## Local development

Backend (port 8000):

```
cd backend
uv sync
cp .env.example .env    # fill ZEN_API_KEY / ZEN_BASE_URL
uv run uvicorn app.main:app --app-dir src --reload
```

Frontend (port 3000):

```
cd frontend
pnpm install
pnpm dev
```

## Docker

```
docker compose up --build          # api + web
docker compose --profile local-models up   # + bundled Ollama
```

## Quality gates

```
cd backend && uv run ruff check src && uv run mypy src && uv run pytest
cd frontend && pnpm lint && pnpm build
```

## Roadmap

See `sdd/BUILD_PLAN.md` — 7 phases; Phase 1 (scaffold + auth foundations) in progress, Phase 2 (DB models, auth, JWT cookies) next.
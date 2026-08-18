# Technology Stack: AIverse

| Technology | Version | Purpose |
|------------|---------|---------|
| **Python** | 3.12+ | Backend language |
| **FastAPI** | 0.115+ | REST + SSE API framework |
| **Uvicorn** | 0.32+ | ASGI server |
| **LangGraph** | >=1.2, <2 | Agent state machine — StateGraph, MessagesState, `RetryPolicy`/`TimeoutPolicy`, `astream_events` v3 |
| **LangChain** | 0.3+ | Chat-model abstraction, text splitters, FAISS vectorstore |
| **OpenAI SDK** | 1.x | OpenAI-compatible client — transport for the **Zen provider** (`ChatOpenAI(base_url=ZEN_BASE_URL)`) |
| **pypdf** | 5.x | PDF text extraction |
| **python-docx** | 1.1+ | DOCX parse + export |
| **reportlab** | 4.x | PDF export |
| **httpx** | 0.28+ | Outbound web search (DuckDuckGo), provider calls |
| **structlog** | 24+ | Structured logging |
| **uv** | latest | Python package manager (never pip) |
| **Next.js** | 16 (App Router, React 19) | Frontend framework |
| **TypeScript** | 5.x strict | Frontend language — `strict: true`, no `any` |
| **Tailwind CSS** | 4.x | Styling |
| **TanStack Query** | 5.x | Server state (file list) |
| **Zustand** | 5.x | Lightweight client state |
| **Lucide React** | latest | Icons |
| **Biome** | 1.9+ | Lint + format (TS) |
| **Ruff** | 0.8+ | Lint + format (Py) |
| **mypy** | 1.13+ (strict) | Type checking (Py) |
| **pytest + pytest-asyncio** | 8.x / 0.24+ | Backend test suite (unit/system/functional/security) |
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

Embeddings: `gemini`/`gemini-embedding-2` default; `openai`/`text-embedding-3-small` and `ollama`/`nomic-embed-text` supported.

## Runtime Requirements

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| RAM | 1 GB (cloud/Zen only) | 4 GB (with local models) |
| Disk | 1 GB | 5 GB (uploads + vectorstore) |
| CPU | 2 cores | 4 cores |

## Dependency Graph

```
[Browser]
   │
   ▼
[Next.js (frontend)] ──SSE POST /api/detect|plagiarism|humanize|chat; REST /api/files, /api/export
   │
   ▼
[FastAPI (backend)]
   ├── parse_service ── pypdf / python-docx / text → blocks
   ├── detect_service ── LLM (zen default) + heuristics → per-block AI%
   ├── plagiarism_service ── httpx → DuckDuckGo HTML → overlap scoring
   ├── humanize_service ── LLM 1–7 rewrite (structure preserved) → SSE
   ├── rag chat ── LangGraph StateGraph ── FAISS (data/vectorstore) ── tools: search_documents, analyze_ai_content
   ├── export_service ── python-docx / reportlab → DOCX / PDF
   └── data/ (uploads + vectorstore, on disk, no database)
```

## Why These Choices

| Decision | Rationale |
|----------|-----------|
| LangGraph for RAG chat | Native state machine with typed v3 event streaming, node `RetryPolicy`/`TimeoutPolicy`, matches the tool-loop chatbot |
| Zen provider via OpenAI-compatible client | One `ChatOpenAI(base_url=ZEN_BASE_URL)` covers zen + openai; free model `deepseek-v4-flash-free` = zero paid keys to start |
| Heuristics + LLM blend for detection | Statistical signals (burstiness, repetition, transitions) make scores stable and cheap; LLM adds reasoning per paragraph |
| DuckDuckGo HTML over paid search APIs | Zero cost, zero keys, sufficient for best-effort originality checks; honestly labeled |
| No database / no auth | Single-user local tool: files + JSON manifests + FAISS on disk is simpler, more private, and matches the brief |
| SSE over WebSockets | One-way streaming, reconnect-friendly, works through proxies |
| python-docx + reportlab | Battle-tested, small, produce spec-compliant DOCX/PDF preserving heading/list structure |

## Environment Placeholders (operator fills values)

All keys live in `.env` (backend) — values are placeholders, never committed. See `backend/.env.example`.

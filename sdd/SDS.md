# Software Design Specification: AIverse

**Version:** 1.0.0

## 1. System Architecture

### Architecture Pattern
REST + SSE API (FastAPI) with a Next.js SPA. Monolithic backend (one process) — single-user self-hosting scope. No database, no auth: files + JSON manifests + per-corpus FAISS indices on disk under `data/`. The AI layer is a LangGraph `StateGraph` (graph API: `MessagesState` + `add_messages` reducer, nodes return updates, model selection via runtime `context_schema`, node fault tolerance via `RetryPolicy`/`TimeoutPolicy`).

### High-Level Architecture
```
[Browser — Next.js :3001]
    → [FastAPI :8001]
        ├── parse (txt/md/json/pdf/docx → blocks)
        ├── detect (LLM score + heuristics → per-block AI%)
        ├── plagiarism (DuckDuckGo fragments → % + URLs)
        ├── humanize (LangGraph, 1–7 scale → rewritten blocks, SSE)
        ├── rag chat (LangGraph + FAISS + tools → grounded answer, SSE)
        ├── export (python-docx / reportlab)
        └── data/
            ├── uploads/{file_id}/original.ext + blocks.json
            └── vectorstore/index.faiss + meta.jsonl
    → [LLM factory: zen (ZEN_BASE_URL, OpenAI-compatible) | openai | anthropic | gemini | ollama]
    → [Embeddings: gemini | openai | ollama]
```

## 2. Folder Structure

### Backend (`backend/`)
```
backend/
├── pyproject.toml
├── Dockerfile
├── .env.example
├── data/                        # runtime artifacts (gitignored)
│   ├── uploads/{file_id}/       # original.ext + blocks.json
│   └── vectorstore/             # index.faiss + meta.jsonl
└── src/app/
    ├── main.py                  # FastAPI app, lifespan, CORS, routers, AppError handlers
    ├── core/
    │   ├── config.py            # pydantic-settings Settings (ZEN_API_KEY, ZEN_BASE_URL, ...)
    │   ├── llm.py               # get_chat_model / get_embeddings factory (5 providers)
    │   ├── blocks.py            # Block/Paragraph types + split utilities
    │   ├── exceptions.py        # AppError hierarchy + status map
    │   └── vector_store.py      # per-corpus FAISS add/search (excerpt + full text)
    ├── agents/
    │   ├── graph.py             # chat StateGraph build + compile (recursion_limit=30)
    │   ├── nodes.py             # chat_node, retrieve_node, analyze_node
    │   ├── tools.py             # search_documents, analyze_ai_content, current_datetime
    │   └── types.py             # AgentState (MessagesState subclass), ContextSchema
    ├── schemas/
    │   ├── file_schema.py       # FileOut, FileListOut
    │   ├── detect_schema.py     # DetectRequest, BlockScoreEvent, DetectDone
    │   ├── plagiarism_schema.py # PlagiarismRequest, FragmentEvent, PlagiarismDone
    │   ├── humanize_schema.py   # HumanizeRequest, BlockStart/Token/BlockEnd/Done
    │   ├── chat_schema.py       # ChatRequest, SseEvent models
    │   └── export_schema.py     # ExportRequest
    ├── routers/
    │   ├── files_router.py      # POST/GET/DELETE /api/files
    │   ├── detect_router.py     # POST /api/detect (SSE)
    │   ├── plagiarism_router.py # POST /api/plagiarism (SSE)
    │   ├── humanize_router.py   # POST /api/humanize (SSE)
    │   ├── chat_router.py       # POST /api/chat (SSE)
    │   ├── export_router.py     # POST /api/export (file download)
    │   └── health_router.py     # GET /health
    └── services/
        ├── parse_service.py     # file → blocks (txt/md/json/pdf/docx)
        ├── detect_service.py    # blocks → per-block AI% + reasons
        ├── plagiarism_service.py# fragments → DDG search + overlap scoring
        ├── humanize_service.py  # blocks → level rewrite (SSE orchestration)
        ├── rag_service.py       # upload→chunk→embed→index; retrieve
        └── export_service.py    # blocks → docx/pdf bytes
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
    │   ├── page.tsx            # landing → three tools
    │   ├── chat/page.tsx       # RAG chatbot + AI-locator
    │   ├── checker/page.tsx    # AI + plagiarism checker
    │   ├── remover/page.tsx    # humanizer (primary)
    │   └── layout.tsx / loading.tsx / error.tsx
    ├── components/
    │   ├── ui/                 # button, slider, file-drop, score-bar, toast
    │   ├── chat/               # ChatPane, MessageList, MessageItem, Composer, SourceChips
    │   ├── checker/            # UploadPane, ScoreBar, ParagraphCard, PlagiarismCard
    │   ├── remover/            # LevelSlider, RewritePane, CopyButton, DownloadButtons
    │   └── files/              # FilePicker (shared upload/select), FileBadge
    ├── lib/
    │   ├── api.ts              # fetch wrapper, typed { success, data, error }
    │   ├── sse.ts              # SSE stream parser
    │   ├── types.ts            # Block, FileMeta, DetectResult, Fragment, SseEvent
    │   └── utils.ts            # cn(), formatBytes(), downloadBlob()
    └── hooks/
        ├── useSseStream.ts     # fetch POST + ReadableStream → SSE events
        └── useFiles.ts         # list/upload/delete + invalidation
```

## 3. Persistence (no database)

### File layout
```
data/uploads/{file_id}/
├── original.{ext}
└── blocks.json                 # { "filename", "blocks": [ { "index", "type", "text", "ai_score": null, "reason": null } ] }
```
- `type ∈ heading | paragraph | list_item | blockquote`
- Manifest written atomically (write temp + rename) after save/extraction
- File list = scan of `data/uploads/*/blocks.json` (id = dir name)

### Vector store (RAG)
```
data/vectorstore/index.faiss    # single corpus (single user)
data/vectorstore/meta.jsonl     # per chunk: { chunk_id, file_id, filename, chunk_index, excerpt(300), text(full) }
```
- Chunking: `RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=100)`
- Retrieval: top_k = 4; delete file → rebuild index without its chunks

## 4. API Routes

### Public (no auth)
| Method | Route | Description |
|--------|-------|-------------|
| GET | /health | Health check |
| POST | /api/files | Upload file (multipart `file`) or raw text (`text` field) |
| GET | /api/files | List uploaded files |
| DELETE | /api/files/{id} | Delete file + blocks + vectors |
| POST | /api/detect | SSE: per-block AI scores + doc score |
| POST | /api/plagiarism | SSE: per-fragment web-match report |
| POST | /api/humanize | SSE: 1–7 structure-preserving rewrite |
| POST | /api/chat | SSE: RAG chatbot with AI-locator tool |
| POST | /api/export | DOCX/PDF download from blocks |

## 5. Request / Response Schemas

### POST /api/detect
**Request:** `{ "source": { "file_id": "uuid" } }` or `{ "source": { "text": "..." }, "model": "deepseek-v4-flash-free" }`
**Stream:**
```
data: {"type":"block_score","data":{"index":0,"score":82,"reason":"Smooth connective overuse; uniform sentence rhythm"}}

data: {"type":"done","data":{"doc_score":74,"blocks":[{"index":0,"type":"paragraph","text":"...","ai_score":82,"reason":"...","flagged":true}]}}
```

### POST /api/humanize
**Request:** `{ "source": { "file_id": "uuid" }, "level": 3 }`
**Stream:**
```
data: {"type":"block_start","data":{"index":0,"original":"..."}}
data: {"type":"token","data":{"content":"..."}}        # many
data: {"type":"block_end","data":{"index":0}}
data: {"type":"done","data":{"blocks":[{"index":0,"type":"heading","original":"...","rewritten":"..."}]}}
```

### POST /api/export
**Request:** `{ "blocks": [...], "format": "docx" }` → **200** binary download, `Content-Disposition: attachment`.

### Error envelope (non-SSE)
```json
{ "success": false, "error": { "code": "UNSUPPORTED_FILE_TYPE", "message": "Only txt, md, json, pdf, docx are allowed" } }
```

## 6. Key Algorithms & Business Logic

### Parsing (parse_service)
```
FUNCTION parse_bytes(data, ext) -> blocks:
  txt/md/json: decode utf-8; md → heading#/list-/quote> detection by line prefix; txt → paragraph by blank-line grouping
  docx: python-docx → runs grouped by style (Heading 1-3 → heading, List Bullet → list_item)
  pdf: pypdf per page → lines; blank-line grouping → paragraphs; heuristic: short bold-ish caps lines → heading
  return [{ index, type, text }]
```
- PDFs have no native structure: paragraphs joined; headings only when a line is short (< 60 chars) and all-caps or ends with `:` and followed by a long line

### Detection (detect_service)
```
heuristic_score(text):
  sentences = split_sentences(text)
  if len(sentences) < 2: return LLM-only weight
  burstiness = stddev(sentence lengths) / mean           # humans vary rhythm
  ttr = unique_tokens / total_tokens                     # humans repeat more
  rep_bigram = max freq(top 20 bigrams) / total_bigrams  # AI repeats set phrases
  transitions = count(Moreover,Furthermore,In addition,Additionally,In conclusion) / total_tokens
  punct = distinct punctuation chars (.,;:!?—"')
  score = clamp(0..100, weighted: +burstiness(favors human→lower AI), -ttr, +rep_bigram, +transitions, +uniform)
blend = 0.6 * llm_score + 0.4 * heuristic (clamped 0..100)
```

### Plagiarism (plagiarism_service)
```
FUNCTION check_fragments(text):
  fragments = split(text, ~120 words, sentence-aligned), max 40
  for f in fragments:
    results = duckduckgo_html_search(f"\"{first 8 tokens}\" {next 40 tokens}")   # fixed host; 1.5s spacing
    overlap = max token n-gram (n=8) overlap ratio vs each snippet
    matched = overlap ≥ 0.30 with ≥ 8 matching tokens
  doc_score = matched_fragments / total_fragments
```
- DDG HTML endpoint: `https://html.duckduckgo.com/html/?q=...`; parse with stdlib HTML parser or regex over result links + snippets; timeout 10 s; no key
- Response caps: parse at most 20 results, snippet ≤ 500 chars each

### Humanize (humanize_service)
System prompt per level:
```
Level 1-2 (max humanizing): casual contractions, varied rhythm, idiomatic phrasings, occasional short punchy sentences,
                            slight imperfection, keep meaning/numbers/facts exactly
Level 3-5 (balanced):        professional, clear, naturally varied, no obvious AI fillers
Level 6-7 (max corporate):   polished, confident, structured business tone, consistent rhythm
Rule: rewrite the paragraph body; keep meaning, facts, numbers; never restructure headings or lists
```

### RAG Chat (LangGraph)
```
AgentState(MessagesState): { iterations: int, source_chunks: list }
ContextSchema(TypedDict): { provider, model, temperature, file_ids: list | None }
builder = StateGraph(AgentState, context_schema=ContextSchema)
add_node("agent_node", agent_node, retry_policy=RetryPolicy(max_attempts=2))   # bind_tools([search_documents, analyze_ai_content])
add_node("tools_executor", tools_executor)
conditional: agent_node → tools_executor (tools pending AND iterations < 5) | END
set_node_defaults(timeout=TimeoutPolicy(run_timeout=60))
compile(); invoke via astream_events(version="v3") with recursion_limit=30; stream.messages → token events
tools: search_documents(query) → top-3 excerpts; analyze_ai_content(query) → detect on top-3 chunks → scores+suggestions
```

## 7. SSE Event Protocol (contract)

| Event | Emitted by | Payload |
|-------|-----------|---------|
| `meta` | chat | `{ conversation_id (client-sent), provider, model }` |
| `token` | chat/humanize | `{ content }` |
| `sources` | chat | `[{ file_id, filename, score, excerpt, ai_score }]` |
| `tool_start` / `tool_end` | chat | `{ tool, input }` / `{ tool, output }` |
| `block_score` | detect | `{ index, score, reason }` |
| `block_start` / `block_end` | humanize | `{ index, original }` / `{ index }` |
| `fragment` | plagiarism | `{ index, text, matched, overlap, matches: [{ url, title, overlap }] }` |
| `done` | all | mode-specific payload |
| `error` | all | `{ code, message }` (HTTP stays 200) |

Codes: `NO_DOCUMENTS`, `PROVIDER_NOT_CONFIGURED`, `PROVIDER_ERROR`, `PLAGIARISM_UNAVAILABLE`, `AGENT_LOOP_LIMIT`, `INTERNAL_ERROR`.

## 8. Environment Variables

```env
# App
APP_ENV=development

# LLM (Zen is default; OpenAI-compatible)
ZEN_API_KEY=
ZEN_BASE_URL=
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
GEMINI_API_KEY=
OLLAMA_BASE_URL=http://localhost:11434

# Defaults
DEFAULT_PROVIDER=zen
DEFAULT_MODEL=deepseek-v4-flash-free
TEMPERATURE=0.7

# Embeddings
EMBEDDING_PROVIDER=gemini
EMBEDDING_MODEL=gemini-embedding-2

# Runtime
DATA_DIR=./data
CORS_ORIGINS=http://localhost:3001
LOG_LEVEL=INFO
```

## 9. Security Design

- **Secrets:** server env only, pydantic-settings validated; never in responses or code
- **Uploads:** extension whitelist + magic-byte sniff (pdf `%PDF`, docx ZIP+`word/`, txt/md/json UTF-8 sniff); UUID storage dirs; sanitized original filename retained only for display
- **Downloads:** filename from `Content-Disposition` built from known blocks (no user path)
- **Outbound:** DDG fixed host via `httpx` with timeouts and max sizes; no user-controlled URLs
- **CORS:** explicit `CORS_ORIGINS`; no wildcard
- **Sizes:** 20 MB upload cap; 40 fragments; 20 results/fragment — bounded memory

## 10. Performance Design

- SSE headers: `Cache-Control: no-cache`, `X-Accel-Buffering: no`; generators only, never buffered
- Detection: heuristic pass in-process; LLM calls concurrent (semaphore 3), per-paragraph
- Plagiarism: 1.5 s spacing between DDG calls; progress events every fragment
- RAG: single FAISS index loaded lazily and cached in-process; top_k=4
- LLM node timeouts: `TimeoutPolicy(run_timeout=60)` + one retry on transient errors

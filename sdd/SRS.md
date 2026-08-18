# Software Requirements Specification: AIverse

**Version:** 1.0.0 | **Standard:** IEEE 830 | **Status:** Draft

## 1. Introduction

### 1.1 Purpose
This document is the engineering contract for AIverse V1. It specifies exact input/output behavior, error codes, and constraints for every feature. Developers and the AI coding agent implement from this document; testers validate against §6.

### 1.2 Scope
Covers: file intake (text/markdown/PDF/DOCX), AI-content detection (per-paragraph + whole-doc percentages), internet plagiarism checking (DuckDuckGo, free, no key), a 1–7 humanization engine with structure-preserving rewrites, a RAG chatbot over uploaded documents that flags AI-written sections and suggests changes, and DOCX/PDF export with a copy button. Excludes: accounts, teams, billing, per-user keys, paid detectors, web search API keys.

### 1.3 Definitions & Acronyms
| Term | Definition |
|------|------------|
| Block | One structural unit of a document: heading, paragraph, list item, blockquote |
| Paragraph | A non-heading text block (may be multi-sentence) |
| AI% | Per-paragraph AI-likelihood 0–100, blended LLM score + statistical heuristics |
| Plagiarism% | Fraction of fragments matched against web search results (best-effort, DuckDuckGo) |
| Humanize scale | 1 = maximum humanizing, 7 = maximum corporate tone |
| Zen | OpenCode Zen API — OpenAI-compatible provider; default model `deepseek-v4-flash-free` |
| SSE | Server-Sent Events — server→client streaming over HTTP |
| Fragment | Plagiarism-check unit ≈ 120 words / 2–3 sentences |

## 2. Overall Description

### 2.1 Product Perspective
Standalone self-hosted application: Next.js frontend + FastAPI backend + on-disk file/vector storage. No accounts, no database. Only external dependencies are optional LLM APIs (Zen default, OpenAI-compatible) and an embedding provider for RAG. Reference tools: Turnitin, ZeroGPT, GPTZero, Grammarly, Duplichecker.

### 2.2 User Characteristics
Individuals (students, researchers, writers) who need to locate AI-written content, check originality, and rework text. Single local user; technical level: can run Docker.

### 2.3 Assumptions & Dependencies
- At least one LLM provider configured; Zen (`ZEN_API_KEY`, `ZEN_BASE_URL`) is the default
- Embedding provider configured for RAG (Gemini recommended; OpenAI/Ollama allowed)
- Plagiarism search is best-effort: DuckDuckGo HTML results, no API key, no guarantee of completeness
- All timestamps ISO 8601 UTC; all IDs are UUID4 strings
- Files persist on disk under `data/`; no database

## 3. Functional Requirements

### FR-01: File Intake & Parsing
- **Input:** `POST /api/files` (multipart, field `file`; or `text` field with plain text). Allowed types: `.txt`, `.md`, `.json`, `.pdf`, `.docx`; max 20 MB
- **Processing:** validate type by extension + magic bytes → save original to `data/uploads/{file_id}/` → extract text with structure (headings via font-size/style for docx; heading markers for md; pdf via pypdf, paragraphs by line grouping) → split into blocks
- **Output (201):** `{ success: true, data: { id, filename, size_bytes, block_count, paragraphs, created_at } }` (blocks include `type`, `text`, `ai_score: null` initially)
- **Error Cases:**
  - Wrong type → 422 `UNSUPPORTED_FILE_TYPE`
  - > 20 MB → 413 `FILE_TOO_LARGE`
  - Extraction failure → 422 `PARSE_FAILED` with message
  - Empty text / empty document → 422 `EMPTY_DOCUMENT`

### FR-02: AI-Content Detection
- **Input:** `POST /api/detect` — body `{ source: { file_id } | { text }, model?: string }`
- **Processing:** parse blocks (if file) → for each paragraph: (1) LLM scores 0–100 with a one-line reason (prompt per §SDS 6), (2) heuristics computed: burstiness (sentence-length variance), type-token ratio, bigram repetition, transition-phrase density, punctuation variety → blended score `0.6·LLM + 0.4·heuristic`, clamp 0–100 → doc-level = paragraph-count-weighted mean
- **Output (200, SSE):** stream of `block_score` events (`{ index, score, reason }`) then `done` with `{ doc_score, blocks: [{ index, type, text, ai_score, reason, flagged }] }`
- **Error Cases:** empty doc → 422; provider missing → error event `PROVIDER_NOT_CONFIGURED`; provider failure → error event `PROVIDER_ERROR`
- **Rules:** flagged = ai_score ≥ 70 (threshold configurable); scores never block the stream; LLM failures fall back to heuristics-only with `reason: "heuristic"`

### FR-03: Plagiarism Check
- **Input:** `POST /api/plagiarism` — body `{ source: { file_id } | { text } }`
- **Processing:** split text into fragments (~120 words, 2–3 sentences) → for each fragment query DuckDuckGo HTML (`https://html.duckduckgo.com/html/?q=…`, fixed host, no SSRF) → parse result titles/URLs/snippets → compute token-overlap ratio (≥ 8-token n-gram match counts) → fragment report `{ fragment, matched, overlap, matches: [{ url, title, overlap }] }` → doc-level = matched-fragments ÷ total
- **Output (200, SSE):** `fragment` events then `done` with `{ doc_score, fragments: [...] }`
- **Error Cases:** empty doc → 422; DDG unreachable/rate-limited → error event `PLAGIARISM_UNAVAILABLE` (checker still returns per-fragment results with `checked: false` where possible); provider not needed
- **Rules:** max 40 fragments checked per request (truncate tail with note); per-fragment rate limiting ≈ 1 request per 1.5 s; results marked `best-effort`

### FR-04: Humanizer (1–7)
- **Input:** `POST /api/humanize` — body `{ source: { file_id } | { text }, level: 1..7, model?: string }`
- **Processing:** parse blocks → LLM rewrites each paragraph at the given level (system prompt per §SDS 6) → preserve headings, list markers, blockquote, bold/italic runs → stream tokens per paragraph
- **Output (200, SSE):** `block_start`/`token`/`block_end` events, then `done` with `{ blocks: [{ index, type, original, rewritten }] }`
- **Error Cases:** level outside 1–7 → 422 `INVALID_LEVEL`; empty doc → 422; provider errors → error event `PROVIDER_ERROR`
- **Rules:** levels 1–2 aggressive humanizing (contractions, varied rhythm, minor imperfection), 3–5 balanced professional, 6–7 polished corporate; never change meaning/numbers; headings never rewritten (only their body blocks)

### FR-05: Export & Copy
- **Input:** `POST /api/export` — body `{ blocks: [...], format: "docx" | "pdf" }`
- **Processing:** rebuild document from blocks: docx via python-docx (heading styles, bold/italic, bullet lists, blockquotes); pdf via reportlab (heading sizes, wrapped paragraphs)
- **Output (200):** file download with `Content-Disposition: attachment; filename="humanized.docx|pdf"`; copy handled client-side (browser clipboard)
- **Error Cases:** empty blocks → 422; unsupported format → 422 `INVALID_FORMAT`
- **Rules:** export preserves order and structure exactly; paragraphs separated per original block

### FR-06: RAG Chatbot (AI-locator)
- **Input:** `POST /api/chat` (SSE) — body `{ message, file_ids?: [uuid] }`
- **Processing:** embed query → FAISS retrieve top-4 chunks from the selected corpus (all ready files, or `file_ids` only) → LangGraph agent with tools `search_documents` and `analyze_ai_content` (runs FR-02 detection on retrieved chunks and returns scores + flagged paragraphs + suggestions) → stream answer tokens; if the question asks about AI content, the bot cites `[N]` markers with `sources` event containing filename + chunk excerpt + per-chunk ai_score
- **Output (200, SSE):** `meta`, `token`, `sources` (rag only, before tokens), `tool_start`/`tool_end` (agent calls), `done`
- **Error Cases:** no ready documents → error event `NO_DOCUMENTS`; provider missing → `PROVIDER_NOT_CONFIGURED`; message empty → 422
- **Rules:** answers grounded in retrieved chunks; scores/suggestions always from the `analyze_ai_content` tool output; recursion limit 30

### FR-07: File Management
- **Input:** `GET /api/files`, `DELETE /api/files/{id}`
- **Output (200/204):** list of `{ id, filename, size_bytes, block_count, status, created_at }`; delete removes `data/uploads/{id}/` + its vectors
- **Error Cases:** missing ID → 404 `NOT_FOUND`; delete removes vectors + stored file (FR-08 rule)

### FR-08: Health
- **Input:** `GET /health`
- **Output (200):** `{ success: true, data: { status: "ok", version } }`

## 4. External Interface Requirements

### 4.1 User Interface
- Three tools: Chatbot, Checker (AI + plagiarism), Remover — with shared file picker; remover is the primary page
- Streaming regions have `aria-live="polite"`; progress shown while streaming
- Checker shows per-paragraph score bars (red ≥ 70, amber 40–69, green < 40) + flagged sections highlightable
- Remover: 1–7 slider, Copy button, Download DOCX, Download PDF
- All screens: loading / error / empty / populated states

### 4.2 API Interface
- All JSON responses: `{ success: boolean, data?: any, error?: { code, message } }` (SSE and downloads are exceptions)
- IDs UUID4; timestamps ISO 8601 UTC
- SSE events: `data: {json}\n\n` frames with types per FR-02/03/04/06

### 4.3 Database Interface
- None. Persistence: files + JSON manifests + FAISS on disk under `data/`

## 5. System Attributes

### 5.1 Security
- No secrets in code; provider keys via `.env` only (validated by pydantic-settings)
- Upload validation: extension whitelist + magic-byte sniffing; stored under UUID dirs (no user-controlled paths)
- Downloads: `Content-Disposition` filename sanitized; no path traversal
- CORS restricted to `CORS_ORIGINS`
- Outbound web search: fixed DuckDuckGo host only (no SSRF); response size caps
- Zip-bomb / decompression: no archive types accepted; 20 MB hard cap
- Provider errors logged with structlog; generic client messages

### 5.2 Performance
- SSE: `Cache-Control: no-cache`; `X-Accel-Buffering: no`
- Detection: heuristics in-process (<100 ms); LLM per paragraph with concurrency 3
- Plagiarism: ≤ 40 fragments/request, 1.5 s spacing → worst case ~60 s; progress events throughout
- RAG retrieval top_k = 4; chunk 800/100
- LLM node timeouts: `TimeoutPolicy(run_timeout=60)` + in-process retry once on transient errors

### 5.3 Reliability
- Detection never fails whole-doc on one bad paragraph — per-paragraph fallback to heuristics
- Plagiarism degrades gracefully when DDG is down
- Humanizer streams per block; a failed block is reported and skipped, stream continues
- All disk operations wrapped; partial uploads cleaned up
- Uploaded docs never silently lost: manifest written after save; failed extraction → 422 with cleanup

### 5.4 Maintainability
- Env vars validated at startup (pydantic-settings)
- Business logic in services; routers thin
- Agents live only in `agents/` (LangGraph)
- Ruff + mypy strict; Biome + `tsc --noEmit` clean
- No file > 300 lines; header comment on every file (path, purpose, exports, deps)

## 6. Validation & Testing Criteria

| Requirement | Test Case | Expected Result |
|-------------|-----------|-----------------|
| FR-01 | Upload valid .docx | 201 + blocks with headings preserved |
| FR-01 | Upload .exe | 422 `UNSUPPORTED_FILE_TYPE` |
| FR-01 | Upload 25 MB | 413 `FILE_TOO_LARGE` |
| FR-01 | Upload empty .txt | 422 `EMPTY_DOCUMENT` |
| FR-02 | Detect on known-AI sample text | 200; `done` doc_score ≥ 70 for AI-style paragraph, reason present |
| FR-02 | Detect without provider key | error event `PROVIDER_NOT_CONFIGURED`, HTTP 200 |
| FR-03 | Fragment present verbatim on web (fixture test hits DDG live; unit test uses fixture HTML) | `matched: true` + URL; doc_score reflects matched fragments |
| FR-03 | Empty text | 422 `EMPTY_DOCUMENT` |
| FR-04 | Level 1 rewrite of sample | stream ends `done`; rewritten differs, meaning preserved; blocks/headings count unchanged |
| FR-04 | Level 8 | 422 `INVALID_LEVEL` |
| FR-05 | Export docx + pdf | Both files valid (openable), same block order/content |
| FR-06 | Chat "where is the AI content?" with uploaded doc | `sources` + `done`; answer cites `[N]` with score/suggestion |
| FR-06 | Chat with no ready files | error event `NO_DOCUMENTS` |
| FR-07 | DELETE file | 204; uploads dir + vectors gone |
| FR-08 | GET /health | 200 `{ status: "ok" }` |
| Security | Upload with disguised extension (exe renamed .txt) | magic-byte check rejects (422) |
| Security | Path traversal in filename | sanitized; stored under UUID dir |

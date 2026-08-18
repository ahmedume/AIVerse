# Build Plan: AIverse

## Strategy

Divide and conquer. Each phase is self-contained with a clear deliverable. Complete each phase fully before moving to the next. Never jump ahead. Compact code everywhere — a function over a 100-line component; nothing over 300 lines.

---

## Phase 1: Spec + Scaffold
**Goal:** Spec set finalized; backend/frontend scaffolded; Nexus remnants scrubbed.
**Depends on:** Nothing

**Tasks:**
1. Replace `sdd/` with AIverse spec set (PRD, SRS, SDS, SPEC, TECH_STACK, BUILD_PLAN, SKILL, PROMPTS)
2. Scrub Nexus code: remove auth/DB/conversations/admin/templates/settings from backend; remove Nexus pages/components from frontend
3. Scaffold AIverse folders per SDS §2 with header comments on every file
4. Backend: `pyproject.toml` (uv), `core/config.py` (pydantic-settings), `core/exceptions.py`, `GET /health`; frontend: keep Next.js scaffold, strict tsconfig, Biome
5. Stop old servers; `.env` + `.env.example` rewritten for AIverse

**Deliverable:** Repo builds; `/health` returns ok; empty-but-correct folder structure.

**Out of scope:** Any feature logic.

---

## Phase 2: File Intake & Parsing
**Goal:** Files in → structured blocks out; list/delete working.
**Depends on:** Phase 1

**Tasks:**
1. `services/parse_service.py`: txt/md/json/pdf/docx → blocks (headings, paragraphs, list_items, blockquotes) per SDS §6
2. `routers/files_router.py`: `POST /api/files` (multipart + raw text), `GET /api/files`, `DELETE /api/files/{id}`; magic-byte validation; atomic manifest write
3. Tests: happy path docx/md/txt/pdf; wrong type; > 20 MB; disguised extension; empty document; delete removes everything

**Deliverable:** curl-verified upload/parse/list/delete with blocks.json on disk.

**Out of scope:** Detection, plagiarism, humanize, chat.

---

## Phase 3: Detection
**Goal:** Per-paragraph AI% + doc score streaming over SSE.
**Depends on:** Phase 2

**Tasks:**
1. `core/blocks.py` split utilities + `services/detect_service.py`: heuristic scorer (burstiness, TTR, bigram repetition, transition density, punctuation variety) + LLM scorer (concurrent, semaphore 3) + 0.6/0.4 blend
2. `routers/detect_router.py`: SSE `block_score` → `done` with blocks (flagged ≥ 70)
3. Provider error semantics: `PROVIDER_NOT_CONFIGURED` / `PROVIDER_ERROR` events; per-paragraph heuristic fallback
4. Tests: AI-style sample scores ≥ 70; human-style ≤ 40; provider-missing → error event; heuristic-only fallback; stream shape

**Deliverable:** curl-verified SSE detection stream with sensible scores.

**Out of scope:** Plagiarism, humanize, chat.

---

## Phase 4: Plagiarism Check
**Goal:** Per-fragment web-match report + doc score over SSE.
**Depends on:** Phase 3 (block splitting reuse)

**Tasks:**
1. `services/plagiarism_service.py`: fragment splitter (~120 words, sentence-aligned, max 40) + DDG HTML search (fixed host, timeout, caps, 1.5 s spacing) + token n-gram overlap scoring
2. `routers/plagiarism_router.py`: SSE `fragment` → `done`
3. Graceful degradation: DDG down → `PLAGIARISM_UNAVAILABLE` note; per-fragment `checked` flags
4. Tests: fixture-HTML matching (unit, no network); live DDG smoke (skipped by default); empty text; caps

**Deliverable:** curl-verified SSE stream with matched URLs on a distinctive sentence.

**Out of scope:** Humanize, chat.

---

## Phase 5: Humanizer + Export
**Goal:** 1–7 rewrite streaming per block; DOCX/PDF download.
**Depends on:** Phase 2

**Tasks:**
1. `services/humanize_service.py`: per-level system prompts (1–2 aggressive human, 3–5 balanced, 6–7 corporate), per-block rewrite, headings/lists untouched, SSE `block_start`/`token`/`block_end`/`done`
2. `services/export_service.py`: blocks → docx (python-docx: heading styles, bullets, quotes, bold/italic) and pdf (reportlab: headings, wrapped paragraphs)
3. `routers/humanize_router.py` + `routers/export_router.py`
4. Tests: level validation; block/heading count preserved; meaning preserved (numbers intact); docx/pdf bytes openable (python-docx/reportlab re-open); empty blocks → 422

**Deliverable:** curl-verified streaming rewrite + valid DOCX/PDF downloads.

**Out of scope:** Chat.

---

## Phase 6: RAG Chatbot
**Goal:** Grounded Q&A over uploads with AI-locator tool.
**Depends on:** Phases 2–3

**Tasks:**
1. `core/vector_store.py`: FAISS index + meta.jsonl (excerpt + full text), rebuild-on-delete
2. `agents/`: `types.py` (AgentState, ContextSchema), `tools.py` (search_documents, analyze_ai_content, current_datetime), `nodes.py`, `graph.py` (RetryPolicy max 2, TimeoutPolicy 60, recursion_limit 30, `astream_events` v3)
3. `services/rag_service.py`: chunk 800/100 → embed → index; retrieve top_k=4
4. `routers/chat_router.py`: SSE `meta`/`token`/`sources`/`tool_start`/`tool_end`/`done`/`error`
5. Tests: NO_DOCUMENTS; retrieval returns owned chunks (single-user → all); analyze tool output shape; loop cap

**Deliverable:** curl-verified streaming chat with citations and AI-score tool output.

**Out of scope:** Auth, persistence of chats.

---

## Phase 7: Frontend — three tools
**Goal:** Landing + Chatbot + Checker + Remover pages, fully wired.
**Depends on:** Phases 2–6 (API surface)

**Tasks:**
1. `lib/api.ts`, `lib/sse.ts`, `hooks/useSseStream.ts`, `hooks/useFiles.ts`
2. Remover (`/remover`, primary): FilePicker, LevelSlider 1–7, streaming RewritePane, CopyButton, Download DOCX/PDF
3. Checker (`/checker`): UploadPane, doc-level AI% + plagiarism% bars, ParagraphCards with scores/reasons, PlagiarismCards with URLs
4. Chatbot (`/chat`): FilePicker, ChatPane, streaming cursor, SourceChips (filename + score + ai_score)
5. Landing `/` linking the three; loading/empty/error states everywhere; accessibility (aria-live on streams)

**Deliverable:** All three tools work end-to-end in the browser against the live API.

**Out of scope:** Dark-mode polish, i18n.

---

## Phase 8: Hardening, Docker & Validation
**Goal:** Production-grade pass + full validation.
**Depends on:** All phases

**Tasks:**
1. Docker: `backend/Dockerfile` (multi-stage, `uv sync --frozen`), `frontend/Dockerfile` (`next build`), root `docker-compose.yml` (api + web + ollama profile), `.dockerignore` excluding `data/`
2. Security tests: path traversal, disguised binaries, CORS, download headers, size caps, no secrets in responses
3. Integration script: upload → detect → plagiarism → humanize → export → chat, asserted end-to-end
4. Final gates: ruff + mypy clean, pytest green, `tsc --noEmit` + Biome clean, no TODO stubs
5. Screenshots of every page (working) into `imgs/`

**Deliverable:** `docker compose up` runs the full stack; every SRS §6 criterion green; screenshots saved.

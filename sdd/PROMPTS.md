# Execution Prompts: AIverse

Always ensure SPEC.md, SRS.md, SDS.md, and SKILL.md are loaded in context before using these. Run the SETUP prompt first.

---

## SETUP PROMPT (Run This First)
```
Read all .md files in sdd/: SPEC.md, PRD.md, SRS.md, SDS.md, SKILL.md, TECH_STACK.md, BUILD_PLAN.md.
Confirm by summarizing: (1) what AIverse is, (2) the tech stack (incl. default Zen provider
and model deepseek-v4-flash-free), (3) the folder structure, (4) the 5 most important
SKILL.md rules (esp. maximum code compaction). Do not write any code until I say "proceed".
```

---

## PROMPT 1: Scaffold + Scrub
```
Scrub all Nexus-era code (auth, database, conversations, admin, templates, settings).
Scaffold AIverse per SDS.md §2: backend/src/app/{core,agents,schemas,routers,services},
frontend/src/{app,components,hooks,lib,stores}. Empty files with header comments only.
core/config.py (pydantic-settings incl. ZEN_API_KEY, ZEN_BASE_URL), core/exceptions.py,
GET /health. Rewrite backend/.env and .env.example (no secrets).
Structure only + health. No business logic yet.
```

---

## PROMPT 2: File Intake & Parsing
```
Implement per SRS.md FR-01 and SDS.md §6 (parsing):
- services/parse_service.py: txt/md/json/pdf/docx → blocks [{index, type, text}] with
  heading/list_item/blockquote detection (md line prefixes; docx styles; pdf blank-line
  grouping + short-line heading heuristic)
- routers/files_router.py: POST /api/files (multipart `file` or `text` field, 20MB cap,
  magic-byte validation), GET /api/files, DELETE /api/files/{id}
- Manifest blocks.json written atomically to data/uploads/{uuid}/
Error codes exactly per SRS.md FR-01 (UNSUPPORTED_FILE_TYPE 422, FILE_TOO_LARGE 413,
PARSE_FAILED 422, EMPTY_DOCUMENT 422, NOT_FOUND 404).
Write pytest coverage for all error paths + happy path. Verify with curl.
```

---

## PROMPT 3: AI Detection
```
Implement per SRS.md FR-02 and SDS.md §6 (detection):
- services/detect_service.py: heuristic_score (burstiness = sentence-length stddev/mean,
  type-token ratio, top-bigram repetition, transition-phrase density, punctuation variety)
  + LLM_score (0-100 + one-line reason, semaphore 3) blended 0.6 LLM / 0.4 heuristic
- routers/detect_router.py: SSE block_score events → done {doc_score, blocks}
- flagged = ai_score >= 70; per-paragraph heuristic-only fallback on LLM failure
Error events: PROVIDER_NOT_CONFIGURED / PROVIDER_ERROR (HTTP stays 200).
Tests: AI-style fixture >= 70, human-style <= 40, provider-missing error event, fallback.
Verify with curl -N.
```

---

## PROMPT 4: Plagiarism Check
```
Implement per SRS.md FR-03 and SDS.md §6 (plagiarism):
- services/plagiarism_service.py: sentence-aligned fragments (~120 words, max 40);
  httpx GET https://html.duckduckgo.com/html/?q=... (fixed host, 10s timeout, parse
  result titles/URLs/snippets, max 20 results, snippet <= 500 chars); token n-gram (n=8)
  overlap vs snippets; matched when >= 8 tokens match; 1.5s spacing between queries
- routers/plagiarism_router.py: SSE fragment events → done {doc_score, fragments}
- DDG unreachable → PLAGIARISM_UNAVAILABLE note + per-fragment checked flags
Unit tests with fixture HTML (no network); live smoke test marked @pytest.mark.smoke.
Verify with curl -N on a distinctive sentence.
```

---

## PROMPT 5: Humanizer + Export
```
Implement per SRS.md FR-04/FR-05 and SDS.md §6 (humanize + export):
- services/humanize_service.py: per-level system prompts (1-2 max humanizing, 3-5
  balanced, 6-7 max corporate); rewrite each paragraph; never rewrite headings; SSE
  block_start/token/block_end/done
- services/export_service.py: blocks → docx via python-docx (Heading 1-3 styles, bullet
  lists, blockquote, bold/italic runs) and pdf via reportlab (heading sizes, wrapped text)
- routers/humanize_router.py (SSE) + routers/export_router.py (Content-Disposition download)
Error codes: INVALID_LEVEL 422, INVALID_FORMAT 422, EMPTY_DOCUMENT 422.
Tests: block/heading count preserved, numbers preserved, levels 1..7, docx+pdf round-trip.
Verify with curl -N + download both formats.
```

---

## PROMPT 6: RAG Chatbot
```
Implement per SRS.md FR-06 and SDS.md §6 (rag chat):
- core/vector_store.py: FAISS + meta.jsonl (chunk_id, file_id, filename, excerpt 300, text);
  add/search/rebuild-on-delete; chunk 800/100; top_k=4
- agents/: types.py AgentState(MessagesState)+ContextSchema, tools.py
  (search_documents top-3 excerpts, analyze_ai_content detection on chunks, current_datetime),
  nodes.py, graph.py with RetryPolicy(max_attempts=2), TimeoutPolicy(run_timeout=60),
  recursion_limit=30, astream_events(version="v3"), iterations<5 loop guard
- routers/chat_router.py: SSE meta/token/sources/tool_start/tool_end/done/error
Error events: NO_DOCUMENTS, PROVIDER_NOT_CONFIGURED, PROVIDER_ERROR, AGENT_LOOP_LIMIT.
Tests: no-docs error, sources shape, analyze tool output, loop cap.
Verify with curl -N.
```

---

## PROMPT 7: Frontend — three tools
```
Implement per SPEC.md §7 Screens 1-4 and SDS.md §2 (frontend):
- lib/api.ts ({success,data,error} fetch client), lib/sse.ts parser,
  hooks/useSseStream.ts (POST + ReadableStream), hooks/useFiles.ts
- /remover (primary): FilePicker (upload or paste), LevelSlider 1-7, streaming
  RewritePane (original ↔ rewritten per block), CopyButton, Download DOCX/PDF
- /checker: UploadPane, doc-level AI% + plagiarism% ScoreBars, ParagraphCard list
  (score bar, reason, flagged ≥ 70), PlagiarismCard (fragment, matches, URLs)
- /chat: FilePicker, ChatPane, MessageList streaming cursor, SourceChips (filename,
  score, ai_score), Composer
- / landing with three tool cards; loading/empty/error states; aria-live on streams
Wire real API calls. Verify every flow in the browser.
```

---

## PROMPT 8: Docker & Hardening
```
Per BUILD_PLAN.md Phase 8:
- backend/Dockerfile (multi-stage, uv sync --frozen, non-root), frontend/Dockerfile
  (next build, standalone), docker-compose.yml (api + web + ollama profile with
  profiles: [local-models]), .dockerignore excluding data/ and .env
- Security tests: path traversal, disguised binaries, CORS, download headers, size caps
- Integration script: upload → detect → plagiarism → humanize → export → chat
Final gates: ruff + mypy clean, pytest green, tsc --noEmit + Biome clean, no TODO stubs.
Take screenshots of every working page into imgs/.
```

---

## PROMPT 9: Debug / Fix
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

## PROMPT 10: Review & Spec Check
```
Review the current implementation against SPEC.md and SRS.md.
Report (do not fix yet):
1. Missing features (not implemented)
2. Incorrectly implemented (behavior deviates from SRS, incl. status codes + SSE event shapes)
3. Out of scope (implemented but not in SPEC.md)
4. SKILL.md violations (comments, file sizes, naming, error handling gaps)
```

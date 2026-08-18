# Project Specification: AIverse

## 1. Overview
- **Project Name:** AIverse
- **One-Line Description:** A self-hosted AI-content detection + humanization toolkit: find AI-written text in your documents, check originality against the web, and rewrite at 7 humanize levels — with DOCX/PDF export
- **Goal:** Give one user the three workflows Turnitin/ZeroGPT/GPTZero cover — detect, compare, rewrite — in one local, provider-agnostic app
- **Target Users:** Students, researchers, and writers who need to locate AI content, verify originality, and adapt tone
- **Version:** 1.0.0 (MVP)

## 2. Problem Statement

AI-written text is everywhere, and existing tools are scattered: detectors are paywalled and give no location or fix guidance; plagiarism checkers require accounts and upload-to-vendor; humanizers are generic "AI humanizers" with no control over tone and no document output. AIverse solves this: one self-hosted toolkit where the user's text never leaves their machine, with per-paragraph AI detection (where + how much + what to change), a best-effort web originality check, and a 1–7 humanize scale with structure-preserving DOCX/PDF download. Powered by the OpenCode Zen API (`deepseek-v4-flash-free` free tier) by default — zero paid keys required to start.

## 3. Core Features (MVP — MUST HAVE)

### Feature 1: File Intake (Agent 1 — Input)
- **Description:** Accept text, PDF, or DOCX (also txt/md/json); parse into structured blocks (headings, paragraphs, lists, quotes) so detection/rewrite/export preserve layout
- **User Flow:** Upload a file or paste text → app parses and shows block count → ready to detect/rewrite/chat
- **Inputs:** file (txt/md/json/pdf/docx, ≤ 20 MB) or plain text
- **Outputs:** structured document (blocks) stored locally
- **Rules:** magic-byte validation; empty documents rejected

### Feature 2: RAG Chatbot — AI-locator (Agent 2)
- **Description:** Chat over your uploaded documents. The bot searches the PDF/file corpus and tells you where the most AI content is detected, what to change, and suggests alternatives — with citations
- **User Flow:** Upload docs → open Chatbot → "where is the most AI content in my paper?" → answer with `[N]` citations, per-section AI scores, and concrete suggestions
- **Inputs:** chat message (+ optional file selection)
- **Outputs:** streamed grounded answer with source chips + AI scores + suggestions
- **Rules:** retrieval top-4 chunks; `analyze_ai_content` tool runs detection on retrieved chunks; no ready docs → friendly error

### Feature 3: AI + Plagiarism Checker (Agent 4)
- **Description:** Paste text or upload a file. Output: "AI detected: X% & plagiarism detected: Y%". Per-paragraph AI bars; per-fragment web-match report with URLs (best-effort DuckDuckGo search, no key)
- **User Flow:** Open Checker → paste/upload → Run → scores stream in per paragraph/fragment → click a red paragraph to see reason and suggested change
- **Inputs:** text or file
- **Outputs:** doc-level AI% and plagiarism%, per-paragraph breakdown, matched URLs
- **Rules:** plagiarism is best-effort (marked as such); AI% = LLM score + statistical heuristics

### Feature 4: AI Content Remover (Agent 3) — Main Page
- **Description:** Upload docx/pdf/text, pick a level (1 = maximum humanizing → 7 = maximum corporate), get a structure-preserving rewrite with a copy button and DOCX/PDF download
- **User Flow:** Open Remover → upload/paste → set level → Rewrite → tokens stream in per paragraph → Copy or Download DOCX/PDF
- **Inputs:** text/file, `level: 1..7`
- **Outputs:** rewritten blocks (headings/lists preserved), copyable; docx/pdf export (Agent 5)
- **Rules:** meaning/facts/numbers never change; headings never rewritten

### Feature 5: Export (Agent 5)
- **Description:** Download the rewritten document as DOCX or PDF
- **User Flow:** After rewrite → Download DOCX / Download PDF
- **Outputs:** valid, openable files preserving block structure

## 4. End-to-End User Flow

1. User lands on `/` → picks a tool (Remover is the hero)
2. Remover: uploads `essay.docx` → parser extracts blocks with headings → user sets level 3 → "Rewrite" → paragraphs stream in, rewritten → user reviews per-paragraph diff → clicks Copy, or Download DOCX/PDF
3. Checker: pastes the same text → "Check" → AI% and plagiarism% appear; red paragraphs highlight; user sees reasons + matched URLs
4. Chatbot: user uploads their paper, asks "where is the AI content?" → bot cites sections with scores and change suggestions
5. All three share one local corpus; deleting a file removes its vectors

## 5. System Behavior (Logic Rules)

- No accounts; no data leaves the machine except: provider LLM calls (zen/cloud/ollama) and DuckDuckGo fragment queries
- Detection never blocks the stream on one bad paragraph — heuristics-only fallback per paragraph
- Plagiarism: max 40 fragments, 1.5 s spacing; DDG outage → graceful `PLAGIARISM_UNAVAILABLE` note, results still returned for checked fragments
- Humanizer: level 1 = most human, 7 = most corporate; facts/numbers invariant; headings/lists untouched
- RAG chatbot: grounded in retrieved chunks only; `AGENT_LOOP_LIMIT` error if the loop exceeds recursion 30
- Deleted file → vectors removed; export requires non-empty blocks

**Edge Cases:**
- Empty document/paste → 422 `EMPTY_DOCUMENT`
- Wrong file type / disguised binary → 422 `UNSUPPORTED_FILE_TYPE`
- Provider key missing → `PROVIDER_NOT_CONFIGURED` error event
- Zen slow/hanging → `TimeoutPolicy(60s)` → retry once → fallback provider
- Very long text → detection/heuristics still bounded; plagiarism truncated at 40 fragments with a note
- Mid-stream disconnect → server aborts; nothing persisted (no partial state)

## 6. Data Model (Entities — no database, on-disk)

### Entity: UploadedFile
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| id | TEXT (uuid4) | Yes | Directory name under `data/uploads/` |
| filename | VARCHAR(255) | Yes | Sanitized original, display only |
| size_bytes | INTEGER | Yes | |
| blocks | JSON | Yes | `[{ index, type, text, ai_score?, reason? }]` |
| created_at | TIMESTAMP | Yes | ISO 8601 UTC |

### Entity: VectorChunk (RAG corpus)
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| chunk_id | TEXT | Yes | In FAISS index + meta.jsonl |
| file_id / filename | TEXT | Yes | Ownership for delete/rebuild |
| excerpt | TEXT | Yes | 300 chars for display |
| text | TEXT | Yes | Full chunk (model context) |

## 7. UI Screens

### Screen 1: Landing `/`
- **Purpose:** Present the three tools; CTA into Remover
- **Components:** Navbar, hero, three tool cards, self-hosted note, footer

### Screen 2: Chatbot `/chat`
- **Purpose:** RAG Q&A + AI-locator over uploaded documents
- **Components:** FilePicker, ChatPane, MessageList (streaming cursor), SourceChips (filename + score + ai_score), Composer
- **States:** loading / empty / streaming / error / populated

### Screen 3: Checker `/checker`
- **Purpose:** AI% + plagiarism% per document
- **Components:** UploadPane (file or paste), Run button, ScoreBar (doc-level AI% + plagiarism%), ParagraphCard list (score bar, reason, flagged highlight), PlagiarismCard (fragment, matched URLs)
- **States:** idle / detecting / checking / done / error / empty

### Screen 4: Remover `/remover` (primary)
- **Purpose:** 1–7 humanization with export
- **Components:** UploadPane, LevelSlider (1–7 labels), Rewrite button, RewritePane (original ↔ rewritten per block), CopyButton, Download DOCX / Download PDF
- **States:** idle / rewriting / streaming / done / error / empty

## 8. Constraints
- FastAPI + Next.js (existing repo stack); `uv`/`pnpm` only
- LangGraph for agent modes; SSE for all streaming
- Zen API default (`deepseek-v4-flash-free`); embeddings via Gemini default
- Plagiarism: DuckDuckGo HTML only, no API keys, best-effort
- No database, no auth, no external storage; single user
- Tests: unit + system + functional + security (pytest; frontend gates via tsc/biome)

## 9. Out of Scope (V1)
- Accounts, multi-user, teams
- Paid detectors (Turnitin/ZeroGPT/API keys), paid search APIs
- OCR for scanned PDFs, image input
- Conversation history persistence (chat is stateless per session)
- Batch processing / CLI

## 10. Future Improvements (V2)
- Cross-reference against user's own corpus as "self-plagiarism"
- Per-paragraph accept/reject in the remover with diff view
- Browser-side copy with formatting (rich text)
- Manual threshold tuning UI
- Citation-aware paraphrase (keep academic citations intact)

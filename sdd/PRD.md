# Product Requirements Document: AIverse

## Executive Summary

AIverse is a self-hosted AI-content detection and humanization toolkit. It gives an individual user three workflows in one local app: **find** AI-written content in their documents (per-paragraph percentages with reasons and change suggestions), **check** originality against the web (best-effort, free DuckDuckGo search), and **rewrite** at 7 humanize levels (1 = maximum humanizing, 7 = maximum corporate) with structure-preserving DOCX/PDF export. It runs on the OpenCode Zen API free tier (`deepseek-v4-flash-free`) by default — a fresh instance works with zero paid keys — and the user's files never leave their machine except for provider LLM calls and web-search fragment queries.

## Problem Statement

Students, researchers, and writers face a fragmented, paywalled market: detectors (Turnitin, GPTZero, ZeroGPT) are expensive, opaque, and often give a single number without telling you *where* or *how* to fix text; plagiarism checkers require accounts and upload-to-vendor; "humanizers" are generic rewrites with no tone control and no document output. AIverse consolidates detect → compare → rewrite into one self-hosted toolkit with per-paragraph location, reasons, suggestions, a 1–7 tone dial, and DOCX/PDF export.

## Goals & Success Metrics

| Goal | Metric | Target |
|------|--------|--------|
| Core usability | Upload → detection results | < 5 s for a 10-paragraph doc (heuristics instant; LLM per paragraph) |
| Out-of-box AI | First detection works with default zen provider after key fill | Yes (documented) |
| Detection quality | Known AI-style paragraph scores ≥ 70; human-style ≤ 40 | ≥ 90% of fixtures |
| Plagiarism honesty | Every report labeled best-effort; DDG outage degrades gracefully | Always |
| Rewrite fidelity | Facts/numbers preserved; heading/list structure identical | 100% in tests |
| Export validity | DOCX + PDF openable, structure preserved | 100% |
| Self-hosting | `docker compose up` from a fresh machine | Works in ≤ 15 minutes |

## User Personas

### Persona 1: Student (Primary)
- **Who they are:** Writing essays; worried about accidental AI flags
- **What they need:** Know where AI-sounding text is, what to change, and a rewrite that stays theirs
- **What frustrates them:** Detectors give a number, not a fix
- **Technical level:** Non-developer; comfortable uploading files

### Persona 2: Researcher
- **Who they are:** Produces long papers with citations and headings
- **What they need:** Per-section AI scan, plagiarism sanity check, structure-preserving tone adjustment
- **What frustrates them:** Rewriters destroy formatting and citations
- **Technical level:** Comfortable with terminals

### Persona 3: Freelance Writer
- **Who they are:** Ghostwrites to a client's tone; needs corporate vs casual output
- **What they need:** The 1–7 dial; DOCX delivery
- **What frustrates them:** Tools with no tone control
- **Technical level:** Non-developer

## User Stories

- As a student, I want per-paragraph AI scores so that I know exactly where to edit
- As a student, I want reasons behind each score so that I know *why* text sounds AI-written
- As a researcher, I want my document's headings and lists preserved when rewritten so that I don't rebuild formatting
- As a writer, I want a 1–7 tone dial so that output matches casual or corporate needs
- As a user, I want DOCX and PDF downloads so that I can submit directly
- As a user, I want an originality check against the web so that I catch copied phrases (knowing it's best-effort)
- As a user, I want a chatbot that locates the most AI-heavy sections of my paper so that I prioritize edits
- As a user, I want no account and no data on someone else's server so that my work stays private

## Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-01 | System shall accept txt/md/json/pdf/docx (≤ 20 MB) or pasted text and parse into structured blocks | Must Have |
| FR-02 | System shall compute per-paragraph AI% (LLM + heuristics) and a doc-level score, streamed over SSE | Must Have |
| FR-03 | System shall run a best-effort web originality check (DuckDuckGo, no key) with per-fragment matches and URLs | Must Have |
| FR-04 | System shall rewrite blocks at levels 1–7 preserving meaning and structure | Must Have |
| FR-05 | System shall export rewritten blocks to DOCX and PDF | Must Have |
| FR-06 | System shall provide a copy button for rewritten text | Must Have |
| FR-07 | System shall provide a RAG chatbot that locates AI-heavy sections and suggests changes with citations | Must Have |
| FR-08 | System shall store files and vectors locally (no database, no accounts) | Must Have |
| FR-09 | System shall degrade gracefully on provider/search failures without crashing streams | Must Have |
| FR-10 | System shall pass unit, system, functional, and security tests | Must Have |

## Non-Functional Requirements

| Category | Requirement |
|----------|-------------|
| Performance | First token TTFT < 5 s (zen); detection heuristics < 100 ms per paragraph; plagiarism bounded (≤ 40 fragments, 1.5 s spacing) |
| Security | No secrets in code or responses; magic-byte upload validation; no path traversal; fixed-host outbound; CORS restricted; no raw user-controlled URLs |
| Reliability | Per-paragraph fallbacks; atomic manifest writes; streams never die on one bad block; deletion cleans files + vectors |
| Maintainability | Env validated via pydantic-settings; routers thin, services own logic; LangGraph isolated in `agents/`; ruff/mypy/tsc/biome clean |
| Accessibility | Streaming regions `aria-live="polite"`; keyboard-navigable; labeled controls |

## Out of Scope
- Accounts, teams, shared workspaces
- Paid detectors / paid search APIs / OCR for scanned PDFs
- Chat history persistence (stateless sessions)
- Batch CLI processing

## Dependencies & Risks

| Item | Type | Impact | Mitigation |
|------|------|--------|------------|
| Zen API key availability | Dependency | High | OpenAI/Anthropic/Gemini/Ollama providers supported; clear provider-status messaging |
| DuckDuckGo rate limits/HTML changes | Risk | Medium | Label best-effort; caps + spacing; graceful `PLAGIARISM_UNAVAILABLE` |
| LLM scores are estimates, not truth | Risk | Medium | Blended with statistical heuristics; reasons shown; UI language honest |
| pypdf quality on complex PDFs | Risk | Medium | Failed extraction → 422 with message; headings heuristic conservative |
| LangGraph/LangChain version churn (>=1.2) | Risk | Medium | Pin majors (`langgraph>=1.2,<2`) |

## Timeline & Milestones

| Milestone | Deliverable | Target |
|-----------|-------------|--------|
| M1 | Spec + scaffold + file intake/parsing | Day 1 |
| M2 | Detection + plagiarism | Day 2 |
| M3 | Humanizer + export | Day 3 |
| M4 | RAG chatbot | Day 4 |
| M5 | Frontend (3 tools) | Day 5–6 |
| M6 | Docker + tests + screenshots | Day 7 |

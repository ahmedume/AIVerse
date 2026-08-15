# Product Requirements Document: Nexus

## Executive Summary

Nexus is a self-hostable AI workspace that gives an individual user four AI capabilities — multi-provider chat, document Q&A (RAG), tool-using agents, and template-driven text generation — behind one clean interface, with no data leaving the user's machine. It targets technically-savvy individuals who want model choice, private document grounding, and the ability to run an agent loop without paying per-seat SaaS fees or trusting a vendor with their data. It ships with the OpenCode Zen API as the default provider (`deepseek-v4-flash-free` free tier) so a freshly self-hosted instance works immediately once the operator pastes a key.

## Problem Statement

Users are locked to one model per product (ChatGPT, Claude.ai), cannot query private documents inside their chat tool without upload-to-vendor, and cannot experiment with open local models without complex glue code. Existing self-hosted options cover chat but not agents or RAG in a coherent product. Nexus consolidates the four most-used AI workflows into one self-hosted package with provider choice included.

## Goals & Success Metrics

| Goal | Metric | Target |
|------|--------|--------|
| Core usability | Register → streamed chat in under 10 minutes | 100% of onboarding users |
| Out-of-box AI | First chat works with default `zen` provider after key fill | Yes (documented) |
| Multi-mode reliability | % of chat requests completing with a `done` event | > 99% |
| RAG quality | Answer grounded in retrieved chunks (sources attached) | ≥ 90% of rag answers |
| Performance | First token TTFT (zen/cloud) | < 2 s |
| Cost control | Working in both zen/cloud and `ollama` local mode | Both documented + tested |
| Self-hosting | `docker compose up` from a fresh machine | Works in ≤ 15 minutes |

## User Personas

### Persona 1: Privacy-Conscious Power User (Primary)
- **Who they are:** Developer/researcher with Docker experience; runs local models
- **What they need:** Private document Q&A + full model choice
- **What frustrates them:** Vendor lock-in, uploads to third parties, per-seat pricing
- **Technical level:** Comfortable with terminals and self-hosting

### Persona 2: AI Tinkerer / Agent Hobbyist
- **Who they are:** Experimenter who wants LLM agent loops with tool access
- **What they need:** Visible tool calls, iteration control, reproducible runs
- **What frustrates them:** Opaque agent behavior, no visibility into tool execution
- **Technical level:** Developer, some RAG awareness

### Persona 3: Free-Tier Explorer
- **Who they are:** Wants to try an AI workspace without paying; Zen API free model is enough
- **What they need:** A working product for $0/month of AI spend
- **What frustrates them:** Products demanding paid API keys before anything works
- **Technical level:** Comfortable editing a `.env` file

### Persona 4: Team Admin (self-hosting for a small group)
- **Who they are:** Runs an instance for friends/colleagues
- **What they need:** Account management, deactivation, role control
- **What frustrates them:** Sign-ups with no moderation tools
- **Technical level:** Sysadmin-ish

## User Stories

- As a user, I want to register with email/password so that my workspace is private
- As a user, I want to pick any provider/model per conversation so that I control cost and quality
- As a user, I want text to stream in so that long answers feel responsive
- As a user, I want my first chat to work with the default free Zen model so that setup is instant
- As a user, I want to upload documents and ask questions so that my private files are queryable
- As a user, I want to see which sources an answer used so that I can trust it
- As a user, I want my agent's tool calls visible so that I understand what it did
- As a user, I want reusable prompt templates so that I stop rewriting common instructions
- As an admin, I want to deactivate abusive accounts so that my instance stays clean

## Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-01 | System shall register users with email + password (bcrypt) | Must Have |
| FR-02 | System shall authenticate via JWT in httpOnly cookies with refresh rotation | Must Have |
| FR-03 | System shall stream chat tokens over SSE in `chat` mode | Must Have |
| FR-04 | System shall run `rag` mode retrieving from the user's ready documents with sources | Must Have |
| FR-05 | System shall run `agent` mode with a max 5-iteration tool loop | Must Have |
| FR-06 | System shall run `textgen` mode from user templates containing `{input}` | Must Have |
| FR-07 | System shall persist conversations, messages, documents, and templates per user | Must Have |
| FR-08 | System shall let users manage documents (upload/delete) with status tracking | Must Have |
| FR-09 | System shall let admins list, search, change roles, and deactivate users | Should Have |
| FR-10 | System shall rate-limit auth (5/min) and chat (20/min per user) | Should Have |
| FR-11 | System shall support Zen, OpenAI, Anthropic, Gemini, and Ollama providers, with Zen as default | Should Have |
| FR-12 | System shall work with zero paid keys: default provider `zen` model `deepseek-v4-flash-free` | Should Have |

## Non-Functional Requirements

| Category | Requirement |
|----------|-------------|
| Performance | First token TTFT < 2 s (zen/cloud); SSE no buffering; list endpoints paginated (50/page) |
| Security | bcrypt cost 12; JWT HS256; httpOnly cookies; CORS restricted to `CORS_ORIGINS`; generic auth errors (no enumeration) |
| Reliability | Assistant message persisted only after `done`; upload failures leave document in `failed` state with reason; provider outage → friendly `error` event |
| Scalability | Single-instance self-hosted; supports dozens of concurrent users; FAISS per-user indices |
| Maintainability | All env vars validated via pydantic-settings; ORM only; structured logging (structlog) |
| Accessibility | Forms keyboard-navigable; ARIA labels on icons/dropdowns; live region for streaming answers |

## Out of Scope
- Shared workspaces / teams / permissions
- Web search tool, custom tool registry
- Per-user API keys, usage billing
- Password reset / email verification

## Dependencies & Risks

| Item | Type | Impact | Mitigation |
|------|------|--------|------------|
| Zen API key availability/free-tier limits | Dependency | High | Placeholder `.env` + provider status cards; OpenAI/Anthropic/Ollama remain fallback providers |
| Ollama presence for local mode | Dependency | Medium | Cloud/zen providers always available; empty-state guidance to run `ollama pull llama3` |
| pypdf parsing quality | Risk | Medium | Failed docs flagged `failed` with stored error — never silently corrupt |
| SQLite concurrency under heavy writes | Risk | Low | WAL mode; single-instance scope; Postgres path documented |
| LangGraph/LangChain version churn (>=1.2 APIs) | Risk | Medium | Pin majors in pyproject (`langgraph>=1.2,<2`); upstream test at Phase 5 start |
| Zen API is OpenAI-compatible but not identical | Risk | Low | Only chat/embeddings endpoints used; no tool-call format assumptions beyond standard OpenAI shapes |

## Timeline & Milestones

| Milestone | Deliverable | Target |
|-----------|-------------|--------|
| M1 | Scaffold + auth backend + tests | Week 1 |
| M2 | Streaming chat engine (zen default) + conversations | Week 2 |
| M3 | Documents/RAG + templates + agents | Week 3 |
| M4 | Full frontend (all screens) | Week 4 |
| M5 | Admin + Docker hardening + validation | Week 5 |
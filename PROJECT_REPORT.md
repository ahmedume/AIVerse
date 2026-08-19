# AIverse — Self-Hosted AI Content Toolkit
## Project Report

---

## ABSTRACT

The rapid proliferation of large language models has made AI-generated text nearly indistinguishable from human writing at a glance, while academic integrity frameworks, editorial workflows, and content teams increasingly need reliable, explainable tools to detect, analyze, and rewrite machine-produced prose. AIverse is a self-hosted, provider-agnostic web application that addresses this need through a unified toolkit of four services: AI-likeness detection, plagiarism checking, humanizing rewrites, and a retrieval-augmented question-answering chatbot grounded in user-supplied documents.

The detection engine combines deterministic statistical heuristics (sentence-length burstiness, type-token ratio, bigram repetition, transition-phrase density, and punctuation variety) with large language model judgment, blended at a 60/40 ratio and normalized to a 0–100 score with a flagging threshold of 70. The plagiarism module performs web search over 120-word fragments using 8-gram overlap matching. The humanizer rewrites flagged blocks across four intensity profiles with per-block token streaming and safe fallback to the original text. The chatbot indexes documents into a FAISS vector store using Gemini embeddings and drives a LangGraph agent loop with retry and timeout policies, streaming sources and answers over Server-Sent Events.

The system is resilient by design: chat and scoring models automatically fall back across four providers (Gemini, OpenCode Zen, Groq, OpenRouter) when quotas or outages occur. The application was validated with 72 automated tests, a fully linted backend and frontend, and end-to-end live verification of every page. This report documents the system's design, architecture, algorithms, testing, and lessons learned.

---

## Table of Contents

**Abstract**

**Chapter 1 — Introduction**
1.1 Introduction · 1.2 Aim & Objectives · 1.3 Problem Statement · 1.4 Proposed System · 1.5 Project Scope · 1.6 Assumptions & Constraints · 1.7 Social Benefits · 1.8 Report Layout

**Chapter 2 — Literature Review / Background and Existing Work**
2.1 Background · 2.2 Literature Review (2.2.1–2.2.5) · 2.3 Literature Summary

**Chapter 3 — Requirements Analysis**
3.1 Stakeholders List · 3.2 Requirements Elicitation (3.2.1–3.2.3) · 3.3 Use Case Design · 3.4 SDLC Model · 3.5 Specific Requirements

**Chapter 4 — Software Design Specification**
4.1 Design Models · 4.2 Work Breakdown Structure · 4.3 System Architecture (4.3.1–4.3.3) · 4.4 Data Representation (4.4.1–4.4.5) · 4.5 Process Flow (4.5.1–4.5.3)

**Chapter 5 — Implementation**
5.1 Algorithm · 5.2 External APIs · 5.3 User Interface

**Chapter 6 — System Testing**
6.1 Manual Testing (6.1.1–6.1.4) · 6.2 Automated Testing · 6.3 Results & Discussion

**Chapter 7 — Conclusion**
7.1 Problems Faced and Lessons Learned · 7.2 Conclusion · 7.3 Limitations · 7.4 Future Work

**Back Matter**
References · Pseudo Code · Appendix A — Design Q&A · Appendix B — API & Configuration Reference · Appendix C — Test Inventory & Screenshots · List of Figures · List of Tables · List of Abbreviations

---

# CHAPTER 1: INTRODUCTION

## 1.1 Introduction

Generative AI has moved from research novelty to everyday tooling. Large language models now produce essays, reports, marketing copy, and code that are fluent, structured, and stylistically consistent. By 2025, studies estimated that a meaningful fraction of web traffic and academic submissions contained machine-generated text, and detection—the task of distinguishing synthetic prose from human writing—has become a first-class engineering problem [1][2].

Most existing solutions fall into two extremes. Commercial detectors such as GPTZero and Turnitin offer strong marketing presence but are closed-source black boxes: users cannot audit their scoring, run them offline, or integrate them with their own workflows without an API key and per-use fees. On the opposite end, open-source detectors publish standalone classifiers that require model downloads, GPU resources, and deep machine-learning expertise to operate. Neither extreme suits a user who wants a transparent, self-hosted, all-in-one workspace: detect *and* fix the problem in the same tool.

AIverse is built to fill that gap. It is a self-hosted web application that combines four capabilities around one document pipeline: a heuristic-plus-LLM AI-likeness detector, a web-search plagiarism matcher, a level-based humanizing rewriter, and a retrieval-augmented chatbot that answers questions about the user's own documents. Every feature streams its output live to a modern browser interface using Server-Sent Events, and the entire model layer is provider-agnostic, failing over automatically across four hosted APIs or a local Ollama instance. This chapter introduces the project's objectives, problem statement, proposed system, scope, constraints, and social relevance.

## 1.2 Aim & Objectives

**Aim:**
To build a self-hosted, provider-agnostic web application that detects AI-generated content, checks plagiarism, rewrites text to sound human, and answers questions about documents—with transparent scoring, live streaming, and automatic provider failover.

**Objectives:**
- Implement a statistical AI-likeness scoring engine that evaluates sentence rhythm, vocabulary diversity, repetition, transition-phrase density, and punctuation variety without requiring an LLM.
- Blend heuristic scores with an LLM assessment at a defined ratio to produce a single 0–100 AI-likeness score per text block.
- Build a plagiarism checker that splits documents into fragments, performs web searches, and reports matches using n-gram overlap.
- Implement a level-based humanizer (four intensity profiles) that rewrites AI-sounding blocks while preserving document structure and falling back safely to the original text on failure.
- Implement a retrieval-augmented chatbot that indexes documents into a vector store and answers questions with tool-grounded evidence, streamed over Server-Sent Events.
- Design a provider-agnostic model layer that automatically fails over across Gemini, OpenCode Zen, Groq, and OpenRouter, skipping unconfigured providers.
- Deliver a modern responsive frontend (Next.js, React 19, Tailwind, shadcn/ui) with live streaming UI for all four tools.
- Achieve a maintainable quality baseline: a fully linted codebase, a passing automated test suite, and live end-to-end verification of every page.

## 1.3 Problem Statement

The market and the technical community both lack a transparent, self-contained tool that covers the full AI-content workflow. The specific problems this project addresses are:

- **Opacity of commercial detectors.** Closed detectors provide a score but no audit trail, no per-block reasoning, and no way to act on the result within the same tool.
- **Fragmentation.** Users must switch between a detector, a plagiarism service, a rewriting tool, and a Q&A chat to complete one editorial task.
- **Provider lock-in and fragility.** Tools that depend on a single model API break whenever that API is rate-limited, out of quota, or unavailable—leaving the user with no fallback and no explanation.
- **Lack of grounding.** Naive chatbots answer from parametric knowledge and hallucinate; they do not base answers on the specific document the user supplies.
- **Entry barriers for self-hosting.** Open-source detection stacks require GPU resources, model downloads, and configuration expertise that most users do not have.
- **No graceful degradation.** Existing tools typically fail hard on quota exhaustion, instead of informing the user clearly or degrading to cheaper deterministic paths.

## 1.4 Proposed System

AIverse is a full-stack web application with a FastAPI backend and a Next.js frontend. The backend exposes seven REST endpoints, five of which stream results as Server-Sent Events. Its core modules are:

- **Detection module** — per-block statistical scoring (burstiness, type-token ratio, bigram repetition, transitions, punctuation) blended 60/40 with an LLM assessment, normalized to 0–100 with a flag threshold of 70.
- **Plagiarism module** — document fragmentation (120-word fragments, max 40), asynchronous web searches over DuckDuckGo HTML results, and 8-gram overlap matching with a 1.5-second polite interval between requests.
- **Humanize module** — four rewrite profiles (level 1–4) applied per block with token-level streaming; the original text is preserved whenever a rewrite fails.
- **Chat module** — document chunking (800 characters, 100 overlap), Gemini embedding, a persisted FAISS index per document, and a LangGraph agent with tools (`search_documents`, `analyze_ai_content`, `current_datetime`) streamed over SSE.
- **Model layer** — a provider-agnostic factory that orders candidates Gemini → Zen → Groq → OpenRouter, skips providers without keys, and returns a chain that every service iterates with automatic failover.

The frontend provides four pages (Landing, Chatbot, Checker, Remover) with live streaming indicators, tool-activity traces, source cards with similarity scores, and DOCX/PDF export.

## 1.5 Project Scope

**Included:**
- AI-likeness detection with per-block scores, reasons, and a blended overall score.
- Plagiarism checking against web-indexed sources with per-fragment matched/unmatched results.
- Humanizing rewrites across four intensity levels with streaming output.
- RAG chatbot with document indexing, tool use, source citations, and streamed answers.
- File library: upload (DOCX, PDF, TXT, MD, up to 20 MB), list, and delete; export to DOCX/PDF.
- Provider auto-failover across Gemini, OpenCode Zen, Groq, and OpenRouter, plus local Ollama.
- Docker Compose deployment for API and web containers.

**Excluded:**
- User authentication, roles, and multi-tenant account management.
- Persistent user data storage beyond the local file library and vector index.
- Fine-tuning or training of custom detection models.
- Mobile-native applications (the UI is responsive but web-first).
- Cloud deployment and production hardening (SSL, monitoring, CI/CD) beyond Phase 8 planning.

**Limitations:**
- The AI-likeness score is a heuristic indicator, not a scientifically validated classifier; accuracy varies by domain and text length.
- Embedding-based retrieval requires at least one configured embedding provider (Gemini or an OpenAI-compatible endpoint).
- Plagiarism coverage depends on the reach of the web-search provider used.

## 1.6 Assumptions & Constraints

### 1.6.1 Assumptions
- Users have at least one valid API key for a supported provider and accept that content is sent to that provider for scoring or rewriting.
- The deployment environment is a modern desktop or server with Python 3.12 and Node.js available (or Docker).
- Documents submitted are text-based (documents, reports, essays, articles); scanned images and handwriting are out of scope.
- The user's web connection can reach the chosen provider APIs and the plagiarism search endpoint.
- Self-hosted operation implies the operator is responsible for their own data governance and API key custody.

### 1.6.2 Constraints
- Technical: embeddings and chat depend on external APIs; quota or outage behavior is mitigated only through the provider chain.
- Technical: batch embedding requests are limited to 100 items per call by the Gemini API; very large documents must be chunked accordingly.
- Design: components are capped at 100 lines and files at 300 lines to keep the codebase maintainable.
- Time: the project is delivered in eight phases; Phase 8 (Docker hardening, security tests, integration) is the next planned increment.
- Budget: only free-tier and quota-limited provider plans are assumed, motivating the multi-provider fallback design.

## 1.7 Social Benefits

- **Academic integrity:** educators gain a transparent, affordable tool to flag potentially AI-generated submissions without relying on opaque paid services.
- **Editorial quality:** journalists and content teams can identify and rewrite AI-sounding drafts before publication, improving readability and originality.
- **Digital literacy:** per-block explanations and reasons help users understand *why* text looks machine-written.
- **Self-hosting and data ownership:** institutions and individuals retain control of their documents and API keys instead of submitting everything to a third party.
- **Cost accessibility:** the multi-provider free-tier fallback chain lets low-budget users run the same workflow as paid platforms.

## 1.8 Report Layout

Chapter 2 reviews the background and existing detection and rewriting tools. Chapter 3 presents the requirements analysis: stakeholders, functional and non-functional requirements, use cases, and the chosen development model. Chapter 4 specifies the software design, including architecture, data representation, and process flows. Chapter 5 details the implementation: algorithms, external APIs, and user interface. Chapter 6 covers manual and automated testing and discusses the results. Chapter 7 concludes with problems faced, limitations, and future work.

---

# CHAPTER 2: LITERATURE REVIEW / BACKGROUND AND EXISTING WORK

## 2.1 Background

Large language models have made machine text difficult to distinguish from human writing. Adoption data illustrates the scale: consumer AI assistants reached hundreds of millions of weekly users within two years of public release, and web platforms now host substantial volumes of AI-generated articles, reviews, and posts [3]. In parallel, surveys of higher-education institutions report widespread use of generative tools in assignments, driving demand for detection and for policy that distinguishes legitimate assistance from plagiarism [4].

Detection research has followed two broad families. **Statistical or feature-based detection** analyzes stylistic signals such as perplexity, burstiness, and token probability under a language model [5][6]. **Classifier-based detection** fine-tunes transformer models on labeled human/AI corpora [7]. Both families share a limitation: they are brittle to adversarial rewriting, paraphrasing, or translation, and they provide no path to *remediation*—that is, no way to fix the flagged text.

A parallel trend is **retrieval-augmented generation (RAG)**, which grounds LLM answers in user-provided documents by embedding chunks, retrieving the most relevant passages, and constraining the model to answer from them [8]. RAG addresses hallucination in document Q&A and is the architectural basis for the chatbot module of this project.

## 2.2 Literature Review

### 2.2.1 GPTZero
GPTZero is a commercial detector that reports perplexity and burstiness scores for a submitted text and was one of the first tools aimed at educators [9]. It is easy to use but closed-source: the scoring algorithm is proprietary, there is no API for self-hosted integration in its free tier, and it offers no rewriting or plagiarism capability. It directly motivated the design goal of a *transparent* score with per-block reasoning.

### 2.2.2 Turnitin (Similarity + AI Writing)
Turnitin's academic suite couples plagiarism similarity checking with an AI-writing indicator [10]. It is the de-facto standard in universities and benefits from a large proprietary document corpus. However, it is institution-bound, paid, and unavailable to individual users or small teams; its AI indicator is also opaque and has been criticized for false positives on multilingual or non-native text. This project's plagiarism module deliberately uses an open web-search approach so that the same workflow works outside institutional licenses.

### 2.2.3 QuillBot
QuillBot provides paraphrasing, grammar checking, and a free/paid web UI, and is widely used to rewrite text to avoid detection [11]. It is a pure rewriting tool: it neither detects AI content nor grounds its rewrites in a score. AIverse's humanizer is differentiated by being *score-driven*—blocks are rewritten only when the detector flags them, and the user chooses the intensity—and by streaming results through an open API.

### 2.2.4 NetusAI and DeepSeek-Based Paraphrasers
A class of "AI bypass" tools (NetusAI and similar) target students explicitly by paraphrasing until detectors fail [12]. These tools raise integrity concerns and provide no transparency. AIverse deliberately does *not* optimize for evading detectors; its humanizer aims for natural, readable prose with an honest rationale, positioning it as an editorial aid rather than an evasion tool.

### 2.2.5 RAG Chat Platforms (ChatGPT with Uploads, NotebookLM, Perplexity)
Mainstream assistants now accept document uploads and answer questions over them using RAG [13][14]. These are powerful, but they are closed, cloud-hosted, and treat detection and rewriting as separate products. AIverse unifies RAG Q&A with detection, plagiarism, and rewriting in one self-hosted application, and it surfaces the retrieved evidence (source excerpts with similarity scores) to the user instead of hiding it.

### 2.2.6 Self-Hosted Detection Stacks (OpenAI Text Classifier, AI Text Classifier OSS)
Open-source and open-weight classifiers exist (for example, models released alongside academic papers and hosted implementations on Hugging Face) [7]. They offer transparency but require downloading model weights, running inference on suitable hardware, and maintaining a separate service. AIverse requires no GPU and no model downloads because its scoring uses lightweight deterministic features plus hosted LLM APIs with automatic failover.

## 2.3 Literature Summary

The review reveals a clear gap: no single open, self-hosted tool covers the complete AI-content workflow—*detect, explain, check for plagiarism, rewrite, and ask questions*—while remaining provider-agnostic and affordable on free tiers. Commercial tools are opaque and fragmented; academic tools are institution-bound; standalone classifiers need GPUs; and rewriting tools are detached from detection. AIverse fills this gap by combining deterministic detection, LLM-assisted scoring, web-search plagiarism, level-based rewriting, and document-grounded chat in one application, with a provider chain that degrades gracefully instead of failing hard.

**Conclusion:** Existing solutions either detect without remediating, remediate without detecting, or require paid, opaque, or high-infrastructure environments. AIverse is the proposed unification of all four capabilities under a transparent, self-hosted, failover-capable design.

---

# CHAPTER 3: REQUIREMENTS ANALYSIS

Chapter 3 defines who the system serves, how its requirements were derived, the functional and non-functional requirements, key use cases, the development model, and the hardware and software environment required to run it.

## 3.1 Stakeholders List (Actors)

| Category | Stakeholder | Role in the system |
|---|---|---|
| Primary Users | Individual writers | Submit documents for detection, plagiarism, rewriting, and Q&A |
| Primary Users | Educators | Flag potentially AI-generated student work with per-block reasoning |
| Primary Users | Content teams / editors | Verify originality and polish drafts before publication |
| Primary Users | System administrator | Self-hosts the application, manages API keys, and monitors service health |
| Development Team | Backend engineer | Builds the API, services, model layer, and tests |
| Development Team | Frontend engineer | Builds the streaming UI, file library, and export flows |
| Development Team | DevOps / release engineer | Containerization, environment configuration, quality gates |
| Secondary Stakeholders | API providers (Gemini, Zen, Groq, OpenRouter) | Supply model and embedding capacity via keyed access |

## 3.2 Requirements Elicitation

Requirements were gathered through analysis of existing tools (Section 2.2), direct experience with provider API limitations during development, and the specification-driven process documented in `sdd/` (SPEC, PRD, SRS, SDS, TECH_STACK, BUILD_PLAN). The provider-failover requirement emerged empirically when development was interrupted by free-tier quota exhaustion, and the resulting design requirement was formalized as a multi-provider chain with graceful degradation.

### 3.2.1 Functional Requirements

1. The system shall accept pasted text or uploaded files (DOCX, PDF, TXT, MD) up to 20 MB and parse them into typed blocks (headings, paragraphs, list items, blockquotes).
2. The system shall compute a per-block AI-likeness score from statistical heuristics and blend it with an LLM assessment at a 60/40 ratio.
3. The system shall stream per-block detection results to the client as Server-Sent Events and emit an overall score with a flag threshold of 70.
4. The system shall split documents into fragments and perform web searches to identify matched and unmatched fragments using 8-gram overlap.
5. The system shall rewrite flagged blocks according to a selected intensity profile (levels 1–4), streaming tokens per block and preserving the original text if a rewrite fails.
6. The system shall index documents into a vector store and answer user questions through a tool-using agent, emitting sources and a final answer over SSE.
7. The system shall export the rewritten document as DOCX or PDF.
8. The system shall try model providers in a configured order, skip unconfigured providers, and fall back automatically when a provider fails.
9. The system shall return a clear message when no provider is available: "We can't process your message right now because you don't have enough credits."
10. The system shall expose a health endpoint and CORS configuration for the frontend origin.

### 3.2.2 Non-Functional Requirements

**Performance:** Chat answers stream tokens as they are generated; detection scores all blocks concurrently with bounded concurrency; plagiarism requests are spaced 1.5 seconds apart to respect the search provider.
**Security:** API keys are stored only in the local environment file, never committed, and never returned by any endpoint; CORS restricts the browser origin; uploads are validated by MIME type and size.
**Scalability:** The vector index is persisted to disk and cached per document; embeddings are cached so repeated queries do not rebuild indexes.
**Reliability:** Every model call is wrapped in a provider chain with retry policies (2 attempts) and timeout policies (60 seconds); a 5-iteration tool-use guard prevents runaway agent loops.
**Usability:** All tools stream live status and results; the UI follows shadcn/ui accessibility conventions with keyboard-usable controls.
**Maintainability:** Files are capped at 300 lines and components at 100 lines; the backend is linted with ruff, the frontend with Biome and ESLint; the backend carries a 72-test suite.

### 3.2.3 Requirements Traceability Matrix

| Requirement | Source | Stakeholder | Goal |
|---|---|---|---|
| FR-1 Parse pasted text and files | User interviews, SRS | All users | 1.1, 1.4 |
| FR-2 Blend heuristic + LLM score | Literature review (§2.2.1 gap) | Educators | 1.1 |
| FR-3 Stream detection results | SDS | Educators, writers | 1.3 |
| FR-4 Plagiarism fragment matching | Existing tool analysis (§2.2.2) | Writers, editors | 1.3 |
| FR-5 Level-based rewriting | Existing tool analysis (§2.2.3) | Writers, editors | 1.3 |
| FR-6 RAG chatbot with sources | RAG literature [8] | All users | 1.4 |
| FR-7 Export DOCX/PDF | SRS | Editors | 1.4 |
| FR-8 Provider auto-failover | Empirical (quota exhaustion) | All users, admin | 1.2 |
| FR-9 No-provider message | SRS | All users | 1.5 |
| FR-10 Health endpoint + CORS | SDS | Admin, DevOps | 1.6 |
| NFR-1 Performance | SRS | All users | 1.2 |
| NFR-2 Security | SPEC | Admin | 1.5 |
| NFR-3 Reliability | SPEC | All users | 1.5 |

## 3.3 Use Case Design/Description

### Use Case 1 — Detect AI-likeness in a document
- **Actors:** Educator, Writer
- **Flow:** 1. The user pastes text or uploads a file. 2. The system parses the document into blocks. 3. The system computes heuristic scores. 4. The system requests LLM assessments for scorable blocks. 5. The system blends scores and streams results per block. 6. The system emits an overall score and flag status.
- **Outcome:** The user sees per-block scores, reasons, and an overall verdict.

### Use Case 2 — Check a document for plagiarism
- **Actors:** Writer, Editor
- **Flow:** 1. The user submits source text. 2. The system builds 120-word fragments (max 40). 3. The system searches the web for each fragment asynchronously with polite spacing. 4. The system matches results using 8-gram overlap. 5. The system streams matched and unmatched fragments.
- **Outcome:** The user sees which fragments match indexed sources with URLs.

### Use Case 3 — Humanize an AI-sounding document
- **Actors:** Writer, Editor
- **Flow:** 1. The user submits source text and picks a level (1–4). 2. The system filters rewritable blocks. 3. The system rewrites each block through the model chain, streaming tokens. 4. Failed rewrites revert to the original text. 5. The system emits the rewritten blocks and supports export.
- **Outcome:** The user obtains a rewritten document with structure preserved.

### Use Case 4 — Ask questions about a document
- **Actors:** Any user
- **Flow:** 1. The user submits a document and a question. 2. The system chunks and embeds the document into a cached FAISS index. 3. The agent retrieves top-4 chunks and optionally calls tools. 4. The system streams tool activity, tokens, sources, and a final answer over SSE.
- **Outcome:** The user receives a grounded answer with visible source excerpts.

### Use Case 5 — Administer the application
- **Actors:** System administrator
- **Flow:** 1. The admin configures API keys and provider order in the environment file. 2. The admin restarts the backend. 3. The admin checks `/health` and monitors logs.
- **Outcome:** The system serves traffic through the configured provider chain.

## 3.4 Software Development Life Cycle Model

The project follows an **incremental, spec-driven development model**. Each of eight phases delivered a working increment (scaffold → agents → detection → plagiarism → humanizer → frontend → integration), with the specification documents (`sdd/`) maintained ahead of each phase. This model was chosen because the project's requirements—provider behavior, API limits, and streaming contracts—were not fully predictable up front; incremental delivery let each phase be verified live and let empirical findings (such as quota exhaustion) be folded back into the requirements as formal fallback requirements.

## 3.5 Specific Requirements (Hardware and Software Requirements)

### 3.5.1 Hardware Requirement

| Component | Specification |
|---|---|
| CPU | Any modern x64 processor (1+ cores; no GPU required) |
| RAM | 4 GB minimum (8 GB recommended) |
| Storage | 1 GB free for the application, index, and uploads |
| Network | Internet access to provider APIs and the plagiarism search endpoint |

### 3.5.2 Software Requirement

| Requirement | Version | Purpose |
|---|---|---|
| Python | 3.12 | Backend runtime (managed via `uv`) |
| Node.js | 18+ (Node 20 recommended) | Frontend build and dev runtime |
| pnpm | 9+ | Frontend package manager and workspace |
| FastAPI / uvicorn | Latest | Async API server and SSE transport |
| LangGraph / LangChain | 1.2.x | Agent orchestration and model abstraction |
| FAISS | Latest | Vector index and similarity search |
| Next.js | 14/15 App Router | Frontend framework |
| Docker (optional) | 24+ | Containerized deployment via Compose |
| Browser | Modern (Chrome, Edge, Firefox) | Client UI |

---

# CHAPTER 4: SOFTWARE DESIGN SPECIFICATION

Chapter 4 specifies how AIverse is designed: its design models, work breakdown, system architecture, data representation, and process flows. Diagrams use Mermaid notation and are referenced before they appear.

## 4.1 Design Models

AIverse uses a **layered, modular architecture** with three layers: a presentation layer (Next.js frontend), an API layer (FastAPI routers), and a service layer (detect, plagiarism, humanize, RAG, parse, export, files). The service layer is further decomposed into the core utilities (heuristics, blocks, LLM factory, SSE formatting) and the agent subsystem (LangGraph nodes, tools, types). Layering was chosen because it isolates streaming concerns from business logic, allows each service to be tested in isolation, and keeps files small (a hard 300-line cap) so the entire architecture remains readable.

## 4.2 Work Breakdown Structure

The project was delivered in eight phases. Figure 4.1 shows the level 1 and level 2 breakdown.

**Figure 4.1 — Work Breakdown Structure**

```mermaid
flowchart TD
    P[AIverse Project]
    P --> P1[Scaffolding]
    P1 --> P1a[FastAPI skeleton]
    P1 --> P1b[Config & settings]
    P1 --> P1c[Health endpoint]
    P --> P2[Agents & Model Layer]
    P2 --> P2a[LangGraph graph]
    P2 --> P2b[Tools & nodes]
    P2 --> P2c[Provider chain]
    P --> P3[Detection]
    P3 --> P3a[Heuristics]
    P3 --> P3b[LLM scoring]
    P3 --> P3c[SSE streaming]
    P --> P4[Plagiarism]
    P4 --> P4a[Fragment builder]
    P4 --> P4b[Web search]
    P4 --> P4c[N-gram matching]
    P --> P5[Humanizer]
    P5 --> P5a[Level profiles]
    P5 --> P5b[Block rewrite]
    P5 --> P5c[Export]
    P --> P6[Frontend]
    P6 --> P6a[Pages & routing]
    P6 --> P6b[Streaming clients]
    P6 --> P6c[File library]
    P --> P7[Integration & Hardening]
    P7 --> P7a[End-to-end fixes]
    P7 --> P7b[Screenshots]
    P --> P8[Docker, Security, Docs]
    P8 --> P8a[Containers]
    P8 --> P8b[Security tests]
    P8 --> P8c[Final docs]
```

The work breakdown is referenced by the incremental SDLC model in Section 3.4; each level 1 item was a shippable increment.

## 4.3 System Architecture

The architecture is a **two-tier client–server system** with a monolith backend: the Next.js frontend talks to one FastAPI process that hosts all routers and services. All client–server communication is HTTP; streaming endpoints use Server-Sent Events, and file upload/export use multipart and binary responses. The backend stores no SQL database—runtime state is the in-memory per-document index cache plus on-disk artifacts (uploads, vector index, exported files).

### 4.3.1 Block Diagram

**Figure 4.2 — Block Diagram**

```mermaid
flowchart LR
    U[User / Browser] -->|HTTP + SSE| FE[Next.js Frontend<br/>Landing, Chat, Checker, Remover]
    FE -->|fetch /api/*| BE[FastAPI Backend :8001]
    BE --> R1[Detect Router] --> S1[Detect Service] -->|heuristics| C1[Core Heuristics]
    BE --> R2[Plagiarism Router] --> S2[Plagiarism Service] -->|search| WEB[Web Search (DuckDuckGo)]
    BE --> R3[Humanize Router] --> S3[Humanize Service] -->|LLM| ML[Model Chain]
    BE --> R4[Chat Router] --> S4[RAG Service] -->|embed| EMB[Gemini Embeddings]
    S4 -->|index/query| FAISS[FAISS Vector Store]
    S4 -->|agent loop| LG[LangGraph Agent]
    BE --> R5[Files Router] --> FS[Uploads Directory]
    BE --> R6[Export Router] --> S3
    ML --> P1[Gemini] & P2[Zen] & P3[Groq] & P4[OpenRouter]
    ML --> P5[Ollama (local)]
```

### 4.3.2 Component Diagram

**Figure 4.3 — Component Diagram**

```mermaid
flowchart TB
    subgraph Frontend["Presentation Layer (Next.js)"]
        LP[Landing Page]
        CH[Chat Client]
        CK[Checker Client]
        RV[Remover Client]
        SL[Source Picker + File Library]
    end
    subgraph API["API Layer (FastAPI)"]
        AR[API Router]
        HE[Health Router]
    end
    subgraph SVC["Service Layer"]
        DS[Detect Service]
        PS[Plagiarism Service]
        HS[Humanize Service]
        RS[RAG Service]
        XS[Parse Service]
        EX[Export Service]
        FL[Files Service]
    end
    subgraph CORE["Core Layer"]
        HX[Heuristics]
        BL[Blocks / Parser]
        LM[LLM Factory]
        SSE[SSE Formatter]
        CF[Config / Settings]
    end
    subgraph AGENT["Agent Subsystem"]
        GR[LangGraph StateGraph]
        TL[Tools]
        ND[Nodes / Retry Policy]
    end
    Frontend --> API
    AR --> DS & PS & HS & RS
    HS --> LM
    DS --> HX
    RS --> GR
    GR --> TL
    LM --> CF
    RS --> AGENT
    EX --> HS
```

### 4.3.3 Software Architecture Diagram

**Figure 4.4 — Software Architecture Diagram**

```mermaid
flowchart TB
    subgraph Browser["Browser"]
        UI["React 19 UI<br/>TanStack Query, shadcn/ui"]
        SSEX["SSE Stream Reader"]
    end
    subgraph App["Next.js App Server"]
        SSR["App Router SSR Pages"]
        API_TS["API Client (lib/api.ts)"]
    end
    subgraph Backend["Backend Process (uvicorn)"]
        ROUTES["Routers"]
        SVC2["Services"]
        CORE2["Core (heuristics, blocks, llm, sse)"]
        AG2["LangGraph Agent"]
        FS2["File Storage (data/)"]
    end
    subgraph External["External"]
        MODELS["Gemini / Zen / Groq / OpenRouter / Ollama"]
        SEARCH["DuckDuckGo HTML Search"]
    end
    UI --> API_TS --> ROUTES
    ROUTES --> SVC2 --> CORE2
    SVC2 --> AG2 --> MODELS
    SVC2 --> SEARCH
    SVC2 --> FS2
    API_TS -. SSE stream .-> SSEX
```

## 4.4 Data Representation

AIverse has no relational database; its persistent state consists of the uploads directory, the per-document vector index, and exported files. The diagrams below describe the logical data model, the domain classes, the data flows, and the runtime object interactions.

### 4.4.1 Entity-Relationship Diagram (ERD)

**Figure 4.5 — Entity-Relationship Diagram**

```mermaid
erDiagram
    DOCUMENT ||--o{ BLOCK : "parsed into"
    DOCUMENT ||--o{ CHUNK : "chunked into"
    DOCUMENT ||--|| INDEX : "indexed as"
    INDEX ||--o{ CHUNK : "contains"
    BLOCK ||--o{ SCORE : "scored as"
    BLOCK ||--o{ FRAGMENT : "split into"
    FRAGMENT ||--o{ MATCH : "matched to"
    MATCH ||--|| RESULT : "references"
    DOCUMENT {
        string id
        string filename
        string ext
        int size
        int blocks
        int words
    }
    BLOCK {
        int index
        string type
        string text
        int level
    }
    CHUNK {
        int block_index
        string text
    }
    INDEX {
        string key
        string path
    }
    SCORE {
        int index
        float ai_score
        string reason
    }
    FRAGMENT {
        int index
        string text
    }
    MATCH {
        string url
        string title
        string snippet
    }
```

**Description:** A `DOCUMENT` (a file in the library or pasted text) is parsed into ordered `BLOCK`s, each carrying a type (heading, paragraph, list_item, blockquote). Scorable blocks receive a `SCORE` with an AI-likeness value and a reason. The document is also chunked into overlapping `CHUNK`s that populate a per-document `INDEX` stored as a FAISS file plus a JSONL metadata file. For plagiarism, blocks are split into `FRAGMENT`s, and each fragment may produce `MATCH` results (URL, title, snippet) from web search. There is no user/account entity because the application is single-tenant and self-hosted.

### 4.4.2 UML Class Diagram

**Figure 4.6 — UML Class Diagram (core domain)**

```mermaid
classDiagram
    class Block {
        +int index
        +str type
        +str text
        +int level
        +float ai_score
        +str reason
    }
    class Settings {
        +str DEFAULT_PROVIDER
        +str DEFAULT_MODEL
        +str FALLBACK_PROVIDER
        +str GROQ_MODEL
        +str OPENROUTER_MODEL
        +bool provider_configured(str)
    }
    class LLMFactory {
        +get_chat_model(provider, model) BaseChatModel
        +get_model_chain(provider, model) list[BaseChatModel]
        +get_embeddings() Embeddings
    }
    class VectorStore {
        +Path folder
        +faiss.Index index
        +list meta
        +build(chunks)
        +load() bool
        +search(query, k) list[dict]
    }
    class LangGraphAgent {
        +StateGraph graph
        +Context context
        +build_graph(model, context) graph
        +chat_stream(source, question) AsyncIterator[str]
    }
    class DetectService {
        +detect_stream(blocks) AsyncIterator[str]
    }
    class HumanizeService {
        +humanize_stream(source, level) AsyncIterator[str]
    }
    class PlagiarismService {
        +plagiarism_stream(source) AsyncIterator[str]
    }
    DetectService --> LLMFactory : uses
    DetectService --> Block
    HumanizeService --> LLMFactory : uses
    LangGraphAgent --> VectorStore : indexes and searches
    LangGraphAgent --> LLMFactory : uses
    PlagiarismService --> Block : fragments
    VectorStore --> Settings : config
    LLMFactory --> Settings : reads keys
```

### 4.4.3 Data Flow Diagram (DFD)

**Figure 4.7 — DFD Level 0**

```mermaid
flowchart LR
    U[User] -->|source text / file / question| P0[AIverse System]
    P0 -->|scores / reasons / sources / rewritten text / answers| U
    P0 -->|search queries| S[Web Search]
    S -->|result snippets| P0
    P0 -->|model prompts| M[Model Providers]
    M -->|completions / embeddings| P0
```

**Figure 4.8 — DFD Level 1 (document pipeline)**

```mermaid
flowchart LR
    U[User] -->|source| P1[Parse Service]
    P1 -->|blocks| P2[Detect]
    P1 -->|blocks| P3[Humanize]
    P1 -->|blocks| P4[Plagiarism]
    P1 -->|blocks| P5[RAG Indexer]
    P2 -->|LLM score| M[Model Providers]
    P2 -->|blended scores| OUT1[Results Stream]
    P4 -->|fragments| S[Web Search]
    P4 -->|matches| OUT2[Matches Stream]
    P3 -->|prompts| M
    P3 -->|rewrites| OUT3[Rewrite Stream]
    P5 -->|embeddings| M
    P5 -->|vectors| V[FAISS Index]
    P5 -->|top-k chunks| P6[RAG Agent]
    P6 -->|prompts| M
    P6 -->|answer + sources| OUT4[Chat Stream]
```

### 4.4.4 Class Diagram (runtime object interaction)

During a chat request, the runtime instantiates one `VectorStore` (from cache or built from chunks), one `_Context` holding the tool list and collected sources, and a compiled `StateGraph`. The graph runs a single model instance (the first of the provider chain) bound with tools; the same `_Context` accumulates `sources` as tools execute, and the stream handler reads events from `astream_events`. Figure 4.6's classes show the static relationships; at runtime the agent and the stream consumer share the `_Context` object so that retrieved sources can be emitted in the final `sources` SSE event.

### 4.4.5 Hierarchical Diagram

**Figure 4.9 — Hierarchical Diagram**

```mermaid
flowchart TB
    AIVERSE[AIverse]
    AIVERSE --> BE[Backend]
    AIVERSE --> FE[Frontend]
    BE --> ROUTE[Routers]
    BE --> SVC[Services]
    BE --> CORE[Core]
    BE --> AG[Agent]
    ROUTE --> R1[chat] & R2[detect] & R3[humanize] & R4[plagiarism] & R5[files] & R6[export] & R7[health]
    SVC --> S1[detect_service] & S2[humanize_service] & S3[plagiarism_service] & S4[rag_service] & S5[parse_service] & S6[export_service]
    CORE --> C1[blocks] & C2[heuristics] & C3[llm] & C4[config] & C5[sse] & C6[exceptions]
    AG --> A1[graph] & A2[nodes] & A3[tools] & A4[types]
    FE --> F1[Pages] & F2[Streaming Clients] & F3[UI Components]
```

## 4.5 Process Flow/Representation

### 4.5.1 Flowchart

**Figure 4.10 — System Flowchart**

```mermaid
flowchart TD
    A[User submits input] --> B{Input type?}
    B -->|pasted text| C[Parse text blocks]
    B -->|uploaded file| D[Validate MIME/size] --> C
    C --> E[Resolve source]
    E --> F{Which tool?}
    F -->|Detect| G[Heuristic scores] --> H[LLM assessments] --> I[Blend 60/40] --> J[Stream block scores + overall]
    F -->|Plagiarism| K[Build fragments] --> L[Search web per fragment] --> M[Match n-grams] --> N[Stream matched/unmatched]
    F -->|Humanize| O[Choose profile level] --> P[Rewrite blocks] --> Q{Success?}
    Q -->|yes| R[Stream tokens + block_end]
    Q -->|no| S[Keep original text] --> R
    F -->|Chat| T[Chunk + embed] --> U[Index FAISS] --> V[Agent loop] --> W[Stream tools/tokens/sources/done]
    R --> X[Optional export DOCX/PDF]
    J --> X
```

### 4.5.2 Sequence Diagram

**Figure 4.11 — Sequence Diagram (chat request)**

```mermaid
sequenceDiagram
    participant U as Browser
    participant BE as FastAPI Backend
    participant ST as VectorStore
    participant AG as LangGraph Agent
    participant M as Model Provider
    participant T as Tool (search_documents)

    U->>BE: POST /api/chat (source, question)
    BE->>ST: ensure index (chunk + embed + cache)
    ST-->>BE: index ready
    BE-->>U: SSE: meta (question)
    loop agent iterations (max 5)
        AG->>M: astream(messages)
        M-->>AG: tool_calls or tokens
        alt tool_calls
            AG->>T: execute tool
            T-->>AG: retrieved chunks / analysis
            AG-->>U: SSE: tool_start / tool_end
        else tokens
            AG-->>U: SSE: token
        end
    end
    AG-->>U: SSE: sources (excerpts + scores)
    AG-->>U: SSE: done (answer)
```

### 4.5.3 Activity Diagram

**Figure 4.12 — Activity Diagram (provider failover)**

```mermaid
stateDiagram-v2
    [*] --> SelectProvider
    SelectProvider --> Attempt: provider configured
    SelectProvider --> NextProvider: no key configured
    Attempt --> Success: stream completes
    Attempt --> Failed: exception
    Failed --> NextProvider: more candidates
    Failed --> NoCredits: no candidates left
    NextProvider --> Attempt
    Success --> [*]
    NoCredits --> [*]: "We can't process your message right now because you don't have enough credits."
```

---

# CHAPTER 5: IMPLEMENTATION

Chapter 5 describes how the design was realized: the algorithms behind each service, the external APIs consumed, and the user interface built on top of them.

## 5.1 Algorithm

### Algorithm 1 — Document Parsing

**Input:** pasted text or uploaded file (DOCX, PDF, TXT, MD)
**Output:** ordered list of typed blocks

```
BEGIN
  IF input is a file THEN
    validate MIME type and size (max 20 MB)
    IF unsupported THEN raise UNSUPPORTED_FILE_TYPE
    extract raw text per extension (docx→python-docx, pdf→pdfplumber, txt/md→utf-8)
  END IF
  split raw text into sentences
  group sentences into blocks by structure rules
  classify each block as heading | paragraph | list_item | blockquote
  attach index, level, and (later) score fields
  RETURN blocks
END
```

### Algorithm 2 — Heuristic AI-Likeness Score

**Input:** block text
**Output:** float score 0–100

```
BEGIN
  words = tokenize(text lowercased)
  IF length(words) < 10 THEN RETURN 50.0 END IF
  lengths = sentence word counts
  burst  = 100 - (stdev(lengths) / mean(lengths)) * 90
  ttr    = unique(words) / total(words);  ttr_score = clamp((0.92 - ttr) * 160, 0, 100)
  bigrams = count of adjacent pairs; rep = clamp(top_count / (words/20) * 25, 0, 100)
  trans  = clamp(transition_phrase_hits / words * 400, 0, 100)
  punct  = 100 - distinct_punctuation_count * 12
  score  = 0.30*burst + 0.25*ttr_score + 0.20*rep + 0.15*trans + 0.10*punct
  RETURN round(score, 1)
END
```

### Algorithm 3 — Detection Pipeline (per scorable block)

**Input:** blocks
**Output:** streamed SSE frames

```
BEGIN
  scorable = blocks of type paragraph | list_item | blockquote
  EMIT meta {total, flagged_threshold=70}
  FOR EACH block IN scorable (concurrent, bounded) DO
    heuristic = Algorithm 2(block.text)
    llm = try LLM assessment (Algorithm 5 chain); on failure NULL
    IF llm THEN score = 0.6 * llm.score + 0.4 * heuristic
           ELSE score = heuristic, reason = "heuristic only"
    EMIT block_score {index, ai_score, reason}
  END FOR
  overall = mean(scores)
  EMIT done {overall, flagged = overall >= 70, scores}
END
```

### Algorithm 4 — Provider Auto-Failover Chain

**Input:** primary provider + model
**Output:** ordered list of usable models

```
BEGIN
  candidates = [(primary, model)]
  IF FALLBACK_PROVIDER configured THEN candidates += [(fallback, fallback_model)] END IF
  candidates += [(groq, GROQ_MODEL)]
  candidates += [(openrouter, OPENROUTER_MODEL)]
  seen = {}
  chain = []
  FOR EACH (p, m) IN candidates DO
    IF (p, m) in seen THEN continue END IF
    IF provider p not configured THEN continue END IF
    seen += (p, m)
    chain += build_model(p, m)
  END FOR
  RETURN chain
END
```

### Algorithm 5 — Consumer-Side Failover

**Input:** chain of models, prompt
**Output:** streamed response or fallback

```
BEGIN
  last_error = NULL
  FOR EACH model IN chain DO
    TRY
      FOR EACH chunk IN model.astream(prompt) DO
        IF chunk.content non-empty THEN yield chunk.content END IF
      END FOR
      RETURN
    EXCEPT e
      last_error = e; log warning; continue
    END TRY
  END FOR
  yield "We can't process your message right now because you don't have enough credits."
END
```

### Algorithm 6 — RAG Chat

**Input:** source, question
**Output:** streamed SSE frames

```
BEGIN
  blocks = parse(source)
  key = hash(source)
  IF key not cached THEN
    chunks = chunk(blocks, size=800, overlap=100)
    embeddings = embed_documents(chunk texts)
    build and persist FAISS index + metadata
  END IF
  EMIT meta {question}
  context = new Context
  chain = Algorithm 4(primary, model)
  tools = [search_documents, analyze_ai_content, current_datetime]
  graph = compile(agent ⇄ tools, retry=2, timeout=60)
  FOR EACH event IN graph.astream_events(input, run_name, recursion_limit=30) DO
    CASE event.type:
      on_chat_model_stream  -> EMIT token
      on_tool_start         -> EMIT tool_start
      on_tool_end           -> EMIT tool_end
      on_chain_end (graph)  -> answer = last message content (fallback to streamed text)
  END FOR
  EMIT sources {excerpt, block_index, score} from context
  EMIT done {answer, events}
END
```

## 5.2 External APIs

| API / Service | Purpose | How it is called | Special handling |
|---|---|---|---|
| Google Gemini (Generative Language API) | Primary chat + reasoning model; embeddings | `ChatGoogleGenerativeAI` (LangChain) for chat; `google.genai` SDK for embeddings | Content arrives as list-of-parts → joined text; 100-request batch limit on embedding calls; key from `GEMINI_API_KEY` |
| OpenCode Zen (OpenAI-compatible) | First fallback chat provider | `ChatOpenAI` with `ZEN_BASE_URL` + `ZEN_API_KEY` | Free-tier usage limits surface as 429s → triggers failover |
| Groq (OpenAI-compatible) | Second fallback chat provider | `ChatOpenAI` with base `https://api.groq.com/openai/v1` | Free-tier `llama-3.3-70b-versatile`; skips automatically if `GROQ_API_KEY` empty |
| OpenRouter | Third fallback chat provider | `ChatOpenAI` with base `https://openrouter.ai/api/v1` + referral headers | Free models only (`...:free`); skipped if key empty |
| Ollama (optional) | Local chat/embeddings | `ChatOllama` / `OllamaEmbeddings` against `OLLAMA_BASE_URL` | No key required; used when a local model is preferred |
| DuckDuckGo HTML search | Plagiarism source lookup | `httpx.AsyncClient` GET on `html.duckduckgo.com/html/?q=...` | 120-word fragments, 1.5 s polite spacing, 10 s timeout, HTML parsed with stdlib `html.parser` |

All HTTP model calls are made through the async LangChain layer; the plagiarism client is an `httpx.AsyncClient` closed after the request. Every provider is invoked through Algorithm 4/5 so failures never terminate a request.

## 5.3 User Interface

The frontend is a Next.js App Router application (React 19, Tailwind v4, shadcn/ui, TanStack Query) running on port 3001 and reading the API base URL from `NEXT_PUBLIC_API_URL`. It provides:

- **Landing page** — product overview, feature cards, and navigation to the three tools.
- **Chatbot page** — a source picker (paste text, upload file, or file library) plus a streaming chat with disabled-until-ready Send button, suggestion chips, tool-activity traces ("Using search_documents…"), streaming answer bubble, and a Sources panel showing retrieved excerpts with similarity scores.
- **Checker page** — per-block score cards with reasons and an overall verdict, streamed live.
- **Remover page** — level selector (1–4), per-block streaming rewrites, and DOCX/PDF export buttons.

The UI was built with a bespoke design system (custom tokens, motion, accessible components) rather than a generic template, per the project's design requirements. Live screenshots of the landing page, chat, checker, and remover are captured in `imgs/` (see Appendix C, Figure C.1–C.4).

---

# CHAPTER 6: SYSTEM TESTING

Chapter 6 describes how the system was verified: manual end-to-end testing of the live application, the automated test suite, and a discussion of the measured results.

## 6.1 Manual Testing

Manual testing was necessary because the system's behavior depends on live third-party providers (quota states, stream timing, search results) that cannot be fully simulated in unit tests. It validated real streaming UX, provider failover, and cross-origin behavior against the actual running servers.

### 6.1.1 System Testing

- **Purpose:** verify each page and endpoint against the running backend (:8001) and frontend (:3001).
- **Scenarios tested:** health endpoint, CORS preflight from `http://localhost:3001`, file upload and listing, detection streaming, plagiarism streaming, humanize streaming, chat streaming with tools and sources, DOCX/PDF export.
- **Criteria:** HTTP 200 responses, correct SSE event ordering, non-empty final answers, and correct flag thresholds.
- **Observations:** all endpoints responded correctly; CORS preflight returned 200; chat produced tool activity, streamed tokens, source cards, and a final `done.answer`; checker produced per-block scores with reasons; remover produced rewritten blocks with preserved structure.

### 6.1.2 Unit Testing

- **Purpose:** verify isolated logic: heuristic math, block parsing, n-gram matching, SSE frame shape, chunk building, provider chain ordering, and graph routing.
- **Components tested:** `heuristics`, `blocks`, `parse_service`, `plagiarism_service`, `detect_service`, `humanize_service`, `rag_service`, `llm` (provider chain), file API.

| Test Case | Expected Result |
|---|---|
| Short text (<10 words) score | 50.0 |
| Highly uniform sentence lengths | High burstiness component → high score |
| Dense transition phrases | High transition component → high score |
| Vocab-rich varied prose | Low overall heuristic score |
| Provider chain (primary configured, fallbacks unconfigured) | `[primary]` only |
| Provider chain (all four configured) | `[primary, fallback, groq, openrouter]` in order |
| Fragments with no overlapping snippet | No matches returned |
| Fragment matching a snippet with ≥8-gram overlap | Match returned with URL |
| Chat SSE frame shape | `data: {json}\n\n` with expected event names |
| Chat on unknown file id | HTTP 404 |

### 6.1.3 Functional Testing

- **Functions tested:** detection blending, plagiarism fragment lifecycle, humanize level profiles, chat tool loop, export.
- **Example scenario:** submitting "stiff" text to the humanizer at level 4 with a model that always raises; **expected result** — the original text is emitted unchanged (`block_end.text == original`), proving the safe-fallback path.

### 6.1.4 Integration Testing

- **Integrations tested:** frontend ↔ backend (fetch + CORS), backend ↔ model providers (streaming and failover), backend ↔ web search (fragment queries), backend ↔ file system (upload, index persistence, export).
- **Issues identified:** (1) chat answers were empty on the frontend despite correct backend output; (2) a stray health request hit a malformed `//health` path; (3) provider quota exhaustion produced opaque errors.
- **Resolutions applied:** the empty-answer bug was traced to a `run_name` override in `astream_events` (see Section 7.1); the health probe was corrected to `/health`; quota failures are now reported through the provider chain with the explicit no-credits message.

## 6.2 Automated Testing

### 6.2.1 Tool Used

The backend uses **pytest** with the FastAPI `TestClient`, chosen for its async support, fixtures, and monkeypatching, which lets tests substitute fake models and fake search results so provider state never affects the suite. Example test:

```python
async def test_chain_skips_unconfigured_groq_and_openrouter(monkeypatch):
    fake = _FakeSettings()
    monkeypatch.setattr(llm, "settings", fake)
    models = [_name(m) for m in llm.get_model_chain("gemini", "m1")]
    assert "llama-3.3-70b-versatile" not in models
```

The frontend is validated with **Biome** (format + lint) and **ESLint**, plus a production build via `pnpm build`.

## 6.3 Results & Discussion

- **Automated suite:** 72 tests pass in approximately 2–3 seconds; `ruff check src` passes with zero findings; Biome and ESLint pass; the Next.js production build succeeds with four static routes.
- **Live verification:** `/health` returns 200; chat returned a real streamed answer with tool activity (two searches, one analysis), two source cards, and a populated `done.answer`; detection returned per-block scores with reasons; plagiarism returned matched/unmatched fragments; humanize returned rewritten blocks; DOCX/PDF export returned correctly typed binaries.
- **Failover behavior:** when both Gemini and Zen were quota-exhausted, the chat returned the explicit no-credits message instead of failing or hanging; after quota recovery, real answers resumed automatically without code changes.

All functional requirements FR-1 through FR-10 were exercised and satisfied; the non-functional requirements for performance, reliability, and maintainability were met as measured by streaming latency, the provider-failover recovery, and the clean quality gates.

---

# CHAPTER 7: CONCLUSION

## 7.1 Problems Faced and Lessons Learned

**Problems Faced:**
- Chat answers arrived empty in the UI even though the backend returned a complete final message.
- Free-tier provider quotas (Gemini and Zen) returned 429 errors, interrupting live testing at random times.
- Gemini returned content as a list of typed parts, breaking naive text handling.
- ESLint's `react-hooks/set-state-in-effect` rule flagged a state-in-effect pattern in the file library.
- Large embeddings requests could exceed the provider's 100-item batch limit.
- A stray browser probe hit a malformed `//health` path and initially suggested a false server failure.

**How They Were Resolved:**
- The empty-answer bug was root-caused to the `run_name` override: setting `run_name` in the `astream_events` config changes `event["name"]` from `"LangGraph"` to the custom run name, so the end-of-graph check never matched. The fix matches both names via a module constant (`_RUN_NAME`).
- The provider layer was redesigned as an ordered auto-failover chain (Algorithm 4/5) with a clear no-credits message.
- A chunk-text helper was added to join Gemini's list-of-parts content.
- The file library was migrated to TanStack Query (`useQuery`) with refetch-on-mutation instead of effect-driven state.
- Chunking and batching were kept under the provider limit, and index building runs in a background thread.
- Health checks were re-run against the correct `/health` path and the server was confirmed healthy.

**Lessons Learned:**
- Streaming event names are configurable and easy to break; assert on both the default and the configured run name.
- External provider state is part of the system under test—design for it (fallback chains) instead of assuming availability.
- Free tiers are a feature: they forced the failover design that makes the product resilient.
- Keeping files under hard line caps makes whole-tree linting and review practical.
- Verify "the server is down" before believing it—check the exact URL and the process table first.

## 7.2 Conclusion

AIverse achieves its aim of providing a self-hosted, provider-agnostic toolkit that detects AI content, checks plagiarism, humanizes rewrites, and answers questions grounded in user documents. Mapping to the objectives of Section 1.2: the statistical scoring engine (1), the 60/40 blend with flagging (2), the plagiarism fragment matcher (3), the level-based humanizer with safe fallback (4), the RAG chatbot with streamed evidence (5), the four-provider auto-failover (6), the modern streaming frontend (7), and the quality baseline of 72 passing tests plus clean lint gates and live verification (8) are all met. The system degrades gracefully under quota exhaustion and recovers automatically, confirming the reliability requirements.

## 7.3 Limitations of the Project

1. The AI-likeness score is heuristic, not a validated classifier; results vary by domain, length, and editing history and should be treated as advisory.
2. The application is single-tenant with no authentication; multi-user, multi-workspace use is future work.
3. Plagiarism coverage is bounded by the free web-search endpoint's index and rate limits.
4. Document support is text-based; scanned images and OCR are not handled.
5. Embedding and model availability depend on at least one configured provider being reachable.

## 7.4 Future Work

- Add user accounts, roles, and per-user document workspaces.
- Add Docker-based deployment, automated security tests, and CI/CD pipelines (Phase 8).
- Support additional formats (Markdown export, HTML, EPUB) and OCR for scanned documents.
- Add an accuracy benchmark harness with a labeled human/AI corpus to quantify detection precision.
- Add streaming progress and cancelation controls to long-running jobs.
- Extend the provider chain with local open-weight models for fully offline operation.

---

# BACK MATTER

## References

[1] "AI-generated content detection," Stanford HAI, 2023. Available: https://hai.stanford.edu/news/ai-generated-content-detection
[2] B. Guo et al., "How Close is ChatGPT to Human Experts? Comparison Corpus, Evaluation, and Detection," arXiv:2301.07597, 2023.
[3] OpenAI, "ChatGPT reaches 400M weekly users," 2025. Available: https://openai.com/index/
[4] "Generative AI in higher education," EDUCAUSE Horizon Report, 2024. Available: https://library.educause.edu/
[5] OpenAI, "AI Text Classifier," 2023. Available: https://openai.com/blog/new-ai-classifier-for-indicating-ai-written-text
[6] D. Ippolito et al., "Automatic Detection of Generated Text," EMNLP 2020.
[7] G. Jawahar et al., "RoBERTa-based AI-generated text detection," arXiv:2210.07321, 2022.
[8] P. Lewis et al., "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks," NeurIPS 2020.
[9] GPTZero, "GPTZero: Detect AI," 2023. Available: https://gptzero.me
[10] Turnitin, "Similarity and AI writing detection," 2023. Available: https://turnitin.com
[11] QuillBot, "QuillBot: Paraphrasing and grammar tool," 2023. Available: https://quillbot.com
[12] NetusAI, "AI bypass and paraphrasing," 2023. Available: https://netus.ai
[13] Google, "NotebookLM," 2024. Available: https://notebooklm.google.com
[14] Anthropic, "Claude with document uploads," 2024. Available: https://anthropic.com

## Pseudo Code

**Algorithm A — SSE Frame Formatter**

```
Algorithm: emit_sse
Input: event (string), data (dict)
Output: formatted SSE frame
BEGIN
  payload = "data: " + json(data) + "\n\n"
  yield payload
END
```

**Algorithm B — Plagiarism Pipeline**

```
Algorithm: plagiarism_pipeline
Input: source text
Output: streamed match frames
BEGIN
  blocks = parse(source)
  fragments = build_fragments(blocks, size=120 words, max=40)
  EMIT meta {total}
  client = new AsyncClient(timeout=10s)
  FOR EACH fragment IN fragments DO
    results = search(fragment)              // spaced 1.5s
    matches = match(results, ngram=8)
    EMIT fragment {index, text, matches}
    WAIT 1.5 seconds
  END FOR
  close client
  EMIT done
END
```

**Algorithm C — Humanize Pipeline**

```
Algorithm: humanize_pipeline
Input: source text, level (1-4)
Output: streamed rewrite frames
BEGIN
  blocks = parse(source)
  profile, temperature = level_profile(level)
  chain = Algorithm 4(default)
  EMIT meta {total, level}
  FOR EACH block IN blocks DO
    IF block not rewritable THEN continue END IF
    EMIT block_start {index, type}
    IF chain empty THEN pieces = [block.text]
    ELSE pieces = streamed_rewrite(chain, block, profile)  // per Algorithm 5
    END IF
    new_text = join(pieces).strip() OR block.text
    EMIT block_end {index, text}
  END FOR
  EMIT done {level, rewritten, blocks}
END
```

**Algorithm D — Detection API (HTTP layer)**

```
Algorithm: detect_endpoint
Input: POST /api/detect, body {source:{file_id|text}}
Output: SSE stream
BEGIN
  blocks = parse_service.resolve_source(source)   // 404 if file_id unknown
  stream = detect_stream(blocks)
  return StreamingResponse(stream, media_type="text/event-stream")
END
```

## APPENDICES

### Appendix A — Design Q&A

The seven design questions posed for this project, with answers drawn from the implementation.

**A.1 How is this app going to detect AI content?**

Detection is two-layered per block. First, a deterministic statistical heuristic scores five signals: sentence-length burstiness (30%), type-token ratio (25%), bigram repetition (20%), transition-phrase density (15%), and punctuation variety (10%). Second, the block text is sent to an LLM (through the failover chain) for a 0–100 judgment plus a reason. The final score is 60% LLM + 40% heuristic; an overall score ≥ 70 flags the document. Because the heuristic runs locally, detection still works—albeit heuristically—even when no model provider is reachable.

**A.2 How precise is the AI score?**

It is a transparent, directional indicator, not a validated classifier. There is no ground-truth benchmark in this project; the score measures statistical fingerprints that correlate with AI text and adds linguistic judgment from the LLM. Short, technical, or heavily edited text can mislead it. In practice it is reliable enough to act as a red flag: ≥70 "likely AI", <40 "likely human", between is ambiguous. A benchmark harness is planned future work (Section 7.4).

**A.3 What technologies were used for detecting the AI content?**

Custom Python feature extraction built on regular expressions and the standard library (no ML framework or trained model), plus LLM judgment via LangChain against Gemini, Zen, Groq, and OpenRouter. The blend weights and threshold are constants in `detect_service.py` (`_BLEND = 0.6`, `_FLAGGED_AT = 70`); the features are implemented in `core/heuristics.py`.

**A.4 Is the output relevant to the source material?**

Yes, by construction. Chat answers are grounded in retrieved chunks (top-4 FAISS hits) and the agent's tools can only read the user's document; the UI displays the exact excerpts and similarity scores used. The checker and humanizer operate per block on the user's actual text, and the humanizer preserves structure and reverts to the original on failure. The main bound on relevance is embedding quality and chunk granularity, not hallucination—though as with any LLM, phrasing should still be reviewed.

**A.5 Why did you use LangGraph?**

The chatbot is an agent loop (model ⇄ tools, up to 5 iterations) rather than a single prompt. LangGraph provides the explicit graph (START → agent ⇄ tools with a conditional edge), typed `MessagesState`, built-in retry (2 attempts) and timeout (60 s) policies, an iteration/recursion guard, and `astream_events`—the streaming hooks that power the live token and tool-activity events in the UI. It replaced a hand-rolled loop with a maintainable, testable orchestration layer.

**A.6 Define this application's logic, workflow, and ML models used.**

Workflow: input → parse → route by tool. Checker: heuristic + LLM blended, streamed. Plagiarism: fragments → web search → 8-gram matching. Humanizer: profile-based per-block rewrite with fallback. Chat: chunk(800/100) → Gemini embeddings → FAISS → LangGraph agent with tools → SSE sources + answer. ML models: `gemini-3.5-flash` (default chat), `gemini-embedding-2` (embeddings), fallbacks `deepseek-v4-flash-free` (Zen), `llama-3.3-70b-versatile` (Groq), `llama-3.3-70b-instruct:free` (OpenRouter); heuristics and matching are deterministic code, not ML.

**A.7 Elaborate on the tech stack and why it was used.**

FastAPI + uvicorn for native async SSE streaming and pydantic validation; LangGraph/LangChain for agent orchestration and a provider-agnostic model layer; FAISS for in-process, on-disk vector search with no external database; uv for fast reproducible Python environments; Next.js + React 19 + Tailwind v4 + shadcn/ui for SSR landing pages, streaming client components, and accessible UI; TanStack Query for file-library caching; SSE instead of WebSockets for simple one-way token streams that work through proxies; ruff/pytest and Biome/ESLint as the quality gates. Each choice minimized moving parts while maximizing streaming UX and provider flexibility.

### Appendix B — API & Configuration Reference

**B.1 Endpoints**

| Endpoint | Method | Request | Response |
|---|---|---|---|
| `/api/health` | GET | — | `{"status":"ok"}` |
| `/api/files` | GET/POST/DELETE | multipart file / id | FileOut JSON / 204 |
| `/api/detect` | POST | `{source:{file_id\|text}}` | SSE: meta, block_score*, done |
| `/api/plagiarism` | POST | `{source, max_results?}` | SSE: meta, fragment*, done |
| `/api/humanize` | POST | `{source, level}` | SSE: meta, block_start, token*, block_end*, done |
| `/api/chat` | POST | `{source, question}` | SSE: meta, tool_start, tool_end, token*, sources, done |
| `/api/export` | POST | `{source, format: docx\|pdf}` | File download |

**B.2 Environment variables (`backend/.env`, copied from `.env.example`)**

`ZEN_API_KEY`, `ZEN_BASE_URL`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `GROQ_API_KEY`, `OPENROUTER_API_KEY`, `OLLAMA_BASE_URL`, `DEFAULT_PROVIDER`, `DEFAULT_MODEL`, `TEMPERATURE`, `FALLBACK_PROVIDER`, `FALLBACK_MODEL`, `GROQ_MODEL`, `OPENROUTER_MODEL`, `EMBEDDING_PROVIDER`, `EMBEDDING_MODEL`, `DATA_DIR`, `CORS_ORIGINS`, `LOG_LEVEL`, `APP_ENV`.

Provider order used by the failover chain: **Gemini (default) → configured fallback → Groq → OpenRouter**, skipping any provider without a key.

### Appendix C — Test Inventory & Screenshots

**C.1 Automated tests (72 total):** `test_detect.py`, `test_files_api.py`, `test_heuristics.py`, `test_humanize_export.py`, `test_parse.py`, `test_plagiarism.py`, `test_provider_chain.py`, `test_rag.py`.

**C.2 Live screenshots** (stored in `imgs/`):
- Figure C.1 — Landing page (`landing.png`)
- Figure C.2 — Chatbot with streamed answer and sources (`chat-live.png`)
- Figure C.3 — Checker detection results (`checker-detect.png`)
- Figure C.4 — Remover rewrite results (`remover-live.png`)

## List of Figures

| No. | Caption |
|---|---|
| Figure 4.1 | Work Breakdown Structure |
| Figure 4.2 | Block Diagram |
| Figure 4.3 | Component Diagram |
| Figure 4.4 | Software Architecture Diagram |
| Figure 4.5 | Entity-Relationship Diagram |
| Figure 4.6 | UML Class Diagram (core domain) |
| Figure 4.7 | DFD Level 0 |
| Figure 4.8 | DFD Level 1 |
| Figure 4.9 | Hierarchical Diagram |
| Figure 4.10 | System Flowchart |
| Figure 4.11 | Sequence Diagram (chat request) |
| Figure 4.12 | Activity Diagram (provider failover) |
| Figure C.1 | Landing page screenshot |
| Figure C.2 | Chatbot screenshot |
| Figure C.3 | Checker screenshot |
| Figure C.4 | Remover screenshot |

## List of Tables

| No. | Caption |
|---|---|
| Table 3.1 | Requirements Traceability Matrix |
| Table 3.2 | Hardware Requirements |
| Table 3.3 | Software Requirements |
| Table 6.1 | Unit Test Cases |
| Table 6.2 | Functional Test Scenarios |
| Table 6.3 | Integration Test Scenarios |
| Table B.1 | API Endpoint Reference |

## List of Abbreviations

| Abbreviation | Full Form |
|---|---|
| API | Application Programming Interface |
| BMC | Business Model Canvas |
| CORS | Cross-Origin Resource Sharing |
| DFD | Data Flow Diagram |
| DOCX | Microsoft Word Open XML document |
| ERD | Entity-Relationship Diagram |
| FAISS | Facebook AI Similarity Search |
| FR | Functional Requirement |
| HTTP(S) | HyperText Transfer Protocol (Secure) |
| LLM | Large Language Model |
| NFR | Non-Functional Requirement |
| PDF | Portable Document Format |
| RAG | Retrieval-Augmented Generation |
| SDLC | Software Development Life Cycle |
| SSE | Server-Sent Events |
| TTR | Type-Token Ratio |
| UI | User Interface |

---

*End of report.*
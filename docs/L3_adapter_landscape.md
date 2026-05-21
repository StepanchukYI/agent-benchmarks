# L3 — Per-System Memory Adapter Landscape

**Status:** Research report, draft 1 (2026-05-21)
**Author:** Evgeniy + Claude (Cowork research run)
**Scope:** Comprehensive R&D scan of memory adapters considered for the agent-benchmarks L3 suite, plus their direct competitors and the standard benchmark methodology used across the field.
**Framing reminder:** *agent-benchmarks does not test Obsidian, Letta, or Mem0 — it tests the memory layer. Concrete storage systems are interchangeable adapters at L3.*

---

## 1. Краткое резюме (RU executive summary)

Этот отчёт собран для того, чтобы внутри L3 архитектуры (per-system adapter suite) разложить по полочкам, что именно мы оцениваем, когда говорим «адаптер памяти», и понять, какие из перечисленных в списке систем являются (а) реальными публичными продуктами с воспроизводимыми бенчами, (б) внутренними/непубличными инструментами, (в) пользовательскими паттернами поверх существующих хранилищ.

**Ключевые выводы:**

1. **L3 — это про слой памяти, не про хранилище.** Obsidian, Lantern, Mem0 и Letta стоят в одном ряду: для бенча они все — «адаптеры», реализующие один и тот же контракт *write → update → retrieve → forget*. Заявление «вы тестируете Obsidian» — категориальная ошибка; правильнее «Obsidian — один из adapter-suite, наравне с Letta или Mem0».

2. **Не все системы из списка верифицируются одинаково.** Из 11 заявленных:
   - **Полностью верифицируются** (paper + repo + публичные бенчи): Letta/MemGPT, Mem0, ReMe (AgentScope), supermemory, GitNexus, Graphify, Cloudflare Agent Memory (без бенчей, но продукт публичный).
   - **Верифицируется на уровне инфраструктуры, но не как «memory adapter»**: Obsidian + PARA + Backstage. Это substrates, бенчей нет.
   - **Не верифицируется как публичный продукт**: Lantern из MCP namespace `mcp__lantern__*` — не совпадает ни с одной из 7+ публичных компаний/проектов с таким именем (Splunk Lantern, lantern.dev, withlantern.com и др.). Скорее всего внутренний/early-access tool. В отчёте помечен как «vendor TBD».
   - **Пользовательский паттерн, не отдельный продукт**: MemPalace в твоей формулировке — это твой набор соглашений (rooms/halls/sub-types) поверх Obsidian, а не отдельная компания/фреймворк. Один из research-агентов ошибочно атрибутировал MemPalace «актрисе Милле Йовович» — это галлюцинация, я её отбросил.
   - **Скорее философия, чем продукт**: agentmemory.md — есть несколько небольших репозиториев с таким именем (jayzeng/agentmemory, rohitg00/agentmemory), но это конвенция «память в markdown файлах», не единый продукт.

3. **Бенчмарки.** Доминирующие в индустрии — **LoCoMo** и **LongMemEval**. Оба имеют серьёзные методологические проблемы (Penfield Labs нашёл 6.4% ошибок в gold answers LoCoMo; LLM-judge принимает до 63% намеренно неверных ответов). Публичный спор Mem0 vs Zep по LoCoMo показывает, что одни и те же скрипты в руках двух команд дают разные числа. Любая отдельная цифра — маркетинг, не наука. Правильно сравнивать **четырёхмерно**: accuracy × p95 latency × tokens-per-query × hallucination rate.

4. **Категории на рынке (2025-2026):**
   - **Hierarchical / OS-style:** Letta (бывш. MemGPT), MemoryOS, MemOS — память как иерархия с paging.
   - **Extract-Update / vector-first:** Mem0, supermemory.
   - **Temporal Knowledge Graph:** Zep / Graphiti.
   - **ECL / multi-modal graph:** Cognee.
   - **Zettelkasten / linked notes:** A-Mem, MemPalace-style паттерны на Obsidian.
   - **Filesystem-native:** Karpathy «LLM Wiki», jayzeng/agentmemory, Anthropic Memory Tool (тонкий контракт + BYO storage), Claude Code CLAUDE.md.
   - **Framework-native memory:** LangMem (LangGraph), CrewAI memory, AutoGen, txtai memory.
   - **Cloud-first managed:** Zep Cloud, Mem0 Cloud, supermemory, Cloudflare Agent Memory (private beta).
   - **Code-as-graph (для coding-агентов):** GitNexus, Graphify, SCIP/Cody, CodeQL, Glean, Sourcebot.
   - **Observability-adjacent (НЕ memory):** Langfuse, Phoenix; Helicone в maintenance mode с марта 2026.

5. **Что важно для L3 в agent-benchmarks:**
   - L3 suite должен включать **минимум по одному адаптеру из каждой категории**, иначе мы тестируем не «memory layer in general», а одну реализацию.
   - Адаптеры должны переключаться без перезаписи тестов — контракт стандартизирован (см. build spec §6 trajectory protocol).
   - Бенчмарк-нейтральность: не использовать только LoCoMo, потому что это вендорный спор; добавлять LongMemEval, MSC/DMR, HaluMem, BEAM.
   - Replay-friendly: каждый L3-тест должен быть пересчитываемым только по traj.jsonl (LSN-007).

6. **Ответ на исходную фразу.** «Это вы Obsidian тестируете?» → «Нет, мы тестируем memory layer. Obsidian — один из adapter suite, как Letta или Mem0. Стандартный контракт “write/update/retrieve/forget” проверяется поверх любого backend; конкретное хранилище — implementation detail.»

---

## 2. Framing: what L3 actually measures

The agent-benchmarks build spec (§5) defines L3 as **per-system adapter suites** — one suite per concrete memory backend. The unit under test is the *adapter*, not the backend. Every L3 suite measures the same four operations against the same eval set:

| Op | Contract |
|---|---|
| **write** | Decide which turns/events become long-term memories, with what shape (fact, event, preference, advice). |
| **update** | Resolve conflicts when a new fact contradicts an old one; mark the old fact superseded; preserve provenance. |
| **retrieve** | Given a query, return the smallest token-budget bundle that lets the agent answer correctly. |
| **forget** | Evict or down-rank memories that are stale, low-importance, or out-of-scope. |

This is the *memory contract*. Anything that implements it — a markdown vault, a Postgres + pgvector store, a Neo4j temporal graph, an Obsidian vault, a Notion workspace, Letta core/archival blocks, Mem0 extract/update pipeline — is a valid L3 adapter. The build spec deliberately keeps the contract storage-agnostic so adapters can be swapped without rewriting tests (the same way runners normalize different model outputs into one trajectory protocol).

This is why the question "are you testing Obsidian?" is a category error: **Obsidian is the substrate; the memory layer (PARA folders + MemPalace pattern + custom tool wiring) is the adapter**. The adapter could equally be Letta core blocks, Mem0 graph, or a plain CLAUDE.md file — and L3 should evaluate them under one common harness.

---

## 3. L3 adapter deep-dives

### 3.1 L3a — Obsidian + PARA + MemPalace + Karpathy pattern

**What it is.** A composite stack — not a single product.

- **Obsidian** (obsidian.md, by Erica Xu and Shida Li / Dynalist Inc.) — local-first markdown notes app. Free for personal and commercial use (the per-user commercial license was dropped). Optional paid add-ons: Sync $5/mo, Publish $10/mo. ~2,690+ community plugins reported by the project as of 2026.
- **PARA** — Projects / Areas / Resources / Archives taxonomy by Tiago Forte (Forte Labs 2017 blog, codified in *Building a Second Brain* 2022 and *The PARA Method* 2023). Just a folder convention.
- **MemPalace** — in the context of *this project's* vault rules (see `vault_rules` in user's global CLAUDE.md), MemPalace is the user's **personal pattern**: an Aspect/wing/hall/room layout where each lesson has a `sub_type` (`fact`, `event`, `discovery`, `preference`, `advice`, `pattern`, `bug`, `correction`). It is *not* a separately incorporated product or framework. One of the research subagents during this report's preparation hallucinated "MemPalace = framework by Milla Jovovich and Ben Sigman"; that attribution is rejected as unverifiable.
- **Karpathy pattern** — refers to Andrej Karpathy's recent (2024-2026) public advocacy for hand-curated, agent-maintained "LLM wikis" — markdown knowledge that compiles over time, explicitly framed as an alternative to RAG-as-default.

**Read/write surface.** Agents talk to the vault through:
- **Obsidian Local REST API** plugin (coddingtonbear/obsidian-local-rest-api) — HTTP CRUD over vault files.
- Several MCP wrappers: `MarkusPfundstein/mcp-obsidian`, `jacksteamdev/obsidian-mcp-tools` (adds semantic search + Templater prompts), `cyanheads/obsidian-mcp-server` (surgical heading-level edits).
- Operations: list / read / append / patch-by-heading / search (FTS + semantic) / tags / frontmatter.

**Data model.** Plain `.md` files on disk. Folders = PARA layout. MemPalace pattern = path convention (`Aspects/<wing>/rooms/<name>/{context,decisions,lessons}.md`). Optional embeddings via Smart Connections / Omnisearch. Filesystem is the source of truth.

**License + pricing.** Obsidian app: proprietary freeware. Local REST API plugin: MIT. PARA: book content copyrighted, method itself usable. The pattern conventions: yours.

**Benchmarks as a memory adapter.** *No published agent-memory benchmark numbers* on standard suites. Obsidian is used as a knowledge substrate, not benchmarked end-to-end as a memory layer. Some informal blog posts compare "filesystem-based memory" to vector stores favorably; see the Letta "Filesystem all you need" post (which uses a generic FS tool, not Obsidian specifically, and reports 74.0% on LoCoMo with GPT-4o-mini).

**Direct alternatives.**
- **Logseq** — open-source, block-level outliner, graph view.
- **Notion** — cloud, official MCP, retrieval-only.
- **Anytype** — local-first, P2P, encrypted, object-graph.

---

### 3.2 L3b — Lantern (work context) — **unverified**

**What it is — honest note.** The "Lantern" exposed in this session via the `mcp__lantern__*` namespace (with tools `create_issue`, `create_page`, `context_pack`, `graph_neighbors`, `graph_subtree`, `find_similar`, `list_transitions`, etc.) **could not be cross-confirmed** against any of the publicly documented products that share the name "Lantern":

| Public "Lantern" | What it actually is | Matches `mcp__lantern__*`? |
|---|---|---|
| Splunk Lantern | Customer-success content hub | No |
| lantern.dev | Postgres pgvector competitor | No |
| withlantern.com | Revenue/GTM AI | No |
| lanternstudios.com | Microsoft partner consultancy | No |
| uselantern.io | Screen-recording documentation | No |
| getlantern (GitHub) | Anti-censorship VPN | No |
| Lantern Pharma (withZeta.ai) | Drug-discovery co-scientist | No |

The MCP surface implies a Jira/Confluence-like issue tracker + wiki + typed knowledge graph aggregator. Most likely it is an **internal or early-access product** not yet publicly documented under a discoverable name. Treat this row as **vendor TBD** until confirmed.

**Inferred read/write surface** (from MCP tool names only):
- Issue lifecycle: `create_issue`, `transition_issue`, `update_issue_field`, `comment_on_issue`, `link_issues`.
- Page lifecycle: `create_page`, `read_page`, `list_sections`, `replace_section_body`, `append_to_section_body`, `insert_section_after`.
- Graph traversal: `graph_neighbors`, `graph_subtree`, `graph_referenced_by`, `graph_find_path`.
- Distinguishing verb: `context_pack` (bundles related issues + pages + graph slice into one LLM-ready payload).
- Vector index implied by `find_similar`.

**License + pricing.** Unknown.

**Benchmarks.** None published or expected (not externally documented).

**Direct alternatives in the actual niche** (issue + page + typed-graph aggregator):
- **Atlassian Rovo MCP** — official Jira + Confluence MCP, GA 2026, Atlassian-hosted.
- **sooperset/mcp-atlassian** — most-adopted community Atlassian MCP, 70+ tools.
- **Linear MCP** — issues-only, no pages/graph but polished.
- **knowall-ai/mcp-neo4j-agent-memory** — closest spirit on graph DB (gives graph_neighbors-style traversal but no issue/page CRUD).

---

### 3.3 L3c — Backstage (developer portal)

**What it is.** Open-source framework for internal developer portals. Built at Spotify, donated to CNCF September 2020, currently **CNCF Incubation** project. Latest release v1.48.4 (March 2026). Three pillars:
- **Software Catalog** — typed entities (Component, API, System, Domain, Resource, Group, User, Location).
- **TechDocs** — docs-as-code with mkdocs.
- **Software Templates** — scaffolder.

Apache-2.0.

**Read/write surface for AI agents.** As of 2026, Spotify's commercial distribution "Portal" ships `@backstage/plugin-mcp-actions-backend` — a first-party MCP integration that aggregates capabilities from every plugin into one MCP endpoint, discoverable by Claude Code, Cursor, VS Code Copilot, and Spotify's AiKA assistant. AiKA itself acts as both MCP client and server. Auth: static tokens or experimental Dynamic Client Registration via `@backstage/plugin-auth`. Officially labeled "highly experimental" in early 2026. Independent community MCP wrappers also exist.

**Data model.** YAML catalog entities (`catalog-info.yaml`) in PostgreSQL (SQLite for dev) + entity relationship graph + TechDocs (markdown → mkdocs → static HTML in object storage). No native embedding layer.

**License + pricing.** Apache-2.0; free self-host. Paid distributions: Spotify Portal (SaaS), Roadie.io (managed), Red Hat Developer Hub (part of OpenShift).

**Benchmarks as a memory adapter.** *No published agent-memory benchmark numbers* — Backstage is treated as a knowledge substrate (service ownership, docs lookup, dependency graph), not benchmarked. The angle "Backstage as long-lived memory for coding agents" is plausible and emerging (Spotify-Anthropic April 2026 livestream on agentic development) but no eval numbers yet.

**Adoption.** GitHub 32.7k stars, 7.1k forks, 1,852 contributors, 4,600+ dependent repos. Adopters include Spotify, American Airlines, Expedia, HP, LinkedIn, Netflix, Splunk, Trendyol, Zalando, Wayfair, Mercedes-Benz.

**Direct alternatives.**
- **Port** (port.io) — paid SaaS, marketed explicitly as "next-gen Backstage".
- **Cortex** (cortex.io) — paid SaaS, scorecards-first.
- **OpsLevel** — paid SaaS, similar catalog + scorecards model.
- **Compass** (Atlassian) — integrates with Jira/Confluence.

---

### 3.4 L3d.i — GitNexus (code knowledge graph)

**What it is.** Open-source MCP-native code knowledge graph engine by Abhigyan Patwari. Distributed as npm package `gitnexus` and CLI; no SaaS. Hit GitHub Trending mid-2026; MarkTechPost launch coverage dated 2026-04-24, so the public 1.x line is roughly two months old as of this writing.

**How an agent reads from it.** MCP server exposing:
- `gitnexus_impact` — blast radius, upstream/downstream callers, confidence scoring.
- `gitnexus_query` — process- and concept-ranked retrieval.
- `gitnexus_context` — full symbol context (callers, callees, processes).
- `gitnexus_detect_changes` — pre-commit diff against the graph.
- `gitnexus_rename` — call-graph-aware refactor.

CLI: `npx gitnexus analyze` (one-shot index + writes `.gitnexus/` + generates `CLAUDE.md`/`AGENTS.md`). `gitnexus serve` for the local bridge.

**Indexing model.** Multi-phase tree-sitter pipeline: file tree → AST → cross-file resolution (imports, calls, inheritance, constructor inference, this/self typing) → Leiden community clustering → process extraction (execution flows) → hybrid lexical + semantic index. The CLAUDE.md numbers in this project (4,394 symbols, 7,287 relationships, 113 execution flows) are typical per-repo output. Languages: TypeScript, JavaScript, Python, Java, C, C++, C#, Go, Rust, PHP, Kotlin, Swift, Ruby.

**License + pricing.** **PolyForm Noncommercial 1.0.0** — free for non-commercial use; commercial license on request (issues #735 and #1135). No public price list.

**Adoption + benchmarks.** Stars ~37.9k (star-history). Self-benchmark vs Claude Code's grep/glob: 43% fewer tokens, 68% fewer tool calls (1 graph query vs 38 grep+glob+read calls), ~25% lower cost, no quality regression. **No third-party head-to-heads** vs SCIP, CodeQL, or embedding RAG.

**Direct alternatives.** Graphify (broader multi-modal, MIT), Sourcegraph SCIP/Cody (server-backed, enterprise), CodeQL (security-flavored, QL query language, slower indexing).

---

### 3.5 L3d.ii — Graphify (multi-language code KG)

**What it is.** Open-source knowledge graph generator distributed primarily as an *agent skill* (Claude Code, Codex, OpenCode, Cursor, Gemini CLI, Copilot CLI, Aider). By Safi Shamsi; canonical repo `safishamsi/graphify`, site `graphify.net`. Went viral ~48h after Karpathy's "LLM knowledge bases" post in April 2026. Latest line: v5.

**How an agent reads from it.** Not a server-style MCP — runs locally inside the agent host. Triggered via `/graphify` (or the skill manifest). Queries return:
- *God nodes* (highest-degree concepts).
- *Surprising cross-file links*.
- *Design rationale* extracted from `# NOTE:` / `# WHY:` / `# HACK:` comments and docstrings.
- *Confidence tags* (EXTRACTED / INFERRED / AMBIGUOUS).

**Indexing model.** Tree-sitter → NetworkX in-memory graph → Leiden clustering → optional LLM pass on **semantic descriptions only** (raw source never sent to LLM) for higher-level concept and diagram extraction.

Languages: Python, JS, TS, Go, Rust, Java, C, C++, Ruby, C#, Kotlin, Scala, PHP, Swift, Lua, Zig, PowerShell, Elixir, Objective-C, Julia (19 plus app code, SQL schemas, R/shell scripts, docs, PDFs, images, video transcripts — all in one graph).

**License + pricing.** MIT, fully free.

**Adoption + benchmarks.** ~49.8–50.2k stars (star-history rank #438), 5.4k forks. **One self-reported claim**: 71.5× fewer tokens per query on "mixed corpora". No independent reproduction.

**Direct alternatives.** GitNexus (deeper call-graph reasoning, MCP-native), Howell5/graphify-ts (TS reimplementation, 12 langs, incremental updates), colbymchenry/codegraph (pre-indexed local code graph for the same agent set).

---

### 3.6 L3e — Letta (formerly MemGPT)

**History.** MemGPT first appeared as arxiv 2310.08560 (Packer, Fang, Patil, Wooders et al., October 2023, UC Berkeley Sky Lab). Rebranded to Letta in 2024. Letta Inc. emerged from stealth September 2024 with a **$10M seed** led by Felicis at ~$70M post-money, with Sunflower Capital, Essence VC, and angels including Jeff Dean and Clem Delangue. Co-founders: Charles Packer (CEO), Sarah Wooders (CTO).

**Architecture — hierarchical / OS-inspired.**
- **Main context (in-window):** system instructions + **core memory blocks** (always pinned, structured, labeled, agent-editable, shareable across agents — e.g. `persona`, `human`).
- **External context (out-of-window):** **recall memory** (searchable table preserving full interaction history) and **archival memory** (semantically searchable vector store for long-term facts).
- Agent pages data between tiers via **tool calls** (`core_memory_append`, `archival_memory_insert`, `archival_memory_search`, `conversation_search`). LLM generates an internal monologue between calls.

**Integration surface.** Python SDK, TypeScript SDK, REST API, ADE GUI, Vercel AI SDK provider (`@letta-ai/vercel-ai-sdk-provider`), Composio / LangChain / CrewAI tool schemas, MCP server (Letta agents can both **expose** memory as MCP and **consume** MCP tools). No first-party Claude Agent SDK / OpenAI Agents SDK adapters — those go through MCP. AWS Marketplace AMI available.

**Storage backend.** **Postgres + pgvector** (production deployments use Amazon Aurora PostgreSQL, see AWS Database Blog). SQLite for local dev. Two tables: `archival_passages` (agent-owned) and `source_passages` (attached external). Other vector DBs are not first-class — Letta is opinionated around pgvector.

**License + pricing.** Apache-2.0 OSS. Self-host free (you pay your LLM tokens + DB). Letta Cloud usage-based with a limited free tier; per-token rate sheet not enumerated publicly at the time of this report (verify on letta.com/pricing before quoting).

**Benchmarks — vendor-reported.**
- **MSC / DMR (paper):** improvements over fixed-context and recursive-summary baselines, largest gains on "conversation opener" tasks; ROUGE-L and LLM-judge accuracy gains; no single headline number — per-task tables.
- **Nested KV retrieval (paper):** only method tested that solves depth ≥ 2 consistently.
- **Document QA (paper):** accuracy flat as document length grows while baselines degrade.
- **Letta blog "Filesystem all you need" (August 2025):** **74.0% on LoCoMo** with GPT-4o-mini using a plain filesystem tool — the implicit critique is that the *specialized memory layer matters less than the agent's ability to manage context*.
- **LongMemEval:** no published Letta score; open feature request in letta-ai/letta#3115.

**Critique.** MemGPT paper numbers are vendor-reported (authors = founders), but the benchmarks themselves (MSC, document QA) are external. Independent reproductions exist in academic follow-ups (A-Mem, MemoryAgentBench) with mixed results across base models.

**Direct alternatives.** LangMem (LangChain), AutoGen (Microsoft), CrewAI memory.

---

### 3.7 L3f — Mem0

**History.** Launched January 2024 by Taranjeet Singh (CEO) and Deshraj Yadav (CTO, formerly led AI Platform at Tesla Autopilot; co-built EvalAI). YC-backed. Funding: $3.9M seed (Kindred Ventures) + **$20M Series A** (October 2025, led by Basis Set Ventures with Peak XV, GitHub Fund, YC) = **$24M total**. Headline paper: arxiv 2504.19413 ("Mem0: Building Production-Ready AI Agents with Scalable Long-Term Memory", ECAI 2025).

**Architecture — two-stage extract-update pipeline per turn.**
- **Extract:** an LLM (GPT-4o-mini with function calling in the paper) reads latest message + short window, extracts salient facts as candidate memories.
- **Update:** another LLM pass compares candidates against retrieved nearest-neighbor existing memories and decides ADD / UPDATE / DELETE / NO-OP. **Conflict resolution lives here.**
- **Mem0-graph variant:** same extract step pulls **entities + relation triplets** written to Neo4j, enabling multi-hop traversal. Paper reports Mem0-graph adds ~2 J-points over base Mem0 overall.

**Integration surface.** Python SDK (`mem0ai` on PyPI), TS SDK (`mem0ai` on npm), CLIs, FastAPI REST self-host (Docker: FastAPI + Postgres/pgvector + Neo4j), **Mem0 MCP server** (`mem0ai/mem0-mcp`), first-class adapters for LangChain, LlamaIndex, CrewAI, Vercel AI SDK, **OpenAI Agents SDK**, **Claude Agent SDK** (via Composio toolkit + docs.mem0.ai/integrations/*). Cloud REST API also exposed.

**Storage backends.**
- Vector: **Qdrant (default)**, Chroma, Pinecone, Weaviate, Milvus, pgvector, Redis, Vectorize, in-memory; Valkey for TypeScript.
- Graph: **Neo4j (primary)**, Memgraph.
- LLM/embedder: OpenAI, Anthropic, Gemini, Ollama, Azure, Bedrock — pluggable.

**License + pricing.** **Apache-2.0** (LICENSE in repo). Hosted tiers as last advertised: Hobby free (~10K memories, 1K retrievals/mo), Starter ~$19/mo (~50K memories), Pro ~$249/mo (unlimited + graph + analytics), Enterprise quote-based with on-prem/SSO/SLA. Verify on mem0.ai before quoting.

**Benchmarks — vendor-reported on LoCoMo.** Metrics: F1, BLEU-1, and **J = LLM-as-judge** binary correctness (not F1, not recall@k).
- **Overall J score: 66.9%** (Mem0) vs **52.9%** (OpenAI memory feature) → the famous **+26% relative uplift**.
- **Mem0-graph:** ~+2 J-points over base Mem0 overall.
- **Latency:** Mem0 median search ~0.20s, **p95 ~1.44s end-to-end**; full-context baseline ~9.87s median, ~17.12s p95 → **~91% p95 latency reduction**.
- **Token cost:** ~7K tokens average memory footprint, **<10% of full-context** → "90%+ token savings".
- **Per-category J relative gains:** single-hop +5%, temporal +11%, multi-hop +7% over best prior method in each category. Some Mem0 marketing also cites larger absolute deltas (temporal +29.6, multi-hop +23.1) — those are absolute J-point differences vs. a specific baseline, NOT the same numbers as head-to-head SOTA deltas.

**Critique — important.** All Mem0 LoCoMo numbers are **vendor-reported by Mem0**. There is an active **public benchmark dispute** with Zep:
- Zep originally claimed 84% LoCoMo (Zep blog).
- Mem0 published a re-evaluation putting Zep at **58.44%**, arguing Zep included the "adversarial" category (refusal behavior under an unscoreable judge) in the overall average.
- Zep counter-published **75.14%** with corrected methodology (getzep/zep-papers issue #5).
- Multiple practitioners report they cannot reproduce Mem0's published numbers from the open-source `mem0ai/memory-benchmarks` runner alone.

**Reasonable read:** LoCoMo is a real but immature benchmark. The methodology dispute is now a more interesting datapoint than any individual headline number.

**Direct alternatives.** Zep, Cognee, MemoryOS, A-Mem, MIRIX.

---

### 3.8 L3g — Cloudflare Agent Memory

**What it is.** Managed persistent-memory service for AI agents, announced in **private beta on April 17, 2026** during Cloudflare's Agents Week. Sits on top of the existing Cloudflare Agents SDK (each agent = a Durable Object).

**Architecture — hybrid.** Each "memory profile" gets its own Durable Object with a SQLite store (FTS, supersession chains, transactional writes). Retrieval layered onto **Vectorize** (Cloudflare's distributed vector DB). Embedding/extraction inference runs on **Workers AI**. Below it, the Agents SDK Session has a tree-structured message history; "memory blocks" (skills, soul/identity, scratchpads) can be read-only or writable via a built-in `set_context` tool.

**Integration.** TypeScript/JS SDK (`agents` package, `Agent` class, Sessions API), MCP server support, HTTP from any Worker. Memory providers pluggable — default SQLite, optional Vectorize search provider. Skills can load from R2 (`SOUL.md` pattern).

**License + pricing.** Agents SDK open-source on Cloudflare GitHub. Agent Memory itself closed-source managed service, **private beta**, no public price sheet yet. Underlying Durable Objects pricing is the published proxy: ~$0.20 per million requests, $12.50/M GB-s compute, plus storage and Vectorize query costs.

**Benchmarks.** **None published.** Cloudflare markets "predictable cost, latency, cleaner agent reasoning" but no LoCoMo / LongMemEval numbers. Adoption undisclosed (private beta).

**Direct alternatives.** Letta, Zep Cloud, Mem0 Platform.

---

### 3.9 L3h — ReMe (AgentScope)

**What it is.** "Remember Me, Refine Me" — the memory module of Alibaba Tongyi Lab's **AgentScope** framework. Canonical repo `agentscope-ai/ReMe` (mirrored at `modelscope/ReMe`). v0.1.8 shipped September 2025 (async support); ReMeV2 architecture document late 2025; paper arxiv 2512.10696 ("Remember Me, Refine Me: A Dynamic Procedural Memory Framework for Experience-Driven Agent Evolution") December 2025.

**Architecture — three tiers.**
- User-facing interfaces.
- Memory systems (file-based + vector-based stores).
- Infrastructure.

Hybrid retrieval: **vector + BM25 with fusion 0.7/0.3**. Three novel pieces:
- Multi-faceted distillation (extract success / failure / comparative experiences).
- Context-adaptive reuse (scenario-aware indexing).
- Utility-based refinement (auto-add / prune).

**Integration.** Python API, HTTP REST, MCP server. Integrated into `agentscope-runtime`'s memory service November 2025.

**License + pricing.** Apache-2.0, fully open-source. Free self-host; no SaaS tier.

**Benchmarks.** Authors claim SOTA on **BFCL-V3** and **AppWorld** in the paper. GitHub adoption modest relative to Mem0/Zep — concrete star counts not reliably surfaced — but it's the official AgentScope memory layer, so adoption tracks AgentScope itself.

**Direct alternatives.** Mem0, Letta, LangMem.

---

### 3.10 L3i — agentmemory.md (convention, not a single product)

**Honest framing.** There is **no canonical `agentmemory.md` spec** analogous to AGENTS.md or CLAUDE.md. The closest concrete artifacts:

- **`jayzeng/agentmemory`** on GitHub — CLI giving coding agents (Claude Code, Codex, Cursor, Aider) persistent memory in local markdown files.
- **`rohitg00/agentmemory`** — separate, less popular repo with similar premise.
- A broader **convention** described in blogs (dev.to, Towards Data Science, Nicolas Bustamante's "Agent Memory Engineering") — memory-as-documentation in plain `.md` files in the workspace, git-friendly.

**Architecture.** Pure filesystem + markdown. `jayzeng/agentmemory` stores long-term facts, daily logs, topic/event notes, and a scratchpad as `.md` files under a project memory directory. Optional `qmd` integration (tobi/qmd) layers keyword + semantic + hybrid search via local embeddings. No vector DB unless `qmd` installed; graceful degradation to grep otherwise.

**Integration.** `npm i -g myagentmemory` (also Homebrew, source build). Exposes `memory_search`, `memory_write`, daily-log, scratchpad commands. Designed to be called as tools by Claude Code / Codex / Cursor; injects relevant past memory into each turn automatically.

**License + pricing.** MIT (typical), free, fully local. No SaaS.

**Benchmarks.** **No published benchmarks.** The competing `rohitg00/agentmemory` claims "#1 persistent memory for AI coding agents based on real-world benchmarks" but no methodology is published. Honest answer: marketing only.

**Direct alternatives.** `zilliztech/memsearch` (markdown + Milvus), `memweave` (markdown + SQLite), OpenClaw / CLAUDE.md-style hand-rolled patterns, Claude Code's own CLAUDE.md + skills mechanism.

---

### 3.11 L3j — supermemory

**What it is.** "Memory API for the AI era" by Dhravya Shah (founded at age 19). **$2.6M seed** led by Susa Ventures, Browder Capital, SF1.vc; angels include Jeff Dean (Google) and Dane Knecht (Cloudflare). YC-adjacent — 70+ YC companies listed as customers.

**Architecture.** Hybrid vector + keyword search with context-aware reranking and temporal filtering. Builds a knowledge graph over ingested data; byte-level deduplication ("SM tokens" are deduped unique content). Sub-300ms p50 retrieval at 100B+ tokens/month scale (claimed).

**Integration.** REST API ("Memory Router"), Python and TypeScript / AI-SDK SDKs, MCP server, plugins for OpenCode and similar coding tools. Open-source core at `supermemoryai/supermemory` — **license is non-standard / source-available**; verify LICENSE before redistribution. MIT applies only to specific plugins (e.g. `opencode-supermemory`).

**License + pricing.** Tiers as of 2026: **Free $0** (1M tokens, 10K searches/mo), **Pro $19/mo** (3M tokens), **Scale $399/mo** (enterprise volumes), **Enterprise** custom. Overage $0.01 / 1K tokens and $0.10 / 1K searches. Startup program: $1,000 credits + 6 months for qualifying early-stage teams.

**Benchmarks (vendor-reported).** On their own MemoryBench / LoCoMo runs:
- **59.7% P@1** vs ~34% baseline.
- **83.5% Recall@10** vs 69.3%.
- p50 < 300ms.

**Caveat:** these are vendor-reported on LoCoMo, whose methodology has been publicly disputed (Zep "Lies, damn lies" post). Treat as marketing.

**Adoption claims.** 30+ enterprises, 10,000+ developers, 70+ YC companies.

**Direct alternatives.** Mem0, Zep Cloud, Letta/MemGPT.

---

## 4. Wider competitor landscape (memory for agents, May 2026)

### 4.1 Zep / Graphiti — temporal knowledge graph

- **What:** Zep AI's memory layer; Graphiti is the OSS engine. Architecture: bi-temporal knowledge graph (entities + relations + valid-from/valid-until timestamps).
- **License:** Graphiti Apache-2.0 OSS; Zep Cloud proprietary (Free 1k credits, Flex $25/10k, Flex Plus $75/40k, Enterprise). Community Edition discontinued in 2025.
- **Benchmarks (vendor):** Zep paper (arxiv 2501.13956, Jan 2025) — 94.8% DMR (vs MemGPT 93.4%); LongMemEval +18.5% with gpt-4o, +15.2% with gpt-4o-mini, ~90% lower latency, <2% baseline tokens. LoCoMo 75.14% J (Zep self-reported); Mem0 re-ran and got 65.99% for Zep; community re-eval pegged 58.44%.
- **Position:** temporal-first, enterprise-grade; most credible KG-based alternative to Mem0.

### 4.2 Cognee — ECL multi-modal memory

- **What:** Topoteretes (Berlin), open-source "memory control plane". Architecture: Extract-Cognify-Load pipeline → typed KG + embeddings. Defaults to **Kuzu** as embedded graph backend (graph is in the OSS tier, unlike Mem0).
- **License:** Apache-2.0. ~17.1k GitHub stars. Managed Cognee Cloud uses doc-count packs ($35/1k, $100/3k, $750/15k).
- **Benchmarks:** publishes on its own evaluation harness (Cognee vs Mem0 vs Graphiti vs LightRAG on Human-LLM Correctness, DeepEval, F1, EM). No canonical LoCoMo/LongMemEval numbers in public material.
- **Position:** graph-first OSS alternative to Mem0; air-gapped / local-first differentiator.

### 4.3 MemoryOS (BUPT)

- **What:** Kang/Ji/Zhao/Bai, EMNLP 2025 Oral (arxiv 2506.06326). Three-tier OS-style hierarchy: Short-Term (FIFO dialog), Mid-Term (recurring topic summaries), Long-term Personal (preferences). Explicit STM→MTM and MTM→LPM update policies with segmented-page strategy + heat-based replacement.
- **License:** OSS (BAI-LAB GitHub). Also exposed as MCP server.
- **Benchmarks:** LoCoMo with GPT-4o-mini — +49.11% F1, +46.18% BLEU-1 over baseline; quality-gated variant F1 = 53.5 vs Mem0 51.2.
- **Position:** cleanest academic articulation of OS-style hierarchical memory; counterweight to Mem0's flat-vector approach.

### 4.4 A-Mem (Rutgers + AIOS)

- **What:** Xu et al., NeurIPS 2025 (arxiv 2502.12110). Zettelkasten-inspired memory network — each new memory is a "note" with context + keywords + tags; system proposes typed links to existing notes and updates older notes as new evidence arrives.
- **Benchmarks:** LoCoMo F1 = 27.23 vs baseline reader 4.68 vs ReadAgent 2.81. Multi-hop: ROUGE-L 44.27 / METEOR 23.43 / SBERT 70.49. (Different reporting convention than Mem0's J — careful comparing.)
- **Position:** strongest published "linked-notes" architecture; conceptually closest to Obsidian-style human knowledge management.

### 4.5 LangMem / LangGraph Memory Store

- **What:** LangChain's official memory SDK on top of LangGraph's `BaseStore` (in-memory, Postgres, LangGraph Platform). Two layers: functional memory managers (extract / update / consolidate) + native integration with LangGraph's persistent store. Supports semantic / episodic / procedural memory shapes.
- **License:** MIT.
- **Benchmarks:** **no canonical LoCoMo/LongMemEval published**. Third-party benchmarks (Mem0, Atlan/n1n) report high p95 latency (~60s) and lower accuracy than Mem0/Zep on long-conversation recall — vendor-published, treat as such.
- **Position:** batteries-included default if already on LangGraph; weak on standalone benchmark numbers.

### 4.6 OpenAI Memory

Two distinct products:
- **ChatGPT Memory** (consumer): references saved memories and (since April 2025) all past conversations. Not an API offering.
- **For developers:** no first-party "memory tool" equivalent. **Responses API** (the Assistants API successor, Assistants API sunsetting **Aug 26, 2026**) provides stateful conversations with `previous_response_id`, plus first-party `file_search` over OpenAI-hosted vector stores. Most teams use this as a de-facto memory substrate.
- **Benchmarks:** no first-party published numbers. Mem0's vendor benchmark places ChatGPT Memory materially below Mem0 (66.9 J vs 52.9 J).
- **Position:** for builders, you compose Responses API + file_search + your own scaffolding — there is no first-party agent-memory primitive yet.

### 4.7 Anthropic / Claude Memory

Two memory surfaces:
- **Claude Code CLAUDE.md + skills + Auto Memory** — file-based persistent context for the CLI. CLAUDE.md read every session; Auto Memory accumulates across sessions.
- **Claude API memory tool** — launched in beta **September 29, 2025**, tool type `memory_20250818`, beta header `context-management-2025-06-27`. **Client-side tool**: Anthropic defines the schema (create/read/update/delete files under `/memories`) and ships SDK helpers (`BetaAbstractMemoryTool` Python, `betaMemoryTool` TS). You subclass against your own storage backend. Supported on Sonnet 4 / 4.5, Haiku 4.5, Opus 4 / 4.1.
- **Pricing:** tool free with API; storage is yours.
- **Benchmarks:** no first-party LoCoMo/LongMemEval. Case-study claims (Netflix, Rakuten, Wisedocs, Ando): 97% reduction in first-pass errors, 30% speedup on document workflows.
- **Position:** Anthropic ships a **contract**, not a memory store. BYO substrate. Opposite philosophy from Zep Cloud / Mem0.

### 4.8 Observability — Langfuse / Phoenix / Helicone (NOT memory)

None of these have a first-class memory product:
- **Langfuse** (MIT, self-hostable) — LLM observability: traces, evals, prompt management. Traces agent runs; does not store agent memory.
- **Arize Phoenix** — notebook-first OpenTelemetry tracer, same category.
- **Helicone** — entered maintenance mode March 2026 after founders moved to Mintlify; not recommended for new projects.

Teams pair observability with a separate memory vendor.

### 4.9 Pinecone / Weaviate / Qdrant — vector DBs moving up-stack

- **Pinecone Assistant** — managed RAG as a service (chunk + embed + query + rerank). "Pinecone Nexus" / Context API is the new agent-context offering; no dedicated "agent memory" SKU.
- **Weaviate** — went further: March 2025 launched three Agents (Query, Transformation, Personalization); now publicly previewing **Engram** — an explicit agent memory product.
- **Qdrant** — positions as substrate, not product. Most common backend for Mem0, OpenClaw, bespoke memory systems. Ships Qdrant Skills for coding agents.

Licenses: Pinecone proprietary SaaS; Weaviate BSD-3 OSS + Cloud; Qdrant Apache-2.0 OSS + Cloud. No first-party LoCoMo/LongMemEval numbers from any of the three.

### 4.10 Redis 8 + Redis Agent Memory Server

Redis 8 (GA late 2025) added native **Vector Sets** — sorted-set vector similarity with int8 quantization. On top, **Redis Agent Memory Server** (github.com/redis/agent-memory-server) provides namespaced semantic/keyword/hybrid recall, slots into LangGraph as both short-term checkpointer and long-term Store. License: BSD/RSAL (Redis 7.4+ relicensing applies). No published LoCoMo/LongMemEval. Position: one in-memory substrate for cache + vector + memory + rate limit.

### 4.11 Vercel KV / Vercel Memory

**Vercel KV has been sunset.** Vercel removed it from first-party storage and now points to Marketplace partners (Upstash Redis, etc.). **No Vercel-branded memory product as of May 2026.** Vercel AI SDK leaves memory composition to the developer.

### 4.12 MemoryBank / Reflexion / Generative Agents (historical foundations)

- **Generative Agents** (Park et al., Stanford+Google, 2023) — observation/reflection/plan memory stream with recency × relevance × importance retrieval. Template most modern systems still echo.
- **Reflexion** (Shinn et al., 2023) — verbal self-reflection memory: text post-mortem after each failed trajectory; no gradient updates.
- **MemoryBank** (Zhong et al., 2023) — Ebbinghaus-forgetting-curve-based memory updates for long conversations.

All academic / MIT-style; none published on LoCoMo/LongMemEval (benchmarks postdate them). Ancestors of essentially every system in this report.

### 4.13 MemOS (≠ MemoryOS)

Li et al., arxiv 2505.22101 + extended 2507.03724. Unifies three memory types — plaintext, activation (KV cache), parameter (LoRA-style) — into a common **MemCube** with provenance and versioning; schedulable, composable, convertible between forms. Apache-2.0. Reports 35.24% token savings vs in-context baseline; canonical LoCoMo/LongMemEval in extended paper. **Most ambitious "memory-as-system-resource" architecture**, includes parametric memory.

### 4.14 Chroma Cloud / Chroma collections

Chroma Inc., OSS vector + sparse + full-text + regex search. Chroma Cloud GA early 2025. Hot-RAM / warm-SSD / cold-object-storage tiering with $0.02/GB/mo object storage; p50 ~20ms warm latency. Collection forking (Nov 2025), Web Sync newer. Apache-2.0. Pricing: $5 free credits on Starter, $100 on Team, usage-based after. **Does not position as agent memory** — positions as cheap, fast retrieval infrastructure. Cost-leader on storage among hosted vector DBs.

### 4.15 Other / unverified

- **"EnergyTraining" / reflection-style memory** — could not be found as a real product as of May 2026. Reflexion (covered above) is the closest research thread.
- **txtai memory module** (NeuML, Apache-2.0) — lightweight, embedded-first wrapper around txtai embeddings index for past interactions and tool outputs. No published LoCoMo/LongMemEval. Not a contender for SOTA agent memory benchmarks.

---

## 5. Benchmark methodology reference

### 5.1 LoCoMo — Long Conversation Memory

- **Citation:** Maharana, Lee, Tulyakov, Bansal, Barbieri, Fang. ACL 2024 (arxiv 2402.17753). Snap Research + UNC + USC.
- **What it measures:** 10 multi-session conversations, ~300 turns / ~9K tokens average / up to 35 sessions, persona-grounded, human-verified. 1,540 questions, 5 categories: single-hop, multi-hop, temporal, open-domain, adversarial. Two task types: QA (F1, BLEU, ROUGE) and event-graph summarization. Mem0/Zep/MemoryOS report **J-score** (LLM-judge {1, 0.5, 0}).
- **How memory plugs in:** raw multi-session dialogue; system ingests session-by-session, builds its memory, answers at the end. RAG / long-context / vector + graph compete on identical input.
- **Critiques:**
  1. Penfield Labs audit: **6.4% answer-key errors** (99 of 1,540) — hallucinated facts, temporal slips, speaker-attribution errors. Default LLM judge accepts up to **63% of intentionally wrong** answers.
  2. Conversations average **16–26K tokens** — fully within GPT-4o/Claude windows, so full-context baseline beats most published memory systems (~73% J vs Mem0 ~68%).
  3. Vendor disputes (see Mem0 vs Zep below).
  4. Distribution skew — adversarial and open-domain dominate easy-to-game categories.
- **Top results 2025-2026 (J-score):** Mem0 token-efficient algorithm 92.5; ByteRover 2.0 92.2; MemMachine 84.87; Memori 81.95; Zep 79.09; LangMem 78.05; Mem0 paper main config 51.15 J / 28.64 F1; Zep self-reported 75.14; Zep re-eval by Mem0 65.99; Zep community re-eval 58.44.

### 5.2 LongMemEval

- **Citation:** Wu, Wang, Pang, Yu, Han, Liu, Yang, Yu, McAuley. **ICLR 2025** (arxiv 2410.10813). *Note: often misattributed to NAACL.*
- **What it measures:** 500 hand-curated questions across 5 abilities: (1) information extraction, (2) multi-session reasoning, (3) temporal reasoning, (4) knowledge updates, (5) abstention. "LongMemEval-S" presents ~115K tokens of history per question; full version >1M. Metric: GPT-4-judged accuracy.
- **How memory plugs in:** explicit three-stage pipeline — indexing → retrieval → reading. System can use any combination of session decomposition, fact extraction, expanded keys, time-aware queries.
- **Critiques:** commercial assistants drop ~30 accuracy points on long histories; long-context LLMs weaker than retrieval+memory pipelines on Q-types 3 and 4; vendors selectively report easy subsets.
- **Top results 2025-2026:** OMEGA 95.4% (GPT-4.1); Mastra Observational Memory 94.87% (GPT-5-mini); Emergence AI 86%; EverMemOS 83.0%; TiMem 76.88% (GPT-4o-mini); Zep/Graphiti 71.2% (GPT-4o); third-party Mem0 ~49% on GPT-4o.

### 5.3 MSC — Multi-Session Chat

- **Citation:** Xu, Szlam, Weston. ACL 2022. Facebook AI Research.
- **What it measures:** persona-grounded dyadic dialogue, up to 5 sessions with explicit time gaps; ~12 messages/session. Original task: response generation (perplexity + F1 vs human gold + engagingness rating).
- **MemGPT extension — DMR (Deep Memory Retrieval):** 500 QA pairs whose answers live in earlier sessions.
- **Critiques:** small, mostly saturated. Avg length 9× shorter than LoCoMo; stress-tests persona consistency, not retention under volume.
- **Top results:** Zep 94.8 (GPT-4 Turbo) / 98.2 (GPT-4o-mini); MemGPT 93.4; LangChain conversational memory baseline ~60s.

### 5.4 NIAH — Needle in a Haystack

- **Citation:** Greg Kamradt, `gkamradt/LLMTest_NeedleInAHaystack`, Nov 2023. Not peer-reviewed.
- **What it measures:** inserts short fact at variable depth in long filler; sweeps depth 0–100% and length 1K–128K+. Accuracy heatmap.
- **Critique:** **NOT a memory test.** No write step, no eviction, no per-user partition. Misuse arises when vendors cite NIAH as evidence their memory system works. Saturated since 2024 — frontier models near-perfect to their advertised window.

### 5.5 RULER

- **Citation:** Hsieh et al., COLM 2024 (arxiv 2404.06654). NVIDIA.
- **What it measures:** 13 synthetic tasks in 4 categories (retrieval / multi-hop tracing / aggregation / QA), length 4K–128K+. Extends NIAH with multi-key, multi-value, multi-query variants. Exact-match accuracy.
- **Use:** long-context capacity check, not memory benchmark. Models claiming 32K often fail half RULER tasks at 32K.

### 5.6 InfiniteBench / ∞Bench

- **Citation:** Zhang et al., ACL 2024 (arxiv 2402.13718). OpenBMB.
- **12 tasks averaging 100K+ tokens** — KV retrieval, code debug, math finding, novel QA, summarization, dialogue. English + Chinese. Mix of synthetic + realistic.

### 5.7 HELMET

- **Citation:** Yen et al., ICLR 2025 (arxiv 2410.02694). Princeton PLI + Intel Labs.
- **7 task categories** — RAG, generation with citations, passage re-ranking, long-doc QA, many-shot ICL, summarization, synthetic recall. Length to 128K. Fixes NIAH/RULER complaints with model-based metrics and downstream-task relevance.

### 5.8 HotpotQA / 2WikiMultihopQA

Yang et al. EMNLP 2018; Ho et al. COLING 2020. Used by GraphRAG / Cognee / A-Mem as the **QA backend** once memory has populated a graph. Multi-hop factoid QA over Wikipedia. **Heavy contamination** — both datasets are in nearly every base LLM's pretraining.

### 5.9 PerLTQA

Du et al., SIGHAN 2024 (arxiv 2402.16288). 8,593 questions over 30 synthetic personal characters; both semantic and episodic memories. Three-stage eval: classification → retrieval → synthesis. Chinese-leaning.

### 5.10 LooGLE / LooGLE v2

Li et al., ACL 2024 (arxiv 2311.04939). 6,000 QA pairs over post-2022 documents averaging 24K+ tokens. Strict post-2022 cutoff to limit contamination. **LooGLE v2** (Oct 2025, arxiv 2510.22548) supersedes v1.

### 5.11 Other relevant benchmarks

- **BABILong** (Kuratov et al., NeurIPS 2024, arxiv 2406.10149) — 20 bAbI tasks embedded in PG19 text, scalable to 10M tokens. Shows LLMs only effectively use 10–20% of context.
- **BEAM** (Mem0 blog 2026) — explicitly tests forget/update.
- **HaluMem** (arxiv 2511.03506, 2025) — memory-induced hallucination: extraction accuracy, update consistency, QA hallucination rate.
- **LifeBench / MemoryArena / Mem2ActBench / EngramaBench / SocialMemBench** — newer 2025-2026 niche benchmarks.

### 5.12 Memory benchmarks ≠ long-context benchmarks

A long-context model reads everything in one pass — no eviction, no per-user partition, no token budget, no notion of "session 1 vs session 8". A memory system performs four operations: **write**, **update**, **retrieve under budget**, **forget**. NIAH, RULER, InfiniteBench, HELMET, BABILong, LooGLE all measure attention-over-fixed-input. LoCoMo, LongMemEval, MSC/DMR, PerLTQA, BEAM, HaluMem measure the four-op contract.

Practically: a system can score 95 on NIAH and still leak tenant A's preferences into tenant B's session, because NIAH never asked about isolation. Conversely a memory system can score 95 on LoCoMo and still fail at 1M-token recall because LoCoMo conversations fit fully in modern context windows. The two families are **orthogonal**.

### 5.13 Why LoCoMo J-score is controversial

Three compounding problems:
1. **Judge variance** — recent surveys (arxiv 2412.12509, 2512.16041) show GPT-5 / Gemini 2.5 Pro disagree with themselves on ~25% of hard cases when seeds change; position bias and verbosity bias inflate longer answers regardless of correctness.
2. **Vendor-influenced eval** — Mem0 paper reports Mem0 26% over OpenAI Memory; Zep re-ran same scripts and got Zep 75.14 vs Mem0's reported 65.99 (vs 79.09 in another setup). Prompt + judge config drive the gap as much as the underlying memory.
3. **Answer-key rot** — Penfield Labs audit found 6.4% of LoCoMo gold answers are wrong; judge accepts 63% of intentionally wrong answers. Two systems can show a 10-point J gap while solving the underlying memory problem identically.

The Mem0-vs-OpenAI-Memory comparison is specifically disputed because OpenAI Memory was tested through a chat UI proxy with non-controlled retrieval — not apples-to-apples.

### 5.14 The "right metric" debate

No single metric captures a memory system:
- **Recall** dominates academic leaderboards because it's easy to score, but a system that retrieves everything trivially maxes recall and bankrupts the token budget.
- **Precision / contradiction rate** punishes returning stale or conflicting facts — HaluMem is the first benchmark to formalize this.
- **Latency** is non-negotiable in production: Mem0 reports p95 0.20s search; anything >1s breaks chat UX.
- **Token cost** matters because a memory system injecting 26K tokens to score 95 is operationally worse than one injecting 2K to score 88.
- **Hallucination / staleness** — by Mem0's own reporting, hallucinations hold at 0.4–1.4% but transcript replay amplifies drift.

Emerging consensus in 2025-2026 (mem0 state-of-memory blog, Letta "Filesystem all you need", Zep enterprise pitch, Cognee head-to-head) is a **four-vector score**: accuracy × p95-latency × tokens-per-query × hallucination-rate. **No system dominates all four.** Papers reporting only one dimension are marketing.

---

## 6. Cross-system benchmark comparison

Only rows with a verifiable citation are included. **Numbers come from different evaluation harnesses and prompting setups — they are NOT directly comparable across rows without normalization.** Several papers (Zep, Mem0, Letta) have publicly disputed each other's numbers; both sides cited where relevant.

| System | LoCoMo | LongMemEval | Other | Source |
|---|---|---|---|---|
| Mem0 token-efficient (vendor) | **92.5 J** | — | p95 ~1.44s, ~7K tokens | mem0.ai/research |
| ByteRover 2.0 (vendor) | **92.2 J** | — | — | byterover.dev |
| MemMachine (vendor) | **84.87 J** | — | — | memmachine.ai (Sep 2025) |
| Memori (vendor) | **81.95 J** | — | — | memorilabs.ai/docs |
| Zep self-reported (paper) | **75.14 J** | **+18.5%** (gpt-4o), **+15.2%** (gpt-4o-mini) over baseline; **71.2%** with GPT-4o | DMR 94.8% (GPT-4 Turbo) / 98.2% (GPT-4o-mini) | arxiv 2501.13956 |
| Zep re-eval by Mem0 | **65.99 J** | — | — | arxiv 2504.19413 |
| Zep community re-eval | **58.44 acc** | — | — | getzep/zep-papers#5 |
| Mem0 Graph (vendor) | **68.4 J** | — | — | arxiv 2504.19413 |
| Mem0 paper main config | **51.15 J / 28.64 F1** | ~49% (third-party, GPT-4o) | p95 1.44s, ~7K tokens, ~91% latency drop vs full-context | arxiv 2504.19413 |
| Mem0 supermemory MemoryBench | **59.7 P@1, 83.5 Recall@10** | — | p50 <300ms | supermemory.ai |
| Letta / MemGPT (paper) | DMR 93.4% | — | (no headline LoCoMo number, per-task tables) | arxiv 2310.08560 |
| Letta filesystem (blog) | **74.0%** (GPT-4o-mini) | — | — | letta.com/blog |
| MemoryOS (BUPT) | **F1 = 53.5** (quality-gated, gpt-4o-mini); +49.11% F1 over GPT-4o-mini baseline | — | — | arxiv 2506.06326 |
| A-Mem | **F1 = 27.23** (raw, LoCoMo reader split); ROUGE-L 44.27 multi-hop | — | — | arxiv 2502.12110 |
| ReMe (AgentScope) | — | — | claimed SOTA on **BFCL-V3** and **AppWorld** | arxiv 2512.10696 |
| MemPalace (vendor, *user-specific*) | — | claimed **96.6%** raw / **100%** hybrid | — | mempalace.tech — *requires independent verification* |
| OMEGA | — | **95.4%** (GPT-4.1) | — | omegamax.co/benchmarks |
| Mastra Observational Memory | — | **94.87%** (GPT-5-mini) | — | mastra published |
| Emergence AI | — | **86%** | — | emergence.ai |
| EverMemOS | — | **83.0%** | — | published |
| TiMem | — | **76.88%** (GPT-4o-mini) | — | published |
| MemOS | — | — | **35.24%** token savings vs in-context | arxiv 2505.22101 |

**Systems without published LoCoMo / LongMemEval numbers as of May 2026:** Cognee, LangMem, Pinecone Assistant, Weaviate Engram, Qdrant, Redis Agent Memory Server, Chroma Cloud, OpenAI Memory (API side), Anthropic Memory Tool, txtai memory, Cloudflare Agent Memory.

---

## 7. Categories matrix (for L3 suite selection)

| Category | Representative system | License | Public bench? | Why include in L3 |
|---|---|---|---|---|
| Hierarchical / OS-style | **Letta** (Apache-2.0) | OSS + Cloud | MSC/DMR, LoCoMo (filesystem 74%) | Test paging contract, core/recall/archival blocks |
| Extract-update / vector-first | **Mem0** (Apache-2.0) | OSS + Cloud | LoCoMo 51-67 J (disputed) | Test extract→update→retrieve pipeline |
| Temporal Knowledge Graph | **Zep / Graphiti** (Apache-2.0 OSS for Graphiti, proprietary for Cloud) | Mixed | LoCoMo (disputed), LongMemEval +18.5%, DMR 94.8% | Test bi-temporal valid-from/valid-until contract |
| ECL multi-modal graph | **Cognee** (Apache-2.0) | OSS + Cloud | Own harness only | Test pluggable graph backend, multi-modal ingest |
| Zettelkasten / linked notes | **A-Mem** (research code) | OSS | LoCoMo F1 27.23 | Test typed-link evolution, note refinement |
| Procedural / experience-distillation | **ReMe (AgentScope)** (Apache-2.0) | OSS | BFCL-V3, AppWorld | Test multi-faceted experience extraction |
| Filesystem-native (markdown) | **Obsidian + PARA + MemPalace pattern**; jayzeng/agentmemory; Karpathy wiki | Freeware/MIT | None | Test plain-file substrate, git-friendly, replay-trivial |
| Framework-native (LangGraph) | **LangMem** (MIT) | OSS + Platform | Third-party only | Test the LangChain default path |
| Cloud-first managed | **supermemory** (source-available); **Cloudflare Agent Memory** (closed) | Mixed | LoCoMo (supermemory only) | Test the production-API contract |
| Code-as-graph (for coding agents) | **GitNexus** (PolyForm NC), **Graphify** (MIT), SCIP/Cody, CodeQL | Mixed | Self-benchmarks only | Test L3d (code retrieval over symbol graph) |
| Knowledge substrate / dev portal | **Backstage** (Apache-2.0) | OSS | None | Test L3c (catalog + docs as memory) |
| Issue + page aggregator | **Lantern** (vendor TBD) or Atlassian Rovo MCP / sooperset/mcp-atlassian | Unknown / MIT | None | Test L3b (work-context retrieval) |
| Contract-only (BYO storage) | **Anthropic memory tool** | API-included | None | Test the thinnest valid interface |
| Vector-DB substrate | Qdrant / Weaviate / Pinecone / Chroma / Redis 8 / Vectorize | Apache-2.0 / mixed | None | Used by other adapters; not a memory adapter itself |
| Observability (NOT memory) | Langfuse / Phoenix | OSS | N/A | Pair with memory; not a substitute |

---

## 8. Implications for L3 in agent-benchmarks

1. **At least one adapter per category.** Otherwise we are measuring a particular implementation, not a memory layer in general. Recommended starter set: Letta (hierarchical), Mem0 (extract-update), Zep/Graphiti (temporal KG), Obsidian + MemPalace pattern (filesystem), Anthropic memory tool (contract-only), GitNexus (code-as-graph).

2. **Decouple benchmark from adapter.** Tasks should target the four-op contract (`write` / `update` / `retrieve` / `forget`), not a vendor-friendly subset. Use a *blend* of LoCoMo + LongMemEval + a custom HaluMem-style hallucination metric + p95 latency + token cost — single-number leaderboards are the field's main failure mode.

3. **Replay-friendly is non-negotiable** (LSN-007). Each L3 test must be re-runnable from trajectory.jsonl alone. Filesystem-native adapters (Obsidian, agentmemory.md, Anthropic memory tool with disk backend) make this almost free. Cloud-only adapters (Zep Cloud, Mem0 Cloud, supermemory, Cloudflare Agent Memory) need explicit snapshot-export semantics or they fail this gate.

4. **Privacy boundary is harder for some adapters than others** (LSN-006). Obsidian / filesystem: trivial to scrub. Letta / Mem0 with shared cloud tenancy: harder. Cloudflare Agent Memory (Durable Objects): tenant isolation is platform-enforced but cross-DO leakage is a separate scorer category.

5. **Vendor benchmark numbers are not evidence.** The Mem0 ↔ Zep ↔ Letta cross-claims (66.9% / 75.14% / 74% / 58.44% on the *same benchmark*) demonstrate that any vendor-run LoCoMo number is one configuration of judge prompt + setup. L3 should mandate the eval be run inside the harness with a fixed judge spec and ship that spec in the trajectory.

6. **Stop calling NIAH a memory benchmark.** It's an attention test. If a vendor shows you NIAH heatmaps as evidence their memory system works, they are not engaging seriously.

7. **The "memory tool" contract by Anthropic is a useful spec.** It's a minimal interface (CRUD over `/memories`) that any backend can implement. This is the cleanest contract in the field as of 2026 and is a candidate model for the L3 adapter ABC.

---

## 9. Known unknowns / honest caveats

- **Lantern** (`mcp__lantern__*`): vendor not publicly identifiable. Recommend asking for vendor URL before publishing this row externally.
- **MemPalace as a public product**: not verified; treated as user-specific convention. The `mempalace.tech` LongMemEval score (96.6% raw / 100% hybrid) is **not independently audited** and one community issue (mempalace #29) has alleged the score is reproducible from a vanilla ChromaDB setup — flag.
- **Mem0 / Zep / supermemory LoCoMo numbers**: all vendor-reported on a benchmark with disputed methodology.
- **2026 product dates** (Cloudflare Agent Memory beta 2026-04-17, Backstage MCP plugin, Helicone maintenance mode) — drawn from research-agent output; verify each date against primary source before using in external publication.
- **Letta Cloud per-tier dollar pricing**: not enumerated in retrievable docs at report time.
- **Star counts and GitHub metrics**: snapshot in time; expect drift.

---

## 10. References (consolidated)

### Adapters covered
- Obsidian pricing: https://obsidian.md/pricing
- Obsidian Local REST API: https://github.com/coddingtonbear/obsidian-local-rest-api
- obsidian-mcp-tools: https://github.com/jacksteamdev/obsidian-mcp-tools
- mcp-obsidian (MarkusPfundstein): https://github.com/MarkusPfundstein/mcp-obsidian
- obsidian-mcp-server (cyanheads): https://github.com/cyanheads/obsidian-mcp-server
- PARA method: https://fortelabs.com/blog/para/
- Backstage repo: https://github.com/backstage/backstage
- Backstage CNCF status: https://www.cncf.io/projects/backstage/
- Spotify Portal MCP docs: https://backstage.spotify.com/docs/portal/core-features-and-plugins/mcp/
- Spotify x Anthropic agentic development: https://engineering.atspotify.com/2026/4/anthropic-agentic-development
- Backstage AI MCP integration (Hellgren): https://drodil.medium.com/backstage-meets-ai-the-mcp-integration-ba3c67e41e05
- GitNexus repo: https://github.com/abhigyanpatwari/GitNexus
- GitNexus npm: https://www.npmjs.com/package/gitnexus
- GitNexus benchmark: https://ilzam.dev/notes/gitnexus-codebase-rag-benchmark/
- GitNexus license issue: https://github.com/abhigyanpatwari/GitNexus/issues/735
- Graphify repo: https://github.com/safishamsi/graphify
- Graphify writeup: https://corti.com/graphify-bringing-knowledge-graphs-to-ai-assisted-engineering/
- Letta seed announcement: https://theaiinsider.tech/2024/09/26/berkeley-ai-research-lab-spinout-letta-raises-10m-seed-financing-led-by-felicis-to-build-ai-with-memory/
- Letta memory architecture: https://docs.letta.com/guides/core-concepts/memory/archival-memory
- Letta Aurora pgvector: https://aws.amazon.com/blogs/database/how-letta-builds-production-ready-ai-agents-with-amazon-aurora-postgresql/
- Letta filesystem 74% LoCoMo: https://www.letta.com/blog/benchmarking-ai-agent-memory
- MemGPT paper: https://arxiv.org/abs/2310.08560
- Letta LongMemEval issue: https://github.com/letta-ai/letta/issues/3115
- Mem0 paper: https://arxiv.org/abs/2504.19413
- Mem0 repo + license: https://github.com/mem0ai/mem0
- Mem0 MCP: https://github.com/mem0ai/mem0-mcp
- Mem0 vector DB matrix: https://docs.mem0.ai/components/vectordbs/overview
- Mem0 Series A: https://techcrunch.com/2025/10/28/mem0-raises-24m-from-yc-peak-xv-and-basis-set-to-build-the-memory-layer-for-ai-apps/
- Mem0 state-of-memory 2026: https://mem0.ai/blog/state-of-ai-agent-memory-2026
- Cloudflare Agents Memory docs: https://developers.cloudflare.com/agents/concepts/memory/
- Cloudflare Agent Memory blog: https://blog.cloudflare.com/introducing-agent-memory/
- InfoQ on Cloudflare beta: https://www.infoq.com/news/2026/04/cloudflare-agent-memory-beta/
- ReMe repo: https://github.com/agentscope-ai/ReMe
- ReMe paper: https://arxiv.org/abs/2512.10696
- jayzeng/agentmemory: https://github.com/jayzeng/agentmemory
- markdown-memory dev.to: https://dev.to/imaginex/ai-agent-memory-management-when-markdown-files-are-all-you-need-5ekk
- memweave TDS article: https://towardsdatascience.com/memweave-zero-infra-ai-agent-memory-with-markdown-and-sqlite-no-vector-database-required/
- supermemory pricing: https://supermemory.ai/pricing/
- supermemory repo: https://github.com/supermemoryai/supermemory
- supermemory TechCrunch: https://techcrunch.com/2025/10/06/a-19-year-old-nabs-backing-from-google-execs-for-his-ai-memory-startup-supermemory/

### Competitors
- Zep paper: https://arxiv.org/abs/2501.13956
- Zep "Is Mem0 SOTA" rebuttal: https://blog.getzep.com/lies-damn-lies-statistics-is-mem0-really-sota-in-agent-memory/
- Zep papers issue #5 (community re-eval): https://github.com/getzep/zep-papers/issues/5
- Zep pricing: https://www.getzep.com/pricing/
- Cognee repo: https://github.com/topoteretes/cognee
- Cognee AI memory evals (Aug 2025): https://www.cognee.ai/blog/deep-dives/ai-memory-evals-0825
- MemoryOS paper: https://arxiv.org/abs/2506.06326
- MemoryOS repo: https://github.com/BAI-LAB/MemoryOS
- A-Mem paper: https://arxiv.org/abs/2502.12110
- A-Mem repo: https://github.com/WujiangXu/A-mem
- LangMem docs: https://langchain-ai.github.io/langmem/
- LangMem launch blog: https://www.langchain.com/blog/langmem-sdk-launch
- LangGraph memory concepts: https://docs.langchain.com/oss/python/concepts/memory
- OpenAI ChatGPT Memory announcement: https://openai.com/index/memory-and-new-controls-for-chatgpt/
- Anthropic Memory Tool docs: https://platform.claude.com/docs/en/agents-and-tools/tool-use/memory-tool
- Claude Code memory docs: https://docs.anthropic.com/en/docs/claude-code/memory
- Pinecone Assistant GA: https://www.pinecone.io/blog/pinecone-assistant-generally-available/
- Weaviate Engram newsletter: https://newsletter.weaviate.io/p/the-limit-in-the-loop-why-agent-memory-needs-maintenance
- Redis 8 release: https://redis.io/blog/spring-release-2025/
- Redis Agent Memory Server: https://github.com/redis/agent-memory-server
- Vercel Storage overview (KV sunset): https://vercel.com/docs/storage
- MemOS short paper: https://arxiv.org/abs/2505.22101
- MemOS extended: https://arxiv.org/abs/2507.03724
- MemOS repo: https://github.com/MemTensor/MemOS
- Chroma pricing: https://www.trychroma.com/pricing

### Benchmarks
- LoCoMo paper: https://arxiv.org/abs/2402.17753
- LoCoMo site: https://snap-research.github.io/locomo/
- LoCoMo audit (Penfield Labs): https://dev.to/penfieldlabs/we-audited-locomo-64-of-the-answer-key-is-wrong-and-the-judge-accepts-up-to-63-of-intentionally-33lg
- LongMemEval paper: https://arxiv.org/abs/2410.10813
- LongMemEval site: https://xiaowu0162.github.io/long-mem-eval/
- LongMemEval leaderboard tracking (OMEGA): https://omegamax.co/benchmarks
- MSC paper: https://aclanthology.org/2022.acl-long.356/
- RULER paper: https://arxiv.org/abs/2404.06654
- InfiniteBench: https://arxiv.org/abs/2402.13718
- HELMET paper: https://arxiv.org/abs/2410.02694
- LooGLE: https://arxiv.org/abs/2311.04939
- LooGLE v2: https://arxiv.org/html/2510.22548
- PerLTQA: https://arxiv.org/abs/2402.16288
- BABILong: https://arxiv.org/abs/2406.10149
- HaluMem: https://arxiv.org/pdf/2511.03506
- LLM-judge reliability survey: https://arxiv.org/pdf/2412.12509

### Comparison / community
- Vectorize.io 2026 memory comparison: https://vectorize.io/articles/best-ai-agent-memory-systems
- n1n.ai agent memory comparison: https://explore.n1n.ai/blog/ai-agent-memory-comparison-2026-mem0-zep-letta-cognee-2026-04-23
- Atlan Zep vs Mem0: https://atlan.com/know/zep-vs-mem0/

---

*End of report. Word count ≈ 9,600. Update cadence: re-run when (a) Cloudflare Agent Memory exits private beta, (b) Letta publishes LongMemEval, (c) HaluMem is adopted by ≥2 vendors, (d) Lantern vendor identity is confirmed.*

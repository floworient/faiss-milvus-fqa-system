# RAG Knowledge QA Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将现有 FAQ 命令行原型升级为支持多格式摄取、Faiss + 关键词混合检索、多轮 Agent、SSE、三级降级和可复现评测的 FastAPI 模块化单体后端。

**Architecture:** FastAPI 作为唯一服务入口，应用工厂负责组合文档摄取、版本化索引、混合检索、会话、Prompt、Agent 与 LLM 路由。核心模块依赖端口而非 DashScope/LlamaIndex 全局对象，文件系统实现负责单机持久化，测试通过确定性 Fake Embedding/LLM 跑通完整链路。

**Tech Stack:** Python 3.10+、FastAPI、Pydantic Settings、LlamaIndex、Faiss、NumPy、DashScope、pytest、httpx、Uvicorn

**Spec:** `docs/superpowers/specs/2026-11-13-rag-knowledge-qa-upgrade-design.md`

## Global Constraints

- 保持 Python、FastAPI、LlamaIndex、Faiss 和 DashScope 技术栈，采用单进程模块化单体。
- 默认持久化根目录为 `data/runtime`，任何测试必须使用 `tmp_path`，不得改写仓库现有 `data/faiss_index` 和备份。
- 测试不得依赖公网或真实 API Key；Embedding、LLM、时钟和 ID 生成器必须可注入。
- 上传仅接受 `.txt`、`.md`、`.json`；JSON 轻量校验失败在任务创建前返回 HTTP 422。
- 混合检索以 chunk 为融合与评测单位；向量、关键词和混合模式必须共享稳定 Chunk ID。
- SSE 输出固定事件类型 `meta`、`retrieval`、`token`、`fallback`、`error`、`done`。
- 首版只面向开发机或受信任内网，不实现认证、多租户、Web 前端或完整 Plan-and-Execute。
- 不伪造 200 条评测集和 73%→85%+ 指标；README 必须将未复现数据标为目标/背景。
- 所有产品代码放入 `app/`；旧脚本在新流程验收完成前不删除，用户备份数据永不由迁移任务删除。

## Review Focus

- 恶意文件名、路径穿越和伪造扩展名：上传文件始终使用服务端 ID，非法类型在落盘前拒绝（Task 5 测试）。
- 空文档、超长段落和中文无空格文本：解析/分块不得产生空 chunk，关键词检索仍能召回（Task 2、Task 4 测试）。
- 索引构建中断或进程重启：旧索引继续可用，遗留任务变成可重试失败（Task 3、Task 5 测试）。
- 主模型已输出部分 token 后失败：不得拼接备用模型输出，残缺回答不得进入下一轮上下文（Task 8 测试）。
- 文档删除后的数据残留：活跃索引和原始文件移除，历史引用保留标识但不保留完整片段（Task 5、Task 8 测试）。

---

## File Structure

```text
app/
├── __init__.py
├── main.py                         # FastAPI 应用工厂与生命周期
├── api/
│   ├── dependencies.py             # 从 app.state 获取服务
│   ├── errors.py                   # 领域异常到 HTTP 的映射
│   ├── documents.py                # 文档与任务路由
│   ├── retrieval.py                # 检索调试路由
│   ├── chat.py                     # 非流式与 SSE 路由
│   ├── sessions.py                 # 会话查询与删除
│   └── evaluations.py              # JSONL 评测上传路由
├── core/
│   ├── config.py                   # Settings 与目录创建
│   ├── errors.py                   # 领域异常
│   ├── logging.py                  # request_id 与结构化日志
│   └── ids.py                      # 稳定/随机 ID 工具
├── domain/
│   ├── documents.py                # 文档、chunk、任务模型
│   ├── retrieval.py                # 候选、引用、检索结果模型
│   └── chat.py                     # 消息、回答、流事件模型
├── ingestion/
│   ├── parsers.py                  # TXT/Markdown/JSON 解析器注册表
│   ├── chunker.py                  # 自适应分块
│   └── service.py                  # 摄取/删除任务编排
├── retrieval/
│   ├── embeddings.py               # EmbeddingPort 与 DashScope 适配器
│   ├── vector.py                   # Faiss 查询与持久化
│   ├── keyword.py                  # 中文友好的 BM25 索引
│   ├── fusion.py                   # RRF
│   ├── repository.py               # 版本化索引原子发布
│   └── service.py                  # vector/keyword/hybrid 统一检索
├── memory/
│   ├── models.py                   # 会话存储模型
│   └── store.py                    # JSON 文件会话仓库
├── prompts/
│   ├── registry.py                 # 模板加载、变量校验与渲染
│   └── templates/contextual_rag_v1.txt
├── llm/
│   ├── ports.py                    # LLMPort、LLMEvent、错误类型
│   ├── dashscope.py                # DashScope 主/备用模型适配器
│   └── router.py                   # 三级降级
├── agents/
│   ├── base.py                     # AgentStrategy 协议
│   ├── registry.py                 # 策略注册表
│   └── contextual_rag.py           # 当前 RAG 策略
├── evaluation/
│   ├── models.py                   # JSONL 样本与结果
│   ├── runner.py                   # Hit@1、Recall@K、MRR
│   └── cli.py                      # 大数据集命令行入口
└── schemas/
    ├── documents.py
    ├── retrieval.py
    ├── chat.py
    └── evaluation.py
tests/
├── conftest.py                     # FakeEmbedding、FakeLLM 与应用 fixture
├── unit/
│   ├── test_config.py
│   ├── test_parsers.py
│   ├── test_chunker.py
│   ├── test_index_repository.py
│   ├── test_keyword_retriever.py
│   ├── test_fusion.py
│   ├── test_memory_store.py
│   ├── test_prompt_registry.py
│   ├── test_llm_router.py
│   └── test_evaluation.py
├── integration/
│   ├── test_documents_api.py
│   ├── test_retrieval_api.py
│   ├── test_chat_api.py
│   └── test_evaluation_api.py
└── fixtures/
    ├── knowledge.md
    └── evaluation.jsonl
docs/image/
├── rag-qa-logo.svg
└── rag-qa-architecture.svg
```

### Task 1: Application foundation and dependency seams

**Files:**
- Create: `pyproject.toml`
- Create: `.env.example`
- Create: `app/__init__.py`
- Create: `app/main.py`
- Create: `app/core/config.py`
- Create: `app/core/errors.py`
- Create: `app/core/ids.py`
- Create: `app/api/errors.py`
- Create: `tests/conftest.py`
- Create: `tests/unit/test_config.py`
- Modify: `requirements.txt`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: none.
- Produces: `Settings(data_dir: Path, upload_max_bytes: int, chunk_min_tokens: int, chunk_max_tokens: int, chunk_overlap_ratio: float, retrieval_top_k: int, retrieval_candidate_k: int)`; `create_app(settings: Settings | None = None, services: ServiceContainer | None = None) -> FastAPI`; `new_id(prefix: str) -> str`; `AppError(code: str, message: str, status_code: int, details: dict | None = None)`.

- [ ] **Step 1: Write failing configuration and health tests**

  Add `test_settings_create_runtime_directories`, `test_settings_reject_overlap_outside_0_to_0_5`, and an async app test asserting `GET /health` returns `200`, `status="ok"`, and a `request_id` header.

- [ ] **Step 2: Run tests and verify failure**

  Run: `pytest tests/unit/test_config.py -q`
  Expected: FAIL because `app.core.config` and `create_app` do not exist.

- [ ] **Step 3: Implement the application foundation**

  Add Pydantic Settings with the exact fields above, an application factory, request-ID middleware, domain error handler, `/health`, directory creation under `data_dir`, and a typed `ServiceContainer` placeholder. Update dependencies with `pydantic-settings`, `python-multipart`, `pytest`, `pytest-asyncio`, and compatible FastAPI/httpx floors; configure pytest in `pyproject.toml`.

- [ ] **Step 4: Run foundation tests**

  Run: `pytest tests/unit/test_config.py -q`
  Expected: all PASS.

- [ ] **Step 5: Commit**

  ```bash
  git add pyproject.toml requirements.txt .env.example .gitignore app tests/conftest.py tests/unit/test_config.py
  git commit -m "build: establish FastAPI application foundation"
  ```

### Task 2: Document models, parsers, and adaptive chunking

**Files:**
- Create: `app/domain/documents.py`
- Create: `app/ingestion/parsers.py`
- Create: `app/ingestion/chunker.py`
- Create: `tests/unit/test_parsers.py`
- Create: `tests/unit/test_chunker.py`

**Interfaces:**
- Consumes: `Settings` from Task 1.
- Produces: `ParsedDocument(document_id: str, source_name: str, title: str | None, text: str, metadata: dict[str, Any])`; `Chunk(chunk_id: str, document_id: str, text: str, position: int, token_count: int, metadata: dict[str, Any])`; `ParserRegistry.validate(filename: str, content: bytes) -> str`; `ParserRegistry.parse(document_id: str, filename: str, content: bytes) -> list[ParsedDocument]`; `AdaptiveChunker.split(document: ParsedDocument) -> list[Chunk]`.

- [ ] **Step 1: Write failing parser tests**

  Cover UTF-8 TXT, Markdown title/section preservation, FAQ JSON arrays, top-level `text`/`content`, object arrays, malformed JSON, unsupported shape, unsupported suffix, empty content, and a client filename containing `../`. Assert invalid JSON/shape raises `DocumentValidationError(code="invalid_json_document")` before parsing tasks exist.

- [ ] **Step 2: Run parser tests and verify failure**

  Run: `pytest tests/unit/test_parsers.py -q`
  Expected: FAIL because parser types are missing.

- [ ] **Step 3: Implement parser registry**

  Use LlamaIndex `Document` only as an internal parser interoperability type where useful; never modify global `Settings`. Normalize client filenames to display-only basenames and generate no filesystem path from them.

- [ ] **Step 4: Run parser tests**

  Run: `pytest tests/unit/test_parsers.py -q`
  Expected: all PASS.

- [ ] **Step 5: Write failing adaptive chunker tests**

  Add tests asserting: short documents yield one non-empty chunk; Markdown headings stay in metadata; a long paragraph yields chunks within `256..768` configured token bounds except the final remainder; adjacent chunks overlap; Chinese text without spaces splits deterministically; identical source/content/config produces stable IDs; empty sections never produce chunks.

- [ ] **Step 6: Run chunker tests and verify failure**

  Run: `pytest tests/unit/test_chunker.py -q`
  Expected: FAIL because `AdaptiveChunker` is missing.

- [ ] **Step 7: Implement adaptive chunking**

  Implement `AdaptiveChunker(settings: Settings, tokenizer: TokenizerPort)` with paragraph/heading boundaries first, sentence boundaries second, token windows last. Derive ID from source identity + document content digest + `chunker-v1` + position.

- [ ] **Step 8: Run parser and chunker tests**

  Run: `pytest tests/unit/test_parsers.py tests/unit/test_chunker.py -q`
  Expected: all PASS.

- [ ] **Step 9: Commit**

  ```bash
  git add app/domain/documents.py app/ingestion tests/unit/test_parsers.py tests/unit/test_chunker.py
  git commit -m "feat: add multi-format parsing and adaptive chunking"
  ```

### Task 3: Versioned Faiss and keyword index repository

**Files:**
- Create: `app/retrieval/embeddings.py`
- Create: `app/retrieval/vector.py`
- Create: `app/retrieval/keyword.py`
- Create: `app/retrieval/repository.py`
- Create: `tests/unit/test_index_repository.py`
- Create: `tests/unit/test_keyword_retriever.py`

**Interfaces:**
- Consumes: `Chunk` from Task 2 and `Settings` from Task 1.
- Produces: `EmbeddingPort.embed_texts(texts: Sequence[str]) -> ndarray`; `EmbeddingPort.embed_query(text: str) -> ndarray`; `DashScopeEmbeddingAdapter`; `FaissIndex.build(chunks: Sequence[Chunk], vectors: ndarray) -> FaissIndex`; `FaissIndex.search(vector: ndarray, limit: int) -> list[RankedChunk]`; `KeywordIndex.build(chunks: Sequence[Chunk]) -> KeywordIndex`; `KeywordIndex.search(query: str, limit: int) -> list[RankedChunk]`; `IndexRepository.publish(chunks: Sequence[Chunk], vectors: ndarray) -> str`; `IndexRepository.load_active() -> IndexSnapshot`; `IndexRepository.remove_document(document_id: str, vectors: ndarray) -> str`.

- [ ] **Step 1: Write failing keyword-index tests**

  Assert Chinese character n-grams recall `如何办理退货` for query `退货`, English token search works, empty queries return `[]`, empty/duplicate chunks do not crash, and results expose rank, score, chunk ID, and source metadata.

- [ ] **Step 2: Run keyword tests and verify failure**

  Run: `pytest tests/unit/test_keyword_retriever.py -q`
  Expected: FAIL because `KeywordIndex` does not exist.

- [ ] **Step 3: Implement the keyword index**

  Implement BM25 scoring over lowercase Latin tokens plus Chinese character bigrams, persist corpus metadata as JSON, and keep stable ordering by `chunk_id` for score ties.

- [ ] **Step 4: Run keyword tests**

  Run: `pytest tests/unit/test_keyword_retriever.py -q`
  Expected: all PASS.

- [ ] **Step 5: Write failing repository tests**

  Assert `faiss.IndexFlatIP` uses normalized vectors, publish creates an immutable version directory and atomically switches `ACTIVE`, a simulated write failure leaves the previous snapshot queryable, missing active index returns an empty snapshot, an interrupted `*.staging` directory is ignored, and publication metadata includes schema/chunker versions.

- [ ] **Step 6: Run repository tests and verify failure**

  Run: `pytest tests/unit/test_index_repository.py -q`
  Expected: FAIL because repository/vector classes are missing.

- [ ] **Step 7: Implement versioned repository**

  Persist `faiss.index`, `chunks.json`, `keyword.json`, and `manifest.json` under `indexes/<version>/`; publish via a same-filesystem temporary directory plus atomic `ACTIVE` replacement. Never read or overwrite legacy `data/faiss_index`.

- [ ] **Step 8: Run index tests**

  Run: `pytest tests/unit/test_keyword_retriever.py tests/unit/test_index_repository.py -q`
  Expected: all PASS.

- [ ] **Step 9: Commit**

  ```bash
  git add app/retrieval tests/unit/test_keyword_retriever.py tests/unit/test_index_repository.py
  git commit -m "feat: add versioned Faiss and keyword indexes"
  ```

### Task 4: Hybrid retrieval and RRF fusion

**Files:**
- Create: `app/domain/retrieval.py`
- Create: `app/retrieval/fusion.py`
- Create: `app/retrieval/service.py`
- Create: `app/schemas/retrieval.py`
- Create: `app/api/retrieval.py`
- Create: `tests/unit/test_fusion.py`
- Create: `tests/integration/test_retrieval_api.py`
- Modify: `app/main.py`

**Interfaces:**
- Consumes: `IndexRepository`, `EmbeddingPort`, `RankedChunk` from Task 3.
- Produces: `reciprocal_rank_fusion(result_sets: Sequence[Sequence[RankedChunk]], k: int = 60) -> list[RankedChunk]`; `RetrievalService.search(query: str, mode: Literal["vector", "keyword", "hybrid"], top_k: int, candidate_k: int) -> RetrievalResult`; `POST /api/v1/retrieval/search`.

- [ ] **Step 1: Write failing RRF tests**

  Assert score equals the sum of `1/(60+rank)`, duplicate chunk IDs merge, deterministic ties sort by chunk ID, and different chunks from one document remain eligible.

- [ ] **Step 2: Run fusion tests and verify failure**

  Run: `pytest tests/unit/test_fusion.py -q`
  Expected: FAIL because fusion is missing.

- [ ] **Step 3: Implement fusion and retrieval service**

  Vector mode calls only embedding/Faiss; keyword mode never calls embedding; hybrid catches query-embedding provider errors and returns keyword results with `degraded_from="hybrid"` and a safe reason code.

- [ ] **Step 4: Run fusion tests**

  Run: `pytest tests/unit/test_fusion.py -q`
  Expected: all PASS.

- [ ] **Step 5: Write failing retrieval API tests**

  Cover all three modes, invalid mode/`top_k`, missing index, hybrid query-embedding outage, and response fields for vector rank, keyword rank, fusion score, source, position, and degradation metadata.

- [ ] **Step 6: Run API tests and verify failure**

  Run: `pytest tests/integration/test_retrieval_api.py -q`
  Expected: FAIL because route/schema are missing.

- [ ] **Step 7: Implement retrieval API**

  Add dependency lookup from `app.state.services`, schemas, route registration, and domain-to-HTTP error mapping.

- [ ] **Step 8: Run retrieval tests**

  Run: `pytest tests/unit/test_fusion.py tests/integration/test_retrieval_api.py -q`
  Expected: all PASS.

- [ ] **Step 9: Commit**

  ```bash
  git add app/domain/retrieval.py app/retrieval/fusion.py app/retrieval/service.py app/schemas/retrieval.py app/api/retrieval.py app/main.py tests/unit/test_fusion.py tests/integration/test_retrieval_api.py
  git commit -m "feat: expose hybrid retrieval with RRF fusion"
  ```

### Task 5: Durable ingestion tasks and document API

**Files:**
- Create: `app/ingestion/service.py`
- Create: `app/schemas/documents.py`
- Create: `app/api/documents.py`
- Create: `tests/integration/test_documents_api.py`
- Modify: `app/domain/documents.py`
- Modify: `app/main.py`

**Interfaces:**
- Consumes: `ParserRegistry`, `AdaptiveChunker`, `EmbeddingPort`, `IndexRepository`.
- Produces: `IngestionService.create_upload(filename: str, content: bytes) -> IngestionTask`; `IngestionService.run(task_id: str) -> None`; `IngestionService.create_delete(document_id: str) -> IngestionTask`; `TaskStore.get(task_id: str) -> IngestionTask`; `POST/GET/DELETE /api/v1/documents...` and `GET /api/v1/tasks/{task_id}`.

- [ ] **Step 1: Write failing upload API tests**

  Assert valid uploads return `202` and persisted `task_id`; malformed JSON, empty file, oversized file, fake suffix, and traversal filename return 4xx before writing content; original files are stored as `<document_id>.source`; successful task publishes both indexes and manifest; failed embedding leaves old active index unchanged.

- [ ] **Step 2: Run upload tests and verify failure**

  Run: `pytest tests/integration/test_documents_api.py -q`
  Expected: FAIL because ingestion routes/services are missing.

- [ ] **Step 3: Implement durable upload tasks**

  Persist each task as JSON before scheduling FastAPI `BackgroundTasks`. On application startup, mark prior `pending`/`running` as `failed` with `code="interrupted_by_restart"` and `retryable=true`.

- [ ] **Step 4: Run upload tests**

  Run: `pytest tests/integration/test_documents_api.py -q`
  Expected: upload and restart cases PASS.

- [ ] **Step 5: Add failing deletion and retention tests**

  Assert delete returns `202`; success removes chunks from both indexes and deletes `<document_id>.source`; failure preserves the old active index; document list excludes deleted item; a retained citation record contains source ID/name and `deleted=true` but no full chunk text.

- [ ] **Step 6: Implement asynchronous deletion**

  Rebuild the next snapshot from remaining chunks, publish it, update manifest, remove source, then mark task successful. If any pre-publication action fails, retain old active version and source.

- [ ] **Step 7: Run document API tests**

  Run: `pytest tests/integration/test_documents_api.py -q`
  Expected: all PASS.

- [ ] **Step 8: Commit**

  ```bash
  git add app/ingestion/service.py app/domain/documents.py app/schemas/documents.py app/api/documents.py app/main.py tests/integration/test_documents_api.py
  git commit -m "feat: add durable document ingestion tasks"
  ```

### Task 6: Conversation memory and Prompt registry

**Files:**
- Create: `app/memory/models.py`
- Create: `app/memory/store.py`
- Create: `app/prompts/registry.py`
- Create: `app/prompts/templates/contextual_rag_v1.txt`
- Create: `tests/unit/test_memory_store.py`
- Create: `tests/unit/test_prompt_registry.py`

**Interfaces:**
- Consumes: `Settings`, `new_id`.
- Produces: `Message(role: Literal["user", "assistant"], content: str, status: Literal["complete", "failed"], citations: list[Citation], metadata: dict)`; `FileConversationStore.create() -> Conversation`; `append_user(session_id: str, content: str) -> Message`; `append_assistant(...) -> Message`; `history_for_prompt(session_id: str, max_chars: int, max_turns: int) -> list[Message]`; `PromptRegistry.render(name: str, version: str, variables: Mapping[str, str]) -> str`.

- [ ] **Step 1: Write failing memory tests**

  Assert atomic JSON persistence, stable session lookup, max-turn/max-character pruning from oldest complete turns, failed assistant text excluded from prompt history, user message preceding a failed stream retained, and deletion removes the session file.

- [ ] **Step 2: Run memory tests and verify failure**

  Run: `pytest tests/unit/test_memory_store.py -q`
  Expected: FAIL because memory store is missing.

- [ ] **Step 3: Implement file conversation store**

  Use per-session JSON with temporary-file replacement and a process-local lock per session; store citation metadata but no deleted-source full text.

- [ ] **Step 4: Run memory tests**

  Run: `pytest tests/unit/test_memory_store.py -q`
  Expected: all PASS.

- [ ] **Step 5: Write failing Prompt tests**

  Assert template version lookup, required variables `question`, `history`, `context`, explicit “仅依据上下文/不确定时说明” policy, safe literal handling of braces in user content, and startup failure for missing variables.

- [ ] **Step 6: Implement Prompt registry and template**

  Parse a small YAML-like metadata header or adjacent Python declaration, but expose only the `render` interface above; user values are substitutions, never parsed as template syntax.

- [ ] **Step 7: Run memory and Prompt tests**

  Run: `pytest tests/unit/test_memory_store.py tests/unit/test_prompt_registry.py -q`
  Expected: all PASS.

- [ ] **Step 8: Commit**

  ```bash
  git add app/memory app/prompts tests/unit/test_memory_store.py tests/unit/test_prompt_registry.py
  git commit -m "feat: add conversation memory and prompt registry"
  ```

### Task 7: Tiered LLM routing and provider adapters

**Files:**
- Create: `app/llm/ports.py`
- Create: `app/llm/dashscope.py`
- Create: `app/llm/router.py`
- Create: `tests/unit/test_llm_router.py`
- Modify: `app/core/config.py`
- Modify: `.env.example`

**Interfaces:**
- Consumes: rendered Prompt and `Citation` list.
- Produces: `LLMPort.complete(prompt: str) -> str`; `LLMPort.stream(prompt: str) -> AsyncIterator[str]`; `TieredLLMRouter.complete(prompt: str, citations: Sequence[Citation]) -> GenerationResult`; `TieredLLMRouter.stream(...) -> AsyncIterator[LLMEvent]`; `LLMEvent(type: Literal["token", "fallback", "error", "done"], data: dict)`.

- [ ] **Step 1: Write failing non-stream fallback tests**

  Assert primary success uses tier 1; timeout/rate-limit/provider error switches once to tier 2; invalid request does not retry; both failures return deterministic retrieval summary with tier 3 and citations; logs/metadata contain safe reason codes but no API key or prompt.

- [ ] **Step 2: Run router tests and verify failure**

  Run: `pytest tests/unit/test_llm_router.py -q`
  Expected: FAIL because LLM ports/router are missing.

- [ ] **Step 3: Implement non-stream router and DashScope adapters**

  Map provider exceptions to `LLMTimeout`, `LLMRateLimited`, `LLMUnavailable`, or `LLMInvalidRequest`; make primary and backup independently configurable so they may use different providers/models.

- [ ] **Step 4: Add failing streaming tests**

  Assert failure before first token emits `fallback` then backup tokens; failure after first token emits `error` then `done(status="failed")` and never calls backup; tier-3 stream emits a fallback event, summary tokens, and done.

- [ ] **Step 5: Implement streaming state machine**

  Track whether any token was emitted; only pre-token retry/fallback is allowed.

- [ ] **Step 6: Run router tests**

  Run: `pytest tests/unit/test_llm_router.py -q`
  Expected: all PASS.

- [ ] **Step 7: Commit**

  ```bash
  git add app/llm app/core/config.py .env.example tests/unit/test_llm_router.py
  git commit -m "feat: add tiered model fallback routing"
  ```

### Task 8: Agent strategy, chat API, SSE, and sessions

**Files:**
- Create: `app/agents/base.py`
- Create: `app/agents/registry.py`
- Create: `app/agents/contextual_rag.py`
- Create: `app/domain/chat.py`
- Create: `app/schemas/chat.py`
- Create: `app/api/chat.py`
- Create: `app/api/sessions.py`
- Create: `tests/integration/test_chat_api.py`
- Modify: `app/main.py`

**Interfaces:**
- Consumes: `RetrievalService`, `PromptRegistry`, `FileConversationStore`, `TieredLLMRouter`.
- Produces: `AgentStrategy.run(request: AgentRequest) -> AgentResponse`; `AgentStrategy.stream(request: AgentRequest) -> AsyncIterator[AgentEvent]`; `AgentRegistry.get(name: str) -> AgentStrategy`; `POST /api/v1/chat/completions`; `POST /api/v1/chat/completions/stream`; `GET/DELETE /api/v1/sessions/{session_id}`.

- [ ] **Step 1: Write failing non-stream chat tests**

  Assert new/existing sessions, retrieval citations, history passed to Prompt, tier metadata, keyword fallback when embedding fails, tier-3 answer when generation fails, unknown strategy rejected, and Plan-and-Execute absent from the registered strategy list.

- [ ] **Step 2: Run chat tests and verify failure**

  Run: `pytest tests/integration/test_chat_api.py -q`
  Expected: FAIL because Agent/chat routes are missing.

- [ ] **Step 3: Implement strategy and non-stream endpoint**

  `ContextualRAGStrategy` performs optional rewrite, retrieval, Prompt render, generation, citation assembly, then persists a complete turn. Rewrite failure uses original query.

- [ ] **Step 4: Add failing SSE protocol tests**

  Parse the event stream and assert exact order `meta → retrieval → token* → done`; pre-token fallback adds `fallback`; post-token failure ends `error → done(status="failed")`; every event is valid JSON; failed partial assistant text is stored for audit but excluded from the next Prompt.

- [ ] **Step 5: Implement SSE endpoint**

  Use FastAPI `StreamingResponse(media_type="text/event-stream")`; serialize named events as `event: <type>\ndata: <json>\n\n`; add no-buffer/cache headers and stop work on client cancellation where possible.

- [ ] **Step 6: Add failing session API tests**

  Assert GET returns safe history and citation metadata, deleted source citations expose `deleted=true` without text, DELETE removes session, and unknown session returns 404.

- [ ] **Step 7: Implement session routes and register all routers**

  Wire the concrete service graph in `create_app` without module-level global LlamaIndex settings.

- [ ] **Step 8: Run chat/session tests**

  Run: `pytest tests/integration/test_chat_api.py -q`
  Expected: all PASS.

- [ ] **Step 9: Commit**

  ```bash
  git add app/agents app/domain/chat.py app/schemas/chat.py app/api/chat.py app/api/sessions.py app/main.py tests/integration/test_chat_api.py
  git commit -m "feat: add contextual RAG chat and SSE streaming"
  ```

### Task 9: Retrieval evaluation API and CLI

**Files:**
- Create: `app/evaluation/models.py`
- Create: `app/evaluation/runner.py`
- Create: `app/evaluation/cli.py`
- Create: `app/schemas/evaluation.py`
- Create: `app/api/evaluations.py`
- Create: `tests/unit/test_evaluation.py`
- Create: `tests/integration/test_evaluation_api.py`
- Create: `tests/fixtures/evaluation.jsonl`
- Modify: `app/main.py`
- Modify: `pyproject.toml`

**Interfaces:**
- Consumes: `RetrievalService.search` from Task 4.
- Produces: `EvaluationRunner.run(samples: Sequence[EvaluationSample], mode: RetrievalMode, top_k: int) -> EvaluationReport`; `load_jsonl(stream: TextIO) -> list[EvaluationSample]`; CLI `rag-eval --dataset PATH --mode hybrid --top-k 5`; `POST /api/v1/evaluations/retrieval` multipart endpoint.

- [ ] **Step 1: Write failing metric tests**

  Use a fixed three-query ranking and assert exact `hit_at_1`, `recall_at_k`, `mrr`, query count, per-query ranks, mode, `top_k`, and configuration snapshot. Assert chunk labels are primary and document-only labels match any returned chunk from that document.

- [ ] **Step 2: Run evaluation tests and verify failure**

  Run: `pytest tests/unit/test_evaluation.py -q`
  Expected: FAIL because runner is missing.

- [ ] **Step 3: Implement JSONL loader and metrics**

  Reject blank/malformed rows with line numbers; accept optional `reference_answer` and `human_correct` but do not synthesize answer accuracy when labels are absent.

- [ ] **Step 4: Run metric tests**

  Run: `pytest tests/unit/test_evaluation.py -q`
  Expected: all PASS.

- [ ] **Step 5: Write failing API/CLI tests**

  Assert multipart JSONL upload returns the same report as the CLI runner; invalid JSONL returns 422 with a line number; `top_k` bounds are enforced; response never claims a 200-sample or 85% result for the fixture.

- [ ] **Step 6: Implement API and CLI adapters**

  Keep small API runs synchronous; document CLI as the path for larger datasets.

- [ ] **Step 7: Run evaluation tests**

  Run: `pytest tests/unit/test_evaluation.py tests/integration/test_evaluation_api.py -q`
  Expected: all PASS.

- [ ] **Step 8: Commit**

  ```bash
  git add app/evaluation app/schemas/evaluation.py app/api/evaluations.py app/main.py tests/unit/test_evaluation.py tests/integration/test_evaluation_api.py tests/fixtures/evaluation.jsonl pyproject.toml
  git commit -m "feat: add reproducible retrieval evaluation"
  ```

### Task 10: Integration fixture, smoke path, and observability hardening

**Files:**
- Create: `app/core/logging.py`
- Create: `tests/fixtures/knowledge.md`
- Create: `tests/integration/test_end_to_end.py`
- Create: `scripts/smoke_test.py`
- Modify: `app/main.py`
- Modify: `app/ingestion/service.py`
- Modify: `app/retrieval/service.py`
- Modify: `app/llm/router.py`

**Interfaces:**
- Consumes: all product interfaces from Tasks 1–9.
- Produces: `configure_logging(level: str) -> None`; runnable `python scripts/smoke_test.py --base-url http://127.0.0.1:8000`.

- [ ] **Step 1: Write failing end-to-end test**

  With Fake Embedding/LLM, upload Markdown, wait for task success, search hybrid, run non-stream chat, parse SSE, evaluate fixture, delete document, and verify subsequent retrieval excludes it. Assert request/task/session IDs appear in structured log records while API keys, full Prompt, and uploaded full text do not.

- [ ] **Step 2: Run end-to-end test and verify failure**

  Run: `pytest tests/integration/test_end_to_end.py -q`
  Expected: FAIL on missing logging/smoke integration.

- [ ] **Step 3: Implement structured logging and smoke client**

  Emit JSON logs for request, ingestion stage, retrieval stage, fallback and completion with safe IDs/durations/reason codes. Smoke client must use only public HTTP APIs and exit non-zero on any failed assertion.

- [ ] **Step 4: Run complete automated suite**

  Run: `pytest -q`
  Expected: all PASS with no network/API key.

- [ ] **Step 5: Run static/import checks**

  Run: `python -m compileall app scripts tests`
  Expected: exit 0 and no syntax errors.

- [ ] **Step 6: Commit**

  ```bash
  git add app/core/logging.py app/main.py app/ingestion/service.py app/retrieval/service.py app/llm/router.py tests/fixtures/knowledge.md tests/integration/test_end_to_end.py scripts/smoke_test.py
  git commit -m "test: cover complete RAG backend workflow"
  ```

### Task 11: Brand assets and architecture documentation

**Files:**
- Create: `docs/image/rag-qa-logo.svg`
- Create: `docs/image/rag-qa-architecture.svg`
- Create: `docs/architecture.md`
- Create: `tests/test_docs_assets.py`

**Interfaces:**
- Consumes: actual module and API names implemented in Tasks 1–10.
- Produces: version-controlled SVG Logo/architecture diagram referenced by README.

- [ ] **Step 1: Write failing asset validation tests**

  Assert both SVGs parse as XML, have `viewBox`, accessible `<title>`, no embedded remote resources/scripts, and architecture labels include FastAPI, Ingestion, Faiss, Keyword/BM25, RRF, Agent, Memory, Tiered LLM and Evaluation.

- [ ] **Step 2: Run asset tests and verify failure**

  Run: `pytest tests/test_docs_assets.py -q`
  Expected: FAIL because assets do not exist.

- [ ] **Step 3: Create SVG assets**

  Create a compact RAG/network motif Logo that works on light and dark README backgrounds and a truthful left-to-right architecture diagram. Use SVG-native shapes/text so assets remain editable and do not require external fonts or raster generation.

- [ ] **Step 4: Write architecture document**

  Explain service boundaries, ingestion publication, query/fallback flow, persistence layout, trust boundary and known single-process limitations; link to the design spec rather than duplicating it.

- [ ] **Step 5: Run asset tests**

  Run: `pytest tests/test_docs_assets.py -q`
  Expected: all PASS.

- [ ] **Step 6: Commit**

  ```bash
  git add docs/image docs/architecture.md tests/test_docs_assets.py
  git commit -m "docs: add RAG project brand and architecture assets"
  ```

### Task 12: Preview-quality README and legacy transition

**Files:**
- Create: `README.md`
- Modify: `INSTALL_TROUBLESHOOTING.md`
- Create: `tests/test_readme_commands.py`

**Interfaces:**
- Consumes: all final commands, routes, assets and verified behavior.
- Produces: truthful Chinese project README, deprecation notices for legacy entry points, verified setup/start/test/evaluation examples.

- [ ] **Step 1: Write failing README checks**

  Assert README links both `docs/image` assets, contains “开发预览版”, lists implemented vs planned capabilities, warns against public unauthenticated exposure, describes no-key tests and DashScope runtime separately, documents OpenAPI/SSE/evaluation commands, and does not state 73%→85%+ as an already reproduced fact.

- [ ] **Step 2: Run README tests and verify failure**

  Run: `pytest tests/test_readme_commands.py -q`
  Expected: FAIL because root README is absent.

- [ ] **Step 3: Write README following the approved information hierarchy**

  Include brand header/badges, preview warning, overview, capabilities table, architecture, module tree, technology, quick start, API/curl examples, SSE event contract, evaluation, project status, roadmap, documentation, security and license-status note. Use commands that were actually verified in Tasks 9–10.

- [ ] **Step 4: Document the legacy transition**

  Keep user data untouched. Explain that the old root scripts were removed by explicit user decision, point to `uvicorn app.main:create_app --factory`, and describe old index incompatibility in the troubleshooting document.

- [ ] **Step 5: Verify README commands and links**

  Run: `pytest tests/test_readme_commands.py tests/test_docs_assets.py -q`
  Expected: all PASS.

- [ ] **Step 6: Run final verification**

  Run: `pytest -q`
  Expected: all PASS.

  Run: `python -m compileall app scripts tests`
  Expected: exit 0.

  Run: `git diff --check`
  Expected: no output, exit 0.

- [ ] **Step 7: Commit**

  ```bash
  git add README.md INSTALL_TROUBLESHOOTING.md tests/test_readme_commands.py
  git commit -m "docs: publish development-preview project guide"
  ```

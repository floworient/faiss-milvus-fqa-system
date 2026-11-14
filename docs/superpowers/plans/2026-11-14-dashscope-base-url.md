# DashScope Base URL Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one validated `RAG_DASHSCOPE_BASE_URL` setting, including the required `/api/v1` path, and use it for both LLM and Embedding requests.

**Architecture:** `Settings` owns the complete DashScope native API base URL. LLM adapters pass it as DashScope SDK `base_address` on every synchronous and streaming request; the LlamaIndex embedding wrapper cannot accept that parameter, so its adapter configures the same DashScope SDK HTTP base before constructing the wrapper.

**Tech Stack:** Python, Pydantic Settings, DashScope SDK, LlamaIndex, pytest

**Spec:** `docs/superpowers/specs/2026-11-14-dashscope-base-url-design.md`

## Global Constraints

- The default is exactly `https://dashscope.aliyuncs.com/api/v1`.
- The environment variable is `RAG_DASHSCOPE_BASE_URL`.
- The value is a complete HTTP(S) base URL; never append `/v1` or `/api/v1` automatically.
- Remove only trailing `/` characters before passing the value downstream.
- Keep one shared setting for LLM and Embedding.

## Review Focus

- A trailing slash must not produce a doubled separator in SDK requests; Task 1 tests normalization.
- An invalid non-HTTP URL must fail settings validation; Task 1 tests rejection.
- Sync and streaming LLM paths could diverge; Task 2 tests each path separately.
- The LlamaIndex wrapper does not forward arbitrary constructor kwargs to DashScope calls; Task 2 tests the SDK global used by the wrapper.
- Existing installations without the new environment variable must continue to use the official endpoint; Task 1 tests the default.

---

### Task 1: Validated DashScope URL configuration

**Files:**
- Modify: `app/core/config.py`
- Modify: `tests/unit/test_config.py`

**Interfaces:**
- Produces: `Settings.dashscope_base_url: HttpUrl`, whose string form has no trailing slash.

- [ ] **Step 1: Write failing configuration tests**

Add tests asserting the official default, environment override normalization, and rejection of an `ftp://` value. Disable repository `.env` loading in these focused tests with `_env_file=None`.

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m pytest tests/unit/test_config.py -q`
Expected: FAIL because `dashscope_base_url` does not exist.

- [ ] **Step 3: Implement the setting and normalization**

Add `dashscope_base_url` to `Settings`, validate it as HTTP(S), and normalize only trailing slashes while preserving `/api/v1` or any custom path.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `python -m pytest tests/unit/test_config.py -q`
Expected: PASS.

### Task 2: Provider wiring and operator documentation

**Files:**
- Modify: `app/llm/dashscope.py`
- Modify: `app/retrieval/embeddings.py`
- Modify: `app/main.py`
- Modify: `tests/unit/test_dashscope_adapter.py`
- Create: `tests/unit/test_dashscope_embeddings.py`
- Modify: `.env.example`
- Modify: `README.md`

**Interfaces:**
- Consumes: normalized `Settings.dashscope_base_url` from Task 1.
- Produces: `DashScopeLLMAdapter(api_key: str, model: str, base_url: str, timeout_seconds: float = 30.0)`.
- Produces: `DashScopeEmbeddingAdapter(api_key: str, model: str, dimension: int, base_url: str)`.

- [ ] **Step 1: Write failing adapter tests**

Test that `complete()` and `stream()` pass the literal custom URL as `base_address`, and that constructing the embedding adapter configures `dashscope.base_http_api_url` before creating the LlamaIndex wrapper.

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m pytest tests/unit/test_dashscope_adapter.py tests/unit/test_dashscope_embeddings.py -q`
Expected: FAIL because both adapter constructors lack `base_url` and requests omit `base_address`.

- [ ] **Step 3: Wire the normalized URL**

Update both adapters and `build_service_container()` to consume the single setting. Preserve existing timeout, model, dimension, and fallback behavior.

- [ ] **Step 4: Run adapter and full suites**

Run: `python -m pytest tests/unit/test_dashscope_adapter.py tests/unit/test_dashscope_embeddings.py -q`
Expected: PASS.

Run: `python -m pytest -q`
Expected: all tests PASS.

- [ ] **Step 5: Update operator documentation**

Add `RAG_DASHSCOPE_BASE_URL=https://dashscope.aliyuncs.com/api/v1` to `.env.example` and README, explicitly stating that `/api/v1` is required for the official native endpoint and is not auto-appended.

- [ ] **Step 6: Final verification and commit**

Run: `python -m compileall -q app tests`, `git diff --check`, and the frontend typecheck/build to protect the shared branch.

Commit: `feat: configure DashScope base URL`

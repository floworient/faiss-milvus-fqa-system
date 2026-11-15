# OpenAI-Compatible LLM Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the RAG backend generate through the verified workspace OpenAI-compatible endpoint while keeping native DashScope embeddings.

**Architecture:** Add a small `httpx` adapter that implements the existing `LLMPort`. Add an independent validated LLM base URL setting and wire only text generation to it; embeddings retain their current native base URL.

**Tech Stack:** Python, httpx, Pydantic Settings, pytest, FastAPI

**Spec:** `docs/superpowers/specs/2026-11-15-openai-compatible-llm-design.md`

## Global Constraints

- No new dependency.
- No API key logging.
- No live provider calls in pytest.
- Existing REST and SSE contracts remain unchanged.

## Review Focus

- A 429 response maps to `LLMRateLimited` so tier fallback still works.
- A 400/422 response maps to `LLMInvalidRequest` and does not silently fall back.
- Timeout/network failures map to the existing timeout/unavailable errors.
- SSE parsing handles fragmented lines and `[DONE]` without losing tokens.
- Empty or malformed successful payloads fail safely as unavailable.

---

### Task 1: OpenAI-Compatible Adapter

**Files:**
- Create: `app/llm/openai_compatible.py`
- Create: `tests/unit/test_openai_compatible_adapter.py`

**Interfaces:**
- Produces: `OpenAICompatibleLLMAdapter(api_key: str, model: str, base_url: str, timeout_seconds: float = 30.0)` with `complete(prompt: str) -> str` and `stream(prompt: str) -> AsyncIterator[str]`.

- [ ] Write failing tests for successful completion, fragmented SSE tokens, 429, 400, timeout, and malformed success.
- [ ] Run `python -m pytest -q tests/unit/test_openai_compatible_adapter.py` and confirm import/test failures.
- [ ] Implement the minimal adapter with `httpx.Client` and `httpx.AsyncClient`.
- [ ] Run the focused adapter tests and confirm they pass.

### Task 2: Configuration and Wiring

**Files:**
- Modify: `app/core/config.py`
- Modify: `app/main.py`
- Modify: `.env.example`
- Modify: `.env`
- Test: `tests/unit/test_config.py`
- Test: `tests/unit/test_openai_compatible_adapter.py`

**Interfaces:**
- Consumes: `OpenAICompatibleLLMAdapter` from Task 1.
- Produces: `Settings.llm_base_url: str` from `RAG_LLM_BASE_URL`.

- [ ] Write failing configuration tests for the default, environment normalization, and unsafe URL rejection.
- [ ] Write a failing container wiring test that asserts LLM and embedding use different base URLs.
- [ ] Run the focused tests and confirm expected failures.
- [ ] Add validated `llm_base_url`, wire both LLM tiers to the new adapter, update examples, and set the workspace compatible URL in local `.env`.
- [ ] Run focused configuration, adapter, embedding, and router tests.

### Task 3: Verification

**Files:**
- Use: `tests/manual_chat_api.py`

- [ ] Run the relevant unit/integration tests and compile changed modules.
- [ ] Restart the backend and verify `/health` returns 200.
- [ ] Run `python -X utf8 tests/manual_chat_api.py` and require provider tier 1 or 2.
- [ ] Run `git diff --check` for changed non-secret files and review status without staging `.env`.

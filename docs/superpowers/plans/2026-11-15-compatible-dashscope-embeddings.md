# Compatible DashScope Embeddings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Index documents through either native DashScope or the configured workspace embedding response schema.

**Architecture:** A local LlamaIndex `DashScopeEmbedding` subclass owns provider response normalization while the existing application adapter continues dimension truncation. Provider data is validated before vectors reach NumPy or Faiss.

**Tech Stack:** Python, LlamaIndex, DashScope SDK, NumPy, pytest

**Spec:** `docs/superpowers/specs/2026-11-15-compatible-dashscope-embeddings-design.md`

## Global Constraints

- Keep LlamaIndex batching and send each batch exactly once.
- Accept both `text_index` and `index` without logging API keys or input text.
- Do not change parsing, chunking, retrieval, Faiss persistence, or frontend APIs.
- Live verification may send only the synthetic text `“测试”`.

## Review Focus

- Provider returns embedding items out of order: restore input order.
- Provider returns duplicate, negative, non-integer, or out-of-range indices: fail safely.
- Provider omits an item or vector: fail safely rather than constructing an object array.
- Provider returns non-200 with a message containing request data: expose only safe status/code.
- Query embeddings: send `text_type="query"` and accept the workspace `index` field.

---

### Task 1: Compatible LlamaIndex DashScope embedding response

**Files:**
- Modify: `app/retrieval/embeddings.py`
- Modify: `tests/unit/test_dashscope_embeddings.py`

**Interfaces:**
- Consumes: `dashscope.TextEmbedding.call(model, input, api_key, **kwargs)` and LlamaIndex `DashScopeEmbedding` batching hooks.
- Produces: unchanged `DashScopeEmbeddingAdapter.embed_texts(texts) -> NDArray[np.float32]` and `embed_query(text) -> NDArray[np.float32]`.

- [ ] **Step 1: Write failing compatibility tests**

Add tests proving workspace `index` items are ordered correctly and truncated, native `text_index` remains supported, query calls use `text_type="query"`, and malformed/non-200 responses raise `EmbeddingUnavailable`.

- [ ] **Step 2: Run tests to verify RED**

Run: `python -m pytest -q tests/unit/test_dashscope_embeddings.py`

Expected: workspace response test fails with `KeyError: 'text_index'`.

- [ ] **Step 3: Implement the compatibility subclass and response normalizer**

In `app/retrieval/embeddings.py`, add a local LlamaIndex subclass that overrides `_get_text_embeddings`, `_get_text_embedding`, and `_get_query_embedding`. Its shared provider helper accepts `text_index` or `index`, validates the full batch, preserves order, and raises `EmbeddingUnavailable` with safe provider metadata.

- [ ] **Step 4: Run focused and full verification**

Run: `python -m pytest -q tests/unit/test_dashscope_embeddings.py -W error`

Expected: all focused tests pass without warnings.

Run: `python -m pytest -q`

Expected: full backend suite passes.

Run: `npm --prefix frontend test -- --run && npm --prefix frontend run build`

Expected: frontend tests and build pass unchanged.

- [ ] **Step 5: Run the live synthetic smoke test**

Call the configured adapter with only `“测试”`; require a float32 vector with shape `(RAG_EMBEDDING_DIMENSION,)`. Then upload a non-sensitive synthetic Markdown document through the API and require the task to reach `succeeded`.

- [ ] **Step 6: Commit**

```bash
git add app/retrieval/embeddings.py tests/unit/test_dashscope_embeddings.py
git commit -m "fix: support workspace embedding responses"
```

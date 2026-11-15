# OpenAI-Compatible LLM Design

## Intent

Route text generation through the workspace's working OpenAI-compatible API while preserving the native DashScope embedding integration.

## Goals

- Add an OpenAI-compatible LLM adapter for synchronous and SSE-streamed chat completions.
- Configure the LLM base URL independently from the DashScope embedding base URL.
- Preserve the existing tiered fallback and public REST/SSE API contracts.
- Map upstream timeouts, rate limits, invalid requests, and service failures to the existing LLM error types.

## Non-goals

- Replace the embedding adapter.
- Add the OpenAI Python SDK or another dependency.
- Change retrieval, prompts, sessions, or frontend contracts.

## Approaches

1. Repoint the existing DashScope SDK at `/compatible-mode/v1`. Rejected because the SDK appends native DashScope service paths and the live workspace rejects that protocol.
2. Add a focused `httpx` OpenAI-compatible adapter and keep DashScope embeddings. Selected because the dependency already exists, the live endpoint is verified, and the provider split stays explicit.
3. Replace both LLM and embeddings with OpenAI-compatible clients. Rejected because the workspace's OpenAI endpoint does not provide the existing text-embedding integration contract.

## Design

`Settings.llm_base_url` is a canonical HTTP(S) base URL. `build_service_container` constructs `OpenAICompatibleLLMAdapter` for primary and backup models using the shared API key and `llm_base_url`; `DashScopeEmbeddingAdapter` continues to use `dashscope_base_url`. The new adapter posts to `<base>/chat/completions`, uses a single user message containing the rendered prompt, parses standard completion JSON, and parses `data:` SSE frames until `[DONE]`.

## Constraints

- Do not log or expose API keys.
- Preserve existing error classes and tiered router behavior.
- Keep real provider calls out of pytest.
- Keep `.env` credentials uncommitted.


# Compatible DashScope Embeddings Design

## Intent

Make document indexing work with both the official DashScope embedding response and the configured workspace gateway without changing the upload API, chunking, Faiss storage, or chat models.

## Chosen approach

Keep LlamaIndex's `DashScopeEmbedding` abstraction and batching, but override its provider call through a local compatibility subclass. Normalize each successful embedding item by accepting either the native `text_index` field or the workspace `index` field, then return vectors in input order.

Alternatives considered were replacing LlamaIndex with a direct SDK-only adapter, which would discard the existing batching abstraction, and retrying after `KeyError`, which would transmit document text twice. Both were rejected.

## Behavior

- Send each text batch exactly once.
- Accept `text_index` and `index` as equivalent response positions.
- Preserve input ordering even when provider items are unordered.
- Use `text_type="document"` for indexed chunks and `text_type="query"` for queries.
- Reject non-200, malformed, duplicate, out-of-range, missing-vector, and incomplete responses as `EmbeddingUnavailable` without including input text or API keys in errors.
- Continue truncating vectors to `RAG_EMBEDDING_DIMENSION` at the application adapter boundary.

## Non-goals

- Changing the configured embedding model or Base URL.
- Changing parsing, chunking, retrieval, Faiss persistence, or frontend contracts.
- Improving the generic ingestion failure message in this change.

## Verification

Unit tests cover native and workspace index fields, ordering, query mode, provider errors, and malformed responses. A final live smoke test sends only the synthetic text `“测试”` to the configured embedding service.

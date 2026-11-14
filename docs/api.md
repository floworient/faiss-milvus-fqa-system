# RAG Knowledge QA API 接口文档

本文档对应 `RAG Knowledge QA API 0.1.0`，根据当前 FastAPI 路由与 Pydantic Schema 编写。项目处于开发预览阶段，接口可能继续调整。

## 1. 接入信息

| 项目 | 值 |
| --- | --- |
| 默认 Base URL | `http://127.0.0.1:8000` |
| API 前缀 | `/api/v1` |
| Swagger UI | `http://127.0.0.1:8000/docs` |
| OpenAPI JSON | `http://127.0.0.1:8000/openapi.json` |
| 普通请求格式 | `application/json` 或 `multipart/form-data` |
| 流式响应格式 | `text/event-stream` |
| 字符编码 | UTF-8 |
| 认证 | 当前未实现 |

> 当前版本没有认证、租户隔离或限流，只能部署在本机或受信网络，不能直接暴露到公网。

启动服务：

```powershell
uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000
```

## 2. 通用约定

### 2.1 请求追踪

客户端可以传入 `X-Request-ID` 请求头。未传入时，服务端自动生成 `req_<uuid>`。所有 HTTP 响应都会返回该请求头，结构化日志也使用相同 ID。

```http
X-Request-ID: req_client_order_001
```

### 2.2 异步任务

文档上传和删除返回 `202 Accepted`，响应中的 `status` 通常为 `pending`。客户端应使用 `task_id` 轮询任务接口，直到状态变为：

- `succeeded`：操作成功；
- `failed`：操作失败，可根据 `code`、`message` 和 `retryable` 决定是否重试。

### 2.3 检索模式

| 模式 | 说明 |
| --- | --- |
| `vector` | 仅使用 Faiss 向量检索；Embedding 不可用时返回错误 |
| `keyword` | 仅使用关键词索引 |
| `hybrid` | 向量和关键词双路召回，通过 RRF 融合；Embedding 不可用时降级到关键词 |

### 2.4 模型层级

`provider_tier` 表示回答来自哪个可用层级：

| 值 | 含义 |
| --- | --- |
| `1` | 主模型 |
| `2` | 备用模型 |
| `3` | 两个模型均不可用时生成的检索摘要 |

### 2.5 应用错误

业务错误使用统一结构：

```json
{
  "code": "document_not_found",
  "message": "Document was not found.",
  "request_id": "req_a1b2c3"
}
```

字段说明：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `code` | string | 稳定错误码，客户端应基于此字段判断错误类型 |
| `message` | string | 安全的客户端提示，不包含内部堆栈 |
| `request_id` | string / null | 请求追踪 ID |
| `details` | object，可选 | 行号等安全附加信息 |

Pydantic 参数校验错误使用 FastAPI 标准 `422` 响应，主体包含 `detail` 数组。

常见状态码：

| HTTP 状态 | 含义 |
| --- | --- |
| `200 OK` | 查询或同步处理成功 |
| `202 Accepted` | 异步任务已接受 |
| `204 No Content` | 删除会话成功 |
| `404 Not Found` | 任务、文档、会话或 Agent 策略不存在 |
| `413 Content Too Large` | 上传文件超过限制 |
| `422 Unprocessable Entity` | 参数、文档或评测数据格式错误 |
| `503 Service Unavailable` | 必要服务未配置或暂时不可用 |

## 3. 接口总览

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/health` | 健康检查 |
| `POST` | `/api/v1/documents` | 上传并异步索引文档 |
| `GET` | `/api/v1/documents` | 查询有效文档列表 |
| `GET` | `/api/v1/tasks/{task_id}` | 查询上传或删除任务 |
| `DELETE` | `/api/v1/documents/{document_id}` | 异步删除文档 |
| `POST` | `/api/v1/retrieval/search` | 执行向量、关键词或混合检索 |
| `POST` | `/api/v1/chat/completions` | 非流式知识问答 |
| `POST` | `/api/v1/chat/completions/stream` | SSE 流式知识问答 |
| `GET` | `/api/v1/sessions/{session_id}` | 查询会话历史 |
| `DELETE` | `/api/v1/sessions/{session_id}` | 删除会话 |
| `POST` | `/api/v1/evaluations/retrieval` | 上传 JSONL 并执行检索评测 |

## 4. 系统接口

### 4.1 健康检查

`GET` `/health`

响应 `200 OK`：

```json
{
  "status": "ok"
}
```

```bash
curl -i http://127.0.0.1:8000/health
```

## 5. 文档与任务接口

### 5.1 上传文档

`POST` `/api/v1/documents`

使用 `multipart/form-data` 上传文档。支持 TXT、JSON、Markdown；默认最大 10 MiB，可通过 `RAG_UPLOAD_MAX_BYTES` 调整。

| 表单字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `file` | binary | 是 | 待解析文档 |

```bash
curl -X POST http://127.0.0.1:8000/api/v1/documents \
  -F "file=@tests/fixtures/knowledge.md;type=text/markdown"
```

响应 `202 Accepted`：

```json
{
  "task_id": "task_0123456789abcdef0123456789abcdef",
  "action": "upload",
  "document_id": "doc_0123456789abcdef0123456789abcdef",
  "source_name": "knowledge.md",
  "status": "pending",
  "code": null,
  "message": null,
  "retryable": false
}
```

可能的业务错误包括：`upload_too_large`、`unsupported_document_type`、`empty_document`、`invalid_json_document`。

### 5.2 查询任务

`GET` `/api/v1/tasks/{task_id}`

`task_id` 必须为服务端签发的 `task_<32位十六进制>`。

```bash
curl http://127.0.0.1:8000/api/v1/tasks/task_0123456789abcdef0123456789abcdef
```

成功响应使用与上传接口相同的 `TaskResponse`。失败任务示例：

```json
{
  "task_id": "task_0123456789abcdef0123456789abcdef",
  "action": "upload",
  "document_id": "doc_0123456789abcdef0123456789abcdef",
  "source_name": "knowledge.md",
  "status": "failed",
  "code": "ingestion_failed",
  "message": "Document indexing failed.",
  "retryable": true
}
```

任务状态枚举：`pending`、`running`、`succeeded`、`failed`。

### 5.3 查询文档列表

`GET` `/api/v1/documents`

```bash
curl http://127.0.0.1:8000/api/v1/documents
```

响应 `200 OK`：

```json
[
  {
    "document_id": "doc_0123456789abcdef0123456789abcdef",
    "source_name": "knowledge.md",
    "status": "active",
    "chunk_count": 3
  }
]
```

### 5.4 删除文档

`DELETE` `/api/v1/documents/{document_id}`

```bash
curl -X DELETE \
  http://127.0.0.1:8000/api/v1/documents/doc_0123456789abcdef0123456789abcdef
```

响应 `202 Accepted`，`action` 为 `delete`。客户端仍需轮询任务接口。删除成功后：

- 新活动索引不再包含该文档；
- 上传源文件被删除并保存安全墓碑；
- 历史会话引用被标记为 `deleted: true`，`excerpt` 被清空；
- 与回答并发时，墓碑和共享锁会阻止正文被重新写入会话文件。

## 6. 检索接口

### 6.1 搜索知识库

`POST` `/api/v1/retrieval/search`

请求体：

| 字段 | 类型 | 必填 | 默认值 | 约束与说明 |
| --- | --- | --- | --- | --- |
| `query` | string | 是 | — | 1～4000 字符，不能全为空白 |
| `mode` | string | 否 | `hybrid` | `vector` / `keyword` / `hybrid` |
| `top_k` | integer | 否 | `5` | 1～50，最终返回数量 |
| `candidate_k` | integer | 否 | `20` | 1～200，单路候选数量 |

```bash
curl -X POST http://127.0.0.1:8000/api/v1/retrieval/search \
  -H "Content-Type: application/json" \
  -d '{"query":"退货政策是什么？","mode":"hybrid","top_k":5,"candidate_k":20}'
```

响应 `200 OK`：

```json
{
  "query": "退货政策是什么？",
  "mode": "hybrid",
  "results": [
    {
      "chunk_id": "chk_abc123",
      "document_id": "doc_0123456789abcdef0123456789abcdef",
      "text": "商品签收后七天内可以申请退货。",
      "source": "knowledge.md",
      "position": 0,
      "score": 0.03278688524590164,
      "rank": 1,
      "vector_rank": 1,
      "keyword_rank": 1
    }
  ],
  "degraded_from": null,
  "degradation_reason": null
}
```

混合检索在 Embedding 不可用时仍可能返回 `200`，此时：

```json
{
  "degraded_from": "hybrid",
  "degradation_reason": "embedding_unavailable"
}
```

纯向量模式遇到相同情况时返回 `503` 和 `embedding_unavailable`。

## 7. 问答接口

### 7.1 公共请求字段

非流式与流式接口使用相同请求模型：

| 字段 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `question` | string | 是 | — | 1～4000 字符，不能全为空白 |
| `session_id` | string / null | 否 | `null` | 不传时创建会话，传入时继续多轮对话 |
| `strategy` | string | 否 | `contextual_rag` | Agent 策略名 |
| `retrieval_mode` | string | 否 | `hybrid` | `vector` / `keyword` / `hybrid` |
| `top_k` | integer | 否 | `5` | 1～50 |
| `candidate_k` | integer | 否 | `20` | 1～200 |

### 7.2 非流式问答

`POST` `/api/v1/chat/completions`

```bash
curl -X POST http://127.0.0.1:8000/api/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"question":"如何申请退货？","retrieval_mode":"hybrid"}'
```

响应 `200 OK`：

```json
{
  "session_id": "session_0123456789abcdef0123456789abcdef",
  "answer": "请在签收后七天内提交退货申请。",
  "provider_tier": 1,
  "citations": [
    {
      "chunk_id": "chk_abc123",
      "document_id": "doc_0123456789abcdef0123456789abcdef",
      "source_name": "knowledge.md",
      "excerpt": "商品签收后七天内可以申请退货。",
      "deleted": false
    }
  ],
  "retrieval": {
    "mode": "hybrid",
    "degraded_from": null,
    "degradation_reason": null
  },
  "metadata": {}
}
```

继续同一会话：

```json
{
  "question": "那退款多久能到账？",
  "session_id": "session_0123456789abcdef0123456789abcdef"
}
```

### 7.3 SSE 流式问答

`POST` `/api/v1/chat/completions/stream`

```bash
curl -N -X POST http://127.0.0.1:8000/api/v1/chat/completions/stream \
  -H "Content-Type: application/json" \
  -d '{"question":"请概括退货规则","retrieval_mode":"hybrid"}'
```

响应头包含：

```http
Content-Type: text/event-stream; charset=utf-8
Cache-Control: no-cache
X-Accel-Buffering: no
```

SSE 事件使用如下格式：

```text
event: token
data: {"text":"七天内","tier":1}

```

事件顺序和含义：

| 事件 | 何时出现 | 关键数据 |
| --- | --- | --- |
| `meta` | 首个事件 | `session_id`、`strategy`、`retrieval_mode` |
| `retrieval` | 检索完成后 | `mode`、降级信息、`citations` |
| `token` | 每次有增量文本 | `text`、`tier` |
| `fallback` | 首 token 前模型不可用并降级 | `from_tier`、`to_tier`、`reason` |
| `error` | 首 token 后发生模型错误 | `code`、`tier` |
| `done` | 流结束 | `status`、`tier` |

正常事件序列示例：

```text
meta → retrieval → token → token → done
```

模型首 token 前失败时可能是：

```text
meta → retrieval → fallback → token → done
```

首 token 后失败时不会拼接其他模型内容：

```text
meta → retrieval → token → error → done
```

## 8. 会话接口

### 8.1 查询会话

`GET` `/api/v1/sessions/{session_id}`

```bash
curl http://127.0.0.1:8000/api/v1/sessions/session_0123456789abcdef0123456789abcdef
```

响应 `200 OK`：

```json
{
  "session_id": "session_0123456789abcdef0123456789abcdef",
  "messages": [
    {
      "role": "user",
      "content": "如何申请退货？",
      "status": "complete",
      "citations": [],
      "metadata": {}
    },
    {
      "role": "assistant",
      "content": "请在签收后七天内提交申请。",
      "status": "complete",
      "citations": [
        {
          "chunk_id": "chk_abc123",
          "document_id": "doc_0123456789abcdef0123456789abcdef",
          "source_name": "knowledge.md",
          "excerpt": "商品签收后七天内可以申请退货。",
          "deleted": false
        }
      ],
      "metadata": {
        "provider_tier": 1
      }
    }
  ],
  "metadata": {}
}
```

流式生成中途失败的 assistant 消息使用 `status: "failed"`，会保留用于审计，但不会进入下一轮 Prompt。已删除文档的 Citation 返回 `deleted: true` 和 `excerpt: null`。

### 8.2 删除会话

`DELETE` `/api/v1/sessions/{session_id}`

```bash
curl -X DELETE \
  http://127.0.0.1:8000/api/v1/sessions/session_0123456789abcdef0123456789abcdef
```

成功返回 `204 No Content`，没有响应体。

## 9. 评测接口

### 9.1 JSONL 数据格式

每行必须是独立 JSON 对象，`query` 必填，并至少提供一种相关性标签：

- `relevant_chunk_ids`：相关 Chunk ID 数组；
- `relevant_document_ids`：相关 Document ID 数组。

可选字段：

- `reference_answer`：参考答案；
- `human_correct`：人工判断回答是否正确，用于统计 `answer_accuracy`。

```jsonl
{"query":"退货政策","relevant_chunk_ids":["chk_abc123"],"human_correct":true}
{"query":"退款到账时间","relevant_document_ids":["doc_0123456789abcdef0123456789abcdef"]}
```

不能包含空白行，格式错误会返回 `422`，`details.line_number` 指向错误行。

### 9.2 执行检索评测

`POST` `/api/v1/evaluations/retrieval`

使用 `multipart/form-data`：

| 表单字段 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `file` | binary | 是 | — | UTF-8 JSONL 数据集 |
| `mode` | string | 否 | `hybrid` | 检索模式 |
| `top_k` | integer | 否 | `5` | 1～50 |
| `dataset_name` | string / null | 否 | `null` | 预留的数据集名称 |

```bash
curl -X POST http://127.0.0.1:8000/api/v1/evaluations/retrieval \
  -F "file=@data/evaluation.jsonl;type=application/jsonl" \
  -F "mode=hybrid" \
  -F "top_k=5"
```

响应 `200 OK`：

```json
{
  "mode": "hybrid",
  "top_k": 5,
  "query_count": 2,
  "hit_at_1": 0.5,
  "recall_at_k": 0.75,
  "mrr": 0.625,
  "answer_accuracy": 1.0,
  "configuration": {
    "mode": "hybrid",
    "top_k": 5,
    "sample_count": 2
  },
  "queries": [
    {
      "query": "退货政策",
      "first_relevant_rank": 1,
      "recall_at_k": 1.0,
      "returned_chunk_ids": ["chk_abc123"],
      "returned_document_ids": ["doc_0123456789abcdef0123456789abcdef"]
    }
  ]
}
```

指标说明：

| 指标 | 说明 |
| --- | --- |
| `hit_at_1` | 第一条结果命中相关标签的查询比例 |
| `recall_at_k` | Top-K 内召回的相关标签比例均值 |
| `mrr` | 首个相关结果倒数排名的均值 |
| `answer_accuracy` | 提供 `human_correct` 标签时的人工正确率，否则为 `null` |

## 10. 完整调用流程

推荐客户端流程：

1. `POST /api/v1/documents` 上传文档；
2. 轮询 `GET /api/v1/tasks/{task_id}`，等待 `succeeded`；
3. 使用 `POST /api/v1/retrieval/search` 验证召回；
4. 使用非流式或 SSE 问答接口；
5. 保存返回的 `session_id` 以继续对话或查询历史；
6. 用 JSONL 评测接口建立检索基线；
7. 删除文档后继续轮询删除任务，成功后确认检索结果已排除该文档。

仓库提供只调用公开 HTTP API 的自动冒烟脚本：

```powershell
python scripts/smoke_test.py --base-url http://127.0.0.1:8000
```

## 11. 配置相关限制

- 未配置 `RAG_DASHSCOPE_API_KEY` 时，真实文档无法生成向量；问答会降级为第 3 层检索摘要。
- `RAG_RETRIEVAL_TOP_K` 必须小于等于 `RAG_RETRIEVAL_CANDIDATE_K`。
- 当前为单进程文件持久化实现，不应使用多个 Uvicorn worker 写入同一 `RAG_DATA_DIR`。
- 上传内容、问题、Prompt 和 API Key 不会写入结构化日志；日志使用 request/task/session ID 关联链路。

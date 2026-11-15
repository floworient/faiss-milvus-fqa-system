# LlamaIndex 与工作空间 Embedding 响应格式不兼容

- 状态：已修复
- 日期：2026-11-15
- 影响范围：Markdown / TXT / JSON 文档索引
- 关联分支：`codex/frontend-api-integration`

## 现象

上传文档后，异步任务进入 `failed`，前端显示 `Document indexing failed.`。文件能够通过格式、UTF-8、解析和分块校验，但无法写入向量索引。

## 根因

项目使用 LlamaIndex 的 `DashScopeEmbedding`。该适配器按原生 DashScope 响应读取：

```text
text_index
```

当前工作空间 Embedding 接口返回：

```text
index
```

请求实际返回 HTTP 200，但 LlamaIndex 在整理向量顺序时触发：

```text
KeyError: 'text_index'
```

因此这不是文档解析失败，也不是问答模型额度不足，而是 Embedding 响应字段兼容问题。

## 修复

- 保留 LlamaIndex 的同步文本 Embedding 抽象和批处理。
- 本地兼容层同时接受 `text_index` 与 `index`。
- 根据索引恢复输入顺序，并拒绝重复、缺失、越界或非整数索引。
- 拒绝空向量、维度不一致、NaN、Infinity 和不能表示为 float32 的数值。
- 将 DashScope SDK 解码和网络异常转换为不包含输入文本、API Key 或供应商 message 的 `EmbeddingUnavailable`。
- 查询向量继续发送 `text_type="query"`，文档向量继续发送 `text_type="document"`。

## 验证

- Embedding 专项测试：18 项通过。
- 后端全量测试：165 项通过。
- 前端测试：2 项通过，生产构建成功。
- 合成文本 `测试` 返回有限的 float32 向量，形状为 `(512,)`。
- 无敏感信息的合成 Markdown 完成上传、解析、分块、向量化和索引发布，任务状态为 `succeeded`；随后清理任务也成功。

## 延期项

单次供应商请求内已经验证向量宽度一致。跨多个 LlamaIndex 批次的聚合宽度检查尚未加入；如果供应商在同一调用周期内跨批次改变向量维度，当前可能在 NumPy 聚合阶段失败。该情况不会发布损坏索引，但后续可统一转换为 `EmbeddingUnavailable`。

## 相关文件

- `app/retrieval/embeddings.py`
- `tests/unit/test_dashscope_embeddings.py`
- `docs/superpowers/specs/2026-11-15-compatible-dashscope-embeddings-design.md`
- `docs/superpowers/plans/2026-11-15-compatible-dashscope-embeddings.md`

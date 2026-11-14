# Apifox 导入与调试

本目录是 `RAG Knowledge QA API 0.1.0` 的完整 Apifox 导入包。

## 导入顺序

1. 启动后端，确认 `http://127.0.0.1:8000/health` 返回 `ok`。
2. 在 Apifox 中导入 `openapi.json`，用于创建接口和数据模型。
3. 导入 `rag-knowledge-qa.postman_collection.json`，用于导入示例、脚本和断言。若导入到同一项目时出现重复接口，请选择合并或覆盖，不要保留两份。
4. 导入 `local.postman_environment.json` 并切换到 `RAG Knowledge QA - Local` 环境。
5. 文件字段若没有自动解析相对路径，请手动选择 `fixtures/knowledge.md`；评测文件按下文生成。

## 推荐端到端顺序

1. `00 系统 / 健康检查`
2. `01 文档与任务 / 上传知识文档`
3. 重复执行“查询上传任务”，直到 `status` 为 `succeeded`；若为 `failed`，断言会失败并显示 `code/message`，停止后续流程
4. 执行文档列表、关键词/向量/混合检索
5. 执行非流式问答；脚本会保存 `session_id`
6. 查询会话历史
7. 在 Apifox SSE 调试器中执行流式问答
8. 从 Apifox 环境复制 `document_id`，生成带真实标签的评测文件：

   ```powershell
   python -X utf8 docs/apifox/prepare_evaluation.py --document-id doc_实际值
   ```

9. 在评测请求中选择 `fixtures/evaluation.runtime.jsonl` 后运行检索评测；正确检索该文档时 Hit@1、Recall@K 和 MRR 应大于 0
10. 删除会话、删除文档，并轮询删除任务直到成功；若删除任务为 `failed`，保留 `document_id` 并检查错误信息

上传和删除是异步任务。集合不会自动无限轮询，避免接口失败时卡死运行器。轮询脚本接受 `pending/running/succeeded`，但会把终态 `failed` 标记为断言失败。

## SSE 验收

流式接口请求头包含 `Accept: text/event-stream`。预期事件顺序为：

```text
meta → retrieval → token（一个或多个）→ done
```

异常时最后一个事件可能是 `error`。Collection 只断言 HTTP 状态和 Content-Type；事件内容请在 Apifox SSE 调试界面查看。

## 环境变量

`request_id` 由 Collection 前置脚本自动刷新。上传、删除和问答成功后，后置脚本会写入 `upload_task_id`、`delete_task_id`、`document_id` 和 `session_id`。环境中不保存 DashScope Key；模型密钥只配置在后端 `.env`。

## 重新生成

后端路由或 Schema 变化后，在仓库根目录执行：

```powershell
python -X utf8 scripts/generate_apifox_bundle.py
python -X utf8 -m pytest tests/unit/test_apifox_bundle.py -q
```

OpenAPI 的权威来源仍是 FastAPI `create_app()`；不要手工修改生成的 JSON。

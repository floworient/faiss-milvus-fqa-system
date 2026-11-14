# Apifox 完整导入包设计

## 目标

为当前 RAG Knowledge QA API 生成一套可导入 Apifox 的版本化资产，使开发者无需手工创建接口即可完成接口调试、变量传递、基础断言和端到端流程验证。

## 交付结构

导入包位于 `docs/apifox/`：

- `openapi.json`：从当前 FastAPI 应用生成的 OpenAPI 快照，用于导入完整接口、Schema、文件上传及响应定义。
- `rag-knowledge-qa.postman_collection.json`：Postman Collection v2.1，用于向 Apifox 导入示例请求、前后置脚本、断言和变量提取。
- `local.postman_environment.json`：本地环境，包含 `base_url` 以及流程运行时变量。
- `fixtures/knowledge.md`：文档上传示例。
- `fixtures/evaluation.template.jsonl`：检索评测模板。
- `prepare_evaluation.py`：使用上传后得到的 `document_id` 生成 `fixtures/evaluation.runtime.jsonl`。
- `README.md`：导入顺序、运行前置条件、文件选择方式、端到端执行顺序和 SSE 调试说明。

## Collection 设计

按以下模块组织请求：

1. 系统：健康检查。
2. 文档：上传、查询上传任务、列出文档、删除、查询删除任务。
3. 检索：关键词、向量、混合检索示例。
4. 问答：普通问答、SSE 流式问答。
5. 会话：查询和删除会话。
6. 评测：上传 JSONL 并执行评测。
7. 异常用例：非法检索参数、不存在的任务和会话。

Collection 级前置脚本生成 `X-Request-ID`。请求级测试脚本执行状态码、响应类型和关键字段断言，并从响应提取 `task_id`、`document_id`、`session_id`。异步任务使用独立轮询请求；`failed` 终态必须触发断言失败并显示错误，README 明确说明停止流程。评测前使用辅助脚本把动态文档 ID 写入 JSONL，避免固定标签产生虚假的零分报告。

## 环境变量

- `base_url`：默认 `http://127.0.0.1:8000`。
- `request_id`：前置脚本自动生成。
- `task_id`、`upload_task_id`、`delete_task_id`：脚本提取。
- `document_id`：上传响应提取。
- `session_id`：问答响应提取。
- `query`：默认知识库问题。

环境文件不包含 DashScope API Key 或其他秘密。

## SSE 约束

流式接口保留 `Accept: text/event-stream`、请求示例和 Content-Type 断言。由于集合运行器对持续流的事件聚合方式可能与 Apifox SSE 调试器不同，事件顺序 `meta → retrieval → token → done/error` 在 README 中作为 SSE 调试器的人工验收项，不伪装成稳定的普通响应脚本断言。

## 生成与验证

- 新增仓库脚本从 `create_app()` 生成确定性的 `openapi.json`，防止手工维护漂移。
- 新增校验测试读取所有 JSON/JSONL 文件，校验 Collection v2.1 Schema 关键字段、请求路径覆盖、脚本变量引用及 OpenAPI 路由覆盖，并比较重新生成结果与已提交资产，防止漂移。
- 生成器导入应用工厂时不得实例化默认应用或修改真实运行时任务。
- 使用 FastAPI 测试客户端或现有服务对非破坏性请求进行烟雾验证；上传、删除等有状态流程使用临时数据目录执行。
- 导入包不包含真实凭证、绝对路径或本机私有数据。

## 取舍

- 同时提供 OpenAPI 与 Postman v2.1：前者保证接口模型完整，后者保证脚本和变量可迁移。
- 不生成未公开稳定格式的 Apifox 原生项目文件，避免版本升级后无法导入。
- 不在脚本中自动无限轮询异步任务，避免集合运行卡死；由清晰的轮询请求和断言展示状态。

## 验收标准

- Apifox 可分别识别 OpenAPI 文件、Collection 和环境文件。
- 11 个当前 API 路由均出现在 OpenAPI 和 Collection 中。
- JSON/JSONL 文件语法有效，测试数据可被现有解析器接受。
- Collection 中不存在硬编码密钥、绝对文件路径或固定资源 ID。
- 脚本能提取并复用任务、文档和会话变量。
- 后端全量测试、导入包校验测试及 Git 差异检查通过。

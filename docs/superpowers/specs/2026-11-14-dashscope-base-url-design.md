# DashScope Base URL 配置设计

## 目标

将 DashScope 服务地址从 SDK 默认值中提取为统一配置，使 LLM 与 Embedding 可以共同切换到代理或私有网关。

## 配置约定

- 新增 `RAG_DASHSCOPE_BASE_URL`。
- 默认值为 `https://dashscope.aliyuncs.com/api/v1`。
- 配置值必须是包含 API 版本路径的完整基础地址；官方地址需要显式包含 `/api/v1`。
- 应用只移除末尾的 `/`，不自动追加 `/v1` 或 `/api/v1`，避免破坏自定义网关路径。
- 该地址面向 DashScope 原生 SDK，不等同于 OpenAI 兼容接口的 `/compatible-mode/v1` 地址。

## 实现范围

- `Settings` 增加 URL 类型配置及环境变量读取。
- LLM 请求通过 DashScope SDK 的 `base_address` 参数逐请求传递，避免修改 SDK 全局状态。
- Embedding 适配器使用同一配置；根据 LlamaIndex DashScope 适配器支持的参数进行显式传递。
- 更新 `.env.example`、README 启动配置说明和相应测试。

## 方案取舍

- 采用一个统一地址：配置简单，符合当前 LLM 与 Embedding 都使用 DashScope 的架构。
- 不采用 LLM/Embedding 双地址：当前没有分别接入不同供应商的需求。
- 不采用自动补全版本路径：`/api/v1`、代理路径和私有部署路径并不总能由程序可靠推断。

## 验收标准

- 未配置时继续使用官方 `https://dashscope.aliyuncs.com/api/v1`。
- 环境变量配置可覆盖默认值。
- LLM 同步与流式请求均收到配置后的 `base_address`。
- Embedding 客户端使用相同地址。
- 配置、适配器及全量测试通过。

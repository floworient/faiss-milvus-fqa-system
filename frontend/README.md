# RAG Knowledge QA Web

Vue 3 + TypeScript + Vite 管理台，接口契约以 [`../docs/api.md`](../docs/api.md) 为准。

## 功能

- 文档拖放上传、异步任务轮询、列表与安全删除
- Vector / Keyword / Hybrid 检索调试与双路排名展示
- 非流式与 SSE 流式问答、多轮会话、引用及模型降级提示
- JSONL 检索评测和 Hit@1、Recall@K、MRR 指标展示
- 后端健康检查、响应式桌面与移动端布局

## 本地运行

先在仓库根目录启动后端：

```powershell
uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000
```

再启动前端：

```powershell
cd frontend
npm install
npm run dev
```

打开 `http://127.0.0.1:5173`。Vite 会将 `/api`、`/health`、`/docs` 和 `/openapi.json` 代理到 `http://127.0.0.1:8000`。

## 验证

```powershell
npm run typecheck
npm test
npm run build
```

生产构建输出到 `frontend/dist/`。部署时应将前端与 API 放在同源网关下，在网关配置 `/api`、`/health`、`/docs` 和 `/openapi.json` 反向代理，并为 Vue Router 配置 HTML5 History 回退到 `index.html`。当前后端没有认证，不应直接暴露到公网。

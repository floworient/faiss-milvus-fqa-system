import { parseSSEStream } from './sse'
import type {
  ApiErrorPayload,
  ChatRequest,
  ChatResponse,
  DocumentResponse,
  EvaluationReport,
  RetrievalMode,
  RetrievalSearchResponse,
  SSEEvent,
  SessionResponse,
  TaskResponse,
} from './types'

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly code = 'request_failed',
    public readonly requestId: string | null = null,
    public readonly details?: unknown,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

async function parseError(response: Response): Promise<ApiError> {
  let payload: ApiErrorPayload = {}
  try {
    payload = (await response.json()) as ApiErrorPayload
  } catch {
    // Non-JSON gateway failures still become a safe UI error.
  }
  const validationMessage = payload.detail?.map((item) => item.msg).join('；')
  return new ApiError(
    payload.message || validationMessage || `请求失败（HTTP ${response.status}）`,
    response.status,
    payload.code || 'request_failed',
    payload.request_id ?? response.headers.get('x-request-id'),
    payload.details,
  )
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init)
  if (!response.ok) throw await parseError(response)
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

export const api = {
  health: () => request<{ status: string }>('/health'),

  listDocuments: () => request<DocumentResponse[]>('/api/v1/documents'),

  async uploadDocument(file: File): Promise<TaskResponse> {
    const form = new FormData()
    form.append('file', file)
    return request('/api/v1/documents', { method: 'POST', body: form })
  },

  getTask: (taskId: string) => request<TaskResponse>(`/api/v1/tasks/${encodeURIComponent(taskId)}`),

  deleteDocument: (documentId: string) =>
    request<TaskResponse>(`/api/v1/documents/${encodeURIComponent(documentId)}`, { method: 'DELETE' }),

  async waitForTask(taskId: string, timeoutMs = 60_000): Promise<TaskResponse> {
    const startedAt = Date.now()
    while (Date.now() - startedAt < timeoutMs) {
      const task = await api.getTask(taskId)
      if (task.status === 'succeeded') return task
      if (task.status === 'failed') {
        throw new ApiError(task.message || '任务执行失败', 500, task.code || 'task_failed', null, task)
      }
      await new Promise((resolve) => window.setTimeout(resolve, 650))
    }
    throw new ApiError('任务等待超时，请稍后刷新查看', 408, 'task_timeout')
  },

  search(query: string, mode: RetrievalMode, topK: number, candidateK: number) {
    return request<RetrievalSearchResponse>('/api/v1/retrieval/search', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query, mode, top_k: topK, candidate_k: candidateK }),
    })
  },

  chat(payload: ChatRequest) {
    return request<ChatResponse>('/api/v1/chat/completions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
  },

  async *streamChat(payload: ChatRequest, signal?: AbortSignal): AsyncGenerator<SSEEvent> {
    const response = await fetch('/api/v1/chat/completions/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      signal,
    })
    if (!response.ok) throw await parseError(response)
    if (!response.body) throw new ApiError('浏览器未提供可读取的流式响应', 500, 'stream_unavailable')
    yield* parseSSEStream(response.body)
  },

  getSession: (sessionId: string) =>
    request<SessionResponse>(`/api/v1/sessions/${encodeURIComponent(sessionId)}`),

  deleteSession: (sessionId: string) =>
    request<void>(`/api/v1/sessions/${encodeURIComponent(sessionId)}`, { method: 'DELETE' }),

  async evaluate(file: File, mode: RetrievalMode, topK: number): Promise<EvaluationReport> {
    const form = new FormData()
    form.append('file', file)
    form.append('mode', mode)
    form.append('top_k', String(topK))
    form.append('dataset_name', file.name)
    return request('/api/v1/evaluations/retrieval', { method: 'POST', body: form })
  },
}

export function formatApiError(error: unknown): string {
  if (error instanceof ApiError) {
    return error.requestId ? `${error.message} · ${error.requestId}` : error.message
  }
  return error instanceof Error ? error.message : '发生未知错误'
}

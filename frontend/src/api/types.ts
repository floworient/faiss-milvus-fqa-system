export type RetrievalMode = 'vector' | 'keyword' | 'hybrid'
export type TaskStatus = 'pending' | 'running' | 'succeeded' | 'failed'

export interface ApiErrorPayload {
  code?: string
  message?: string
  request_id?: string | null
  details?: Record<string, unknown>
  detail?: Array<{ loc: Array<string | number>; msg: string; type: string }>
}

export interface TaskResponse {
  task_id: string
  action: 'upload' | 'delete'
  document_id: string
  source_name: string
  status: TaskStatus
  code: string | null
  message: string | null
  retryable: boolean
}

export interface DocumentResponse {
  document_id: string
  source_name: string
  status: 'active' | 'deleted'
  chunk_count: number
}

export interface Citation {
  chunk_id: string
  document_id: string
  source_name: string
  excerpt: string | null
  deleted: boolean
}

export interface RetrievalTrace {
  mode: RetrievalMode
  degraded_from?: RetrievalMode | null
  degradation_reason?: string | null
}

export interface RetrievalItem {
  chunk_id: string
  document_id: string
  text: string
  source: string | null
  position: number
  score: number
  rank: number
  vector_rank: number | null
  keyword_rank: number | null
}

export interface RetrievalSearchResponse extends RetrievalTrace {
  query: string
  results: RetrievalItem[]
}

export interface ChatRequest {
  question: string
  session_id?: string | null
  strategy?: string
  retrieval_mode?: RetrievalMode
  top_k?: number
  candidate_k?: number
}

export interface ChatResponse {
  session_id: string
  answer: string
  provider_tier: 1 | 2 | 3
  citations: Citation[]
  retrieval: RetrievalTrace
  metadata: Record<string, unknown>
}

export interface SessionMessage {
  role: 'user' | 'assistant'
  content: string
  status: 'complete' | 'failed'
  citations: Citation[]
  metadata: Record<string, unknown>
}

export interface SessionResponse {
  session_id: string
  messages: SessionMessage[]
  metadata: Record<string, unknown>
}

export interface QueryEvaluation {
  query: string
  first_relevant_rank: number | null
  recall_at_k: number
  returned_chunk_ids: string[]
  returned_document_ids: string[]
}

export interface EvaluationReport {
  mode: RetrievalMode
  top_k: number
  query_count: number
  hit_at_1: number
  recall_at_k: number
  mrr: number
  answer_accuracy: number | null
  configuration: Record<string, unknown>
  queries: QueryEvaluation[]
}

export type SSEEventType = 'meta' | 'retrieval' | 'token' | 'fallback' | 'error' | 'done'

export interface SSEEvent {
  type: SSEEventType
  data: Record<string, unknown>
}

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { api, formatApiError } from '../api/client'
import type { Citation, RetrievalMode, SessionMessage } from '../api/types'
import AppIcon from '../components/AppIcon.vue'
import PageHeader from '../components/PageHeader.vue'
import StatusPill from '../components/StatusPill.vue'

interface UiMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  status: 'complete' | 'streaming' | 'failed'
  citations: Citation[]
  tier?: number
  fallback?: string
}

const STORAGE_KEY = 'rag-qa-session-id'
const messages = ref<UiMessage[]>([])
const question = ref('')
const sessionId = ref<string | null>(localStorage.getItem(STORAGE_KEY))
const retrievalMode = ref<RetrievalMode>('hybrid')
const topK = ref(5)
const streaming = ref(true)
const sending = ref(false)
const loadingSession = ref(false)
const error = ref('')
const chatBody = ref<HTMLElement | null>(null)
let controller: AbortController | null = null

const suggestions = [
  '退货政策是什么？',
  '如何联系人工客服？',
  '请总结知识库的核心内容',
]

const tierLabel = (tier?: number) => tier === 1 ? '主模型' : tier === 2 ? '备用模型' : tier === 3 ? '检索摘要' : '生成中'
const hasMessages = computed(() => messages.value.length > 0)

function mapHistory(item: SessionMessage, index: number): UiMessage {
  const rawTier = item.metadata.provider_tier
  return {
    id: `history-${index}`,
    role: item.role,
    content: item.content,
    status: item.status,
    citations: item.citations,
    tier: typeof rawTier === 'number' ? rawTier : undefined,
  }
}

async function loadSession() {
  if (!sessionId.value) return
  loadingSession.value = true
  try {
    const session = await api.getSession(sessionId.value)
    messages.value = session.messages.map(mapHistory)
    await scrollToBottom()
  } catch {
    localStorage.removeItem(STORAGE_KEY)
    sessionId.value = null
  } finally {
    loadingSession.value = false
  }
}

function saveSession(id: string) {
  sessionId.value = id
  localStorage.setItem(STORAGE_KEY, id)
}

async function scrollToBottom() {
  await nextTick()
  if (chatBody.value) chatBody.value.scrollTop = chatBody.value.scrollHeight
}

function newConversation() {
  if (sending.value) controller?.abort()
  messages.value = []
  sessionId.value = null
  localStorage.removeItem(STORAGE_KEY)
  error.value = ''
}

async function deleteConversation() {
  if (!sessionId.value) return newConversation()
  if (!window.confirm('确认删除当前会话及其全部消息？')) return
  try {
    await api.deleteSession(sessionId.value)
    newConversation()
  } catch (caught) {
    error.value = formatApiError(caught)
  }
}

function useSuggestion(text: string) {
  question.value = text
  void sendMessage()
}

async function sendMessage() {
  const text = question.value.trim()
  if (!text || sending.value) return
  error.value = ''
  question.value = ''
  sending.value = true

  messages.value.push({ id: crypto.randomUUID(), role: 'user', content: text, status: 'complete', citations: [] })
  const assistant: UiMessage = { id: crypto.randomUUID(), role: 'assistant', content: '', status: 'streaming', citations: [] }
  messages.value.push(assistant)
  await scrollToBottom()

  const payload = {
    question: text,
    session_id: sessionId.value,
    retrieval_mode: retrievalMode.value,
    top_k: topK.value,
    candidate_k: Math.max(20, topK.value),
  }

  try {
    if (!streaming.value) {
      const response = await api.chat(payload)
      saveSession(response.session_id)
      assistant.content = response.answer
      assistant.citations = response.citations
      assistant.tier = response.provider_tier
      assistant.status = 'complete'
      return
    }

    controller = new AbortController()
    for await (const event of api.streamChat(payload, controller.signal)) {
      if (event.type === 'meta' && typeof event.data.session_id === 'string') saveSession(event.data.session_id)
      if (event.type === 'retrieval' && Array.isArray(event.data.citations)) assistant.citations = event.data.citations as Citation[]
      if (event.type === 'token') {
        assistant.content += String(event.data.text ?? '')
        if (typeof event.data.tier === 'number') assistant.tier = event.data.tier
      }
      if (event.type === 'fallback') {
        assistant.fallback = `模型已从 Tier ${String(event.data.from_tier)} 降级到 Tier ${String(event.data.to_tier)} · ${String(event.data.reason)}`
      }
      if (event.type === 'error') {
        assistant.status = 'failed'
        error.value = `流式生成中断：${String(event.data.code ?? 'unknown_error')}`
      }
      if (event.type === 'done') {
        assistant.status = event.data.status === 'complete' ? 'complete' : 'failed'
        if (typeof event.data.tier === 'number') assistant.tier = event.data.tier
      }
      await scrollToBottom()
    }
  } catch (caught) {
    if ((caught as Error).name !== 'AbortError') {
      assistant.status = 'failed'
      error.value = formatApiError(caught)
    }
  } finally {
    sending.value = false
    controller = null
    if (!assistant.content && assistant.status === 'failed') assistant.content = '本次回答未能完成，请稍后重试。'
    await scrollToBottom()
  }
}

function onComposerKeydown(event: KeyboardEvent) {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    void sendMessage()
  }
}

onMounted(loadSession)
onBeforeUnmount(() => controller?.abort())
</script>

<template>
  <section class="chat-page">
    <PageHeader eyebrow="Contextual RAG Agent" title="智能问答" description="基于知识库进行可追溯问答，支持多轮上下文、引用来源和实时 SSE 输出。">
      <button class="button" @click="newConversation"><AppIcon name="plus" :size="16" />新建会话</button>
      <button v-if="sessionId" class="button button-danger" @click="deleteConversation"><AppIcon name="trash" :size="15" />删除会话</button>
    </PageHeader>

    <div class="chat-layout">
      <div class="panel chat-panel">
        <div class="chat-toolbar">
          <div class="agent-identity"><span class="agent-avatar"><AppIcon name="sparkle" /></span><div><strong>Knowledge Agent</strong><span><i /> 在线 · 上下文检索</span></div></div>
          <div class="chat-toolbar-meta"><StatusPill :tone="streaming ? 'info' : 'neutral'" :label="streaming ? 'SSE STREAM' : 'STANDARD'" /><span v-if="sessionId" class="session-short mono">{{ sessionId.slice(0, 18) }}…</span></div>
        </div>

        <div ref="chatBody" class="chat-body">
          <div v-if="loadingSession" class="chat-loading"><span class="typing-dots"><i /><i /><i /></span>正在恢复会话…</div>
          <div v-else-if="!hasMessages" class="chat-welcome">
            <div class="welcome-orbit"><span /><span /><span /><AppIcon name="chat" :size="34" /></div>
            <p class="eyebrow">KNOWLEDGE READY</p>
            <h2>今天想从知识库了解什么？</h2>
            <p>回答将严格基于已索引文档，并展示相关引用与模型供应层级。</p>
            <div class="suggestion-grid"><button v-for="item in suggestions" :key="item" @click="useSuggestion(item)"><AppIcon name="sparkle" :size="15" />{{ item }}</button></div>
          </div>

          <div v-else class="message-list">
            <article v-for="message in messages" :key="message.id" class="message" :class="`message-${message.role}`">
              <div class="message-avatar"><AppIcon :name="message.role === 'assistant' ? 'sparkle' : 'chat'" :size="17" /></div>
              <div class="message-content">
                <div class="message-meta"><strong>{{ message.role === 'assistant' ? 'Knowledge Agent' : '你' }}</strong><span v-if="message.role === 'assistant'">{{ tierLabel(message.tier) }}</span><span v-if="message.status === 'failed'" class="message-failed">生成中断</span></div>
                <div class="message-text" :class="{ 'stream-cursor': message.status === 'streaming' }">{{ message.content || '正在分析知识库…' }}</div>
                <div v-if="message.fallback" class="fallback-note"><AppIcon name="alert" :size="14" />{{ message.fallback }}</div>
                <details v-if="message.citations.length" class="citations">
                  <summary><span><AppIcon name="file" :size="14" />{{ message.citations.length }} 个引用来源</span><span>展开</span></summary>
                  <div class="citation-list"><div v-for="(citation, index) in message.citations" :key="citation.chunk_id" class="citation-item"><span class="citation-number">{{ index + 1 }}</span><div><strong>{{ citation.source_name }}</strong><p>{{ citation.deleted ? '来源文档已删除' : citation.excerpt }}</p><span class="mono">{{ citation.chunk_id }}</span></div></div></div>
                </details>
              </div>
            </article>
          </div>
        </div>

        <div v-if="error" class="chat-error"><AppIcon name="alert" :size="15" />{{ error }}</div>
        <div class="composer-wrap">
          <textarea v-model="question" class="composer" rows="1" maxlength="4000" placeholder="输入问题，Enter 发送，Shift + Enter 换行" :disabled="sending" @keydown="onComposerKeydown" />
          <button class="send-button" :disabled="!question.trim() || sending" aria-label="发送问题" @click="sendMessage"><AppIcon name="send" :size="19" /></button>
          <div class="composer-foot"><span>答案可能存在偏差，请结合引用核验</span><span>{{ question.length }} / 4000</span></div>
        </div>
      </div>

      <aside class="chat-settings">
        <div class="panel settings-panel">
          <div class="panel-header"><div class="panel-title"><span class="panel-title-icon"><AppIcon name="database" /></span><div><h2>检索设置</h2><p>本会话生效</p></div></div></div>
          <div class="panel-body settings-body">
            <div class="field"><label>检索模式</label><select v-model="retrievalMode" class="select" :disabled="sending"><option value="hybrid">Hybrid · 混合检索</option><option value="vector">Vector · 向量检索</option><option value="keyword">Keyword · 关键词检索</option></select></div>
            <div class="field"><label>引用数量 Top K</label><div class="range-row"><input v-model.number="topK" type="range" min="1" max="20" :disabled="sending" /><span class="range-value">{{ topK }}</span></div></div>
            <label class="toggle-row"><div><strong>流式输出</strong><span>使用 SSE 实时显示 Token</span></div><input v-model="streaming" type="checkbox" :disabled="sending" /><i /></label>
          </div>
        </div>
        <div class="panel session-panel">
          <div class="panel-body"><p class="eyebrow">CURRENT SESSION</p><strong>{{ sessionId ? '会话已持久化' : '新会话' }}</strong><code>{{ sessionId || '发送首条消息后生成 ID' }}</code><div class="session-stats"><span><strong>{{ messages.filter((item) => item.role === 'user').length }}</strong>轮对话</span><span><strong>{{ messages.reduce((sum, item) => sum + item.citations.length, 0) }}</strong>条引用</span></div></div>
        </div>
      </aside>
    </div>
  </section>
</template>

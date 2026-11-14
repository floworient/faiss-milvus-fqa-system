<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api, formatApiError } from '../api/client'
import type { DocumentResponse, TaskResponse } from '../api/types'
import AppIcon from '../components/AppIcon.vue'
import EmptyState from '../components/EmptyState.vue'
import PageHeader from '../components/PageHeader.vue'
import StatusPill from '../components/StatusPill.vue'

const documents = ref<DocumentResponse[]>([])
const loading = ref(true)
const uploading = ref(false)
const dragging = ref(false)
const error = ref('')
const activeTask = ref<TaskResponse | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)

const totalChunks = computed(() => documents.value.reduce((sum, item) => sum + item.chunk_count, 0))
const averageChunks = computed(() => documents.value.length ? (totalChunks.value / documents.value.length).toFixed(1) : '0')

async function loadDocuments() {
  loading.value = true
  error.value = ''
  try {
    documents.value = await api.listDocuments()
  } catch (caught) {
    error.value = formatApiError(caught)
  } finally {
    loading.value = false
  }
}

function validateFile(file: File) {
  const suffix = file.name.split('.').pop()?.toLowerCase()
  if (!suffix || !['txt', 'json', 'md', 'markdown'].includes(suffix)) {
    throw new Error('仅支持 TXT、JSON、Markdown 文档')
  }
  if (file.size > 10 * 1024 * 1024) throw new Error('文件不能超过 10 MiB')
}

async function upload(file: File) {
  error.value = ''
  uploading.value = true
  try {
    validateFile(file)
    const task = await api.uploadDocument(file)
    activeTask.value = task
    activeTask.value = await api.waitForTask(task.task_id)
    await loadDocuments()
  } catch (caught) {
    error.value = formatApiError(caught)
  } finally {
    uploading.value = false
  }
}

function onFileChange(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (file) void upload(file)
  ;(event.target as HTMLInputElement).value = ''
}

function onDrop(event: DragEvent) {
  dragging.value = false
  const file = event.dataTransfer?.files?.[0]
  if (file) void upload(file)
}

async function removeDocument(document: DocumentResponse) {
  if (!window.confirm(`确认删除“${document.source_name}”？索引和历史引用将同步更新。`)) return
  error.value = ''
  try {
    const task = await api.deleteDocument(document.document_id)
    activeTask.value = task
    activeTask.value = await api.waitForTask(task.task_id)
    await loadDocuments()
  } catch (caught) {
    error.value = formatApiError(caught)
  }
}

function formatSizeHint(name: string) {
  const ext = name.split('.').pop()?.toUpperCase()
  return ext === 'MD' || ext === 'MARKDOWN' ? 'Markdown' : ext || 'TEXT'
}

onMounted(loadDocuments)
</script>

<template>
  <section>
    <PageHeader
      eyebrow="Knowledge Base"
      title="知识库"
      description="上传结构化知识文档，系统会自动解析、分块、向量化，并以原子版本发布到混合索引。"
    >
      <button class="button" :disabled="loading" @click="loadDocuments">
        <AppIcon name="refresh" :class="{ spinning: loading }" :size="16" />刷新
      </button>
      <button class="button button-primary" :disabled="uploading" @click="fileInput?.click()">
        <AppIcon name="upload" :size="16" />{{ uploading ? '处理中…' : '上传文档' }}
      </button>
      <input ref="fileInput" hidden type="file" accept=".txt,.json,.md,.markdown" @change="onFileChange" />
    </PageHeader>

    <div class="metric-grid knowledge-metrics">
      <div class="metric-card"><span class="metric-label">有效文档</span><strong class="metric-value">{{ documents.length }}</strong><span class="metric-hint">当前活动索引</span></div>
      <div class="metric-card"><span class="metric-label">知识分块</span><strong class="metric-value">{{ totalChunks }}</strong><span class="metric-hint">可检索 Chunk</span></div>
      <div class="metric-card"><span class="metric-label">平均分块</span><strong class="metric-value">{{ averageChunks }}</strong><span class="metric-hint">Chunk / 文档</span></div>
      <div class="metric-card"><span class="metric-label">索引策略</span><strong class="metric-value metric-text">Hybrid</strong><span class="metric-hint">Faiss + Keyword + RRF</span></div>
    </div>

    <div v-if="error" class="notice notice-error page-notice"><AppIcon name="alert" :size="17" />{{ error }}</div>
    <div v-if="activeTask" class="notice page-notice">
      <AppIcon :name="activeTask.status === 'succeeded' ? 'check' : 'refresh'" :class="{ spinning: ['pending', 'running'].includes(activeTask.status) }" :size="17" />
      <span>任务 <span class="mono">{{ activeTask.task_id }}</span> · {{ activeTask.action === 'upload' ? '文档入库' : '删除文档' }} · {{ activeTask.status }}</span>
    </div>

    <div class="grid-sidebar knowledge-layout">
      <div class="panel">
        <div class="panel-header">
          <div class="panel-title"><span class="panel-title-icon"><AppIcon name="database" /></span><div><h2>文档列表</h2><p>当前可用于问答与检索的知识来源</p></div></div>
          <StatusPill tone="success" :label="`${documents.length} active`" />
        </div>
        <div v-if="loading" class="document-list">
          <div v-for="index in 3" :key="index" class="document-row"><span class="document-file skeleton" /><div class="document-info"><span class="skeleton skeleton-line" /><span class="skeleton skeleton-line short" /></div></div>
        </div>
        <EmptyState v-else-if="documents.length === 0" icon="database" title="知识库还是空的" description="上传第一份 TXT、JSON 或 Markdown 文档，开始构建可检索知识库。">
          <button class="button button-primary" @click="fileInput?.click()"><AppIcon name="upload" :size="15" />上传文档</button>
        </EmptyState>
        <div v-else class="document-list">
          <article v-for="document in documents" :key="document.document_id" class="document-row">
            <span class="document-file"><AppIcon name="file" /></span>
            <div class="document-info">
              <div class="document-title-row"><strong>{{ document.source_name }}</strong><StatusPill tone="success" label="已索引" /></div>
              <div class="document-meta"><span>{{ formatSizeHint(document.source_name) }}</span><span>{{ document.chunk_count }} 个分块</span><span class="mono">{{ document.document_id.slice(0, 14) }}…</span></div>
            </div>
            <button class="icon-button delete-button" :aria-label="`删除 ${document.source_name}`" @click="removeDocument(document)"><AppIcon name="trash" :size="17" /></button>
          </article>
        </div>
      </div>

      <aside class="panel upload-panel">
        <div class="panel-header"><div class="panel-title"><span class="panel-title-icon"><AppIcon name="upload" /></span><div><h2>快速入库</h2><p>拖放即可上传</p></div></div></div>
        <div class="panel-body">
          <button
            class="drop-zone"
            :class="{ 'drop-zone-active': dragging }"
            :disabled="uploading"
            @click="fileInput?.click()"
            @dragover.prevent="dragging = true"
            @dragleave.prevent="dragging = false"
            @drop.prevent="onDrop"
          >
            <span class="drop-icon"><AppIcon name="upload" :size="25" /></span>
            <strong>{{ uploading ? '正在解析并构建索引' : '拖放文档到这里' }}</strong>
            <small>或点击选择本地文件</small>
          </button>
          <div class="upload-rules">
            <div><span>支持格式</span><strong>TXT · JSON · MD</strong></div>
            <div><span>大小限制</span><strong>≤ 10 MiB</strong></div>
            <div><span>处理方式</span><strong>异步任务</strong></div>
          </div>
        </div>
      </aside>
    </div>
  </section>
</template>

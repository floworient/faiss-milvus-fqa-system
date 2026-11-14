<script setup lang="ts">
import { computed, ref } from 'vue'
import { api, formatApiError } from '../api/client'
import type { RetrievalMode, RetrievalSearchResponse } from '../api/types'
import AppIcon from '../components/AppIcon.vue'
import EmptyState from '../components/EmptyState.vue'
import PageHeader from '../components/PageHeader.vue'
import StatusPill from '../components/StatusPill.vue'

const query = ref('')
const mode = ref<RetrievalMode>('hybrid')
const topK = ref(5)
const candidateK = ref(20)
const loading = ref(false)
const error = ref('')
const response = ref<RetrievalSearchResponse | null>(null)
const modes: RetrievalMode[] = ['hybrid', 'vector', 'keyword']

const topScore = computed(() => response.value?.results[0]?.score ?? 0)
const sources = computed(() => new Set(response.value?.results.map((item) => item.document_id)).size)

async function search() {
  if (!query.value.trim() || loading.value) return
  loading.value = true
  error.value = ''
  try {
    response.value = await api.search(
      query.value.trim(),
      mode.value,
      topK.value,
      Math.max(candidateK.value, topK.value),
    )
  } catch (caught) {
    error.value = formatApiError(caught)
    response.value = null
  } finally {
    loading.value = false
  }
}

function useExample(text: string) {
  query.value = text
  void search()
}
</script>

<template>
  <section>
    <PageHeader eyebrow="Retrieval Lab" title="检索调试" description="直接观察向量、关键词和 RRF 混合召回结果，定位知识覆盖与排序问题。">
      <StatusPill :tone="mode === 'hybrid' ? 'info' : 'neutral'" :label="`${mode.toUpperCase()} MODE`" />
    </PageHeader>

    <div class="panel search-console">
      <form class="search-form" @submit.prevent="search">
        <div class="search-input-wrap"><AppIcon name="search" :size="20" /><input v-model="query" class="search-input" maxlength="4000" placeholder="输入需要验证的检索问题，例如：退货政策是什么？" /><button class="button button-primary" :disabled="!query.trim() || loading" type="submit">{{ loading ? '检索中…' : '开始检索' }}</button></div>
        <div class="search-options">
          <div class="mode-tabs" role="radiogroup" aria-label="检索模式">
            <button v-for="item in modes" :key="item" type="button" :class="{ active: mode === item }" @click="mode = item">{{ item === 'hybrid' ? '混合检索' : item === 'vector' ? '向量检索' : '关键词检索' }}</button>
          </div>
          <div class="compact-range"><span>Top K</span><input v-model.number="topK" type="range" min="1" max="20" /><strong>{{ topK }}</strong></div>
          <div class="compact-range"><span>候选数</span><input v-model.number="candidateK" type="range" min="5" max="100" step="5" /><strong>{{ candidateK }}</strong></div>
        </div>
      </form>
    </div>

    <div class="example-row"><span>试试：</span><button @click="useExample('退货政策是什么？')">退货政策</button><button @click="useExample('如何联系人工客服？')">人工客服</button><button @click="useExample('发票如何开具？')">发票开具</button></div>
    <div v-if="error" class="notice notice-error page-notice"><AppIcon name="alert" :size="17" />{{ error }}</div>
    <div v-if="response?.degraded_from" class="notice notice-warning page-notice"><AppIcon name="alert" :size="17" />{{ response.degraded_from }} 已降级：{{ response.degradation_reason }}</div>

    <div v-if="response" class="search-summary">
      <div><span>返回结果</span><strong>{{ response.results.length }}</strong></div>
      <div><span>知识来源</span><strong>{{ sources }}</strong></div>
      <div><span>最高得分</span><strong>{{ topScore.toFixed(4) }}</strong></div>
      <div><span>检索模式</span><strong>{{ response.mode }}</strong></div>
    </div>

    <div v-if="loading" class="result-list">
      <div v-for="index in 3" :key="index" class="result-card"><div class="result-rank skeleton" /><div class="result-main"><span class="skeleton skeleton-line" /><span class="skeleton skeleton-line long" /><span class="skeleton skeleton-line" /></div></div>
    </div>
    <EmptyState v-else-if="!response" icon="search" title="等待检索问题" description="选择检索模式并输入问题，结果会展示融合得分、双路排名和原始片段。" />
    <EmptyState v-else-if="response.results.length === 0" icon="search" title="没有召回结果" description="尝试更换表达方式、切换检索模式，或先向知识库上传相关文档。" />
    <div v-else class="result-list">
      <article v-for="item in response.results" :key="item.chunk_id" class="result-card">
        <div class="result-rank"><span>#</span>{{ item.rank }}</div>
        <div class="result-main">
          <div class="result-head"><div><strong>{{ item.source || '未知来源' }}</strong><span class="mono">{{ item.chunk_id }}</span></div><span class="score-badge">{{ item.score.toFixed(5) }}</span></div>
          <p>{{ item.text }}</p>
          <div class="result-foot"><span>位置 {{ item.position + 1 }}</span><span>Vector Rank: {{ item.vector_rank ?? '—' }}</span><span>Keyword Rank: {{ item.keyword_rank ?? '—' }}</span><span class="mono">{{ item.document_id }}</span></div>
        </div>
      </article>
    </div>
  </section>
</template>

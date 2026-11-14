<script setup lang="ts">
import { computed, ref } from 'vue'
import { api, formatApiError } from '../api/client'
import type { EvaluationReport, RetrievalMode } from '../api/types'
import AppIcon from '../components/AppIcon.vue'
import EmptyState from '../components/EmptyState.vue'
import PageHeader from '../components/PageHeader.vue'
import StatusPill from '../components/StatusPill.vue'

const file = ref<File | null>(null)
const mode = ref<RetrievalMode>('hybrid')
const topK = ref(5)
const loading = ref(false)
const dragging = ref(false)
const error = ref('')
const report = ref<EvaluationReport | null>(null)
const input = ref<HTMLInputElement | null>(null)

const fileSize = computed(() => file.value ? `${Math.max(file.value.size / 1024, 0.1).toFixed(1)} KiB` : '')
const pct = (value: number | null) => value === null ? '—' : `${(value * 100).toFixed(1)}%`

function selectFile(selected?: File) {
  if (!selected) return
  if (!selected.name.toLowerCase().endsWith('.jsonl')) {
    error.value = '评测数据集必须是 .jsonl 文件'
    return
  }
  file.value = selected
  error.value = ''
  report.value = null
}

function onDrop(event: DragEvent) {
  dragging.value = false
  selectFile(event.dataTransfer?.files?.[0])
}

function onFileChange(event: Event) {
  selectFile((event.target as HTMLInputElement).files?.[0])
  ;(event.target as HTMLInputElement).value = ''
}

async function runEvaluation() {
  if (!file.value || loading.value) return
  loading.value = true
  error.value = ''
  try {
    report.value = await api.evaluate(file.value, mode.value, topK.value)
  } catch (caught) {
    error.value = formatApiError(caught)
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <section>
    <PageHeader eyebrow="Evaluation Suite" title="效果评测" description="上传带相关性标签的 JSONL 数据集，复用线上检索链路计算 Hit@1、Recall@K 与 MRR。">
      <StatusPill tone="warning" label="离线评测" />
    </PageHeader>

    <div class="grid-sidebar evaluation-layout">
      <div>
        <div v-if="report" class="metric-grid evaluation-metrics">
          <div class="metric-card metric-accent"><span class="metric-label">Hit@1</span><strong class="metric-value">{{ pct(report.hit_at_1) }}</strong><span class="metric-hint">首条命中率</span></div>
          <div class="metric-card"><span class="metric-label">Recall@{{ report.top_k }}</span><strong class="metric-value">{{ pct(report.recall_at_k) }}</strong><span class="metric-hint">平均召回率</span></div>
          <div class="metric-card"><span class="metric-label">MRR</span><strong class="metric-value">{{ report.mrr.toFixed(3) }}</strong><span class="metric-hint">平均倒数排名</span></div>
          <div class="metric-card"><span class="metric-label">Answer Acc.</span><strong class="metric-value">{{ pct(report.answer_accuracy) }}</strong><span class="metric-hint">人工正确率</span></div>
        </div>

        <div v-if="error" class="notice notice-error page-notice"><AppIcon name="alert" :size="17" />{{ error }}</div>
        <div class="panel evaluation-results">
          <div class="panel-header"><div class="panel-title"><span class="panel-title-icon"><AppIcon name="chart" /></span><div><h2>查询明细</h2><p>逐问题分析首个相关排名和召回结果</p></div></div><StatusPill v-if="report" tone="success" :label="`${report.query_count} queries`" /></div>
          <EmptyState v-if="!report" icon="chart" title="尚未运行评测" description="在右侧上传带标签的 JSONL 数据集并启动评测，指标报告会显示在这里。" />
          <div v-else class="table-wrap">
            <table class="data-table">
              <thead><tr><th>查询</th><th>首个相关排名</th><th>Recall@K</th><th>返回数量</th></tr></thead>
              <tbody><tr v-for="item in report.queries" :key="item.query"><td>{{ item.query }}</td><td><span :class="['rank-chip', { missed: item.first_relevant_rank === null }]">{{ item.first_relevant_rank ?? '未命中' }}</span></td><td>{{ pct(item.recall_at_k) }}</td><td>{{ item.returned_chunk_ids.length }}</td></tr></tbody>
            </table>
          </div>
        </div>
      </div>

      <aside class="panel evaluation-config">
        <div class="panel-header"><div class="panel-title"><span class="panel-title-icon"><AppIcon name="file" /></span><div><h2>评测配置</h2><p>JSONL relevance labels</p></div></div></div>
        <div class="panel-body">
          <button class="dataset-drop" :class="{ active: dragging, selected: file }" @click="input?.click()" @dragover.prevent="dragging = true" @dragleave.prevent="dragging = false" @drop.prevent="onDrop">
            <span><AppIcon :name="file ? 'check' : 'upload'" :size="24" /></span>
            <strong>{{ file?.name || '选择 JSONL 数据集' }}</strong>
            <small>{{ file ? fileSize : '点击选择或拖放文件' }}</small>
          </button>
          <input ref="input" hidden type="file" accept=".jsonl,application/jsonl" @change="onFileChange" />
          <div class="field config-field"><label>检索模式</label><select v-model="mode" class="select"><option value="hybrid">Hybrid · 混合检索</option><option value="vector">Vector · 向量检索</option><option value="keyword">Keyword · 关键词</option></select></div>
          <div class="field config-field"><label>Top K</label><div class="range-row"><input v-model.number="topK" type="range" min="1" max="50" /><span class="range-value">{{ topK }}</span></div></div>
          <div class="dataset-format"><strong>数据格式</strong><code>{"query":"问题","relevant_document_ids":["doc_xxx"]}</code></div>
          <button class="button button-primary run-evaluation" :disabled="!file || loading" @click="runEvaluation"><AppIcon name="chart" :size="16" />{{ loading ? '正在评测…' : '运行检索评测' }}</button>
        </div>
      </aside>
    </div>
  </section>
</template>

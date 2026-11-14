<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { RouterLink, RouterView } from 'vue-router'
import { api } from './api/client'
import AppIcon from './components/AppIcon.vue'
import StatusPill from './components/StatusPill.vue'

const mobileOpen = ref(false)
const backendOnline = ref(false)
const checking = ref(true)
let healthTimer: number | undefined

const navItems = [
  { to: '/chat', label: '智能问答', hint: '对话与引用', icon: 'chat' },
  { to: '/knowledge', label: '知识库', hint: '文档与索引', icon: 'database' },
  { to: '/search', label: '检索调试', hint: '召回与排序', icon: 'search' },
  { to: '/evaluation', label: '效果评测', hint: '指标与数据集', icon: 'chart' },
]

async function checkHealth() {
  checking.value = true
  try {
    const result = await api.health()
    backendOnline.value = result.status === 'ok'
  } catch {
    backendOnline.value = false
  } finally {
    checking.value = false
  }
}

onMounted(() => {
  void checkHealth()
  healthTimer = window.setInterval(checkHealth, 30_000)
})

onBeforeUnmount(() => {
  if (healthTimer) window.clearInterval(healthTimer)
})
</script>

<template>
  <div class="app-shell">
    <div v-if="mobileOpen" class="sidebar-scrim" @click="mobileOpen = false" />
    <aside class="sidebar" :class="{ 'sidebar-open': mobileOpen }">
      <div class="brand-row">
        <div class="brand-mark" aria-hidden="true">
          <span class="node node-a" /><span class="node node-b" /><span class="node node-c" />
          <AppIcon name="chat" :size="23" />
        </div>
        <div class="brand-copy">
          <strong>RAG Knowledge</strong>
          <span>QA Console</span>
        </div>
        <button class="icon-button sidebar-close" aria-label="关闭菜单" @click="mobileOpen = false">
          <AppIcon name="close" />
        </button>
      </div>

      <div class="workspace-label">WORKSPACE</div>
      <nav class="nav-list" aria-label="主导航">
        <RouterLink
          v-for="item in navItems"
          :key="item.to"
          :to="item.to"
          class="nav-item"
          @click="mobileOpen = false"
        >
          <span class="nav-icon"><AppIcon :name="item.icon" /></span>
          <span><strong>{{ item.label }}</strong><small>{{ item.hint }}</small></span>
        </RouterLink>
      </nav>

      <div class="sidebar-spacer" />
      <div class="preview-card">
        <div class="preview-icon"><AppIcon name="sparkle" /></div>
        <div>
          <strong>开发预览版</strong>
          <p>接口与数据结构仍可能迭代，请勿直接暴露到公网。</p>
        </div>
      </div>
      <div class="sidebar-footer">
        <a href="/docs" target="_blank" rel="noreferrer">
          <AppIcon name="external" :size="16" /> API 文档
        </a>
        <span>v0.1.0</span>
      </div>
    </aside>

    <div class="main-column">
      <header class="topbar">
        <button class="icon-button mobile-menu" aria-label="打开菜单" @click="mobileOpen = true">
          <AppIcon name="menu" />
        </button>
        <div class="topbar-context">
          <span class="topbar-product">知识问答工作台</span>
          <span class="topbar-divider" />
          <span class="topbar-subtitle">Retrieve · Reason · Respond</span>
        </div>
        <div class="topbar-actions">
          <button class="icon-button" aria-label="刷新服务状态" :disabled="checking" @click="checkHealth">
            <AppIcon name="refresh" :class="{ spinning: checking }" />
          </button>
          <StatusPill
            :tone="checking ? 'neutral' : backendOnline ? 'success' : 'danger'"
            :label="checking ? '连接中' : backendOnline ? '服务正常' : '服务离线'"
          />
        </div>
      </header>

      <main class="content-area">
        <RouterView />
      </main>
    </div>
  </div>
</template>

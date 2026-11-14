import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'
import ChatView from './views/ChatView.vue'
import EvaluationView from './views/EvaluationView.vue'
import KnowledgeView from './views/KnowledgeView.vue'
import SearchView from './views/SearchView.vue'
import './styles.css'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/chat' },
    { path: '/chat', component: ChatView, meta: { title: '智能问答' } },
    { path: '/knowledge', component: KnowledgeView, meta: { title: '知识库' } },
    { path: '/search', component: SearchView, meta: { title: '检索调试' } },
    { path: '/evaluation', component: EvaluationView, meta: { title: '效果评测' } },
  ],
})

router.afterEach((to) => {
  document.title = `${String(to.meta.title ?? '控制台')} · RAG Knowledge QA`
})

createApp(App).use(router).mount('#app')

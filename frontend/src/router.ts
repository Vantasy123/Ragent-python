import { createRouter, createWebHistory } from 'vue-router'
import LoginPage from '@/pages/LoginPage.vue'
import ChatPage from '@/pages/ChatPage.vue'
import KnowledgeBasePage from '@/pages/KnowledgeBasePage.vue'
import AdminLayout from '@/pages/AdminLayout.vue'
import DashboardPage from '@/pages/DashboardPage.vue'
import TracePage from '@/pages/TracePage.vue'
import SettingsPage from '@/pages/SettingsPage.vue'
import UsersPage from '@/pages/UsersPage.vue'
import IngestionPage from '@/pages/IngestionPage.vue'
import IntentTreePage from '@/pages/IntentTreePage.vue'
import SampleQuestionPage from '@/pages/SampleQuestionPage.vue'
import MappingPage from '@/pages/MappingPage.vue'
import { useAuthStore } from '@/stores/authStore'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/chat' },
    { path: '/login', component: LoginPage },
    { path: '/chat', component: ChatPage, meta: { requiresAuth: true } },
    { path: '/knowledge', component: KnowledgeBasePage, meta: { requiresAuth: true, requiresAdmin: true } },
    {
      path: '/admin',
      component: AdminLayout,
      meta: { requiresAuth: true, requiresAdmin: true },
      children: [
        { path: '', redirect: '/admin/dashboard' },
        { path: 'dashboard', component: DashboardPage },
        { path: 'knowledge', component: KnowledgeBasePage },
        { path: 'ingestion', component: IngestionPage },
        { path: 'traces', component: TracePage },
        { path: 'settings', component: SettingsPage },
        { path: 'users', component: UsersPage },
        { path: 'intent-tree', component: IntentTreePage },
        { path: 'sample-questions', component: SampleQuestionPage },
        { path: 'mappings', component: MappingPage },
      ],
    },
  ],
})

router.beforeEach((to) => {
  const auth = useAuthStore()
  if (to.meta.requiresAuth && !auth.isAuthenticated) {
    return '/login'
  }
  if (to.meta.requiresAdmin && auth.user?.role !== 'admin') {
    return '/chat'
  }
  if (to.path === '/login' && auth.isAuthenticated) {
    return auth.user?.role === 'admin' ? '/admin/dashboard' : '/chat'
  }
  return true
})

export default router

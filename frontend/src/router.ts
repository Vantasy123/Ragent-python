import { createRouter, createWebHistory } from 'vue-router'
import LoginPage from '@/pages/LoginPage.vue'
import UserLayout from '@/layouts/UserLayout.vue'
import ChatPage from '@/pages/ChatPage.vue'

// 求职用户业务页面
import ResumeCenterPage from '@/pages/job/ResumeCenterPage.vue'
import JobMatchingPage from '@/pages/job/JobMatchingPage.vue'
import JobKanbanPage from '@/pages/job/JobKanbanPage.vue'
import MockInterviewPage from '@/pages/job/MockInterviewPage.vue'
import JobAutoFillPage from '@/pages/job/JobAutoFillPage.vue'
import JobDashboardPage from '@/pages/job/JobDashboardPage.vue'

// 后台管理与审计系统页面
import AdminLayout from '@/pages/AdminLayout.vue'
import DashboardPage from '@/pages/DashboardPage.vue'
import EvaluationPage from '@/pages/EvaluationPage.vue'
import TracePage from '@/pages/TracePage.vue'
import TraceDetailPage from '@/pages/TraceDetailPage.vue'
import SettingsPage from '@/pages/SettingsPage.vue'
import UsersPage from '@/pages/UsersPage.vue'
import SecurityAuditPage from '@/pages/SecurityAuditPage.vue'
import IngestionPage from '@/pages/IngestionPage.vue'
import KnowledgeBasePage from '@/pages/KnowledgeBasePage.vue'
import KnowledgeDocumentsPage from '@/pages/KnowledgeDocumentsPage.vue'
import KnowledgeChunksPage from '@/pages/KnowledgeChunksPage.vue'

import { useAuthStore } from '@/stores/authStore'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', component: LoginPage },

    // 用户求职工作台（所有已登录用户可用）
    {
      path: '/',
      component: UserLayout,
      meta: { requiresAuth: true },
      children: [
        { path: '', redirect: '/chat' },
        { path: 'chat', component: ChatPage },
        { path: 'resumes', component: ResumeCenterPage },
        { path: 'job-matching', component: JobMatchingPage },
        { path: 'job-kanban', component: JobKanbanPage },
        { path: 'mock-interviews', component: MockInterviewPage },
        { path: 'job-autofill', component: JobAutoFillPage },
        { path: 'job-dashboard', component: JobDashboardPage },
      ],
    },

    // 系统管理与审计控制台（仅管理员可用）
    {
      path: '/admin',
      component: AdminLayout,
      meta: { requiresAuth: true, requiresAdmin: true },
      children: [
        { path: '', redirect: '/admin/dashboard' },
        { path: 'dashboard', component: DashboardPage },
        { path: 'knowledge', component: KnowledgeBasePage },
        { path: 'knowledge/:kbId', component: KnowledgeDocumentsPage },
        { path: 'knowledge/:kbId/docs/:docId', component: KnowledgeChunksPage },
        { path: 'ingestion', component: IngestionPage },
        { path: 'traces', component: TracePage },
        { path: 'traces/:traceId', component: TraceDetailPage },
        { path: 'evaluations', component: EvaluationPage },
        { path: 'settings', component: SettingsPage },
        { path: 'users', component: UsersPage },
        { path: 'security-audit', component: SecurityAuditPage },

        // 兼容旧路径重定向至用户工作台业务页面
        { path: 'job-dashboard', redirect: '/job-dashboard' },
        { path: 'resumes', redirect: '/resumes' },
        { path: 'job-matching', redirect: '/job-matching' },
        { path: 'job-kanban', redirect: '/job-kanban' },
        { path: 'mock-interviews', redirect: '/mock-interviews' },
        { path: 'job-autofill', redirect: '/job-autofill' },
      ],
    },

    { path: '/knowledge', redirect: '/admin/knowledge' },
    { path: '/:pathMatch(.*)*', redirect: '/chat' },
  ],
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  await auth.restoreSession()

  if (to.meta.requiresAuth && !auth.isAuthenticated) {
    return { path: '/login', query: { redirect: to.fullPath } }
  }
  if (to.meta.requiresAdmin && auth.user?.role !== 'admin') {
    return '/chat'
  }
  if (to.path === '/login' && auth.isAuthenticated) {
    return typeof to.query.redirect === 'string'
      ? to.query.redirect
      : '/chat'
  }
  return true
})

export default router

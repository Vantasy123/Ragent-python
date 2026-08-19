<template>
  <div class="admin-shell">
    <aside class="admin-sidebar">
      <div class="admin-brand">
        <div class="admin-brand-subtitle">系统管理与审计中心</div>
        <div class="admin-brand-title">Ragent 管理后台</div>
        <div class="helper-text mt-2 text-xs !text-slate-400">
          聚焦系统运行大盘、知识库工程、链路追踪、智能体评测、安全合规审计与系统配置。
        </div>
      </div>

      <!-- 监控与评估体系 -->
      <div class="sidebar-group">
        <div class="sidebar-section-label">📈 监控与评估体系</div>
        <router-link v-for="item in monitorItems" :key="item.to" :to="item.to" class="sidebar-link">
          <span>{{ item.label }}</span>
          <span class="muted text-xs font-medium">{{ item.hint }}</span>
        </router-link>
      </div>

      <!-- 知识与数据治理 -->
      <div class="sidebar-group">
        <div class="sidebar-section-label">📚 知识与数据治理</div>
        <router-link v-for="item in baseItems" :key="item.to" :to="item.to" class="sidebar-link">
          <span>{{ item.label }}</span>
          <span class="muted text-xs font-medium">{{ item.hint }}</span>
        </router-link>
      </div>

      <!-- 系统设置与安全审计 -->
      <div class="sidebar-group">
        <div class="sidebar-section-label">⚙️ 安全审计与系统管理</div>
        <router-link v-for="item in systemItems" :key="item.to" :to="item.to" class="sidebar-link">
          <span>{{ item.label }}</span>
          <span class="muted text-xs font-medium">{{ item.hint }}</span>
        </router-link>
      </div>

      <div class="sidebar-footer">
        <router-link to="/chat" class="btn btn-primary w-full justify-center text-xs shadow-sm">
          🏠 返回用户求职工作台
        </router-link>
        <button class="btn btn-ghost w-full justify-center text-xs !text-slate-400 hover:!text-slate-200 cursor-pointer" @click="logout">
          退出登录
        </button>
      </div>
    </aside>

    <main class="admin-main">
      <div class="topbar">
        <div class="topbar-card flex-1">
          <div>
            <div class="meta-label !text-slate-500">管理后台</div>
            <div class="mt-1 text-lg font-semibold text-slate-900">Ragent 系统与审计控制台</div>
          </div>
          <div class="flex items-center gap-3">
            <router-link to="/chat" class="btn btn-secondary text-xs">
              返回工作台
            </router-link>
            <div class="text-right border-l border-slate-200 pl-3">
              <div class="meta-label !text-slate-500">管理员</div>
              <div class="mt-1 font-semibold text-slate-900">{{ auth.user?.nickname || auth.user?.username || 'admin' }}</div>
            </div>
          </div>
        </div>
      </div>
      <router-view />
    </main>
  </div>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/authStore'

const router = useRouter()
const auth = useAuthStore()

const monitorItems = [
  { to: '/admin/dashboard', label: '系统运行大盘', hint: 'Overview' },
  { to: '/admin/traces', label: 'Agent 链路追踪', hint: 'Trace' },
  { to: '/admin/evaluations', label: '智能体评测基准', hint: 'Evals' },
]

const baseItems = [
  { to: '/admin/knowledge', label: '八股面经知识库', hint: 'RAG' },
  { to: '/admin/ingestion', label: 'ETL 摄取流水线', hint: 'Pipeline' },
]

const systemItems = [
  { to: '/admin/users', label: '用户与权限管理', hint: 'RBAC' },
  { to: '/admin/security-audit', label: '安全合规与审计', hint: 'Audit' },
  { to: '/admin/settings', label: '大模型与系统配置', hint: 'Config' },
]

async function logout() {
  await auth.logout()
  await router.replace('/login')
}
</script>

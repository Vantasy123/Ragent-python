<template>
  <div class="admin-shell">
    <aside class="admin-sidebar">
      <div class="admin-brand">
        <div class="admin-brand-subtitle">Enterprise Console</div>
        <div class="admin-brand-title">Ragent Admin</div>
        <div class="helper-text mt-2 text-sm !text-slate-300/80">
          面向知识库、摄取、链路追踪和运营配置的一体化控制台。
        </div>
      </div>

      <div class="sidebar-group">
        <div class="sidebar-section-label">Core</div>
        <router-link v-for="item in primaryItems" :key="item.to" :to="item.to" class="sidebar-link">
          <span>{{ item.label }}</span>
          <span class="muted text-xs">{{ item.hint }}</span>
        </router-link>
      </div>

      <div class="sidebar-group">
        <div class="sidebar-section-label">Operations</div>
        <router-link v-for="item in operationItems" :key="item.to" :to="item.to" class="sidebar-link">
          <span>{{ item.label }}</span>
          <span class="muted text-xs">{{ item.hint }}</span>
        </router-link>
      </div>

      <div class="sidebar-footer">
        <router-link to="/chat" class="btn btn-secondary">返回聊天工作台</router-link>
        <button class="btn btn-ghost" @click="logout">退出登录</button>
      </div>
    </aside>

    <main class="admin-main">
      <div class="topbar">
        <div class="topbar-card flex-1">
          <div>
            <div class="meta-label !text-slate-500">Current Workspace</div>
            <div class="mt-1 text-lg font-semibold">ragent-python / admin</div>
          </div>
          <div class="text-right">
            <div class="meta-label !text-slate-500">Signed in as</div>
            <div class="mt-1 font-semibold">{{ auth.user?.nickname || auth.user?.username || 'admin' }}</div>
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

const primaryItems = [
  { to: '/admin/dashboard', label: '仪表盘', hint: 'overview' },
  { to: '/admin/knowledge', label: '知识库', hint: 'docs' },
  { to: '/admin/ingestion', label: '摄取任务', hint: 'pipelines' },
  { to: '/admin/traces', label: '链路追踪', hint: 'runs' },
  { to: '/admin/settings', label: '系统设置', hint: 'config' },
]

const operationItems = [
  { to: '/admin/users', label: '用户管理', hint: 'accounts' },
  { to: '/admin/intent-tree', label: '意图树', hint: 'routing' },
  { to: '/admin/sample-questions', label: '示例问题', hint: 'prompts' },
  { to: '/admin/mappings', label: '术语映射', hint: 'terms' },
]

async function logout() {
  await auth.logout()
  router.push('/login')
}
</script>

<template>
  <div class="admin-shell">
    <aside class="admin-sidebar">
      <div class="admin-brand">
        <div class="admin-brand-subtitle">企业控制台</div>
        <div class="admin-brand-title">Ragent 管理后台</div>
        <div class="helper-text mt-2 text-sm !text-slate-300/80">
          对齐原版后台信息架构，覆盖知识库、摄取、链路追踪、评估与运营配置。
        </div>
      </div>

      <div class="sidebar-group">
        <div class="sidebar-section-label">核心能力</div>
        <router-link v-for="item in primaryItems" :key="item.to" :to="item.to" class="sidebar-link">
          <span>{{ item.label }}</span>
          <span class="muted text-xs">{{ item.hint }}</span>
        </router-link>
      </div>

      <div class="sidebar-group">
        <div class="sidebar-section-label">运营配置</div>
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
            <div class="meta-label !text-slate-500">当前工作区</div>
            <div class="mt-1 text-lg font-semibold">ragent-python / 管理后台</div>
          </div>
          <div class="text-right">
            <div class="meta-label !text-slate-500">当前登录用户</div>
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
  { to: '/admin/dashboard', label: '仪表盘', hint: '概览' },
  { to: '/admin/knowledge', label: '知识库', hint: '文档' },
  { to: '/admin/ingestion', label: '摄取任务', hint: '流程' },
  { to: '/admin/traces', label: '链路追踪', hint: '运行' },
  { to: '/admin/evaluations', label: '智能体评估', hint: '评分' },
  { to: '/admin/settings', label: '系统设置', hint: '配置' },
]

const operationItems = [
  { to: '/admin/users', label: '用户管理', hint: '账号' },
  { to: '/admin/intent-tree', label: '意图树', hint: '总览' },
  { to: '/admin/intent-list', label: '意图列表', hint: '编辑' },
  { to: '/admin/sample-questions', label: '示例问题', hint: '提示' },
  { to: '/admin/mappings', label: '术语映射', hint: '词表' },
]

async function logout() {
  await auth.logout()
  router.push('/login')
}
</script>

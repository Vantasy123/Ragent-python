<template>
  <div class="min-h-screen bg-slate-50 flex flex-col font-sans">
    <!-- Top Navigation Bar -->
    <header class="sticky top-0 z-30 bg-white/90 backdrop-blur-md border-b border-slate-200/80 shadow-2xs">
      <div class="max-w-[1600px] mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between gap-4">
        <!-- Logo & Brand -->
        <router-link to="/chat" class="flex items-center gap-3 shrink-0 hover:opacity-90 transition-opacity">
          <div class="w-9 h-9 rounded-xl bg-gradient-to-tr from-blue-600 to-indigo-600 flex items-center justify-center text-white font-black text-lg shadow-sm shadow-blue-500/20">
            R
          </div>
          <div>
            <div class="flex items-center gap-2">
              <span class="font-bold text-slate-900 text-base tracking-tight">Ragent</span>
              <span class="px-1.5 py-0.5 rounded-full text-[10px] font-bold bg-blue-50 text-blue-600 border border-blue-200">
                求职工作台
              </span>
            </div>
            <p class="text-[11px] text-slate-400 font-medium hidden sm:block">AI 智能求职 · 面试对练 · 人岗匹配</p>
          </div>
        </router-link>

        <!-- Navigation Links (7 大业务功能) -->
        <nav class="flex items-center gap-1 overflow-x-auto scrollbar-none py-1">
          <router-link
            v-for="item in navItems"
            :key="item.to"
            :to="item.to"
            :class="[
              'px-3 py-1.5 rounded-xl text-xs sm:text-sm font-semibold transition-all duration-200 flex items-center gap-1.5 shrink-0',
              route.path === item.to || (item.to !== '/chat' && route.path.startsWith(item.to))
                ? 'bg-blue-600 text-white shadow-sm shadow-blue-500/25'
                : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
            ]"
          >
            <span>{{ item.icon }}</span>
            <span>{{ item.label }}</span>
          </router-link>
        </nav>

        <!-- Right Side Actions -->
        <div class="flex items-center gap-3 shrink-0">
          <!-- Admin Console Switch (仅管理员可见) -->
          <router-link
            v-if="auth.user?.role === 'admin'"
            to="/admin/dashboard"
            class="hidden md:flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold bg-slate-100 text-slate-700 hover:bg-slate-200 border border-slate-200/80 transition-colors shadow-2xs"
          >
            <span>🛡️</span>
            <span>管理后台</span>
          </router-link>

          <!-- User Info & Logout -->
          <div class="flex items-center gap-2 border-l border-slate-200 pl-3">
            <div class="w-8 h-8 rounded-full bg-indigo-50 border border-indigo-200 flex items-center justify-center text-xs font-bold text-indigo-700">
              {{ (auth.user?.nickname || auth.user?.username || 'U').charAt(0).toUpperCase() }}
            </div>
            <div class="hidden lg:block text-left">
              <p class="text-xs font-bold text-slate-800 leading-tight">{{ auth.user?.nickname || auth.user?.username || '求职者' }}</p>
              <p class="text-[10px] text-slate-400 capitalize">{{ auth.user?.role === 'admin' ? '系统管理员' : '普通求职者' }}</p>
            </div>
            <button
              class="p-1.5 rounded-lg text-slate-400 hover:text-red-600 hover:bg-red-50 transition-colors text-xs font-medium cursor-pointer"
              title="退出登录"
              @click="handleLogout"
            >
              <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
              </svg>
            </button>
          </div>
        </div>
      </div>
    </header>

    <!-- Main Content Area -->
    <main class="flex-1 w-full flex flex-col">
      <!-- 对话台全屏沉浸，其他业务页面标准居中容器 -->
      <div v-if="route.path === '/chat'" class="flex-1 flex flex-col">
        <router-view />
      </div>
      <div v-else class="max-w-[1600px] w-full mx-auto p-4 sm:p-6 lg:p-8 flex-1">
        <router-view />
      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/authStore'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const navItems = [
  { to: '/chat', label: 'AI 对话', icon: '💬' },
  { to: '/resumes', label: '简历中枢', icon: '📄' },
  { to: '/job-matching', label: '岗位匹配', icon: '🎯' },
  { to: '/job-kanban', label: '投递看板', icon: '📋' },
  { to: '/mock-interviews', label: '模拟面试', icon: '🎙️' },
  { to: '/job-autofill', label: '自动网申', icon: '⚡' },
  { to: '/job-dashboard', label: '求职大盘', icon: '📊' },
]

async function handleLogout() {
  await auth.logout()
  await router.replace('/login')
}
</script>

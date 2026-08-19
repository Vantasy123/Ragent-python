<template>
  <div class="min-h-screen p-6 flex items-center justify-center">
    <div class="mx-auto grid min-h-[calc(100vh-8rem)] max-w-5xl items-center gap-12 lg:grid-cols-[1.1fr_0.9fr] w-full">
      <section class="panel border-slate-200 bg-white/70 p-8 rounded-2xl shadow-sm">
        <div class="page-eyebrow !text-blue-600 font-bold">Ragent Python 管理平台</div>
        <h1 class="mt-3 text-4xl font-extrabold leading-tight text-slate-800">把管理后台从 demo 提升为真正可运营的控制台</h1>
        <p class="page-description mt-5 max-w-2xl text-sm text-slate-500 leading-relaxed">
          统一管理知识库、摄取任务、意图树、运营配置与链路追踪。默认管理员账号可直接进入后台完成首次验收。
        </p>
        <div class="grid-three mt-8 gap-4">
          <div class="detail-item bg-slate-50 border border-slate-100 p-4 rounded-xl">
            <div class="meta-label !text-slate-400 font-semibold">后台管理</div>
            <div class="detail-value text-sm text-slate-700 mt-1">知识库与配置治理</div>
          </div>
          <div class="detail-item bg-slate-50 border border-slate-100 p-4 rounded-xl">
            <div class="meta-label !text-slate-400 font-semibold">智能对话</div>
            <div class="detail-value text-sm text-slate-700 mt-1">流式会话与追踪回传</div>
          </div>
          <div class="detail-item bg-slate-50 border border-slate-100 p-4 rounded-xl">
            <div class="meta-label !text-slate-400 font-semibold">链路追踪</div>
            <div class="detail-value text-sm text-slate-700 mt-1">运行与节点双层观测</div>
          </div>
        </div>
      </section>

      <section class="panel border-slate-200 bg-white p-8 rounded-2xl shadow-xl">
        <div class="page-eyebrow !text-slate-400 font-semibold">登录</div>
        <h2 class="mt-2 text-2xl font-bold text-slate-800">登录控制台</h2>
        <p class="page-description mt-2 text-xs text-slate-500">登录后可进入后台或聊天工作区。请使用已配置的账号登录。</p>
        <form class="mt-6 form-grid gap-4" @submit.prevent="submit">
          <input v-model="username" autocomplete="username" :disabled="loading" class="input border-slate-200 text-slate-800 placeholder-slate-400 focus:border-blue-500" placeholder="用户名" />
          <input v-model="password" type="password" autocomplete="current-password" :disabled="loading" class="input border-slate-200 text-slate-800 placeholder-slate-400 focus:border-blue-500" placeholder="密码" />
          <button :disabled="loading || !username.trim() || !password" class="btn btn-primary w-full bg-blue-600 hover:bg-blue-500 text-white font-bold py-2.5 rounded-xl transition-all disabled:cursor-not-allowed disabled:opacity-60">{{ loading ? '登录中…' : '登录' }}</button>
        </form>
        <p v-if="error" class="mt-4 text-xs text-red-600">{{ error }}</p>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/authStore'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()
const username = ref('')
const password = ref('')
const error = ref('')
const loading = ref(false)
const redirect = computed(() => typeof route.query.redirect === 'string' ? route.query.redirect : '')

async function submit() {
  error.value = ''
  loading.value = true
  try {
    await auth.login(username.value, password.value)
    router.replace(redirect.value || '/chat')
  } catch (err: any) {
    error.value = err?.detail || err?.message || '登录失败'
  } finally {
    loading.value = false
  }
}
</script>

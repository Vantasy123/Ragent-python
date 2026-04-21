<template>
  <div class="min-h-screen p-6">
    <div class="mx-auto grid min-h-[calc(100vh-3rem)] max-w-6xl items-center gap-8 lg:grid-cols-[1.2fr_0.8fr]">
      <section class="panel">
        <div class="page-eyebrow !text-slate-500">Ragent Python</div>
        <h1 class="mt-3 text-5xl font-black leading-tight">把管理后台从 demo 提升为真正可运营的控制台。</h1>
        <p class="page-description mt-5 max-w-2xl text-lg">
          统一管理知识库、摄取任务、意图树、运营配置与链路追踪。默认管理员账号可直接进入后台完成首次验收。
        </p>
        <div class="grid-three mt-8">
          <div class="detail-item">
            <div class="meta-label !text-slate-500">Admin</div>
            <div class="detail-value">知识库与配置治理</div>
          </div>
          <div class="detail-item">
            <div class="meta-label !text-slate-500">Chat</div>
            <div class="detail-value">SSE 会话与 Trace 回传</div>
          </div>
          <div class="detail-item">
            <div class="meta-label !text-slate-500">Trace</div>
            <div class="detail-value">Run / Node 双层观测</div>
          </div>
        </div>
      </section>

      <section class="panel">
        <div class="page-eyebrow !text-slate-500">Sign In</div>
        <h2 class="mt-3 text-3xl font-bold">登录控制台</h2>
        <p class="page-description mt-3">登录后可进入后台或聊天工作区。默认管理员为 `admin / admin123`。</p>
        <form class="mt-8 form-grid" @submit.prevent="submit">
          <input v-model="username" class="input" placeholder="用户名" />
          <input v-model="password" type="password" class="input" placeholder="密码" />
          <button class="btn btn-primary w-full">登录</button>
        </form>
        <p v-if="error" class="mt-4 text-sm text-red-600">{{ error }}</p>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/authStore'

const router = useRouter()
const auth = useAuthStore()
const username = ref('admin')
const password = ref('admin123')
const error = ref('')

async function submit() {
  error.value = ''
  try {
    await auth.login(username.value, password.value)
    router.push(auth.user?.role === 'admin' ? '/admin/dashboard' : '/chat')
  } catch (err: any) {
    error.value = err?.detail || err?.message || '登录失败'
  }
}
</script>

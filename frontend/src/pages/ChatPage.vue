<template>
  <div class="conversation-shell">
    <aside class="conversation-sidebar">
      <div class="topbar-card !min-h-0 !p-0 !bg-transparent !shadow-none !border-none">
        <div>
          <div class="meta-label !text-slate-500">Conversation Workspace</div>
          <div class="mt-1 text-2xl font-semibold">Ragent Chat</div>
          <div class="helper-text mt-2 text-sm">用于验证会话、SSE 流和 Trace 回传是否正常工作。</div>
        </div>
        <router-link v-if="auth.user?.role === 'admin'" to="/admin/dashboard" class="btn btn-secondary">进入后台</router-link>
      </div>

      <div class="inline-actions">
        <button class="btn btn-primary" @click="startConversation">新建会话</button>
        <button class="btn btn-secondary" @click="refresh">刷新列表</button>
      </div>

      <SurfaceCard compact>
        <KeyValueGrid
          :columns="1"
          :items="[
            { label: '当前会话', value: chat.currentConversationId || '未创建' },
            { label: '最新 Trace', value: chat.currentTraceId || '等待生成' },
          ]"
        />
      </SurfaceCard>

      <AsyncState
        :loading="loadingConversations"
        :error="chat.errorMessage"
        :empty="!conversations.length"
        empty-title="暂无会话"
        empty-description="发送第一条消息后，会话列表会显示在这里。"
      >
        <div class="list-stack">
          <button
            v-for="item in conversations"
            :key="item.id"
            class="resource-item text-left"
            :class="{ active: item.id === chat.currentConversationId }"
            @click="select(item.id)"
          >
            <div class="resource-title">{{ item.title || '未命名会话' }}</div>
            <div class="resource-meta">
              <span>{{ item.messageCount ?? 0 }} 条消息</span>
              <span>{{ formatDate(item.updatedAt || item.createdAt) }}</span>
            </div>
          </button>
        </div>
      </AsyncState>
    </aside>

    <main class="flex min-h-screen flex-col gap-4 p-6">
      <div class="message-list">
        <AsyncState
          :loading="false"
          :empty="!messages.length"
          empty-title="开始一段新对话"
          empty-description="提一个业务问题，检查聊天流式返回、会话落库和 Trace 回传。"
        >
          <div class="list-stack">
            <article v-for="(message, index) in messages" :key="index">
              <div class="meta-label !text-slate-500">{{ message.role === 'user' ? 'User' : 'Assistant' }}</div>
              <div :class="['message-bubble mt-2', message.role === 'user' ? 'message-bubble-user' : 'message-bubble-assistant']">
                {{ message.content || (isLoading ? '模型生成中...' : '') }}
              </div>
            </article>
          </div>
        </AsyncState>
      </div>

      <SurfaceCard compact>
        <p v-if="chat.errorMessage" class="text-sm text-red-600">{{ chat.errorMessage }}</p>
        <form class="mt-2 flex gap-3" @submit.prevent="submit">
          <textarea v-model="question" class="textarea !min-h-[88px]" placeholder="输入问题，触发聊天和 RAG 流程" />
          <button class="btn btn-primary self-end" :disabled="isLoading || !question.trim()">
            {{ isLoading ? '发送中...' : '发送' }}
          </button>
        </form>
      </SurfaceCard>
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import AsyncState from '@/components/admin/AsyncState.vue'
import KeyValueGrid from '@/components/admin/KeyValueGrid.vue'
import SurfaceCard from '@/components/admin/SurfaceCard.vue'
import { useAuthStore } from '@/stores/authStore'
import { useChatStore } from '@/stores/chatStore'

const auth = useAuthStore()
const chat = useChatStore()
const question = ref('')
const loadingConversations = ref(false)
const messages = computed(() => chat.messages)
const conversations = computed(() => chat.conversations)
const isLoading = computed(() => chat.isLoading)

async function refresh() {
  loadingConversations.value = true
  try {
    await chat.loadConversations()
  } finally {
    loadingConversations.value = false
  }
}

function startConversation() {
  question.value = ''
  chat.startConversation()
}

async function submit() {
  if (!question.value.trim()) return
  const current = question.value
  question.value = ''
  await chat.sendMessage(current)
}

async function select(id: string) {
  await chat.selectConversation(id)
}

function formatDate(value?: string) {
  return value ? new Date(value).toLocaleString() : '-'
}

onMounted(refresh)
</script>

import { defineStore } from 'pinia'
import { ref } from 'vue'
import { listConversations, listMessages, sendChatMessage } from '@/services/chatService'

export interface UIMessage {
  id?: string
  role: string
  content: string
}

export const useChatStore = defineStore('chat', () => {
  const messages = ref<UIMessage[]>([])
  const conversations = ref<any[]>([])
  const currentConversationId = ref<string>('')
  const isLoading = ref(false)
  const errorMessage = ref('')
  const currentTraceId = ref('')

  async function loadConversations() {
    errorMessage.value = ''
    conversations.value = await listConversations()
    if (!currentConversationId.value && conversations.value[0]?.id) {
      await selectConversation(conversations.value[0].id)
    }
  }

  async function selectConversation(id: string) {
    errorMessage.value = ''
    try {
      const nextMessages = await listMessages(id)
      currentConversationId.value = id
      messages.value = nextMessages
    } catch (error: any) {
      errorMessage.value = error?.message || '加载会话消息失败'
    }
  }

  function startConversation() {
    errorMessage.value = ''
    currentTraceId.value = ''
    currentConversationId.value = ''
    messages.value = []
  }

  async function sendMessage(content: string) {
    errorMessage.value = ''
    currentTraceId.value = ''
    messages.value.push({ role: 'user', content })
    messages.value.push({ role: 'assistant', content: '' })
    const target = messages.value[messages.value.length - 1]
    isLoading.value = true
    let capturedConversationId = currentConversationId.value
    try {
      await sendChatMessage(content, currentConversationId.value || undefined, (event) => {
        if (event.type === 'token') {
          target.content += String(event.content || '')
        }
        if (event.type === 'error') {
          errorMessage.value = String(event.content || '聊天链路失败')
          target.content = errorMessage.value
        }
        if (typeof event.traceId === 'string') {
          currentTraceId.value = event.traceId
        }
        if (typeof event.conversationId === 'string' && event.conversationId) {
          capturedConversationId = event.conversationId
        }
      })
      await loadConversations()
      if (capturedConversationId) {
        currentConversationId.value = capturedConversationId
      }
    } catch (error: any) {
      errorMessage.value = error?.message || '发送消息失败'
      target.content = '请求失败，请检查模型配置或稍后重试。'
    } finally {
      isLoading.value = false
    }
  }

  return {
    messages,
    conversations,
    currentConversationId,
    currentTraceId,
    isLoading,
    errorMessage,
    loadConversations,
    selectConversation,
    startConversation,
    sendMessage,
  }
})

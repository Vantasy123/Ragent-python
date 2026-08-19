import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  clearConversationMessages,
  listConversations,
  listMessages,
  sendUnifiedChatMessage,
  type ChatMode,
  type ChatAttachment,
} from '@/services/chatService'

export interface UIMessage {
  id?: string
  role: string
  content: string
  attachments?: ChatAttachment[]
}

export interface StreamEvent {
  type: string
  channel?: string
  thought?: string
  reason?: string
  tool?: string
  args?: any
  result?: any
  content?: string
  message?: string
  sources?: any[]
  traceId?: string
}

export const useChatStore = defineStore('chat', () => {
  const messages = ref<UIMessage[]>([])
  const conversations = ref<any[]>([])
  const currentConversationId = ref('')
  const currentTraceId = ref('')
  const mode = ref<ChatMode>('auto')
  const streamEvents = ref<StreamEvent[]>([])
  const currentStage = ref('')
  const finalOutput = ref('')
  const isLoading = ref(false)
  const errorMessage = ref('')

  function setMode(nextMode: ChatMode) {
    mode.value = nextMode
  }

  async function loadConversations() {
    errorMessage.value = ''
    try {
      conversations.value = await listConversations()
      if (!currentConversationId.value && conversations.value[0]?.id) {
        await selectConversation(conversations.value[0].id)
      }
    } catch {
      // ignore
    }
  }

  let conversationSelectionVersion = 0

  async function selectConversation(id: string) {
    errorMessage.value = ''
    const selectionVersion = ++conversationSelectionVersion
    currentConversationId.value = id
    try {
      const loadedMessages = await listMessages(id)
      if (selectionVersion === conversationSelectionVersion && currentConversationId.value === id) {
        messages.value = loadedMessages
      }
    } catch (error: any) {
      if (selectionVersion === conversationSelectionVersion) {
        errorMessage.value = error?.message || '加载会话消息失败'
      }
    }
  }

  async function clearConversation(id: string) {
    errorMessage.value = ''
    try {
      await clearConversationMessages(id)
      if (currentConversationId.value === id) {
        messages.value = []
        streamEvents.value = []
        currentTraceId.value = ''
        currentConversationId.value = ''
      }
      conversations.value = conversations.value.filter((item) => item.id !== id)
    } catch (error: any) {
      errorMessage.value = error?.message || '清空会话记录失败'
    }
  }

  function startConversation() {
    conversationSelectionVersion += 1
    errorMessage.value = ''
    currentTraceId.value = ''
    currentConversationId.value = ''
    streamEvents.value = []
    currentStage.value = ''
    finalOutput.value = ''
    messages.value = []
  }

  async function sendMessage(content: string, attachments?: ChatAttachment[]) {
    errorMessage.value = ''
    currentTraceId.value = ''
    streamEvents.value = []
    currentStage.value = '正在思考...'
    finalOutput.value = ''
    messages.value.push({
      role: 'user',
      content,
      attachments: attachments && attachments.length ? [...attachments] : undefined,
    })
    messages.value.push({ role: 'assistant', content: '' })
    const assistantIndex = messages.value.length - 1
    isLoading.value = true
    let capturedConversationId = currentConversationId.value
    try {
      await sendUnifiedChatMessage(
        {
          message: content,
          mode: mode.value,
          conversationId: currentConversationId.value || undefined,
          attachments,
        },
        (event: any) => {
          if (event.type !== 'token') streamEvents.value.push(event as StreamEvent)
          if (event.type === 'react_step') currentStage.value = String(event.thought || event.reason || '智能求职 Agent 正在分析')
          if (event.type === 'tool_call') currentStage.value = `正在调用工具：${event.tool || '求职工具'}`
          if (event.type === 'observation') currentStage.value = String(event.result?.summary || '工具已返回结果')
          if (event.type === 'final_answer') {
            finalOutput.value = String(event.content || '')
            if (messages.value[assistantIndex]) {
              messages.value[assistantIndex].content = finalOutput.value
            }
          }
          if (event.type === 'token') {
            if (messages.value[assistantIndex]) {
              messages.value[assistantIndex].content = (messages.value[assistantIndex].content || '') + String(event.content || '')
            }
          }
          if (event.type === 'done') {
            currentStage.value = '已完成'
            if (messages.value[assistantIndex] && !messages.value[assistantIndex].content && finalOutput.value) {
              messages.value[assistantIndex].content = finalOutput.value
            }
          }
          if (event.type === 'error') {
            errorMessage.value = String(event.content || '聊天链路失败')
            if (messages.value[assistantIndex]) {
              messages.value[assistantIndex].content = errorMessage.value
            }
          }
          if (typeof event.traceId === 'string') currentTraceId.value = event.traceId
          if (typeof event.conversationId === 'string' && event.conversationId) capturedConversationId = event.conversationId
        },
      )
      await loadConversations()
      if (capturedConversationId) currentConversationId.value = capturedConversationId
    } catch (error: any) {
      errorMessage.value = error?.message || '发送消息失败'
      if (messages.value[assistantIndex]) {
        messages.value[assistantIndex].content = '请求失败，请检查后端模型配置或网络连接。'
      }
    } finally {
      isLoading.value = false
    }
  }

  return {
    messages,
    conversations,
    currentConversationId,
    currentTraceId,
    mode,
    streamEvents,
    currentStage,
    finalOutput,
    isLoading,
    errorMessage,
    setMode,
    loadConversations,
    selectConversation,
    clearConversation,
    startConversation,
    sendMessage,
  }
})

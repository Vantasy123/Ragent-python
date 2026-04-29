import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  clearConversationMessages,
  listConversations,
  listMessages,
  sendUnifiedChatMessage,
  type ChatMode,
} from '@/services/chatService'
import { opsAgentService, type OpsAgentEvent } from '@/services/opsAgentService'

export interface UIMessage {
  id?: string
  role: string
  content: string
}

function toOpsEvent(event: Record<string, unknown>): OpsAgentEvent {
  return event as OpsAgentEvent
}

function summarizeOpsEvent(event: OpsAgentEvent) {
  switch (event.type) {
    case 'plan_created':
      return `已生成运维执行计划，共 ${event.steps?.length || 0} 个步骤。`
    case 'step_started':
      return '正在执行计划步骤。'
    case 'step_observed':
      return '当前步骤已返回观察结果。'
    case 'replan_decision':
      return event.reason || '已完成一次重规划判断。'
    case 'final_answer':
      return event.content || '已生成最终输出。'
    case 'react_step':
      return event.reason || event.thought || '对话 Agent 正在判断下一步。'
    case 'run_created':
      return '运维诊断任务已创建，正在进入多智能体编排。'
    case 'orchestrator_start':
      return event.message || '编排智能体已启动，正在理解问题并拆解任务。'
    case 'task_decomposition':
      return `已拆解 ${event.subTasks?.length || 0} 个子任务，开始分配给专业智能体。`
    case 'agent_assigned':
      return `${event.agent || '智能体'} 已接收任务：${event.message || event.content || ''}`
    case 'agent_plan':
      return `${event.agent || '智能体'} 已生成执行计划，共 ${event.steps?.length || 0} 个步骤。`
    case 'tool_call':
      return `${event.agent || '智能体'} 正在调用工具：${event.tool || '未知工具'}。`
    case 'observation':
      return event.result?.summary || `${event.agent || '智能体'} 已返回观察结果。`
    case 'approval_required':
      return `需要审批危险操作：${event.tool || '运维操作'}。`
    case 'agent_done':
      return `${event.agent || '智能体'} 已完成。`
    case 'report':
    case 'done':
      return event.content || event.report || '运维诊断已完成。'
    case 'error':
      return event.content || event.message || '运维 Agent 执行失败。'
    default:
      return event.content || event.message || event.type
  }
}

export const useChatStore = defineStore('chat', () => {
  const messages = ref<UIMessage[]>([])
  const conversations = ref<any[]>([])
  const currentConversationId = ref('')
  const currentTraceId = ref('')
  const currentRunId = ref('')
  const mode = ref<ChatMode>('auto')
  const opsEvents = ref<OpsAgentEvent[]>([])
  const streamEvents = ref<OpsAgentEvent[]>([])
  const currentStage = ref('')
  const finalOutput = ref('')
  const isLoading = ref(false)
  const errorMessage = ref('')
  const approvalLoading = ref('')

  function setMode(nextMode: ChatMode) {
    mode.value = nextMode
  }

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
      currentConversationId.value = id
      messages.value = await listMessages(id)
    } catch (error: any) {
      errorMessage.value = error?.message || '加载会话消息失败'
    }
  }

  async function clearConversation(id: string) {
    errorMessage.value = ''
    try {
      await clearConversationMessages(id)
      if (currentConversationId.value === id) {
        messages.value = []
        opsEvents.value = []
        streamEvents.value = []
        currentTraceId.value = ''
        currentRunId.value = ''
        currentConversationId.value = ''
      }
      conversations.value = conversations.value.filter((item) => item.id !== id)
    } catch (error: any) {
      errorMessage.value = error?.message || '清空会话记录失败'
    }
  }

  function startConversation() {
    errorMessage.value = ''
    currentTraceId.value = ''
    currentRunId.value = ''
    currentConversationId.value = ''
    opsEvents.value = []
    streamEvents.value = []
    currentStage.value = ''
    finalOutput.value = ''
    messages.value = []
  }

  function applyOpsEvent(rawEvent: Record<string, unknown>, target: UIMessage) {
    const event = toOpsEvent(rawEvent)
    opsEvents.value.push(event)
    streamEvents.value.push(event)
    if (event.runId) currentRunId.value = event.runId
    if (event.traceId) currentTraceId.value = event.traceId

    const summary = summarizeOpsEvent(event)
    currentStage.value = summary
    if (event.type === 'report' || event.type === 'done') {
      target.content = summary
      finalOutput.value = summary
    } else if (event.type === 'final_answer') {
      target.content = summary
      finalOutput.value = summary
    } else if (!target.content || event.type === 'approval_required' || event.type === 'error') {
      target.content = summary
    }

    if (event.type === 'error') {
      errorMessage.value = summary
    }
  }

  async function approveOpsEvent(event: OpsAgentEvent, approved: boolean) {
    if (!currentRunId.value || !event.approvalId) return
    approvalLoading.value = event.approvalId
    try {
      await opsAgentService.approve(currentRunId.value, {
        approvalId: event.approvalId,
        approved,
        comment: approved ? '用户在聊天台批准执行' : '用户在聊天台拒绝执行',
      })
      opsEvents.value.push({
        type: approved ? 'approval_approved' : 'approval_rejected',
        channel: 'ops',
        runId: currentRunId.value,
        agent: event.agent,
        tool: event.tool,
        content: approved ? '审批已通过，等待后端继续执行。' : '审批已拒绝，危险操作不会执行。',
      })
    } catch (error: any) {
      errorMessage.value = error?.message || '审批操作失败'
    } finally {
      approvalLoading.value = ''
    }
  }

  async function sendMessage(content: string) {
    errorMessage.value = ''
    currentTraceId.value = ''
    opsEvents.value = []
    streamEvents.value = []
    currentStage.value = '正在发送请求'
    finalOutput.value = ''
    messages.value.push({ role: 'user', content })
    messages.value.push({ role: 'assistant', content: '' })
    const target = messages.value[messages.value.length - 1]
    isLoading.value = true
    let capturedConversationId = currentConversationId.value
    try {
      await sendUnifiedChatMessage(
        {
          message: content,
          mode: mode.value,
          conversationId: currentConversationId.value || undefined,
        },
        (event) => {
          const channel = String(event.channel || 'rag')
          if (channel === 'ops') {
            applyOpsEvent(event, target)
            return
          }
          if (event.type !== 'token') streamEvents.value.push(toOpsEvent(event))
          if (event.type === 'react_step') currentStage.value = String(event.thought || event.reason || '对话 Agent 正在处理')
          if (event.type === 'tool_call') currentStage.value = `正在调用工具：${event.tool || '未知工具'}`
          if (event.type === 'observation') currentStage.value = String(event.result?.summary || '工具已返回结果')
          if (event.type === 'final_answer') finalOutput.value = String(event.content || '')
          if (event.type === 'token') target.content += String(event.content || '')
          if (event.type === 'done') {
            currentStage.value = '已完成'
            finalOutput.value = target.content
          }
          if (event.type === 'error') {
            errorMessage.value = String(event.content || '聊天链路失败')
            target.content = errorMessage.value
          }
          if (typeof event.traceId === 'string') currentTraceId.value = event.traceId
          if (typeof event.conversationId === 'string' && event.conversationId) capturedConversationId = event.conversationId
        },
      )
      await loadConversations()
      if (capturedConversationId) currentConversationId.value = capturedConversationId
    } catch (error: any) {
      errorMessage.value = error?.message || '发送消息失败'
      target.content = '请求失败，请检查后端、模型配置或登录状态。'
    } finally {
      isLoading.value = false
    }
  }

  return {
    messages,
    conversations,
    currentConversationId,
    currentTraceId,
    currentRunId,
    mode,
    opsEvents,
    streamEvents,
    currentStage,
    finalOutput,
    isLoading,
    errorMessage,
    approvalLoading,
    setMode,
    loadConversations,
    selectConversation,
    clearConversation,
    startConversation,
    sendMessage,
    approveOpsEvent,
  }
})

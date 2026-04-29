<template>
  <div class="conversation-shell">
    <aside class="conversation-sidebar">
      <div class="conversation-sidebar-head">
        <div>
          <div class="meta-label !text-slate-500">会话工作台</div>
          <div class="conversation-title">Ragent 智能对话</div>
          <div class="helper-text mt-2 text-sm">统一入口支持知识问答和运维诊断。</div>
        </div>
        <router-link v-if="auth.user?.role === 'admin'" to="/admin/dashboard" class="btn btn-secondary conversation-admin-link">后台</router-link>
      </div>

      <div class="inline-actions">
        <button class="btn btn-primary" @click="startConversation">新建会话</button>
        <button class="btn btn-secondary" @click="refresh">刷新列表</button>
      </div>

      <SurfaceCard compact>
        <label class="meta-label mb-2 block !text-slate-500">对话模式</label>
        <select class="input" :value="chat.mode" @change="changeMode">
          <option value="auto">自动识别</option>
          <option value="rag">知识问答</option>
          <option value="ops">运维诊断</option>
        </select>
        <KeyValueGrid
          class="mt-4"
          :columns="1"
          :items="[
            { label: '当前会话', value: chat.currentConversationId || '未创建' },
            { label: '最新 Trace', value: chat.currentTraceId || '等待生成' },
            { label: '运维 Run', value: chat.currentRunId || '未触发' },
          ]"
        />
      </SurfaceCard>

      <AsyncState
        :loading="loadingConversations"
        :error="chat.errorMessage"
        :empty="!conversations.length"
        empty-title="暂无会话"
        empty-description="发送第一条消息后，会话会显示在这里。"
      >
        <div class="list-stack">
          <button
            v-for="item in conversations"
            :key="item.id"
            class="resource-item text-left"
            :class="{ active: item.id === chat.currentConversationId }"
            @click="select(item.id)"
          >
            <div class="flex items-center justify-between gap-3">
              <div class="resource-title">{{ item.title || '未命名会话' }}</div>
              <button class="btn btn-ghost !px-3 !py-1 text-xs" @click.stop="clearConversation(item.id)">清空记录</button>
            </div>
            <div class="resource-meta">
              <span>{{ item.messageCount ?? 0 }} 条消息</span>
              <span>{{ formatDate(item.updatedAt || item.createdAt) }}</span>
            </div>
          </button>
        </div>
      </AsyncState>
    </aside>

    <main class="conversation-main">
      <div class="message-list">
        <AsyncState
          :loading="false"
          :empty="!messages.length"
          empty-title="开始一段新对话"
          empty-description="普通问题会走知识问答；运维问题可自动进入多 Agent 诊断，也可以手动选择运维诊断模式。"
        >
          <div class="list-stack">
            <article v-for="(message, index) in messages" :key="index">
              <div class="meta-label !text-slate-500">{{ message.role === 'user' ? '用户' : '助手' }}</div>
              <div :class="['message-bubble mt-2', message.role === 'user' ? 'message-bubble-user' : 'message-bubble-assistant']">
                {{ message.content || (isLoading ? '生成中...' : '') }}
              </div>
            </article>
          </div>
        </AsyncState>
      </div>

      <SurfaceCard v-if="chat.streamEvents.length" compact>
        <div class="flex items-center justify-between gap-3">
          <div>
            <div class="meta-label !text-slate-500">当前运行阶段</div>
            <div class="mt-1 font-semibold">{{ chat.currentStage || '正在等待事件' }}</div>
            <div v-if="chat.finalOutput" class="helper-text mt-2 whitespace-pre-wrap">{{ chat.finalOutput }}</div>
          </div>
          <div class="flex items-center gap-2">
            <span class="status-pill status-running">{{ chat.streamEvents.length }} 个事件</span>
            <button class="btn btn-secondary !px-3 !py-2 text-sm" @click="showOpsDetails = !showOpsDetails">
              {{ showOpsDetails ? '隐藏详情' : '显示详情' }}
            </button>
          </div>
        </div>

        <div v-if="showOpsDetails" class="mt-4 grid gap-3">
          <article v-for="(event, index) in chat.streamEvents" :key="eventKey(event, index)" class="rounded-2xl border border-slate-200 bg-slate-50 p-4 text-sm">
            <div class="flex flex-wrap items-center justify-between gap-3">
              <div class="flex items-center gap-2">
                <span class="status-pill" :style="{ color: agentTheme(event.agent).color }">
                  {{ agentTheme(event.agent).label }}
                </span>
                <strong>{{ eventTypeLabel(event.type) }}</strong>
              </div>
              <div class="flex items-center gap-2">
                <span v-if="event.tool" class="meta-label !text-slate-500">工具：{{ event.tool }}</span>
                <button
                  v-if="hasEventDetails(event)"
                  class="btn btn-ghost !px-3 !py-1 text-xs"
                  @click="toggleEventExpanded(event, index)"
                >
                  {{ isEventExpanded(event, index) ? '收起详情' : '展开详情' }}
                </button>
              </div>
            </div>

            <p class="mt-2 text-slate-700">{{ eventText(event) }}</p>

            <div v-if="isEventExpanded(event, index) && event.subTasks?.length" class="mt-3 grid gap-2">
              <div v-for="(task, taskIndex) in event.subTasks" :key="taskIndex" class="rounded-xl border border-slate-200 bg-white p-3">
                <div class="font-semibold">{{ task.agent || '智能体' }}</div>
                <div class="mt-1 text-slate-700">{{ task.task || task.message || '-' }}</div>
                <div v-if="task.reason" class="helper-text mt-1">原因：{{ task.reason }}</div>
              </div>
            </div>

            <DataPreview v-if="isEventExpanded(event, index) && event.steps?.length" class="mt-3" :data="event.steps" empty-text="暂无计划步骤" />
            <DataPreview v-if="isEventExpanded(event, index) && event.args" class="mt-3" :data="event.args" empty-text="暂无工具参数" />
            <DataPreview v-if="isEventExpanded(event, index) && event.result" class="mt-3" :data="event.result" empty-text="暂无观察结果" />
            <DataPreview v-if="isEventExpanded(event, index) && event.memory" class="mt-3" :data="event.memory" empty-text="暂无共享记忆" />

            <div v-if="isEventExpanded(event, index) && event.type === 'approval_required'" class="mt-3 rounded-2xl border border-amber-200 bg-amber-50 p-3">
              <div class="font-semibold text-amber-900">需要审批后才会执行危险操作</div>
              <div class="helper-text mt-1">风险等级：{{ event.riskLevel || '未标注' }}，审批 ID：{{ event.approvalId || '-' }}</div>
              <div class="mt-3 flex gap-2">
                <button class="btn btn-primary" :disabled="chat.approvalLoading === event.approvalId" @click="approve(event, true)">批准执行</button>
                <button class="btn btn-secondary" :disabled="chat.approvalLoading === event.approvalId" @click="approve(event, false)">拒绝执行</button>
              </div>
            </div>
          </article>
        </div>
      </SurfaceCard>

      <div class="chat-composer">
        <p v-if="chat.errorMessage" class="mb-2 text-sm text-red-600">{{ chat.errorMessage }}</p>
        <form class="chat-composer-form" @submit.prevent="submit">
          <textarea
            v-model="question"
            class="chat-composer-input"
            placeholder="输入问题，例如：后端 502 帮我诊断，或查询知识库内容。"
            rows="1"
            @keydown="handleComposerKeydown"
          />
          <button class="chat-send-button" :disabled="isLoading || !question.trim()" type="submit" title="发送">
            {{ isLoading ? '发送中...' : '发送' }}
          </button>
        </form>
        <div class="chat-composer-hint">Enter 发送，Shift + Enter 换行</div>
      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import type { ChatMode } from '@/services/chatService'
import { AGENT_THEME, type OpsAgentEvent } from '@/services/opsAgentService'
import AsyncState from '@/components/admin/AsyncState.vue'
import DataPreview from '@/components/admin/DataPreview.vue'
import KeyValueGrid from '@/components/admin/KeyValueGrid.vue'
import SurfaceCard from '@/components/admin/SurfaceCard.vue'
import { useAuthStore } from '@/stores/authStore'
import { useChatStore } from '@/stores/chatStore'
import { formatShanghaiDateTime } from '@/utils/date'

const auth = useAuthStore()
const chat = useChatStore()
const question = ref('')
const loadingConversations = ref(false)
const messages = computed(() => chat.messages)
const conversations = computed(() => chat.conversations)
const isLoading = computed(() => chat.isLoading)
const expandedEventKeys = reactive(new Set<string>())
const showOpsDetails = ref(false)

function changeMode(event: Event) {
  chat.setMode((event.target as HTMLSelectElement).value as ChatMode)
}

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
  expandedEventKeys.clear()
  showOpsDetails.value = false
}

async function submit() {
  if (!question.value.trim()) return
  const current = question.value
  question.value = ''
  await chat.sendMessage(current)
}

function handleComposerKeydown(event: KeyboardEvent) {
  if (event.key !== 'Enter' || event.shiftKey || event.isComposing) return
  event.preventDefault()
  submit()
}

async function select(id: string) {
  await chat.selectConversation(id)
}

async function clearConversation(id: string) {
  if (!window.confirm('确定清空该会话的对话记录吗？会话本身会保留。')) return
  await chat.clearConversation(id)
  expandedEventKeys.clear()
  showOpsDetails.value = false
}

async function approve(event: OpsAgentEvent, approved: boolean) {
  await chat.approveOpsEvent(event, approved)
}

function agentTheme(agent?: string) {
  return AGENT_THEME[agent || ''] || { color: '#475569', label: agent || '系统事件' }
}

function eventTypeLabel(type: string) {
  const labels: Record<string, string> = {
    run_created: '任务创建',
    orchestrator_start: '编排启动',
    task_decomposition: '任务拆解',
    agent_assigned: '智能体分配',
    plan_created: '计划生成',
    step_started: '步骤执行',
    step_observed: '步骤观察',
    replan_decision: '重规划',
    final_answer: '最终输出',
    react_step: '对话推理',
    agent_plan: '执行计划',
    tool_call: '工具调用',
    observation: '观察结果',
    approval_required: '等待审批',
    approval_approved: '审批通过',
    approval_rejected: '审批拒绝',
    agent_done: '智能体完成',
    report: '诊断报告',
    done: '完成',
    error: '错误',
  }
  return labels[type] || type
}

function eventText(event: OpsAgentEvent) {
  if (event.content) return event.content
  if (event.message) return event.message
  if (event.report) return event.report
  if (event.type === 'task_decomposition') return `已拆解 ${event.subTasks?.length || 0} 个子任务。`
  if (event.type === 'agent_plan') return `生成 ${event.steps?.length || 0} 个计划步骤。`
  if (event.type === 'plan_created') return `生成 ${event.steps?.length || 0} 个计划步骤。`
  if (event.type === 'replan_decision') return event.reason || '已完成重规划判断。'
  if (event.type === 'step_started') return '正在执行计划步骤。'
  if (event.type === 'step_observed') return event.result?.summary || '步骤已返回观察结果。'
  if (event.type === 'final_answer') return event.content || '已生成最终输出。'
  if (event.type === 'react_step') return event.reason || event.thought || '对话 Agent 正在判断下一步。'
  if (event.type === 'tool_call') return `正在调用 ${event.tool || '未知工具'}。`
  if (event.type === 'approval_required') return `工具 ${event.tool || '未知工具'} 需要人工审批。`
  return eventTypeLabel(event.type)
}

// 事件详情默认折叠，只在用户展开时渲染结构化内容，避免流式过程直接铺满页面。
function eventKey(event: OpsAgentEvent, index: number) {
  return `${event.type}-${event.approvalId || event.runId || event.tool || index}`
}

function hasEventDetails(event: OpsAgentEvent) {
  return Boolean(
    event.subTasks?.length ||
      event.steps?.length ||
      event.step ||
      event.args ||
      event.result ||
      event.memory ||
      event.type === 'approval_required',
  )
}

function isEventExpanded(event: OpsAgentEvent, index: number) {
  return expandedEventKeys.has(eventKey(event, index))
}

function toggleEventExpanded(event: OpsAgentEvent, index: number) {
  const key = eventKey(event, index)
  if (expandedEventKeys.has(key)) {
    expandedEventKeys.delete(key)
    return
  }
  expandedEventKeys.add(key)
}

function formatDate(value?: string) {
  return formatShanghaiDateTime(value)
}

onMounted(refresh)
</script>

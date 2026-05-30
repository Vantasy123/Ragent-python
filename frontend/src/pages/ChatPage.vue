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

      <div class="flex w-full gap-2">
        <button class="btn btn-primary flex-1 justify-center" @click="startConversation">新建会话</button>
        <button class="btn btn-secondary flex-1 justify-center" @click="refresh">刷新列表</button>
      </div>

      <SurfaceCard compact>
        <label class="meta-label mb-2 block !text-slate-500">对话模式</label>
        <div class="grid grid-cols-3 gap-1 rounded-lg bg-slate-100 p-1 border border-slate-200">
          <button 
            v-for="opt in [{value: 'auto', label: '自动'}, {value: 'rag', label: '问答'}, {value: 'ops', label: '运维'}]" 
            :key="opt.value" 
            type="button"
            :class="['px-1 py-1.5 text-xs font-semibold rounded-md transition-all text-center', chat.mode === opt.value ? 'bg-blue-600 text-white shadow-sm' : 'text-slate-500 hover:text-slate-900']"
            @click="chat.setMode(opt.value)"
          >
            {{ opt.label }}
          </button>
        </div>
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
              <div class="resource-title text-slate-800">{{ item.title || '未命名会话' }}</div>
              <button 
                class="text-slate-400 hover:text-red-600 transition-colors p-1" 
                title="删除会话" 
                @click.stop="clearConversation(item.id)"
              >
                <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                </svg>
              </button>
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
      <div class="message-list flex-1 min-h-[480px]">
        <AsyncState
          :loading="false"
          :empty="!messages.length"
          empty-title="开始一段新对话"
          empty-description="普通问题会走知识问答；运维问题可自动进入多 Agent 诊断，也可以手动选择运维诊断模式。"
        >
          <div class="space-y-6">
            <article 
              v-for="(message, index) in messages" 
              :key="index" 
              :class="['flex items-start gap-4', message.role === 'user' ? 'flex-row-reverse' : '']"
            >
              <!-- Avatar -->
              <div :class="['flex h-8 w-8 shrink-0 select-none items-center justify-center rounded-lg text-sm font-bold border', 
                message.role === 'user' ? 'bg-slate-800 border-slate-700 text-slate-100' : 'bg-blue-50 border-blue-100 text-blue-600']">
                <template v-if="message.role === 'user'">
                  <svg xmlns="http://www.w3.org/2000/svg" class="h-4.5 w-4.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                  </svg>
                </template>
                <template v-else>
                  <svg xmlns="http://www.w3.org/2000/svg" class="h-4.5 w-4.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                  </svg>
                </template>
              </div>

              <!-- Message Block -->
              <div :class="['flex-1 min-w-0 flex flex-col', message.role === 'user' ? 'items-end' : 'items-start']">
                <span class="text-xs font-semibold text-zinc-500 mb-1">
                  {{ message.role === 'user' ? '用户' : 'Ragent 助手' }}
                </span>
                
                <!-- Chat Bubble Container -->
                <div 
                  v-if="message.role === 'user'" 
                  class="text-left text-sm text-white bg-blue-600 border border-blue-700 rounded-2xl rounded-tr-none px-4 py-2.5 max-w-[85%] whitespace-pre-wrap selection:bg-blue-800/30"
                >
                  {{ message.content }}
                </div>
                <div 
                  v-else 
                  class="text-left markdown-body bg-slate-50 border border-slate-200/80 rounded-2xl rounded-tl-none px-4 py-2.5 max-w-[85%] selection:bg-blue-500/10" 
                  v-html="renderMarkdown(message.content || (isLoading && index === messages.length - 1 ? '*AI 正在处理...*' : ''))"
                >
                </div>
              </div>
            </article>
          </div>
        </AsyncState>
      </div>

      <SurfaceCard v-if="chat.streamEvents.length" compact class="border-slate-200 bg-slate-50/80">
        <div class="flex items-center justify-between border-b border-slate-200 pb-3">
          <div class="flex items-center gap-2">
            <span class="flex h-2 w-2 rounded-full bg-blue-500 animate-pulse"></span>
            <span class="text-xs font-semibold text-slate-500">智能体运维执行日志</span>
          </div>
          <button class="btn btn-secondary !px-2.5 !py-1 text-xs" @click="showOpsDetails = !showOpsDetails">
            {{ showOpsDetails ? '隐藏日志明细' : '查看日志明细 (' + chat.streamEvents.length + ')' }}
          </button>
        </div>

        <div v-if="showOpsDetails" class="mt-4 border-l border-slate-200 ml-2 pl-4 space-y-4">
          <article v-for="(event, index) in chat.streamEvents" :key="eventKey(event, index)" class="relative text-xs">
            <!-- Timeline dot -->
            <span class="absolute -left-[21px] top-1 flex h-2 w-2 items-center justify-center rounded-full bg-slate-200 ring-4 ring-slate-100">
              <span :class="['h-1.5 w-1.5 rounded-full', event.type === 'error' ? 'bg-red-500' : event.type === 'done' || event.type === 'final_answer' ? 'bg-emerald-500' : 'bg-blue-500']"></span>
            </span>

            <div class="flex items-start justify-between gap-3">
              <div class="min-w-0">
                <div class="flex items-center flex-wrap gap-2">
                  <span class="px-1.5 py-0.5 rounded text-[10px] font-bold bg-slate-100 text-slate-700 border border-slate-200" :style="{ borderLeft: '2px solid ' + agentTheme(event.agent).color }">
                    {{ agentTheme(event.agent).label }}
                  </span>
                  <span class="font-semibold text-slate-700">{{ eventTypeLabel(event.type) }}</span>
                  <span v-if="event.tool" class="text-zinc-500">工具: {{ event.tool }}</span>
                </div>
                <p class="mt-1 text-slate-500 font-mono">{{ eventText(event) }}</p>
              </div>

              <button
                v-if="hasEventDetails(event)"
                class="text-[10px] text-blue-500 hover:text-blue-400 font-semibold shrink-0"
                @click="toggleEventExpanded(event, index)"
              >
                {{ isEventExpanded(event, index) ? '收起数据' : '查看数据' }}
              </button>
            </div>

            <!-- Details section -->
            <div v-if="isEventExpanded(event, index)" class="mt-2 space-y-2 bg-white rounded-lg p-2.5 border border-slate-200">
              <div v-if="event.subTasks?.length" class="space-y-1.5">
                <div class="text-[10px] font-semibold text-zinc-500">拆解子任务</div>
                <div v-for="(task, taskIndex) in event.subTasks" :key="taskIndex" class="border border-slate-150 bg-slate-50 rounded p-2">
                  <div class="font-semibold text-slate-700">{{ task.agent || '智能体' }}</div>
                  <div class="mt-0.5 text-slate-600">{{ task.task || task.message || '-' }}</div>
                  <div v-if="task.reason" class="text-[10px] text-zinc-500 mt-0.5">原因: {{ task.reason }}</div>
                </div>
              </div>

              <DataPreview v-if="event.steps?.length" class="mt-1 font-mono text-[11px]" :data="event.steps" empty-text="暂无计划步骤" />
              <DataPreview v-if="event.args" class="mt-1 font-mono text-[11px]" :data="event.args" empty-text="暂无工具参数" />
              <DataPreview v-if="event.result" class="mt-1 font-mono text-[11px]" :data="event.result" empty-text="暂无观察结果" />
              <DataPreview v-if="event.memory" class="mt-1 font-mono text-[11px]" :data="event.memory" empty-text="暂无共享记忆" />
              <DataPreview v-if="event.sources?.length" class="mt-1 font-mono text-[11px]" :data="event.sources" empty-text="暂无来源出处" />

              <div v-if="event.type === 'approval_required'" class="border border-amber-900/30 bg-amber-950/20 rounded p-2">
                <div class="font-semibold text-amber-500">此高危运维操作需要您的授权审批</div>
                <div class="text-[10px] text-zinc-500 mt-0.5">风险等级: {{ event.riskLevel || '未标注' }} | 审批ID: {{ event.approvalId || '-' }}</div>
                <div class="mt-2 flex gap-2">
                  <button class="btn btn-primary !px-2.5 !py-1 text-[10px]" :disabled="chat.approvalLoading === event.approvalId" @click="approve(event, true)">批准执行</button>
                  <button class="btn btn-secondary !px-2.5 !py-1 text-[10px]" :disabled="chat.approvalLoading === event.approvalId" @click="approve(event, false)">拒绝执行</button>
                </div>
              </div>
            </div>
          </article>
        </div>
      </SurfaceCard>

      <div class="chat-composer">
        <p v-if="chat.errorMessage" class="mb-2 text-sm text-red-600">{{ chat.errorMessage }}</p>
        <form class="chat-composer-form border-slate-300 bg-white/95 shadow-md" @submit.prevent="submit">
          <textarea
            v-model="question"
            class="chat-composer-input text-slate-800 placeholder-slate-400"
            placeholder="输入问题，例如：后端 502 帮我诊断，或查询知识库内容。"
            rows="1"
            @keydown="handleComposerKeydown"
          />
          <button class="chat-send-button" :disabled="isLoading || !question.trim()" type="submit" title="发送">
            {{ isLoading ? '...' : '发送' }}
          </button>
        </form>
        <div class="chat-composer-hint text-slate-400">Enter 发送，Shift + Enter 换行</div>
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
import { marked } from 'marked'

const auth = useAuthStore()
const chat = useChatStore()
const question = ref('')
const loadingConversations = ref(false)
const messages = computed(() => chat.messages)
const conversations = computed(() => chat.conversations)
const isLoading = computed(() => chat.isLoading)
const expandedEventKeys = reactive(new Set<string>())
const showOpsDetails = ref(false)

function renderMarkdown(content: string) {
  if (!content) return ''
  return marked.parse(content) as string
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
    sources: '来源出处',
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
  if (event.type === 'sources') return `已生成 ${event.sources?.length || 0} 条来源出处。`
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
      event.sources?.length ||
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

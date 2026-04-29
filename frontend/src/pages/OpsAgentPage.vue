<template>
  <section class="ops-page">
    <PageHeader
      title="运维 Agent 控制台"
      eyebrow="AIOps"
      description="查看多智能体的诊断、知识检索、审批和最终报告。"
    >
      <template #actions>
        <button class="btn btn-secondary" @click="loadAgents">刷新智能体</button>
        <button class="btn btn-secondary" @click="loadTools">刷新工具</button>
      </template>
    </PageHeader>

    <div class="grid-two">
      <SurfaceCard title="发起诊断" subtitle="输入问题后，编排智能体会调度诊断、知识、监控和执行智能体。">
        <div class="form-stack">
          <textarea
            v-model="message"
            class="form-input ops-textarea"
            placeholder="例如：检查后端服务情况，并确认前端代理和数据库是否正常。"
          />
          <label class="toggle-row">
            <input v-model="autoExecuteReadOnly" type="checkbox" />
            <span>自动执行只读诊断工具</span>
          </label>
          <div class="inline-actions">
            <button class="btn btn-primary" :disabled="running || !message.trim()" @click="startRun">
              {{ running ? '诊断进行中...' : '开始诊断' }}
            </button>
            <button v-if="currentRunId" class="btn btn-secondary" @click="refreshRun">刷新详情</button>
            <button v-if="running && currentRunId" class="btn btn-danger" @click="stopRun">停止运行</button>
          </div>
          <p v-if="error" class="helper-text text-red-600">{{ error }}</p>
        </div>
      </SurfaceCard>

      <SurfaceCard title="运行概览" subtitle="从时间线中提取当前最关键的服务状态。">
        <AsyncState :empty="!healthCards.length" empty-title="暂无运行结果" empty-description="发起诊断后会自动生成服务健康概览。">
          <div class="ops-health-grid">
            <article v-for="card in healthCards" :key="card.label" class="ops-health-card">
              <div class="ops-health-label">{{ card.label }}</div>
              <div class="ops-health-value">{{ card.value }}</div>
              <div class="ops-health-hint">{{ card.hint }}</div>
            </article>
          </div>
        </AsyncState>
      </SurfaceCard>
    </div>

    <div class="grid-two mt-5">
      <SurfaceCard title="智能体团队" subtitle="当前可参与协作的运维智能体。">
        <AsyncState :loading="loadingAgents" :empty="!agentList.length" empty-title="暂无智能体">
          <div class="ops-agent-grid">
            <article
              v-for="agent in agentList"
              :key="agent.role"
              class="ops-agent-card"
              :style="{ borderColor: getAgentColor(agent.role) }"
            >
              <div class="ops-agent-icon" :style="{ background: getAgentColor(agent.role) }">
                {{ getAgentIcon(agent.role) }}
              </div>
              <div class="ops-agent-body">
                <div class="ops-agent-name">{{ getAgentLabel(agent.role) }}</div>
                <div class="ops-agent-desc">{{ agent.description }}</div>
              </div>
              <span
                class="status-badge"
                :class="activeAgents.has(agent.role) ? 'status-ok' : 'status-badge-neutral'"
              >
                {{ activeAgents.has(agent.role) ? '运行中' : '空闲' }}
              </span>
            </article>
          </div>
        </AsyncState>
      </SurfaceCard>

      <SurfaceCard title="工具目录" subtitle="系统允许调用的受控运维工具。">
        <AsyncState :loading="loadingTools" :empty="!tools.length" empty-title="暂无工具">
          <div class="list-stack">
            <article v-for="tool in tools" :key="tool.name" class="resource-item">
              <div class="resource-item-row">
                <div>
                  <div class="resource-title">{{ tool.name }}</div>
                  <div class="resource-item-note">{{ tool.description }}</div>
                </div>
                <div class="tool-badges">
                  <span class="status-badge" :class="tool.requiresApproval ? 'status-danger' : 'status-ok'">
                    {{ tool.requiresApproval ? '需审批' : '自动执行' }}
                  </span>
                  <span class="status-badge status-badge-neutral">{{ tool.riskLevel || tool.risk_level || 'read' }}</span>
                </div>
              </div>
            </article>
          </div>
        </AsyncState>
      </SurfaceCard>
    </div>

    <div class="grid-two mt-5">
      <SurfaceCard title="运行阶段" subtitle="默认只展示当前阶段和最终输出，详细事件按需展开。">
        <AsyncState :empty="!events.length" empty-title="暂无事件" empty-description="发起诊断后将实时显示多智能体事件流。">
          <div class="stage-panel">
            <div class="meta-label !text-slate-500">当前阶段</div>
            <div class="stage-title">{{ currentStage || '等待开始' }}</div>
            <div v-if="finalOutput" class="report-content whitespace-pre-wrap">{{ finalOutput }}</div>
            <div class="mt-4 flex items-center justify-between gap-3">
              <span class="status-badge status-badge-neutral">{{ events.length }} 个事件</span>
              <button class="btn btn-secondary" @click="showTimelineDetails = !showTimelineDetails">
                {{ showTimelineDetails ? '隐藏详情' : '显示详情' }}
              </button>
            </div>
          </div>

          <div v-if="showTimelineDetails" class="timeline mt-4">
            <article
              v-for="(event, index) in events"
              :key="eventKey(event, index)"
              class="timeline-item"
              :class="timelineItemClass(event)"
            >
              <div class="timeline-dot" :style="{ background: getAgentColor(event.agent || 'orchestrator') }"></div>
              <div class="timeline-header">
                <span
                  class="timeline-agent-badge"
                  :style="{ background: `${getAgentColor(event.agent || 'orchestrator')}22`, color: getAgentColor(event.agent || 'orchestrator') }"
                >
                  {{ getAgentIcon(event.agent || 'orchestrator') }} {{ getAgentLabel(event.agent || 'orchestrator') }}
                </span>
                <span class="timeline-type">{{ formatEventType(event.type) }}</span>
              </div>
              <div class="mt-2 flex items-center justify-end">
                <button
                  v-if="hasEventDetails(event)"
                  class="btn btn-ghost !px-3 !py-1 text-xs"
                  @click="toggleEventExpanded(event, index)"
                >
                  {{ isEventExpanded(event, index) ? '收起详情' : '展开详情' }}
                </button>
              </div>
              <div class="resource-item-note whitespace-pre-wrap">{{ eventText(event) }}</div>

              <DataPreview v-if="isEventExpanded(event, index) && event.steps?.length" :data="event.steps || []" />
              <DataPreview v-if="isEventExpanded(event, index) && event.args" :data="event.args || {}" />
              <DataPreview v-if="isEventExpanded(event, index) && event.result" :data="event.result || {}" />

              <div v-if="isEventExpanded(event, index) && event.type === 'report'" class="report-content whitespace-pre-wrap">
                {{ event.content }}
              </div>

              <div v-if="isEventExpanded(event, index) && event.type === 'approval_required'" class="inline-actions mt-3">
                <button class="btn btn-primary" @click="approve(event, true)">批准执行</button>
                <button class="btn btn-danger" @click="approve(event, false)">拒绝</button>
              </div>
            </article>
          </div>
        </AsyncState>
      </SurfaceCard>

      <div class="detail-column">
        <SurfaceCard title="运行详情" subtitle="持久化后的运行信息和最终报告。">
          <AsyncState :empty="!runDetail" empty-title="暂无运行详情" empty-description="开始诊断后可在这里查看运行结果。">
            <div v-if="runDetail" class="list-stack">
              <KeyValueGrid :items="runFacts" />
              <SurfaceCard compact title="最终报告">
                <div class="whitespace-pre-wrap">{{ runDetail.finalReport || '暂无最终报告' }}</div>
              </SurfaceCard>
              <SurfaceCard compact title="工具调用记录">
                <AsyncState
                  :empty="!normalizedToolCalls.length"
                  empty-title="暂无工具调用"
                  empty-description="执行过程中的工具结果会显示在这里。"
                >
                  <div class="list-stack">
                    <article v-for="toolCall in normalizedToolCalls" :key="toolCall.id" class="resource-item">
                      <div class="resource-item-row">
                        <div>
                          <div class="resource-title">{{ toolCall.toolName }}</div>
                          <div class="resource-item-note">{{ toolCall.statusLabel }}</div>
                        </div>
                        <span class="status-badge" :class="toolCall.statusClass">{{ toolCall.statusLabel }}</span>
                      </div>
                      <DataPreview :data="toolCall.result || toolCall.args || {}" />
                    </article>
                  </div>
                </AsyncState>
              </SurfaceCard>
            </div>
          </AsyncState>
        </SurfaceCard>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import AsyncState from '@/components/admin/AsyncState.vue'
import DataPreview from '@/components/admin/DataPreview.vue'
import KeyValueGrid from '@/components/admin/KeyValueGrid.vue'
import PageHeader from '@/components/admin/PageHeader.vue'
import SurfaceCard from '@/components/admin/SurfaceCard.vue'
import { AGENT_THEME, opsAgentService, streamOpsAgent, type OpsAgentEvent } from '@/services/opsAgentService'

const message = ref('检查后端服务情况，并确认前端代理与数据库连接是否正常。')
const autoExecuteReadOnly = ref(true)
const running = ref(false)
const error = ref('')
const events = ref<OpsAgentEvent[]>([])
const tools = ref<Array<Record<string, any>>>([])
const agentList = ref<Array<Record<string, any>>>([])
const loadingTools = ref(false)
const loadingAgents = ref(false)
const currentRunId = ref('')
const runDetail = ref<Record<string, any> | null>(null)
const currentStage = ref('')
const finalOutput = ref('')
const showTimelineDetails = ref(false)
const activeAgents = reactive(new Set<string>())
const expandedTimelineKeys = reactive(new Set<string>())

function getAgentColor(role: string): string {
  return AGENT_THEME[role]?.color || '#2563eb'
}

function getAgentIcon(role: string): string {
  return AGENT_THEME[role]?.icon || '控'
}

function getAgentLabel(role: string): string {
  return AGENT_THEME[role]?.label || role
}

const runFacts = computed(() => {
  if (!runDetail.value) return []
  return [
    { label: '运行 ID', value: runDetail.value.id },
    { label: '状态', value: formatStatus(runDetail.value.status) },
    { label: '消息', value: runDetail.value.message || '-' },
    { label: '工具调用数', value: normalizedToolCalls.value.length },
  ]
})

const normalizedToolCalls = computed(() =>
  ((runDetail.value?.toolCalls as Array<Record<string, any>> | undefined) || []).map((item) => {
    const rawStatus = String(item.status || '')
    return {
      ...item,
      statusLabel: statusLabel(rawStatus),
      statusClass: statusClass(rawStatus),
    }
  }),
)

const healthCards = computed(() => {
  const compose = events.value.find((event) => event.type === 'observation' && event.result?.data?.stdout)
  const api = events.value.find((event) => event.type === 'observation' && String(event.result?.summary || '').includes('HTTP 200'))
  const log = events.value.find((event) => event.type === 'observation' && event.tool === 'container_logs')
  const toolsCount = normalizedToolCalls.value.length

  return [
    {
      label: '容器状态',
      value: compose ? '正常' : '待检查',
      hint: compose ? 'Compose 服务已拉起并返回状态表。' : '尚未拿到容器状态结果。',
    },
    {
      label: '后端健康检查',
      value: api ? 'HTTP 200' : '未完成',
      hint: api ? String(api.result?.summary || '') : '等待健康检查结果。',
    },
    {
      label: '工具调用数',
      value: String(toolsCount),
      hint: toolsCount ? '已写入运行详情。' : '当前还没有持久化的工具调用记录。',
    },
    {
      label: '日志状态',
      value: log ? '已获取' : '未获取',
      hint: log ? '最近日志已进入事件流。' : '尚未拉取后端日志。',
    },
  ]
})

async function loadTools() {
  loadingTools.value = true
  try {
    tools.value = (await opsAgentService.tools()) as Array<Record<string, any>>
  } finally {
    loadingTools.value = false
  }
}

async function loadAgents() {
  loadingAgents.value = true
  try {
    const data = (await opsAgentService.agents()) as Record<string, Record<string, unknown>>
    agentList.value = Object.entries(data).map(([role, info]) => ({ role, ...(info || {}) }))
  } finally {
    loadingAgents.value = false
  }
}

async function startRun() {
  running.value = true
  error.value = ''
  events.value = []
  runDetail.value = null
  currentRunId.value = ''
  currentStage.value = '正在创建运维诊断任务'
  finalOutput.value = ''
  showTimelineDetails.value = false
  activeAgents.clear()
  expandedTimelineKeys.clear()

  try {
    // 事件流以回调方式逐条回放，页面只做增量渲染，不等待整轮结束再展示。
    await streamOpsAgent(
      { message: message.value, autoExecuteReadOnly: autoExecuteReadOnly.value },
      (event) => {
        events.value.push(event)
        currentStage.value = eventText(event) || formatEventType(event.type)
        if (event.type === 'report' || event.type === 'done' || event.type === 'final_answer') {
          finalOutput.value = event.content || event.report || eventText(event)
        }
        if (event.runId) currentRunId.value = event.runId
        if (event.agent) activeAgents.add(event.agent)
        if (event.type === 'agent_done' && event.agent) activeAgents.delete(event.agent)
      },
    )
    await refreshRun()
  } catch (err: any) {
    error.value = err?.message || '运维 Agent 执行失败'
  } finally {
    running.value = false
    activeAgents.clear()
  }
}

async function refreshRun() {
  if (!currentRunId.value) return
  runDetail.value = (await opsAgentService.run(currentRunId.value)) as Record<string, any>
}

async function stopRun() {
  if (!currentRunId.value) return
  const result = (await opsAgentService.stop(currentRunId.value)) as Record<string, any>
  runDetail.value = { ...(runDetail.value || {}), ...result }
  running.value = false
}

async function approve(event: OpsAgentEvent, approved: boolean) {
  if (!event.runId || !event.approvalId) return
  await opsAgentService.approve(event.runId, {
    approvalId: event.approvalId,
    approved,
    comment: approved ? '管理员批准执行' : '管理员拒绝执行',
  })
  await refreshRun()
}

function formatStatus(status?: string): string {
  const map: Record<string, string> = {
    running: '运行中',
    completed: '已完成',
    failed: '失败',
    stopped: '已停止',
    waiting_approval: '等待审批',
  }
  return map[String(status || '')] || String(status || '-')
}

function statusLabel(status: string): string {
  const map: Record<string, string> = {
    running: '执行中',
    success: '成功',
    failed: '失败',
    blocked: '等待审批',
  }
  return map[status] || status || '未知'
}

function statusClass(status: string): string {
  if (status === 'success') return 'status-ok'
  if (status === 'failed') return 'status-danger'
  if (status === 'blocked') return 'status-warn'
  return 'status-badge-neutral'
}

function formatEventType(type: string): string {
  const map: Record<string, string> = {
    run_created: '运行创建',
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
    agent_done: '智能体完成',
    report: '综合报告',
    done: '运行完成',
    error: '错误',
  }
  return map[type] || type
}

function eventText(event: OpsAgentEvent): string {
  if (event.type === 'task_decomposition') {
    return `本轮拆分为 ${(event.subTasks || []).length} 个子任务。`
  }
  if (event.type === 'agent_assigned') {
    return event.reason ? String((event as Record<string, unknown>).reason) : '已分配给对应智能体处理。'
  }
  if (event.type === 'plan_created') {
    return `已生成 ${(event.steps || []).length} 个执行步骤。`
  }
  if (event.type === 'step_started') {
    return '正在执行计划步骤。'
  }
  if (event.type === 'step_observed') {
    return String(event.result?.summary || '当前步骤已返回观察结果。')
  }
  if (event.type === 'replan_decision') {
    return String(event.reason || '已完成一次重规划判断。')
  }
  if (event.type === 'final_answer') {
    return event.content || '已生成最终输出。'
  }
  if (event.type === 'tool_call') {
    return `${event.tool || '未知工具'} ${JSON.stringify(event.args || {}, null, 2)}`
  }
  if (event.type === 'observation') {
    return String(event.result?.summary || event.content || '')
  }
  if (event.type === 'report' || event.type === 'done') {
    return event.content || ''
  }
  return event.message || event.content || ''
}

// 时间线详情默认折叠，先展示摘要，再按需展开结构化结果和审批面板。
function eventKey(event: OpsAgentEvent, index: number) {
  return `${event.type}-${event.approvalId || event.runId || event.tool || index}`
}

function hasEventDetails(event: OpsAgentEvent): boolean {
  return Boolean(event.steps?.length || event.step || event.args || event.result || event.type === 'approval_required' || event.type === 'report')
}

function isEventExpanded(event: OpsAgentEvent, index: number): boolean {
  return expandedTimelineKeys.has(eventKey(event, index))
}

function toggleEventExpanded(event: OpsAgentEvent, index: number) {
  const key = eventKey(event, index)
  if (expandedTimelineKeys.has(key)) {
    expandedTimelineKeys.delete(key)
    return
  }
  expandedTimelineKeys.add(key)
}

function timelineItemClass(event: OpsAgentEvent): string {
  if (event.type === 'error') return 'timeline-error'
  if (event.type === 'approval_required') return 'timeline-approval'
  if (event.type === 'report') return 'timeline-report'
  if (event.type === 'done') return 'timeline-done'
  return ''
}

onMounted(() => {
  loadTools()
  loadAgents()
})
</script>

<style scoped>
.ops-page {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.ops-textarea {
  min-height: 132px;
}

.ops-health-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.ops-health-card {
  border: 1px solid var(--border);
  border-radius: 18px;
  padding: 16px;
  background: rgba(255, 255, 255, 0.76);
}

.ops-health-label {
  font-size: 12px;
  color: #64748b;
}

.ops-health-value {
  margin-top: 6px;
  font-size: 24px;
  font-weight: 700;
  color: #0f172a;
}

.ops-health-hint {
  margin-top: 8px;
  font-size: 13px;
  color: #475569;
}

.ops-agent-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 12px;
}

.ops-agent-card {
  display: flex;
  align-items: center;
  gap: 12px;
  border: 1px solid var(--border);
  border-radius: 18px;
  padding: 14px 16px;
  background: rgba(255, 255, 255, 0.76);
}

.ops-agent-icon {
  width: 40px;
  height: 40px;
  border-radius: 12px;
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  flex-shrink: 0;
}

.ops-agent-body {
  flex: 1;
}

.ops-agent-name {
  font-weight: 700;
  color: #0f172a;
}

.ops-agent-desc {
  margin-top: 4px;
  font-size: 13px;
  color: #475569;
}

.report-content {
  margin-top: 12px;
  padding: 14px;
  border-radius: 14px;
  background: rgba(15, 23, 42, 0.04);
  color: #0f172a;
}

.stage-panel {
  border: 1px solid var(--border);
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.78);
  padding: 16px;
}

.stage-title {
  margin-top: 8px;
  font-size: 1.15rem;
  font-weight: 700;
  color: #0f172a;
  line-height: 1.45;
}

@media (max-width: 1024px) {
  .ops-health-grid {
    grid-template-columns: 1fr;
  }
}
</style>

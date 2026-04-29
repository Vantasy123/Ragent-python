<template>
  <section>
    <PageHeader
      title="智能体效果评估"
      eyebrow="效果评估"
      description="基于在线 Trace 自动计算结果、过程、工具使用与系统指标，用于定位低分回答、慢请求和工具异常。"
    >
      <template #actions>
        <button class="btn btn-secondary" @click="load">刷新评估</button>
      </template>
    </PageHeader>

    <AsyncState :loading="loading" :error="error">
      <div class="dashboard-grid">
        <article v-for="item in overviewCards" :key="item.label" class="metric-card">
          <div class="meta-label !text-slate-500">{{ item.label }}</div>
          <div class="metric-value">{{ item.value }}</div>
          <div class="metric-trend">{{ item.trend }}</div>
        </article>
      </div>

      <div class="grid-two mt-5">
        <SurfaceCard title="评估运行记录" subtitle="按最新评估结果排序，点击查看指标和问题详情。">
          <AsyncState :loading="false" :empty="!runs.length" empty-title="暂无评估记录" empty-description="重新评估链路后会生成记录。">
            <div class="table-wrap">
              <table class="data-table">
                <thead>
                  <tr>
                    <th>追踪</th>
                    <th>评分</th>
                    <th>状态</th>
                    <th>创建时间</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="item in runs"
                    :key="item.id"
                    :class="{ 'row-active': selectedRun?.id === item.id }"
                    @click="openRun(item.id)"
                  >
                    <td>{{ shortId(item.traceId) }}</td>
                    <td>{{ scoreText(item.overallScore) }}</td>
                    <td><span :class="statusClass(item.status)" class="status-badge">{{ formatStatus(item.status) }}</span></td>
                    <td>{{ formatDate(item.createdAt) }}</td>
                    <td><button class="btn btn-secondary" @click.stop="openRun(item.id)">详情</button></td>
                  </tr>
                </tbody>
              </table>
            </div>
            <PaginationBar :total="runPagination.total" :page-size="runPagination.pageSize" :current-page="runPagination.pageNo" @update:page="changeRunPage" />
          </AsyncState>
        </SurfaceCard>

        <SurfaceCard title="最近问题" subtitle="自动识别低质量回答、检索为空、节点失败和慢请求。">
          <AsyncState :loading="false" :empty="!issues.length" empty-title="暂无问题" empty-description="当前规则评估未发现异常。">
            <div class="list-stack">
              <article v-for="issue in issues" :key="issue.id" class="resource-item">
                <div class="resource-item-row">
                  <div>
                    <div class="resource-title">{{ issue.issueKey }}</div>
                    <div class="resource-item-note">{{ issue.message }}</div>
                  </div>
                  <span :class="severityClass(issue.severity)" class="status-badge">{{ formatSeverity(issue.severity) }}</span>
                </div>
                <div class="resource-meta mt-2">
                  <span>{{ formatDimension(issue.dimension) }}</span>
                  <span>{{ shortId(issue.traceId) }}</span>
                  <span>{{ formatDate(issue.createdAt) }}</span>
                </div>
              </article>
            </div>
            <PaginationBar :total="issuePagination.total" :page-size="issuePagination.pageSize" :current-page="issuePagination.pageNo" @update:page="changeIssuePage" />
          </AsyncState>
        </SurfaceCard>
      </div>

      <SurfaceCard class="mt-5" title="评估详情" subtitle="展示选中评估记录的总体信息、指标明细和问题证据。">
        <AsyncState :loading="loadingDetail" :error="detailError" :empty="!selectedRun" empty-title="未选择评估记录">
          <div v-if="selectedRun" class="list-stack">
            <div class="inline-actions">
              <router-link class="btn btn-secondary" :to="`/admin/traces/${selectedRun.traceId}`">查看 Trace 详情</router-link>
              <button class="btn btn-secondary" @click="rerunEvaluation(selectedRun.traceId)">重新评估</button>
            </div>

            <KeyValueGrid :items="runFacts" />

            <SurfaceCard compact title="指标明细" subtitle="每个指标统一使用 0-1 分，越高越好。">
              <div class="table-wrap">
                <table class="data-table">
                  <thead>
                    <tr>
                      <th>维度</th>
                      <th>指标</th>
                      <th>评分</th>
                      <th>原因</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="metric in selectedRun.metrics || []" :key="metric.id">
                      <td>{{ formatDimension(metric.dimension) }}</td>
                      <td>{{ metric.metricKey }}</td>
                      <td>{{ scoreText(metric.score) }}</td>
                      <td>{{ metric.reason }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </SurfaceCard>

            <div class="grid-two">
              <SurfaceCard compact title="问题证据">
                <DataPreview :data="selectedRun.issues || []" />
              </SurfaceCard>
              <SurfaceCard compact title="指标证据">
                <DataPreview :data="(selectedRun.metrics || []).map((item: any) => item.evidence)" />
              </SurfaceCard>
            </div>
          </div>
        </AsyncState>
      </SurfaceCard>
    </AsyncState>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import AsyncState from '@/components/admin/AsyncState.vue'
import DataPreview from '@/components/admin/DataPreview.vue'
import KeyValueGrid from '@/components/admin/KeyValueGrid.vue'
import PageHeader from '@/components/admin/PageHeader.vue'
import PaginationBar from '@/components/admin/PaginationBar.vue'
import SurfaceCard from '@/components/admin/SurfaceCard.vue'
import { adminService } from '@/services/adminService'
import { formatShanghaiDateTime } from '@/utils/date'

type EvaluationRun = {
  id: string
  traceId: string
  conversationId?: string
  messageId?: string
  status: string
  overallScore: number
  summary?: string
  createdAt: string
  metrics?: Array<Record<string, any>>
  issues?: Array<Record<string, any>>
}

type EvaluationIssue = {
  id: string
  traceId: string
  dimension: string
  issueKey: string
  severity: string
  message: string
  createdAt: string
}

const loading = ref(false)
const error = ref('')
const overview = ref<Record<string, any>>({})
const runs = ref<EvaluationRun[]>([])
const issues = ref<EvaluationIssue[]>([])
const runPagination = ref({ total: 0, pageNo: 1, pageSize: 8 })
const issuePagination = ref({ total: 0, pageNo: 1, pageSize: 8 })
const loadingDetail = ref(false)
const detailError = ref('')
const selectedRun = ref<EvaluationRun | null>(null)

const overviewCards = computed(() => [
  { label: '评估记录', value: overview.value.evaluationRuns ?? 0, trend: `低分 ${overview.value.lowScoreRuns ?? 0}` },
  { label: '平均评分', value: scoreText(overview.value.avgScore), trend: '规则指标均值' },
  { label: '链路成功率', value: `${overview.value.successRate ?? 0}%`, trend: `P95 ${overview.value.p95TotalMs ?? 0} ms` },
  { label: '满意率', value: `${overview.value.feedbackSatisfactionRate ?? 0}%`, trend: `问题 ${overview.value.issueCount ?? 0}` },
])

const runFacts = computed(() => {
  const run = selectedRun.value
  if (!run) return []
  return [
    { label: '追踪标识', value: run.traceId },
    { label: '评分', value: scoreText(run.overallScore) },
    { label: '状态', value: formatStatus(run.status) },
    { label: '摘要', value: run.summary || '-' },
    { label: '会话', value: run.conversationId || '-' },
    { label: '消息', value: run.messageId || '-' },
  ]
})

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [overviewData, runPage, issuePage] = await Promise.all([
      adminService.evaluationOverview(),
      adminService.evaluationRuns(runPagination.value.pageNo, runPagination.value.pageSize),
      adminService.evaluationIssues(issuePagination.value.pageNo, issuePagination.value.pageSize),
    ])
    overview.value = overviewData
    runs.value = runPage.items as EvaluationRun[]
    issues.value = issuePage.items as EvaluationIssue[]
    runPagination.value = { total: runPage.total, pageNo: runPage.pageNo, pageSize: runPage.pageSize }
    issuePagination.value = { total: issuePage.total, pageNo: issuePage.pageNo, pageSize: issuePage.pageSize }
    if (selectedRun.value?.id) {
      selectedRun.value = runs.value.find((item) => item.id === selectedRun.value?.id) || null
    }
  } catch (err: any) {
    error.value = err?.detail || err?.message || '评估数据加载失败'
  } finally {
    loading.value = false
  }
}

async function openRun(runId: string) {
  loadingDetail.value = true
  detailError.value = ''
  try {
    selectedRun.value = (await adminService.evaluationRun(runId)) as EvaluationRun
  } catch (err: any) {
    detailError.value = err?.detail || err?.message || '评估详情加载失败'
  } finally {
    loadingDetail.value = false
  }
}

async function rerunEvaluation(traceId: string) {
  selectedRun.value = (await adminService.evaluateTrace(traceId)) as EvaluationRun
  await load()
}

function changeRunPage(pageNo: number) {
  runPagination.value.pageNo = pageNo
  void load()
}

function changeIssuePage(pageNo: number) {
  issuePagination.value.pageNo = pageNo
  void load()
}

function scoreText(value?: number) {
  const score = Number(value ?? 0)
  return score <= 1 ? score.toFixed(2) : String(score)
}

function shortId(value?: string) {
  if (!value) return '-'
  return value.length > 12 ? `${value.slice(0, 8)}...${value.slice(-4)}` : value
}

function formatDate(value?: string) {
  return formatShanghaiDateTime(value)
}

function statusClass(status: string) {
  const normalized = String(status || '').toLowerCase()
  if (['success', 'completed'].includes(normalized)) return 'status-badge-success'
  if (['failed', 'error'].includes(normalized)) return 'status-badge-danger'
  return 'status-badge-neutral'
}

function formatStatus(status?: string) {
  const map: Record<string, string> = {
    completed: '已完成',
    success: '成功',
    failed: '失败',
    error: '错误',
    pending: '待处理',
    running: '运行中',
  }
  return map[String(status || '').toLowerCase()] || status || '-'
}

function formatSeverity(severity?: string) {
  const map: Record<string, string> = {
    high: '高',
    medium: '中',
    low: '低',
  }
  return map[String(severity || '').toLowerCase()] || severity || '-'
}

function formatDimension(dimension?: string) {
  const map: Record<string, string> = {
    outcome: '结果',
    process: '过程',
    tool: '工具使用',
    system: '系统',
  }
  return map[String(dimension || '').toLowerCase()] || dimension || '-'
}

function severityClass(severity: string) {
  const normalized = String(severity || '').toLowerCase()
  if (normalized === 'high') return 'status-badge-danger'
  if (normalized === 'medium') return 'status-badge-warning'
  return 'status-badge-neutral'
}

onMounted(load)
</script>

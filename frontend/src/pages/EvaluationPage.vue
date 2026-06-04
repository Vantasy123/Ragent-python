<template>
  <section>
    <PageHeader
      title="智能体效果评估"
      eyebrow="效果评估"
      description="同时覆盖在线 Trace 评估、离线数据集评测和批次报告，用于量化检索、生成、工具调用和系统稳定性。"
    >
      <template #actions>
        <button class="btn btn-secondary" @click="loadAll">刷新评估</button>
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

      <div class="tabs-bar mt-5">
        <button v-for="item in tabs" :key="item.key" class="btn" :class="activeTab === item.key ? 'btn-primary' : 'btn-secondary'" @click="activeTab = item.key">
          {{ item.label }}
        </button>
      </div>

      <div v-if="activeTab === 'online'" class="mt-5">
        <div class="grid-two">
          <SurfaceCard title="在线评估运行记录" subtitle="自动计算结果、过程、工具使用与系统指标。">
            <AsyncState :loading="false" :empty="!runs.length" empty-title="暂无评估记录" empty-description="重新评估链路后会生成记录。">
              <div class="table-wrap">
                <table class="data-table">
                  <thead>
                    <tr>
                      <th class="cell-id">追踪</th>
                      <th class="cell-nowrap">综合评分</th>
                      <th class="cell-nowrap">状态</th>
                      <th class="cell-nowrap">创建时间</th>
                      <th class="cell-nowrap">操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="item in runs" :key="item.id" :class="{ 'row-active': selectedRun?.id === item.id && onlineDrawerOpen }" @click="viewRunDetails(item.id)">
                      <td class="cell-id">{{ shortId(item.traceId) }}</td>
                      <td class="cell-nowrap font-bold text-slate-700">{{ scoreText(item.overallScore) }}</td>
                      <td class="cell-nowrap"><span :class="statusClass(item.status)" class="status-badge">{{ formatStatus(item.status) }}</span></td>
                      <td class="cell-nowrap cell-mono text-slate-500">{{ formatDate(item.createdAt) }}</td>
                      <td class="cell-nowrap"><button class="btn btn-secondary !py-1 !px-2.5 text-xs" @click.stop="viewRunDetails(item.id)">详情</button></td>
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
                      <div class="resource-item-note mt-1 text-xs text-slate-500">{{ issue.message }}</div>
                    </div>
                    <span :class="severityClass(issue.severity)" class="status-badge">{{ formatSeverity(issue.severity) }}</span>
                  </div>
                  <div class="resource-meta mt-2">
                    <span>{{ formatDimension(issue.dimension) }}</span>
                    <span class="cell-mono">{{ shortId(issue.traceId) }}</span>
                    <span class="cell-mono">{{ formatDate(issue.createdAt) }}</span>
                  </div>
                </article>
              </div>
              <PaginationBar :total="issuePagination.total" :page-size="issuePagination.pageSize" :current-page="issuePagination.pageNo" @update:page="changeIssuePage" />
            </AsyncState>
          </SurfaceCard>
        </div>
      </div>

      <div v-if="activeTab === 'datasets'" class="grid-two mt-5">
        <SurfaceCard title="评估数据集" subtitle="维护离线评估问题、期望答案、期望片段和关键词。">
          <div class="list-stack">
            <form class="settings-form" @submit.prevent="saveDataset">
              <input v-model="datasetForm.name" class="input" placeholder="数据集名称" />
              <textarea v-model="datasetForm.description" class="input min-h-[88px]" placeholder="数据集说明"></textarea>
              <input v-model="datasetForm.kbId" class="input" placeholder="知识库 ID（可选）" />
              <input v-model="datasetTagsText" class="input" placeholder="标签，使用逗号分隔" />
              <div class="inline-actions">
                <button class="btn btn-primary" type="submit">{{ datasetForm.id ? '保存数据集' : '新建数据集' }}</button>
                <button class="btn btn-secondary" type="button" @click="resetDatasetForm">清空</button>
              </div>
            </form>

            <AsyncState :loading="false" :empty="!datasets.length" empty-title="暂无数据集">
              <div class="table-wrap">
                <table class="data-table">
                  <thead>
                    <tr>
                      <th class="cell-truncate">数据集名称</th>
                      <th class="cell-nowrap">用例数</th>
                      <th class="cell-nowrap">状态</th>
                      <th class="cell-nowrap">操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="item in datasets" :key="item.id" :class="{ 'row-active': selectedDataset?.id === item.id }" @click="openDataset(item.id)">
                      <td class="cell-truncate font-semibold text-slate-800" :title="item.name">{{ item.name }}</td>
                      <td class="cell-nowrap cell-mono text-slate-600">{{ item.caseCount ?? 0 }}</td>
                      <td class="cell-nowrap">
                        <span class="status-badge" :class="item.enabled ? 'status-badge-success' : 'status-badge-neutral'">{{ item.enabled ? '启用' : '停用' }}</span>
                      </td>
                      <td class="cell-nowrap">
                        <button class="btn btn-secondary !py-1 !px-2.5 text-xs" @click.stop="openDataset(item.id)">选择</button>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </AsyncState>
          </div>
        </SurfaceCard>

        <SurfaceCard title="评估用例" subtitle="为选中数据集维护问题、期望答案、期望片段和关键词。">
          <AsyncState :loading="caseLoading" :empty="!selectedDataset" empty-title="未选择数据集">
            <div v-if="selectedDataset" class="list-stack">
              <form class="settings-form" @submit.prevent="saveCase">
                <textarea v-model="caseForm.question" class="input min-h-[88px]" placeholder="问题"></textarea>
                <textarea v-model="caseForm.expectedAnswer" class="input min-h-[88px]" placeholder="期望答案"></textarea>
                <input v-model="expectedChunkIdsText" class="input" placeholder="期望片段 chunkId，使用逗号分隔" />
                <input v-model="expectedKeywordsText" class="input" placeholder="期望关键词，使用逗号分隔" />
                <input v-model="caseForm.kbId" class="input" placeholder="知识库 ID（可选）" />
                <div class="inline-actions">
                  <button class="btn btn-primary" type="submit">{{ caseForm.id ? '保存用例' : '新增用例' }}</button>
                  <button class="btn btn-secondary" type="button" @click="resetCaseForm">清空</button>
                  <button class="btn btn-secondary" type="button" @click="startBatchRun">启动批量评估</button>
                </div>
              </form>

              <form class="settings-form" @submit.prevent="importCases">
                <textarea v-model="csvText" class="input min-h-[100px]" placeholder="CSV 导入：question,expectedAnswer,expectedChunkIds,expectedKeywords"></textarea>
                <button class="btn btn-secondary" type="submit">导入 CSV</button>
              </form>

              <div class="table-wrap">
                <table class="data-table">
                  <thead>
                    <tr>
                      <th class="cell-truncate">问题</th>
                      <th class="cell-truncate">期望答案</th>
                      <th class="cell-nowrap text-center">期望片段</th>
                      <th class="cell-truncate">期望关键词</th>
                      <th class="cell-nowrap">操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="item in cases" :key="item.id" @click="editCase(item)">
                      <td class="cell-truncate text-slate-800" :title="item.question">{{ truncate(item.question, 36) }}</td>
                      <td class="cell-truncate text-slate-600" :title="item.expectedAnswer">{{ truncate(item.expectedAnswer, 30) }}</td>
                      <td class="cell-nowrap cell-mono text-center">{{ (item.expectedChunkIds || []).length }}</td>
                      <td class="cell-truncate text-slate-500" :title="(item.expectedKeywords || []).join('、')">{{ (item.expectedKeywords || []).join('、') || '-' }}</td>
                      <td class="cell-nowrap">
                        <button class="btn btn-danger !py-1 !px-2.5 text-xs" @click.stop="removeCase(item.id)">删除</button>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </AsyncState>
        </SurfaceCard>
      </div>

      <div v-if="activeTab === 'batches'" class="grid-two mt-5">
        <SurfaceCard title="批次报告" subtitle="查看离线数据集评测的综合评分、进度和报告入口。">
          <AsyncState :loading="false" :empty="!batchRuns.length" empty-title="暂无批次">
            <div class="table-wrap">
              <table class="data-table">
                <thead>
                  <tr>
                    <th class="cell-truncate">数据集</th>
                    <th class="cell-nowrap">综合评分</th>
                    <th class="cell-nowrap">进度</th>
                    <th class="cell-nowrap">状态</th>
                    <th class="cell-nowrap">操作</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="item in batchRuns" :key="item.id" :class="{ 'row-active': selectedBatch?.id === item.id && batchDrawerOpen }" @click="viewBatchDetails(item.id)">
                    <td class="cell-truncate font-semibold text-slate-800" :title="item.datasetName">{{ item.datasetName || shortId(item.datasetId) }}</td>
                    <td class="cell-nowrap font-bold text-slate-700">{{ scoreText(item.overallScore) }}</td>
                    <td class="cell-nowrap cell-mono text-slate-600">{{ item.completedCases }}/{{ item.totalCases }}，失败 {{ item.failedCases }}</td>
                    <td class="cell-nowrap">
                      <span class="status-badge" :class="statusClass(item.status)">{{ formatStatus(item.status) }}</span>
                    </td>
                    <td class="cell-nowrap">
                      <button class="btn btn-secondary !py-1 !px-2.5 text-xs" @click.stop="viewBatchDetails(item.id)">报告</button>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </AsyncState>
        </SurfaceCard>
      </div>
    </AsyncState>

    <!-- 在线评估详情抽屉 -->
    <transition name="drawer">
      <div v-if="onlineDrawerOpen" class="drawer-backdrop" @click.self="onlineDrawerOpen = false">
        <div class="drawer-panel">
          <div class="drawer-head">
            <div>
              <div class="meta-label">在线评估详情</div>
              <div class="panel-title text-lg">Trace 链路评估</div>
            </div>
            <button class="btn btn-ghost !p-1.5" @click="onlineDrawerOpen = false">
              <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
          <div class="drawer-body">
            <AsyncState :loading="loadingDetail" :error="detailError" :empty="!selectedRun" empty-title="尚未选择评估记录">
              <div v-if="selectedRun" class="list-stack">
                <div class="inline-actions">
                  <router-link class="btn btn-secondary !py-1 !px-2.5 text-xs" :to="`/admin/traces/${selectedRun.traceId}`">查看 Trace 详情</router-link>
                  <button class="btn btn-secondary !py-1 !px-2.5 text-xs" @click="rerunEvaluation(selectedRun.traceId)">重新评估</button>
                </div>
                <KeyValueGrid :items="runFacts" />
                
                <div class="meta-label !text-slate-500 mt-4">维度指标得分</div>
                <div class="table-wrap">
                  <table class="data-table">
                    <thead>
                      <tr>
                        <th class="cell-nowrap">维度</th>
                        <th class="cell-nowrap">指标</th>
                        <th class="cell-nowrap">评分</th>
                        <th>原因描述</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="metric in selectedRun.metrics || []" :key="metric.id">
                        <td class="cell-nowrap">{{ formatDimension(metric.dimension) }}</td>
                        <td class="cell-nowrap font-mono text-xs">{{ metric.metricKey }}</td>
                        <td class="cell-nowrap cell-mono font-bold text-slate-700">{{ scoreText(metric.score) }}</td>
                        <td class="text-slate-600 text-xs">{{ metric.reason }}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>

                <SurfaceCard compact class="mt-4" title="问题与指标证据" subtitle="评估智能体提取的判定凭证。">
                  <DataPreview :data="{ 问题证据: selectedRun.issues || [], 指标证据: (selectedRun.metrics || []).map((item: any) => item.evidence) }" />
                </SurfaceCard>
              </div>
            </AsyncState>
          </div>
        </div>
      </div>
    </transition>

    <!-- 批次详情抽屉 -->
    <transition name="drawer">
      <div v-if="batchDrawerOpen" class="drawer-backdrop" @click.self="batchDrawerOpen = false">
        <div class="drawer-panel">
          <div class="drawer-head">
            <div>
              <div class="meta-label">批次报告详情</div>
              <div class="panel-title text-lg">{{ selectedBatch?.datasetName || '评测报告' }}</div>
            </div>
            <button class="btn btn-ghost !p-1.5" @click="batchDrawerOpen = false">
              <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
          <div class="drawer-body">
            <AsyncState :loading="batchLoading" :empty="!selectedBatch" empty-title="尚未选择批次">
              <div v-if="selectedBatch" class="list-stack">
                <KeyValueGrid :items="batchFacts" />
                
                <SurfaceCard compact title="均值与摘要" subtitle="批次评测的核心结果汇总。">
                  <DataPreview :data="{ 指标均值: selectedBatch.metricSummary || {}, 批次摘要: selectedBatch.summary }" />
                </SurfaceCard>

                <SurfaceCard compact title="OpenAI Evals 复评" subtitle="把本地批次输出提交到 OpenAI Evals 做外部裁判和报告追踪。">
                  <div class="inline-actions mb-3">
                    <button class="btn btn-secondary !py-1 !px-2.5 text-xs" :disabled="openaiEvalLoading" @click="previewOpenAIEvals">预览请求</button>
                    <button class="btn btn-primary !py-1 !px-2.5 text-xs" :disabled="openaiEvalLoading" @click="startOpenAIEvals">启动复评</button>
                    <button class="btn btn-secondary !py-1 !px-2.5 text-xs" :disabled="openaiEvalLoading || !selectedBatch.openaiEval?.runId" @click="syncOpenAIEvals">同步状态</button>
                  </div>
                  <KeyValueGrid :items="openaiEvalFacts" />
                  <DataPreview v-if="openaiEvalPreview" class="mt-3" :data="openaiEvalPreview" />
                </SurfaceCard>

                <div class="meta-label !text-slate-500 mt-4">用例评测记录</div>
                <div class="table-wrap">
                  <table class="data-table">
                    <thead>
                      <tr>
                        <th class="cell-truncate">问题</th>
                        <th class="cell-nowrap">综合评分</th>
                        <th class="cell-nowrap">执行成功</th>
                        <th class="cell-nowrap">工具有效</th>
                        <th class="cell-nowrap">无错误</th>
                        <th class="cell-nowrap">检索命中</th>
                        <th class="cell-nowrap">上下文召回</th>
                        <th class="cell-nowrap">忠实度</th>
                        <th class="cell-nowrap">答案相关性</th>
                        <th class="cell-nowrap">Trace</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="item in selectedBatch.results || []" :key="item.id">
                        <td class="cell-truncate text-slate-800" :title="item.question">{{ truncate(item.question, 34) }}</td>
                        <td class="cell-nowrap cell-mono font-bold text-slate-700">{{ scoreText(item.overallScore) }}</td>
                        <td class="cell-nowrap cell-mono text-slate-500">{{ metricScore(item, 'execution_success') }}</td>
                        <td class="cell-nowrap cell-mono text-slate-500">{{ metricScore(item, 'tool_effectiveness') }}</td>
                        <td class="cell-nowrap cell-mono text-slate-500">{{ metricScore(item, 'execution_error_free') }}</td>
                        <td class="cell-nowrap cell-mono text-slate-500">{{ metricScore(item, 'hit_at_k') }}</td>
                        <td class="cell-nowrap cell-mono text-slate-500">{{ metricScore(item, 'context_recall') }}</td>
                        <td class="cell-nowrap cell-mono text-slate-500">{{ metricScore(item, 'faithfulness') }}</td>
                        <td class="cell-nowrap cell-mono text-slate-500">{{ metricScore(item, 'answer_relevancy') }}</td>
                        <td class="cell-nowrap">
                          <router-link v-if="item.traceId" class="btn btn-secondary !py-0.5 !px-2 text-xs" :to="`/admin/traces/${item.traceId}`">查看</router-link>
                          <span v-else>-</span>
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>
            </AsyncState>
          </div>
        </div>
      </div>
    </transition>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import AsyncState from '@/components/admin/AsyncState.vue'
import DataPreview from '@/components/admin/DataPreview.vue'
import KeyValueGrid from '@/components/admin/KeyValueGrid.vue'
import PageHeader from '@/components/admin/PageHeader.vue'
import PaginationBar from '@/components/admin/PaginationBar.vue'
import SurfaceCard from '@/components/admin/SurfaceCard.vue'
import { adminService } from '@/services/adminService'
import { formatShanghaiDateTime } from '@/utils/date'

type TabKey = 'online' | 'datasets' | 'batches'

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

type EvaluationDataset = {
  id: string
  name: string
  description?: string
  kbId?: string
  tags?: string[]
  enabled: boolean
  caseCount?: number
}

type EvaluationCase = {
  id: string
  question: string
  expectedAnswer?: string
  expectedChunkIds?: string[]
  expectedKeywords?: string[]
  kbId?: string
  enabled?: boolean
}

type EvaluationBatch = {
  id: string
  datasetId: string
  datasetName?: string
  status: string
  totalCases: number
  completedCases: number
  failedCases: number
  overallScore: number
  metricSummary?: Record<string, number>
  summary?: string
  openaiEval?: {
    evalId?: string
    runId?: string
    status?: string
    report?: Record<string, any>
  }
  results?: Array<Record<string, any>>
}

const tabs = [
  { key: 'online' as TabKey, label: '在线 Trace 评估' },
  { key: 'datasets' as TabKey, label: '离线数据集' },
  { key: 'batches' as TabKey, label: '批次报告' },
]

const activeTab = ref<TabKey>('online')
const loading = ref(false)
const error = ref('')
const overview = ref<Record<string, any>>({})
const runs = ref<EvaluationRun[]>([])
const issues = ref<EvaluationIssue[]>([])
const datasets = ref<EvaluationDataset[]>([])
const cases = ref<EvaluationCase[]>([])
const batchRuns = ref<EvaluationBatch[]>([])
const runPagination = ref({ total: 0, pageNo: 1, pageSize: 8 })
const issuePagination = ref({ total: 0, pageNo: 1, pageSize: 8 })
const loadingDetail = ref(false)
const detailError = ref('')
const caseLoading = ref(false)
const batchLoading = ref(false)
const openaiEvalLoading = ref(false)
const selectedRun = ref<EvaluationRun | null>(null)
const selectedDataset = ref<EvaluationDataset | null>(null)
const selectedBatch = ref<EvaluationBatch | null>(null)
const openaiEvalPreview = ref<Record<string, any> | null>(null)
const datasetTagsText = ref('')
const expectedChunkIdsText = ref('')
const expectedKeywordsText = ref('')
const csvText = ref('')
const onlineDrawerOpen = ref(false)
const batchDrawerOpen = ref(false)

const datasetForm = ref({ id: '', name: '', description: '', kbId: '', tags: [] as string[], enabled: true })
const caseForm = ref({ id: '', question: '', expectedAnswer: '', expectedChunkIds: [] as string[], expectedKeywords: [] as string[], kbId: '', enabled: true })

const overviewCards = computed(() => [
  { label: '在线记录', value: overview.value.evaluationRuns ?? 0, trend: `低分 ${overview.value.lowScoreRuns ?? 0}` },
  { label: '数据集', value: overview.value.datasetCount ?? 0, trend: `用例 ${overview.value.caseCount ?? 0}` },
  { label: '批次评估', value: overview.value.batchRunCount ?? 0, trend: `平均分 ${scoreText(overview.value.avgScore)}` },
  { label: '链路成功率', value: `${overview.value.successRate ?? 0}%`, trend: `P95 ${overview.value.p95TotalMs ?? 0} ms` },
])

const runFacts = computed(() => {
  const run = selectedRun.value
  if (!run) return []
  return [
    { label: '追踪标识', value: run.traceId },
    { label: '综合评分', value: scoreText(run.overallScore) },
    { label: '状态', value: formatStatus(run.status) },
    { label: '摘要', value: run.summary || '-' },
    { label: '会话', value: run.conversationId || '-' },
    { label: '消息', value: run.messageId || '-' },
  ]
})

const batchFacts = computed(() => {
  const batch = selectedBatch.value
  if (!batch) return []
  return [
    { label: '数据集', value: batch.datasetName || batch.datasetId },
    { label: '综合评分', value: scoreText(batch.overallScore) },
    { label: '状态', value: formatStatus(batch.status) },
    { label: '完成用例', value: `${batch.completedCases}/${batch.totalCases}` },
    { label: '失败用例', value: batch.failedCases },
    { label: '摘要', value: batch.summary || '-' },
  ]
})

const openaiEvalFacts = computed(() => {
  const remote = selectedBatch.value?.openaiEval
  const report = remote?.report || {}
  return [
    { label: '远程状态', value: remote?.status || '未启动' },
    { label: 'Eval ID', value: remote?.evalId || '-' },
    { label: 'Run ID', value: remote?.runId || '-' },
    { label: '报告链接', value: report.reportUrl || '-' },
    { label: '结果统计', value: JSON.stringify(report.resultCounts || {}) },
  ]
})

watch(activeTab, () => {
  void loadAll()
})

async function loadAll() {
  loading.value = true
  error.value = ''
  try {
    overview.value = await adminService.evaluationOverview()
    if (activeTab.value === 'online') {
      await loadOnline()
    } else if (activeTab.value === 'datasets') {
      await loadDatasets()
    } else {
      await loadBatches()
    }
  } catch (err: any) {
    error.value = err?.detail || err?.message || '评估数据加载失败'
  } finally {
    loading.value = false
  }
}

async function loadOnline() {
  const [runPage, issuePage] = await Promise.all([
    adminService.evaluationRuns(runPagination.value.pageNo, runPagination.value.pageSize),
    adminService.evaluationIssues(issuePagination.value.pageNo, issuePagination.value.pageSize),
  ])
  runs.value = runPage.items as EvaluationRun[]
  issues.value = issuePage.items as EvaluationIssue[]
  runPagination.value = { total: runPage.total, pageNo: runPage.pageNo, pageSize: runPage.pageSize }
  issuePagination.value = { total: issuePage.total, pageNo: issuePage.pageNo, pageSize: issuePage.pageSize }
}

async function loadDatasets() {
  const page = await adminService.evaluationDatasets(1, 50)
  datasets.value = page.items as EvaluationDataset[]
  if (selectedDataset.value?.id) {
    const matched = datasets.value.find((item) => item.id === selectedDataset.value?.id)
    if (matched) await openDataset(matched.id)
  }
}

async function loadBatches() {
  const page = await adminService.evaluationBatchRuns('', 1, 50)
  batchRuns.value = page.items as EvaluationBatch[]
  if (selectedBatch.value?.id) {
    await openBatch(selectedBatch.value.id)
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

async function viewRunDetails(runId: string) {
  onlineDrawerOpen.value = true
  await openRun(runId)
}

async function rerunEvaluation(traceId: string) {
  selectedRun.value = (await adminService.evaluateTrace(traceId)) as EvaluationRun
  await loadOnline()
}

async function saveDataset() {
  const payload = {
    name: datasetForm.value.name,
    description: datasetForm.value.description,
    kbId: datasetForm.value.kbId || null,
    tags: splitList(datasetTagsText.value),
    enabled: datasetForm.value.enabled,
  }
  if (datasetForm.value.id) {
    await adminService.updateEvaluationDataset(datasetForm.value.id, payload)
  } else {
    await adminService.createEvaluationDataset(payload)
  }
  resetDatasetForm()
  await loadDatasets()
}

async function openDataset(datasetId: string) {
  caseLoading.value = true
  try {
    selectedDataset.value = (await adminService.evaluationDataset(datasetId)) as EvaluationDataset
    datasetForm.value = {
      id: selectedDataset.value.id,
      name: selectedDataset.value.name,
      description: selectedDataset.value.description || '',
      kbId: selectedDataset.value.kbId || '',
      tags: selectedDataset.value.tags || [],
      enabled: selectedDataset.value.enabled,
    }
    datasetTagsText.value = (selectedDataset.value.tags || []).join(',')
    const page = await adminService.evaluationCases(datasetId, 1, 100)
    cases.value = page.items as EvaluationCase[]
  } finally {
    caseLoading.value = false
  }
}

async function saveCase() {
  if (!selectedDataset.value) return
  const payload = {
    question: caseForm.value.question,
    expectedAnswer: caseForm.value.expectedAnswer,
    expectedChunkIds: splitList(expectedChunkIdsText.value),
    expectedKeywords: splitList(expectedKeywordsText.value),
    kbId: caseForm.value.kbId || selectedDataset.value.kbId || null,
    tags: [],
    enabled: caseForm.value.enabled,
    metadata: {},
  }
  if (caseForm.value.id) {
    await adminService.updateEvaluationCase(caseForm.value.id, payload)
  } else {
    await adminService.createEvaluationCase(selectedDataset.value.id, payload)
  }
  resetCaseForm()
  await openDataset(selectedDataset.value.id)
}

function editCase(item: EvaluationCase) {
  caseForm.value = {
    id: item.id,
    question: item.question,
    expectedAnswer: item.expectedAnswer || '',
    expectedChunkIds: item.expectedChunkIds || [],
    expectedKeywords: item.expectedKeywords || [],
    kbId: item.kbId || '',
    enabled: item.enabled ?? true,
  }
  expectedChunkIdsText.value = (item.expectedChunkIds || []).join(',')
  expectedKeywordsText.value = (item.expectedKeywords || []).join(',')
}

async function removeCase(caseId: string) {
  if (!selectedDataset.value) return
  await adminService.deleteEvaluationCase(caseId)
  await openDataset(selectedDataset.value.id)
}

async function importCases() {
  if (!selectedDataset.value) return
  await adminService.importEvaluationCases(selectedDataset.value.id, { csvText: csvText.value })
  csvText.value = ''
  await openDataset(selectedDataset.value.id)
}

async function startBatchRun() {
  if (!selectedDataset.value) return
  const batch = (await adminService.createEvaluationBatchRun(selectedDataset.value.id)) as EvaluationBatch
  activeTab.value = 'batches'
  selectedBatch.value = batch
  await loadBatches()
}

async function openBatch(batchId: string) {
  batchLoading.value = true
  try {
    selectedBatch.value = (await adminService.evaluationBatchRun(batchId)) as EvaluationBatch
    openaiEvalPreview.value = null
  } finally {
    batchLoading.value = false
  }
}

async function viewBatchDetails(batchId: string) {
  batchDrawerOpen.value = true
  await openBatch(batchId)
}

async function previewOpenAIEvals() {
  if (!selectedBatch.value) return
  openaiEvalLoading.value = true
  try {
    openaiEvalPreview.value = await adminService.openAIEvalsPreview(selectedBatch.value.id)
  } finally {
    openaiEvalLoading.value = false
  }
}

async function startOpenAIEvals() {
  if (!selectedBatch.value) return
  openaiEvalLoading.value = true
  try {
    const remote = await adminService.startOpenAIEvals(selectedBatch.value.id)
    selectedBatch.value.openaiEval = remote
    await openBatch(selectedBatch.value.id)
  } finally {
    openaiEvalLoading.value = false
  }
}

async function syncOpenAIEvals() {
  if (!selectedBatch.value) return
  openaiEvalLoading.value = true
  try {
    const remote = await adminService.syncOpenAIEvals(selectedBatch.value.id)
    selectedBatch.value.openaiEval = remote
    await openBatch(selectedBatch.value.id)
  } finally {
    openaiEvalLoading.value = false
  }
}

function resetDatasetForm() {
  datasetForm.value = { id: '', name: '', description: '', kbId: '', tags: [], enabled: true }
  datasetTagsText.value = ''
}

function resetCaseForm() {
  caseForm.value = { id: '', question: '', expectedAnswer: '', expectedChunkIds: [], expectedKeywords: [], kbId: '', enabled: true }
  expectedChunkIdsText.value = ''
  expectedKeywordsText.value = ''
}

// 前端输入统一用逗号分隔，提交前转成后端需要的数组。
function splitList(value: string) {
  return value.split(',').map((item) => item.trim()).filter(Boolean)
}

function changeRunPage(pageNo: number) {
  runPagination.value.pageNo = pageNo
  void loadOnline()
}

function changeIssuePage(pageNo: number) {
  issuePagination.value.pageNo = pageNo
  void loadOnline()
}

function scoreText(value?: number) {
  const score = Number(value ?? 0)
  return score <= 1 ? score.toFixed(2) : String(score)
}

function metricScore(result: Record<string, any>, key: string) {
  const metric = result.metrics?.[key]
  if (!metric || metric.status === 'skipped') return '跳过'
  return scoreText(metric.score)
}

function shortId(value?: string) {
  if (!value) return '-'
  return value.length > 12 ? `${value.slice(0, 8)}...${value.slice(-4)}` : value
}

function truncate(value?: string, size = 40) {
  const text = value || ''
  return text.length > size ? `${text.slice(0, size)}...` : text || '-'
}

function formatDate(value?: string) {
  return formatShanghaiDateTime(value)
}

function statusClass(status: string) {
  const normalized = String(status || '').toLowerCase()
  if (['success', 'completed'].includes(normalized)) return 'status-badge-success'
  if (['failed', 'error', 'completed_with_errors'].includes(normalized)) return 'status-badge-danger'
  if (['running', 'pending'].includes(normalized)) return 'status-badge-warning'
  return 'status-badge-neutral'
}

function formatStatus(status?: string) {
  const map: Record<string, string> = {
    completed: '已完成',
    completed_with_errors: '部分失败',
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
    execution: '执行效果',
    system: '系统',
    retrieval: '检索',
    answer: '答案',
    judge: '裁判模型',
  }
  return map[String(dimension || '').toLowerCase()] || dimension || '-'
}

function severityClass(severity: string) {
  const normalized = String(severity || '').toLowerCase()
  if (normalized === 'high') return 'status-badge-danger'
  if (normalized === 'medium') return 'status-badge-warning'
  return 'status-badge-neutral'
}

onMounted(loadAll)
</script>

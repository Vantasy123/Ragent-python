<template>
  <section>
    <PageHeader
      title="摄取任务中心"
      eyebrow="摄取运维"
      description="按原版后台主线管理流程、提交任务，并查看节点级执行详情。"
    >
      <template #actions>
        <button class="btn btn-secondary" @click="load">刷新数据</button>
      </template>
    </PageHeader>

    <div class="grid-two">
      <SurfaceCard title="流程管理" subtitle="通过模块模板编排摄取流程，并维护节点顺序。">
        <div class="form-grid">
          <input v-model="pipelineForm.name" class="input" placeholder="流程名称" />
          <textarea v-model="pipelineForm.description" class="textarea" placeholder="流程描述" />

          <ModuleComposer
            title="模块编排"
            subtitle="通过模板和模块库组合摄取流程，并调整执行顺序。"
            :presets="ingestionPipelinePresets"
            :selected-preset-id="selectedPresetId"
            :active-preset="activePreset"
            :available-options="availableModuleViews"
            :draft-key="moduleDraftKey"
            :modules="selectedModuleViews"
            preset-placeholder="选择流程模板"
            module-placeholder="选择模块"
            @update:selected-preset-id="selectedPresetId = $event"
            @update:draft-key="moduleDraftKey = $event"
            @apply-preset="applyPreset"
            @add-module="addModule"
            @reset-modules="resetPipelineModules"
            @move-module="moveModule"
            @remove-module="removeModule"
          />

          <div class="inline-actions">
            <button class="btn btn-primary" :disabled="!pipelineForm.name.trim() || !selectedModules.length" @click="submitPipeline">
              {{ pipelineForm.id ? '保存流程' : '创建流程' }}
            </button>
            <button v-if="pipelineForm.id" class="btn btn-secondary" @click="resetPipelineForm">取消编辑</button>
          </div>
        </div>

        <div class="subtle-divider" />

        <AsyncState
          :loading="loading"
          :error="error"
          :empty="!pipelines.length"
          empty-title="暂无流程"
          empty-description="先配置一个摄取流程，后续任务才能绑定具体执行路径。"
        >
          <div class="list-stack">
            <article v-for="item in pipelines" :key="item.id" class="resource-item" :class="{ active: selectedPipeline?.id === item.id }">
              <div class="resource-item-row">
                <button class="w-full text-left" @click="selectPipeline(item)">
                  <div class="resource-title">{{ item.name }}</div>
                  <div class="resource-meta">
                    <span>{{ item.enabled ? '已启用' : '已停用' }}</span>
                    <span>{{ formatDate(item.createdAt) }}</span>
                  </div>
                  <div class="helper-text mt-2">{{ item.description || '暂无描述' }}</div>
                </button>
              </div>
              <div class="mt-3 inline-actions">
                <button class="btn btn-secondary" @click="editPipeline(item.id)">编辑</button>
                <button class="btn btn-danger" @click="removePipeline(item.id)">删除</button>
              </div>
            </article>
          </div>
          <PaginationBar :total="pipelinePagination.total" :page-size="pipelinePagination.pageSize" :current-page="pipelinePagination.pageNo" @update:page="changePipelinePage" />
        </AsyncState>
      </SurfaceCard>

      <div class="list-stack">
        <SurfaceCard title="任务创建" subtitle="通过下拉选择已有知识库、文档和来源配置。">
          <div class="form-grid form-grid-two">
            <input v-model="taskForm.name" class="input" placeholder="任务名称" />
            <select v-model="taskForm.pipeline_id" class="select">
              <option value="">选择流程</option>
              <option v-for="item in pipelines" :key="item.id" :value="item.id">{{ item.name }}</option>
            </select>
            <select v-model="taskForm.kb_id" class="select">
              <option value="">选择知识库（可选）</option>
              <option v-for="item in knowledgeBases" :key="item.id" :value="item.id">{{ item.name }}</option>
            </select>
            <select v-model="taskForm.doc_id" class="select" :disabled="!taskForm.kb_id">
              <option value="">选择文档（可选）</option>
              <option v-for="item in taskDocuments" :key="item.id" :value="item.id">{{ item.docName }}</option>
            </select>
            <select v-model="taskForm.source" class="select">
              <option v-for="item in taskSourceOptions" :key="item.value" :value="item.value">{{ item.label }}</option>
            </select>
            <select v-model="taskForm.retry" class="select">
              <option v-for="item in retryOptions" :key="item" :value="item">{{ item }} 次重试</option>
            </select>
          </div>

          <SurfaceCard compact class="mt-4" title="任务上下文预览" subtitle="按表单生成请求载荷，无需手写配置。">
            <KeyValueGrid :items="taskPayloadFacts" />
          </SurfaceCard>

          <div class="mt-4 inline-actions">
            <button class="btn btn-primary" :disabled="!taskForm.name.trim()" @click="submitTask">提交任务</button>
          </div>
        </SurfaceCard>

        <SurfaceCard title="任务列表" subtitle="查看状态，点击详情在右侧窗口查看节点明细。">
          <AsyncState
            :loading="loading"
            :error="error"
            :empty="!tasks.length"
            empty-title="暂无任务"
            empty-description="提交任务后，这里会展示状态推进和执行结果。"
          >
            <div class="table-wrap">
              <table class="data-table">
                <thead>
                  <tr>
                    <th class="cell-truncate">任务</th>
                    <th class="cell-nowrap">状态</th>
                    <th class="cell-nowrap">创建时间</th>
                    <th class="cell-nowrap">完成时间</th>
                    <th class="cell-nowrap">操作</th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="item in tasks"
                    :key="item.id"
                    :class="{ 'row-active': selectedTask?.id === item.id && drawerOpen }"
                    @click="viewTaskDetails(item.id)"
                  >
                    <td class="cell-truncate font-semibold text-slate-800" :title="item.name">{{ item.name }}</td>
                    <td class="cell-nowrap">
                      <span :class="statusClass(item.status)" class="status-badge">{{ formatStatus(item.status) }}</span>
                    </td>
                    <td class="cell-nowrap cell-mono text-slate-500">{{ formatDate(item.createdAt) }}</td>
                    <td class="cell-nowrap cell-mono text-slate-500">{{ formatDate(item.finishedAt) }}</td>
                    <td class="cell-nowrap">
                      <button class="btn btn-secondary !py-1 !px-2.5 text-xs" @click.stop="viewTaskDetails(item.id)">详情</button>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
            <PaginationBar :total="taskPagination.total" :page-size="taskPagination.pageSize" :current-page="taskPagination.pageNo" @update:page="changeTaskPage" />
          </AsyncState>
        </SurfaceCard>
      </div>
    </div>

    <!-- 任务详情抽屉 -->
    <transition name="drawer">
      <div v-if="drawerOpen" class="drawer-backdrop" @click.self="drawerOpen = false">
        <div class="drawer-panel">
          <div class="drawer-head">
            <div>
              <div class="meta-label">摄取任务详情</div>
              <div class="panel-title text-lg">{{ selectedTask?.name || '任务详情' }}</div>
            </div>
            <button class="btn btn-ghost !p-1.5" @click="drawerOpen = false">
              <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
          <div class="drawer-body">
            <AsyncState
              :loading="loadingTaskDetail"
              :error="taskDetailError"
              :empty="!selectedTask"
              empty-title="尚未加载详情"
            >
              <div v-if="selectedTask" class="list-stack">
                <KeyValueGrid
                  :items="[
                    { label: '任务名称', value: selectedTask.name },
                    { label: '状态', value: formatStatus(selectedTask.status) },
                    { label: '流程 ID', value: selectedTask.pipelineId || '-' },
                    { label: '知识库 ID', value: selectedTask.kbId || '-' },
                    { label: '文档 ID', value: selectedTask.docId || '-' },
                    { label: '开始时间', value: formatDate(selectedTask.startedAt) },
                    { label: '结束时间', value: formatDate(selectedTask.finishedAt) },
                    { label: '错误信息', value: selectedTask.errorMessage || '-' },
                  ]"
                />

                <SurfaceCard compact class="mt-4" title="任务载荷 (Payload)" subtitle="执行此任务传入的参数。">
                  <DataPreview :data="selectedTask.payload || {}" />
                </SurfaceCard>

                <div class="meta-label !text-slate-500 mt-4">节点执行时间线</div>
                <div class="selection-list">
                  <article v-for="node in taskNodes" :key="node.id" class="resource-item">
                    <div class="resource-item-row">
                      <div class="mini-stack">
                        <div class="resource-title">{{ node.nodeName }}</div>
                        <div class="resource-meta">
                          <span>{{ node.durationMs ?? 0 }} ms</span>
                          <span>输出 {{ node.outputCount ?? 0 }}</span>
                        </div>
                      </div>
                      <span :class="statusClass(node.status)" class="status-badge">{{ formatStatus(node.status) }}</span>
                    </div>
                    <div class="resource-item-note mt-2 text-xs text-slate-500">{{ node.errorMessage || '节点执行完成，无额外错误信息。' }}</div>
                  </article>
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
import ModuleComposer from '@/components/admin/ModuleComposer.vue'
import PageHeader from '@/components/admin/PageHeader.vue'
import PaginationBar from '@/components/admin/PaginationBar.vue'
import SurfaceCard from '@/components/admin/SurfaceCard.vue'
import { adminService } from '@/services/adminService'
import { knowledgeService } from '@/services/knowledgeService'
import {
  buildPipelineNodes,
  ingestionModuleCatalog,
  ingestionPipelinePresets,
  moduleMeta,
  normalizePipelineNodes,
  type IngestionModuleSelection,
} from '@/modules/ingestionModules'
import { formatShanghaiDateTime } from '@/utils/date'

type PipelineSummary = {
  id: string
  name: string
  description?: string
  enabled?: boolean
  createdAt?: string
  updatedAt?: string
  nodes?: Array<Record<string, unknown>>
}

type KnowledgeBaseOption = {
  id: string
  name: string
}

type DocumentOption = {
  id: string
  docName: string
}

const loading = ref(false)
const error = ref('')
const pipelines = ref<PipelineSummary[]>([])
const tasks = ref<any[]>([])
const pipelinePagination = ref({ total: 0, pageNo: 1, pageSize: 6 })
const taskPagination = ref({ total: 0, pageNo: 1, pageSize: 8 })
const selectedPipeline = ref<PipelineSummary | null>(null)
const selectedTask = ref<any | null>(null)
const taskNodes = ref<any[]>([])
const loadingTaskDetail = ref(false)
const taskDetailError = ref('')
const drawerOpen = ref(false)

const knowledgeBases = ref<KnowledgeBaseOption[]>([])
const taskDocuments = ref<DocumentOption[]>([])

const pipelineForm = ref({ id: '', name: '', description: '' })
const selectedModules = ref<IngestionModuleSelection[]>([])
const moduleDraftKey = ref('')
const selectedPresetId = ref('standard_rag')

const taskForm = ref({
  name: '',
  kb_id: '',
  doc_id: '',
  pipeline_id: '',
  source: 'manual',
  retry: '0',
})

const retryOptions = ['0', '1', '2', '3']
const taskSourceOptions = [
  { value: 'manual', label: '手动触发' },
  { value: 'upload', label: '上传文件' },
  { value: 'schedule', label: '调度任务' },
]

const activePreset = computed(() => ingestionPipelinePresets.find((item) => item.id === selectedPresetId.value) ?? null)

const availableModuleOptions = computed(() =>
  ingestionModuleCatalog.filter((item) => !selectedModules.value.some((selected) => selected.key === item.key)),
)

const availableModuleViews = computed(() =>
  availableModuleOptions.value.map((item) => ({
    key: item.key,
    label: item.label,
    description: item.description,
    category: item.category,
  })),
)

const selectedModuleViews = computed(() =>
  selectedModules.value.map((item) => {
    const meta = moduleMeta(item.key)
    return {
      key: item.key,
      label: meta?.label || item.key,
      description: meta?.description || '已选择模块',
      category: meta?.category || '模块',
    }
  }),
)

const taskPayloadFacts = computed(() => [
  { label: '来源', value: taskSourceOptions.find((item) => item.value === taskForm.value.source)?.label || '-' },
  { label: '重试次数', value: `${Number(taskForm.value.retry)} 次` },
  { label: '知识库', value: knowledgeBases.value.find((item) => item.id === taskForm.value.kb_id)?.name || '未选择' },
  { label: '文档', value: taskDocuments.value.find((item) => item.id === taskForm.value.doc_id)?.docName || '未选择' },
])

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [pipelinePage, taskPage, kbPage] = await Promise.all([
      adminService.pipelines(pipelinePagination.value.pageNo, pipelinePagination.value.pageSize),
      adminService.tasks(taskPagination.value.pageNo, taskPagination.value.pageSize),
      knowledgeService.listKnowledgeBases(),
    ])
    pipelines.value = pipelinePage.items as PipelineSummary[]
    tasks.value = taskPage.items
    pipelinePagination.value = { total: pipelinePage.total, pageNo: pipelinePage.pageNo, pageSize: pipelinePage.pageSize }
    taskPagination.value = { total: taskPage.total, pageNo: taskPage.pageNo, pageSize: taskPage.pageSize }
    knowledgeBases.value = (kbPage.items || []).map((item: any) => ({ id: item.id, name: item.name }))
    if (selectedTask.value?.id) {
      selectedTask.value = tasks.value.find((item) => item.id === selectedTask.value.id) || null
    }
    if (taskForm.value.kb_id) {
      await loadTaskDocuments(taskForm.value.kb_id)
    }
  } catch (err: any) {
    error.value = err?.detail || err?.message || '摄取数据加载失败'
  } finally {
    loading.value = false
  }
}

async function loadTaskDocuments(kbId: string) {
  if (!kbId) {
    taskDocuments.value = []
    return
  }
  try {
    const page = await knowledgeService.listDocuments(kbId)
    taskDocuments.value = (page.items || []).map((item: any) => ({ id: item.id, docName: item.docName }))
  } catch {
    taskDocuments.value = []
  }
}

function applyPreset() {
  if (!activePreset.value) return
  selectedModules.value = activePreset.value.modules.map((key) => ({ key }))
  moduleDraftKey.value = ''
}

function addModule() {
  if (!moduleDraftKey.value) return
  selectedModules.value.push({ key: moduleDraftKey.value })
  moduleDraftKey.value = ''
}

function removeModule(index: number) {
  selectedModules.value.splice(index, 1)
}

function moveModule(index: number, offset: number) {
  const nextIndex = index + offset
  if (nextIndex < 0 || nextIndex >= selectedModules.value.length) return
  const cloned = [...selectedModules.value]
  const [item] = cloned.splice(index, 1)
  cloned.splice(nextIndex, 0, item)
  selectedModules.value = cloned
}

function resetPipelineModules() {
  selectedModules.value = buildDefaultModules()
  selectedPresetId.value = 'standard_rag'
  moduleDraftKey.value = ''
}

function buildDefaultModules() {
  return ingestionPipelinePresets[0].modules.map((key) => ({ key }))
}

function selectPipeline(item: PipelineSummary) {
  selectedPipeline.value = item
}

async function editPipeline(id: string) {
  const detail = await adminService.pipelineDetail(id)
  selectedPipeline.value = detail as PipelineSummary
  pipelineForm.value = {
    id: detail.id,
    name: detail.name,
    description: detail.description || '',
  }
  selectedModules.value = normalizePipelineNodes(detail.nodes)
  if (!selectedModules.value.length) {
    resetPipelineModules()
  }
}

function resetPipelineForm() {
  pipelineForm.value = { id: '', name: '', description: '' }
  resetPipelineModules()
}

async function submitPipeline() {
  const payload = {
    name: pipelineForm.value.name,
    description: pipelineForm.value.description,
    nodes: buildPipelineNodes(selectedModules.value),
  }
  if (pipelineForm.value.id) {
    await adminService.updatePipeline(pipelineForm.value.id, payload)
  } else {
    await adminService.createPipeline(payload)
  }
  resetPipelineForm()
  await load()
}

async function removePipeline(id: string) {
  await adminService.deletePipeline(id)
  if (selectedPipeline.value?.id === id) selectedPipeline.value = null
  await load()
}

async function submitTask() {
  await adminService.createTask({
    name: taskForm.value.name,
    kb_id: taskForm.value.kb_id || undefined,
    doc_id: taskForm.value.doc_id || undefined,
    pipeline_id: taskForm.value.pipeline_id || undefined,
    payload: {
      source: taskForm.value.source,
      retry: Number(taskForm.value.retry),
    },
  })
  taskForm.value = { name: '', kb_id: '', doc_id: '', pipeline_id: '', source: 'manual', retry: '0' }
  taskDocuments.value = []
  await load()
}

async function selectTask(taskId: string) {
  loadingTaskDetail.value = true
  taskDetailError.value = ''
  try {
    const [detail, nodes] = await Promise.all([
      adminService.taskDetail(taskId),
      adminService.taskNodes(taskId),
    ])
    selectedTask.value = detail
    taskNodes.value = nodes
  } catch (err: any) {
    taskDetailError.value = err?.detail || err?.message || '任务详情加载失败'
  } finally {
    loadingTaskDetail.value = false
  }
}

async function viewTaskDetails(taskId: string) {
  drawerOpen.value = true
  await selectTask(taskId)
}

function changePipelinePage(pageNo: number) {
  pipelinePagination.value.pageNo = pageNo
  void load()
}

function changeTaskPage(pageNo: number) {
  taskPagination.value.pageNo = pageNo
  void load()
}

function statusClass(status: string) {
  const normalized = String(status || '').toLowerCase()
  if (['success', 'completed'].includes(normalized)) return 'status-badge-success'
  if (['failed', 'error'].includes(normalized)) return 'status-badge-danger'
  if (['running', 'processing', 'pending'].includes(normalized)) return 'status-badge-warning'
  return 'status-badge-neutral'
}

function formatStatus(status?: string) {
  const map: Record<string, string> = {
    success: '成功',
    completed: '已完成',
    failed: '失败',
    error: '错误',
    running: '运行中',
    processing: '处理中',
    pending: '待处理',
  }
  return map[String(status || '').toLowerCase()] || status || '-'
}

function formatDate(value?: string) {
  return formatShanghaiDateTime(value)
}

watch(
  () => taskForm.value.kb_id,
  async (value) => {
    taskForm.value.doc_id = ''
    await loadTaskDocuments(value)
  },
)

onMounted(() => {
  resetPipelineModules()
  void load()
})
</script>

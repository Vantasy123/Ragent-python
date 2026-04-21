<template>
  <section>
    <PageHeader
      title="摄取任务中心"
      eyebrow="Ingestion Ops"
      description="主页面保留 Pipeline 管理和任务列表，任务详情改为抽屉查看。"
    >
      <template #actions>
        <button class="btn btn-secondary" @click="load">刷新数据</button>
      </template>
    </PageHeader>

    <div class="grid-two">
      <SurfaceCard title="Pipeline 管理" subtitle="从已有模块库中编排流程并维护节点顺序。">
        <div class="form-grid">
          <input v-model="pipelineForm.name" class="input" placeholder="Pipeline 名称" />
          <textarea v-model="pipelineForm.description" class="textarea" placeholder="Pipeline 描述" />

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

          <SurfaceCard compact title="提交流程预览" subtitle="实际发送到后端的节点定义。">
            <pre class="preformatted">{{ pipelineNodesPreview }}</pre>
          </SurfaceCard>

          <div class="inline-actions">
            <button class="btn btn-primary" :disabled="!pipelineForm.name.trim() || !selectedModules.length" @click="submitPipeline">
              {{ pipelineForm.id ? '保存 Pipeline' : '创建 Pipeline' }}
            </button>
            <button v-if="pipelineForm.id" class="btn btn-secondary" @click="resetPipelineForm">取消编辑</button>
          </div>
        </div>

        <div class="subtle-divider" />

        <AsyncState
          :loading="loading"
          :error="error"
          :empty="!pipelines.length"
          empty-title="暂无 Pipeline"
          empty-description="先配置一个摄取流程，后续任务才能绑定具体执行路径。"
        >
          <div class="list-stack">
            <article v-for="item in pipelines" :key="item.id" class="resource-item" :class="{ active: selectedPipelineId === item.id }">
              <button class="w-full text-left" @click="selectPipeline(item.id)">
                <div class="resource-title">{{ item.name }}</div>
                <div class="resource-meta">
                  <span>{{ item.enabled ? 'enabled' : 'disabled' }}</span>
                  <span>{{ formatDate(item.createdAt) }}</span>
                </div>
                <div class="helper-text mt-2">{{ item.description || '暂无描述' }}</div>
              </button>
              <div class="mt-3 inline-actions">
                <button class="btn btn-secondary" @click="editPipeline(item.id)">编辑</button>
                <button class="btn btn-danger" @click="removePipeline(item.id)">删除</button>
              </div>
            </article>
          </div>
        </AsyncState>
      </SurfaceCard>

      <div class="list-stack">
        <SurfaceCard title="任务创建" subtitle="通过下拉选择已有知识库、文档和来源配置。">
          <div class="form-grid form-grid-two">
            <input v-model="taskForm.name" class="input" placeholder="任务名称" />
            <select v-model="taskForm.pipeline_id" class="select">
              <option value="">选择 Pipeline</option>
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

          <SurfaceCard compact class="mt-4" title="任务上下文预览" subtitle="按表单生成 payload，无需手写 JSON。">
            <pre class="preformatted">{{ taskPayloadPreview }}</pre>
          </SurfaceCard>

          <div class="mt-4 inline-actions">
            <button class="btn btn-primary" :disabled="!taskForm.name.trim()" @click="submitTask">提交任务</button>
          </div>
        </SurfaceCard>

        <SurfaceCard title="任务列表" subtitle="在主页面查看状态，详情进入抽屉。">
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
                    <th>任务</th>
                    <th>状态</th>
                    <th>创建时间</th>
                    <th>完成时间</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="item in tasks" :key="item.id">
                    <td>{{ item.name }}</td>
                    <td><span :class="statusClass(item.status)" class="status-badge">{{ item.status }}</span></td>
                    <td>{{ formatDate(item.createdAt) }}</td>
                    <td>{{ formatDate(item.finishedAt) }}</td>
                    <td><button class="btn btn-secondary" @click="selectTask(item.id)">查看详情</button></td>
                  </tr>
                </tbody>
              </table>
            </div>
          </AsyncState>
        </SurfaceCard>
      </div>
    </div>

    <DetailDrawer
      :open="drawerOpen"
      title="任务详情"
      :subtitle="selectedTask?.name ? `${selectedTask.name} 的节点执行详情` : '加载中'"
      @close="drawerOpen = false"
    >
      <AsyncState
        :loading="loadingTaskDetail"
        :error="taskDetailError"
        :empty="!selectedTask"
        empty-title="尚未选择任务"
        empty-description="从任务列表中选择一项查看执行节点与错误信息。"
      >
        <div v-if="selectedTask" class="list-stack">
          <KeyValueGrid
            :items="[
              { label: '状态', value: selectedTask.status },
              { label: '错误信息', value: selectedTask.errorMessage || '无' },
              { label: '开始时间', value: formatDate(selectedTask.startedAt) },
              { label: '结束时间', value: formatDate(selectedTask.finishedAt) },
            ]"
          />

          <div class="selection-list">
            <article v-for="node in taskNodes" :key="node.id" class="resource-item">
              <div class="resource-item-row">
                <div class="mini-stack">
                  <div class="resource-title">{{ node.nodeName }}</div>
                  <div class="resource-meta">
                    <span>{{ node.durationMs ?? 0 }} ms</span>
                    <span>output {{ node.outputCount ?? 0 }}</span>
                  </div>
                </div>
                <span :class="statusClass(node.status)" class="status-badge">{{ node.status }}</span>
              </div>
              <div class="resource-item-note">{{ node.errorMessage || '节点执行完成，无额外错误信息。' }}</div>
            </article>
          </div>
        </div>
      </AsyncState>
    </DetailDrawer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import AsyncState from '@/components/admin/AsyncState.vue'
import DetailDrawer from '@/components/admin/DetailDrawer.vue'
import KeyValueGrid from '@/components/admin/KeyValueGrid.vue'
import ModuleComposer from '@/components/admin/ModuleComposer.vue'
import PageHeader from '@/components/admin/PageHeader.vue'
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

type PipelineSummary = {
  id: string
  name: string
  description?: string
  enabled?: boolean
  createdAt?: string
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
const selectedPipelineId = ref('')
const drawerOpen = ref(false)
const selectedTask = ref<any | null>(null)
const taskNodes = ref<any[]>([])
const loadingTaskDetail = ref(false)
const taskDetailError = ref('')

const knowledgeBases = ref<KnowledgeBaseOption[]>([])
const taskDocuments = ref<DocumentOption[]>([])

const pipelineForm = ref({ id: '', name: '', description: '' })
const selectedModules = ref<IngestionModuleSelection[]>([])
const moduleDraftKey = ref('')
const selectedPresetId = ref('')

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

const pipelineNodesPreview = computed(() => JSON.stringify(buildPipelineNodes(selectedModules.value), null, 2))

const taskPayloadPreview = computed(() =>
  JSON.stringify(
    {
      source: taskForm.value.source,
      retry: Number(taskForm.value.retry),
      kb_id: taskForm.value.kb_id || undefined,
      doc_id: taskForm.value.doc_id || undefined,
    },
    null,
    2,
  ),
)

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [pipelinePage, taskPage, kbPage] = await Promise.all([
      adminService.pipelines(),
      adminService.tasks(),
      knowledgeService.listKnowledgeBases(),
    ])
    pipelines.value = pipelinePage.items as PipelineSummary[]
    tasks.value = taskPage.items
    knowledgeBases.value = (kbPage.items || []).map((item: any) => ({ id: item.id, name: item.name }))
    if (taskForm.value.kb_id) {
      await loadTaskDocuments(taskForm.value.kb_id)
    }
  } catch (err: any) {
    error.value = err?.detail || err?.message || '摄取模块加载失败'
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

async function selectPipeline(id: string) {
  selectedPipelineId.value = id
}

async function editPipeline(id: string) {
  const detail = await adminService.pipelineDetail(id)
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
  if (selectedPipelineId.value === id) selectedPipelineId.value = ''
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
  drawerOpen.value = true
  loadingTaskDetail.value = true
  taskDetailError.value = ''
  try {
    const [detail, nodes] = await Promise.all([adminService.taskDetail(taskId), adminService.taskNodes(taskId)])
    selectedTask.value = detail
    taskNodes.value = nodes
  } catch (err: any) {
    taskDetailError.value = err?.detail || err?.message || '任务详情加载失败'
  } finally {
    loadingTaskDetail.value = false
  }
}

function formatDate(value?: string) {
  return value ? new Date(value).toLocaleString() : '-'
}

function statusClass(status: string) {
  const normalized = String(status || '').toLowerCase()
  if (['success', 'completed'].includes(normalized)) return 'status-badge-success'
  if (['failed', 'error'].includes(normalized)) return 'status-badge-danger'
  if (['processing', 'pending', 'running'].includes(normalized)) return 'status-badge-warning'
  return 'status-badge-neutral'
}

watch(
  () => taskForm.value.kb_id,
  async (kbId) => {
    taskForm.value.doc_id = ''
    await loadTaskDocuments(kbId)
  },
)

onMounted(async () => {
  resetPipelineModules()
  await load()
})
</script>

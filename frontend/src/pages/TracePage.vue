<template>
  <section>
    <PageHeader
      title="链路追踪"
      eyebrow="Observability"
      description="查看聊天、检索、重排、生成等节点的运行状态、耗时和输入输出摘要。"
    >
      <template #actions>
        <button class="btn btn-secondary" @click="load">刷新</button>
      </template>
    </PageHeader>

    <SurfaceCard title="Trace Runs" subtitle="选择一条 trace 后，在右侧抽屉查看节点详情。">
      <AsyncState
        :loading="loading"
        :error="error"
        :empty="!runs.length"
        empty-title="暂无追踪记录"
        empty-description="执行聊天或工作流后，追踪记录会出现在这里。"
      >
        <div class="table-wrap">
          <table class="data-table">
            <thead>
              <tr>
                <th>Trace ID</th>
                <th>状态</th>
                <th>耗时</th>
                <th>开始时间</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in runs" :key="item.traceId">
                <td>{{ item.traceId }}</td>
                <td><span :class="statusClass(item.status)" class="status-badge">{{ item.status }}</span></td>
                <td>{{ item.totalDurationMs ?? 0 }} ms</td>
                <td>{{ formatDate(item.createdAt) }}</td>
                <td><button class="btn btn-secondary" @click="selectRun(item.traceId)">查看详情</button></td>
              </tr>
            </tbody>
          </table>
        </div>
      </AsyncState>
    </SurfaceCard>

    <DetailDrawer
      :open="drawerOpen"
      title="Trace 详情"
      :subtitle="selectedRun?.traceId ? `当前 Trace: ${selectedRun.traceId}` : '加载中'"
      @close="closeDrawer"
    >
      <AsyncState
        :loading="loadingDetail"
        :error="detailError"
        :empty="!selectedRun"
        empty-title="尚未选择 Trace"
        empty-description="从左侧表格中选择一条 trace 查看详情。"
      >
        <div v-if="selectedRun" class="list-stack">
          <KeyValueGrid :items="selectedRunFacts" />

          <div class="grid-two">
            <div class="selection-list">
              <button
                v-for="node in normalizedNodes"
                :key="node.id"
                type="button"
                class="selection-item"
                :class="{ active: selectedNodeId === node.id }"
                @click="selectedNodeId = node.id"
              >
                <div class="resource-item-row">
                  <div class="mini-stack">
                    <div class="resource-title">{{ node.displayName }}</div>
                    <div class="resource-meta">
                      <span>{{ node.operation }}</span>
                      <span>{{ node.durationMs }} ms</span>
                    </div>
                  </div>
                  <span :class="statusClass(node.status)" class="status-badge">{{ node.status }}</span>
                </div>
              </button>
            </div>

            <SurfaceCard
              compact
              :title="selectedNode ? selectedNode.displayName : '节点详情'"
              subtitle="输入、输出、元数据和错误信息"
            >
              <div v-if="selectedNode" class="list-stack">
                <KeyValueGrid
                  :items="[
                    { label: '节点', value: selectedNode.displayName },
                    { label: 'Operation', value: selectedNode.operation },
                    { label: '状态', value: selectedNode.status || '-' },
                    { label: '耗时', value: `${selectedNode.durationMs} ms` },
                  ]"
                />

                <SurfaceCard v-if="selectedNode.errorMessage" compact title="错误信息">
                  <DataPreview :data="selectedNode.errorMessage" />
                </SurfaceCard>

                <div class="grid-two">
                  <SurfaceCard compact title="输入摘要">
                    <DataPreview :data="selectedNode.input" />
                  </SurfaceCard>
                  <SurfaceCard compact title="输出摘要">
                    <DataPreview :data="selectedNode.output" />
                  </SurfaceCard>
                </div>

                <SurfaceCard compact title="完整元数据">
                  <DataPreview :data="selectedNode.metadata" />
                </SurfaceCard>
              </div>
            </SurfaceCard>
          </div>
        </div>
      </AsyncState>
    </DetailDrawer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import AsyncState from '@/components/admin/AsyncState.vue'
import DataPreview from '@/components/admin/DataPreview.vue'
import DetailDrawer from '@/components/admin/DetailDrawer.vue'
import KeyValueGrid from '@/components/admin/KeyValueGrid.vue'
import PageHeader from '@/components/admin/PageHeader.vue'
import SurfaceCard from '@/components/admin/SurfaceCard.vue'
import { adminService } from '@/services/adminService'

type TraceNode = {
  id: string
  name?: string
  operation?: string
  spanName?: string
  nodeName?: string
  status?: string
  durationMs?: number
  input?: unknown
  output?: unknown
  request?: unknown
  response?: unknown
  metadata?: Record<string, unknown>
  errorMessage?: string
}

const loading = ref(false)
const error = ref('')
const runs = ref<any[]>([])
const drawerOpen = ref(false)
const selectedRun = ref<any | null>(null)
const nodes = ref<TraceNode[]>([])
const selectedNodeId = ref('')
const loadingDetail = ref(false)
const detailError = ref('')

function nodeDisplayName(node: TraceNode) {
  return node.name || node.operation || node.spanName || node.nodeName || '未命名节点'
}

function nodeInput(node: TraceNode) {
  return node.input ?? node.request ?? node.metadata ?? {}
}

function nodeOutput(node: TraceNode) {
  return node.output ?? node.response ?? node.metadata ?? {}
}

const normalizedNodes = computed(() =>
  nodes.value.map((node) => ({
    ...node,
    displayName: nodeDisplayName(node),
    operation: node.operation || node.name || node.spanName || node.nodeName || '-',
    status: node.status || '-',
    durationMs: node.durationMs ?? 0,
    input: nodeInput(node),
    output: nodeOutput(node),
    metadata: node.metadata || {},
  })),
)

const selectedNode = computed(() => normalizedNodes.value.find((item) => item.id === selectedNodeId.value) || normalizedNodes.value[0] || null)

const selectedRunFacts = computed(() => {
  if (!selectedRun.value) return []
  return [
    { label: 'Trace ID', value: selectedRun.value.traceId || '-' },
    { label: '状态', value: selectedRun.value.status || '-' },
    { label: '总耗时', value: `${selectedRun.value.totalDurationMs ?? 0} ms` },
    { label: '开始时间', value: formatDate(selectedRun.value.createdAt) },
  ]
})

async function load() {
  loading.value = true
  error.value = ''
  try {
    runs.value = await adminService.traces()
  } catch (err: any) {
    error.value = err?.detail || err?.message || 'Trace 列表加载失败'
  } finally {
    loading.value = false
  }
}

async function selectRun(traceId: string) {
  drawerOpen.value = true
  loadingDetail.value = true
  detailError.value = ''
  try {
    const [detail, nodeList] = await Promise.all([adminService.traceDetail(traceId), adminService.traceNodes(traceId)])
    selectedRun.value = detail
    nodes.value = nodeList as TraceNode[]
    selectedNodeId.value = nodeList[0]?.id || ''
  } catch (err: any) {
    detailError.value = err?.detail || err?.message || 'Trace 详情加载失败'
  } finally {
    loadingDetail.value = false
  }
}

function closeDrawer() {
  drawerOpen.value = false
}

function statusClass(status: string) {
  const normalized = String(status || '').toLowerCase()
  if (['success', 'completed'].includes(normalized)) return 'status-badge-success'
  if (['failed', 'error'].includes(normalized)) return 'status-badge-danger'
  if (['running', 'processing', 'pending'].includes(normalized)) return 'status-badge-warning'
  return 'status-badge-neutral'
}

function formatDate(value?: string) {
  return value ? new Date(value).toLocaleString() : '-'
}

onMounted(load)
</script>

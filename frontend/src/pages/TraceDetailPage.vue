<template>
  <section>
    <PageHeader
      :title="detail.traceId ? `Trace 详情 / ${detail.traceId}` : 'Trace 详情'"
      eyebrow="Trace Detail"
      description="展示基础信息、节点时间线、输入输出摘要和评估结果。"
    >
      <template #actions>
        <div class="inline-actions">
          <router-link class="btn btn-secondary" to="/admin/traces">返回 Trace 列表</router-link>
          <button class="btn btn-secondary" @click="load">刷新</button>
        </div>
      </template>
    </PageHeader>

    <AsyncState :loading="loading" :error="error" :empty="!detail.traceId" empty-title="Trace 不存在">
      <div class="grid-two">
        <SurfaceCard title="运行摘要" subtitle="会话、任务、状态和总耗时。">
          <KeyValueGrid :items="facts" />
        </SurfaceCard>

        <SurfaceCard title="评估摘要" subtitle="如果已有评估结果，这里直接展示概览。">
          <DataPreview :data="detail.evaluationSummary || { message: '暂无评估摘要' }" />
        </SurfaceCard>
      </div>

      <div class="grid-two mt-5">
        <SurfaceCard title="节点时间线" subtitle="按时间顺序查看各节点的运行结果。">
          <div class="selection-list">
            <button
              v-for="node in nodes"
              :key="node.id"
              type="button"
              class="selection-item"
              :class="{ active: selectedNodeId === node.id }"
              @click="selectedNodeId = node.id"
            >
              <div class="resource-item-row">
                <div class="mini-stack">
                  <div class="resource-title">{{ node.name || node.operation }}</div>
                  <div class="resource-meta">
                    <span>{{ node.operation }}</span>
                    <span>{{ node.durationMs ?? 0 }} ms</span>
                  </div>
                </div>
                <span :class="statusClass(node.status)" class="status-badge">{{ formatStatus(node.status) }}</span>
              </div>
            </button>
          </div>
        </SurfaceCard>

        <SurfaceCard :title="selectedNode?.name || selectedNode?.operation || '节点详情'" subtitle="查看节点输入、输出和错误信息。">
          <AsyncState :loading="false" :empty="!selectedNode" empty-title="未选择节点">
            <div v-if="selectedNode" class="list-stack">
              <KeyValueGrid
                :items="[
                  { label: '节点', value: selectedNode.name || selectedNode.operation || '-' },
                  { label: '状态', value: formatStatus(selectedNode.status) },
                  { label: '耗时', value: `${selectedNode.durationMs ?? 0} ms` },
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
          </AsyncState>
        </SurfaceCard>
      </div>
    </AsyncState>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import AsyncState from '@/components/admin/AsyncState.vue'
import DataPreview from '@/components/admin/DataPreview.vue'
import KeyValueGrid from '@/components/admin/KeyValueGrid.vue'
import PageHeader from '@/components/admin/PageHeader.vue'
import SurfaceCard from '@/components/admin/SurfaceCard.vue'
import { adminService } from '@/services/adminService'
import { formatShanghaiDateTime } from '@/utils/date'

const route = useRoute()
const traceId = computed(() => String(route.params.traceId || ''))

const loading = ref(false)
const error = ref('')
const detail = ref<Record<string, any>>({})
const nodes = ref<any[]>([])
const selectedNodeId = ref('')

const selectedNode = computed(() => nodes.value.find((item) => item.id === selectedNodeId.value) || nodes.value[0] || null)
const facts = computed(() => [
  { label: 'Trace ID', value: detail.value.traceId || '-' },
  { label: '会话 ID', value: detail.value.sessionId || '-' },
  { label: '任务 ID', value: detail.value.taskId || '-' },
  { label: '状态', value: formatStatus(detail.value.status) },
  { label: '总耗时', value: `${detail.value.totalDurationMs ?? 0} ms` },
  { label: '创建时间', value: formatDate(detail.value.createdAt) },
])

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [runDetail, nodeList] = await Promise.all([
      adminService.traceDetail(traceId.value),
      adminService.traceNodes(traceId.value),
    ])
    detail.value = runDetail
    nodes.value = nodeList
    selectedNodeId.value = nodeList[0]?.id || ''
  } catch (err: any) {
    error.value = err?.detail || err?.message || 'Trace 详情加载失败'
  } finally {
    loading.value = false
  }
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

watch(traceId, () => {
  void load()
})

onMounted(load)
</script>

<template>
  <section>
    <PageHeader
      title="运营仪表盘"
      eyebrow="Admin Overview"
      description="把概览、性能和趋势拆成结构化卡片，避免后台直接展示原始 JSON。"
    >
      <template #actions>
        <button class="btn btn-secondary" @click="load">刷新数据</button>
      </template>
    </PageHeader>

    <AsyncState :loading="loading" :error="error">
      <div class="dashboard-grid">
        <article v-for="item in metrics" :key="item.label" class="metric-card">
          <div class="meta-label !text-slate-500">{{ item.label }}</div>
          <div class="metric-value">{{ item.value }}</div>
          <div class="metric-trend">{{ item.trend }}</div>
        </article>
      </div>

      <div class="grid-two mt-5">
        <SurfaceCard title="系统概览" subtitle="按业务面汇总主要规模指标。">
          <KeyValueGrid :items="overviewDetails" />
        </SurfaceCard>

        <SurfaceCard title="性能视图" subtitle="聚合响应、检索和错误相关指标。">
          <KeyValueGrid :items="performanceDetails" />
        </SurfaceCard>
      </div>

      <div class="grid-two mt-5">
        <SurfaceCard title="趋势面板" subtitle="按模块查看趋势返回的结构化摘要。">
          <div class="list-stack">
            <article v-for="item in trendCards" :key="item.title" class="resource-item">
              <div class="resource-title">{{ item.title }}</div>
              <div class="resource-item-note">趋势数据摘要</div>
              <div class="mt-3">
                <DataPreview :data="item.data" />
              </div>
            </article>
          </div>
        </SurfaceCard>

        <SurfaceCard title="补充指标" subtitle="将原本裸露的性能明细收敛成可读字段列表。">
          <KeyValueGrid :items="extraPerformance" />
        </SurfaceCard>
      </div>
    </AsyncState>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import AsyncState from '@/components/admin/AsyncState.vue'
import DataPreview from '@/components/admin/DataPreview.vue'
import KeyValueGrid from '@/components/admin/KeyValueGrid.vue'
import PageHeader from '@/components/admin/PageHeader.vue'
import SurfaceCard from '@/components/admin/SurfaceCard.vue'
import { adminService } from '@/services/adminService'

const loading = ref(false)
const error = ref('')
const overview = ref<Record<string, any>>({})
const performance = ref<Record<string, any>>({})
const trends = ref<Record<string, any>>({})

const metrics = computed(() => [
  { label: '知识库', value: overview.value.knowledgeBases ?? 0, trend: `${overview.value.documents ?? 0} 份文档` },
  { label: '会话量', value: overview.value.conversations ?? 0, trend: `${overview.value.messages ?? 0} 条消息` },
  { label: 'Trace 数', value: overview.value.traces ?? 0, trend: `${overview.value.traceSpans ?? 0} 个 span` },
  { label: '用户数', value: overview.value.users ?? 0, trend: `${overview.value.adminUsers ?? 0} 位管理员` },
])

const overviewDetails = computed(() => [
  { label: '文档总数', value: overview.value.documents ?? 0 },
  { label: 'Chunk 总数', value: overview.value.chunks ?? 0 },
  { label: '摄取任务', value: overview.value.ingestionTasks ?? 0 },
  { label: 'Pipeline 数量', value: overview.value.ingestionPipelines ?? 0 },
])

const performanceDetails = computed(() => [
  { label: '平均响应耗时', value: `${performance.value.avgResponseMs ?? 0} ms` },
  { label: '平均检索耗时', value: `${performance.value.avgRetrievalMs ?? 0} ms` },
  { label: '成功率', value: `${performance.value.successRate ?? 0}%` },
  { label: '错误请求', value: performance.value.errorCount ?? 0 },
])

const trendCards = computed(() =>
  Object.entries(trends.value || {}).map(([key, value]) => ({
    title: key,
    data: value,
  })),
)

const extraPerformance = computed(() =>
  Object.entries(performance.value || {})
    .filter(([key]) => !['avgResponseMs', 'avgRetrievalMs', 'successRate', 'errorCount'].includes(key))
    .map(([key, value]) => ({ label: key, value })),
)

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [overviewData, performanceData, trendData] = await Promise.all([
      adminService.overview(),
      adminService.performance(),
      adminService.trends(),
    ])
    overview.value = overviewData
    performance.value = performanceData
    trends.value = trendData
  } catch (err: any) {
    error.value = err?.detail || err?.message || '仪表盘加载失败'
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

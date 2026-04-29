<template>
  <section>
    <PageHeader
      title="运营仪表盘"
      eyebrow="后台总览"
      description="将概览、性能和趋势拆成结构化卡片，优先展示真实业务指标。"
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

        <SurfaceCard title="性能视图" subtitle="聚合响应、检索和评估相关指标。">
          <KeyValueGrid :items="performanceDetails" />
        </SurfaceCard>
      </div>

      <div class="grid-two mt-5">
        <SurfaceCard title="近 7 日趋势" subtitle="按天查看会话与链路变化。">
          <AsyncState :loading="false" :empty="!trendPoints.length" empty-title="暂无趋势数据">
            <div class="list-stack">
              <article v-for="item in trendPoints" :key="item.date" class="resource-item">
                <div class="resource-item-row">
                  <div class="resource-title">{{ item.date }}</div>
                  <div class="resource-meta">
                    <span>会话 {{ item.conversations ?? 0 }}</span>
                    <span>链路 {{ item.traceRuns ?? 0 }}</span>
                  </div>
                </div>
              </article>
            </div>
          </AsyncState>
        </SurfaceCard>

        <SurfaceCard title="评估与健康度" subtitle="展示在线评估和慢请求相关指标。">
          <KeyValueGrid :items="evaluationDetails" />
        </SurfaceCard>
      </div>
    </AsyncState>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import AsyncState from '@/components/admin/AsyncState.vue'
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
  { label: '追踪数量', value: overview.value.traceRuns ?? 0, trend: `${overview.value.traceSpans ?? 0} 个节点` },
  { label: '用户数', value: overview.value.users ?? 0, trend: `${overview.value.adminUsers ?? 0} 位管理员` },
])

const overviewDetails = computed(() => [
  { label: '文档总数', value: overview.value.documents ?? 0 },
  { label: '分块总数', value: overview.value.chunks ?? 0 },
  { label: '摄取任务', value: overview.value.ingestionTasks ?? 0 },
  { label: '流程数量', value: overview.value.ingestionPipelines ?? 0 },
])

const performanceDetails = computed(() => [
  { label: '平均响应耗时', value: `${performance.value.avgResponseMs ?? 0} ms` },
  { label: '平均检索耗时', value: `${performance.value.avgRetrievalMs ?? 0} ms` },
  { label: '平均链路耗时', value: `${performance.value.avgTraceDurationMs ?? 0} ms` },
  { label: '成功率', value: `${performance.value.successRate ?? 0}%` },
  { label: '错误请求', value: performance.value.errorCount ?? 0 },
  { label: '已完成任务', value: performance.value.completedTasks ?? 0 },
])

const evaluationDetails = computed(() => [
  { label: '平均评估分', value: scoreText(performance.value.avgEvaluationScore) },
  { label: '满意率', value: `${performance.value.feedbackSatisfactionRate ?? 0}%` },
  { label: '低分运行', value: performance.value.lowScoreRuns ?? 0 },
  { label: 'P50 总耗时', value: `${performance.value.evaluation?.p50TotalMs ?? 0} ms` },
  { label: 'P95 总耗时', value: `${performance.value.evaluation?.p95TotalMs ?? 0} ms` },
])

const trendPoints = computed(() => (Array.isArray(trends.value.points) ? trends.value.points : []))

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

function scoreText(value?: number) {
  const score = Number(value ?? 0)
  return score <= 1 ? score.toFixed(2) : String(score)
}

onMounted(load)
</script>

<template>
  <div class="preview-stack">
    <div v-if="summaryEntries.length" class="preview-grid">
      <article v-for="entry in summaryEntries" :key="entry.label" class="preview-card">
        <div class="meta-label !text-slate-500">{{ entry.label }}</div>
        <div class="preview-value">{{ entry.value }}</div>
      </article>
    </div>
    <div v-else class="helper-text">{{ emptyText }}</div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { formatShanghaiDateTime } from '@/utils/date'

const props = withDefaults(defineProps<{
  data?: unknown
  emptyText?: string
  limit?: number
}>(), {
  emptyText: '暂无结构化数据',
  limit: 8,
})

const VALUE_TEXT: Record<string, string> = {
  success: '成功',
  completed: '已完成',
  failed: '失败',
  error: '错误',
  pending: '待处理',
  running: '运行中',
  processing: '处理中',
  enabled: '已启用',
  disabled: '已停用',
  high: '高',
  medium: '中',
  low: '低',
  true: '是',
  false: '否',
}

const LABEL_TEXT: Record<string, string> = {
  id: 'ID',
  name: '名称',
  title: '标题',
  type: '类型',
  status: '状态',
  message: '消息',
  summary: '摘要',
  content: '内容',
  error: '错误',
  errorMessage: '错误信息',
  durationMs: '耗时',
  totalDurationMs: '总耗时',
  createdAt: '创建时间',
  updatedAt: '更新时间',
  startedAt: '开始时间',
  finishedAt: '结束时间',
  sourceCount: '来源数量',
  chunks: '分块数',
  chunkCount: '分块数',
  score: '评分',
  overallScore: '综合评分',
  reason: '原因',
  evidence: '证据',
  dimension: '维度',
  metricKey: '指标',
  issueKey: '问题类型',
  severity: '严重级别',
  toolName: '工具',
  tool: '工具',
  args: '参数',
  result: '结果',
  approvals: '审批',
  riskLevel: '风险等级',
  agent: '智能体',
  task: '任务',
  observation: '观察结果',
}

const IMPORTANT_KEYS = [
  'summary',
  'message',
  'content',
  'status',
  'errorMessage',
  'error',
  'name',
  'title',
  'toolName',
  'tool',
  'score',
  'overallScore',
  'durationMs',
  'totalDurationMs',
  'chunkCount',
  'chunks',
]

function valueText(value: string): string {
  return VALUE_TEXT[value.toLowerCase()] || value
}

function labelText(key: string): string {
  return LABEL_TEXT[key] || key
}

function formatDateLike(value: string): string {
  if (!/^\d{4}-\d{2}-\d{2}T/.test(value)) return valueText(value)
  return formatShanghaiDateTime(value)
}

function summarizeObject(value: Record<string, unknown>, depth: number): string {
  const importantKey = IMPORTANT_KEYS.find((key) => value[key] !== undefined && value[key] !== null && value[key] !== '')
  if (importantKey) {
    return `${labelText(importantKey)}：${summarize(value[importantKey], depth - 1)}`
  }

  const pairs = Object.entries(value)
    .filter(([, item]) => item !== undefined && item !== null && item !== '')
    .slice(0, 3)
    .map(([key, item]) => `${labelText(key)}：${summarize(item, depth - 1)}`)

  return pairs.length ? pairs.join('；') : '-'
}

function summarize(value: unknown, depth = 4): string {
  if (value === null || value === undefined || value === '') return '-'
  if (typeof value === 'boolean') return value ? '是' : '否'
  if (typeof value === 'number') return Number.isInteger(value) ? String(value) : value.toFixed(3)
  if (typeof value === 'string') return formatDateLike(value)
  if (Array.isArray(value)) {
    if (!value.length) return '-'
    if (depth <= 0) return `${value.length} 条记录`
    return value.slice(0, 3).map((item) => summarize(item, depth - 1)).join('；')
  }
  if (typeof value === 'object') {
    return summarizeObject(value as Record<string, unknown>, depth)
  }
  return String(value)
}

const summaryEntries = computed(() => {
  const data = props.data
  if (!data) return []
  if (Array.isArray(data)) {
    return data.slice(0, props.limit).map((item, index) => ({
      label: `条目 ${index + 1}`,
      value: summarize(item),
    }))
  }
  if (typeof data === 'object') {
    return Object.entries(data as Record<string, unknown>).slice(0, props.limit).map(([key, value]) => ({
      label: labelText(key),
      value: summarize(value),
    }))
  }
  return [{ label: '值', value: summarize(data) }]
})
</script>

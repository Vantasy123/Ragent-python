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

const props = withDefaults(defineProps<{
  data?: unknown
  emptyText?: string
  limit?: number
}>(), {
  emptyText: '暂无结构化数据',
  limit: 8,
})

function summarize(value: unknown): string {
  if (value === null || value === undefined || value === '') return '-'
  if (Array.isArray(value)) return value.length ? value.map((item) => summarize(item)).join(', ') : '-'
  if (typeof value === 'object') {
    const keys = Object.keys(value as Record<string, unknown>)
    return keys.length ? `${keys.length} fields` : '-'
  }
  return String(value)
}

const summaryEntries = computed(() => {
  const data = props.data
  if (!data) return []
  if (Array.isArray(data)) {
    return data.slice(0, props.limit).map((item, index) => ({
      label: `item_${index + 1}`,
      value: summarize(item),
    }))
  }
  if (typeof data === 'object') {
    return Object.entries(data as Record<string, unknown>).slice(0, props.limit).map(([key, value]) => ({
      label: key,
      value: summarize(value),
    }))
  }
  return [{ label: 'value', value: summarize(data) }]
})
</script>

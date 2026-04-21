<template>
  <div class="detail-grid" :class="columns === 1 ? 'detail-grid-single' : ''">
    <div v-for="item in normalizedItems" :key="item.label" class="detail-item">
      <div class="meta-label !text-slate-500">{{ item.label }}</div>
      <div class="detail-value">{{ item.value }}</div>
      <div v-if="item.hint" class="helper-text mt-1">{{ item.hint }}</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface KeyValueItem {
  label: string
  value: string | number | boolean | null | undefined
  hint?: string
}

const props = withDefaults(defineProps<{
  items: KeyValueItem[]
  columns?: 1 | 2
}>(), {
  columns: 2,
})

const normalizedItems = computed(() =>
  props.items.map((item) => ({
    ...item,
    value: item.value === null || item.value === undefined || item.value === '' ? '-' : String(item.value),
  })),
)
</script>

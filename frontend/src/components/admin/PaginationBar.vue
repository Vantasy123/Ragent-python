<template>
  <div class="pagination-bar">
    <div class="helper-text">
      共 {{ total }} 条，当前第 {{ currentPage }} / {{ totalPages }} 页
    </div>
    <div class="inline-actions">
      <button class="btn btn-secondary" :disabled="currentPage <= 1" @click="$emit('update:page', currentPage - 1)">上一页</button>
      <button class="btn btn-secondary" :disabled="currentPage >= totalPages" @click="$emit('update:page', currentPage + 1)">下一页</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  total: number
  pageSize: number
  currentPage: number
}>(), {
  total: 0,
  pageSize: 20,
  currentPage: 1,
})

defineEmits<{
  'update:page': [value: number]
}>()

const totalPages = computed(() => Math.max(1, Math.ceil(props.total / Math.max(props.pageSize, 1))))
</script>

<template>
  <div v-if="loading" class="state-card">
    <div class="state-title">正在加载</div>
    <div class="state-description">{{ loadingText || '正在同步最新数据。' }}</div>
  </div>
  <div v-else-if="error" class="state-card state-card-danger">
    <div class="state-title">加载失败</div>
    <div class="state-description">{{ error }}</div>
  </div>
  <div v-else-if="empty" class="state-card">
    <div class="state-title">{{ emptyTitle || '暂无数据' }}</div>
    <div v-if="emptyDescription" class="state-description">{{ emptyDescription }}</div>
  </div>
  <slot v-else />
</template>

<script setup lang="ts">
defineProps<{
  loading?: boolean
  error?: string
  empty?: boolean
  loadingText?: string
  emptyTitle?: string
  emptyDescription?: string
}>()
</script>

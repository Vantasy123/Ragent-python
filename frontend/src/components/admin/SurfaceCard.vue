<template>
  <section class="panel" :class="compact ? 'panel-compact' : ''">
    <div v-if="title || subtitle || $slots.actions" class="panel-head">
      <div>
        <div v-if="title" class="panel-title">{{ title }}</div>
        <div v-if="subtitle" class="panel-subtitle">{{ subtitle }}</div>
      </div>
      <div v-if="$slots.actions" class="panel-actions">
        <slot name="actions" />
      </div>
    </div>
    <slot />
  </section>
</template>

<script setup lang="ts">
defineProps<{
  title?: string
  subtitle?: string
  compact?: boolean
}>()
</script>

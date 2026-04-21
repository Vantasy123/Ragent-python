<template>
  <transition name="drawer-fade">
    <div v-if="open" class="drawer-backdrop" @click.self="$emit('close')">
      <aside class="drawer-panel">
        <div class="drawer-head">
          <div>
            <div class="panel-title">{{ title }}</div>
            <div v-if="subtitle" class="panel-subtitle">{{ subtitle }}</div>
          </div>
          <button class="btn btn-ghost" type="button" @click="$emit('close')">关闭</button>
        </div>
        <div class="drawer-body">
          <slot />
        </div>
      </aside>
    </div>
  </transition>
</template>

<script setup lang="ts">
defineProps<{
  open: boolean
  title: string
  subtitle?: string
}>()

defineEmits<{
  close: []
}>()
</script>

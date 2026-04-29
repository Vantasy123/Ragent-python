<template>
  <div class="panel panel-compact">
    <div class="panel-head">
      <div>
        <div class="panel-title">{{ title }}</div>
        <div class="panel-subtitle">{{ subtitle }}</div>
      </div>
    </div>

    <div v-if="presets.length" class="list-stack">
      <div class="inline-actions">
        <select :value="selectedPresetId" class="select" @change="onPresetChange">
          <option value="">{{ presetPlaceholder }}</option>
          <option v-for="preset in presets" :key="preset.id" :value="preset.id">
            {{ preset.label }}
          </option>
        </select>
        <button class="btn btn-secondary" type="button" :disabled="!selectedPresetId" @click="$emit('apply-preset')">
          应用模板
        </button>
      </div>
      <div v-if="activePreset" class="helper-text">
        {{ activePreset.description }}
      </div>
    </div>

    <div class="inline-actions mt-4">
      <select :value="draftKey" class="select" @change="onDraftChange">
        <option value="">{{ modulePlaceholder }}</option>
        <option v-for="item in availableOptions" :key="item.key" :value="item.key">
          {{ item.label }} · {{ item.category }}
        </option>
      </select>
      <button class="btn btn-secondary" type="button" :disabled="!draftKey" @click="$emit('add-module')">
        添加模块
      </button>
      <button class="btn btn-secondary" type="button" @click="$emit('reset-modules')">
        恢复默认
      </button>
    </div>

    <div v-if="modules.length" class="list-stack mt-4">
      <article v-for="(item, index) in modules" :key="`${item.key}-${index}`" class="resource-item">
        <div class="flex items-start justify-between gap-4">
          <div>
            <div class="resource-title">{{ index + 1 }}. {{ item.label || item.key }}</div>
            <div class="resource-meta">
              <span>{{ item.category || '模块' }}</span>
            </div>
            <div class="helper-text mt-2">{{ item.description || '已选择模块' }}</div>
          </div>
          <div class="inline-actions">
            <button class="btn btn-secondary" type="button" :disabled="index === 0" @click="$emit('move-module', index, -1)">
              上移
            </button>
            <button class="btn btn-secondary" type="button" :disabled="index === modules.length - 1" @click="$emit('move-module', index, 1)">
              下移
            </button>
            <button class="btn btn-danger" type="button" @click="$emit('remove-module', index)">
              移除
            </button>
          </div>
        </div>
      </article>
    </div>
    <div v-else class="empty-shell mt-4">
      <div class="empty-shell-title">尚未选择模块</div>
      <div class="empty-shell-description">先应用模板或从模块库中逐个添加。</div>
    </div>
  </div>
</template>

<script setup lang="ts">
type ModuleView = {
  key: string
  label?: string
  description?: string
  category?: string
}

type PresetView = {
  id: string
  label: string
  description: string
}

defineProps<{
  title: string
  subtitle: string
  presets: PresetView[]
  selectedPresetId: string
  activePreset?: PresetView | null
  availableOptions: ModuleView[]
  draftKey: string
  modules: ModuleView[]
  presetPlaceholder?: string
  modulePlaceholder?: string
}>()

const emit = defineEmits<{
  'update:selectedPresetId': [value: string]
  'update:draftKey': [value: string]
  'apply-preset': []
  'add-module': []
  'reset-modules': []
  'move-module': [index: number, offset: number]
  'remove-module': [index: number]
}>()

function onPresetChange(event: Event) {
  emit('update:selectedPresetId', (event.target as HTMLSelectElement).value)
}

function onDraftChange(event: Event) {
  emit('update:draftKey', (event.target as HTMLSelectElement).value)
}
</script>

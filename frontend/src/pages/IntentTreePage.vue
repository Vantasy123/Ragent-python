<template>
  <section>
    <PageHeader
      title="意图树配置"
      eyebrow="Intent Routing"
      description="用树形结构组织意图节点，并通过下拉框绑定已有知识库，而不是手填资源 ID。"
    >
      <template #actions>
        <button class="btn btn-secondary" @click="load">刷新</button>
      </template>
    </PageHeader>

    <div class="grid-two">
      <SurfaceCard title="节点编辑器" subtitle="创建、更新、删除与启停意图节点。">
        <div class="form-grid form-grid-two">
          <input v-model="form.name" class="input" placeholder="节点名称" />
          <select v-model="form.parent_id" class="select">
            <option value="">根节点</option>
            <option v-for="item in parentOptions" :key="item.id" :value="item.id">{{ item.label }}</option>
          </select>
          <select v-model="form.kb_id" class="select">
            <option value="">未绑定知识库</option>
            <option v-for="item in knowledgeBaseOptions" :key="item.id" :value="item.id">{{ item.name }}</option>
          </select>
          <input v-model.number="form.priority" type="number" class="input" placeholder="优先级" />
        </div>
        <textarea v-model="form.description" class="textarea mt-4" placeholder="节点描述" />
        <label class="mt-4 inline-actions items-center">
          <input v-model="form.enabled" type="checkbox" />
          <span>启用节点</span>
        </label>
        <div class="mt-4 inline-actions">
          <button class="btn btn-primary" :disabled="!form.name.trim()" @click="submit">
            {{ form.id ? '保存节点' : '创建节点' }}
          </button>
          <button v-if="form.id" class="btn btn-secondary" @click="resetForm">取消编辑</button>
        </div>
      </SurfaceCard>

      <SurfaceCard title="意图树视图" subtitle="按层级展开节点，直接查看知识库绑定情况。">
        <AsyncState
          :loading="loading"
          :error="error"
          :empty="!rows.length"
          empty-title="暂无意图节点"
          empty-description="先创建根节点，再继续补充子节点和知识库绑定关系。"
        >
          <div class="list-stack">
            <article v-for="item in treeRows" :key="item.id" class="resource-item">
              <div class="flex items-start justify-between gap-4">
                <div>
                  <div class="resource-title" :style="{ paddingLeft: `${item.depth * 16}px` }">
                    {{ item.name }}
                  </div>
                  <div class="resource-meta">
                    <span>priority {{ item.priority }}</span>
                    <span>{{ item.parentId || 'root' }}</span>
                  </div>
                </div>
                <span :class="statusClass(item.enabled ? 'enabled' : 'disabled')" class="status-badge">
                  {{ item.enabled ? 'enabled' : 'disabled' }}
                </span>
              </div>
              <div class="resource-item-note">{{ item.description || '无描述' }}</div>
              <div class="mt-3">
                <KeyValueGrid
                  :columns="1"
                  :items="[
                    { label: '绑定知识库', value: item.kbName || item.kbId || '未绑定' },
                    { label: '树深度', value: item.depth },
                  ]"
                />
              </div>
              <div class="mt-3 inline-actions">
                <button class="btn btn-secondary" @click="edit(item)">编辑</button>
                <button class="btn btn-danger" @click="remove(item.id)">删除</button>
              </div>
            </article>
          </div>
        </AsyncState>
      </SurfaceCard>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import AsyncState from '@/components/admin/AsyncState.vue'
import KeyValueGrid from '@/components/admin/KeyValueGrid.vue'
import PageHeader from '@/components/admin/PageHeader.vue'
import SurfaceCard from '@/components/admin/SurfaceCard.vue'
import { adminService } from '@/services/adminService'
import { knowledgeService } from '@/services/knowledgeService'

const loading = ref(false)
const error = ref('')
const rows = ref<any[]>([])
const knowledgeBaseOptions = ref<{ id: string; name: string }[]>([])
const form = ref({
  id: '',
  parent_id: '',
  name: '',
  description: '',
  kb_id: '',
  enabled: true,
  priority: 0,
})

const knowledgeBaseMap = computed(
  () => new Map(knowledgeBaseOptions.value.map((item) => [item.id, item.name])),
)

const treeRows = computed(() => {
  const map = new Map<string, any[]>()
  for (const item of rows.value) {
    const key = item.parentId || 'root'
    const bucket = map.get(key) || []
    bucket.push(item)
    map.set(key, bucket)
  }
  const output: any[] = []
  const walk = (parentId: string | null, depth: number) => {
    const children = (map.get(parentId || 'root') || []).sort((a, b) => (a.priority ?? 0) - (b.priority ?? 0))
    for (const child of children) {
      output.push({
        ...child,
        depth,
        kbName: knowledgeBaseMap.value.get(child.kbId || '') || '',
      })
      walk(child.id, depth + 1)
    }
  }
  walk(null, 0)
  return output
})

const parentOptions = computed(() =>
  treeRows.value
    .filter((item) => item.id !== form.value.id)
    .map((item) => ({
      id: item.id,
      label: `${'　'.repeat(item.depth)}${item.name}`,
    })),
)

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [intentRows, kbPage] = await Promise.all([adminService.intents(), knowledgeService.listKnowledgeBases()])
    rows.value = intentRows
    knowledgeBaseOptions.value = kbPage.items.map((item: any) => ({
      id: item.id,
      name: item.name,
    }))
  } catch (err: any) {
    error.value = err?.detail || err?.message || '意图树加载失败'
  } finally {
    loading.value = false
  }
}

async function submit() {
  const payload = {
    parent_id: form.value.parent_id || null,
    name: form.value.name,
    description: form.value.description,
    kb_id: form.value.kb_id || null,
    enabled: form.value.enabled,
    priority: Number(form.value.priority || 0),
  }
  if (form.value.id) {
    await adminService.updateIntent(form.value.id, payload)
  } else {
    await adminService.createIntent(payload)
  }
  resetForm()
  await load()
}

function edit(item: any) {
  form.value = {
    id: item.id,
    parent_id: item.parentId || '',
    name: item.name,
    description: item.description || '',
    kb_id: item.kbId || '',
    enabled: !!item.enabled,
    priority: Number(item.priority || 0),
  }
}

function resetForm() {
  form.value = { id: '', parent_id: '', name: '', description: '', kb_id: '', enabled: true, priority: 0 }
}

async function remove(id: string) {
  await adminService.deleteIntent(id)
  if (form.value.id === id) resetForm()
  await load()
}

function statusClass(status: string) {
  return status === 'enabled' ? 'status-badge-success' : 'status-badge-danger'
}

onMounted(load)
</script>

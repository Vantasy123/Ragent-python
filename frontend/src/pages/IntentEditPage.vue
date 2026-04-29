<template>
  <section>
    <PageHeader
      :title="isCreate ? '新建意图' : '编辑意图'"
      eyebrow="意图编辑"
      description="承接原版独立编辑页职责，集中修改节点基础信息、父子关系和知识库绑定。"
    >
      <template #actions>
        <div class="inline-actions">
          <router-link class="btn btn-secondary" to="/admin/intent-list">返回意图列表</router-link>
          <button class="btn btn-primary" :disabled="!form.name.trim() || saving" @click="submit">
            {{ saving ? '保存中...' : '保存' }}
          </button>
        </div>
      </template>
    </PageHeader>

    <AsyncState :loading="loading" :error="error">
      <div class="grid-two">
        <SurfaceCard title="节点信息" subtitle="名称、层级与路由优先级。">
          <div class="form-grid">
            <input v-model="form.name" class="input" placeholder="节点名称" />
            <select v-model="form.parent_id" class="select">
              <option value="">根节点</option>
              <option v-for="item in parentOptions" :key="item.id" :value="item.id">{{ item.name }}</option>
            </select>
            <input v-model.number="form.priority" type="number" class="input" placeholder="优先级" />
            <textarea v-model="form.description" class="textarea" placeholder="节点描述" />
            <label class="inline-actions items-center">
              <input v-model="form.enabled" type="checkbox" />
              <span>启用节点</span>
            </label>
          </div>
        </SurfaceCard>

        <SurfaceCard title="知识库绑定" subtitle="通过下拉框选择已有知识库，不再手填 ID。">
          <div class="form-grid">
            <select v-model="form.kb_id" class="select">
              <option value="">未绑定知识库</option>
              <option v-for="item in knowledgeBases" :key="item.id" :value="item.id">{{ item.name }}</option>
            </select>
            <div class="helper-text text-sm">当前绑定：{{ currentKnowledgeBaseName }}</div>
          </div>
        </SurfaceCard>
      </div>
    </AsyncState>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AsyncState from '@/components/admin/AsyncState.vue'
import PageHeader from '@/components/admin/PageHeader.vue'
import SurfaceCard from '@/components/admin/SurfaceCard.vue'
import { adminService } from '@/services/adminService'
import { knowledgeService } from '@/services/knowledgeService'

const route = useRoute()
const router = useRouter()
const itemId = computed(() => String(route.params.id || ''))
const isCreate = computed(() => itemId.value === 'new')

const loading = ref(false)
const saving = ref(false)
const error = ref('')
const rows = ref<any[]>([])
const knowledgeBases = ref<any[]>([])
const form = ref({
  parent_id: '',
  name: '',
  description: '',
  kb_id: '',
  enabled: true,
  priority: 0,
})

const parentOptions = computed(() => rows.value.filter((item) => item.id !== itemId.value))
const currentKnowledgeBaseName = computed(() => {
  if (!form.value.kb_id) return '未绑定'
  return knowledgeBases.value.find((item: any) => item.id === form.value.kb_id)?.name || form.value.kb_id
})

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [intentRows, kbPage] = await Promise.all([adminService.intents(), knowledgeService.listKnowledgeBases()])
    rows.value = intentRows
    knowledgeBases.value = kbPage.items

    if (!isCreate.value) {
      const detail = await adminService.intentDetail(itemId.value)
      form.value = {
        parent_id: detail.parentId || '',
        name: detail.name || '',
        description: detail.description || '',
        kb_id: detail.kbId || '',
        enabled: Boolean(detail.enabled),
        priority: Number(detail.priority || 0),
      }
    }
  } catch (err: any) {
    error.value = err?.detail || err?.message || '意图详情加载失败'
  } finally {
    loading.value = false
  }
}

async function submit() {
  saving.value = true
  try {
    const payload = {
      parent_id: form.value.parent_id || null,
      name: form.value.name,
      description: form.value.description,
      kb_id: form.value.kb_id || null,
      enabled: form.value.enabled,
      priority: Number(form.value.priority || 0),
    }
    if (isCreate.value) {
      await adminService.createIntent(payload)
    } else {
      await adminService.updateIntent(itemId.value, payload)
    }
    router.push('/admin/intent-list')
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

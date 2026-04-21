<template>
  <section>
    <PageHeader
      title="术语映射"
      eyebrow="Query Mappings"
      description="维护用户词汇到检索标准词的映射，减少查询分歧和召回损失。"
    />

    <div class="grid-two">
      <SurfaceCard title="映射编辑器" subtitle="维护术语别名与目标术语的绑定关系。">
        <div class="form-grid">
          <input v-model="form.source_term" class="input" placeholder="原始术语" />
          <input v-model="form.target_term" class="input" placeholder="目标术语" />
          <label class="inline-actions items-center rounded-2xl border border-slate-200 px-4 py-3">
            <input v-model="form.enabled" type="checkbox" />
            <span>启用映射</span>
          </label>
          <div class="inline-actions">
            <button class="btn btn-primary" :disabled="!form.source_term.trim() || !form.target_term.trim()" @click="submit">
              {{ form.id ? '保存映射' : '新增映射' }}
            </button>
            <button v-if="form.id" class="btn btn-secondary" @click="resetForm">取消编辑</button>
          </div>
        </div>
      </SurfaceCard>

      <SurfaceCard title="映射列表" subtitle="集中检查术语清洗是否覆盖关键业务词。">
        <AsyncState
          :loading="loading"
          :error="error"
          :empty="!rows.length"
          empty-title="暂无映射"
          empty-description="新增映射后，查询重写和检索更容易命中标准术语。"
        >
          <div class="list-stack">
            <article v-for="item in rows" :key="item.id" class="resource-item">
              <div class="resource-item-row">
                <div class="mini-stack">
                  <div class="resource-title">{{ item.sourceTerm }}</div>
                  <div class="resource-item-note">映射到 {{ item.targetTerm }}</div>
                </div>
                <span :class="item.enabled ? 'status-badge-success' : 'status-badge-danger'" class="status-badge">
                  {{ item.enabled ? 'enabled' : 'disabled' }}
                </span>
              </div>
              <div class="mt-3">
                <KeyValueGrid
                  :columns="1"
                  :items="[
                    { label: '源术语', value: item.sourceTerm },
                    { label: '目标术语', value: item.targetTerm },
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
import { onMounted, ref } from 'vue'
import AsyncState from '@/components/admin/AsyncState.vue'
import KeyValueGrid from '@/components/admin/KeyValueGrid.vue'
import PageHeader from '@/components/admin/PageHeader.vue'
import SurfaceCard from '@/components/admin/SurfaceCard.vue'
import { adminService } from '@/services/adminService'

const loading = ref(false)
const error = ref('')
const rows = ref<any[]>([])
const form = ref({ id: '', source_term: '', target_term: '', enabled: true })

async function load() {
  loading.value = true
  error.value = ''
  try {
    rows.value = await adminService.mappings()
  } catch (err: any) {
    error.value = err?.detail || err?.message || '术语映射加载失败'
  } finally {
    loading.value = false
  }
}

async function submit() {
  const payload = {
    source_term: form.value.source_term,
    target_term: form.value.target_term,
    enabled: form.value.enabled,
  }
  if (form.value.id) {
    await adminService.updateMapping(form.value.id, payload)
  } else {
    await adminService.createMapping(payload)
  }
  resetForm()
  await load()
}

function edit(item: any) {
  form.value = {
    id: item.id,
    source_term: item.sourceTerm,
    target_term: item.targetTerm,
    enabled: !!item.enabled,
  }
}

function resetForm() {
  form.value = { id: '', source_term: '', target_term: '', enabled: true }
}

async function remove(id: string) {
  await adminService.deleteMapping(id)
  if (form.value.id === id) resetForm()
  await load()
}

onMounted(load)
</script>

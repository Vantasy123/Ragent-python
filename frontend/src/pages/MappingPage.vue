<template>
  <section>
    <PageHeader
      title="术语映射"
      eyebrow="查询映射"
      description="维护用户词汇到检索标准词的映射，减少查询分歧和召回损失。"
    >
      <template #actions>
        <div class="inline-actions">
          <button class="btn btn-secondary" @click="load">刷新</button>
          <button class="btn btn-primary" @click="resetForm">新建映射</button>
        </div>
      </template>
    </PageHeader>

    <div class="grid-two">
      <SurfaceCard title="映射列表" subtitle="集中检查术语清洗是否覆盖关键业务词。">
        <AsyncState
          :loading="loading"
          :error="error"
          :empty="!rows.length"
          empty-title="暂无映射"
          empty-description="新增映射后，查询重写和检索更容易命中标准术语。"
        >
          <div class="table-wrap">
            <table class="data-table">
              <thead>
                <tr>
                  <th>源术语</th>
                  <th>目标术语</th>
                  <th>状态</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="item in rows"
                  :key="item.id"
                  :class="{ 'row-active': selectedItem?.id === item.id }"
                  @click="selectItem(item.id)"
                >
                  <td>{{ item.sourceTerm }}</td>
                  <td>{{ item.targetTerm }}</td>
                  <td>
                    <span :class="item.enabled ? 'status-badge-success' : 'status-badge-danger'" class="status-badge">
                      {{ item.enabled ? '已启用' : '已停用' }}
                    </span>
                  </td>
                  <td>
                    <div class="inline-actions">
                      <button class="btn btn-secondary" @click.stop="edit(item)">编辑</button>
                      <button class="btn btn-danger" @click.stop="remove(item.id)">删除</button>
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </AsyncState>
      </SurfaceCard>

      <SurfaceCard title="映射详情与编辑" subtitle="维护源术语、目标术语和启停状态。">
        <AsyncState
          :loading="detailLoading"
          :error="detailError"
          :empty="!selectedItem && !form.id && !form.source_term.trim()"
          empty-title="未选择映射"
          empty-description="选择左侧映射查看详情，或直接创建新的术语映射。"
        >
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
              <button v-if="form.id || form.source_term.trim() || form.target_term.trim()" class="btn btn-secondary" @click="resetForm">重置</button>
            </div>
          </div>

          <div v-if="selectedItem" class="subtle-divider" />

          <div v-if="selectedItem" class="list-stack">
            <SurfaceCard compact title="当前详情">
              <KeyValueGrid
                :columns="1"
                :items="[
                  { label: '映射 ID', value: selectedItem.id },
                  { label: '源术语', value: selectedItem.sourceTerm },
                  { label: '目标术语', value: selectedItem.targetTerm },
                  { label: '状态', value: selectedItem.enabled ? '已启用' : '已停用' },
                ]"
              />
            </SurfaceCard>
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
const detailLoading = ref(false)
const detailError = ref('')
const rows = ref<any[]>([])
const selectedItem = ref<any | null>(null)
const form = ref({ id: '', source_term: '', target_term: '', enabled: true })

async function load() {
  loading.value = true
  error.value = ''
  try {
    rows.value = await adminService.mappings()
    if (selectedItem.value) {
      selectedItem.value = rows.value.find((item) => item.id === selectedItem.value?.id) || null
    }
  } catch (err: any) {
    error.value = err?.detail || err?.message || '术语映射加载失败'
  } finally {
    loading.value = false
  }
}

async function selectItem(id: string) {
  detailLoading.value = true
  detailError.value = ''
  try {
    selectedItem.value = await adminService.mappingDetail(id)
  } catch (err: any) {
    detailError.value = err?.detail || err?.message || '术语映射详情加载失败'
  } finally {
    detailLoading.value = false
  }
}

function edit(item: any) {
  selectedItem.value = item
  form.value = {
    id: item.id,
    source_term: item.sourceTerm,
    target_term: item.targetTerm,
    enabled: !!item.enabled,
  }
}

function resetForm(clearSelection = true) {
  if (clearSelection) {
    selectedItem.value = null
  }
  detailError.value = ''
  form.value = { id: '', source_term: '', target_term: '', enabled: true }
}

async function submit() {
  const payload = {
    source_term: form.value.source_term,
    target_term: form.value.target_term,
    enabled: form.value.enabled,
  }
  const keepId = form.value.id
  if (keepId) {
    await adminService.updateMapping(keepId, payload)
  } else {
    await adminService.createMapping(payload)
  }
  await load()
  if (keepId) {
    await selectItem(keepId)
  }
  resetForm(false)
}

async function remove(id: string) {
  await adminService.deleteMapping(id)
  if (selectedItem.value?.id === id || form.value.id === id) {
    resetForm()
  }
  await load()
}

onMounted(load)
</script>

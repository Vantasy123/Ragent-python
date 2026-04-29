<template>
  <section>
    <PageHeader
      title="示例问题"
      eyebrow="问题种子"
      description="维护聊天页可复用的问题模板和参考答案，用于空状态展示与运营推荐。"
    >
      <template #actions>
        <div class="inline-actions">
          <button class="btn btn-secondary" @click="load">刷新</button>
          <button class="btn btn-primary" @click="resetForm">新建问题</button>
        </div>
      </template>
    </PageHeader>

    <div class="grid-two">
      <SurfaceCard title="问题列表" subtitle="按排序和启停状态统一查看运营问题池。">
        <AsyncState
          :loading="loading"
          :error="error"
          :empty="!rows.length"
          empty-title="暂无示例问题"
          empty-description="创建后可用于首页推荐或聊天页空状态提示。"
        >
          <div class="table-wrap">
            <table class="data-table">
              <thead>
                <tr>
                  <th>问题</th>
                  <th>排序</th>
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
                  <td>
                    <div class="font-semibold">{{ item.question }}</div>
                    <div class="muted mt-1 text-xs">{{ truncate(item.answer || '无参考答案', 72) }}</div>
                  </td>
                  <td>{{ item.sortOrder ?? 0 }}</td>
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

      <SurfaceCard title="问题详情与编辑" subtitle="维护问题文案、参考答案、排序和启停。">
        <AsyncState
          :loading="detailLoading"
          :error="detailError"
          :empty="!selectedItem && !form.id && !form.question.trim()"
          empty-title="未选择问题"
          empty-description="选择左侧问题后可查看详情，或直接新建一条示例问题。"
        >
          <div class="form-grid">
            <input v-model="form.question" class="input" placeholder="问题" />
            <textarea v-model="form.answer" class="textarea" placeholder="参考答案" />
            <div class="grid-two">
              <input v-model.number="form.sort_order" type="number" class="input" placeholder="排序" />
              <label class="inline-actions items-center rounded-2xl border border-slate-200 px-4 py-3">
                <input v-model="form.enabled" type="checkbox" />
                <span>启用问题</span>
              </label>
            </div>
            <div class="inline-actions">
              <button class="btn btn-primary" :disabled="!form.question.trim()" @click="submit">
                {{ form.id ? '保存问题' : '新增问题' }}
              </button>
              <button v-if="form.id || form.question.trim() || form.answer.trim()" class="btn btn-secondary" @click="resetForm">重置</button>
            </div>
          </div>

          <div v-if="selectedItem" class="subtle-divider" />

          <div v-if="selectedItem" class="list-stack">
            <SurfaceCard compact title="当前详情">
              <KeyValueGrid
                :columns="1"
                :items="[
                  { label: '问题 ID', value: selectedItem.id },
                  { label: '排序', value: selectedItem.sortOrder ?? 0 },
                  { label: '状态', value: selectedItem.enabled ? '已启用' : '已停用' },
                ]"
              />
            </SurfaceCard>
            <SurfaceCard compact title="参考答案预览">
              <div class="helper-text whitespace-pre-wrap text-sm">{{ selectedItem.answer || '无参考答案' }}</div>
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
const form = ref({ id: '', question: '', answer: '', enabled: true, sort_order: 0 })

async function load() {
  loading.value = true
  error.value = ''
  try {
    rows.value = await adminService.samples()
    if (selectedItem.value) {
      selectedItem.value = rows.value.find((item) => item.id === selectedItem.value?.id) || null
    }
  } catch (err: any) {
    error.value = err?.detail || err?.message || '示例问题加载失败'
  } finally {
    loading.value = false
  }
}

async function selectItem(id: string) {
  detailLoading.value = true
  detailError.value = ''
  try {
    selectedItem.value = await adminService.sampleDetail(id)
  } catch (err: any) {
    detailError.value = err?.detail || err?.message || '示例问题详情加载失败'
  } finally {
    detailLoading.value = false
  }
}

function edit(item: any) {
  selectedItem.value = item
  form.value = {
    id: item.id,
    question: item.question,
    answer: item.answer || '',
    enabled: !!item.enabled,
    sort_order: Number(item.sortOrder || 0),
  }
}

function resetForm(clearSelection = true) {
  if (clearSelection) {
    selectedItem.value = null
  }
  detailError.value = ''
  form.value = { id: '', question: '', answer: '', enabled: true, sort_order: 0 }
}

async function submit() {
  const payload = {
    question: form.value.question,
    answer: form.value.answer,
    enabled: form.value.enabled,
    sort_order: Number(form.value.sort_order || 0),
  }
  const keepId = form.value.id
  if (keepId) {
    await adminService.updateSample(keepId, payload)
  } else {
    await adminService.createSample(payload)
  }
  await load()
  if (keepId) {
    await selectItem(keepId)
  }
  resetForm(false)
}

async function remove(id: string) {
  await adminService.deleteSample(id)
  if (selectedItem.value?.id === id || form.value.id === id) {
    resetForm()
  }
  await load()
}

function truncate(value: string, length: number) {
  return value.length > length ? `${value.slice(0, length)}...` : value
}

onMounted(load)
</script>

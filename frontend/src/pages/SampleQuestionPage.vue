<template>
  <section>
    <PageHeader
      title="示例问题"
      eyebrow="Prompt Seeds"
      description="维护聊天页可复用的问题模板和参考答案，用于空状态展示和运营推荐。"
    />

    <div class="grid-two">
      <SurfaceCard title="示例问题编辑器" subtitle="完整 CRUD，不再使用占位数据。">
        <div class="form-grid">
          <input v-model="form.question" class="input" placeholder="问题" />
          <textarea v-model="form.answer" class="textarea" placeholder="参考答案" />
          <div class="form-grid form-grid-two">
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
            <button v-if="form.id" class="btn btn-secondary" @click="resetForm">取消编辑</button>
          </div>
        </div>
      </SurfaceCard>

      <SurfaceCard title="问题列表" subtitle="按排序和启停状态检查内容质量。">
        <AsyncState
          :loading="loading"
          :error="error"
          :empty="!rows.length"
          empty-title="暂无示例问题"
          empty-description="创建后可用于首页推荐或聊天页空状态提示。"
        >
          <div class="list-stack">
            <article v-for="item in rows" :key="item.id" class="resource-item">
              <div class="resource-item-row">
                <div class="mini-stack">
                  <div class="resource-title">{{ item.question }}</div>
                  <div class="resource-item-note">{{ item.answer || '无参考答案' }}</div>
                </div>
                <span :class="item.enabled ? 'status-badge-success' : 'status-badge-danger'" class="status-badge">
                  {{ item.enabled ? 'enabled' : 'disabled' }}
                </span>
              </div>
              <div class="mt-3">
                <KeyValueGrid :columns="1" :items="[{ label: '排序', value: item.sortOrder ?? 0 }]" />
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
const form = ref({ id: '', question: '', answer: '', enabled: true, sort_order: 0 })

async function load() {
  loading.value = true
  error.value = ''
  try {
    rows.value = await adminService.samples()
  } catch (err: any) {
    error.value = err?.detail || err?.message || '示例问题加载失败'
  } finally {
    loading.value = false
  }
}

async function submit() {
  const payload = {
    question: form.value.question,
    answer: form.value.answer,
    enabled: form.value.enabled,
    sort_order: Number(form.value.sort_order || 0),
  }
  if (form.value.id) {
    await adminService.updateSample(form.value.id, payload)
  } else {
    await adminService.createSample(payload)
  }
  resetForm()
  await load()
}

function edit(item: any) {
  form.value = {
    id: item.id,
    question: item.question,
    answer: item.answer || '',
    enabled: !!item.enabled,
    sort_order: Number(item.sortOrder || 0),
  }
}

function resetForm() {
  form.value = { id: '', question: '', answer: '', enabled: true, sort_order: 0 }
}

async function remove(id: string) {
  await adminService.deleteSample(id)
  if (form.value.id === id) resetForm()
  await load()
}

onMounted(load)
</script>

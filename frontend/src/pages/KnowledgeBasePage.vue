<template>
  <section>
    <PageHeader
      title="知识库列表"
      eyebrow="Knowledge Console"
      description="对齐原版后台主工作流的第一层：先管理知识库，再进入文档列表和分块管理。"
    >
      <template #actions>
        <button class="btn btn-secondary" @click="load">刷新</button>
      </template>
    </PageHeader>

    <div class="grid-two">
      <SurfaceCard title="知识库表单" subtitle="创建或编辑知识库基础信息。">
        <div class="form-grid">
          <input v-model="form.name" class="input" placeholder="知识库名称" />
          <textarea v-model="form.description" class="textarea" placeholder="知识库描述" />
          <div class="inline-actions">
            <button class="btn btn-primary" :disabled="!form.name.trim()" @click="submit">
              {{ form.id ? '保存知识库' : '创建知识库' }}
            </button>
            <button v-if="form.id" class="btn btn-secondary" @click="resetForm">取消编辑</button>
          </div>
        </div>
      </SurfaceCard>

      <SurfaceCard title="分块策略" subtitle="展示可选分块策略，供文档页和分块管理页复用。">
        <AsyncState :loading="loadingStrategies" :error="strategyError" :empty="!chunkStrategies.length" empty-title="暂无策略">
          <div class="list-stack">
            <article v-for="strategy in chunkStrategies" :key="strategy.value" class="resource-item">
              <div class="resource-title">{{ strategy.label || strategy.value }}</div>
              <div class="resource-meta">
                <span>{{ strategy.value }}</span>
              </div>
            </article>
          </div>
        </AsyncState>
      </SurfaceCard>
    </div>

    <SurfaceCard class="mt-5" title="知识库清单" subtitle="从这里进入文档列表页。">
      <AsyncState
        :loading="loading"
        :error="error"
        :empty="!rows.length"
        empty-title="暂无知识库"
        empty-description="先创建一个知识库，再继续上传文档和管理 Chunk。"
      >
        <div class="table-wrap">
          <table class="data-table">
            <thead>
              <tr>
                <th>名称</th>
                <th>向量集合</th>
                <th>嵌入模型</th>
                <th>状态</th>
                <th>创建时间</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="kb in rows" :key="kb.id">
                <td>
                  <div class="font-semibold">{{ kb.name }}</div>
                  <div class="muted mt-1 text-xs">{{ kb.description || '无描述' }}</div>
                </td>
                <td>{{ kb.collectionName }}</td>
                <td>{{ kb.embeddingModel }}</td>
                <td>
                  <span :class="kb.enabled ? 'status-badge-success' : 'status-badge-danger'" class="status-badge">
                    {{ kb.enabled ? '已启用' : '已停用' }}
                  </span>
                </td>
                <td>{{ formatDate(kb.createdAt) }}</td>
                <td>
                  <div class="inline-actions">
                    <router-link class="btn btn-secondary" :to="`/admin/knowledge/${kb.id}`">文档管理</router-link>
                    <button class="btn btn-secondary" @click="edit(kb)">编辑</button>
                    <button class="btn btn-danger" @click="remove(kb.id)">删除</button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <PaginationBar :total="pagination.total" :page-size="pagination.pageSize" :current-page="pagination.pageNo" @update:page="changePage" />
      </AsyncState>
    </SurfaceCard>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import AsyncState from '@/components/admin/AsyncState.vue'
import PageHeader from '@/components/admin/PageHeader.vue'
import PaginationBar from '@/components/admin/PaginationBar.vue'
import SurfaceCard from '@/components/admin/SurfaceCard.vue'
import { knowledgeService } from '@/services/knowledgeService'
import { formatShanghaiDateTime } from '@/utils/date'

type KnowledgeBaseItem = {
  id: string
  name: string
  description?: string
  collectionName?: string
  embeddingModel?: string
  enabled?: boolean
  createdAt?: string
}

const loading = ref(false)
const error = ref('')
const rows = ref<KnowledgeBaseItem[]>([])
const pagination = ref({ total: 0, pageNo: 1, pageSize: 10 })
const loadingStrategies = ref(false)
const strategyError = ref('')
const chunkStrategies = ref<Array<{ value: string; label: string }>>([])
const form = ref({ id: '', name: '', description: '' })

async function load() {
  loading.value = true
  error.value = ''
  try {
    const page = await knowledgeService.listKnowledgeBases(pagination.value.pageNo, pagination.value.pageSize)
    rows.value = page.items as KnowledgeBaseItem[]
    pagination.value = { total: page.total, pageNo: page.pageNo, pageSize: page.pageSize }
  } catch (err: any) {
    error.value = err?.detail || err?.message || '知识库列表加载失败'
  } finally {
    loading.value = false
  }
}

async function loadStrategies() {
  loadingStrategies.value = true
  strategyError.value = ''
  try {
    chunkStrategies.value = await knowledgeService.chunkStrategies()
  } catch (err: any) {
    strategyError.value = err?.detail || err?.message || 'Chunk 策略加载失败'
  } finally {
    loadingStrategies.value = false
  }
}

async function submit() {
  const payload = { name: form.value.name, description: form.value.description }
  if (form.value.id) {
    await knowledgeService.updateKnowledgeBase(form.value.id, payload)
  } else {
    await knowledgeService.createKnowledgeBase(payload)
  }
  resetForm()
  await load()
}

function edit(item: KnowledgeBaseItem) {
  form.value = { id: item.id, name: item.name, description: item.description || '' }
}

function resetForm() {
  form.value = { id: '', name: '', description: '' }
}

async function remove(id: string) {
  await knowledgeService.deleteKnowledgeBase(id)
  if (form.value.id === id) resetForm()
  await load()
}

function changePage(pageNo: number) {
  pagination.value.pageNo = pageNo
  void load()
}

function formatDate(value?: string) {
  return formatShanghaiDateTime(value)
}

onMounted(async () => {
  // 首屏同时加载知识库和分块策略，保证二级、三级页面进入前有稳定基础数据。
  await Promise.all([load(), loadStrategies()])
})
</script>

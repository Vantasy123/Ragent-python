<template>
  <section>
    <PageHeader
      title="意图列表"
      eyebrow="意图管理"
      description="对齐原版后台结构，将树总览和编辑页拆开，列表页只负责筛选、查看和跳转。"
    >
      <template #actions>
        <div class="inline-actions">
          <router-link class="btn btn-primary" to="/admin/intent-list/new/edit">新建意图</router-link>
          <button class="btn btn-secondary" @click="load">刷新</button>
        </div>
      </template>
    </PageHeader>

    <SurfaceCard title="节点列表" subtitle="统一查看节点、绑定知识库、状态与优先级。">
      <AsyncState
        :loading="loading"
        :error="error"
        :empty="!rows.length"
        empty-title="暂无意图节点"
        empty-description="先创建一个根节点，再逐步扩展树形结构。"
      >
        <div class="table-wrap">
          <table class="data-table">
            <thead>
              <tr>
                <th>名称</th>
                <th>父节点</th>
                <th>知识库</th>
                <th>优先级</th>
                <th>状态</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in rows" :key="item.id">
                <td>
                  <div class="font-semibold">{{ item.name }}</div>
                  <div class="muted mt-1 text-xs">{{ item.description || '无描述' }}</div>
                </td>
                <td>{{ parentName(item.parentId) }}</td>
                <td>{{ kbName(item.kbId) }}</td>
                <td>{{ item.priority ?? 0 }}</td>
                <td>
                  <span :class="item.enabled ? 'status-badge-success' : 'status-badge-danger'" class="status-badge">
                    {{ item.enabled ? '已启用' : '已停用' }}
                  </span>
                </td>
                <td>
                  <div class="inline-actions">
                    <router-link class="btn btn-secondary" :to="`/admin/intent-list/${item.id}/edit`">编辑</router-link>
                    <button class="btn btn-danger" @click="remove(item.id)">删除</button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </AsyncState>
    </SurfaceCard>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import AsyncState from '@/components/admin/AsyncState.vue'
import PageHeader from '@/components/admin/PageHeader.vue'
import SurfaceCard from '@/components/admin/SurfaceCard.vue'
import { adminService } from '@/services/adminService'
import { knowledgeService } from '@/services/knowledgeService'

const loading = ref(false)
const error = ref('')
const rows = ref<any[]>([])
const knowledgeBases = ref<any[]>([])

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [intentRows, kbPage] = await Promise.all([adminService.intents(), knowledgeService.listKnowledgeBases()])
    rows.value = intentRows
    knowledgeBases.value = kbPage.items
  } catch (err: any) {
    error.value = err?.detail || err?.message || '意图列表加载失败'
  } finally {
    loading.value = false
  }
}

function parentName(parentId?: string) {
  if (!parentId) return '根节点'
  return rows.value.find((item) => item.id === parentId)?.name || parentId
}

function kbName(kbId?: string) {
  if (!kbId) return '未绑定'
  return knowledgeBases.value.find((item: any) => item.id === kbId)?.name || kbId
}

async function remove(id: string) {
  await adminService.deleteIntent(id)
  await load()
}

onMounted(load)
</script>

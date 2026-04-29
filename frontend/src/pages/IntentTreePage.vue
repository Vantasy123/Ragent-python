<template>
  <section>
    <PageHeader
      title="意图树总览"
      eyebrow="意图路由"
      description="保留树视图负责总览与启停，具体编辑统一进入意图列表和编辑页。"
    >
      <template #actions>
        <div class="inline-actions">
          <router-link class="btn btn-secondary" to="/admin/intent-list">进入意图列表</router-link>
          <button class="btn btn-secondary" @click="load">刷新</button>
        </div>
      </template>
    </PageHeader>

    <SurfaceCard title="意图树" subtitle="按层级查看节点与知识库绑定关系。">
      <AsyncState
        :loading="loading"
        :error="error"
        :empty="!treeRows.length"
        empty-title="暂无意图节点"
        empty-description="先创建根节点，再进入意图列表继续补齐节点信息。"
      >
        <div class="list-stack">
          <article v-for="item in treeRows" :key="item.id" class="resource-item">
            <div class="resource-item-row">
              <div class="mini-stack">
                <div class="resource-title" :style="{ paddingLeft: `${item.depth * 16}px` }">{{ item.name }}</div>
                <div class="resource-meta">
                  <span>优先级 {{ item.priority ?? 0 }}</span>
                  <span>{{ item.parentId || '根节点' }}</span>
                </div>
              </div>
              <span :class="item.enabled ? 'status-badge-success' : 'status-badge-danger'" class="status-badge">
                {{ item.enabled ? '已启用' : '已停用' }}
              </span>
            </div>
            <div class="resource-item-note">{{ item.description || '无描述' }}</div>
            <div class="resource-meta mt-2">
              <span>知识库：{{ kbName(item.kbId) }}</span>
            </div>
            <div class="mt-3 inline-actions">
              <router-link class="btn btn-secondary" :to="`/admin/intent-list/${item.id}/edit`">编辑</router-link>
            </div>
          </article>
        </div>
      </AsyncState>
    </SurfaceCard>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import AsyncState from '@/components/admin/AsyncState.vue'
import PageHeader from '@/components/admin/PageHeader.vue'
import SurfaceCard from '@/components/admin/SurfaceCard.vue'
import { adminService } from '@/services/adminService'
import { knowledgeService } from '@/services/knowledgeService'

const loading = ref(false)
const error = ref('')
const rows = ref<any[]>([])
const knowledgeBases = ref<any[]>([])

const treeRows = computed(() => {
  const grouped = new Map<string, any[]>()
  for (const item of rows.value) {
    const key = item.parentId || 'root'
    const bucket = grouped.get(key) || []
    bucket.push(item)
    grouped.set(key, bucket)
  }

  const output: any[] = []

  // 递归展开树结构，给页面补充 depth 方便做层级缩进。
  const walk = (parentId: string | null, depth: number) => {
    const children = (grouped.get(parentId || 'root') || []).sort((a, b) => Number(a.priority || 0) - Number(b.priority || 0))
    for (const child of children) {
      output.push({ ...child, depth })
      walk(child.id, depth + 1)
    }
  }

  walk(null, 0)
  return output
})

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [intentRows, kbPage] = await Promise.all([adminService.intents(), knowledgeService.listKnowledgeBases()])
    rows.value = intentRows
    knowledgeBases.value = kbPage.items
  } catch (err: any) {
    error.value = err?.detail || err?.message || '意图树加载失败'
  } finally {
    loading.value = false
  }
}

function kbName(kbId?: string) {
  if (!kbId) return '未绑定'
  return knowledgeBases.value.find((item: any) => item.id === kbId)?.name || kbId
}

onMounted(load)
</script>

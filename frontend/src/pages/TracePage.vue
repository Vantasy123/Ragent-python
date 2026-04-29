<template>
  <section>
    <PageHeader
      title="链路追踪"
      eyebrow="追踪运行"
      description="对齐原版结构，列表页负责展示运行记录，并进入独立详情页查看节点和评估摘要。"
    >
      <template #actions>
        <button class="btn btn-secondary" @click="load">刷新</button>
      </template>
    </PageHeader>

    <SurfaceCard title="追踪列表" subtitle="点击详情进入独立链路详情页。">
      <AsyncState
        :loading="loading"
        :error="error"
        :empty="!runs.length"
        empty-title="暂无追踪记录"
        empty-description="执行聊天、运维 Agent 或摄取任务后，这里会出现新的 Trace。"
      >
        <div class="table-wrap">
          <table class="data-table">
            <thead>
              <tr>
                <th>Trace ID</th>
                <th>状态</th>
                <th>耗时</th>
                <th>会话</th>
                <th>创建时间</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in runs" :key="item.traceId">
                <td>{{ item.traceId }}</td>
                <td>
                  <span :class="statusClass(item.status)" class="status-badge">{{ formatStatus(item.status) }}</span>
                </td>
                <td>{{ item.totalDurationMs ?? 0 }} ms</td>
                <td>{{ item.sessionId || '-' }}</td>
                <td>{{ formatDate(item.createdAt) }}</td>
                <td>
                  <router-link class="btn btn-secondary" :to="`/admin/traces/${item.traceId}`">详情</router-link>
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
import { adminService } from '@/services/adminService'
import { formatShanghaiDateTime } from '@/utils/date'

const loading = ref(false)
const error = ref('')
const runs = ref<any[]>([])
const pagination = ref({ total: 0, pageNo: 1, pageSize: 12 })

async function load() {
  loading.value = true
  error.value = ''
  try {
    const page = await adminService.traces(pagination.value.pageNo, pagination.value.pageSize)
    runs.value = page.items
    pagination.value = { total: page.total, pageNo: page.pageNo, pageSize: page.pageSize }
  } catch (err: any) {
    error.value = err?.detail || err?.message || '追踪列表加载失败'
  } finally {
    loading.value = false
  }
}

function changePage(pageNo: number) {
  pagination.value.pageNo = pageNo
  void load()
}

function statusClass(status: string) {
  const normalized = String(status || '').toLowerCase()
  if (['success', 'completed'].includes(normalized)) return 'status-badge-success'
  if (['failed', 'error'].includes(normalized)) return 'status-badge-danger'
  if (['running', 'processing', 'pending'].includes(normalized)) return 'status-badge-warning'
  return 'status-badge-neutral'
}

function formatStatus(status?: string) {
  const map: Record<string, string> = {
    success: '成功',
    completed: '已完成',
    failed: '失败',
    error: '错误',
    running: '运行中',
    processing: '处理中',
    pending: '待处理',
  }
  return map[String(status || '').toLowerCase()] || status || '-'
}

function formatDate(value?: string) {
  return formatShanghaiDateTime(value)
}

onMounted(load)
</script>

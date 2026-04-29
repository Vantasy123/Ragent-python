<template>
  <section>
    <PageHeader
      :title="docDetail.docName ? `${docDetail.docName} / 分块管理` : '分块管理'"
      eyebrow="Knowledge Chunks"
      description="第三层工作流：对文档分块做增删改、启停、批量操作和重建。"
    >
      <template #actions>
        <div class="inline-actions">
          <router-link class="btn btn-secondary" :to="`/admin/knowledge/${kbId}`">返回文档列表</router-link>
          <button class="btn btn-secondary" @click="load">刷新</button>
        </div>
      </template>
    </PageHeader>

    <div class="grid-two">
      <SurfaceCard title="文档摘要" subtitle="显示文档基础信息与重建入口。">
        <AsyncState :loading="loadingDetail" :error="detailError" :empty="!docDetail.id" empty-title="文档未找到">
          <div class="list-stack">
            <div class="resource-title">{{ docDetail.docName }}</div>
            <div class="resource-meta">
              <span>{{ docDetail.fileType || '-' }}</span>
              <span>{{ docDetail.chunkCount ?? 0 }} 个 Chunk</span>
              <span>{{ docDetail.enabled ? '已启用' : '已停用' }}</span>
            </div>
            <div class="helper-text">{{ docDetail.errorMessage || '无错误信息' }}</div>
            <div class="inline-actions">
              <button class="btn btn-primary" @click="rebuild">重建 Chunk</button>
              <button class="btn btn-secondary" @click="loadLogs">刷新日志</button>
            </div>
          </div>
        </AsyncState>
      </SurfaceCard>

      <SurfaceCard title="Chunk 表单" subtitle="创建新 Chunk 或编辑当前选中内容。">
        <div class="form-grid">
          <textarea v-model="chunkForm.content" class="textarea" placeholder="Chunk 内容" />
          <div class="grid-two">
            <select v-model="chunkForm.source" class="select">
              <option value="manual">手工录入</option>
              <option value="upload">上传文件</option>
              <option value="parser">解析器</option>
              <option value="chunker">分块器</option>
            </select>
            <input v-model="chunkForm.note" class="input" placeholder="备注" />
          </div>
          <label class="inline-actions items-center">
            <input v-model="chunkForm.enabled" type="checkbox" />
            <span>启用此 Chunk</span>
          </label>
          <div class="inline-actions">
            <button class="btn btn-primary" :disabled="!chunkForm.content.trim()" @click="saveChunk">
              {{ chunkForm.id ? '保存 Chunk' : '新增 Chunk' }}
            </button>
            <button class="btn btn-secondary" @click="resetForm">重置</button>
          </div>
        </div>
      </SurfaceCard>
    </div>

    <div class="grid-two mt-5">
      <SurfaceCard title="Chunk 列表" subtitle="支持批量启停、单个编辑和删除。">
        <template #actions>
          <div class="inline-actions">
            <button class="btn btn-secondary" :disabled="!selectedChunkIds.length" @click="batchToggle(true)">批量启用</button>
            <button class="btn btn-secondary" :disabled="!selectedChunkIds.length" @click="batchToggle(false)">批量停用</button>
          </div>
        </template>
        <AsyncState :loading="loadingChunks" :error="chunkError" :empty="!chunks.length" empty-title="暂无 Chunk">
          <div class="table-wrap">
            <table class="data-table">
              <thead>
                <tr>
                  <th></th>
                  <th>#</th>
                  <th>内容</th>
                  <th>状态</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="chunk in chunks" :key="chunk.id">
                  <td><input v-model="selectedChunkIds" type="checkbox" :value="chunk.id" /></td>
                  <td>{{ chunk.chunkIndex }}</td>
                  <td>{{ truncate(chunk.content, 96) }}</td>
                  <td>
                    <span :class="chunk.enabled ? 'status-badge-success' : 'status-badge-danger'" class="status-badge">
                      {{ chunk.enabled ? '已启用' : '已停用' }}
                    </span>
                  </td>
                  <td>
                    <div class="inline-actions">
                      <button class="btn btn-secondary" @click="toggleChunk(chunk)">{{ chunk.enabled ? '停用' : '启用' }}</button>
                      <button class="btn btn-secondary" @click="editChunk(chunk)">编辑</button>
                      <button class="btn btn-danger" @click="removeChunk(chunk.id)">删除</button>
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <PaginationBar :total="pagination.total" :page-size="pagination.pageSize" :current-page="pagination.pageNo" @update:page="changePage" />
        </AsyncState>
      </SurfaceCard>

      <SurfaceCard title="分块日志" subtitle="最近一次分块与重建执行结果。">
        <AsyncState :loading="loadingLogs" :error="logError" :empty="!chunkLogs.length" empty-title="暂无日志">
          <div class="list-stack">
            <article v-for="log in chunkLogs" :key="log.id" class="resource-item">
              <div class="resource-item-row">
                <span :class="statusClass(log.status)" class="status-badge">{{ formatStatus(log.status) }}</span>
                <span class="text-xs text-slate-500">{{ formatDate(log.createdAt) }}</span>
              </div>
              <div class="resource-item-note">{{ log.message || '无日志说明' }}</div>
              <div class="resource-meta">
                <span>生成分块 {{ log.chunkCount ?? 0 }}</span>
              </div>
            </article>
          </div>
        </AsyncState>
      </SurfaceCard>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import AsyncState from '@/components/admin/AsyncState.vue'
import PageHeader from '@/components/admin/PageHeader.vue'
import PaginationBar from '@/components/admin/PaginationBar.vue'
import SurfaceCard from '@/components/admin/SurfaceCard.vue'
import { knowledgeService } from '@/services/knowledgeService'
import { formatShanghaiDateTime } from '@/utils/date'

const route = useRoute()
const kbId = computed(() => String(route.params.kbId || ''))
const docId = computed(() => String(route.params.docId || ''))

const loadingDetail = ref(false)
const detailError = ref('')
const loadingChunks = ref(false)
const chunkError = ref('')
const loadingLogs = ref(false)
const logError = ref('')
const docDetail = ref<Record<string, any>>({})
const chunks = ref<any[]>([])
const pagination = ref({ total: 0, pageNo: 1, pageSize: 10 })
const chunkLogs = ref<any[]>([])
const selectedChunkIds = ref<string[]>([])
const chunkForm = ref({
  id: '',
  content: '',
  enabled: true,
  source: 'manual',
  note: '',
})

async function load() {
  await Promise.all([loadDetail(), loadChunks(), loadLogs()])
}

async function loadDetail() {
  loadingDetail.value = true
  detailError.value = ''
  try {
    docDetail.value = await knowledgeService.getDocument(docId.value)
  } catch (err: any) {
    detailError.value = err?.detail || err?.message || '文档详情加载失败'
  } finally {
    loadingDetail.value = false
  }
}

async function loadChunks() {
  loadingChunks.value = true
  chunkError.value = ''
  try {
    const page = await knowledgeService.listChunks(docId.value, pagination.value.pageNo, pagination.value.pageSize)
    chunks.value = page.items
    pagination.value = { total: page.total, pageNo: page.pageNo, pageSize: page.pageSize }
  } catch (err: any) {
    chunkError.value = err?.detail || err?.message || 'Chunk 列表加载失败'
  } finally {
    loadingChunks.value = false
  }
}

async function loadLogs() {
  loadingLogs.value = true
  logError.value = ''
  try {
    chunkLogs.value = await knowledgeService.chunkLogs(docId.value)
  } catch (err: any) {
    logError.value = err?.detail || err?.message || 'Chunk 日志加载失败'
  } finally {
    loadingLogs.value = false
  }
}

function editChunk(chunk: any) {
  chunkForm.value = {
    id: chunk.id,
    content: chunk.content,
    enabled: !!chunk.enabled,
    source: String(chunk.metadata?.source || 'manual'),
    note: String(chunk.metadata?.note || ''),
  }
}

function resetForm() {
  chunkForm.value = { id: '', content: '', enabled: true, source: 'manual', note: '' }
}

function changePage(pageNo: number) {
  pagination.value.pageNo = pageNo
  void loadChunks()
}

async function saveChunk() {
  const payload = {
    content: chunkForm.value.content,
    enabled: chunkForm.value.enabled,
    metadata: {
      source: chunkForm.value.source,
      ...(chunkForm.value.note.trim() ? { note: chunkForm.value.note.trim() } : {}),
    },
  }
  if (chunkForm.value.id) {
    await knowledgeService.updateChunk(docId.value, chunkForm.value.id, payload)
  } else {
    await knowledgeService.createChunk(docId.value, payload)
  }
  resetForm()
  await Promise.all([loadChunks(), loadDetail()])
}

async function toggleChunk(chunk: any) {
  if (chunk.enabled) {
    await knowledgeService.disableChunk(docId.value, chunk.id)
  } else {
    await knowledgeService.enableChunk(docId.value, chunk.id)
  }
  await loadChunks()
}

async function batchToggle(enabled: boolean) {
  await knowledgeService.batchEnableChunks(docId.value, selectedChunkIds.value, enabled)
  selectedChunkIds.value = []
  await loadChunks()
}

async function removeChunk(chunkId: string) {
  await knowledgeService.deleteChunk(docId.value, chunkId)
  await Promise.all([loadChunks(), loadDetail()])
}

async function rebuild() {
  await knowledgeService.rebuildChunks(docId.value)
  await Promise.all([loadChunks(), loadLogs(), loadDetail()])
}

function statusClass(status: string) {
  const normalized = String(status || '').toLowerCase()
  if (['success', 'completed', 'enabled'].includes(normalized)) return 'status-badge-success'
  if (['failed', 'error', 'disabled'].includes(normalized)) return 'status-badge-danger'
  if (['processing', 'running', 'pending'].includes(normalized)) return 'status-badge-warning'
  return 'status-badge-neutral'
}

function formatStatus(status?: string) {
  const map: Record<string, string> = {
    success: '成功',
    completed: '已完成',
    failed: '失败',
    error: '错误',
    disabled: '已停用',
    enabled: '已启用',
    processing: '处理中',
    running: '运行中',
    pending: '待处理',
  }
  return map[String(status || '').toLowerCase()] || status || '-'
}

function truncate(value: string, length: number) {
  return value.length > length ? `${value.slice(0, length)}...` : value
}

function formatDate(value?: string) {
  return formatShanghaiDateTime(value)
}

watch([kbId, docId], () => {
  pagination.value.pageNo = 1
  resetForm()
  selectedChunkIds.value = []
  void load()
})

onMounted(load)
</script>

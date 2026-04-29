<template>
  <section>
    <PageHeader
      :title="kbDetail.name ? `${kbDetail.name} / 文档列表` : '文档列表'"
      eyebrow="知识库文档"
      description="第二层工作流：文档上传、搜索、状态筛选、启停和分块任务入口。"
    >
      <template #actions>
        <div class="inline-actions">
          <router-link class="btn btn-secondary" to="/admin/knowledge">返回知识库</router-link>
          <button class="btn btn-secondary" @click="load">刷新</button>
        </div>
      </template>
    </PageHeader>

    <SurfaceCard title="知识库信息" subtitle="当前知识库摘要与文档筛选条件。">
      <div class="grid-two">
        <div class="list-stack">
          <div class="meta-label !text-slate-500">描述</div>
          <div>{{ kbDetail.description || '无描述' }}</div>
          <div class="resource-meta">
            <span>{{ kbDetail.collectionName || '-' }}</span>
            <span>{{ kbDetail.embeddingModel || '-' }}</span>
          </div>
        </div>
        <div class="form-grid">
          <input v-model="keyword" class="input" placeholder="搜索文档名称" />
          <select v-model="statusFilter" class="select">
            <option value="">全部状态</option>
            <option value="completed">已完成</option>
            <option value="processing">处理中</option>
            <option value="failed">失败</option>
            <option value="pending">待处理</option>
          </select>
          <input type="file" class="input" @change="pickFile" />
          <div class="inline-actions">
            <button class="btn btn-primary" :disabled="!pendingFile || uploading" @click="upload">
              {{ uploading ? '上传中...' : '上传文档' }}
            </button>
            <button class="btn btn-secondary" @click="applyFilters">应用筛选</button>
          </div>
          <div v-if="uploadMessage" class="helper-text text-sm">{{ uploadMessage }}</div>
        </div>
      </div>
    </SurfaceCard>

    <div class="grid-two mt-5">
      <SurfaceCard title="文档列表" subtitle="进入分块管理和查看分块日志。">
        <AsyncState
          :loading="loading"
          :error="error"
          :empty="!docs.length"
          empty-title="暂无文档"
          empty-description="上传文档后，这里会展示处理状态和后续操作入口。"
        >
          <div class="table-wrap">
            <table class="data-table">
              <thead>
                <tr>
                  <th>文档</th>
                  <th>状态</th>
                  <th>分块数</th>
                  <th>类型</th>
                  <th>大小</th>
                  <th>时间</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="doc in docs"
                  :key="doc.id"
                  :class="{ 'row-active': selectedDoc?.id === doc.id }"
                  @click="loadDetail(doc.id)"
                >
                  <td>
                    <div class="font-semibold">{{ doc.docName }}</div>
                    <div class="muted mt-1 text-xs">{{ doc.id }}</div>
                  </td>
                  <td>
                    <span :class="statusClass(doc.status)" class="status-badge">{{ formatStatus(doc.status) }}</span>
                  </td>
                  <td>{{ doc.chunkCount ?? 0 }}</td>
                  <td>{{ doc.fileType || '-' }}</td>
                  <td>{{ formatBytes(doc.fileSize) }}</td>
                  <td>{{ formatDate(doc.createdAt) }}</td>
                  <td>
                    <div class="inline-actions">
                      <router-link class="btn btn-secondary" :to="`/admin/knowledge/${kbId}/docs/${doc.id}`" @click.stop>分块管理</router-link>
                      <button class="btn btn-secondary" @click.stop="runChunk(doc.id)">分块</button>
                      <button class="btn btn-secondary" @click.stop="toggleDoc(doc)">{{ doc.enabled ? '停用' : '启用' }}</button>
                      <button class="btn btn-danger" @click.stop="removeDoc(doc.id)">删除</button>
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <PaginationBar :total="pagination.total" :page-size="pagination.pageSize" :current-page="pagination.pageNo" @update:page="changePage" />
        </AsyncState>
      </SurfaceCard>

      <SurfaceCard title="文档详情与分块日志" subtitle="查看当前文档的配置和最近一次处理结果。">
        <AsyncState
          :loading="detailLoading"
          :error="detailError"
          :empty="!selectedDoc"
          empty-title="未选择文档"
          empty-description="点击左侧文档行即可查看详情和最近分块日志。"
        >
          <div v-if="selectedDoc" class="list-stack">
            <div class="resource-title">{{ selectedDoc.docName }}</div>
            <div class="resource-meta">
              <span>{{ strategyLabel(selectedDoc.chunkStrategy) }}</span>
              <span>{{ selectedDoc.enabled ? '已启用' : '已停用' }}</span>
            </div>

            <div class="form-grid">
              <input v-model="docForm.doc_name" class="input" placeholder="文档名称" />
              <select v-model="docForm.chunk_strategy" class="select">
                <option v-for="item in strategies" :key="item.value" :value="item.value">{{ item.label }}</option>
              </select>
              <div class="grid-two">
                <input v-model.number="docForm.chunk_size" type="number" min="100" class="input" placeholder="分块大小" />
                <input v-model.number="docForm.chunk_overlap" type="number" min="0" class="input" placeholder="分块重叠" />
              </div>
              <div class="inline-actions">
                <button class="btn btn-primary" @click="saveDocument">保存文档配置</button>
                <button class="btn btn-secondary" @click="loadDetail(selectedDoc.id)">刷新详情</button>
              </div>
            </div>

            <div class="subtle-divider" />

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
          </div>
        </AsyncState>
      </SurfaceCard>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import AsyncState from '@/components/admin/AsyncState.vue'
import PageHeader from '@/components/admin/PageHeader.vue'
import PaginationBar from '@/components/admin/PaginationBar.vue'
import SurfaceCard from '@/components/admin/SurfaceCard.vue'
import { knowledgeService } from '@/services/knowledgeService'
import { formatShanghaiDateTime } from '@/utils/date'

const route = useRoute()
const kbId = computed(() => String(route.params.kbId || ''))

const loading = ref(false)
const error = ref('')
const detailLoading = ref(false)
const detailError = ref('')
const kbDetail = ref<Record<string, any>>({})
const docs = ref<any[]>([])
const pagination = ref({ total: 0, pageNo: 1, pageSize: 10 })
const selectedDoc = ref<any | null>(null)
const chunkLogs = ref<any[]>([])
const strategies = ref<Array<{ value: string; label: string }>>([])
const pendingFile = ref<File | null>(null)
const uploading = ref(false)
const uploadMessage = ref('')
const keyword = ref('')
const statusFilter = ref('')
const docForm = ref({
  doc_name: '',
  chunk_strategy: 'recursive',
  chunk_size: 500,
  chunk_overlap: 50,
})

async function load() {
  await Promise.all([loadKbDetail(), loadStrategies(), loadDocuments()])
}

async function loadKbDetail() {
  kbDetail.value = await knowledgeService.getKnowledgeBase(kbId.value)
}

async function loadStrategies() {
  strategies.value = await knowledgeService.chunkStrategies()
}

async function loadDocuments() {
  loading.value = true
  error.value = ''
  try {
    const page = await knowledgeService.listDocuments(
      kbId.value,
      keyword.value,
      statusFilter.value,
      pagination.value.pageNo,
      pagination.value.pageSize,
    )
    docs.value = page.items
    pagination.value = { total: page.total, pageNo: page.pageNo, pageSize: page.pageSize }

    if (docs.value.length && !selectedDoc.value) {
      await loadDetail(docs.value[0].id)
    } else if (selectedDoc.value) {
      const nextSelected = docs.value.find((item) => item.id === selectedDoc.value?.id)
      if (nextSelected) {
        await loadDetail(nextSelected.id)
      } else {
        selectedDoc.value = null
        chunkLogs.value = []
      }
    }
  } catch (err: any) {
    error.value = err?.detail || err?.message || '文档列表加载失败'
  } finally {
    loading.value = false
  }
}

async function loadDetail(docId: string) {
  detailLoading.value = true
  detailError.value = ''
  try {
    const [doc, logs] = await Promise.all([knowledgeService.getDocument(docId), knowledgeService.chunkLogs(docId)])
    selectedDoc.value = doc
    chunkLogs.value = logs
    docForm.value = {
      doc_name: doc.docName || '',
      chunk_strategy: doc.chunkStrategy || 'recursive',
      chunk_size: Number(doc.chunkConfig?.chunk_size ?? 500),
      chunk_overlap: Number(doc.chunkConfig?.chunk_overlap ?? 50),
    }
  } catch (err: any) {
    detailError.value = err?.detail || err?.message || '文档详情加载失败'
  } finally {
    detailLoading.value = false
  }
}

function pickFile(event: Event) {
  const input = event.target as HTMLInputElement
  pendingFile.value = input.files?.[0] ?? null
}

async function upload() {
  if (!pendingFile.value) return
  uploading.value = true
  uploadMessage.value = ''
  try {
    const response = await knowledgeService.uploadDocument(kbId.value, pendingFile.value)
    uploadMessage.value = `上传成功：${response.data?.docName || pendingFile.value.name}`
    pendingFile.value = null
    pagination.value.pageNo = 1
    await loadDocuments()
  } catch (err: any) {
    uploadMessage.value = err?.detail || err?.message || '上传失败'
  } finally {
    uploading.value = false
  }
}

function applyFilters() {
  pagination.value.pageNo = 1
  void loadDocuments()
}

function changePage(pageNo: number) {
  pagination.value.pageNo = pageNo
  void loadDocuments()
}

async function runChunk(docId: string) {
  await knowledgeService.startChunk(docId)
  await loadDocuments()
  if (selectedDoc.value?.id === docId) {
    await loadDetail(docId)
  }
}

async function toggleDoc(doc: any) {
  await knowledgeService.setDocumentEnabled(doc.id, !doc.enabled)
  await loadDocuments()
}

async function removeDoc(docId: string) {
  await knowledgeService.deleteDocument(docId)
  if (selectedDoc.value?.id === docId) {
    selectedDoc.value = null
    chunkLogs.value = []
  }
  await loadDocuments()
}

async function saveDocument() {
  if (!selectedDoc.value) return
  await knowledgeService.updateDocument(selectedDoc.value.id, {
    doc_name: docForm.value.doc_name,
    chunk_strategy: docForm.value.chunk_strategy,
    chunk_config: {
      chunk_size: Number(docForm.value.chunk_size || 500),
      chunk_overlap: Number(docForm.value.chunk_overlap || 0),
    },
  })
  await Promise.all([loadDocuments(), loadDetail(selectedDoc.value.id)])
}

function strategyLabel(value?: string) {
  const match = strategies.value.find((item) => item.value === value)
  return match?.label || value || '-'
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

function formatBytes(size?: number) {
  if (!size) return '-'
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / 1024 / 1024).toFixed(2)} MB`
}

watch(
  kbId,
  () => {
    pagination.value.pageNo = 1
    selectedDoc.value = null
    chunkLogs.value = []
    void load()
  },
  { immediate: true },
)
</script>

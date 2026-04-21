<template>
  <section>
    <PageHeader
      title="知识库管理"
      eyebrow="Knowledge Console"
      description="主页面保留知识库和文档列表，文档详情、Chunk 与日志统一放到右侧抽屉。"
    >
      <template #actions>
        <button class="btn btn-secondary" @click="refreshAll">刷新</button>
      </template>
    </PageHeader>

    <div class="split-layout">
      <SurfaceCard title="知识库列表" subtitle="创建、编辑和切换当前知识库。">
        <div class="form-grid">
          <input v-model="kbForm.name" class="input" placeholder="知识库名称" />
          <textarea v-model="kbForm.description" class="textarea" placeholder="知识库描述" />
          <div class="inline-actions">
            <button class="btn btn-primary" :disabled="savingKb || !kbForm.name.trim()" @click="submitKb">
              {{ kbForm.id ? '保存知识库' : '创建知识库' }}
            </button>
            <button v-if="kbForm.id" class="btn btn-secondary" @click="resetKbForm">取消编辑</button>
          </div>
        </div>

        <div class="subtle-divider" />

        <AsyncState
          :loading="loadingKb"
          :error="kbError"
          :empty="!kbRows.length"
          empty-title="还没有知识库"
          empty-description="先创建一个知识库，再进入文档治理和检索配置。"
        >
          <div class="list-stack">
            <article
              v-for="kb in kbRows"
              :key="kb.id"
              class="resource-item"
              :class="{ active: selectedKbId === kb.id }"
            >
              <button class="w-full text-left" @click="selectKb(kb.id)">
                <div class="resource-title">{{ kb.name }}</div>
                <div class="resource-meta">
                  <span>{{ kb.collectionName }}</span>
                  <span>{{ kb.embeddingModel }}</span>
                  <span>{{ formatDate(kb.createdAt) }}</span>
                </div>
              </button>
              <div class="mt-3 inline-actions">
                <button class="btn btn-secondary" @click="editKb(kb)">编辑</button>
                <button class="btn btn-danger" @click="removeKb(kb.id)">删除</button>
              </div>
            </article>
          </div>
        </AsyncState>
      </SurfaceCard>

      <SurfaceCard
        title="文档工作区"
        :subtitle="selectedKb?.name ? `当前知识库：${selectedKb.name}` : '先选择左侧知识库，再查看文档。'"
      >
        <template #actions>
          <select v-model="docFilter" class="select !w-auto">
            <option value="">全部状态</option>
            <option value="success">成功</option>
            <option value="processing">处理中</option>
            <option value="failed">失败</option>
          </select>
        </template>

        <div class="toolbar">
          <input v-model="docKeyword" class="input max-w-sm" placeholder="搜索文档名称" />
          <input type="file" class="input max-w-sm" @change="pickFile" />
          <button class="btn btn-primary" :disabled="!selectedKbId || !pendingFile || uploading" @click="upload">
            {{ uploading ? '上传中...' : '上传文档' }}
          </button>
          <button class="btn btn-secondary" :disabled="!selectedKbId" @click="loadDocuments">刷新文档</button>
        </div>
        <div v-if="uploadStatus" class="helper-text mb-4 text-sm">{{ uploadStatus }}</div>

        <AsyncState
          :loading="loadingDocs"
          :error="docError"
          :empty="!filteredDocs.length"
          empty-title="没有可展示的文档"
          empty-description="上传文档或放宽筛选条件后，这里会显示文档清单。"
        >
          <div class="table-wrap">
            <table class="data-table">
              <thead>
                <tr>
                  <th>文档</th>
                  <th>状态</th>
                  <th>Chunk</th>
                  <th>类型</th>
                  <th>大小</th>
                  <th>更新时间</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="doc in filteredDocs" :key="doc.id">
                  <td>
                    <div class="font-semibold">{{ doc.docName }}</div>
                    <div class="muted mt-1 text-xs">KB {{ doc.kbId }}</div>
                  </td>
                  <td><span :class="statusClass(doc.status)" class="status-badge">{{ doc.status }}</span></td>
                  <td>{{ doc.chunkCount }}</td>
                  <td>{{ doc.fileType || '-' }}</td>
                  <td>{{ formatBytes(doc.fileSize) }}</td>
                  <td>{{ formatDate(doc.createdAt) }}</td>
                  <td>
                    <div class="inline-actions">
                      <button class="btn btn-secondary" @click="openDocumentDrawer(doc.id)">查看详情</button>
                      <button class="btn btn-secondary" @click="runChunk(doc.id)">分块</button>
                      <button class="btn btn-secondary" @click="toggleDoc(doc)">
                        {{ doc.enabled ? '停用' : '启用' }}
                      </button>
                      <button class="btn btn-danger" @click="removeDoc(doc.id)">删除</button>
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </AsyncState>
      </SurfaceCard>
    </div>

    <DetailDrawer
      :open="drawerOpen"
      title="文档详情与 Chunk 管理"
      :subtitle="selectedDoc?.docName || '加载中'"
      @close="drawerOpen = false"
    >
      <AsyncState
        :loading="loadingDetail"
        :error="detailError"
        :empty="!selectedDoc"
        empty-title="尚未选择文档"
        empty-description="从文档列表中选择一条记录查看详情。"
      >
        <div v-if="selectedDoc" class="list-stack">
          <KeyValueGrid :items="documentDetails" />

          <div class="grid-two">
            <div class="form-grid">
              <div>
                <div class="meta-label !text-slate-500">文档名称</div>
                <input v-model="docForm.doc_name" class="input mt-2" placeholder="文档名称" />
              </div>
              <div>
                <div class="meta-label !text-slate-500">分块策略</div>
                <select v-model="docForm.chunk_strategy" class="select mt-2">
                  <option v-for="strategy in chunkStrategies" :key="strategy" :value="strategy">{{ strategy }}</option>
                </select>
              </div>
              <div>
                <div class="meta-label !text-slate-500">分块配置</div>
                <div class="grid-two mt-2">
                  <input v-model.number="docConfigForm.chunk_size" type="number" min="100" step="50" class="input" placeholder="chunk size" />
                  <input v-model.number="docConfigForm.chunk_overlap" type="number" min="0" step="10" class="input" placeholder="chunk overlap" />
                </div>
              </div>
              <div class="inline-actions">
                <button class="btn btn-primary" @click="saveDocument">保存文档配置</button>
                <button class="btn btn-secondary" @click="rebuildChunks">重建 Chunk</button>
              </div>
            </div>

            <SurfaceCard compact title="最近分块日志" subtitle="查看最近一次分块和重建结果。">
              <div class="list-stack">
                <div v-for="log in chunkLogs" :key="log.id" class="resource-item">
                  <div class="resource-item-row">
                    <span :class="statusClass(log.status)" class="status-badge">{{ log.status }}</span>
                    <span class="text-xs text-slate-500">{{ formatDate(log.createdAt) }}</span>
                  </div>
                  <div class="resource-item-note">{{ log.message || '无附加信息' }}</div>
                  <div class="resource-meta">
                    <span>生成 chunk {{ log.chunkCount ?? 0 }}</span>
                  </div>
                </div>
              </div>
            </SurfaceCard>
          </div>

          <SurfaceCard compact title="Chunk 列表" subtitle="支持批量启停、编辑和删除。">
            <template #actions>
              <div class="inline-actions">
                <button class="btn btn-secondary" :disabled="!selectedChunkIds.length" @click="batchToggleChunks(true)">批量启用</button>
                <button class="btn btn-secondary" :disabled="!selectedChunkIds.length" @click="batchToggleChunks(false)">批量停用</button>
              </div>
            </template>

            <div class="table-wrap">
              <table class="data-table">
                <thead>
                  <tr>
                    <th></th>
                    <th>#</th>
                    <th>内容片段</th>
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
                      <span :class="statusClass(chunk.enabled ? 'enabled' : 'disabled')" class="status-badge">
                        {{ chunk.enabled ? 'enabled' : 'disabled' }}
                      </span>
                    </td>
                    <td>
                      <div class="inline-actions">
                        <button class="btn btn-secondary" @click="editChunk(chunk)">编辑</button>
                        <button class="btn btn-danger" @click="removeChunk(chunk.id)">删除</button>
                      </div>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </SurfaceCard>

          <SurfaceCard compact :title="chunkForm.id ? '编辑 Chunk' : '新增 Chunk'" subtitle="修正文档片段或手工补录高价值内容。">
            <div class="form-grid">
              <textarea v-model="chunkForm.content" class="textarea" placeholder="Chunk 内容" />
              <div class="grid-two">
                <select v-model="chunkMetadataForm.source" class="select">
                  <option v-for="item in chunkSourceOptions" :key="item" :value="item">{{ item }}</option>
                </select>
                <input v-model="chunkMetadataForm.note" class="input" placeholder="metadata note" />
              </div>
              <label class="inline-actions items-center">
                <input v-model="chunkForm.enabled" type="checkbox" />
                <span>启用此 Chunk</span>
              </label>
              <div class="inline-actions">
                <button class="btn btn-primary" :disabled="!selectedDoc?.id || !chunkForm.content.trim()" @click="saveChunk">
                  {{ chunkForm.id ? '保存 Chunk' : '新增 Chunk' }}
                </button>
                <button class="btn btn-secondary" @click="resetChunkForm">重置</button>
              </div>
            </div>
          </SurfaceCard>
        </div>
      </AsyncState>
    </DetailDrawer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import AsyncState from '@/components/admin/AsyncState.vue'
import DetailDrawer from '@/components/admin/DetailDrawer.vue'
import KeyValueGrid from '@/components/admin/KeyValueGrid.vue'
import PageHeader from '@/components/admin/PageHeader.vue'
import SurfaceCard from '@/components/admin/SurfaceCard.vue'
import { knowledgeService } from '@/services/knowledgeService'

const kbRows = ref<any[]>([])
const docs = ref<any[]>([])
const chunks = ref<any[]>([])
const chunkLogs = ref<any[]>([])
const chunkStrategies = ref<string[]>([])

const selectedKbId = ref('')
const selectedDocId = ref('')
const selectedDoc = ref<any | null>(null)
const selectedChunkIds = ref<string[]>([])
const pendingFile = ref<File | null>(null)
const docKeyword = ref('')
const docFilter = ref('')
const drawerOpen = ref(false)

const loadingKb = ref(false)
const kbError = ref('')
const loadingDocs = ref(false)
const docError = ref('')
const loadingDetail = ref(false)
const detailError = ref('')
const savingKb = ref(false)
const uploading = ref(false)
const uploadStatus = ref('')

const kbForm = ref({ id: '', name: '', description: '' })
const docForm = ref({
  doc_name: '',
  chunk_strategy: 'recursive',
})
const docConfigForm = ref({ chunk_size: 500, chunk_overlap: 50 })
const chunkForm = ref<{ id: string; content: string; enabled: boolean }>({ id: '', content: '', enabled: true })
const chunkMetadataForm = ref({ source: 'manual', note: '' })
const chunkSourceOptions = ['manual', 'upload', 'parser', 'chunker', 'indexer']

const selectedKb = computed(() => kbRows.value.find((item) => item.id === selectedKbId.value) ?? null)

const filteredDocs = computed(() =>
  docs.value.filter((item) => (!docFilter.value ? true : item.status === docFilter.value)),
)

const documentDetails = computed(() => {
  if (!selectedDoc.value) return []
  return [
    { label: '状态', value: selectedDoc.value.status },
    { label: '启用状态', value: selectedDoc.value.enabled ? '已启用' : '已停用' },
    { label: '文件类型', value: selectedDoc.value.fileType || '-' },
    { label: '文件大小', value: formatBytes(selectedDoc.value.fileSize) },
    { label: 'Chunk 数量', value: selectedDoc.value.chunkCount ?? 0 },
    { label: '错误信息', value: selectedDoc.value.errorMessage || '无' },
  ]
})

async function loadKnowledgeBases() {
  loadingKb.value = true
  kbError.value = ''
  try {
    const page = await knowledgeService.listKnowledgeBases()
    kbRows.value = page.items
    if (!selectedKbId.value && kbRows.value[0]?.id) {
      await selectKb(kbRows.value[0].id)
    }
  } catch (err: any) {
    kbError.value = err?.detail || err?.message || '知识库加载失败'
  } finally {
    loadingKb.value = false
  }
}

async function loadStrategies() {
  try {
    chunkStrategies.value = await knowledgeService.chunkStrategies()
  } catch {
    chunkStrategies.value = ['recursive']
  }
}

async function loadDocuments() {
  if (!selectedKbId.value) return
  loadingDocs.value = true
  docError.value = ''
  try {
    const page = await knowledgeService.listDocuments(selectedKbId.value, docKeyword.value)
    docs.value = page.items
    if (selectedDocId.value && docs.value.some((item) => item.id === selectedDocId.value)) {
      await selectDocument(selectedDocId.value)
    }
  } catch (err: any) {
    docError.value = err?.detail || err?.message || '文档列表加载失败'
  } finally {
    loadingDocs.value = false
  }
}

async function selectKb(id: string) {
  selectedKbId.value = id
  selectedDocId.value = ''
  selectedDoc.value = null
  chunks.value = []
  chunkLogs.value = []
  await loadDocuments()
}

async function openDocumentDrawer(id: string) {
  drawerOpen.value = true
  await selectDocument(id)
}

async function selectDocument(id: string) {
  selectedDocId.value = id
  loadingDetail.value = true
  detailError.value = ''
  try {
    const [doc, chunkPage, logs] = await Promise.all([
      knowledgeService.getDocument(id),
      knowledgeService.listChunks(id),
      knowledgeService.chunkLogs(id),
    ])
    selectedDoc.value = doc
    docForm.value = {
      doc_name: doc.docName || '',
      chunk_strategy: doc.chunkStrategy || chunkStrategies.value[0] || 'recursive',
    }
    docConfigForm.value = {
      chunk_size: Number(doc.chunkConfig?.chunk_size ?? 500),
      chunk_overlap: Number(doc.chunkConfig?.chunk_overlap ?? 50),
    }
    chunks.value = chunkPage.items
    chunkLogs.value = logs
    selectedChunkIds.value = []
    resetChunkForm()
  } catch (err: any) {
    detailError.value = err?.detail || err?.message || '文档详情加载失败'
  } finally {
    loadingDetail.value = false
  }
}

async function submitKb() {
  savingKb.value = true
  try {
    if (kbForm.value.id) {
      await knowledgeService.updateKnowledgeBase(kbForm.value.id, {
        name: kbForm.value.name,
        description: kbForm.value.description,
      })
    } else {
      await knowledgeService.createKnowledgeBase({
        name: kbForm.value.name,
        description: kbForm.value.description,
      })
    }
    resetKbForm()
    await loadKnowledgeBases()
  } finally {
    savingKb.value = false
  }
}

function editKb(kb: any) {
  kbForm.value = { id: kb.id, name: kb.name, description: kb.description || '' }
}

function resetKbForm() {
  kbForm.value = { id: '', name: '', description: '' }
}

async function removeKb(id: string) {
  await knowledgeService.deleteKnowledgeBase(id)
  if (selectedKbId.value === id) {
    selectedKbId.value = ''
    selectedDocId.value = ''
    selectedDoc.value = null
    docs.value = []
    chunks.value = []
    chunkLogs.value = []
  }
  await loadKnowledgeBases()
}

function pickFile(event: Event) {
  const input = event.target as HTMLInputElement
  pendingFile.value = input.files?.[0] ?? null
}

async function upload() {
  if (!selectedKbId.value || !pendingFile.value) return
  uploading.value = true
  uploadStatus.value = '文件上传中...'
  try {
    const result = await knowledgeService.uploadDocument(selectedKbId.value, pendingFile.value)
    uploadStatus.value = `已入队处理：${result.data?.docName || pendingFile.value.name}`
    pendingFile.value = null
    await loadDocuments()
  } catch (err: any) {
    uploadStatus.value = err?.detail || err?.message || '上传失败'
  } finally {
    uploading.value = false
  }
}

async function runChunk(docId: string) {
  await knowledgeService.startChunk(docId)
  uploadStatus.value = '已触发分块任务，正在刷新文档状态。'
  await loadDocuments()
  if (selectedDocId.value === docId) {
    await selectDocument(docId)
  }
}

async function toggleDoc(doc: any) {
  await knowledgeService.setDocumentEnabled(doc.id, !doc.enabled)
  await loadDocuments()
  if (selectedDocId.value === doc.id) {
    await selectDocument(doc.id)
  }
}

async function removeDoc(docId: string) {
  await knowledgeService.deleteDocument(docId)
  if (selectedDocId.value === docId) {
    selectedDocId.value = ''
    selectedDoc.value = null
    chunks.value = []
    chunkLogs.value = []
    drawerOpen.value = false
  }
  await loadDocuments()
}

async function saveDocument() {
  if (!selectedDocId.value) return
  await knowledgeService.updateDocument(selectedDocId.value, {
    doc_name: docForm.value.doc_name,
    chunk_strategy: docForm.value.chunk_strategy,
    chunk_config: {
      chunk_size: Number(docConfigForm.value.chunk_size || 500),
      chunk_overlap: Number(docConfigForm.value.chunk_overlap || 0),
    },
  })
  await selectDocument(selectedDocId.value)
}

async function rebuildChunks() {
  if (!selectedDocId.value) return
  await knowledgeService.rebuildChunks(selectedDocId.value)
  await selectDocument(selectedDocId.value)
  await loadDocuments()
}

function editChunk(chunk: any) {
  chunkForm.value = {
    id: chunk.id,
    content: chunk.content,
    enabled: !!chunk.enabled,
  }
  chunkMetadataForm.value = {
    source: String(chunk.metadata?.source || 'manual'),
    note: String(chunk.metadata?.note || ''),
  }
}

function resetChunkForm() {
  chunkForm.value = { id: '', content: '', enabled: true }
  chunkMetadataForm.value = { source: 'manual', note: '' }
}

async function saveChunk() {
  if (!selectedDocId.value) return
  const payload = {
    content: chunkForm.value.content,
    enabled: chunkForm.value.enabled,
    metadata: {
      source: chunkMetadataForm.value.source,
      ...(chunkMetadataForm.value.note.trim() ? { note: chunkMetadataForm.value.note.trim() } : {}),
    },
  }
  if (chunkForm.value.id) {
    await knowledgeService.updateChunk(selectedDocId.value, chunkForm.value.id, payload)
  } else {
    await knowledgeService.createChunk(selectedDocId.value, payload)
  }
  resetChunkForm()
  await selectDocument(selectedDocId.value)
  await loadDocuments()
}

async function removeChunk(chunkId: string) {
  if (!selectedDocId.value) return
  await knowledgeService.deleteChunk(selectedDocId.value, chunkId)
  await selectDocument(selectedDocId.value)
}

async function batchToggleChunks(enabled: boolean) {
  if (!selectedDocId.value || !selectedChunkIds.value.length) return
  await knowledgeService.batchEnableChunks(selectedDocId.value, selectedChunkIds.value, enabled)
  await selectDocument(selectedDocId.value)
}

async function refreshAll() {
  await Promise.all([loadStrategies(), loadKnowledgeBases()])
  if (selectedKbId.value) {
    await loadDocuments()
  }
  if (selectedDocId.value) {
    await selectDocument(selectedDocId.value)
  }
}

watch(docKeyword, () => {
  if (!selectedKbId.value) return
  void loadDocuments()
})

function formatDate(value?: string) {
  return value ? new Date(value).toLocaleString() : '-'
}

function formatBytes(size?: number) {
  if (!size) return '0 B'
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / 1024 / 1024).toFixed(2)} MB`
}

function truncate(value: string, length: number) {
  return value.length > length ? `${value.slice(0, length)}...` : value
}

function statusClass(status: string) {
  const normalized = String(status || '').toLowerCase()
  if (['success', 'completed', 'enabled'].includes(normalized)) return 'status-badge-success'
  if (['failed', 'error', 'disabled'].includes(normalized)) return 'status-badge-danger'
  if (['processing', 'running', 'pending'].includes(normalized)) return 'status-badge-warning'
  return 'status-badge-neutral'
}

onMounted(async () => {
  await loadStrategies()
  await loadKnowledgeBases()
})
</script>

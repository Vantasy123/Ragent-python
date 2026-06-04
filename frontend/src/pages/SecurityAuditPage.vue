<template>
  <section class="audit-page">
    <PageHeader
      title="安全审计中心"
      eyebrow="Security Audit"
      description="集中追溯账号、运行时配置和高风险运维审批的关键操作。"
    >
      <template #actions>
        <button class="btn btn-secondary" @click="exportActiveCsv">导出当前页</button>
        <button class="btn btn-secondary" :disabled="exportingAll" @click="exportAllActiveCsv">
          {{ exportingAll ? '导出中...' : '导出筛选结果' }}
        </button>
        <button class="btn btn-secondary" @click="refreshActive">刷新当前审计</button>
      </template>
    </PageHeader>

    <div class="audit-overview">
      <article v-for="card in overviewCards" :key="card.label" class="audit-card">
        <div class="meta-label !text-slate-500">{{ card.label }}</div>
        <div class="audit-card-value">{{ card.value }}</div>
        <div class="helper-text">{{ card.hint }}</div>
      </article>
    </div>

    <SurfaceCard title="审计查询" subtitle="按审计域切换，不同域保留独立筛选条件和分页。">
      <div class="audit-tabs">
        <button
          v-for="tab in auditTabs"
          :key="tab.key"
          class="audit-tab"
          :class="activeTab === tab.key ? 'audit-tab-active' : ''"
          @click="activeTab = tab.key"
        >
          {{ tab.label }}
        </button>
      </div>

      <div v-if="activeTab === 'users'" class="audit-section">
        <div class="inline-actions mb-4">
          <select v-model="userFilter.action" class="select max-w-xs" @change="loadUserAudit(1)">
            <option value="">全部动作</option>
            <option value="create">创建</option>
            <option value="update">更新</option>
            <option value="delete">删除</option>
          </select>
          <input v-model="userFilter.targetUserId" class="input max-w-xs" placeholder="按用户 ID 过滤" @keyup.enter="loadUserAudit(1)" />
          <button class="btn btn-secondary" :disabled="userAudit.loading" @click="loadUserAudit(1)">查询</button>
        </div>
        <AsyncState :loading="userAudit.loading" :error="userAudit.error" :empty="!userAudit.items.length" empty-title="暂无用户审计记录">
          <div class="overflow-x-auto">
            <table class="audit-table">
              <thead>
                <tr>
                  <th>时间</th>
                  <th>动作</th>
                  <th>目标用户</th>
                  <th>变更摘要</th>
                  <th>操作人</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in userAudit.items" :key="row.id">
                  <td>{{ formatTime(row.createdAt) }}</td>
                  <td>{{ userActionLabel(row.action) }}</td>
                  <td>
                    <div class="font-medium text-slate-800">{{ row.targetUsername || '-' }}</div>
                    <div class="helper-text">{{ row.targetUserId || '-' }}</div>
                  </td>
                  <td>{{ userChangeSummary(row) }}</td>
                  <td>{{ row.changedBy || '-' }}</td>
                  <td>
                    <button class="btn btn-ghost !px-3 !py-1 text-xs" @click="openAuditDetail('users', row)">详情</button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <PaginationBar :total="userAudit.total" :page-size="userAudit.pageSize" :current-page="userAudit.pageNo" @update:page="loadUserAudit" />
        </AsyncState>
      </div>

      <div v-else-if="activeTab === 'settings'" class="audit-section">
        <div class="inline-actions mb-4">
          <input v-model="settingFilter.key" class="input max-w-xs" placeholder="按配置键过滤，例如 rag.topK" @keyup.enter="loadSettingAudit(1)" />
          <button class="btn btn-secondary" :disabled="settingAudit.loading" @click="loadSettingAudit(1)">查询</button>
        </div>
        <AsyncState :loading="settingAudit.loading" :error="settingAudit.error" :empty="!settingAudit.items.length" empty-title="暂无设置审计记录">
          <div class="overflow-x-auto">
            <table class="audit-table">
              <thead>
                <tr>
                  <th>时间</th>
                  <th>配置键</th>
                  <th>原值</th>
                  <th>新值</th>
                  <th>操作人</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in settingAudit.items" :key="row.id">
                  <td>{{ formatTime(row.createdAt) }}</td>
                  <td class="font-medium text-slate-800">{{ row.key }}</td>
                  <td>{{ displayValue(row.oldValue) }}</td>
                  <td>{{ displayValue(row.newValue) }}</td>
                  <td>{{ row.changedBy || '-' }}</td>
                  <td>
                    <button class="btn btn-ghost !px-3 !py-1 text-xs" @click="openAuditDetail('settings', row)">详情</button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <PaginationBar :total="settingAudit.total" :page-size="settingAudit.pageSize" :current-page="settingAudit.pageNo" @update:page="loadSettingAudit" />
        </AsyncState>
      </div>

      <div v-else-if="activeTab === 'events'" class="audit-section">
        <div class="inline-actions mb-4">
          <select v-model="eventFilter.category" class="select max-w-xs" @change="loadEventAudit(1)">
            <option value="">全部类型</option>
            <option value="export">导出</option>
          </select>
          <select v-model="eventFilter.action" class="select max-w-xs" @change="loadEventAudit(1)">
            <option value="">全部动作</option>
            <option value="export_audit_csv">审计导出</option>
          </select>
          <select v-model="eventFilter.targetId" class="select max-w-xs" @change="loadEventAudit(1)">
            <option value="">全部对象</option>
            <option value="users">用户审计</option>
            <option value="settings">设置审计</option>
            <option value="ops">运维审批</option>
            <option value="events">安全事件</option>
          </select>
          <button class="btn btn-secondary" :disabled="eventAudit.loading" @click="loadEventAudit(1)">查询</button>
        </div>
        <AsyncState :loading="eventAudit.loading" :error="eventAudit.error" :empty="!eventAudit.items.length" empty-title="暂无安全事件记录">
          <div class="overflow-x-auto">
            <table class="audit-table">
              <thead>
                <tr>
                  <th>时间</th>
                  <th>类型</th>
                  <th>动作</th>
                  <th>对象</th>
                  <th>操作人</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in eventAudit.items" :key="row.id">
                  <td>{{ formatTime(row.createdAt) }}</td>
                  <td>{{ eventCategoryLabel(row.category) }}</td>
                  <td>{{ eventActionLabel(row.action) }}</td>
                  <td>{{ row.targetType || '-' }} / {{ row.targetId || '-' }}</td>
                  <td>{{ row.operatorId || '-' }}</td>
                  <td>
                    <button class="btn btn-ghost !px-3 !py-1 text-xs" @click="openAuditDetail('events', row)">详情</button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <PaginationBar :total="eventAudit.total" :page-size="eventAudit.pageSize" :current-page="eventAudit.pageNo" @update:page="loadEventAudit" />
        </AsyncState>
      </div>

      <div v-else class="audit-section">
        <div class="inline-actions mb-4">
          <select v-model="opsFilter.status" class="select max-w-xs" @change="loadOpsAudit(1)">
            <option value="">全部状态</option>
            <option value="pending">待审批</option>
            <option value="approved">已通过</option>
            <option value="rejected">已拒绝</option>
          </select>
          <input v-model="opsFilter.runId" class="input max-w-xs" placeholder="按运行 ID 过滤" @keyup.enter="loadOpsAudit(1)" />
          <button class="btn btn-secondary" :disabled="opsAudit.loading" @click="loadOpsAudit(1)">查询</button>
        </div>
        <AsyncState :loading="opsAudit.loading" :error="opsAudit.error" :empty="!opsAudit.items.length" empty-title="暂无运维审批记录">
          <div class="overflow-x-auto">
            <table class="audit-table">
              <thead>
                <tr>
                  <th>时间</th>
                  <th>工具</th>
                  <th>状态</th>
                  <th>审批人</th>
                  <th>意见</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in opsAudit.items" :key="row.id">
                  <td>{{ formatTime(row.decidedAt || row.createdAt) }}</td>
                  <td>
                    <div class="font-medium text-slate-800">{{ row.toolName }}</div>
                    <div class="helper-text">{{ row.runId }}</div>
                  </td>
                  <td>
                    <span class="status-badge" :class="opsStatusClass(row.status)">{{ opsStatusLabel(row.status) }}</span>
                  </td>
                  <td>{{ row.approvedByName || row.requestedByName || '-' }}</td>
                  <td>{{ row.comment || row.message || '-' }}</td>
                  <td>
                    <button class="btn btn-ghost !px-3 !py-1 text-xs" @click="openAuditDetail('ops', row)">详情</button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <PaginationBar :total="opsAudit.total" :page-size="opsAudit.pageSize" :current-page="opsAudit.pageNo" @update:page="loadOpsAudit" />
        </AsyncState>
      </div>
    </SurfaceCard>

    <DetailDrawer :open="Boolean(selectedAudit)" :title="detailTitle" :subtitle="detailSubtitle" @close="selectedAudit = null">
      <div class="detail-stack">
        <KeyValueGrid :items="detailItems" :columns="1" />
        <SurfaceCard compact title="原始字段">
          <DataPreview :data="selectedAudit || {}" />
        </SurfaceCard>
      </div>
    </DetailDrawer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import AsyncState from '@/components/admin/AsyncState.vue'
import DataPreview from '@/components/admin/DataPreview.vue'
import DetailDrawer from '@/components/admin/DetailDrawer.vue'
import KeyValueGrid from '@/components/admin/KeyValueGrid.vue'
import PageHeader from '@/components/admin/PageHeader.vue'
import PaginationBar from '@/components/admin/PaginationBar.vue'
import SurfaceCard from '@/components/admin/SurfaceCard.vue'
import { adminService } from '@/services/adminService'

type AuditTab = 'users' | 'settings' | 'ops' | 'events'

type AuditPageState<T> = {
  items: T[]
  total: number
  pageNo: number
  pageSize: number
  loading: boolean
  error: string
}

type UserAuditRow = {
  id: string
  action: string
  targetUserId: string
  targetUsername: string
  oldValue: Record<string, any>
  newValue: Record<string, any>
  changedBy: string | null
  createdAt: string | null
}

type SettingAuditRow = {
  id: string
  key: string
  oldValue: string
  newValue: string
  changedBy: string | null
  createdAt: string | null
}

type OpsAuditRow = {
  id: string
  runId: string
  toolCallId?: string
  toolName: string
  args?: Record<string, unknown>
  status: string
  requestedBy?: string
  requestedByName?: string
  approvedBy?: string
  approvedByName?: string
  comment?: string
  message?: string
  createdAt?: string
  decidedAt?: string
}

type SecurityEventRow = {
  id: string
  category: string
  action: string
  targetType: string
  targetId: string
  detail: Record<string, any>
  operatorId: string | null
  createdAt: string | null
}

const auditTabs: Array<{ key: AuditTab; label: string }> = [
  { key: 'users', label: '用户审计' },
  { key: 'settings', label: '设置审计' },
  { key: 'ops', label: '运维审批' },
  { key: 'events', label: '安全事件' },
]

const activeTab = ref<AuditTab>('users')
const userFilter = reactive({ action: '', targetUserId: '' })
const settingFilter = reactive({ key: '' })
const opsFilter = reactive({ status: '', runId: '' })
const eventFilter = reactive({ category: '', action: '', targetId: '' })
const userAudit = reactive<AuditPageState<UserAuditRow>>(createPageState<UserAuditRow>())
const settingAudit = reactive<AuditPageState<SettingAuditRow>>(createPageState<SettingAuditRow>())
const opsAudit = reactive<AuditPageState<OpsAuditRow>>(createPageState<OpsAuditRow>())
const eventAudit = reactive<AuditPageState<SecurityEventRow>>(createPageState<SecurityEventRow>())
const selectedAudit = ref<Record<string, unknown> | null>(null)
const selectedAuditKind = ref<AuditTab>('users')
const exportingAll = ref(false)
const EXPORT_PAGE_SIZE = 100
const MAX_EXPORT_ROWS = 5000

const overviewCards = computed(() => [
  { label: '用户审计', value: userAudit.total, hint: '账号增删改记录' },
  { label: '设置审计', value: settingAudit.total, hint: '运行时配置变更' },
  { label: '运维审批', value: opsAudit.total, hint: '高风险工具人工决定' },
  { label: '安全事件', value: eventAudit.total, hint: '导出等跨模块安全动作' },
])
const detailTitle = computed(() => {
  const map: Record<AuditTab, string> = { users: '用户审计详情', settings: '设置审计详情', ops: '运维审批详情', events: '安全事件详情' }
  return map[selectedAuditKind.value]
})
const detailSubtitle = computed(() => selectedAudit.value?.id ? `审计 ID：${selectedAudit.value.id}` : '审计原始字段')
const detailItems = computed(() => {
  if (!selectedAudit.value) return []
  if (selectedAuditKind.value === 'settings') return settingDetailItems(selectedAudit.value as unknown as SettingAuditRow)
  if (selectedAuditKind.value === 'ops') return opsDetailItems(selectedAudit.value as unknown as OpsAuditRow)
  if (selectedAuditKind.value === 'events') return eventDetailItems(selectedAudit.value as unknown as SecurityEventRow)
  return userDetailItems(selectedAudit.value as unknown as UserAuditRow)
})

function createPageState<T>(): AuditPageState<T> {
  return { items: [], total: 0, pageNo: 1, pageSize: 10, loading: false, error: '' }
}

async function loadUserAudit(pageNo = userAudit.pageNo) {
  userAudit.loading = true
  userAudit.error = ''
  try {
    const page = await adminService.userAuditLogs(pageNo, userAudit.pageSize, userFilter.targetUserId.trim(), userFilter.action)
    applyPage(userAudit, page, pageNo)
  } catch (err: any) {
    userAudit.error = err?.detail || err?.message || '用户审计加载失败'
  } finally {
    userAudit.loading = false
  }
}

async function loadSettingAudit(pageNo = settingAudit.pageNo) {
  settingAudit.loading = true
  settingAudit.error = ''
  try {
    const page = await adminService.settingAuditLogs(pageNo, settingAudit.pageSize, settingFilter.key.trim())
    applyPage(settingAudit, page, pageNo)
  } catch (err: any) {
    settingAudit.error = err?.detail || err?.message || '设置审计加载失败'
  } finally {
    settingAudit.loading = false
  }
}

async function loadOpsAudit(pageNo = opsAudit.pageNo) {
  opsAudit.loading = true
  opsAudit.error = ''
  try {
    const page = await adminService.opsApprovalAuditLogs(pageNo, opsAudit.pageSize, opsFilter.status, opsFilter.runId.trim())
    applyPage(opsAudit, page, pageNo)
  } catch (err: any) {
    opsAudit.error = err?.detail || err?.message || '运维审批审计加载失败'
  } finally {
    opsAudit.loading = false
  }
}

async function loadEventAudit(pageNo = eventAudit.pageNo) {
  eventAudit.loading = true
  eventAudit.error = ''
  try {
    const page = await adminService.securityAuditEvents(pageNo, eventAudit.pageSize, eventFilter.category, eventFilter.action, eventFilter.targetId ? 'audit' : '', eventFilter.targetId)
    applyPage(eventAudit, page, pageNo)
  } catch (err: any) {
    eventAudit.error = err?.detail || err?.message || '安全事件加载失败'
  } finally {
    eventAudit.loading = false
  }
}

function applyPage<T>(state: AuditPageState<T>, page: any, fallbackPageNo: number) {
  state.items = Array.isArray(page?.items) ? page.items : []
  state.total = Number(page?.total ?? 0)
  state.pageNo = Number(page?.pageNo ?? fallbackPageNo)
  state.pageSize = Number(page?.pageSize ?? state.pageSize)
}

function refreshActive() {
  if (activeTab.value === 'users') return loadUserAudit(1)
  if (activeTab.value === 'settings') return loadSettingAudit(1)
  if (activeTab.value === 'events') return loadEventAudit(1)
  return loadOpsAudit(1)
}

function openAuditDetail(kind: AuditTab, row: Record<string, unknown>) {
  selectedAuditKind.value = kind
  selectedAudit.value = row
}

function exportActiveCsv() {
  const { filename, headers, rows } = activeCsvPayload()
  if (!rows.length) return
  downloadCsv(filename, headers, rows)
  void recordExportEvent('current_page', rows.length)
}

function activeCsvPayload() {
  if (activeTab.value === 'settings') {
    return {
      filename: `设置审计-${settingAudit.pageNo}.csv`,
      headers: ['时间', '配置键', '原值', '新值', '操作人'],
      rows: settingAudit.items.map((row) => [formatTime(row.createdAt), row.key, displayValue(row.oldValue), displayValue(row.newValue), row.changedBy || '-']),
    }
  }
  if (activeTab.value === 'ops') {
    return {
      filename: `运维审批审计-${opsAudit.pageNo}.csv`,
      headers: ['时间', '运行ID', '工具', '状态', '审批人', '意见'],
      rows: opsAudit.items.map((row) => [
        formatTime(row.decidedAt || row.createdAt),
        row.runId,
        row.toolName,
        opsStatusLabel(row.status),
        row.approvedByName || row.requestedByName || '-',
        row.comment || row.message || '-',
      ]),
    }
  }
  if (activeTab.value === 'events') {
    return {
      filename: `安全事件-${eventAudit.pageNo}.csv`,
      headers: ['时间', '类型', '动作', '对象类型', '对象 ID', '操作人'],
      rows: eventAudit.items.map((row) => [
        formatTime(row.createdAt),
        eventCategoryLabel(row.category),
        eventActionLabel(row.action),
        row.targetType || '-',
        row.targetId || '-',
        row.operatorId || '-',
      ]),
    }
  }
  return {
    filename: `用户审计-${userAudit.pageNo}.csv`,
    headers: ['时间', '动作', '目标用户', '用户ID', '变更摘要', '操作人'],
    rows: userAudit.items.map((row) => [
      formatTime(row.createdAt),
      userActionLabel(row.action),
      row.targetUsername || '-',
      row.targetUserId || '-',
      userChangeSummary(row),
      row.changedBy || '-',
    ]),
  }
}

async function exportAllActiveCsv() {
  exportingAll.value = true
  try {
    const { filename, headers, rows, capped, totalRows } = await allCsvPayload()
    if (!rows.length) return
    downloadCsv(filename, headers, rows)
    await recordExportEvent('filtered_all', rows.length, totalRows)
    if (capped) {
      window.alert(`当前导出已限制为前 ${MAX_EXPORT_ROWS} 条，请缩小筛选条件后继续导出剩余记录。`)
    }
  } finally {
    exportingAll.value = false
  }
}

async function allCsvPayload() {
  if (activeTab.value === 'settings') {
    const rows = await loadAllRows<SettingAuditRow>((pageNo) => adminService.settingAuditLogs(pageNo, EXPORT_PAGE_SIZE, settingFilter.key.trim()))
    return {
      filename: '设置审计-筛选结果.csv',
      headers: ['时间', '配置键', '原值', '新值', '操作人'],
      rows: rows.items.map((row) => [formatTime(row.createdAt), row.key, displayValue(row.oldValue), displayValue(row.newValue), row.changedBy || '-']),
      capped: rows.capped,
      totalRows: rows.total,
    }
  }
  if (activeTab.value === 'ops') {
    const rows = await loadAllRows<OpsAuditRow>((pageNo) => adminService.opsApprovalAuditLogs(pageNo, EXPORT_PAGE_SIZE, opsFilter.status, opsFilter.runId.trim()))
    return {
      filename: '运维审批审计-筛选结果.csv',
      headers: ['时间', '运行ID', '工具', '状态', '审批人', '意见'],
      rows: rows.items.map((row) => [
        formatTime(row.decidedAt || row.createdAt),
        row.runId,
        row.toolName,
        opsStatusLabel(row.status),
        row.approvedByName || row.requestedByName || '-',
        row.comment || row.message || '-',
      ]),
      capped: rows.capped,
      totalRows: rows.total,
    }
  }
  if (activeTab.value === 'events') {
    const rows = await loadAllRows<SecurityEventRow>((pageNo) =>
      adminService.securityAuditEvents(pageNo, EXPORT_PAGE_SIZE, eventFilter.category, eventFilter.action, eventFilter.targetId ? 'audit' : '', eventFilter.targetId),
    )
    return {
      filename: '安全事件-筛选结果.csv',
      headers: ['时间', '类型', '动作', '对象类型', '对象 ID', '操作人'],
      rows: rows.items.map((row) => [
        formatTime(row.createdAt),
        eventCategoryLabel(row.category),
        eventActionLabel(row.action),
        row.targetType || '-',
        row.targetId || '-',
        row.operatorId || '-',
      ]),
      capped: rows.capped,
      totalRows: rows.total,
    }
  }
  const rows = await loadAllRows<UserAuditRow>((pageNo) => adminService.userAuditLogs(pageNo, EXPORT_PAGE_SIZE, userFilter.targetUserId.trim(), userFilter.action))
  return {
    filename: '用户审计-筛选结果.csv',
    headers: ['时间', '动作', '目标用户', '用户ID', '变更摘要', '操作人'],
    rows: rows.items.map((row) => [
      formatTime(row.createdAt),
      userActionLabel(row.action),
      row.targetUsername || '-',
      row.targetUserId || '-',
      userChangeSummary(row),
      row.changedBy || '-',
    ]),
    capped: rows.capped,
    totalRows: rows.total,
  }
}

async function loadAllRows<T>(loader: (pageNo: number) => Promise<any>) {
  const items: T[] = []
  let pageNo = 1
  let total = 0
  while (items.length < MAX_EXPORT_ROWS) {
    const page = await loader(pageNo)
    const pageItems = Array.isArray(page?.items) ? page.items as T[] : []
    total = Number(page?.total ?? total)
    items.push(...pageItems.slice(0, Math.max(0, MAX_EXPORT_ROWS - items.length)))
    if (!pageItems.length || items.length >= total) break
    pageNo += 1
  }
  return { items, total, capped: total > items.length }
}

function downloadCsv(filename: string, headers: string[], rows: unknown[][]) {
  const content = [headers, ...rows].map((row) => row.map(csvCell).join(',')).join('\n')
  const blob = new Blob([`\uFEFF${content}`], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}

function csvCell(value: unknown) {
  const text = value === null || value === undefined ? '' : String(value)
  return `"${text.replaceAll('"', '""')}"`
}

async function recordExportEvent(scope: 'current_page' | 'filtered_all', rows: number, totalRows = rows) {
  await adminService.recordSecurityAuditEvent({
    category: 'export',
    action: 'export_audit_csv',
    targetType: 'audit',
    targetId: activeTab.value,
    detail: {
      scope,
      rows,
      totalRows,
      filters: activeExportFilters(),
      capped: totalRows > rows,
    },
  })
  await loadEventAudit(1)
}

function activeExportFilters() {
  if (activeTab.value === 'settings') return { key: settingFilter.key.trim() }
  if (activeTab.value === 'ops') return { status: opsFilter.status, runId: opsFilter.runId.trim() }
  if (activeTab.value === 'events') return { category: eventFilter.category, action: eventFilter.action, targetId: eventFilter.targetId }
  return { action: userFilter.action, targetUserId: userFilter.targetUserId.trim() }
}

function userDetailItems(row: UserAuditRow) {
  return [
    { label: '审计类型', value: '用户管理' },
    { label: '动作', value: userActionLabel(row.action) },
    { label: '目标用户', value: row.targetUsername || '-' },
    { label: '目标用户 ID', value: row.targetUserId || '-' },
    { label: '变更摘要', value: userChangeSummary(row) },
    { label: '操作人', value: row.changedBy || '-' },
    { label: '发生时间', value: formatTime(row.createdAt) },
  ]
}

function settingDetailItems(row: SettingAuditRow) {
  return [
    { label: '审计类型', value: '运行时配置' },
    { label: '配置键', value: row.key },
    { label: '原值', value: displayValue(row.oldValue) },
    { label: '新值', value: displayValue(row.newValue) },
    { label: '操作人', value: row.changedBy || '-' },
    { label: '发生时间', value: formatTime(row.createdAt) },
  ]
}

function opsDetailItems(row: OpsAuditRow) {
  return [
    { label: '审计类型', value: '运维审批' },
    { label: '运行 ID', value: row.runId },
    { label: '工具调用 ID', value: row.toolCallId || '-' },
    { label: '工具名称', value: row.toolName },
    { label: '审批状态', value: opsStatusLabel(row.status) },
    { label: '申请人', value: row.requestedByName || row.requestedBy || '-' },
    { label: '审批人', value: row.approvedByName || row.approvedBy || '-' },
    { label: '审批意见', value: row.comment || '-' },
    { label: '运行消息', value: row.message || '-' },
    { label: '申请时间', value: formatTime(row.createdAt) },
    { label: '决定时间', value: formatTime(row.decidedAt) },
  ]
}

function formatTime(value?: string | null) {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('zh-CN', { hour12: false })
}

function displayValue(value?: string | null) {
  return value ? value : '-'
}

function userActionLabel(action?: string) {
  const map: Record<string, string> = { create: '创建', update: '更新', delete: '删除' }
  return map[String(action || '').toLowerCase()] || action || '-'
}

function userChangeSummary(row: UserAuditRow) {
  const source = Object.keys(row.newValue || {}).length ? row.newValue : row.oldValue
  if (!source || Object.keys(source).length === 0) return '-'
  const parts = [
    source.username ? `用户名：${source.username}` : '',
    source.nickname ? `昵称：${source.nickname}` : '',
    source.role ? `角色：${source.role}` : '',
    typeof source.isActive === 'boolean' ? `状态：${source.isActive ? '启用' : '停用'}` : '',
    source.passwordChanged ? '密码：已变更' : '',
  ].filter(Boolean)
  return parts.join('；') || '-'
}

function opsStatusLabel(status?: string) {
  const map: Record<string, string> = { pending: '待审批', approved: '已通过', rejected: '已拒绝' }
  return map[String(status || '').toLowerCase()] || status || '-'
}

function opsStatusClass(status?: string) {
  const normalized = String(status || '').toLowerCase()
  if (normalized === 'approved') return 'status-ok'
  if (normalized === 'rejected') return 'status-danger'
  if (normalized === 'pending') return 'status-warn'
  return 'status-badge-neutral'
}

function eventCategoryLabel(category?: string) {
  const map: Record<string, string> = { export: '导出' }
  return map[String(category || '').toLowerCase()] || category || '-'
}

function eventActionLabel(action?: string) {
  const map: Record<string, string> = { export_audit_csv: '审计导出' }
  return map[String(action || '').toLowerCase()] || action || '-'
}

function eventDetailItems(row: SecurityEventRow) {
  return [
    { label: '审计类型', value: '安全事件' },
    { label: '事件类型', value: eventCategoryLabel(row.category) },
    { label: '动作', value: eventActionLabel(row.action) },
    { label: '对象类型', value: row.targetType || '-' },
    { label: '对象 ID', value: row.targetId || '-' },
    { label: '操作人', value: row.operatorId || '-' },
    { label: '发生时间', value: formatTime(row.createdAt) },
  ]
}

watch(activeTab, () => {
  if (activeTab.value === 'users' && !userAudit.items.length) loadUserAudit()
  if (activeTab.value === 'settings' && !settingAudit.items.length) loadSettingAudit()
  if (activeTab.value === 'ops' && !opsAudit.items.length) loadOpsAudit()
  if (activeTab.value === 'events' && !eventAudit.items.length) loadEventAudit()
})

onMounted(() => {
  loadUserAudit()
  loadSettingAudit()
  loadOpsAudit()
  loadEventAudit()
})
</script>

<style scoped>
.audit-page {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.audit-overview {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.audit-card {
  border: 1px solid var(--border);
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.78);
  padding: 16px;
}

.audit-card-value {
  margin-top: 8px;
  font-size: 28px;
  font-weight: 750;
  color: #0f172a;
}

.audit-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 18px;
}

.audit-tab {
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 9px 14px;
  background: #fff;
  color: #475569;
  font-weight: 650;
}

.audit-tab-active {
  border-color: #2563eb;
  background: #eff6ff;
  color: #1d4ed8;
}

.audit-section {
  min-height: 320px;
}

.audit-table {
  min-width: 100%;
  font-size: 14px;
}

.audit-table th {
  border-bottom: 1px solid #e2e8f0;
  padding: 10px 16px 10px 0;
  text-align: left;
  font-weight: 650;
  color: #64748b;
  white-space: nowrap;
}

.audit-table td {
  border-bottom: 1px solid #f1f5f9;
  padding: 12px 16px 12px 0;
  color: #475569;
  vertical-align: top;
}

.detail-stack {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

@media (max-width: 900px) {
  .audit-overview {
    grid-template-columns: 1fr;
  }
}
</style>

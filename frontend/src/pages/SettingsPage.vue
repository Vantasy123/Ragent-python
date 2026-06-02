<template>
  <section>
    <PageHeader
      title="系统设置"
      eyebrow="运行时设置"
      description="运营参数支持在线保存。已接入热切换的字段会立即生效，需要重启的字段会明确标记。"
    >
      <template #actions>
        <div class="inline-actions">
          <button class="btn btn-secondary" @click="load">刷新</button>
          <button class="btn btn-secondary" :disabled="!isDirty || saving" @click="resetForm">重置</button>
          <button class="btn btn-primary" :disabled="!isDirty || saving" @click="save">
            {{ saving ? '保存中...' : '保存设置' }}
          </button>
        </div>
      </template>
    </PageHeader>

    <AsyncState :loading="loading" :error="error">
      <SurfaceCard v-if="saveMessage" class="mb-5" title="保存结果" :subtitle="saveSubtitle">
        <div class="inline-actions">
          <span :class="saveBadgeClass">{{ saveBadgeLabel }}</span>
          <span class="helper-text">{{ saveMessage }}</span>
        </div>
      </SurfaceCard>

      <SurfaceCard v-if="isDirty" class="mb-5" title="未保存变更" subtitle="当前表单与最近一次已保存配置不一致。">
        <div class="inline-actions">
          <span class="status-badge status-badge-warning">待保存变更</span>
          <span class="helper-text">保存后会刷新页面数据，并按字段能力决定是否热切换。</span>
        </div>
      </SurfaceCard>

      <div class="grid-two">
        <SurfaceCard title="RAG 参数" subtitle="召回数量与生成温度支持在线生效。">
          <div class="form-grid">
            <FieldMeta label="召回数量" :meta="fieldMeta.rag.topK">
              <SettingNumberInput v-model="form.rag.topK" :meta="fieldMeta.rag.topK" />
            </FieldMeta>
            <FieldMeta label="生成温度" :meta="fieldMeta.rag.temperature">
              <SettingNumberInput v-model="form.rag.temperature" :meta="fieldMeta.rag.temperature" :step="0.1" />
            </FieldMeta>
          </div>
        </SurfaceCard>

        <SurfaceCard title="记忆参数" subtitle="历史轮数与标题长度可热更新，摘要相关参数需重启生效。">
          <div class="form-grid form-grid-two">
            <FieldMeta label="历史保留轮数" :meta="fieldMeta.memory.historyKeepTurns">
              <SettingNumberInput v-model="form.memory.historyKeepTurns" :meta="fieldMeta.memory.historyKeepTurns" />
            </FieldMeta>
            <FieldMeta label="摘要启动轮数" :meta="fieldMeta.memory.summaryStartTurns">
              <SettingNumberInput v-model="form.memory.summaryStartTurns" :meta="fieldMeta.memory.summaryStartTurns" />
            </FieldMeta>
            <FieldMeta label="摘要最大字符数" :meta="fieldMeta.memory.summaryMaxChars">
              <SettingNumberInput v-model="form.memory.summaryMaxChars" :meta="fieldMeta.memory.summaryMaxChars" />
            </FieldMeta>
            <FieldMeta label="标题最大长度" :meta="fieldMeta.memory.titleMaxLength">
              <SettingNumberInput v-model="form.memory.titleMaxLength" :meta="fieldMeta.memory.titleMaxLength" />
            </FieldMeta>
          </div>
          <label class="mt-4 inline-actions items-center rounded-2xl border border-slate-200 px-4 py-3">
            <input v-model="form.memory.summaryEnabled" type="checkbox" />
            <span>启用摘要</span>
          </label>
        </SurfaceCard>
      </div>

      <div class="grid-two mt-5">
        <SurfaceCard title="上传限制" subtitle="上传大小限制支持在线更新，超限请求会立即返回错误。">
          <div class="form-grid form-grid-two">
            <FieldMeta label="单文件最大大小" :meta="fieldMeta.upload.maxFileSize">
              <SettingNumberInput v-model="form.upload.maxFileSize" :meta="fieldMeta.upload.maxFileSize" />
            </FieldMeta>
            <FieldMeta label="单请求最大大小" :meta="fieldMeta.upload.maxRequestSize">
              <SettingNumberInput v-model="form.upload.maxRequestSize" :meta="fieldMeta.upload.maxRequestSize" />
            </FieldMeta>
          </div>
        </SurfaceCard>

        <SurfaceCard title="只读配置" subtitle="模型、向量、存储和安全配置当前仅展示，不支持页面直接修改。">
          <div class="list-stack">
            <SurfaceCard compact title="模型与候选">
              <DataPreview :data="readonly.models" />
            </SurfaceCard>
            <SurfaceCard compact title="向量与存储">
              <DataPreview :data="{ vector: readonly.vector, storage: readonly.storage }" />
            </SurfaceCard>
            <SurfaceCard compact title="安全与追踪">
              <DataPreview :data="{ trace: readonly.trace, security: readonly.security }" />
            </SurfaceCard>
          </div>
        </SurfaceCard>
      </div>

      <SurfaceCard class="mt-5" title="设置审计" subtitle="按时间倒序展示后台运行时配置变更记录。">
        <div class="inline-actions mb-4">
          <input v-model="auditKey" class="input max-w-xs" placeholder="按配置键过滤，例如 rag.topK" @keyup.enter="loadAudit(1)" />
          <button class="btn btn-secondary" :disabled="auditLoading" @click="loadAudit(1)">
            {{ auditLoading ? '加载中...' : '查询' }}
          </button>
          <button class="btn btn-secondary" :disabled="auditLoading || !auditKey" @click="clearAuditFilter">清除</button>
        </div>
        <div v-if="auditError" class="helper-text text-red-600">{{ auditError }}</div>
        <div v-else-if="auditRows.length === 0" class="helper-text">暂无设置变更记录。</div>
        <div v-else class="overflow-x-auto">
          <table class="min-w-full text-sm">
            <thead>
              <tr class="border-b border-slate-200 text-left text-slate-500">
                <th class="py-2 pr-4 font-medium">时间</th>
                <th class="py-2 pr-4 font-medium">配置键</th>
                <th class="py-2 pr-4 font-medium">原值</th>
                <th class="py-2 pr-4 font-medium">新值</th>
                <th class="py-2 pr-4 font-medium">类型</th>
                <th class="py-2 pr-4 font-medium">操作者</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in auditRows" :key="row.id" class="border-b border-slate-100">
                <td class="py-3 pr-4 whitespace-nowrap text-slate-600">{{ formatAuditTime(row.createdAt) }}</td>
                <td class="py-3 pr-4 whitespace-nowrap font-medium text-slate-800">{{ row.key }}</td>
                <td class="py-3 pr-4 text-slate-600">{{ displayAuditValue(row.oldValue) }}</td>
                <td class="py-3 pr-4 text-slate-900">{{ displayAuditValue(row.newValue) }}</td>
                <td class="py-3 pr-4 whitespace-nowrap text-slate-600">{{ row.valueType }}</td>
                <td class="py-3 pr-4 whitespace-nowrap text-slate-600">{{ row.changedBy || '-' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="mt-4 inline-actions justify-between">
          <span class="helper-text">共 {{ auditTotal }} 条，当前第 {{ auditPageNo }} 页</span>
          <div class="inline-actions">
            <button class="btn btn-secondary" :disabled="auditLoading || auditPageNo <= 1" @click="loadAudit(auditPageNo - 1)">上一页</button>
            <button class="btn btn-secondary" :disabled="auditLoading || auditPageNo >= auditTotalPages" @click="loadAudit(auditPageNo + 1)">下一页</button>
          </div>
        </div>
      </SurfaceCard>
    </AsyncState>
  </section>
</template>

<script setup lang="ts">
import { computed, defineComponent, h, onMounted, ref } from 'vue'
import AsyncState from '@/components/admin/AsyncState.vue'
import DataPreview from '@/components/admin/DataPreview.vue'
import PageHeader from '@/components/admin/PageHeader.vue'
import SurfaceCard from '@/components/admin/SurfaceCard.vue'
import { adminService } from '@/services/adminService'

type SettingsForm = {
  rag: {
    topK: number
    temperature: number
  }
  memory: {
    historyKeepTurns: number
    summaryEnabled: boolean
    summaryStartTurns: number
    summaryMaxChars: number
    titleMaxLength: number
  }
  upload: {
    maxFileSize: number
    maxRequestSize: number
  }
}

type SettingAuditRow = {
  id: string
  key: string
  oldValue: string
  newValue: string
  valueType: string
  changedBy: string | null
  createdAt: string | null
}

const FieldMeta = defineComponent({
  name: 'FieldMeta',
  props: {
    label: { type: String, required: true },
    meta: { type: Object, default: () => ({}) },
  },
  setup(props, { slots }) {
    const rangeText = computed(() => formatMetaRange(props.meta as Record<string, any>))
    return () =>
      h('div', [
        h('div', { class: 'meta-label !text-slate-500' }, props.label),
        h('div', { class: 'mt-2 inline-actions' }, [
          h(
            'span',
            {
              class: `status-badge ${props.meta?.restartRequired ? 'status-badge-warning' : 'status-badge-success'}`,
            },
            props.meta?.restartRequired ? '需重启' : '即时生效',
          ),
          rangeText.value ? h('span', { class: 'helper-text' }, rangeText.value) : null,
        ]),
        slots.default?.(),
      ])
  },
})

const SettingNumberInput = defineComponent({
  name: 'SettingNumberInput',
  props: {
    modelValue: { type: Number, required: true },
    meta: { type: Object, default: () => ({}) },
    step: { type: Number, default: 1 },
  },
  emits: ['update:modelValue'],
  setup(props, { emit }) {
    return () =>
      h('input', {
        value: props.modelValue,
        type: 'number',
        min: normalizeMetaNumber(props.meta?.min),
        max: normalizeMetaNumber(props.meta?.max),
        step: props.step,
        class: 'input mt-2',
        onInput: (event: Event) => {
          const target = event.target as HTMLInputElement
          emit('update:modelValue', target.value === '' ? 0 : Number(target.value))
        },
      })
  },
})

const loading = ref(false)
const saving = ref(false)
const error = ref('')
const saveMessage = ref('')
const saveRequiresRestart = ref(false)
const initialForm = ref<SettingsForm | null>(null)
const meta = ref<Record<string, any>>({})
const form = ref<SettingsForm>({
  rag: { topK: 5, temperature: 0.7 },
  memory: {
    historyKeepTurns: 4,
    summaryEnabled: true,
    summaryStartTurns: 5,
    summaryMaxChars: 200,
    titleMaxLength: 30,
  },
  upload: {
    maxFileSize: 50 * 1024 * 1024,
    maxRequestSize: 100 * 1024 * 1024,
  },
})
const readonly = ref<Record<string, any>>({})
const auditRows = ref<SettingAuditRow[]>([])
const auditLoading = ref(false)
const auditError = ref('')
const auditKey = ref('')
const auditPageNo = ref(1)
const auditPageSize = 10
const auditTotal = ref(0)

const isDirty = computed(() => JSON.stringify(form.value) !== JSON.stringify(initialForm.value))
const auditTotalPages = computed(() => Math.max(1, Math.ceil(auditTotal.value / auditPageSize)))
const saveBadgeClass = computed(() => (saveRequiresRestart.value ? 'status-badge status-badge-warning' : 'status-badge status-badge-success'))
const saveBadgeLabel = computed(() => (saveRequiresRestart.value ? '部分需重启' : '已热切换'))
const saveSubtitle = computed(() =>
  saveRequiresRestart.value ? '配置已写入数据库。标记为需重启的字段会在后端重启后生效。' : '配置已写入数据库，当前字段已在线生效。',
)
const fieldMeta = computed(() => ({
  rag: meta.value.rag || {},
  memory: meta.value.memory || {},
  upload: meta.value.upload || {},
}))

function cloneForm(source: SettingsForm): SettingsForm {
  return JSON.parse(JSON.stringify(source)) as SettingsForm
}

function normalizeMetaNumber(value: unknown) {
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined
}

function formatMetaRange(metaValue: Record<string, any> | undefined) {
  const min = normalizeMetaNumber(metaValue?.min)
  const max = normalizeMetaNumber(metaValue?.max)
  if (min === undefined && max === undefined) return ''
  if (min !== undefined && max !== undefined) return `范围 ${min} - ${max}`
  if (min !== undefined) return `不小于 ${min}`
  return `不大于 ${max}`
}

function applyPayload(payload: any) {
  const values = payload?.values || {}
  const nextForm: SettingsForm = {
    rag: {
      topK: Number(values.rag?.topK ?? 5),
      temperature: Number(values.rag?.temperature ?? 0.7),
    },
    memory: {
      historyKeepTurns: Number(values.memory?.historyKeepTurns ?? 4),
      summaryEnabled: Boolean(values.memory?.summaryEnabled ?? true),
      summaryStartTurns: Number(values.memory?.summaryStartTurns ?? 5),
      summaryMaxChars: Number(values.memory?.summaryMaxChars ?? 200),
      titleMaxLength: Number(values.memory?.titleMaxLength ?? 30),
    },
    upload: {
      maxFileSize: Number(values.upload?.maxFileSize ?? 50 * 1024 * 1024),
      maxRequestSize: Number(values.upload?.maxRequestSize ?? 100 * 1024 * 1024),
    },
  }
  initialForm.value = cloneForm(nextForm)
  form.value = cloneForm(nextForm)
  readonly.value = values.readonly || {}
  meta.value = payload?.meta || {}
  saveRequiresRestart.value = Boolean(payload?.restartRequired)
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const payload = await adminService.settings()
    applyPayload(payload)
  } catch (err: any) {
    error.value = err?.detail || err?.message || '系统设置加载失败'
  } finally {
    loading.value = false
  }
}

async function loadAudit(pageNo = auditPageNo.value) {
  auditLoading.value = true
  auditError.value = ''
  try {
    const payload = await adminService.settingAuditLogs(pageNo, auditPageSize, auditKey.value.trim())
    auditRows.value = Array.isArray(payload?.items) ? payload.items : []
    auditTotal.value = Number(payload?.total ?? 0)
    auditPageNo.value = Number(payload?.pageNo ?? pageNo)
  } catch (err: any) {
    auditError.value = err?.detail || err?.message || '设置审计加载失败'
  } finally {
    auditLoading.value = false
  }
}

function clearAuditFilter() {
  auditKey.value = ''
  loadAudit(1)
}

function displayAuditValue(value: string | null | undefined) {
  const normalized = value ?? ''
  return normalized === '' ? '-' : normalized
}

function formatAuditTime(value: string | null | undefined) {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('zh-CN', { hour12: false })
}

function resetForm() {
  saveMessage.value = ''
  if (!initialForm.value) return
  form.value = cloneForm(initialForm.value)
}

async function save() {
  saving.value = true
  error.value = ''
  saveMessage.value = ''
  try {
    const payload = await adminService.updateSettings(form.value as unknown as Record<string, unknown>)
    applyPayload(payload)
    await loadAudit(1)
    const changedKeys = Array.isArray(payload?.changedKeys) ? payload.changedKeys.join('、') : ''
    saveMessage.value = changedKeys ? `已保存：${changedKeys}` : '配置已保存，但当前没有新的字段变更。'
  } catch (err: any) {
    error.value = err?.detail || err?.message || '系统设置保存失败'
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  load()
  loadAudit()
})
</script>

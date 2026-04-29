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
              <input v-model.number="form.rag.topK" type="number" min="1" class="input mt-2" />
            </FieldMeta>
            <FieldMeta label="生成温度" :meta="fieldMeta.rag.temperature">
              <input v-model.number="form.rag.temperature" type="number" step="0.1" min="0" max="2" class="input mt-2" />
            </FieldMeta>
          </div>
        </SurfaceCard>

        <SurfaceCard title="记忆参数" subtitle="历史轮数与标题长度可热更新，摘要相关参数需重启生效。">
          <div class="form-grid form-grid-two">
            <FieldMeta label="历史保留轮数" :meta="fieldMeta.memory.historyKeepTurns">
              <input v-model.number="form.memory.historyKeepTurns" type="number" min="1" class="input mt-2" />
            </FieldMeta>
            <FieldMeta label="摘要启动轮数" :meta="fieldMeta.memory.summaryStartTurns">
              <input v-model.number="form.memory.summaryStartTurns" type="number" min="1" class="input mt-2" />
            </FieldMeta>
            <FieldMeta label="摘要最大字符数" :meta="fieldMeta.memory.summaryMaxChars">
              <input v-model.number="form.memory.summaryMaxChars" type="number" min="50" class="input mt-2" />
            </FieldMeta>
            <FieldMeta label="标题最大长度" :meta="fieldMeta.memory.titleMaxLength">
              <input v-model.number="form.memory.titleMaxLength" type="number" min="10" class="input mt-2" />
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
              <input v-model.number="form.upload.maxFileSize" type="number" min="1" class="input mt-2" />
            </FieldMeta>
            <FieldMeta label="单请求最大大小" :meta="fieldMeta.upload.maxRequestSize">
              <input v-model.number="form.upload.maxRequestSize" type="number" min="1" class="input mt-2" />
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

const FieldMeta = defineComponent({
  name: 'FieldMeta',
  props: {
    label: { type: String, required: true },
    meta: { type: Object, default: () => ({}) },
  },
  setup(props, { slots }) {
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
        ]),
        slots.default?.(),
      ])
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

const isDirty = computed(() => JSON.stringify(form.value) !== JSON.stringify(initialForm.value))
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
    const changedKeys = Array.isArray(payload?.changedKeys) ? payload.changedKeys.join('、') : ''
    saveMessage.value = changedKeys ? `已保存：${changedKeys}` : '配置已保存，但当前没有新的字段变更。'
  } catch (err: any) {
    error.value = err?.detail || err?.message || '系统设置保存失败'
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

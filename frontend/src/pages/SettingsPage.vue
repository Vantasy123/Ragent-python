<template>
  <section>
    <PageHeader
      title="系统设置"
      eyebrow="Runtime Settings"
      description="运营参数支持在线保存。已接入热切换的字段会立即生效，摘要类设置仍需后端重启。"
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
          <span class="status-badge status-badge-warning">Pending Changes</span>
          <span class="helper-text">保存后会立即刷新页面数据，并按字段能力决定是否热切换。</span>
        </div>
      </SurfaceCard>

      <div class="grid-two">
        <SurfaceCard title="RAG 参数" subtitle="Top K 与 Temperature 已支持热切换。">
          <div class="form-grid">
            <div>
              <div class="meta-label !text-slate-500">Top K</div>
              <input v-model.number="form.rag.topK" type="number" min="1" class="input mt-2" />
            </div>
            <div>
              <div class="meta-label !text-slate-500">Temperature</div>
              <input v-model.number="form.rag.temperature" type="number" step="0.1" min="0" max="2" class="input mt-2" />
            </div>
            <div class="inline-actions">
              <span class="status-badge status-badge-success">即时生效</span>
            </div>
          </div>
        </SurfaceCard>

        <SurfaceCard title="记忆参数" subtitle="历史轮数与标题截断支持热切换，摘要相关设置暂时仍需重启。">
          <div class="form-grid form-grid-two">
            <div>
              <div class="meta-label !text-slate-500">History Turns</div>
              <input v-model.number="form.memory.historyKeepTurns" type="number" min="1" class="input mt-2" />
            </div>
            <div>
              <div class="meta-label !text-slate-500">Summary Start Turns</div>
              <input v-model.number="form.memory.summaryStartTurns" type="number" min="1" class="input mt-2" />
            </div>
            <div>
              <div class="meta-label !text-slate-500">Summary Max Chars</div>
              <input v-model.number="form.memory.summaryMaxChars" type="number" min="50" class="input mt-2" />
            </div>
            <div>
              <div class="meta-label !text-slate-500">Title Max Length</div>
              <input v-model.number="form.memory.titleMaxLength" type="number" min="10" class="input mt-2" />
            </div>
          </div>
          <label class="mt-4 inline-actions items-center">
            <input v-model="form.memory.summaryEnabled" type="checkbox" />
            <span>启用摘要</span>
          </label>
          <div class="mt-4 inline-actions">
            <span class="status-badge status-badge-success">History / Title 即时生效</span>
            <span class="status-badge status-badge-warning">Summary 需重启</span>
          </div>
        </SurfaceCard>
      </div>

      <div class="grid-two mt-5">
        <SurfaceCard title="上传限制" subtitle="上传大小限制已支持热切换，超限请求会立即返回 413。">
          <div class="form-grid form-grid-two">
            <div>
              <div class="meta-label !text-slate-500">Max File Size</div>
              <input v-model.number="form.upload.maxFileSize" type="number" min="1" class="input mt-2" />
            </div>
            <div>
              <div class="meta-label !text-slate-500">Max Request Size</div>
              <input v-model.number="form.upload.maxRequestSize" type="number" min="1" class="input mt-2" />
            </div>
          </div>
          <div class="mt-4 inline-actions">
            <span class="status-badge status-badge-success">即时生效</span>
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
            <SurfaceCard compact title="安全与 Trace">
              <DataPreview :data="{ trace: readonly.trace, security: readonly.security }" />
            </SurfaceCard>
          </div>
        </SurfaceCard>
      </div>
    </AsyncState>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
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

const loading = ref(false)
const saving = ref(false)
const error = ref('')
const saveMessage = ref('')
const saveRequiresRestart = ref(false)
const initialForm = ref<SettingsForm | null>(null)
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
  saveRequiresRestart.value ? '配置已写入数据库。摘要相关字段仍需重启后端后生效。' : '配置已写入数据库，当前字段已在线生效。'
)

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
    const changedKeys = Array.isArray(payload?.changedKeys) ? payload.changedKeys.join(', ') : ''
    saveMessage.value = changedKeys ? `已保存：${changedKeys}` : '配置已保存，当前没有新的字段变更。'
  } catch (err: any) {
    error.value = err?.detail || err?.message || '系统设置保存失败'
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<template>
  <section>
    <PageHeader
      title="接入配置"
      eyebrow="开源部署"
      description="按个人环境配置模型外的业务服务器、监控地址和健康检查目标，保存后即可被运维监控看板使用。"
    >
      <template #actions>
        <button class="btn btn-secondary" :disabled="loading" @click="loadConfig">刷新配置</button>
      </template>
    </PageHeader>

    <AsyncState :loading="loading" :error="error">
      <div class="dashboard-grid mb-5">
        <article class="metric-card">
          <div class="meta-label">初始化状态</div>
          <div class="mt-3">
            <span :class="['status-badge', status.ready ? 'status-badge-success' : 'status-badge-warning']">
              {{ status.ready ? '已就绪' : '待完善' }}
            </span>
          </div>
          <div class="metric-trend">{{ status.ready ? '配置文件已满足基础接入要求' : '仍有配置项需要补齐' }}</div>
        </article>
        <article class="metric-card">
          <div class="meta-label">业务服务器</div>
          <div class="metric-value">{{ status.enabledServerCount || 0 }}</div>
          <div class="metric-trend">已启用 / 总数 {{ status.serverCount || 0 }}</div>
        </article>
        <article class="metric-card">
          <div class="meta-label">Prometheus</div>
          <div class="mt-3">
            <span :class="['status-badge', status.prometheusConfigured ? 'status-badge-success' : 'status-badge-warning']">
              {{ status.prometheusConfigured ? '已配置' : '未配置' }}
            </span>
          </div>
          <div class="metric-trend">指标数据源</div>
        </article>
        <article class="metric-card">
          <div class="meta-label">Alertmanager</div>
          <div class="mt-3">
            <span :class="['status-badge', status.alertmanagerConfigured ? 'status-badge-success' : 'status-badge-warning']">
              {{ status.alertmanagerConfigured ? '已配置' : '未配置' }}
            </span>
          </div>
          <div class="metric-trend">告警数据源</div>
        </article>
      </div>

      <SurfaceCard v-if="status.nextSteps?.length" title="下一步" subtitle="这些提示来自后端对当前配置文件的检查。" class="mb-5">
        <div class="list-stack">
          <div v-for="item in status.nextSteps" :key="item" class="resource-item">
            <div class="resource-title">{{ item }}</div>
          </div>
        </div>
      </SurfaceCard>

      <div class="grid-two mb-5">
        <SurfaceCard title="监控地址" subtitle="配置 Prometheus 和 Alertmanager，运维监控页会直接读取这些地址。">
          <div class="form-grid">
            <label class="form-stack">
              <span class="meta-label">启用监控</span>
              <select v-model="monitoring.enabled" class="select">
                <option :value="true">启用</option>
                <option :value="false">停用</option>
              </select>
            </label>
            <label class="form-stack">
              <span class="meta-label">Prometheus 地址</span>
              <input v-model.trim="monitoring.prometheus_url" class="input" placeholder="http://prometheus:9090" />
            </label>
            <label class="form-stack">
              <span class="meta-label">Alertmanager 地址</span>
              <input v-model.trim="monitoring.alertmanager_url" class="input" placeholder="http://alertmanager:9093" />
            </label>
            <label class="form-stack">
              <span class="meta-label">超时时间（秒）</span>
              <input v-model.number="monitoring.timeout_seconds" class="input" type="number" min="1" max="30" />
            </label>
            <button class="btn btn-primary" :disabled="savingMonitoring" @click="saveMonitoring">
              {{ savingMonitoring ? '保存中' : '保存监控配置' }}
            </button>
          </div>
        </SurfaceCard>

        <SurfaceCard title="临时探测" subtitle="保存业务服务器前，先测试健康检查 URL 是否可达。">
          <div class="form-grid">
            <label class="form-stack">
              <span class="meta-label">服务名称</span>
              <input v-model.trim="testProbe.name" class="input" placeholder="订单服务" />
            </label>
            <label class="form-stack">
              <span class="meta-label">健康检查 URL</span>
              <input v-model.trim="testProbe.url" class="input" placeholder="http://order-service:8080/health" />
            </label>
            <button class="btn btn-secondary" :disabled="testingProbe || !testProbe.url" @click="runProbeTest">
              {{ testingProbe ? '探测中' : '测试连通性' }}
            </button>
            <div v-if="probeResult" class="state-card !p-4">
              <div class="state-title">
                <span :class="['status-badge', probeResult.status === 'healthy' ? 'status-badge-success' : 'status-badge-danger']">
                  {{ probeResult.statusLabel || (probeResult.status === 'healthy' ? '正常' : '异常') }}
                </span>
              </div>
              <div class="state-description mt-2">{{ probeResult.message }}</div>
            </div>
          </div>
        </SurfaceCard>
      </div>

      <SurfaceCard title="业务服务器" subtitle="这些服务会自动进入运维监控的服务探测列表。">
        <template #actions>
          <button class="btn btn-secondary" @click="addServer">新增服务器</button>
          <button class="btn btn-primary" :disabled="savingServers" @click="saveServers">
            {{ savingServers ? '保存中' : '保存服务器配置' }}
          </button>
        </template>

        <div class="server-list">
          <article v-for="(server, index) in servers" :key="server.localKey" class="server-card">
            <div class="server-card-head">
              <div>
                <div class="resource-title">{{ server.name || '未命名服务' }}</div>
                <div class="resource-meta">
                  <span>{{ server.env || '未设置环境' }}</span>
                  <span>{{ server.owner || '未设置负责人' }}</span>
                </div>
              </div>
              <div class="inline-actions">
                <label class="toggle-row">
                  <input v-model="server.enabled" type="checkbox" />
                  <span>{{ server.enabled ? '启用' : '停用' }}</span>
                </label>
                <button class="btn btn-danger" @click="removeServer(index)">删除</button>
              </div>
            </div>

            <div class="form-grid form-grid-two mt-4">
              <label class="form-stack">
                <span class="meta-label">服务 ID</span>
                <input v-model.trim="server.id" class="input" placeholder="order-service" />
              </label>
              <label class="form-stack">
                <span class="meta-label">服务名称</span>
                <input v-model.trim="server.name" class="input" placeholder="订单服务" />
              </label>
              <label class="form-stack">
                <span class="meta-label">环境</span>
                <input v-model.trim="server.env" class="input" placeholder="prod / staging / dev" />
              </label>
              <label class="form-stack">
                <span class="meta-label">负责人</span>
                <input v-model.trim="server.owner" class="input" placeholder="交易团队" />
              </label>
              <label class="form-stack form-wide">
                <span class="meta-label">基础地址</span>
                <input v-model.trim="server.base_url" class="input" placeholder="http://order-service:8080" />
              </label>
              <label class="form-stack form-wide">
                <span class="meta-label">健康检查 URL</span>
                <input v-model.trim="server.health_url" class="input" placeholder="http://order-service:8080/health" />
              </label>
              <label class="form-stack form-wide">
                <span class="meta-label">指标 URL</span>
                <input v-model.trim="server.metrics_url" class="input" placeholder="http://order-service:8080/metrics" />
              </label>
              <label class="form-stack form-wide">
                <span class="meta-label">标签</span>
                <input v-model.trim="server.tagsText" class="input" placeholder="order, core, java" />
              </label>
            </div>
          </article>
        </div>
      </SurfaceCard>
    </AsyncState>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { adminService } from '@/services/adminService'
import PageHeader from '@/components/admin/PageHeader.vue'
import SurfaceCard from '@/components/admin/SurfaceCard.vue'
import AsyncState from '@/components/admin/AsyncState.vue'

type EditableServer = {
  localKey: string
  id: string
  name: string
  env: string
  enabled: boolean
  base_url: string
  health_url: string
  metrics_url: string
  owner: string
  tagsText: string
}

const loading = ref(false)
const error = ref('')
const status = ref<Record<string, any>>({})
const monitoring = ref({
  enabled: true,
  prometheus_url: '',
  alertmanager_url: '',
  timeout_seconds: 5,
})
const probes = ref<Record<string, any>[]>([])
const servers = ref<EditableServer[]>([])
const savingMonitoring = ref(false)
const savingServers = ref(false)
const testingProbe = ref(false)
const probeResult = ref<Record<string, any> | null>(null)
const testProbe = ref({ name: '临时探测', url: '' })

function makeKey() {
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function toEditableServer(item: Record<string, any>): EditableServer {
  return {
    localKey: makeKey(),
    id: item.id || '',
    name: item.name || '',
    env: item.env || '',
    enabled: item.enabled !== false,
    base_url: item.base_url || item.baseUrl || '',
    health_url: item.health_url || item.healthUrl || '',
    metrics_url: item.metrics_url || item.metricsUrl || '',
    owner: item.owner || '',
    tagsText: Array.isArray(item.tags) ? item.tags.join(', ') : '',
  }
}

function serializeServer(item: EditableServer) {
  return {
    id: item.id,
    name: item.name,
    env: item.env,
    enabled: item.enabled,
    base_url: item.base_url,
    health_url: item.health_url,
    metrics_url: item.metrics_url,
    owner: item.owner,
    tags: item.tagsText
      .split(',')
      .map((tag) => tag.trim())
      .filter(Boolean),
  }
}

async function loadConfig() {
  loading.value = true
  error.value = ''
  try {
    const [statusData, serverData, monitoringData] = await Promise.all([
      adminService.projectConfigStatus(),
      adminService.projectConfigServers(),
      adminService.projectConfigMonitoring(),
    ])
    status.value = statusData || {}
    servers.value = Array.isArray(serverData.items) ? serverData.items.map(toEditableServer) : []
    const rawMonitoring = monitoringData.monitoring?.monitoring || monitoringData.monitoring || {}
    monitoring.value = {
      enabled: rawMonitoring.enabled !== false,
      prometheus_url: rawMonitoring.prometheus_url || '',
      alertmanager_url: rawMonitoring.alertmanager_url || '',
      timeout_seconds: Number(rawMonitoring.timeout_seconds || 5),
    }
    probes.value = Array.isArray(rawMonitoring.probes) ? rawMonitoring.probes : []
  } catch (err: any) {
    error.value = err?.detail || err?.message || '读取接入配置失败'
  } finally {
    loading.value = false
  }
}

function addServer() {
  servers.value.unshift(toEditableServer({
    enabled: true,
    env: 'prod',
  }))
}

function removeServer(index: number) {
  servers.value.splice(index, 1)
}

async function saveMonitoring() {
  savingMonitoring.value = true
  try {
    await adminService.saveProjectConfigMonitoring({
      monitoring: monitoring.value,
      probes: probes.value,
    })
    await loadConfig()
  } finally {
    savingMonitoring.value = false
  }
}

async function saveServers() {
  savingServers.value = true
  try {
    await adminService.saveProjectConfigServers({
      servers: servers.value.map(serializeServer),
    })
    await loadConfig()
  } finally {
    savingServers.value = false
  }
}

async function runProbeTest() {
  testingProbe.value = true
  probeResult.value = null
  try {
    probeResult.value = await adminService.projectConfigProbeTest(testProbe.value)
  } finally {
    testingProbe.value = false
  }
}

onMounted(loadConfig)
</script>

<style scoped>
.server-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.server-card {
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface-strong);
  padding: 18px;
}

.server-card-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
}

.form-wide {
  grid-column: 1 / -1;
}

@media (max-width: 720px) {
  .server-card-head {
    flex-direction: column;
  }

  .inline-actions {
    width: 100%;
  }

  .inline-actions .btn {
    flex: 1;
  }
}
</style>

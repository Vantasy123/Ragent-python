<template>
  <section class="monitoring-container">
    <PageHeader
      title="运维监控"
      eyebrow="后台运维"
      description="系统实时健康状态、资源水位、活跃告警及探针详情总览。"
    >
      <template #actions>
        <button class="btn btn-secondary" :disabled="loading" @click="loadAll">
          <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 mr-1.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 1121.21 8H17" />
          </svg>
          刷新数据
        </button>
      </template>
    </PageHeader>

    <div v-if="issueText" class="state-card state-card-danger mb-5 flex items-start gap-3">
      <span class="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-red-100 text-red-600 font-bold text-sm">!</span>
      <div>
        <div class="state-title text-red-800 font-bold">降级原因</div>
        <div class="state-description mt-1 text-red-700 text-sm">{{ issueText }}</div>
      </div>
    </div>

    <AsyncState :loading="loading" :error="error">
      <!-- Overview Cards -->
      <div class="dashboard-grid mb-5">
        <article class="metric-card">
          <div class="meta-label">系统状态</div>
          <div class="flex items-center gap-2 mt-3">
            <span :class="['status-badge', statusTheme(overview.status).class]">
              {{ statusTheme(overview.status).label }}
            </span>
          </div>
          <div class="page-description mt-2 text-xs truncate" :title="overview.summary">
            {{ overview.summary || '系统运行状态正常' }}
          </div>
        </article>

        <article class="metric-card">
          <div class="meta-label">活跃告警</div>
          <div class="metric-value">{{ alerts.length }}</div>
          <div class="metric-trend text-red-600 font-semibold" v-if="alerts.length > 0">触发警报中</div>
          <div class="metric-trend text-emerald-600 font-semibold" v-else>无活跃告警</div>
        </article>

        <article class="metric-card">
          <div class="meta-label">CPU 使用率</div>
          <div class="metric-value">{{ latestCpuValue.toFixed(1) }}%</div>
          <div class="metric-trend">主控核心水位</div>
        </article>

        <article class="metric-card">
          <div class="meta-label">内存使用率</div>
          <div class="metric-value">{{ latestMemoryValue.toFixed(1) }}%</div>
          <div class="metric-trend">动态物理占用</div>
        </article>
      </div>

      <!-- Mid Section: Sparkline Chart & Active Alerts -->
      <div class="grid-two mb-5">
        <SurfaceCard title="指标趋势" subtitle="实时查看 Prometheus 汇聚的资源趋势指标。">
          <template #actions>
            <div class="flex items-center gap-2">
              <select v-model="activeMetric" class="select select-compact max-w-[140px] !py-1 !px-2 text-xs" @change="loadSeries">
                <option value="cpu_percent">CPU 使用率</option>
                <option value="memory_percent">内存使用率</option>
                <option value="container_cpu">容器 CPU</option>
                <option value="container_memory">容器内存</option>
                <option value="probe_success">探测成功率</option>
              </select>
              <select v-model="minutes" class="select select-compact max-w-[90px] !py-1 !px-2 text-xs" @change="loadSeries">
                <option :value="15">15分钟</option>
                <option :value="30">30分钟</option>
                <option :value="60">1小时</option>
              </select>
            </div>
          </template>

          <div class="chart-container relative mt-4">
            <div v-if="loadingSeries" class="absolute inset-0 bg-white/70 backdrop-blur-xs flex items-center justify-center z-10 text-xs text-slate-500">
              加载趋势数据...
            </div>
            
            <div v-if="!seriesPoints.length && !loadingSeries" class="h-[200px] flex items-center justify-center text-slate-400 text-sm">
              暂无趋势数据
            </div>

            <svg 
              v-else 
              class="w-full h-[200px] overflow-visible select-none" 
              viewBox="0 0 500 200"
              preserveAspectRatio="none"
              @mousemove="handleMouseMove"
              @mouseleave="handleMouseLeave"
            >
              <defs>
                <linearGradient id="line-gradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stop-color="#2563eb" stop-opacity="0.22" />
                  <stop offset="100%" stop-color="#2563eb" stop-opacity="0" />
                </linearGradient>
              </defs>

              <!-- Grid horizontal lines -->
              <line x1="20" y1="20" x2="480" y2="20" stroke="#f1f5f9" stroke-width="1" />
              <line x1="20" y1="95" x2="480" y2="95" stroke="#f1f5f9" stroke-width="1" />
              <line x1="20" y1="170" x2="480" y2="170" stroke="#f1f5f9" stroke-width="1" />

              <!-- Fill Area -->
              <path :d="fillPath" fill="url(#line-gradient)" />

              <!-- Line Path -->
              <path :d="linePath" fill="none" stroke="#2563eb" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" />

              <!-- Hover elements -->
              <g v-if="hoverIndex !== null">
                <!-- Vertical tracker line -->
                <line :x1="hoverX" y1="20" :x2="hoverX" y2="170" stroke="#cbd5e1" stroke-width="1" stroke-dasharray="4 4" />
                <!-- Dot on the line -->
                <circle :cx="hoverX" :cy="hoverY" r="5.5" fill="#2563eb" stroke="#ffffff" stroke-width="2" />
              </g>
            </svg>

            <!-- Chart Hover Tooltip -->
            <div 
              v-if="hoverPoint" 
              class="absolute z-20 bg-slate-800 text-white rounded-lg p-2 text-xs shadow-lg pointer-events-none transition-all duration-75"
              :style="{ left: hoverTooltipPos.x + 'px', top: hoverTooltipPos.y + 'px' }"
            >
              <div class="font-semibold text-[10px] text-slate-300">{{ formatTime(hoverPoint.timestamp) }}</div>
              <div class="mt-0.5 font-bold text-sm">{{ hoverPoint.value.toFixed(2) }}{{ activeMetric.includes('percent') || activeMetric.includes('success') ? '%' : '' }}</div>
            </div>
            
            <!-- Chart X labels -->
            <div class="flex justify-between text-[10px] text-slate-400 mt-1 px-4">
              <span>{{ formatTime(chartBounds?.minTime) }}</span>
              <span>{{ formatTime(chartBounds?.maxTime) }}</span>
            </div>
          </div>
        </SurfaceCard>

        <SurfaceCard title="活跃告警列表" subtitle="Alertmanager 捕获的正在触发中的系统告警。">
          <div class="overflow-y-auto max-h-[250px] pr-1">
            <div v-if="!alerts.length" class="h-[200px] flex items-center justify-center text-slate-400 text-sm">
              当前没有正在活动的报警
            </div>
            <div v-else class="list-stack">
              <article v-for="(alert, idx) in alerts" :key="idx" class="resource-item !p-3">
                <div class="flex items-center justify-between gap-3">
                  <div class="font-bold text-slate-800 text-sm">{{ alert.displayName || alert.name }}</div>
                  <span :class="['pill', alertSeverityTheme(alert.severityLabel || alert.severity).class]">
                    {{ alert.severityLabel || alert.severity || '一般' }}
                  </span>
                </div>
                <div class="text-xs text-slate-500 mt-2 leading-relaxed">{{ alert.summary || '无告警摘要详情' }}</div>
                <div class="text-[10px] text-slate-400 mt-2 flex justify-between">
                  <span>触发时间: {{ formatDateTime(alert.startsAt) }}</span>
                </div>
              </article>
            </div>
          </div>
        </SurfaceCard>
      </div>

      <!-- Lower Tables -->
      <div class="flex flex-col gap-5 mb-5">
        <SurfaceCard title="服务探测" subtitle="外部 HTTP 探针对主要端点进行健康度诊断的数据。">
          <div class="table-wrap max-h-[300px]">
            <table class="data-table">
              <thead>
                <tr>
                  <th>服务名称</th>
                  <th>运行状态</th>
                  <th>状态码</th>
                  <th>响应时间</th>
                  <th>探测结果</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="srv in probes" :key="srv.key || srv.displayName">
                  <td class="font-bold text-slate-800">{{ srv.displayName }}</td>
                  <td>
                    <span :class="['pill', probeStatusTheme(srv.statusLabel || srv.status).class]">
                      {{ srv.statusLabel || srv.status || '未知' }}
                    </span>
                  </td>
                  <td class="font-mono text-xs">{{ srv.statusCode || '-' }}</td>
                  <td class="font-mono text-xs">{{ srv.durationMs !== null && srv.durationMs !== undefined ? Number(srv.durationMs).toFixed(0) + ' ms' : '-' }}</td>
                  <td class="text-slate-500 text-xs truncate max-w-[200px]" :title="srv.message">{{ srv.message || '-' }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </SurfaceCard>

        <SurfaceCard title="采集目标 (Targets)" subtitle="Prometheus 采集各个主机的 exporter 存活状态。">
          <div class="table-wrap max-h-[300px]">
            <table class="data-table">
              <thead>
                <tr>
                  <th>任务 (Job)</th>
                  <th>实例 (Instance)</th>
                  <th>状态</th>
                  <th>最近采集</th>
                  <th>最近错误</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="tgt in targets" :key="tgt.instance">
                  <td class="font-bold text-slate-800 text-xs">{{ tgt.job }}</td>
                  <td class="font-mono text-xs text-slate-600">{{ tgt.instance }}</td>
                  <td>
                    <span :class="['pill', targetStatusClass(tgt)]">
                      {{ tgt.statusLabel || tgt.status || 'unknown' }}
                    </span>
                  </td>
                  <td class="font-mono text-[10px] text-slate-500">{{ formatDateTime(tgt.lastScrape) }}</td>
                  <td class="text-red-600 text-xs truncate max-w-[150px]" :title="tgt.lastError">{{ tgt.lastError || '-' }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </SurfaceCard>
      </div>

      <!-- PromQL Terminal Tool -->
      <SurfaceCard compact class="mb-5 border-slate-200 bg-slate-50/50">
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-2">
            <svg xmlns="http://www.w3.org/2000/svg" class="h-4.5 w-4.5 text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
              <path stroke-linecap="round" stroke-linejoin="round" d="M8 9l3 3-3 3m5 0h3M5 20h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
            </svg>
            <span class="text-sm font-bold text-slate-700">PromQL 调试工具</span>
          </div>
          <button class="btn btn-ghost !py-1 !px-2.5 text-xs font-semibold" @click="showQueryTerminal = !showQueryTerminal">
            {{ showQueryTerminal ? '收起终端' : '展开终端' }}
          </button>
        </div>

        <div v-if="showQueryTerminal" class="mt-4 border-t border-slate-200/80 pt-4">
          <form class="flex gap-2" @submit.prevent="runQuery">
            <input 
              v-model="promqlQuery" 
              class="input font-mono text-sm border-slate-300 focus:border-blue-500" 
              placeholder="输入 PromQL 语句进行查询，例如: up 或 cpu_percent"
            />
            <button class="btn btn-primary min-w-[80px]" :disabled="queryLoading" type="submit">
              {{ queryLoading ? '查询中' : '执行' }}
            </button>
          </form>

          <div v-if="queryError" class="mt-3 bg-amber-50 border border-amber-200 text-amber-800 rounded-lg p-3 text-xs leading-relaxed">
            <span class="font-bold">查询降级/错误提示:</span> {{ queryError }}
          </div>

          <div v-if="queryResult" class="mt-3">
            <div class="text-[10px] text-slate-400 font-semibold mb-1">执行结果 JSON:</div>
            <DataPreview class="font-mono text-xs max-h-[300px] overflow-auto" :data="queryResult" />
          </div>
        </div>
      </SurfaceCard>
    </AsyncState>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { adminService } from '@/services/adminService'
import PageHeader from '@/components/admin/PageHeader.vue'
import SurfaceCard from '@/components/admin/SurfaceCard.vue'
import AsyncState from '@/components/admin/AsyncState.vue'
import DataPreview from '@/components/admin/DataPreview.vue'

interface DataPoint {
  timestamp: string | number
  value: number
}

// Global state
const loading = ref(false)
const error = ref('')
const overview = ref<Record<string, any>>({})
const targets = ref<any[]>([])
const alerts = ref<any[]>([])
const probes = ref<any[]>([])

// Metric trend states
const activeMetric = ref('cpu_percent')
const minutes = ref(30)
const seriesPoints = ref<DataPoint[]>([])
const loadingSeries = ref(false)

// PromQL Terminal states
const showQueryTerminal = ref(false)
const promqlQuery = ref('up')
const queryResult = ref<any>(null)
const queryLoading = ref(false)
const queryError = ref('')

// Chart hover states
const hoverIndex = ref<number | null>(null)
const hoverX = ref(0)
const hoverY = ref(0)
const hoverPoint = ref<DataPoint | null>(null)
const hoverContainerPos = ref({ x: 0, y: 0 })

// Compute latest metric values for summary cards
const latestCpuValue = computed(() => {
  const card = Array.isArray(overview.value.cards)
    ? overview.value.cards.find((item: any) => item.key === 'cpuPercent')
    : null
  if (card?.value !== undefined) return Number(card.value)
  if (overview.value.metrics?.cpuPercent?.data?.value !== undefined) return Number(overview.value.metrics.cpuPercent.data.value)
  return 0
})

const latestMemoryValue = computed(() => {
  const card = Array.isArray(overview.value.cards)
    ? overview.value.cards.find((item: any) => item.key === 'memoryPercent')
    : null
  if (card?.value !== undefined) return Number(card.value)
  if (overview.value.metrics?.memoryPercent?.data?.value !== undefined) return Number(overview.value.metrics.memoryPercent.data.value)
  return 0
})

const issueText = computed(() => {
  const items = overview.value.issues
  if (!Array.isArray(items) || !items.length) return ''
  return items.map((item: any) => `${item.来源 || item.source || '监控源'}：${item.原因 || item.reason || item.summary || ''}`).join('；')
})

// Custom Sparkline chart metrics calculations
const chartBounds = computed(() => {
  const pts = seriesPoints.value
  if (!pts.length) return null

  const times = pts.map(p => timestampMs(p.timestamp))
  const vals = pts.map(p => p.value)

  const minTime = Math.min(...times)
  const maxTime = Math.max(...times)
  const minVal = Math.min(...vals)
  const maxVal = Math.max(...vals)

  const yMin = 0
  const yMax = maxVal === yMin ? yMin + 100 : maxVal * 1.15

  return { minTime, maxTime, yMin, yMax }
})

const chartPoints = computed(() => {
  const bounds = chartBounds.value
  if (!bounds || !seriesPoints.value.length) return []

  const { minTime, maxTime, yMin, yMax } = bounds
  const width = 460
  const height = 150
  const paddingX = 20
  const paddingY = 20

  return seriesPoints.value.map(p => {
    const t = timestampMs(p.timestamp)
    const x = bounds.maxTime === bounds.minTime
      ? width / 2 + paddingX
      : ((t - minTime) / (maxTime - minTime)) * width + paddingX

    const y = bounds.yMax === bounds.yMin
      ? height / 2 + paddingY
      : height + paddingY - ((p.value - yMin) / (yMax - yMin)) * height

    return { x, y, raw: p }
  })
})

const linePath = computed(() => {
  const pts = chartPoints.value
  if (!pts.length) return ''
  return pts.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(' ')
})

const fillPath = computed(() => {
  const pts = chartPoints.value
  if (!pts.length) return ''
  const first = pts[0]
  const last = pts[pts.length - 1]
  const baseLine = 170
  return `${linePath.value} L ${last.x.toFixed(1)} ${baseLine} L ${first.x.toFixed(1)} ${baseLine} Z`
})

// Calculate tooltip absolute position over chart area
const hoverTooltipPos = computed(() => {
  return {
    x: hoverX.value + 10,
    y: hoverY.value - 40
  }
})

// Hover interaction handlers
function handleMouseMove(e: MouseEvent) {
  const svg = e.currentTarget as SVGSVGElement
  const rect = svg.getBoundingClientRect()
  const mouseX = e.clientX - rect.left
  const svgX = (mouseX / rect.width) * 500

  const pts = chartPoints.value
  if (!pts.length) return

  let closestIndex = 0
  let minDiff = Infinity
  for (let i = 0; i < pts.length; i++) {
    const diff = Math.abs(pts[i].x - svgX)
    if (diff < minDiff) {
      minDiff = diff
      closestIndex = i
    }
  }

  hoverIndex.value = closestIndex
  hoverX.value = pts[closestIndex].x
  hoverY.value = pts[closestIndex].y
  hoverPoint.value = pts[closestIndex].raw
}

function handleMouseLeave() {
  hoverIndex.value = null
  hoverPoint.value = null
}

// Load data
async function loadAll() {
  loading.value = true
  error.value = ''
  try {
    const [overviewData, targetsData, alertsData, probesData] = await Promise.all([
      adminService.monitoringOverview(),
      adminService.monitoringTargets(),
      adminService.monitoringAlerts(),
      adminService.monitoringProbes()
    ])
    overview.value = overviewData
    targets.value = targetsData
    alerts.value = alertsData
    probes.value = probesData
    
    await loadSeries()
  } catch (err: any) {
    error.value = err?.detail || err?.message || '加载监控数据失败'
  } finally {
    loading.value = false
  }
}

async function loadSeries() {
  loadingSeries.value = true
  try {
    const response = await adminService.monitoringSeries(activeMetric.value, minutes.value)
    seriesPoints.value = Array.isArray(response.data?.points)
      ? response.data.points
      : (Array.isArray(response.points) ? response.points : [])
  } catch (err: any) {
    console.error('Failed to load metric series', err)
  } finally {
    loadingSeries.value = false
  }
}

async function runQuery() {
  if (!promqlQuery.value.trim()) return
  queryLoading.value = true
  queryError.value = ''
  queryResult.value = null
  try {
    const response = await adminService.monitoringQuery({
      query: promqlQuery.value,
      time: null
    })
    if (response.status === 'degraded') {
      queryError.value = response.summary || '查询受限或被拦截'
    }
    queryResult.value = response
  } catch (err: any) {
    queryError.value = err?.detail || err?.message || '执行 PromQL 查询失败'
  } finally {
    queryLoading.value = false
  }
}

// Utility styling functions
function statusTheme(status?: string) {
  switch (status) {
    case 'healthy':
      return { class: 'status-badge-success', label: '正常' }
    case 'degraded':
      return { class: 'status-badge-warning', label: '降级' }
    case 'critical':
      return { class: 'status-badge-danger', label: '异常' }
    default:
      return { class: 'status-badge-neutral', label: '未知' }
  }
}

function alertSeverityTheme(severity?: string) {
  const clean = String(severity || '').toLowerCase()
  if (clean.includes('crit') || clean.includes('high')) {
    return { class: 'status-badge-danger' }
  }
  if (clean.includes('warn') || clean.includes('med')) {
    return { class: 'status-badge-warning' }
  }
  return { class: 'status-badge-neutral' }
}

function probeStatusTheme(status?: string) {
  const clean = String(status || '').toLowerCase()
  if (clean.includes('healthy') || clean.includes('ok') || clean.includes('success')) {
    return { class: 'status-badge-success' }
  }
  if (clean.includes('degrad') || clean.includes('warn')) {
    return { class: 'status-badge-warning' }
  }
  return { class: 'status-badge-danger' }
}

function targetStatusClass(target: any) {
  const text = `${target?.statusLabel || ''} ${target?.status || ''}`.toLowerCase()
  if (text.includes('正常') || text.includes('healthy') || text.includes('up')) return 'status-badge-success'
  if (text.includes('降级') || text.includes('degraded')) return 'status-badge-warning'
  return 'status-badge-danger'
}

// Date helpers
function timestampMs(raw?: string | number) {
  if (raw === null || raw === undefined || raw === '') return 0
  if (typeof raw === 'number') return raw < 1000000000000 ? raw * 1000 : raw
  const numeric = Number(raw)
  if (!Number.isNaN(numeric)) return numeric < 1000000000000 ? numeric * 1000 : numeric
  return new Date(raw).getTime()
}

function formatDateTime(str?: string) {
  if (!str) return '-'
  const d = new Date(str)
  if (isNaN(d.getTime())) return str
  return d.toLocaleString('zh-CN', { hour12: false })
}

function formatTime(str?: string | number) {
  if (!str) return ''
  const d = new Date(timestampMs(str))
  if (isNaN(d.getTime())) return ''
  return d.toLocaleTimeString('zh-CN', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

onMounted(loadAll)
</script>

<style scoped>
.monitoring-container {
  max-width: 100%;
}
.chart-container {
  background: rgba(255, 255, 255, 0.5);
  border-radius: var(--radius-lg);
  border: 1px solid var(--border);
  padding: 12px;
}
.select-compact {
  height: 28px;
  line-height: 28px;
  border-radius: 6px;
}
</style>

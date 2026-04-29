import apiClient from './api'
import { unwrapData } from './result'

export type OpsAgentEvent = {
  type: string
  channel?: 'ops'
  runId?: string
  traceId?: string
  approvalId?: string
  agent?: string
  tool?: string
  args?: Record<string, unknown>
  content?: string
  message?: string
  status?: string
  riskLevel?: string
  subTasks?: Array<Record<string, unknown>>
  steps?: Array<Record<string, unknown>>
  result?: Record<string, unknown>
  memory?: Array<Record<string, unknown>> | Record<string, unknown>
  report?: string
  durationMs?: number
}

export const AGENT_THEME: Record<string, { color: string; label: string; icon: string }> = {
  orchestrator: { color: '#2563eb', label: '编排智能体', icon: '控' },
  diagnostics: { color: '#16a34a', label: '诊断智能体', icon: '诊' },
  monitor: { color: '#ea580c', label: '监控智能体', icon: '监' },
  executor: { color: '#dc2626', label: '执行智能体', icon: '执' },
  knowledge: { color: '#7c3aed', label: '知识智能体', icon: '知' },
}

export async function streamOpsAgent(
  payload: { message: string; conversationId?: string; autoExecuteReadOnly?: boolean },
  onEvent: (event: OpsAgentEvent) => void,
) {
  const token = localStorage.getItem('ragent_token')
  const response = await fetch('/api/agent/ops/chat', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(payload),
  })

  if (!response.ok || !response.body) {
    throw new Error(`运维 Agent 请求失败：${response.status}`)
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''

  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const frames = buffer.split('\n\n')
    buffer = frames.pop() || ''

    for (const frame of frames) {
      const line = frame
        .split('\n')
        .find((item) => item.startsWith('data: '))
      if (!line) continue
      onEvent(JSON.parse(line.slice(6)))
    }
  }
}

export const opsAgentService = {
  async tools() {
    return unwrapData(await apiClient.get('/agent/ops/tools'), [])
  },
  async agents() {
    return unwrapData(await apiClient.get('/agent/ops/agents'), {})
  },
  async run(runId: string) {
    return unwrapData(await apiClient.get(`/agent/ops/runs/${runId}`), {})
  },
  async approve(runId: string, payload: { approvalId: string; approved: boolean; comment?: string }) {
    return unwrapData(await apiClient.post(`/agent/ops/runs/${runId}/approve`, payload), {})
  },
  async stop(runId: string) {
    return unwrapData(await apiClient.post(`/agent/ops/runs/${runId}/stop`), {})
  },
}

import apiClient from './api'
import { toArrayResult, toTablePageResult, unwrapData } from './result'

function normalizeIntent(item: Record<string, any>) {
  return {
    ...item,
    parentId: item.parentId ?? item.parent_id ?? null,
    kbId: item.kbId ?? item.kb_id ?? null,
  }
}

function normalizeSample(item: Record<string, any>) {
  return {
    ...item,
    sortOrder: item.sortOrder ?? item.sort_order ?? 0,
  }
}

function normalizeMapping(item: Record<string, any>) {
  return {
    ...item,
    sourceTerm: item.sourceTerm ?? item.source_term ?? '',
    targetTerm: item.targetTerm ?? item.target_term ?? '',
  }
}

export const adminService = {
  async overview() {
    return unwrapData(await apiClient.get('/admin/dashboard/overview'), {})
  },
  async performance() {
    return unwrapData(await apiClient.get('/admin/dashboard/performance'), {})
  },
  async trends() {
    return unwrapData(await apiClient.get('/admin/dashboard/trends'), {})
  },
  async settings() {
    return unwrapData(await apiClient.get('/rag/settings'), {})
  },
  async updateSettings(payload: Record<string, unknown>) {
    return unwrapData(await apiClient.put('/rag/settings', payload), {})
  },
  async traces(pageNo = 1, pageSize = 20) {
    return toTablePageResult(await apiClient.get(`/rag/traces/runs?pageNo=${pageNo}&pageSize=${pageSize}`))
  },
  async traceDetail(traceId: string) {
    return unwrapData(await apiClient.get(`/rag/traces/runs/${traceId}`), {})
  },
  async traceNodes(traceId: string) {
    return toArrayResult(await apiClient.get(`/rag/traces/runs/${traceId}/nodes`))
  },
  async evaluationOverview() {
    return unwrapData(await apiClient.get('/admin/evaluations/overview'), {})
  },
  async evaluationRuns(pageNo = 1, pageSize = 50) {
    return toTablePageResult(await apiClient.get(`/admin/evaluations/runs?pageNo=${pageNo}&pageSize=${pageSize}`))
  },
  async evaluationRun(runId: string) {
    return unwrapData(await apiClient.get(`/admin/evaluations/runs/${runId}`), {})
  },
  async evaluateTrace(traceId: string) {
    return unwrapData(await apiClient.post(`/admin/evaluations/runs/${traceId}/evaluate`), {})
  },
  async evaluationIssues(pageNo = 1, pageSize = 50, severity = '') {
    const suffix = severity ? `&severity=${encodeURIComponent(severity)}` : ''
    return toTablePageResult(await apiClient.get(`/admin/evaluations/issues?pageNo=${pageNo}&pageSize=${pageSize}${suffix}`))
  },
  async users(pageNo = 1, pageSize = 100) {
    return toTablePageResult(await apiClient.get(`/users?pageNo=${pageNo}&pageSize=${pageSize}`))
  },
  createUser(payload: Record<string, unknown>) {
    return apiClient.post('/users', payload)
  },
  updateUser(userId: string, payload: Record<string, unknown>) {
    return apiClient.put(`/users/${userId}`, payload)
  },
  deleteUser(userId: string) {
    return apiClient.delete(`/users/${userId}`)
  },
  changePassword(payload: { password: string }) {
    return apiClient.put('/user/password', payload)
  },
  async pipelines(pageNo = 1, pageSize = 100) {
    return toTablePageResult(await apiClient.get(`/ingestion/pipelines?pageNo=${pageNo}&pageSize=${pageSize}`))
  },
  async pipelineDetail(pipelineId: string) {
    return unwrapData(await apiClient.get(`/ingestion/pipelines/${pipelineId}`), {})
  },
  createPipeline(payload: Record<string, unknown>) {
    return apiClient.post('/ingestion/pipelines', payload)
  },
  updatePipeline(pipelineId: string, payload: Record<string, unknown>) {
    return apiClient.put(`/ingestion/pipelines/${pipelineId}`, payload)
  },
  deletePipeline(pipelineId: string) {
    return apiClient.delete(`/ingestion/pipelines/${pipelineId}`)
  },
  async tasks(pageNo = 1, pageSize = 100) {
    return toTablePageResult(await apiClient.get(`/ingestion/tasks?pageNo=${pageNo}&pageSize=${pageSize}`))
  },
  createTask(payload: Record<string, unknown>) {
    return apiClient.post('/ingestion/tasks', payload)
  },
  async taskDetail(taskId: string) {
    return unwrapData(await apiClient.get(`/ingestion/tasks/${taskId}`), {})
  },
  async taskNodes(taskId: string) {
    return toArrayResult(await apiClient.get(`/ingestion/tasks/${taskId}/nodes`))
  },
  async intents() {
    return toArrayResult(await apiClient.get('/intent-tree/trees')).map((item: any) => normalizeIntent(item))
  },
  async intentDetail(itemId: string) {
    return normalizeIntent(unwrapData(await apiClient.get(`/intent-tree/${itemId}`), {}))
  },
  createIntent(payload: Record<string, unknown>) {
    return apiClient.post('/intent-tree', payload)
  },
  updateIntent(itemId: string, payload: Record<string, unknown>) {
    return apiClient.put(`/intent-tree/${itemId}`, payload)
  },
  deleteIntent(itemId: string) {
    return apiClient.delete(`/intent-tree/${itemId}`)
  },
  async samples() {
    return toArrayResult(await apiClient.get('/sample-questions')).map((item: any) => normalizeSample(item))
  },
  async sampleDetail(itemId: string) {
    return normalizeSample(unwrapData(await apiClient.get(`/sample-questions/${itemId}`), {}))
  },
  createSample(payload: Record<string, unknown>) {
    return apiClient.post('/sample-questions', payload)
  },
  updateSample(itemId: string, payload: Record<string, unknown>) {
    return apiClient.put(`/sample-questions/${itemId}`, payload)
  },
  deleteSample(itemId: string) {
    return apiClient.delete(`/sample-questions/${itemId}`)
  },
  async mappings() {
    return toArrayResult(await apiClient.get('/mappings')).map((item: any) => normalizeMapping(item))
  },
  async mappingDetail(itemId: string) {
    return normalizeMapping(unwrapData(await apiClient.get(`/mappings/${itemId}`), {}))
  },
  createMapping(payload: Record<string, unknown>) {
    return apiClient.post('/mappings', payload)
  },
  updateMapping(itemId: string, payload: Record<string, unknown>) {
    return apiClient.put(`/mappings/${itemId}`, payload)
  },
  deleteMapping(itemId: string) {
    return apiClient.delete(`/mappings/${itemId}`)
  },
}

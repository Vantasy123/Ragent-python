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

function nestedItems(payload: any) {
  const data = unwrapData<any>(payload, {})
  if (Array.isArray(data)) return data
  if (Array.isArray(data.items)) return data.items
  if (Array.isArray(data.data?.items)) return data.data.items
  return []
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
  async evaluationDatasets(pageNo = 1, pageSize = 20) {
    return toTablePageResult(await apiClient.get(`/admin/evaluations/datasets?pageNo=${pageNo}&pageSize=${pageSize}`))
  },
  async evaluationDataset(datasetId: string) {
    return unwrapData(await apiClient.get(`/admin/evaluations/datasets/${datasetId}`), {})
  },
  createEvaluationDataset(payload: Record<string, unknown>) {
    return apiClient.post('/admin/evaluations/datasets', payload)
  },
  updateEvaluationDataset(datasetId: string, payload: Record<string, unknown>) {
    return apiClient.put(`/admin/evaluations/datasets/${datasetId}`, payload)
  },
  deleteEvaluationDataset(datasetId: string) {
    return apiClient.delete(`/admin/evaluations/datasets/${datasetId}`)
  },
  async evaluationCases(datasetId: string, pageNo = 1, pageSize = 100) {
    return toTablePageResult(await apiClient.get(`/admin/evaluations/datasets/${datasetId}/cases?pageNo=${pageNo}&pageSize=${pageSize}`))
  },
  createEvaluationCase(datasetId: string, payload: Record<string, unknown>) {
    return apiClient.post(`/admin/evaluations/datasets/${datasetId}/cases`, payload)
  },
  updateEvaluationCase(caseId: string, payload: Record<string, unknown>) {
    return apiClient.put(`/admin/evaluations/cases/${caseId}`, payload)
  },
  deleteEvaluationCase(caseId: string) {
    return apiClient.delete(`/admin/evaluations/cases/${caseId}`)
  },
  importEvaluationCases(datasetId: string, payload: Record<string, unknown>) {
    return apiClient.post(`/admin/evaluations/datasets/${datasetId}/cases/import`, payload)
  },
  async createEvaluationBatchRun(datasetId: string) {
    return unwrapData(await apiClient.post(`/admin/evaluations/datasets/${datasetId}/runs`), {})
  },
  async evaluationBatchRuns(datasetId = '', pageNo = 1, pageSize = 20) {
    const suffix = datasetId ? `&datasetId=${encodeURIComponent(datasetId)}` : ''
    return toTablePageResult(await apiClient.get(`/admin/evaluations/batch-runs?pageNo=${pageNo}&pageSize=${pageSize}${suffix}`))
  },
  async evaluationBatchRun(batchId: string) {
    return unwrapData(await apiClient.get(`/admin/evaluations/batch-runs/${batchId}`), {})
  },
  async evaluationCaseResults(batchId: string, pageNo = 1, pageSize = 100) {
    return toTablePageResult(await apiClient.get(`/admin/evaluations/batch-runs/${batchId}/results?pageNo=${pageNo}&pageSize=${pageSize}`))
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
    return toArrayResult(await apiClient.get('/intent-tree')).map((item: any) => normalizeIntent(item))
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
  async monitoringOverview() {
    return unwrapData(await apiClient.get('/admin/monitoring/overview'), {})
  },
  async monitoringTargets() {
    return nestedItems(await apiClient.get('/admin/monitoring/targets'))
  },
  async monitoringAlerts() {
    return nestedItems(await apiClient.get('/admin/monitoring/alerts'))
  },
  async monitoringSeries(metric: string, minutes = 30) {
    return unwrapData(await apiClient.get(`/admin/monitoring/series/${metric}?minutes=${minutes}`), {})
  },
  async monitoringProbes() {
    return nestedItems(await apiClient.get('/admin/monitoring/probes'))
  },
  async monitoringQuery(payload: { query: string, time: string | null }) {
    return unwrapData(await apiClient.post('/admin/monitoring/query', payload), {})
  },
  async projectConfigStatus() {
    return unwrapData(await apiClient.get('/admin/project-config/status'), {})
  },
  async projectConfigServers() {
    return unwrapData(await apiClient.get('/admin/project-config/servers'), {})
  },
  async saveProjectConfigServers(payload: { servers: Record<string, unknown>[] }) {
    return unwrapData(await apiClient.put('/admin/project-config/servers', payload), {})
  },
  async projectConfigMonitoring() {
    return unwrapData(await apiClient.get('/admin/project-config/monitoring'), {})
  },
  async saveProjectConfigMonitoring(payload: { monitoring: Record<string, unknown>, probes: Record<string, unknown>[] }) {
    return unwrapData(await apiClient.put('/admin/project-config/monitoring', payload), {})
  },
  async projectConfigProbeTest(payload: { name: string, url: string }) {
    return unwrapData(await apiClient.post('/admin/project-config/probe-test', payload), {})
  },
}

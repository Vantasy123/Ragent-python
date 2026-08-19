import apiClient from './api'
import { toArrayResult, toTablePageResult, unwrapData } from './result'

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
  async settingAuditLogs(pageNo = 1, pageSize = 10, key = '') {
    const suffix = key ? `&key=${encodeURIComponent(key)}` : ''
    return toTablePageResult(await apiClient.get(`/rag/settings/audit?pageNo=${pageNo}&pageSize=${pageSize}${suffix}`))
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
  async openAIEvalsPreview(batchId: string) {
    return unwrapData(await apiClient.get(`/admin/evaluations/batch-runs/${batchId}/openai-evals/preview`), {})
  },
  async startOpenAIEvals(batchId: string) {
    return unwrapData(await apiClient.post(`/admin/evaluations/batch-runs/${batchId}/openai-evals/start`), {})
  },
  async syncOpenAIEvals(batchId: string) {
    return unwrapData(await apiClient.post(`/admin/evaluations/batch-runs/${batchId}/openai-evals/sync`), {})
  },
  async users(pageNo = 1, pageSize = 100) {
    return toTablePageResult(await apiClient.get(`/users?pageNo=${pageNo}&pageSize=${pageSize}`))
  },
  async userAuditLogs(pageNo = 1, pageSize = 10, targetUserId = '', action = '') {
    const params = new URLSearchParams({
      pageNo: String(pageNo),
      pageSize: String(pageSize),
    })
    if (targetUserId) params.set('targetUserId', targetUserId)
    if (action) params.set('action', action)
    return toTablePageResult(await apiClient.get(`/users/audit?${params.toString()}`))
  },
  async securityAuditEvents(pageNo = 1, pageSize = 10, category = '', action = '', targetType = '', targetId = '') {
    const params = new URLSearchParams({
      pageNo: String(pageNo),
      pageSize: String(pageSize),
    })
    if (category) params.set('category', category)
    if (action) params.set('action', action)
    if (targetType) params.set('targetType', targetType)
    if (targetId) params.set('targetId', targetId)
    return toTablePageResult(await apiClient.get(`/admin/security-audit/events?${params.toString()}`))
  },
  async recordSecurityAuditEvent(payload: Record<string, unknown>) {
    return unwrapData(await apiClient.post('/admin/security-audit/events', payload), {})
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
  async projectConfigStatus() {
    return unwrapData(await apiClient.get('/admin/project-config/status'), {})
  },
  async projectConfigServers() {
    return unwrapData(await apiClient.get('/admin/project-config/servers'), {})
  },
  async saveProjectConfigServers(payload: { servers: Record<string, unknown>[] }) {
    return unwrapData(await apiClient.put('/admin/project-config/servers', payload), {})
  },
}

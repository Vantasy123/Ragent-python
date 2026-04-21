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
  async traces() {
    return toArrayResult(await apiClient.get('/rag/traces/runs'))
  },
  async traceDetail(traceId: string) {
    return unwrapData(await apiClient.get(`/rag/traces/runs/${traceId}`), {})
  },
  async traceNodes(traceId: string) {
    return toArrayResult(await apiClient.get(`/rag/traces/runs/${traceId}/nodes`))
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
    return toArrayResult(await apiClient.get('/intent-tree/trees'))
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
    return toArrayResult(await apiClient.get('/sample-questions'))
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
    return toArrayResult(await apiClient.get('/mappings'))
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

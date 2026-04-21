import apiClient from './api'
import { toArrayResult, toTablePageResult, unwrapData } from './result'

export const knowledgeService = {
  async listKnowledgeBases(pageNo = 1, pageSize = 100) {
    return toTablePageResult(await apiClient.get(`/knowledge-base?pageNo=${pageNo}&pageSize=${pageSize}`))
  },
  createKnowledgeBase(payload: { name: string; description: string }) {
    return apiClient.post('/knowledge-base', payload)
  },
  updateKnowledgeBase(id: string, payload: { name: string; description: string }) {
    return apiClient.put(`/knowledge-base/${id}`, payload)
  },
  deleteKnowledgeBase(id: string) {
    return apiClient.delete(`/knowledge-base/${id}`)
  },
  async getKnowledgeBase(id: string) {
    return unwrapData(await apiClient.get(`/knowledge-base/${id}`), {})
  },
  async chunkStrategies() {
    return toArrayResult(await apiClient.get('/knowledge-base/chunk-strategies'))
  },
  async listDocuments(kbId: string, keyword = '', pageNo = 1, pageSize = 100) {
    const search = keyword ? `&keyword=${encodeURIComponent(keyword)}` : ''
    return toTablePageResult(await apiClient.get(`/knowledge-base/${kbId}/docs?pageNo=${pageNo}&pageSize=${pageSize}${search}`))
  },
  async searchDocuments(keyword: string) {
    return toArrayResult(await apiClient.get(`/knowledge-base/docs/search?keyword=${encodeURIComponent(keyword)}`))
  },
  uploadDocument(kbId: string, file: File) {
    const formData = new FormData()
    formData.append('file', file)
    formData.append('chunkStrategy', 'recursive')
    formData.append('chunkSize', '500')
    formData.append('chunkOverlap', '50')
    return apiClient.post(`/knowledge-base/${kbId}/docs/upload`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
  startChunk(docId: string) {
    return apiClient.post(`/knowledge-base/docs/${docId}/chunk`)
  },
  async getDocument(docId: string) {
    return unwrapData(await apiClient.get(`/knowledge-base/docs/${docId}`), {})
  },
  updateDocument(docId: string, payload: Record<string, unknown>) {
    return apiClient.put(`/knowledge-base/docs/${docId}`, payload)
  },
  deleteDocument(docId: string) {
    return apiClient.delete(`/knowledge-base/docs/${docId}`)
  },
  setDocumentEnabled(docId: string, value: boolean) {
    return apiClient.patch(`/knowledge-base/docs/${docId}/enable?value=${value}`)
  },
  async listChunks(docId: string, pageNo = 1, pageSize = 100) {
    return toTablePageResult(await apiClient.get(`/knowledge-base/docs/${docId}/chunks?pageNo=${pageNo}&pageSize=${pageSize}`))
  },
  async chunkLogs(docId: string) {
    return toArrayResult(await apiClient.get(`/knowledge-base/docs/${docId}/chunk-logs`))
  },
  createChunk(docId: string, payload: Record<string, unknown>) {
    return apiClient.post(`/knowledge-base/docs/${docId}/chunks`, payload)
  },
  updateChunk(docId: string, chunkId: string, payload: Record<string, unknown>) {
    return apiClient.put(`/knowledge-base/docs/${docId}/chunks/${chunkId}`, payload)
  },
  deleteChunk(docId: string, chunkId: string) {
    return apiClient.delete(`/knowledge-base/docs/${docId}/chunks/${chunkId}`)
  },
  batchEnableChunks(docId: string, chunkIds: string[], enabled: boolean) {
    return apiClient.post(`/knowledge-base/docs/${docId}/chunks/batch-enable`, { chunkIds, enabled })
  },
  rebuildChunks(docId: string) {
    return apiClient.post(`/knowledge-base/docs/${docId}/chunks/rebuild`)
  },
}

import apiClient from './api'
import { toArrayResult } from './result'

export type ChatMode = 'auto' | 'rag' | 'job'

export interface ConversationSummary {
  id: string
  title?: string
  updatedAt?: string
  createdAt?: string
  messageCount?: number
}

export interface ChatMessageDTO {
  id?: string
  role: string
  content: string
  metadata?: Record<string, unknown>
}

export interface ChatAttachment {
  filename: string
  file_type: string
  file_size: number
  char_count: number
  text: string
  summary: string
}

export interface ModelOption {
  id: string
  name: string
  provider: string
  category: string
  tag: string
  description: string
  pricingTag: string
  inputPrice: number
  outputPrice: number
  isRecommended?: boolean
  isDefault?: boolean
}

export interface UnifiedChatPayload {
  message: string
  mode: ChatMode
  conversationId?: string
  deepThinking?: boolean
  attachments?: ChatAttachment[]
  model?: string
}

export async function listAvailableModels(): Promise<{ currentDefault: string; models: ModelOption[] }> {
  const response = await apiClient.get('/agent/models')
  return response.data?.data || response.data
}

export async function uploadChatFile(file: File): Promise<ChatAttachment> {
  const formData = new FormData()
  formData.append('file', file)
  const token = localStorage.getItem('ragent_token') || ''
  const response = await fetch('/api/agent/upload-file', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
    },
    body: formData,
  })
  if (!response.ok) {
    if (response.status === 401) dispatchUnauthorized()
    const errorJson = await response.json().catch(() => ({}))
    throw new Error(errorJson.detail || `上传解析失败：${response.status}`)
  }
  const res = await response.json()
  return res.data || res
}

export async function listConversations(): Promise<ConversationSummary[]> {
  const response = await apiClient.get('/conversations?pageNo=1&pageSize=20')
  return toArrayResult<ConversationSummary>(response)
}

export async function listMessages(conversationId: string): Promise<ChatMessageDTO[]> {
  const response = await apiClient.get(`/conversations/${conversationId}/messages`)
  return toArrayResult<ChatMessageDTO>(response)
}

export async function clearConversationMessages(conversationId: string): Promise<void> {
  await apiClient.delete(`/conversations/${conversationId}/messages`)
}

function dispatchUnauthorized() {
  window.dispatchEvent(new Event('ragent:unauthorized'))
}

function parseSseBuffer(buffer: string, onEvent: (event: Record<string, unknown>) => void, flush = false) {
  const normalized = buffer.replace(/\r\n/g, '\n').replace(/\r/g, '\n')
  const frames = normalized.split('\n\n')
  const tail = flush ? '' : (frames.pop() || '')
  for (const frame of frames) {
    if (!frame.trim()) continue
    const lines = frame.split('\n')
    for (const line of lines) {
      const trimmed = line.trim()
      if (trimmed.startsWith('data:')) {
        const jsonStr = trimmed.slice(5).trim()
        if (jsonStr) {
          try {
            onEvent(JSON.parse(jsonStr))
          } catch (err) {
            console.warn('Failed to parse SSE frame:', jsonStr, err)
          }
        }
      }
    }
  }
  return tail
}

export async function sendUnifiedChatMessage(
  payload: UnifiedChatPayload,
  onEvent: (event: Record<string, unknown>) => void,
) {
  const token = localStorage.getItem('ragent_token') || ''
  const response = await fetch('/api/agent/chat', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  })
  if (!response.ok) {
    if (response.status === 401) dispatchUnauthorized()
    throw new Error(`聊天请求失败：${response.status}`)
  }
  const reader = response.body?.getReader()
  if (!reader) return
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) {
      buffer += decoder.decode()
      if (buffer.trim()) parseSseBuffer(`${buffer}\n\n`, onEvent, true)
      break
    }
    buffer += decoder.decode(value, { stream: true })
    buffer = parseSseBuffer(buffer, onEvent)
  }
}

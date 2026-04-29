import apiClient from './api'
import { toArrayResult } from './result'

export type ChatMode = 'auto' | 'rag' | 'ops'

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

export interface UnifiedChatPayload {
  message: string
  mode: ChatMode
  conversationId?: string
  deepThinking?: boolean
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

function parseSseBuffer(buffer: string, onEvent: (event: Record<string, unknown>) => void) {
  const frames = buffer.split('\n\n')
  const tail = frames.pop() || ''
  for (const frame of frames) {
    const line = frame.split('\n').find((item) => item.startsWith('data: '))
    if (!line) continue
    try {
      onEvent(JSON.parse(line.slice(6)))
    } catch {
      // 代理可能把 SSE 帧拆开，解析失败的半帧留给下一轮数据兜底。
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
    throw new Error(`聊天请求失败：${response.status}`)
  }
  const reader = response.body?.getReader()
  if (!reader) return
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    buffer = parseSseBuffer(buffer, onEvent)
  }
}

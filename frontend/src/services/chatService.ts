import apiClient from './api'
import { toArrayResult } from './result'

export interface ConversationSummary {
  id: string
  title?: string
  updatedAt?: string
}

export interface ChatMessageDTO {
  id?: string
  role: string
  content: string
}

export async function createConversation() {
  const response = await apiClient.get('/conversations?pageNo=1&pageSize=1')
  const first = toArrayResult<ConversationSummary>(response)[0]
  return first?.id ?? ''
}

export async function listConversations(): Promise<ConversationSummary[]> {
  const response = await apiClient.get('/conversations?pageNo=1&pageSize=20')
  return toArrayResult<ConversationSummary>(response)
}

export async function listMessages(conversationId: string): Promise<ChatMessageDTO[]> {
  const response = await apiClient.get(`/conversations/${conversationId}/messages`)
  return toArrayResult<ChatMessageDTO>(response)
}

export async function sendChatMessage(
  question: string,
  conversationId: string | undefined,
  onEvent: (event: Record<string, unknown>) => void,
) {
  const token = localStorage.getItem('ragent_token') || ''
  const url = `/api/rag/v3/chat?question=${encodeURIComponent(question)}${conversationId ? `&conversationId=${conversationId}` : ''}`
  const response = await fetch(url, { headers: { Authorization: `Bearer ${token}` } })
  if (!response.ok) {
    throw new Error(`chat request failed: ${response.status}`)
  }
  const reader = response.body?.getReader()
  if (!reader) return
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const parts = buffer.split('\n')
    buffer = parts.pop() || ''
    for (const line of parts) {
      if (!line.startsWith('data: ')) continue
      try {
        onEvent(JSON.parse(line.slice(6)))
      } catch {
        // ignore malformed SSE event
      }
    }
  }
}

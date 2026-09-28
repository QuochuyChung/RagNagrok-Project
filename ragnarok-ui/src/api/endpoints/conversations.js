import { apiRequest } from '../client'

/** GET /v1/conversations — danh sách hội thoại của user hiện tại, phân trang. */
export function listConversations({ limit = 20, offset = 0 } = {}) {
  return apiRequest(`/v1/conversations?limit=${limit}&offset=${offset}`)
}

/** GET /v1/conversations/{id}/messages — toàn bộ tin nhắn của 1 hội thoại. */
export function getConversationMessages(conversationId) {
  return apiRequest(`/v1/conversations/${conversationId}/messages`)
}

/** DELETE /v1/conversations/{id} — xóa cứng 1 hội thoại. */
export function deleteConversationApi(conversationId) {
  return apiRequest(`/v1/conversations/${conversationId}`, { method: 'DELETE' })
}

import { API_BASE_URL, createRequestId } from '../client'

function buildChatHeaders() {
  const token = localStorage.getItem('ragnarok_token')
  const tenantId = localStorage.getItem('tenantId') || import.meta.env.VITE_DEFAULT_TENANT
  const headers = {
    'Content-Type': 'application/json',
    'X-Request-ID': createRequestId(),
  }
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }
  if (tenantId) {
    headers['X-Tenant-ID'] = tenantId
  }
  return headers
}

/**
 * Backend trả lỗi ở 2 dạng:
 *   - Exception handler (app/core/errors.py): { error_code, message, request_id, timestamp }
 *   - HTTPException (vd TENANT_REQUIRED):     { detail: { error_code, message } }
 *   - Middleware JWT:                         { error_code } (không có message)
 */
function toChatError(status, body) {
  if (typeof body === 'string') {
    const error = new Error(body || `Yêu cầu thất bại (HTTP ${status}).`)
    error.status = status
    error.errorCode = null
    return error
  }

  const payload = (body && body.detail) || body || {}
  const error = new Error(payload.message || `Yêu cầu thất bại (HTTP ${status}).`)
  error.status = status
  error.errorCode = payload.error_code || null
  error.requestId = payload.request_id || null
  return error
}

async function parseBody(response) {
  const text = await response.text()
  if (!text) return null
  try {
    return JSON.parse(text)
  } catch {
    return text
  }
}

/**
 * POST /v1/chat — chạy trọn pipeline RAG (non-streaming).
 *
 * payload: { message, conversation_id, stream, top_k }
 * trả về ChatResponse: { conversation_id, message, citations[], latency_ms, timestamp }
 */
export async function sendChatMessage(payload) {
  const response = await fetch(`${API_BASE_URL}/v1/chat`, {
    method: 'POST',
    headers: buildChatHeaders(),
    body: JSON.stringify(payload),
  })

  const body = await parseBody(response)

  if (!response.ok) {
    throw toChatError(response.status, body)
  }

  return body
}

/**
 * POST /v1/chat (stream=true) — chạy pipeline RAG dạng SSE.
 *
 * Backend yield lần lượt các event: "citations" (1 lần, ngay sau retrieval),
 * "token" (nhiều lần, mỗi lần 1 mẩu câu trả lời), "done" (1 lần, cuối cùng,
 * kèm conversation_id + latency_ms), hoặc "error" nếu pipeline lỗi giữa chừng.
 *
 * Trả về async generator — dùng `for await (const evt of streamChatMessage(...))`.
 * Không dùng EventSource được vì: (1) endpoint là POST, (2) cần set header
 * Authorization/X-Tenant-ID mà EventSource không hỗ trợ custom header.
 */
export async function* streamChatMessage(payload) {
  const response = await fetch(`${API_BASE_URL}/v1/chat`, {
    method: 'POST',
    headers: buildChatHeaders(),
    body: JSON.stringify({ ...payload, stream: true }),
  })

  if (!response.ok) {
    const body = await parseBody(response)
    throw toChatError(response.status, body)
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    // 1 event SSE kết thúc bằng dòng trống ("\n\n") — có thể nhiều event
    // dính liền trong cùng 1 lần đọc, nên rút hết bao nhiêu event đủ điều
    // kiện thì rút, phần dư (chưa đủ 1 event) giữ lại buffer chờ đợt sau.
    let idx
    while ((idx = buffer.indexOf('\n\n')) !== -1) {
      const eventBlock = buffer.slice(0, idx)
      buffer = buffer.slice(idx + 2)

      const lines = eventBlock.split('\n')
      const eventLine = lines.find((l) => l.startsWith('event:'))
      const dataLine = lines.find((l) => l.startsWith('data:'))
      if (!eventLine || !dataLine) continue

      yield {
        event: eventLine.slice(6).trim(),
        data: JSON.parse(dataLine.slice(5).trim()),
      }
    }
  }
}

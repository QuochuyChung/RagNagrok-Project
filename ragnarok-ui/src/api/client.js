const DEFAULT_API_BASE_URL = 'http://localhost:8000'

export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || DEFAULT_API_BASE_URL

export function createRequestId() {
  return crypto.randomUUID()
}

export async function apiRequest(path, options = {}) {
  const rawTenantId = localStorage.getItem('tenantId')
  const tenantId =
    (rawTenantId && rawTenantId !== 'null' && rawTenantId !== 'undefined')
      ? rawTenantId
      : import.meta.env.VITE_DEFAULT_TENANT
  const token = localStorage.getItem('ragnarok_token')
  const headers = new Headers(options.headers)

  headers.set('X-Request-ID', createRequestId())
  if (tenantId && tenantId !== 'null' && tenantId !== 'undefined') {
    if (!headers.has('X-Tenant-ID')) {
      headers.set('X-Tenant-ID', tenantId)
    }
  }
  if (token) {
    headers.set('Authorization', `Bearer ${token}`)
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers,
  })

  if (response.status === 204) {
    if (!response.ok) {
      throw { status: response.status, statusText: response.statusText }
    }
    return null
  }

  const text = await response.text()
  let body = null
  if (text) {
    try {
      body = JSON.parse(text)
    } catch {
      body = text
    }
  }

  if (!response.ok) {
    if (path.startsWith('/health') && body && typeof body === 'object' && body.services) {
      return body
    }
    let message = 'Đã có lỗi xảy ra. Vui lòng thử lại.'
    if (body && typeof body === 'object') {
      if (body.error && typeof body.error === 'object' && body.error.message) {
        message = body.error.message
      } else if (Array.isArray(body.detail)) {
        message = body.detail.map((d) => d.msg || JSON.stringify(d)).join('; ')
      } else if (body.detail && typeof body.detail === 'object' && body.detail.message) {
        message = body.detail.message
      } else {
        message = body.message || (typeof body.detail === 'string' ? body.detail : message)
      }
    } else if (typeof body === 'string' && body.trim()) {
      message = body
    }

    const error = new Error(message)
    error.status = response.status
    error.body = body
    throw error
    }

    return body
}

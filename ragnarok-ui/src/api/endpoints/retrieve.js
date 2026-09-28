import { apiRequest } from '../client'

export function semanticSearch(payload) {
  return apiRequest('/v1/retrieve', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

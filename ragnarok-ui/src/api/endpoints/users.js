import { apiRequest } from '../client'

export function getUsers() {
  return apiRequest('/v1/users')
}

export function createUser(payload) {
  return apiRequest('/v1/users', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function deleteUser(userId) {
  return apiRequest(`/v1/users/${userId}`, {
    method: 'DELETE',
  })
}

export function restoreUser(userId) {
  return apiRequest(`/v1/users/${userId}/restore`, {
    method: 'PATCH',
  })
}

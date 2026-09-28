export function getCurrentUser() {
  const storedUser = localStorage.getItem('ragnarok_user')
  if (storedUser) {
    try {
      return Promise.resolve(JSON.parse(storedUser))
    } catch (e) {
      return Promise.resolve(null)
    }
  }
  return Promise.resolve(null)
}

import { apiRequest } from '../client'

export async function forgotPassword(email) {
  return apiRequest('/v1/tokens/forgot-password', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email })
  })
}

export async function validateResetToken(token) {
  return apiRequest(`/v1/tokens/reset-password/validate?token=${token}`, {
    method: 'GET'
  })
}

export async function resetPassword(payload) {
  return apiRequest('/v1/tokens/reset-password', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  })
}

export async function validateInviteToken(token) {
  return apiRequest(`/v1/tokens/invitations/validate?token=${token}`, {
    method: 'GET'
  })
}

export async function acceptInvite(payload) {
  return apiRequest('/v1/tokens/invitations/accept', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  })
}

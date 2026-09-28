import { apiRequest } from '../client'

export function getTenants() {
  return apiRequest('/v1/tenants')
}

export function createTenant(payload) {
  return apiRequest('/v1/tenants', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function deleteTenant(tenantId) {
  return apiRequest(`/v1/tenants/${tenantId}`, {
    method: 'DELETE',
  })
}

export function inviteUsers(tenantId, payload) {
  return apiRequest(`/v1/tenants/invitations`, {
    method: 'POST',
    headers: { 
      'Content-Type': 'application/json',
      'X-Tenant-ID': tenantId
    },
    body: JSON.stringify(payload),
  })
}

export function inviteUsersCSV(tenantId, role, expiry, formData) {
  // Use fetch directly for FormData to let browser set boundary
  return apiRequest(`/v1/tenants/invitations/csv?role_name=${role}&expires_in_hours=${expiry}`, {
    method: 'POST',
    headers: {
      'X-Tenant-ID': tenantId
    },
    // Do not set Content-Type header here, the browser will set it with boundary
    body: formData,
  })
}

export function resendInvite(tenantId, userId) {
  return apiRequest(`/v1/tenants/invitations/${userId}/resend`, {
    method: 'POST',
    headers: {
      'X-Tenant-ID': tenantId
    }
  })
}

export function revokeInvite(tenantId, userId) {
  return apiRequest(`/v1/tenants/invitations/${userId}`, {
    method: 'DELETE',
    headers: {
      'X-Tenant-ID': tenantId
    }
  })
}

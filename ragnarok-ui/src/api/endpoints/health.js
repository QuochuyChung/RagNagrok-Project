import { apiRequest } from '../client'

export function getHealth() {
  return apiRequest('/health/debug')
}

export function getVersion() {
  return apiRequest('/version')
}

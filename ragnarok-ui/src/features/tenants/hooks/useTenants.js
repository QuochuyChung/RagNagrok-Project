import { useEffect, useState } from 'react'
import { getTenants, createTenant, deleteTenant as apiDeleteTenant } from '../../../api/endpoints/tenants'

export function useTenants() {
  const [tenants, setTenants] = useState([])
  const [error, setError] = useState(null)
  const [isLoading, setIsLoading] = useState(false)

  const getMockTenants = () => {
    const stored = localStorage.getItem('ragnarok_mock_tenants')
    if (stored) return JSON.parse(stored)
    const initial = [
      { id: '1', name: 'Công ty Cổ phần A', qdrantCollection: 'tenant_co_a', status: 'active', createdAt: '2026-07-01T08:00:00Z' },
      { id: '2', name: 'Tập đoàn Đầu tư B', qdrantCollection: 'tenant_tap_doan_b', status: 'active', createdAt: '2026-07-03T10:30:00Z' },
      { id: '3', name: 'Ngân hàng Thương mại C', qdrantCollection: 'tenant_ngan_hang_c', status: 'inactive', createdAt: '2026-07-05T14:45:00Z' }
    ]
    localStorage.setItem('ragnarok_mock_tenants', JSON.stringify(initial))
    return initial
  }

  const refresh = () => {
    setIsLoading(true)
    setError(null)
    return getTenants()
      .then((data) => {
        const rawList = Array.isArray(data)
          ? data
          : Array.isArray(data?.tenants)
          ? data.tenants
          : []
        const list = rawList.map((t) => ({
          id: t.id,
          name: t.name,
          qdrantCollection: t.qdrant_collection || t.qdrantCollection || `tenant_${t.name}`,
          status: t.is_active !== undefined ? (t.is_active ? 'active' : 'inactive') : t.status || 'active',
          createdAt: t.created_at || t.createdAt || new Date().toISOString(),
          updatedAt: t.updated_at || t.updatedAt || null,
        }))
        setTenants(list)
      })
      .catch((err) => {
        console.warn('Backend API not available, falling back to mock tenants:', err)
        setTenants(getMockTenants())
      })
      .finally(() => setIsLoading(false))
  }

  const addTenant = async (name, adminEmail, adminFullName, adminUsername) => {
    const payload = { name }
    if (adminEmail && adminFullName) {
      payload.tenant_admin = { email: adminEmail, full_name: adminFullName, username: adminUsername || undefined }
    }
    await createTenant(payload)
    await refresh()
  }

  const toggleTenantStatus = (id) => {
    setTenants(prev => prev.map(t => 
      t.id === id ? { ...t, status: t.status === 'active' ? 'inactive' : 'active' } : t
    ))
  }

  const deleteTenant = async (id) => {
    try {
      await apiDeleteTenant(id)
      setTenants(prev => prev.filter(t => t.id !== id))
    } catch (err) {
      console.warn('Backend deleteTenant failed, removing from local state:', err)
      setTenants(prev => prev.filter(t => t.id !== id))
    }
  }

  useEffect(() => {
    refresh()
  }, [])

  return { tenants, error, isLoading, refresh, addTenant, toggleTenantStatus, deleteTenant }
}

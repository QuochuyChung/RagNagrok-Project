import { createContext, useContext, useMemo, useState } from 'react'

const TenantContext = createContext(null)

export function TenantProvider({ children }) {
  const [tenantId, setTenantIdState] = useState(
    localStorage.getItem('tenantId') || import.meta.env.VITE_DEFAULT_TENANT || '',
  )

  function setTenantId(nextTenantId) {
    setTenantIdState(nextTenantId)
    if (nextTenantId) {
      localStorage.setItem('tenantId', nextTenantId)
    } else {
      localStorage.removeItem('tenantId')
    }
  }

  const value = useMemo(() => ({ tenantId, setTenantId }), [tenantId])

  return (
    <TenantContext.Provider value={value}>{children}</TenantContext.Provider>
  )
}

export function useTenant() {
  const context = useContext(TenantContext)

  if (!context) {
    throw new Error('useTenant must be used inside TenantProvider')
  }

  return context
}

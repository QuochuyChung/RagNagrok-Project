import { TenantSwitcher } from '../../../features/tenants/components/TenantSwitcher'

export function Header() {
  return (
    <header className="app-header">
      <h1>Multi-Tenant RAG Gateway</h1>
      <TenantSwitcher />
    </header>
  )
}

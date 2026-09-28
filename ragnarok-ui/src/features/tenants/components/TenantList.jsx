export function TenantList({ tenants = [] }) {
  if (!tenants.length) {
    return <p className="muted">Chua co tenant nao de hien thi.</p>
  }

  return (
    <ul>
      {tenants.map((tenant) => (
        <li key={tenant.id || tenant.tenant_id}>{tenant.name || tenant.id}</li>
      ))}
    </ul>
  )
}

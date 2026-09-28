import { useTenant } from '../../../context/TenantContext'

export function TenantSwitcher() {
  const { tenantId, setTenantId } = useTenant()

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', width: '100%' }}>
      <label style={{
        fontSize: '11px',
        fontWeight: '700',
        color: 'var(--sidebar-muted)',
        textTransform: 'uppercase',
        letterSpacing: '0.5px',
        userSelect: 'none'
      }}>
        Không gian làm việc (Tenant)
      </label>
      <input
        value={tenantId}
        onChange={(event) => setTenantId(event.target.value)}
        placeholder="Nhập ID không gian..."
        style={{
          width: '100%',
          padding: '8px 12px',
          borderRadius: '8px',
          border: '1px solid var(--border)',
          backgroundColor: '#ffffff',
          color: 'var(--sidebar-text)',
          fontSize: '13.5px',
          fontFamily: 'inherit',
          outline: 'none',
          boxSizing: 'border-box',
          transition: 'all 0.15s ease'
        }}
        onFocus={(e) => e.target.style.borderColor = '#b4b4b8'}
        onBlur={(e) => e.target.style.borderColor = 'var(--border)'}
      />
    </div>
  )
}

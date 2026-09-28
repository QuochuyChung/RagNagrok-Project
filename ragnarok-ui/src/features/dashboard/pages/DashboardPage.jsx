import { useState, useEffect, useCallback } from 'react'
import { useAuth } from '../../../context/AuthContext'
import { useChat } from '../../../context/ChatContext'
import { getUsers } from '../../../api/endpoints/users'
import { listDocuments } from '../../../api/endpoints/documents'
import { getHealth, getVersion } from '../../../api/endpoints/health'
import { getTenants } from '../../../api/endpoints/tenants'
import './DashboardPage.css'

function navigate(path) {
  window.history.pushState({}, '', path)
  window.dispatchEvent(new PopStateEvent('popstate'))
}

function formatBytes(bytes) {
  if (!bytes || bytes === 0) return '0 B'
  if (bytes >= 1073741824) return `${(bytes / 1073741824).toFixed(2)} GB`
  if (bytes >= 1048576) return `${(bytes / 1048576).toFixed(1)} MB`
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${bytes} B`
}

function formatTime(date) {
  if (!date) return '—'
  return date.toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

function getInitials(name) {
  return name ? name.split(' ').map((p) => p[0]).filter(Boolean).slice(0, 2).join('').toUpperCase() || '?' : '?'
}

function getAvatarGradient(str = '') {
  const g = [
    ['#10b981', '#059669'],
    ['#6366f1', '#4f46e5'],
    ['#f59e0b', '#d97706'],
    ['#ec4899', '#db2777'],
    ['#06b6d4', '#0891b2'],
    ['#8b5cf6', '#7c3aed'],
    ['#14b8a6', '#0d9488'],
  ]
  let h = 0
  for (let i = 0; i < str.length; i++) h = str.charCodeAt(i) + ((h << 5) - h)
  const [a, b] = g[Math.abs(h) % g.length]
  return `linear-gradient(135deg, ${a} 0%, ${b} 100%)`
}

function LatencyBadge({ latency, status }) {
  if (!status || status !== 'up') return <span className="dash-service-latency dash-service-latency--down">down</span>
  if (latency === null || latency === undefined) return null
  const cls = latency < 50 ? 'fast' : latency < 200 ? 'medium' : 'slow'
  return <span className={`dash-service-latency dash-service-latency--${cls}`}>{latency.toFixed(1)} ms</span>
}

function MetricCard({ label, value, unit, sub, accentColor, iconBg, icon, loading }) {
  return (
    <div className={`dash-metric-card${loading ? ' dash-metric-card--skeleton' : ''}`}>
      <div className="dash-metric-card__accent" style={{ background: accentColor }} />
      <div className="dash-metric-card__icon" style={{ background: iconBg }}>
        {icon}
      </div>
      <div className="dash-metric-card__label">{label}</div>
      <div className="dash-metric-card__value">
        {loading ? '···' : value}
        {!loading && unit && <span className="dash-metric-card__value-unit">{unit}</span>}
      </div>
      <div className="dash-metric-card__sub">{loading ? '···' : sub}</div>
    </div>
  )
}

export function DashboardPage() {
  const { user } = useAuth()
  const { conversations } = useChat()

  const isPlatformAdmin = user?.role === 'PLATFORM_ADMIN'

  const [tenants, setTenants] = useState([])
  const [documents, setDocuments] = useState([])
  const [users, setUsers] = useState([])
  const [health, setHealth] = useState(null)
  const [version, setVersion] = useState(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [lastUpdated, setLastUpdated] = useState(null)
  const [errors, setErrors] = useState({})

  const fetchAll = useCallback(async (isManualRefresh = false) => {
    if (isManualRefresh) setRefreshing(true)
    const errs = {}

    const requests = [
      listDocuments(),
      getUsers(),
      getHealth(),
      getVersion(),
    ]

    if (isPlatformAdmin) {
      requests.push(getTenants())
    }

    const results = await Promise.allSettled(requests)
    const [docsResult, usersResult, healthResult, versionResult, tenantsResult] = results

    // Documents
    if (docsResult.status === 'fulfilled') {
      const raw = docsResult.value
      const list = Array.isArray(raw) ? raw : Array.isArray(raw?.documents) ? raw.documents : []
      setDocuments(list)
    } else {
      errs.documents = true
    }

    // Users
    if (usersResult.status === 'fulfilled') {
      const raw = usersResult.value
      setUsers(raw?.users || raw || [])
    } else {
      errs.users = true
    }

    // Health
    if (healthResult.status === 'fulfilled') {
      setHealth(healthResult.value)
    } else if (healthResult.reason && healthResult.reason.services) {
      setHealth(healthResult.reason)
    } else {
      errs.health = true
    }

    // Version
    if (versionResult.status === 'fulfilled') {
      setVersion(versionResult.value)
    } else {
      errs.version = true
    }

    // Tenants (Platform Admin)
    if (isPlatformAdmin && tenantsResult) {
      if (tenantsResult.status === 'fulfilled') {
        const raw = tenantsResult.value
        setTenants(Array.isArray(raw) ? raw : Array.isArray(raw?.tenants) ? raw.tenants : [])
      } else {
        errs.tenants = true
      }
    }

    setErrors(errs)
    setLastUpdated(new Date())
    setLoading(false)
    setRefreshing(false)
  }, [isPlatformAdmin])

  useEffect(() => {
    fetchAll()
    const interval = setInterval(() => fetchAll(), 30000)
    return () => clearInterval(interval)
  }, [fetchAll])

  // Tenant stats
  const tenantTotal = tenants.length
  const activeTenants = tenants.filter(t => t.status === 'active').length
  const inactiveTenants = tenants.filter(t => t.status === 'inactive').length
  const totalCollections = new Set(tenants.map(t => t.qdrantCollection)).size

  // Derived document stats
  const docTotal = documents.length
  const docIndexed = documents.filter(d => {
    const s = (d.status || '').toLowerCase()
    return s === 'completed' || s === 'ingested'
  }).length
  const docPending = documents.filter(d => {
    const s = (d.status || '').toLowerCase()
    return s === 'pending' || s === 'processing'
  }).length
  const docFailed = documents.filter(d => (d.status || '').toLowerCase() === 'failed').length
  const totalBytes = documents.reduce((acc, d) => acc + (d.file_size || 0), 0)

  // User stats
  const userTotal = Array.isArray(users) ? users.length : 0
  const activeUsers = Array.isArray(users) ? users.filter(u => u.is_active !== false).length : 0

  // Conversations
  const convTotal = conversations.length

  // Services
  const services = health?.services || {}
  const serviceList = [
    { key: 'postgres', label: 'PostgreSQL', sub: 'Relational Database' },
    { key: 'qdrant', label: 'Qdrant', sub: 'Vector Database' },
    { key: 'ollama', label: 'Ollama', sub: 'LLM Engine' },
  ]

  const overallStatus = health?.status
  const isHealthy = overallStatus === 'healthy'

  const now = new Date()
  const hourOfDay = now.getHours()
  const greeting = hourOfDay < 12 ? 'Chào buổi sáng' : hourOfDay < 18 ? 'Chào buổi chiều' : 'Chào buổi tối'
  const firstName = (user?.name || user?.username || '').split(' ').slice(-1)[0]

  const docBarItems = [
    { label: 'Đã indexed', count: docIndexed, color: '#10b981', total: docTotal },
    { label: 'Đang xử lý', count: docPending, color: '#f59e0b', total: docTotal },
    { label: 'Lỗi', count: docFailed, color: '#ef4444', total: docTotal },
  ]

  return (
    <div className="dash-page">
      {/* ── Header ─────────────────────────────────────── */}
      <div className="dash-header">
        <div className="dash-header__left">
          <h1 className="dash-header__greeting">
            {greeting}, <span>{firstName}</span> 👋
          </h1>
          <p className="dash-header__sub">
            {isPlatformAdmin
              ? 'Tổng quan hệ thống RAG Gateway'
              : 'Tổng quan không gian làm việc của bạn'}
          </p>
        </div>
        <div className="dash-header__right">
          {lastUpdated && (
            <span className="dash-last-updated">Cập nhật lúc {formatTime(lastUpdated)}</span>
          )}
          <button
            className={`dash-refresh-btn${refreshing ? ' spinning' : ''}`}
            onClick={() => fetchAll(true)}
            disabled={refreshing}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="23 4 23 10 17 10" />
              <polyline points="1 20 1 14 7 14" />
              <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
            </svg>
            Làm mới
          </button>
        </div>
      </div>

      {/* ── KPI Metrics ────────────────────────────────── */}
      <div className="dash-metrics-grid">
        {isPlatformAdmin ? (
          <>
            <MetricCard
              label="Không gian (Tenants)"
              value={tenantTotal}
              unit="thuê bao"
              sub={`${activeTenants} đang hoạt động · ${inactiveTenants} tạm khóa`}
              accentColor="linear-gradient(90deg, #10b981, #34d399)"
              iconBg="rgba(16, 185, 129, 0.1)"
              loading={loading}
              icon={
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#10b981" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="2" y="7" width="20" height="14" rx="2" ry="2" />
                  <path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16" />
                </svg>
              }
            />
            <MetricCard
              label="Tài liệu RAG toàn hệ thống"
              value={docTotal}
              unit="tệp"
              sub={`${docIndexed} đã indexed · ${docPending} đang xử lý`}
              accentColor="linear-gradient(90deg, #059669, #10b981)"
              iconBg="rgba(5, 150, 105, 0.1)"
              loading={loading}
              icon={
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#059669" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                  <polyline points="14 2 14 8 20 8" />
                  <line x1="16" y1="13" x2="8" y2="13" />
                  <line x1="16" y1="17" x2="8" y2="17" />
                  <polyline points="10 9 9 9 8 9" />
                </svg>
              }
            />
            <MetricCard
              label="Dung lượng lưu trữ hệ thống"
              value={formatBytes(totalBytes)}
              sub={`${docTotal} tệp tin đã tải lên toàn hệ thống`}
              accentColor="linear-gradient(90deg, #ec4899, #f43f5e)"
              iconBg="rgba(236, 72, 153, 0.1)"
              loading={loading}
              icon={
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#ec4899" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <ellipse cx="12" cy="5" rx="9" ry="3" />
                  <path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3" />
                  <path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5" />
                </svg>
              }
            />
            <MetricCard
              label="Tài khoản & Vector Collections"
              value={userTotal}
              unit="người dùng"
              sub={`${activeUsers} active · ${totalCollections || tenantTotal} Qdrant spaces`}
              accentColor="linear-gradient(90deg, #6366f1, #818cf8)"
              iconBg="rgba(99, 102, 241, 0.1)"
              loading={loading}
              icon={
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#6366f1" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
                  <circle cx="9" cy="7" r="4" />
                  <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
                  <path d="M16 3.13a4 4 0 0 1 0 7.75" />
                </svg>
              }
            />
          </>
        ) : (
          <>
            <MetricCard
              label="Tài liệu RAG"
              value={docTotal}
              unit="tệp"
              sub={`${docIndexed} đã indexed · ${docPending} đang xử lý`}
              accentColor="linear-gradient(90deg, #10a37f, #0ea5e9)"
              iconBg="rgba(16, 163, 127, 0.1)"
              loading={loading}
              icon={
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#10a37f" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z" />
                  <path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z" />
                </svg>
              }
            />
            <MetricCard
              label="Người dùng"
              value={userTotal}
              unit="tài khoản"
              sub={`${activeUsers} đang hoạt động`}
              accentColor="linear-gradient(90deg, #6366f1, #8b5cf6)"
              iconBg="rgba(99, 102, 241, 0.1)"
              loading={loading}
              icon={
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#6366f1" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
                  <circle cx="9" cy="7" r="4" />
                  <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
                  <path d="M16 3.13a4 4 0 0 1 0 7.75" />
                </svg>
              }
            />
            <MetricCard
              label="Hội thoại"
              value={convTotal}
              unit="cuộc trò chuyện"
              sub="Lưu trữ trong phiên này"
              accentColor="linear-gradient(90deg, #f59e0b, #f97316)"
              iconBg="rgba(245, 158, 11, 0.1)"
              loading={loading}
              icon={
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#f59e0b" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
                </svg>
              }
            />
            <MetricCard
              label="Dung lượng lưu trữ"
              value={formatBytes(totalBytes)}
              sub={`${docTotal} tệp tin đã tải lên`}
              accentColor="linear-gradient(90deg, #ec4899, #f43f5e)"
              iconBg="rgba(236, 72, 153, 0.1)"
              loading={loading}
              icon={
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#ec4899" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <ellipse cx="12" cy="5" rx="9" ry="3" />
                  <path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3" />
                  <path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5" />
                </svg>
              }
            />
          </>
        )}
      </div>

      {/* ── Main Two Columns ────────────────────────────── */}
      <div className="dash-two-col">
        {/* Left Column */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {isPlatformAdmin && (
            <div className="dash-panel">
              <div className="dash-panel__header">
                <h2 className="dash-panel__title">
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ color: 'var(--text-secondary)' }}>
                    <rect x="2" y="7" width="20" height="14" rx="2" ry="2" />
                    <path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16" />
                  </svg>
                  Danh sách Không gian (Tenants)
                </h2>
                <button
                  style={{
                    background: 'none',
                    border: 'none',
                    color: 'var(--accent)',
                    fontSize: '12.5px',
                    fontWeight: '600',
                    cursor: 'pointer'
                  }}
                  onClick={() => navigate('/tenants')}
                >
                  Quản lý Tenant →
                </button>
              </div>
              <div className="dash-tenant-list">
                {loading ? (
                  <p style={{ color: 'var(--text-secondary)', fontSize: '13px', margin: '4px 0' }}>Đang nạp danh sách tenant...</p>
                ) : tenants.length === 0 ? (
                  <p style={{ color: 'var(--text-secondary)', fontSize: '13px', margin: '4px 0' }}>Chưa có tenant nào.</p>
                ) : (
                  tenants.slice(0, 5).map(t => {
                    const initials = getInitials(t.name)
                    const avatarBg = getAvatarGradient(t.name)
                    const isActive = t.status === 'active'
                    return (
                      <div className="dash-tenant-item" key={t.id}>
                        <div className="dash-tenant-item__left">
                          <div className="dash-tenant-avatar" style={{ background: avatarBg }}>
                            {initials}
                          </div>
                          <div>
                            <div className="dash-tenant-name">{t.name}</div>
                            <span className="dash-tenant-collection">{t.qdrantCollection}</span>
                          </div>
                        </div>
                        <span className={`dash-service-latency ${isActive ? 'dash-service-latency--fast' : 'dash-service-latency--slow'}`}>
                          {isActive ? '● Active' : '○ Inactive'}
                        </span>
                      </div>
                    )
                  })
                )}
              </div>
            </div>
          )}

          {/* Document status distribution */}
          <div className="dash-panel">
            <div className="dash-panel__header">
              <h2 className="dash-panel__title">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ color: 'var(--text-secondary)' }}>
                  <path d="M18 20V10" /><path d="M12 20V4" /><path d="M6 20v-6" />
                </svg>
                Phân bổ tài liệu RAG
              </h2>
              <span className="dash-panel__badge">{docTotal} tệp</span>
            </div>
            <div className="dash-doc-stats">
              {docBarItems.map(item => {
                const pct = docTotal > 0 ? Math.round((item.count / docTotal) * 100) : 0
                return (
                  <div className="dash-doc-stat-row" key={item.label}>
                    <div className="dash-doc-stat-label">
                      <span className="dash-doc-stat-name">
                        <span className="dash-doc-stat-dot" style={{ background: item.color }} />
                        {item.label}
                      </span>
                      <span className="dash-doc-stat-count">{loading ? '···' : `${item.count} (${pct}%)`}</span>
                    </div>
                    <div className="dash-doc-stat-bar">
                      <div
                        className="dash-doc-stat-fill"
                        style={{ width: loading ? '0%' : `${pct}%`, background: item.color }}
                      />
                    </div>
                  </div>
                )
              })}
              {!loading && docTotal === 0 && (
                <p style={{ color: 'var(--text-secondary)', fontSize: '13px', margin: '8px 0 0', textAlign: 'center' }}>
                  Chưa có tài liệu nào được tải lên.
                </p>
              )}
            </div>
          </div>
        </div>

        {/* Right Column: Infrastructure + Quick Actions */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {/* Infrastructure status */}
          <div className="dash-panel">
            <div className="dash-panel__header">
              <h2 className="dash-panel__title">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ color: 'var(--text-secondary)' }}>
                  <rect x="2" y="2" width="20" height="8" rx="2" ry="2" />
                  <rect x="2" y="14" width="20" height="8" rx="2" ry="2" />
                  <line x1="6" y1="6" x2="6.01" y2="6" />
                  <line x1="6" y1="18" x2="6.01" y2="18" />
                </svg>
                Dịch vụ hạ tầng
              </h2>
              {!loading && health && (
                <div className={`dash-overall-health dash-overall-health--${isHealthy ? 'healthy' : 'unhealthy'}`}>
                  <span className="dash-overall-health__dot" />
                  {isHealthy ? 'Hoạt động tốt' : 'Có sự cố'}
                </div>
              )}
              {loading && (
                <div className="dash-overall-health dash-overall-health--loading">
                  <span className="dash-overall-health__dot" />
                  Đang kiểm tra...
                </div>
              )}
            </div>
            <div className="dash-service-list">
              {serviceList.map(({ key, label, sub }) => {
                const svc = services[key]
                const isUp = svc?.status === 'up'
                const indicatorClass = loading
                  ? 'dash-service-indicator--loading'
                  : isUp
                  ? 'dash-service-indicator--up'
                  : 'dash-service-indicator--down'
                return (
                  <div className="dash-service-row" key={key}>
                    <div className="dash-service-row__left">
                      <div className={`dash-service-indicator ${indicatorClass}`} />
                      <div>
                        <div className="dash-service-name">{label}</div>
                        <div className="dash-service-sub">{sub}</div>
                      </div>
                    </div>
                    {!loading && <LatencyBadge latency={svc?.latency_ms} status={svc?.status} />}
                  </div>
                )
              })}
              {errors.health && !loading && (
                <p style={{ color: 'var(--text-secondary)', fontSize: '12px', margin: '4px 0 0' }}>
                  ⚠️ Không thể tải trạng thái dịch vụ.
                </p>
              )}
            </div>
          </div>

          {/* Quick Actions */}
          <div className="dash-panel">
            <div className="dash-panel__header">
              <h2 className="dash-panel__title">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ color: 'var(--text-secondary)' }}>
                  <circle cx="12" cy="12" r="10" />
                  <polygon points="10 8 16 12 10 16 10 8" />
                </svg>
                Truy cập nhanh
              </h2>
            </div>
            <div className="dash-quick-actions">
              {isPlatformAdmin && (
                <button className="dash-quick-action-btn" onClick={() => navigate('/tenants')}>
                  <div className="dash-quick-action-icon" style={{ background: 'rgba(16, 185, 129, 0.1)' }}>
                    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="#10b981" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <rect x="2" y="7" width="20" height="14" rx="2" ry="2" />
                      <path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16" />
                    </svg>
                  </div>
                  <div className="dash-quick-action-text">
                    <strong>Quản lý Tenants</strong>
                    <span>Khởi tạo & cấu hình không gian làm việc</span>
                  </div>
                </button>
              )}
              <button className="dash-quick-action-btn" onClick={() => navigate('/users')}>
                <div className="dash-quick-action-icon" style={{ background: 'rgba(99, 102, 241, 0.1)' }}>
                  <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="#6366f1" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
                    <circle cx="9" cy="7" r="4" />
                    <line x1="19" y1="8" x2="19" y2="14" />
                    <line x1="22" y1="11" x2="16" y2="11" />
                  </svg>
                </div>
                <div className="dash-quick-action-text">
                  <strong>Quản lý Người dùng</strong>
                  <span>Phân quyền & quản trị tài khoản</span>
                </div>
              </button>
              <button className="dash-quick-action-btn" onClick={() => navigate('/documents')}>
                <div className="dash-quick-action-icon" style={{ background: 'rgba(16, 163, 127, 0.1)' }}>
                  <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="#10a37f" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                    <polyline points="17 8 12 3 7 8" />
                    <line x1="12" y1="3" x2="12" y2="15" />
                  </svg>
                </div>
                <div className="dash-quick-action-text">
                  <strong>Tải tài liệu RAG</strong>
                  <span>Nạp file PDF, Word, Markdown...</span>
                </div>
              </button>
              <button className="dash-quick-action-btn" onClick={() => navigate('/chat')}>
                <div className="dash-quick-action-icon" style={{ background: 'rgba(245, 158, 11, 0.1)' }}>
                  <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="#f59e0b" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
                  </svg>
                </div>
                <div className="dash-quick-action-text">
                  <strong>RAG Chat Playground</strong>
                  <span>Khởi tạo cuộc hội thoại AI</span>
                </div>
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* ── System Info Footer ──────────────────────────── */}
      {version && (
        <div className="dash-sysinfo">
          <div className="dash-sysinfo__item">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="16 18 22 12 16 6" />
              <polyline points="8 6 2 12 8 18" />
            </svg>
            Gateway <strong>v{version.version}</strong>
          </div>
          <div className="dash-sysinfo__divider" />
          <div className="dash-sysinfo__item">
            API <strong>{version.api_version}</strong>
          </div>
          <div className="dash-sysinfo__divider" />
          <div className="dash-sysinfo__item">
            Python <strong>{version.python_version}</strong>
          </div>
          {version.git_commit && (
            <>
              <div className="dash-sysinfo__divider" />
              <div className="dash-sysinfo__item">
                Git <strong style={{ fontFamily: 'monospace' }}>{version.git_commit}</strong>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  )
}

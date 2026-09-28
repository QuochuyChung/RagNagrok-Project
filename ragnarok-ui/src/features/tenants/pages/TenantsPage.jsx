import { useState, useMemo } from 'react'
import { useTenants } from '../hooks/useTenants'
import { AddTenantModal } from '../components/AddTenantModal'
import './TenantsPage.css'

export function TenantsPage() {
  const { tenants, isLoading, error, addTenant, toggleTenantStatus, deleteTenant } = useTenants()
  const [searchQuery, setSearchQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState('ALL')
  const [message, setMessage] = useState(null)
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [currentPage, setCurrentPage] = useState(1)
  const [deletingId, setDeletingId] = useState(null)
  const PAGE_SIZE = 10

  const showMessage = (type, text) => {
    setMessage({ type, text })
    setTimeout(() => setMessage(null), 4000)
  }

  const handleCopy = (text, type) => {
    navigator.clipboard.writeText(text)
    showMessage('success', `Đã sao chép ${type}`)
  }

  const handleAddTenant = async (name, adminEmail, adminFullName, adminUsername) => {
    setIsSubmitting(true)
    try {
      await addTenant(name, adminEmail, adminFullName, adminUsername)
      showMessage('success', `Khởi tạo Tenant "${name}" thành công.`)
      setIsModalOpen(false)
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleToggle = (tenant) => {
    toggleTenantStatus(tenant.id)
    const newStatus = tenant.status === 'active' ? 'Tạm khóa' : 'Kích hoạt'
    showMessage('success', `Tenant "${tenant.name}" đã được ${newStatus === 'Tạm khóa' ? 'tạm khóa' : 'kích hoạt'}.`)
  }

  const handleDelete = async (tenant) => {
    if (!window.confirm(`Xóa tenant "${tenant.name}"?\nThao tác này không thể hoàn tác. Toàn bộ dữ liệu và quyền truy cập của thành viên trong tenant sẽ bị xóa vĩnh viễn.`)) return
    setDeletingId(tenant.id)
    try {
      await deleteTenant(tenant.id)
      showMessage('success', `Tenant "${tenant.name}" đã được xóa vĩnh viễn.`)
    } catch (err) {
      showMessage('error', err?.message || 'Không thể xóa tenant. Vui lòng thử lại.')
    } finally {
      setDeletingId(null)
    }
  }

  const filteredTenants = useMemo(() => {
    const q = searchQuery.toLowerCase()
    return tenants.filter((t) => {
      const matchSearch = !q ||
        (t.name || '').toLowerCase().includes(q) ||
        (t.qdrantCollection || '').toLowerCase().includes(q)
      const matchStatus = statusFilter === 'ALL' || t.status === statusFilter
      return matchSearch && matchStatus
    })
  }, [tenants, searchQuery, statusFilter])

  const totalPages = Math.max(1, Math.ceil(filteredTenants.length / PAGE_SIZE))
  const pagedTenants = filteredTenants.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE)

  const stats = useMemo(() => ({
    total: tenants.length,
    active: tenants.filter((t) => t.status === 'active').length,
    inactive: tenants.filter((t) => t.status === 'inactive').length,
    collections: new Set(tenants.map(t => t.qdrantCollection)).size
  }), [tenants])

  const getInitials = (name) =>
    name ? name.split(' ').map((p) => p[0]).filter(Boolean).slice(0, 2).join('').toUpperCase() || '?' : '?'

  const getAvatarGradient = (str = '') => {
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

  const formatDate = (iso) => {
    if (!iso) return '—'
    try {
      return new Intl.DateTimeFormat('vi-VN', { day: '2-digit', month: '2-digit', year: 'numeric' }).format(new Date(iso))
    } catch { return iso }
  }

  return (
    <div className="tenants-page">
      {/* ── Page Header ─────────────────────────────────── */}
      <div className="tenants-page__header">
        <div className="tenants-page__header-info">
          <h1 className="tenants-page__title">Quản lý Tenants</h1>
          <p className="tenants-page__subtitle">
            Tạo và quản lý các tenant độc lập, theo dõi trạng thái và dung lượng lưu trữ.
          </p>
        </div>
        <button className="tenants-btn-primary" onClick={() => setIsModalOpen(true)}>
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
            <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
          </svg>
          Tạo Tenant
        </button>
      </div>

      {/* ── Toast ───────────────────────────────────────── */}
      {message && (
        <div className={`tenants-toast tenants-toast--${message.type}`}>
          <span className="tenants-toast__icon">{message.type === 'success' ? '✓' : '!'}</span>
          <span>{message.text}</span>
        </div>
      )}

      {/* ── Stats Row ───────────────────────────────────── */}
      <div className="tenants-stats">
        <div className="tenants-stat-card">
          <div className="tenants-stat-card__label">Tổng Tenant</div>
          <div className="tenants-stat-card__value">{stats.total}</div>
          <div className="tenants-stat-card__sub">tenant trên hệ thống</div>
        </div>
        <div className="tenants-stat-card tenants-stat-card--green">
          <div className="tenants-stat-card__label">Đang hoạt động</div>
          <div className="tenants-stat-card__value tenants-stat-card__value--green">{stats.active}</div>
          <div className="tenants-stat-card__sub">
            {stats.total > 0 ? Math.round((stats.active / stats.total) * 100) : 0}% đang hoạt động
          </div>
        </div>
        <div className="tenants-stat-card tenants-stat-card--indigo">
          <div className="tenants-stat-card__label">Tạm khóa</div>
          <div className="tenants-stat-card__value tenants-stat-card__value--indigo">{stats.inactive}</div>
          <div className="tenants-stat-card__sub">tenant bị tạm khóa</div>
        </div>
        <div className="tenants-stat-card tenants-stat-card--emerald">
          <div className="tenants-stat-card__label">Kho dữ liệu</div>
          <div className="tenants-stat-card__value tenants-stat-card__value--emerald">{stats.collections}</div>
          <div className="tenants-stat-card__sub">vector collections riêng biệt</div>
        </div>
      </div>

      {/* ── Toolbar ─────────────────────────────────────── */}
      <div className="tenants-toolbar">
        <div className="tenants-search">
          <svg className="tenants-search__icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
          <input
            className="tenants-search__input"
            type="text"
            placeholder="Tìm theo tên tenant..."
            value={searchQuery}
            onChange={(e) => { setSearchQuery(e.target.value); setCurrentPage(1) }}
          />
          {searchQuery && (
            <button className="tenants-search__clear" onClick={() => setSearchQuery('')}>✕</button>
          )}
        </div>

        <div className="tenants-filters">
          <div className="tenants-filter-group">
            <label className="tenants-filter-group__label">Trạng thái</label>
            <select
              className="tenants-filter-select"
              value={statusFilter}
              onChange={(e) => { setStatusFilter(e.target.value); setCurrentPage(1) }}
            >
              <option value="ALL">Tất cả trạng thái</option>
              <option value="active">Đang hoạt động</option>
              <option value="inactive">Tạm khóa</option>
            </select>
          </div>
          <div className="tenants-results-count">
            {filteredTenants.length} tenant
          </div>
        </div>
      </div>

      {/* ── Table Card ──────────────────────────────────── */}
      <div className="tenants-table-card">
        {isLoading ? (
          <div className="tenants-empty-state">
            <div className="tenants-spinner" />
            <span>Đang tải...</span>
          </div>
        ) : error ? (
          <div className="tenants-empty-state" style={{ color: '#ef4444' }}>
            <p>Không thể tải danh sách tenant. Vui lòng thử lại sau.</p>
          </div>
        ) : pagedTenants.length === 0 ? (
          <div className="tenants-empty-state">
            <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
              <circle cx="12" cy="8" r="4" /><path d="M4 20c0-4 3.6-7 8-7s8 3 8 7" />
            </svg>
            <p>Không tìm thấy kết quả nào{searchQuery ? ` cho "${searchQuery}"` : ''}.</p>
          </div>
        ) : (
          <table className="tenants-table">
            <thead>
              <tr>
                <th>Tenant</th>
                <th>Kho dữ liệu</th>
                <th>Loại lưu trữ</th>
                <th>Trạng thái</th>
                <th>Cập nhật lần cuối</th>
                <th style={{ textAlign: 'right' }}>Thao tác</th>
              </tr>
            </thead>
            <tbody>
              {pagedTenants.map((t) => {
                const isActive = t.status === 'active'
                const initials = getInitials(t.name)
                const avatarBg = getAvatarGradient(t.name)
                const isDeleting = deletingId === t.id

                return (
                  <tr key={t.id} className={isDeleting ? 'tenants-table__row--deleting' : ''}>
                    {/* Avatar + Name */}
                    <td>
                      <div className="tenants-member-cell">
                        <div
                          className="tenants-avatar"
                          style={{ background: avatarBg }}
                          title={t.name}
                        >
                          {initials}
                        </div>
                        <div className="tenants-member-info">
                          <span className="tenants-member-name">
                            {t.name}
                          </span>
                        </div>
                      </div>
                    </td>

                    {/* Collection */}
                    <td>
                      <span className="tenants-collection">{t.qdrantCollection}</span>
                    </td>

                    {/* Type Badge */}
                    <td>
                      <span className="tenants-type-badge">
                        <svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor">
                          <path d="M12 1L3 5v6c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V5l-9-4z" />
                        </svg>
                        Vector độc lập
                      </span>
                    </td>

                    {/* Status */}
                    <td>
                      <span className={`tenants-status ${isActive ? 'tenants-status--active' : 'tenants-status--inactive'}`}>
                        <span className="tenants-status__dot" />
                        {isActive ? 'Đang hoạt động' : 'Tạm khóa'}
                      </span>
                    </td>

                    {/* Updated At */}
                    <td>
                      <span className="tenants-date">{formatDate(t.updatedAt || t.createdAt)}</span>
                    </td>

                    {/* Actions */}
                    <td>
                      <div className="tenants-actions">
                        <button
                          className="tenants-action-btn tenants-action-btn--icon"
                          onClick={() => handleToggle(t)}
                          disabled={isDeleting}
                          title={isActive ? 'Tạm khóa tenant' : 'Kích hoạt lại tenant'}
                        >
                          {isActive ? (
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                              <rect x="3" y="11" width="18" height="11" rx="2" ry="2" /><path d="M7 11V7a5 5 0 0 1 10 0v4" />
                            </svg>
                          ) : (
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                              <rect x="3" y="11" width="18" height="11" rx="2" ry="2" /><path d="M7 11V7a5 5 0 0 1 9.9-1" />
                            </svg>
                          )}
                        </button>
                        <button
                          className="tenants-action-btn tenants-action-btn--icon tenants-action-btn--danger"
                          onClick={() => handleDelete(t)}
                          disabled={isDeleting}
                          title="Xóa tenant"
                        >
                          {isDeleting ? (
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="tenants-spin">
                              <circle cx="12" cy="12" r="10" strokeDasharray="32" strokeDashoffset="10" />
                            </svg>
                          ) : (
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                              <polyline points="3,6 5,6 21,6" />
                              <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
                              <path d="M10 11v6M14 11v6" />
                            </svg>
                          )}
                        </button>
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}

        {/* ── Pagination ─────────────────────────── */}
        {!isLoading && filteredTenants.length > PAGE_SIZE && (
          <div className="tenants-pagination">
            <span className="tenants-pagination__info">
              Hiển thị {(currentPage - 1) * PAGE_SIZE + 1}–{Math.min(currentPage * PAGE_SIZE, filteredTenants.length)} trong tổng số {filteredTenants.length} tenant
            </span>
            <div className="tenants-pagination__controls">
              <button
                className="tenants-pagination__btn"
                onClick={() => setCurrentPage((p) => Math.max(p - 1, 1))}
                disabled={currentPage === 1}
              >
                ← Trước
              </button>
              {Array.from({ length: totalPages }, (_, i) => i + 1).map((p) => (
                <button
                  key={p}
                  className={`tenants-pagination__btn ${p === currentPage ? 'tenants-pagination__btn--active' : ''}`}
                  onClick={() => setCurrentPage(p)}
                >
                  {p}
                </button>
              ))}
              <button
                className="tenants-pagination__btn"
                onClick={() => setCurrentPage((p) => Math.min(p + 1, totalPages))}
                disabled={currentPage === totalPages}
              >
                Tiếp theo →
              </button>
            </div>
          </div>
        )}
      </div>

      {/* ── Modal Create Tenant ─────────────────────────── */}
      <AddTenantModal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        onSubmit={handleAddTenant}
        isSubmitting={isSubmitting}
      />
    </div>
  )
}

import { useState, useEffect, useMemo } from 'react'
import { getUsers, createUser, deleteUser } from '../../../api/endpoints/users'
import { getTenants } from '../../../api/endpoints/tenants'
import { useAuth } from '../../../context/AuthContext'
import { AddUserModal } from '../components/AddUserModal'
import { BulkInviteModal } from '../components/BulkInviteModal'
import './UsersPage.css'

export function UsersPage() {
  const { user: currentUser } = useAuth()
  const isPlatformAdmin = currentUser?.role === 'PLATFORM_ADMIN'

  const [users, setUsers] = useState([])
  const [tenants, setTenants] = useState([])
  const [searchQuery, setSearchQuery] = useState('')
  const [roleFilter, setRoleFilter] = useState('ALL')
  const [tenantFilter, setTenantFilter] = useState('ALL')
  const [message, setMessage] = useState(null)
  const [isLoading, setIsLoading] = useState(true)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [isBulkModalOpen, setIsBulkModalOpen] = useState(false)
  const [currentPage, setCurrentPage] = useState(1)
  const [deletingId, setDeletingId] = useState(null)
  const PAGE_SIZE = 10

  const fetchTenants = async () => {
    try {
      const response = await getTenants()
      const rawTenants = response.tenants || response || []
      const mapped = rawTenants.map((t) => ({
        id: t.id || t.tenant_id,
        name: t.name || t.tenant_name,
        qdrant_collection: t.qdrant_collection || t.collection_name,
      }))
      setTenants(mapped)
    } catch (err) {
      console.warn('API getTenants failed:', err)
    }
  }

  const fetchUsers = async () => {
    setIsLoading(true)
    try {
      const response = await getUsers()
      const rawUsers = response.users || response || []
      const mapped = rawUsers.map((u) => ({
        id: u.user_id || u.id,
        username: u.user_name || u.username,
        name: u.full_name || u.name || u.user_name || u.username,
        email: u.email || null,
        role: u.role_name
          ? u.role_name.toUpperCase()
          : u.role
            ? u.role.toUpperCase()
            : 'USER',
        tenantId: u.tenant_id || u.tenantId || null,
        status: u.status || (u.is_active !== false ? 'active' : 'disabled'),
        createdAt: u.created_at || u.createdAt || new Date().toISOString(),
        updatedAt: u.updated_at || u.updatedAt || null,
      }))
      setUsers(mapped)
    } catch (err) {
      console.warn('API getUsers failed, using local fallback:', err)
      const stored = localStorage.getItem('ragnarok_mock_users')
      if (stored) {
        setUsers(JSON.parse(stored))
      } else {
        const seed = [
          { id: '1', username: 'tenant0', name: 'Tenant Admin', email: 'admin@devteam.local', role: 'TENANT_ADMIN', isActive: true, createdAt: '2026-07-01T10:00:00Z' },
          { id: '2', username: 'user0', name: 'User Zero', email: 'user0@devteam.local', role: 'USER', isActive: true, createdAt: '2026-07-02T14:30:00Z' },
        ]
        setUsers(seed)
      }
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    fetchUsers()
    fetchTenants()
  }, [])

  const tenantMap = useMemo(() => {
    const map = {}
    tenants.forEach((t) => {
      map[t.id] = t.name
    })
    return map
  }, [tenants])

  const filteredUsers = useMemo(() => {
    const q = searchQuery.toLowerCase()
    let result = users.filter((u) => {
      const matchSearch = !q ||
        u.name.toLowerCase().includes(q) ||
        u.username.toLowerCase().includes(q) ||
        (u.email || '').toLowerCase().includes(q)
      const matchRole = roleFilter === 'ALL' || u.role === roleFilter
      const matchTenant = tenantFilter === 'ALL' || u.tenantId === tenantFilter
      return matchSearch && matchRole && matchTenant
    })
    result.sort((a, b) => {
      if (a.status === 'disabled' && b.status !== 'disabled') return 1;
      if (a.status !== 'disabled' && b.status === 'disabled') return -1;
      return 0;
    });
    return result;
  }, [users, searchQuery, roleFilter, tenantFilter])

  const totalPages = Math.max(1, Math.ceil(filteredUsers.length / PAGE_SIZE))
  const pagedUsers = filteredUsers.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE)

  const stats = useMemo(() => ({
    total: users.length,
    admins: users.filter((u) => u.role === 'TENANT_ADMIN').length,
    regular: users.filter((u) => u.role === 'USER').length,
    active: users.filter((u) => u.status === 'active').length,
  }), [users])

  const showMessage = (type, text) => {
    setMessage({ type, text })
    setTimeout(() => setMessage(null), 4000)
  }

  const handleCopy = (text, type) => {
    navigator.clipboard.writeText(text)
    const label = type === 'Username' ? 'tên đăng nhập' : 'email'
    showMessage('success', `Đã sao chép ${label}`)
  }

  const handleAddUser = async (payload) => {
    setIsSubmitting(true)
    try {
      const targetTenantId = isPlatformAdmin ? payload.tenant_id : (currentUser?.tenant_id || currentUser?.tenantId)
      if (!targetTenantId) {
        throw new Error("Không xác định được tenant để gửi lời mời.")
      }

      const invitePayload = {
        invitees: [{
          email: payload.email,
          full_name: payload.name,
          username: payload.username
        }],
        role_name: payload.role
      }

      const { inviteUsers } = await import('../../../api/endpoints/tenants')
      await inviteUsers(targetTenantId, invitePayload)

      showMessage('success', `Lời mời đã được gửi đến "${payload.username}".`)
      setIsModalOpen(false)
      fetchUsers()
    } catch (err) {
      throw err
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleBulkInvite = async ({ formData, tenantId }) => {
    const targetTenantId = isPlatformAdmin ? tenantId : (currentUser?.tenant_id || currentUser?.tenantId);
    if (!targetTenantId) {
      throw new Error('Không xác định được tenant.');
    }

    // The query parameters for role and expiry must be added to the URL for the CSV endpoint
    // We already appended role_name and expires_in_hours in the formData in the modal,
    // but the CSV endpoint expects them as query parameters `?role_name=X&expires_in_hours=Y`
    // Let's modify the endpoint call in tenants.js or just pass the formData, but wait!
    // The endpoint is `router.post("/invitations/csv", ... role_name: str = Query(...))`
    // That means it expects query params!
    try {
      const { inviteUsersCSV } = await import('../../../api/endpoints/tenants');
      // Get the values before sending
      const role = formData.get('role_name') || 'USER';
      const expiry = formData.get('expires_in_hours') || '48';
      const response = await inviteUsersCSV(targetTenantId, role, expiry, formData);

      let msg = `Đã gửi lời mời đến ${response.total_invited} thành viên.`;
      if (response.total_skipped > 0) {
        msg += ` Bỏ qua ${response.total_skipped} email đã tồn tại.`;
      }

      showMessage('success', msg);
      setIsBulkModalOpen(false);
      fetchUsers();
    } catch (err) {
      throw err;
    }
  }

  const handleDelete = async (u) => {
    if (!window.confirm(`Tạm khóa tài khoản "${u.name}" (@${u.username})?\nNgười dùng này sẽ không thể đăng nhập cho đến khi được kích hoạt lại.`)) return
    setDeletingId(u.id)
    try {
      await deleteUser(u.id)
      showMessage('success', `Tài khoản "${u.name}" đã được tạm khóa.`)
      fetchUsers()
    } catch (err) {
      showMessage('error', typeof err === 'string' ? err : err?.message || 'Tạm khóa tài khoản thất bại.')
    } finally {
      setDeletingId(null)
    }
  }

  const handleRestore = async (u) => {
    if (!window.confirm(`Kích hoạt lại tài khoản "${u.name}" (@${u.username})?\nNgười dùng này sẽ có thể đăng nhập bình thường.`)) return
    try {
      const { restoreUser } = await import('../../../api/endpoints/users')
      await restoreUser(u.id)
      showMessage('success', `Tài khoản "${u.name}" đã được kích hoạt lại.`)
      fetchUsers()
    } catch (err) {
      showMessage('error', err?.message || 'Kích hoạt lại tài khoản thất bại.')
    }
  }

  const handleResendInvite = async (u) => {
    const tenantId = u.tenantId || currentUser?.tenant_id || currentUser?.tenantId;
    if (!tenantId) {
      showMessage('error', 'Không xác định được tenant.');
      return;
    }
    try {
      const { resendInvite } = await import('../../../api/endpoints/tenants');
      await resendInvite(tenantId, u.id);
      showMessage('success', `Lời mời đã được gửi lại đến ${u.email || u.username}.`);
      setUsers(prev => prev.map(user => user.id === u.id ? { ...user, status: 'pending_invitation' } : user));
    } catch (err) {
      showMessage('error', err.message || 'Gửi lại lời mời thất bại.');
    }
  }

  const handleRevokeInvite = async (u) => {
    if (!window.confirm(`Thu hồi lời mời của "${u.name}"?\nLink mời hiện tại sẽ bị hủy. Bạn có thể gửi lại lời mời mới bất cứ lúc nào.`)) return
    const tenantId = u.tenantId || currentUser?.tenant_id || currentUser?.tenantId;
    if (!tenantId) {
      showMessage('error', 'Không xác định được tenant.');
      return;
    }
    try {
      const { revokeInvite } = await import('../../../api/endpoints/tenants');
      await revokeInvite(tenantId, u.id);
      showMessage('success', `Lời mời của ${u.name} đã bị thu hồi.`);
      setUsers(prev => prev.map(user => user.id === u.id ? { ...user, status: 'revoked' } : user));
    } catch (err) {
      showMessage('error', err.message || 'Thu hồi lời mời thất bại.');
    }
  }

  const getInitials = (name) =>
    name.split(' ').map((p) => p[0]).filter(Boolean).slice(0, 2).join('').toUpperCase() || '?'

  const getAvatarGradient = (str) => {
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
    <div className="users-page">
      {/* ── Page Header ─────────────────────────────────── */}
      <div className="users-page__header">
        <div className="users-page__header-info">
          <h1 className="users-page__title">Thành viên</h1>
          <p className="users-page__subtitle">
            Mời thành viên, phân quyền và theo dõi trạng thái truy cập của người dùng.
          </p>
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
          {!isPlatformAdmin && (
            <button className="users-btn-primary" style={{ backgroundColor: '#0891b2' }} onClick={() => setIsBulkModalOpen(true)}>
              <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                <polyline points="17 8 12 3 7 8" />
                <line x1="12" y1="3" x2="12" y2="15" />
              </svg>
              Nhập từ CSV
            </button>
          )}
          <button className="users-btn-primary" style={{ backgroundColor: '#006c52' }} onClick={() => setIsModalOpen(true)}>
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
              <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
            </svg>
            Mời thành viên
          </button>
        </div>
      </div>

      {/* ── Toast ───────────────────────────────────────── */}
      {message && (
        <div className={`users-toast users-toast--${message.type}`}>
          <span className="users-toast__icon">{message.type === 'success' ? '✓' : '!'}</span>
          <span>{message.text}</span>
        </div>
      )}

      {/* ── Stats Row ───────────────────────────────────── */}
      <div className="users-stats">
        <div className="users-stat-card">
          <div className="users-stat-card__label">Tổng thành viên</div>
          <div className="users-stat-card__value">{stats.total}</div>
          <div className="users-stat-card__sub">tổng số tài khoản</div>
        </div>
        <div className="users-stat-card users-stat-card--green">
          <div className="users-stat-card__label">Quản trị viên</div>
          <div className="users-stat-card__value users-stat-card__value--green">{stats.admins}</div>
          <div className="users-stat-card__sub">có quyền quản trị tenant</div>
        </div>
        <div className="users-stat-card users-stat-card--indigo">
          <div className="users-stat-card__label">Người dùng</div>
          <div className="users-stat-card__value users-stat-card__value--indigo">{stats.regular}</div>
          <div className="users-stat-card__sub">tài khoản người dùng thông thường</div>
        </div>
        <div className="users-stat-card users-stat-card--emerald">
          <div className="users-stat-card__label">Đang hoạt động</div>
          <div className="users-stat-card__value users-stat-card__value--emerald">{stats.active}</div>
          <div className="users-stat-card__sub">
            {stats.total > 0 ? Math.round(stats.active / stats.total * 100) : 0}% đang hoạt động
          </div>
        </div>
      </div>

      {/* ── Toolbar ─────────────────────────────────────── */}
      <div className="users-toolbar">
        <div className="users-search">
          <svg className="users-search__icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
          <input
            className="users-search__input"
            type="text"
            placeholder="Tìm theo tên, email hoặc username..."
            value={searchQuery}
            onChange={(e) => { setSearchQuery(e.target.value); setCurrentPage(1) }}
          />
          {searchQuery && (
            <button className="users-search__clear" onClick={() => setSearchQuery('')}>✕</button>
          )}
        </div>

        <div className="users-filters">
          {/* Tenant filter dropdown for PLATFORM_ADMIN */}
          {isPlatformAdmin && tenants.length > 0 && (
            <div className="users-filter-group">
              <label className="users-filter-group__label">Tenant</label>
              <select
                className="users-filter-select"
                value={tenantFilter}
                onChange={(e) => { setTenantFilter(e.target.value); setCurrentPage(1) }}
              >
                <option value="ALL">Tất cả tenant</option>
                {tenants.map((t) => (
                  <option key={t.id} value={t.id}>{t.name}</option>
                ))}
              </select>
            </div>
          )}

          <div className="users-filter-group">
            <label className="users-filter-group__label">Vai trò</label>
            <select
              className="users-filter-select"
              value={roleFilter}
              onChange={(e) => { setRoleFilter(e.target.value); setCurrentPage(1) }}
            >
              <option value="ALL">Tất cả vai trò</option>
              <option value="TENANT_ADMIN">Tenant Admin</option>
              <option value="USER">User</option>
            </select>
          </div>
          <div className="users-results-count">
            {filteredUsers.length} thành viên
          </div>
        </div>
      </div>

      {/* ── Table ───────────────────────────────────────── */}
      <div className="users-table-card">
        {isLoading ? (
          <div className="users-empty-state">
            <div className="users-spinner" />
            <span>Đang tải...</span>
          </div>
        ) : pagedUsers.length === 0 ? (
          <div className="users-empty-state">
            <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
              <circle cx="12" cy="8" r="4" /><path d="M4 20c0-4 3.6-7 8-7s8 3 8 7" />
            </svg>
            <p>Không tìm thấy kết quả nào{searchQuery ? ` cho "${searchQuery}"` : ''}.</p>
          </div>
        ) : (
          <div className="users-table-wrapper">
            <table className="users-table">
              <thead>
                <tr>
                  <th>Thành viên</th>
                  <th>Tên đăng nhập</th>
                  <th>Email</th>
                  {isPlatformAdmin && <th>Tenant</th>}
                  <th>Vai trò</th>
                  <th>Trạng thái</th>
                  <th>Cập nhật lần cuối</th>
                  <th style={{ textAlign: 'right' }}>Thao tác</th>
                </tr>
              </thead>
              <tbody>
                {pagedUsers.map((u) => {
                  const isAdmin = u.role === 'TENANT_ADMIN'
                  const initials = getInitials(u.name)
                  const avatarBg = getAvatarGradient(u.username)
                  const isDeleting = deletingId === u.id
                  const isSelf = currentUser?.id === u.id

                  return (
                    <tr key={u.id} className={isDeleting ? 'users-table__row--deleting' : ''}>
                      {/* Avatar + Name */}
                      <td>
                        <div className="users-member-cell">
                          <div
                            className="users-avatar"
                            style={{ background: avatarBg }}
                            title={u.name}
                          >
                            {initials}
                          </div>
                          <div className="users-member-info">
                            <span className="users-member-name">
                              {u.name}
                              {isSelf && <span className="users-self-badge">Bạn</span>}
                            </span>
                          </div>
                        </div>
                      </td>

                      {/* Username */}
                      <td>
                        <div className="users-copyable">
                          <span className="users-username">@{u.username}</span>
                          <button className="users-copy-btn" onClick={() => handleCopy(u.username, 'Username')} title="Sao chép Username">
                            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
                          </button>
                        </div>
                      </td>

                      {/* Email */}
                      <td>
                        <div className="users-copyable">
                          <span className="users-email" style={{ maxWidth: '180px', display: 'inline-block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', verticalAlign: 'bottom' }}>{u.email || '—'}</span>
                          {u.email && (
                            <button className="users-copy-btn" onClick={() => handleCopy(u.email, 'Email')} title="Sao chép Email">
                              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
                            </button>
                          )}
                        </div>
                      </td>

                      {/* Tenant column for PLATFORM_ADMIN */}
                      {isPlatformAdmin && (
                        <td>
                          <span className="users-tenant-badge" style={{ maxWidth: '140px', display: 'inline-block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', verticalAlign: 'bottom' }}>
                            {tenantMap[u.tenantId] || u.tenantId || 'Platform'}
                          </span>
                        </td>
                      )}

                      {/* Role Badge */}
                      <td>
                        <span className={`users-role-badge ${isAdmin ? 'users-role-badge--admin' : 'users-role-badge--user'}`}>
                          {isAdmin ? (
                            <svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor">
                              <path d="M12 1L3 5v6c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V5l-9-4z" />
                            </svg>
                          ) : (
                            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                              <circle cx="12" cy="8" r="4" /><path d="M4 20c0-4 3.6-7 8-7s8 3 8 7" />
                            </svg>
                          )}
                          {isAdmin ? 'Quản trị viên' : 'Thành viên'}
                        </span>
                      </td>

                      {/* Status */}
                      <td>
                        <span className={`users-status users-status--${u.status.replace('_', '-')}`}>
                          <span className="users-status__dot" />
                          {u.status === 'active' ? 'Hoạt động' :
                            u.status === 'pending_invitation' ? 'Chờ kích hoạt' :
                              u.status === 'revoked' ? 'Đã thu hồi' :
                                u.status === 'expired' ? 'Hết hạn' :
                                  u.status === 'disabled' ? 'Đã tạm khóa' : 'Không hoạt động'}
                        </span>
                      </td>

                      {/* Updated At */}
                      <td>
                        <span className="users-date">{formatDate(u.updatedAt || u.createdAt)}</span>
                      </td>

                      {/* Actions */}
                      <td>
                        <div className="users-actions">
                          {['pending_invitation', 'expired', 'revoked'].includes(u.status) && (
                            <>
                              <button
                                className="users-action-btn users-action-btn--icon"
                                onClick={() => handleResendInvite(u)}
                                title="Gửi lại lời mời"
                              >
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                  <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
                                </svg>
                              </button>
                              {u.status !== 'revoked' && (
                                <button
                                  className="users-action-btn users-action-btn--icon users-action-btn--danger"
                                  onClick={() => handleRevokeInvite(u)}
                                  title="Thu hồi lời mời"
                                >
                                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                    <circle cx="12" cy="12" r="10" />
                                    <line x1="15" y1="9" x2="9" y2="15" />
                                    <line x1="9" y1="9" x2="15" y2="15" />
                                  </svg>
                                </button>
                              )}
                            </>
                          )}

                          {!['pending_invitation', 'expired', 'revoked', 'disabled'].includes(u.status) && (
                            <button
                              className="users-action-btn users-action-btn--icon users-action-btn--danger"
                              onClick={() => handleDelete(u)}
                              disabled={isDeleting || isSelf}
                              title={isSelf ? 'Không thể khóa tài khoản của chính bạn' : 'Tạm khóa tài khoản'}
                            >
                              {isDeleting ? (
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="users-spin">
                                  <circle cx="12" cy="12" r="10" strokeDasharray="32" strokeDashoffset="10" />
                                </svg>
                              ) : (
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                  <polyline points="3,6 5,6 21,6" />
                                  <path d="M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6" />
                                  <path d="M10 11v6M14 11v6" />
                                </svg>
                              )}
                            </button>
                          )}
                          {u.status === 'disabled' && (
                            <button
                              className="users-action-btn users-action-btn--icon"
                              onClick={() => handleRestore(u)}
                              title="Kích hoạt lại tài khoản"
                            >
                              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" />
                                <path d="M3 3v5h5" />
                              </svg>
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}

        {/* ── Pagination ─────────────────────────── */}
        {!isLoading && filteredUsers.length > PAGE_SIZE && (
          <div className="users-pagination">
            <span className="users-pagination__info">
              Hiển thị {(currentPage - 1) * PAGE_SIZE + 1}–{Math.min(currentPage * PAGE_SIZE, filteredUsers.length)} trong tổng số {filteredUsers.length} thành viên
            </span>
            <div className="users-pagination__controls">
              <button
                className="users-pagination__btn"
                onClick={() => setCurrentPage((p) => Math.max(p - 1, 1))}
                disabled={currentPage === 1}
              >
                ← Trước
              </button>
              {Array.from({ length: totalPages }, (_, i) => i + 1).map((p) => (
                <button
                  key={p}
                  className={`users-pagination__btn users-pagination__btn--page ${p === currentPage ? 'users-pagination__btn--active' : ''}`}
                  onClick={() => setCurrentPage(p)}
                >
                  {p}
                </button>
              ))}
              <button
                className="users-pagination__btn"
                onClick={() => setCurrentPage((p) => Math.min(p + 1, totalPages))}
                disabled={currentPage === totalPages}
              >
                Tiếp theo →
              </button>
            </div>
          </div>
        )}
      </div>

      {/* ── Modals ───────────────────────────────────────── */}
      <AddUserModal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        onSubmit={handleAddUser}
        isSubmitting={isSubmitting}
        tenants={tenants}
        isPlatformAdmin={isPlatformAdmin}
      />

      <BulkInviteModal
        isOpen={isBulkModalOpen}
        onClose={() => setIsBulkModalOpen(false)}
        onSubmit={handleBulkInvite}
        tenants={tenants}
        isPlatformAdmin={isPlatformAdmin}
      />
    </div>
  )
}

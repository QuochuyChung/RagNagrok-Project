import { useState } from 'react'
import { useAuth } from '../../../context/AuthContext'
import { useChat } from '../../../context/ChatContext'

export function Sidebar({
  routes = [],
  currentPath = '/',
  isCollapsed = false,
  onToggleCollapse
}) {
  const { user, logout } = useAuth()
  const {
    conversations = [],
    currentConversationId,
    selectConversation,
    deleteConversation,
    startNewChat
  } = useChat()

  const [showSearch, setShowSearch] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')

  const navigate = (path) => {
    window.history.pushState({}, '', path)
    window.dispatchEvent(new PopStateEvent('popstate'))
  }

  const handleNewChatClick = () => {
    if (currentPath !== '/chat') {
      navigate('/chat')
    }
    startNewChat()
  }

  const handleConvoClick = (id) => {
    if (currentPath !== '/chat') {
      navigate(`/chat?id=${id}`)
    } else {
      selectConversation(id)
    }
  }

  const userRole = (user?.role || '').toUpperCase()
  const defaultPath = (userRole === 'PLATFORM_ADMIN' || userRole === 'TENANT_ADMIN') ? '/dashboard' : '/chat'

  const currentRoutePath = currentPath

  const filteredConversations = conversations.filter((convo) =>
    convo.title.toLowerCase().includes(searchQuery.toLowerCase())
  )

  return (
    <>
      {!isCollapsed && <div className="sidebar-backdrop" onClick={onToggleCollapse} />}

      <aside className="sidebar">
        <div className="sidebar-top">
          <div className="sidebar-brand-wrapper" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '28px' }}>
            <div
              className="sidebar-brand"
              style={{ margin: 0, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '10px' }}
              onClick={() => navigate(defaultPath)}
              title="Về trang chủ"
            >
              <img src="/logo.jpg" alt="Ragnarok" className="sidebar-logo-icon" />
              {!isCollapsed && <span>Ragnarok AI</span>}
            </div>
            <button
              className="sidebar-toggle-btn"
              onClick={onToggleCollapse}
              style={{ background: 'transparent', border: 'none', color: 'var(--sidebar-muted)', cursor: 'pointer', padding: '6px', borderRadius: '8px', display: 'flex', alignItems: 'center', justifyContent: 'center', transition: 'all 150ms ease' }}
            >
              <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
                <line x1="9" y1="3" x2="9" y2="21" />
              </svg>
            </button>
          </div>

          {user && (
            <>
              {userRole !== 'PLATFORM_ADMIN' && (
                <button className="new-chat-btn" onClick={handleNewChatClick} title="Đoạn chat mới">
                  <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
                    <path d="M18.5 2.5a2.121 2.121 0 1 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
                  </svg>
                  {!isCollapsed && <span>Đoạn chat mới</span>}
                </button>
              )}

              {!isCollapsed && (
                <>
                  {/* Menu điều hướng phụ theo phân quyền */}
                  <div className="sidebar-nav-menu" style={{ display: 'grid', gap: '2px', marginBottom: '24px' }}>
                    {/* Cho phép tìm kiếm chat đối với User & Tenant Admin */}
                    {userRole !== 'PLATFORM_ADMIN' && (
                      <>
                        <div
                          className={`sidebar-menu-item ${showSearch ? 'active' : ''}`}
                          onClick={() => setShowSearch(!showSearch)}
                        >
                          <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="menu-icon">
                            <circle cx="11" cy="11" r="8" />
                            <line x1="21" y1="21" x2="16.65" y2="16.65" />
                          </svg>
                          <span>Tìm kiếm đoạn chat</span>
                        </div>

                        {showSearch && (
                          <div style={{ padding: '4px 12px 12px 12px' }}>
                            <input
                              type="text"
                              value={searchQuery}
                              onChange={(e) => setSearchQuery(e.target.value)}
                              placeholder="Tìm cuộc trò chuyện..."
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
                                boxSizing: 'border-box'
                              }}
                              autoFocus
                            />
                          </div>
                        )}
                      </>
                    )}

                    {/* Platform Admin và Tenant Admin xem được Dashboard */}
                    {(userRole === 'TENANT_ADMIN' || userRole === 'PLATFORM_ADMIN') && (
                      <div
                        className={`sidebar-menu-item ${currentRoutePath === '/dashboard' ? 'active' : ''}`}
                        onClick={() => navigate('/dashboard')}
                      >
                        <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="menu-icon">
                          <rect x="3" y="4" width="18" height="16" rx="2" />
                          <line x1="9" y1="9" x2="9" y2="15" />
                          <line x1="15" y1="11" x2="15" y2="15" />
                        </svg>
                        <span>Dashboard</span>
                      </div>
                    )}

                    {/* Chỉ Tenant Admin quản lý được Documents */}
                    {userRole === 'TENANT_ADMIN' && (
                      <div
                        className={`sidebar-menu-item ${currentRoutePath === '/documents' ? 'active' : ''}`}
                        onClick={() => navigate('/documents')}
                      >
                        <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="menu-icon">
                          <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z" />
                          <path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z" />
                        </svg>
                        <span>Thư viện tài liệu</span>
                      </div>
                    )}

                    {/* Platform Admin và Tenant Admin quản lý được Users */}
                    {(userRole === 'TENANT_ADMIN' || userRole === 'PLATFORM_ADMIN') && (
                      <div
                        className={`sidebar-menu-item ${currentRoutePath === '/users' ? 'active' : ''}`}
                        onClick={() => navigate('/users')}
                      >
                        <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="menu-icon">
                          <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
                          <circle cx="9" cy="7" r="4" />
                          <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
                          <path d="M16 3.13a4 4 0 0 1 0 7.75" />
                        </svg>
                        <span>Quản lý thành viên</span>
                      </div>
                    )}

                    {/* Chỉ Platform Admin quản lý được Tenants */}
                    {userRole === 'PLATFORM_ADMIN' && (
                      <div
                        className={`sidebar-menu-item ${currentRoutePath === '/tenants' ? 'active' : ''}`}
                        onClick={() => navigate('/tenants')}
                      >
                        <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="menu-icon">
                          <rect x="3" y="3" width="7" height="7" />
                          <rect x="14" y="3" width="7" height="7" />
                          <rect x="14" y="14" width="7" height="7" />
                          <rect x="3" y="14" width="7" height="7" />
                        </svg>
                        <span>Quản lý Tenants</span>
                      </div>
                    )}
                  </div>

                  {userRole !== 'PLATFORM_ADMIN' && filteredConversations.length > 0 && (
                    <>
                      <div className="sidebar-convos-header">Trò chuyện gần đây</div>
                      <div className="sidebar-convo-list">
                        {filteredConversations.map((convo) => {
                          const isActive = currentConversationId === convo.id && currentPath === '/chat'
                          return (
                            <div
                              key={convo.id}
                              className={`sidebar-convo-item ${isActive ? 'active' : ''}`}
                              onClick={() => handleConvoClick(convo.id)}
                            >
                              <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="convo-icon">
                                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
                              </svg>
                              <span className="convo-title">{convo.title}</span>
                              <button
                                className="convo-delete-btn"
                                onClick={(e) => deleteConversation(convo.id, e)}
                                title="Xóa đoạn chat"
                              >
                                <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                                  <polyline points="3 6 5 6 21 6" />
                                  <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                                </svg>
                              </button>
                            </div>
                          )
                        })}
                      </div>
                    </>
                  )}
                </>
              )}
            </>
          )}
        </div>

        {user && (
          <div className="sidebar-footer">
            <div className="user-profile" onClick={() => navigate(defaultPath)} style={{ cursor: 'pointer' }} title="Về trang chủ">
              <div className="user-avatar" style={{ background: user.avatarBg }}>
                {user.initials}
              </div>
              {!isCollapsed && (
                <div className="user-details">
                  <div className="user-name">{user.name}</div>
                  <div className="user-role">{user.roleName}</div>
                </div>
              )}
            </div>
            <button className="logout-btn" onClick={logout} title="Đăng xuất">
              <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
                <polyline points="16 17 21 12 16 7" />
                <line x1="21" y1="12" x2="9" y2="12" />
              </svg>
            </button>
          </div>
        )}
      </aside>
    </>
  )
}

import { useState, useEffect } from 'react'
import { TenantProvider } from './context/TenantContext'
import { AuthProvider, useAuth } from './context/AuthContext'
import { ChatProvider } from './context/ChatContext'
import { Sidebar } from './shared/components/layout/Sidebar'
import { routes } from './router/routes'
import { LoginPage } from './features/auth/pages/LoginPage'
import { ForgotPasswordPage } from './features/auth/pages/ForgotPasswordPage'
import { ResetPasswordPage } from './features/auth/pages/ResetPasswordPage'
import { AcceptInvitePage } from './features/auth/pages/AcceptInvitePage'

function AppContent() {
  const { user, loading } = useAuth()
  const [currentPath, setCurrentPath] = useState(window.location.pathname)
  // Trên mobile (<900px, khớp globals.css) sidebar giờ là overlay nổi thay vì
  // ẩn hẳn, nên phải khởi đầu ở trạng thái thu gọn để không che kín màn hình.
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(() => window.innerWidth <= 900)

  useEffect(() => {
    const handleLocationChange = () => {
      const path = window.location.pathname
      if (!user) {
        setCurrentPath(path)
        return
      }

      const route = routes.find((r) => r.path === path)
      const userRole = (user.role || '').toUpperCase()

      // Fallback path based on role
      const defaultPath =
        userRole === 'PLATFORM_ADMIN' || userRole === 'TENANT_ADMIN'
          ? '/dashboard'
          : '/chat'

      if (path === '/' || path === '' || !route) {
        // Redirect if visiting root or path does not exist
        window.history.replaceState({}, '', defaultPath)
        setCurrentPath(defaultPath)
      } else if (route.roles && !route.roles.includes(userRole)) {
        // Redirect if role is not allowed to view the route
        window.history.replaceState({}, '', defaultPath)
        setCurrentPath(defaultPath)
      } else {
        // Preserve valid path on page refresh or direct navigation
        setCurrentPath(path)
      }
    }

    handleLocationChange()

    window.addEventListener('popstate', handleLocationChange)
    return () => window.removeEventListener('popstate', handleLocationChange)
  }, [user])

  if (loading) {
    return (
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        minHeight: '100vh',
        backgroundColor: '#ffffff',
        color: '#171717',
        fontFamily: 'Inter, sans-serif'
      }}>
        <div className="login-spinner" style={{ width: '40px', height: '40px', borderWidth: '3px' }}></div>
      </div>
    )
  }

  if (!user) {
    if (currentPath === '/forgot-password') return <ForgotPasswordPage />
    if (currentPath === '/reset-password') return <ResetPasswordPage />
    if (currentPath === '/accept-invite') return <AcceptInvitePage />
    return <LoginPage />
  }

  // Find routing element based on current path, default to first route (HealthPage) if not found
  const currentRoute = routes.find((route) => route.path === currentPath) || routes[0]
  const ActivePage = currentRoute.element

  return (
    <div className={`app-shell ${isSidebarCollapsed ? 'sidebar-collapsed' : ''}`}>
      <Sidebar
        routes={routes}
        currentPath={currentPath}
        isCollapsed={isSidebarCollapsed}
        onToggleCollapse={() => setIsSidebarCollapsed((v) => !v)}
      />
      <main className="app-main">
        <ActivePage />
      </main>
    </div>
  )
}

function App() {
  return (
    <AuthProvider>
      <TenantProvider>
        <ChatProvider>
          <AppContent />
        </ChatProvider>
      </TenantProvider>
    </AuthProvider>
  )
}

export default App


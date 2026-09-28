import { useState } from 'react'
import { useAuth } from '../../../context/AuthContext'
import '../styles/LoginPage.css'

export function LoginPage() {
  const { login } = useAuth()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [isSubmitting, setIsSubmitting] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError(null)
    setIsSubmitting(true)

    try {
      await login(username, password)
      // Redirect or state change is handled automatically by AuthContext & App.jsx
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Đăng nhập không thành công, vui lòng thử lại.')
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleSocialLogin = async (provider) => {
    setError(null)
    setIsSubmitting(true)
    try {
      // Simulate OAuth login
      await login(`${provider.toLowerCase()}_user`, 'social_password_123')
    } catch (err) {
      setError('Đăng nhập qua mạng xã hội thất bại.')
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="login-container">
      <div className="login-card">
        <div className="login-header">
          <div className="login-logo-wrapper">
            <img 
              src="/logo.jpg" 
              alt="Ragnarok Project Logo" 
              className="login-logo" 
              onError={(e) => {
                // Fallback inside case of load errors (like missing path)
                e.target.src = 'https://api.dicebear.com/7.x/initials/svg?seed=R&radius=50'
              }}
            />
          </div>
          <h1 className="login-title">Chào mừng quay trở lại</h1>
          <p className="login-subtitle">Đăng nhập với tài khoản Ragnarok để tiếp tục</p>
        </div>

        {error && (
          <div className="login-error">
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="login-form">
          <div className="login-input-wrapper">
            <input
              type="text"
              placeholder="Tên đăng nhập hoặc email"
              className="login-input"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              disabled={isSubmitting}
              required
              autoFocus
            />
          </div>
          
          <div className="login-input-wrapper">
            <input
              type="password"
              placeholder="Mật khẩu"
              className="login-input"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={isSubmitting}
              required
            />
          </div>

          <div style={{ textAlign: 'right', marginBottom: '16px' }}>
            <a href="/forgot-password" style={{ fontSize: '14px', color: '#10a37f', textDecoration: 'none', fontWeight: 500 }}>
              Quên mật khẩu?
            </a>
          </div>

          <button type="submit" className="login-btn" disabled={isSubmitting}>
            {isSubmitting ? (
              <>
                <div className="login-spinner"></div>
                <span>Đang xử lý...</span>
              </>
            ) : (
              <span>Tiếp tục</span>
            )}
          </button>
        </form>

        <p className="login-signup-text">
          Chưa có tài khoản? 
          <span className="login-link" onClick={() => setError('Đăng ký tài khoản hiện không khả dụng. Vui lòng liên hệ Admin.')}>
            Đăng ký
          </span>
        </p>

        <div className="login-divider">Hoặc</div>

        <button className="login-social-btn" onClick={() => handleSocialLogin('Google')} disabled={isSubmitting}>
          <span className="login-social-icon">
            <svg viewBox="0 0 24 24" width="18" height="18">
              <path fill="#EA4335" d="M12 5.04c1.66 0 3.2.57 4.38 1.69l3.27-3.27C17.68 1.54 14.98 1 12 1 7.35 1 3.37 3.67 1.39 7.56l3.85 2.99c.92-2.77 3.51-4.51 6.76-4.51z"/>
              <path fill="#4285F4" d="M23.49 12.27c0-.81-.07-1.59-.2-2.36H12v4.51h6.43c-.28 1.44-1.09 2.67-2.3 3.48l3.57 2.77c2.08-1.92 3.29-4.75 3.29-8.4z"/>
              <path fill="#FBBC05" d="M5.24 10.55c-.24-.72-.38-1.5-.38-2.3s.14-1.58.38-2.3L1.39 2.96C.5 4.77 0 6.81 0 8.97s.5 4.2 1.39 6.01l3.85-2.99c-.24-.72-.38-1.5-.38-2.3s.14-1.58.38-2.3z"/>
              <path fill="#34A853" d="M12 23c3.24 0 5.97-1.07 7.96-2.92l-3.57-2.77c-1.12.75-2.55 1.19-4.39 1.19-3.25 0-5.84-1.74-6.76-4.51L1.39 16.98C3.37 20.87 7.35 23 12 23z"/>
            </svg>
          </span>
          <span>Tiếp tục với Google</span>
        </button>

        <button className="login-social-btn" onClick={() => handleSocialLogin('Microsoft')} disabled={isSubmitting}>
          <span className="login-social-icon">
            <svg viewBox="0 0 23 23" width="18" height="18">
              <rect x="0" y="0" width="10.5" height="10.5" fill="#f25022" />
              <rect x="11.5" y="0" width="10.5" height="10.5" fill="#7fba00" />
              <rect x="0" y="11.5" width="10.5" height="10.5" fill="#00a4ef" />
              <rect x="11.5" y="11.5" width="10.5" height="10.5" fill="#ffb900" />
            </svg>
          </span>
          <span>Tiếp tục với Microsoft Account</span>
        </button>

        <button className="login-social-btn" onClick={() => handleSocialLogin('Apple')} disabled={isSubmitting}>
          <span className="login-social-icon">
            <svg viewBox="0 0 170 170" width="18" height="18" fill="currentColor">
              <path d="M150.37 130.25c-2.45 5.66-5.35 10.87-8.71 15.66-4.58 6.53-8.33 11.05-11.22 13.56-4.48 4.12-9.28 6.23-14.42 6.35-3.69 0-8.14-1.05-13.32-3.18-5.19-2.12-9.97-3.17-14.34-3.17-4.58 0-9.49 1.05-14.75 3.17-5.26 2.13-9.5 3.24-12.74 3.35-4.35.13-9.13-1.76-14.34-5.66-3.79-2.88-7.86-7.75-12.21-14.61-9.97-15.68-14.96-32.96-14.96-51.8 0-16.1 4.35-29.69 13.06-40.79 8.7-11.1 19.34-16.73 31.91-16.85 5.35 0 10.97 1.54 16.85 4.63 5.88 3.09 9.87 4.63 11.97 4.63 1.88 0 5.64-1.42 11.28-4.24 5.64-2.83 10.96-4.3 15.96-4.43 14.13-.25 25.1 4.7 32.91 14.86-11.97 7.3-17.84 17.15-17.62 29.54.22 10.27 4.13 18.84 11.73 25.7 7.6 6.87 16.5 10.5 26.68 10.9 2.29-6.4 5.16-12.63 8.6-18.72zm-35.09-122.95c0 8.04-2.85 15.34-8.54 21.89-5.69 6.55-12.63 10.6-20.81 12.16.22-7.53 3.03-14.77 8.44-21.73 5.41-6.95 12.44-11.28 21.09-12.98.66 7.55-.18 14.44-2.18 20.66z" />
            </svg>
          </span>
          <span>Tiếp tục với Apple</span>
        </button>
      </div>

      <div className="login-footer">
        <div className="login-footer-links">
          <a href="#" className="login-footer-link" onClick={(e) => e.preventDefault()}>Điều khoản dịch vụ</a>
          <a href="#" className="login-footer-link" onClick={(e) => e.preventDefault()}>Chính sách bảo mật</a>
        </div>
        <div>© 2026 Ragnarok RAG. All rights reserved.</div>
      </div>
    </div>
  )
}

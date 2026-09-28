import { useState, useEffect } from 'react'
import { forgotPassword } from '../../../api/endpoints/auth'
import '../styles/LoginPage.css'

export function ForgotPasswordPage() {
  const [email, setEmail] = useState('')
  const [status, setStatus] = useState('idle') // idle, submitting, success
  const [error, setError] = useState(null)
  const [countdown, setCountdown] = useState(5)

  useEffect(() => {
    let timer;
    if (status === 'success') {
      timer = setInterval(() => {
        setCountdown((prev) => {
          if (prev <= 1) {
            clearInterval(timer)
            window.history.replaceState({}, '', '/')
            window.dispatchEvent(new Event('popstate'))
            return 0
          }
          return prev - 1
        })
      }, 1000)
    }
    return () => clearInterval(timer)
  }, [status])

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError(null)
    setStatus('submitting')

    try {
      await forgotPassword(email)
      setStatus('success')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Đã có lỗi xảy ra. Vui lòng thử lại.')
      setStatus('idle')
    }
  }

  return (
    <div className="login-container">
      <div className="login-card">


        {error && (
          <div className="login-error" style={{ display: 'flex', alignItems: 'flex-start', gap: '8px' }}>
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" style={{ flexShrink: 0, marginTop: '2px' }}>
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
            <span style={{ flex: 1, textAlign: 'left' }}>{error}</span>
          </div>
        )}

        {status === 'success' ? (
          <div style={{ position: 'fixed', inset: 0, backgroundColor: '#f0f9f6', color: '#003828', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', zIndex: 9999 }}>
            <div style={{ width: '100%', maxWidth: '540px', background: '#ffffff', border: '1px solid #c2dfd5', borderRadius: '12px', padding: '40px', textAlign: 'center', boxShadow: '0 4px 24px -1px rgba(0, 56, 40, 0.05)', display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
              <div style={{ marginBottom: '32px' }}>
                <div style={{ border: '2px solid #5bdcb0', borderRadius: '12px', padding: '12px', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', background: 'rgba(91, 220, 176, 0.05)' }}>
                  <svg viewBox="0 0 24 24" width="40" height="40" fill="none" stroke="#5bdcb0" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
                    <polyline points="22 4 12 14.01 9 11.01" />
                  </svg>
                </div>
              </div>
              <h1 style={{ fontSize: '32px', fontWeight: '600', color: '#003828', marginBottom: '24px', letterSpacing: '-0.01em', fontFamily: 'Geist, sans-serif' }}>
                Đã gửi liên kết khôi phục
              </h1>
              <div style={{ marginBottom: '40px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
                <p style={{ fontSize: '16px', color: '#2d5a4f', lineHeight: '1.6' }}>
                  Nếu email hợp lệ, một liên kết khôi phục đã được gửi đến <span style={{ backgroundColor: '#e6f4ef', padding: '2px 6px', borderRadius: '4px', fontFamily: 'monospace', color: '#003828' }}>{email}</span>.
                </p>
                <p style={{ fontSize: '14px', color: '#2d5a4f', opacity: 0.7, maxWidth: '400px', margin: '0 auto' }}>
                  Vui lòng kiểm tra hộp thư của bạn, bao gồm cả thư mục spam nếu bạn không thấy email trong vài phút.
                </p>
              </div>
              <button 
                style={{ width: '100%', maxWidth: '300px', backgroundColor: '#5bdcb0', color: '#003828', padding: '14px 24px', border: 'none', borderRadius: '8px', fontSize: '14px', fontWeight: '700', letterSpacing: '0.1em', textTransform: 'uppercase', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px', transition: 'all 0.3s ease' }}
                onClick={() => {
                  window.history.replaceState({}, '', '/')
                  window.dispatchEvent(new Event('popstate'))
                }}
                onMouseOver={(e) => { e.currentTarget.style.backgroundColor = '#4ed1a5'; e.currentTarget.style.boxShadow = '0 4px 12px rgba(91, 220, 176, 0.3)' }}
                onMouseOut={(e) => { e.currentTarget.style.backgroundColor = '#5bdcb0'; e.currentTarget.style.boxShadow = 'none' }}
              >
                <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M19 12H5M12 19l-7-7 7-7" />
                </svg>
                Quay lại đăng nhập ({countdown}s)
              </button>
            </div>
            <div style={{ position: 'absolute', bottom: '40px', width: '100%', textAlign: 'center' }}>
              <p style={{ fontSize: '11px', color: '#2d5a4f', opacity: 0.5, letterSpacing: '0.15em', textTransform: 'uppercase', fontWeight: '700' }}>
                © 2026 RAGNAROK PLATFORM. ALL RIGHTS RESERVED.
              </p>
            </div>
          </div>
        ) : (
          <>
            <div className="login-header">
              <div className="login-logo-wrapper">
                <img 
                  src="/logo.jpg" 
                  alt="Ragnarok Project Logo" 
                  className="login-logo" 
                  onError={(e) => {
                    e.target.src = 'https://api.dicebear.com/7.x/initials/svg?seed=R&radius=50'
                  }}
                />
              </div>
              <h1 className="login-title">Quên mật khẩu</h1>
              <p className="login-subtitle">
                Nhập email của bạn và chúng tôi sẽ gửi liên kết để đặt lại mật khẩu.
              </p>
            </div>
            <form onSubmit={handleSubmit} className="login-form">
            <div className="login-input-wrapper">
              <input
                type="email"
                placeholder="Địa chỉ email"
                className="login-input"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                disabled={status === 'submitting'}
                required
                autoFocus
              />
            </div>

            <button type="submit" className="login-btn" disabled={status === 'submitting' || !email}>
              {status === 'submitting' ? (
                <>
                  <div className="login-spinner"></div>
                  <span>Đang gửi...</span>
                </>
              ) : (
                <span>Gửi liên kết khôi phục</span>
              )}
            </button>
            
            <div style={{ textAlign: 'center', marginTop: '16px' }}>
              <button 
                type="button"
                style={{ background: 'none', border: 'none', color: '#444748', cursor: 'pointer', fontSize: '14px', textDecoration: 'underline' }}
                onClick={() => {
                  window.history.replaceState({}, '', '/')
                  window.dispatchEvent(new Event('popstate'))
                }}
              >
                Quay lại đăng nhập
              </button>
            </div>
          </form>
          </>
        )}

      </div>
    </div>
  )
}

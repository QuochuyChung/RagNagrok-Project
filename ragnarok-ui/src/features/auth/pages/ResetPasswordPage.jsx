import { useState, useEffect } from 'react'
import { validateResetToken, resetPassword } from '../../../api/endpoints/auth'
import '../styles/LoginPage.css'

export function ResetPasswordPage() {
  const [token, setToken] = useState('')
  const [validation, setValidation] = useState({ status: 'checking', data: null, error: null })
  
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  
  const [status, setStatus] = useState('idle') // idle, submitting, success
  const [submitError, setSubmitError] = useState(null)
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

  useEffect(() => {
    const searchParams = new URLSearchParams(window.location.search)
    const t = searchParams.get('token')
    if (!t) {
      setValidation({ status: 'error', data: null, error: 'Không tìm thấy mã xác nhận trong URL.' })
      return
    }
    setToken(t)
    
    validateResetToken(t)
      .then(res => {
        if (res.valid) {
          setValidation({ status: 'success', data: res, error: null })
        } else {
          setValidation({ status: 'error', data: null, error: res.message || 'Liên kết không hợp lệ.' })
        }
      })
      .catch(err => {
        setValidation({ status: 'error', data: null, error: 'Lỗi kết nối máy chủ.' })
      })
  }, [])

  const calculateStrength = (pwd) => {
    if (!pwd) return 0
    let score = 0
    if (pwd.length >= 8) score += 1
    if (pwd.match(/[A-Z]/)) score += 1
    if (pwd.match(/[0-9]/)) score += 1
    if (pwd.match(/[^A-Za-z0-9]/)) score += 1
    return score
  }

  const strength = calculateStrength(newPassword)
  let strengthLabel = 'Yếu'
  let strengthColor = '#ba1a1a'
  if (strength === 2 || strength === 3) {
    strengthLabel = 'Trung bình'
    strengthColor = '#f59e0b'
  } else if (strength >= 4) {
    strengthLabel = 'Mạnh'
    strengthColor = '#10b981'
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setSubmitError(null)
    
    if (newPassword.length < 8) {
      setSubmitError('Mật khẩu phải có ít nhất 8 ký tự.')
      return
    }
    if (newPassword !== confirmPassword) {
      setSubmitError('Mật khẩu xác nhận không khớp.')
      return
    }

    setStatus('submitting')
    try {
      await resetPassword({ token, new_password: newPassword, confirm_password: confirmPassword })
      setStatus('success')
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : 'Đã có lỗi xảy ra. Vui lòng thử lại.')
      setStatus('idle')
    }
  }

  if (validation.status === 'checking') {
    return (
      <div className="login-container">
        <div className="login-card" style={{ display: 'flex', justifyContent: 'center', padding: '48px' }}>
          <div className="login-spinner"></div>
        </div>
      </div>
    )
  }

  if (validation.status === 'error') {
    return (
      <div className="login-container">
        <div className="login-card">
          <div className="login-header">
            <h1 className="login-title">Liên kết không hợp lệ</h1>
          </div>
          <div className="login-error" style={{ justifyContent: 'center', marginBottom: '24px' }}>
            <span>{validation.error}</span>
          </div>
          <button 
            className="login-btn" 
            onClick={() => {
              window.history.replaceState({}, '', '/forgot-password')
              window.dispatchEvent(new Event('popstate'))
            }}
          >
            Yêu cầu liên kết mới
          </button>
        </div>
      </div>
    )
  }

  if (status === 'success') {
    return (
      <div style={{ position: 'fixed', inset: 0, backgroundColor: '#f8faf9', color: '#002116', display: 'flex', flexDirection: 'column', zIndex: 9999 }}>
        <header style={{ width: '100%', position: 'sticky', top: 0, backgroundColor: 'rgba(255, 255, 255, 0.5)', backdropFilter: 'blur(12px)', borderBottom: '1px solid rgba(0, 108, 80, 0.08)', zIndex: 50 }}>
          <nav style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '16px 24px', maxWidth: '1280px', margin: '0 auto', width: '100%' }}>
            <div style={{ fontSize: '24px', fontWeight: 'bold', color: '#006c50', letterSpacing: '-0.02em', fontFamily: 'Geist, sans-serif' }}>RAGnarok</div>
            <svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="#006c50" strokeWidth="2" style={{ cursor: 'pointer' }}>
              <circle cx="12" cy="12" r="10" /><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3" /><line x1="12" y1="17" x2="12.01" y2="17" />
            </svg>
          </nav>
        </header>

        <main style={{ flexGrow: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '32px 16px', position: 'relative' }}>
          <div style={{ width: '100%', maxWidth: '600px', display: 'flex', flexDirection: 'column', alignItems: 'center', textAlign: 'center', zIndex: 10 }}>
            <div style={{ marginBottom: '32px' }}>
              <div style={{ width: '80px', height: '80px', borderRadius: '16px', backgroundColor: 'rgba(91, 220, 176, 0.2)', border: '1px solid rgba(0, 108, 80, 0.1)', display: 'flex', alignItems: 'center', justifyContent: 'center', boxShadow: '0 8px 30px rgba(0, 108, 80, 0.08)' }}>
                <svg viewBox="0 0 24 24" width="40" height="40" fill="none" stroke="#006c50" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
                  <polyline points="22 4 12 14.01 9 11.01" />
                </svg>
              </div>
            </div>

            <div style={{ marginBottom: '16px' }}>
              <h1 style={{ fontSize: '40px', fontWeight: '600', color: '#006c50', letterSpacing: '-0.02em', fontFamily: 'Geist, sans-serif', marginBottom: '16px' }}>
                Cập nhật thành công!
              </h1>
              <p style={{ fontSize: '16px', color: '#3d4a43' }}>
                Mật khẩu của bạn đã được thay đổi an toàn.
              </p>
            </div>

            <div style={{ marginTop: '32px', padding: '16px 0', display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
              <div style={{ height: '96px', display: 'flex', alignItems: 'center', justifyContent: 'center', overflow: 'hidden' }}>
                <span style={{ fontSize: '64px', fontWeight: 'bold', color: '#006c50', fontFamily: 'Geist, sans-serif' }}>{countdown}</span>
              </div>
              <p style={{ fontSize: '10px', color: '#86948c', textTransform: 'uppercase', letterSpacing: '0.2em', marginTop: '4px', fontWeight: '700' }}>
                Chuyển hướng sau...
              </p>
            </div>

            <div style={{ marginTop: '32px', width: '100%', maxWidth: '400px' }}>
              <button 
                style={{ width: '100%', padding: '16px 32px', backgroundColor: '#006c50', color: '#ffffff', fontWeight: 'bold', borderRadius: '12px', border: 'none', cursor: 'pointer', transition: 'all 0.2s' }}
                onClick={() => {
                  window.history.replaceState({}, '', '/')
                  window.dispatchEvent(new Event('popstate'))
                }}
                onMouseOver={(e) => e.currentTarget.style.transform = 'translateY(-2px)'}
                onMouseOut={(e) => e.currentTarget.style.transform = 'translateY(0)'}
              >
                Đăng nhập ngay
              </button>
            </div>
          </div>
        </main>

        <footer style={{ width: '100%', padding: '24px', backgroundColor: 'transparent', borderTop: '1px solid rgba(0,108,80,0.08)', textAlign: 'center' }}>
          <p style={{ fontSize: '13px', color: '#3d4a43', opacity: 0.6 }}>© 2026 RAGnarok Platform. All Rights Reserved.</p>
        </footer>
      </div>
    )
  }

  return (
    <div className="login-container">
      <div className="login-card">
        <div className="login-header">
          <h1 className="login-title">Đặt lại mật khẩu</h1>
          <p className="login-subtitle">
            Xin chào <strong>{validation.data?.user_name || validation.data?.email}</strong>,<br/>
            Vui lòng nhập mật khẩu mới của bạn bên dưới.
          </p>
        </div>

        {submitError && (
          <div className="login-error" style={{ display: 'flex', alignItems: 'flex-start', gap: '8px' }}>
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" style={{ flexShrink: 0, marginTop: '2px' }}>
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
            <span style={{ flex: 1, textAlign: 'left' }}>{submitError}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="login-form">
          <div className="login-input-wrapper">
            <input
              type="password"
              placeholder="Mật khẩu mới (tối thiểu 8 ký tự)"
              className="login-input"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              disabled={status === 'submitting'}
              required
            />
          </div>
          
          {newPassword.length > 0 && (
            <div style={{ marginBottom: '16px' }}>
              <div style={{ display: 'flex', gap: '4px', marginBottom: '8px' }}>
                <div style={{ height: '4px', flex: 1, backgroundColor: strength >= 1 ? strengthColor : '#e2e2e3', borderRadius: '2px' }}></div>
                <div style={{ height: '4px', flex: 1, backgroundColor: strength >= 2 ? strengthColor : '#e2e2e3', borderRadius: '2px' }}></div>
                <div style={{ height: '4px', flex: 1, backgroundColor: strength >= 3 ? strengthColor : '#e2e2e3', borderRadius: '2px' }}></div>
                <div style={{ height: '4px', flex: 1, backgroundColor: strength >= 4 ? strengthColor : '#e2e2e3', borderRadius: '2px' }}></div>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div style={{ fontSize: '11px', color: '#747878' }}>
                  Yêu cầu: ≥8 ký tự, in hoa, số, ký tự đặc biệt
                </div>
                <div style={{ fontSize: '12px', color: strengthColor, fontWeight: 600 }}>
                  {strengthLabel}
                </div>
              </div>
            </div>
          )}

          <div className="login-input-wrapper">
            <input
              type="password"
              placeholder="Xác nhận mật khẩu mới"
              className="login-input"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              disabled={status === 'submitting'}
              required
            />
          </div>

          <button type="submit" className="login-btn" disabled={status === 'submitting' || !newPassword || !confirmPassword}>
            {status === 'submitting' ? (
              <>
                <div className="login-spinner"></div>
                <span>Đang xử lý...</span>
              </>
            ) : (
              <span>Đổi mật khẩu</span>
            )}
          </button>
        </form>
      </div>
    </div>
  )
}

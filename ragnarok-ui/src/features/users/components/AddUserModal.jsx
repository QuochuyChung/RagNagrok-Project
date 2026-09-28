import { useState, useEffect, useRef } from 'react'
import './AddUserModal.css'

// Field wrapper defined OUTSIDE the modal to prevent remounting on every render
function Field({ label, error, required, hint, children }) {
  return (
    <div className="um-field">
      <label className="um-field__label">
        {label}{required && <span className="um-field__required">*</span>}
      </label>
      {children}
      {hint && !error && <span className="um-field__hint">{hint}</span>}
      {error && <span className="um-field__error">{error}</span>}
    </div>
  )
}

function formatApiError(err) {
  if (!err) return 'Đã xảy ra lỗi. Vui lòng thử lại.'
  if (typeof err === 'string') return err

  const detail = err.detail || err.message || err.error
  if (typeof detail === 'string') return detail

  if (Array.isArray(detail)) {
    return detail.map((d) => d.msg || d.message || JSON.stringify(d)).join('; ')
  }

  if (detail && typeof detail === 'object') {
    if (detail.message) return detail.message
    if (detail.error_code) return `Lỗi [${detail.error_code}]: ${detail.message || ''}`
  }

  if (err.message) return err.message
  if (err.error_code) return `Lỗi [${err.error_code}]: ${err.message || ''}`

  return 'Không thể gửi lời mời. Vui lòng kiểm tra lại thông tin.'
}

export function AddUserModal({ isOpen, onClose, onSubmit, isSubmitting: externalSubmitting, tenants = [], isPlatformAdmin = false }) {
  const [username, setUsername] = useState('')
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [role, setRole] = useState('USER')
  const [tenantId, setTenantId] = useState('')
  const [errors, setErrors] = useState({})
  const [serverError, setServerError] = useState(null)
  const [internalSubmitting, setInternalSubmitting] = useState(false)
  const usernameRef = useRef(null)

  const isSubmitting = externalSubmitting || internalSubmitting

  useEffect(() => {
    if (isOpen) {
      setTimeout(() => usernameRef.current?.focus(), 80)
      setErrors({})
      setServerError(null)
    }
  }, [isOpen])

  if (!isOpen) return null

  const validate = () => {
    const e = {}
    if (!username.trim()) e.username = 'Vui lòng nhập tên đăng nhập.'
    else if (/\s/.test(username)) e.username = 'Tên đăng nhập không được chứa khoảng trắng.'
    else if (username.trim().length > 16) e.username = 'Tên đăng nhập không được vượt quá 16 ký tự.'
    if (email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) e.email = 'Địa chỉ email không đúng định dạng.'
    if (isPlatformAdmin && !tenantId) e.tenant_id = 'Vui lòng chọn tenant cho tài khoản này.'
    return e
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setServerError(null)
    const errs = validate()
    if (Object.keys(errs).length) { setErrors(errs); return }

    const payload = {
      username: username.trim(),
      name: name.trim() || username.trim(),
      email: email.trim() || `${username.trim()}@ragnarok.ai`,
      role,
    }

    if (isPlatformAdmin && tenantId) {
      payload.tenant_id = tenantId
    }

    setInternalSubmitting(true)
    try {
      await onSubmit(payload)
      handleClose()
    } catch (err) {
      setServerError(formatApiError(err))
    } finally {
      setInternalSubmitting(false)
    }
  }

  const handleClose = () => {
    if (isSubmitting) return
    setUsername(''); setName(''); setEmail(''); setRole('USER'); setTenantId(''); setErrors({}); setServerError(null)
    onClose()
  }

  return (
    <div className="um-backdrop" onClick={(e) => e.target === e.currentTarget && handleClose()}>
      <div className="um-dialog" role="dialog" aria-modal="true" aria-label="Thêm thành viên mới">

        {/* Header */}
        <div className="um-dialog__header">
          <div className="um-dialog__title-group">
            <div className="um-dialog__icon">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round">
                <circle cx="12" cy="8" r="4" />
                <path d="M4 20c0-4 3.6-7 8-7s8 3 8 7" />
                <line x1="19" y1="8" x2="19" y2="14" />
                <line x1="16" y1="11" x2="22" y2="11" />
              </svg>
            </div>
            <div>
              <h2 className="um-dialog__title">Mời thành viên mới</h2>
              <p className="um-dialog__subtitle">Gửi lời mời qua email để thêm thành viên vào tenant.</p>
            </div>
          </div>
          <button className="um-dialog__close" onClick={handleClose} disabled={isSubmitting} aria-label="Đóng">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        {/* Body */}
        <form onSubmit={handleSubmit} noValidate>
          <div className="um-dialog__body">

            {/* Server Error Alert Banner */}
            {serverError && (
              <div className="um-alert um-alert--error" role="alert">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="12" cy="12" r="10" />
                  <line x1="12" y1="8" x2="12" y2="12" />
                  <line x1="12" y1="16" x2="12.01" y2="16" />
                </svg>
                <span>{serverError}</span>
              </div>
            )}

            {/* Tenant Selection Dropdown for PLATFORM_ADMIN */}
            {isPlatformAdmin && (
              <Field label="Tenant" required error={errors.tenant_id}>
                <select
                  className={`um-input ${errors.tenant_id ? 'um-input--error' : ''}`}
                  value={tenantId}
                  onChange={(e) => { setTenantId(e.target.value); setErrors((p) => ({ ...p, tenant_id: null })) }}
                  disabled={isSubmitting}
                >
                  <option value="">— Chọn tenant —</option>
                  {tenants.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.name}
                    </option>
                  ))}
                </select>
              </Field>
            )}

            <div className="um-grid-2">
              <Field label="Tên đăng nhập" required error={errors.username}>
                <input
                  ref={usernameRef}
                  className={`um-input ${errors.username ? 'um-input--error' : ''}`}
                  type="text"
                  value={username}
                  onChange={(e) => { setUsername(e.target.value); setErrors((p) => ({ ...p, username: null })) }}
                  placeholder="vd: nguyen_van_a"
                  disabled={isSubmitting}
                  autoComplete="off"
                />
              </Field>

              <Field label="Họ và tên">
                <input
                  className="um-input"
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="vd: Nguyễn Văn A (không bắt buộc)"
                  disabled={isSubmitting}
                />
              </Field>
            </div>

            <Field label="Địa chỉ email" error={errors.email}>
              <input
                className={`um-input ${errors.email ? 'um-input--error' : ''}`}
                type="email"
                value={email}
                onChange={(e) => { setEmail(e.target.value); setErrors((p) => ({ ...p, email: null })) }}
                placeholder="vd: ten@congty.com"
                disabled={isSubmitting}
                autoComplete="off"
              />
            </Field>

            {/* Role Selector */}
            <div className="um-field">
              <label className="um-field__label">Phân quyền</label>
              <div className="um-role-options">
                <label className={`um-role-option ${role === 'USER' ? 'um-role-option--selected' : ''}`}>
                  <input type="radio" name="role" value="USER" checked={role === 'USER'} onChange={() => setRole('USER')} disabled={isSubmitting} />
                  <div className="um-role-option__icon um-role-option__icon--user">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <circle cx="12" cy="8" r="4" /><path d="M4 20c0-4 3.6-7 8-7s8 3 8 7" />
                    </svg>
                  </div>
                  <div className="um-role-option__info">
                    <span className="um-role-option__name">Thành viên</span>
                  </div>
                  <div className="um-role-option__check">
                    {role === 'USER' && <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><polyline points="20,6 9,17 4,12" /></svg>}
                  </div>
                </label>

                <label className={`um-role-option ${role === 'TENANT_ADMIN' ? 'um-role-option--selected um-role-option--admin' : ''}`}>
                  <input type="radio" name="role" value="TENANT_ADMIN" checked={role === 'TENANT_ADMIN'} onChange={() => setRole('TENANT_ADMIN')} disabled={isSubmitting} />
                  <div className="um-role-option__icon um-role-option__icon--admin">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
                      <path d="M12 1L3 5v6c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V5l-9-4z" />
                    </svg>
                  </div>
                  <div className="um-role-option__info">
                    <span className="um-role-option__name">Quản trị viên tenant</span>
                  </div>
                  <div className="um-role-option__check">
                    {role === 'TENANT_ADMIN' && <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><polyline points="20,6 9,17 4,12" /></svg>}
                  </div>
                </label>
              </div>
            </div>
          </div>

          {/* Footer */}
          <div className="um-dialog__footer">
            <button type="button" className="um-btn um-btn--ghost" onClick={handleClose} disabled={isSubmitting}>Huỷ</button>
            <button type="submit" className="um-btn um-btn--primary" disabled={isSubmitting}>
              {isSubmitting ? (
                <><span className="um-btn__spinner" />Đang gửi...</>
              ) : (
                <><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" /></svg>Gửi lời mời</>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

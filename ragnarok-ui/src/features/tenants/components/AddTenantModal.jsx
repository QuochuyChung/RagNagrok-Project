import { useState, useEffect, useRef } from 'react'
import './AddTenantModal.css'

function Field({ label, error, required, hint, children }) {
  return (
    <div className="tm-field">
      <label className="tm-field__label">
        {label}{required && <span className="tm-field__required">*</span>}
      </label>
      {children}
      {hint && !error && <span className="tm-field__hint">{hint}</span>}
      {error && <span className="tm-field__error">{error}</span>}
    </div>
  )
}

export function AddTenantModal({ isOpen, onClose, onSubmit, isSubmitting }) {
  const [name, setName] = useState('')
  const [adminUsername, setAdminUsername] = useState('')
  const [adminEmail, setAdminEmail] = useState('')
  const [adminFullName, setAdminFullName] = useState('')
  const [errors, setErrors] = useState({})
  const [apiError, setApiError] = useState(null)
  const nameRef = useRef(null)

  useEffect(() => {
    if (isOpen) {
      setTimeout(() => nameRef.current?.focus(), 80)
      setErrors({})
      setApiError(null)
    }
  }, [isOpen])

  if (!isOpen) return null

  const validate = () => {
    const e = {}
    if (!name.trim()) e.name = 'Vui lòng nhập tên tenant.'
    if (adminEmail.trim() && !/^\S+@\S+\.\S+$/.test(adminEmail)) e.adminEmail = 'Địa chỉ email không đúng định dạng.'
    if (adminEmail.trim() && !adminUsername.trim()) e.adminUsername = 'Vui lòng nhập tên đăng nhập cho quản trị viên.'
    if (adminEmail.trim() && !adminFullName.trim()) e.adminFullName = 'Vui lòng nhập họ và tên quản trị viên.'
    return e
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setApiError(null)
    const errs = validate()
    if (Object.keys(errs).length) { setErrors(errs); return }
    try {
      await onSubmit(name.trim(), adminEmail.trim(), adminFullName.trim(), adminUsername.trim())
    } catch (err) {
      setApiError(err instanceof Error ? err.message : 'Không thể tạo tenant. Vui lòng thử lại.')
    }
  }

  const handleClose = () => {
    if (isSubmitting) return
    setName(''); setAdminUsername(''); setAdminEmail(''); setAdminFullName(''); setErrors({}); setApiError(null);
    onClose()
  }

  return (
    <div className="tm-backdrop" onClick={(e) => e.target === e.currentTarget && handleClose()}>
      <div className="tm-dialog" role="dialog" aria-modal="true" aria-label="Khởi tạo Tenant mới">
        {/* Header */}
        <div className="tm-dialog__header">
          <div className="tm-dialog__title-group">
            <div className="tm-dialog__icon">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <rect x="3" y="3" width="7" height="7" />
                <rect x="14" y="3" width="7" height="7" />
                <rect x="14" y="14" width="7" height="7" />
                <rect x="3" y="14" width="7" height="7" />
              </svg>
            </div>
            <div>
              <h2 className="tm-dialog__title">Tạo Tenant mới</h2>
              <p className="tm-dialog__subtitle">Mỗi tenant có kho dữ liệu riêng biệt và nhóm thành viên độc lập.</p>
            </div>
          </div>
          <button className="tm-dialog__close" onClick={handleClose} disabled={isSubmitting} aria-label="Đóng">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        {/* Form Body */}
        <form onSubmit={handleSubmit} noValidate>
          <div className="tm-dialog__body">
            {apiError && (
              <div className="tm-api-error" style={{ padding: '12px', marginBottom: '16px', background: 'rgba(239, 68, 68, 0.07)', border: '1px solid rgba(239, 68, 68, 0.2)', borderRadius: '8px', color: '#dc2626', fontSize: '13px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>
                {apiError}
              </div>
            )}
            <Field label="Tên tenant" required error={errors.name}>
              <input
                ref={nameRef}
                className={`tm-input ${errors.name ? 'tm-input--error' : ''}`}
                type="text"
                value={name}
                onChange={(e) => { setName(e.target.value); setErrors((p) => ({ ...p, name: null })) }}
                placeholder="vd: Công ty ACME"
                disabled={isSubmitting}
                autoComplete="off"
              />
            </Field>

            <Field label="Email quản trị viên (không bắt buộc)" error={errors.adminEmail}>
              <input
                className={`tm-input ${errors.adminEmail ? 'tm-input--error' : ''}`}
                type="email"
                value={adminEmail}
                onChange={(e) => { setAdminEmail(e.target.value); setErrors((p) => ({ ...p, adminEmail: null })) }}
                placeholder="vd: admin@acme.com"
                disabled={isSubmitting}
                autoComplete="email"
              />
            </Field>

            <Field label="Tên đăng nhập quản trị viên" required={!!adminEmail.trim()} error={errors.adminUsername}>
              <input
                className={`tm-input ${errors.adminUsername ? 'tm-input--error' : ''}`}
                type="text"
                value={adminUsername}
                onChange={(e) => { setAdminUsername(e.target.value); setErrors((p) => ({ ...p, adminUsername: null })) }}
                placeholder="vd: acme_admin"
                disabled={isSubmitting || !adminEmail.trim()}
                autoComplete="username"
              />
            </Field>

            <Field label="Họ và tên quản trị viên" required={!!adminEmail.trim()} error={errors.adminFullName}>
              <input
                className={`tm-input ${errors.adminFullName ? 'tm-input--error' : ''}`}
                type="text"
                value={adminFullName}
                onChange={(e) => { setAdminFullName(e.target.value); setErrors((p) => ({ ...p, adminFullName: null })) }}
                placeholder="vd: Nguyễn Văn An"
                disabled={isSubmitting || !adminEmail.trim()}
                autoComplete="name"
              />
            </Field>
          </div>

          {/* Footer */}
          <div className="tm-dialog__footer">
            <button type="button" className="tm-btn tm-btn--ghost" onClick={handleClose} disabled={isSubmitting}>Huỷ</button>
            <button type="submit" className="tm-btn tm-btn--primary" disabled={isSubmitting}>
              {isSubmitting ? (
                <><span className="tm-btn__spinner" />Đang tạo...</>
              ) : (
                <><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" /></svg>Tạo Tenant</>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

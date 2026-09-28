import { useState, useEffect, useRef } from 'react'
import './AddUserModal.css'

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
  if (!err) return 'Đã xảy ra lỗi không xác định.'
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

  return 'Khởi tạo tài khoản thất bại. Vui lòng kiểm tra lại thông tin.'
}

export function BulkInviteModal({ isOpen, onClose, onSubmit, tenants = [], isPlatformAdmin = false }) {
  const [file, setFile] = useState(null)
  const [role, setRole] = useState('USER')
  const [expiresInHours, setExpiresInHours] = useState(48)
  const [tenantId, setTenantId] = useState('')
  const [errors, setErrors] = useState({})
  const [serverError, setServerError] = useState(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const fileInputRef = useRef(null)

  useEffect(() => {
    if (isOpen) {
      setErrors({})
      setServerError(null)
      setFile(null)
    }
  }, [isOpen])

  if (!isOpen) return null

  const validate = () => {
    const e = {}
    if (!file) e.file = 'Vui lòng chọn file danh sách (định dạng .csv).'
    if (isPlatformAdmin && !tenantId) e.tenant_id = 'Vui lòng chọn tenant.'
    if (!expiresInHours || expiresInHours <= 0) e.expiresInHours = 'Vui lòng nhập thời hạn hợp lệ (tối thiểu 1 giờ).'
    return e
  }

  const handleFileChange = (e) => {
    if (e.target.files && e.target.files.length > 0) {
      const selectedFile = e.target.files[0]
      if (!selectedFile.name.endsWith('.csv')) {
        setErrors(p => ({ ...p, file: 'Chỉ hỗ trợ file định dạng .csv.' }))
        setFile(null)
      } else {
        setFile(selectedFile)
        setErrors(p => ({ ...p, file: null }))
      }
    }
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setServerError(null)
    const errs = validate()
    if (Object.keys(errs).length) { setErrors(errs); return }
    
    setIsSubmitting(true)
    try {
      // In a real implementation, you would construct FormData here
      // and pass it to onSubmit which calls the API.
      const formData = new FormData()
      formData.append('file', file)
      formData.append('role_name', role)
      formData.append('expires_in_hours', expiresInHours)
      
      const targetTenant = isPlatformAdmin ? tenantId : null // Depends on API client logic
      
      await onSubmit({ formData, tenantId: targetTenant })
      handleClose()
    } catch (err) {
      setServerError(formatApiError(err))
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleClose = () => {
    if (isSubmitting) return
    setFile(null); setRole('USER'); setTenantId(''); setExpiresInHours(48); setErrors({}); setServerError(null)
    onClose()
  }

  return (
    <div className="um-backdrop" onClick={(e) => e.target === e.currentTarget && handleClose()}>
      <div className="um-dialog" role="dialog" aria-modal="true" aria-label="Mời thành viên hàng loạt">
        {/* Header */}
        <div className="um-dialog__header">
          <div className="um-dialog__title-group">
            <div className="um-dialog__icon" style={{ backgroundColor: '#e0f2fe', color: '#0369a1' }}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                <polyline points="17 8 12 3 7 8" />
                <line x1="12" y1="3" x2="12" y2="15" />
              </svg>
            </div>
            <div>
              <h2 className="um-dialog__title">Nhập danh sách từ CSV</h2>
              <p className="um-dialog__subtitle">Tải lên file CSV để gửi lời mời hàng loạt đến nhiều thành viên cùng lúc.</p>
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

            <Field label="File danh sách (CSV)" required error={errors.file}
              hint="File cần có cột: email, full_name">
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <button 
                  type="button" 
                  className="um-btn um-btn--ghost" 
                  onClick={() => fileInputRef.current?.click()}
                  disabled={isSubmitting}
                >
                  Chọn file
                </button>
                <span style={{ fontSize: '14px', color: '#444748' }}>
                  {file ? file.name : 'Chưa chọn file'}
                </span>
              </div>
              <input 
                type="file" 
                accept=".csv"
                ref={fileInputRef}
                style={{ display: 'none' }}
                onChange={handleFileChange}
              />
            </Field>

            <Field label="Thời hạn lời mời (giờ)" required error={errors.expiresInHours}>
              <input
                className={`um-input ${errors.expiresInHours ? 'um-input--error' : ''}`}
                type="number"
                min="1"
                max="720"
                value={expiresInHours}
                placeholder="vd: 48"
                onChange={(e) => { setExpiresInHours(e.target.value); setErrors((p) => ({ ...p, expiresInHours: null })) }}
                disabled={isSubmitting}
              />
            </Field>

            {/* Role Selector */}
            <div className="um-field">
              <label className="um-field__label">Phân quyền mặc định</label>
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
            <button type="submit" className="um-btn um-btn--primary" style={{ backgroundColor: '#0891b2', color: '#fff' }} disabled={isSubmitting}>
              {isSubmitting ? (
                <><span className="um-btn__spinner" />Đang gửi...</>
              ) : (
                <><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M22 2L11 13" /><polygon points="22 2 15 22 11 13 2 9 22 2" /></svg>Gửi lời mời</>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

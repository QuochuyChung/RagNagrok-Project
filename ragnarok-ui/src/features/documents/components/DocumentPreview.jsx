import { useEffect, useState, useRef, useCallback, useMemo } from 'react'
import ReactMarkdown from 'react-markdown'
import { formatDate } from '../../../shared/utils/formatDate'
import { API_BASE_URL } from '../../../api/client'

// crypto.randomUUID thay cho createRequestId từ client.js
function createRequestId() {
  return crypto.randomUUID()
}

// Lấy file extension
function getFileExt(name = '') {
  return (name.split('.').pop() || '').toLowerCase()
}

// Format file size
function formatSize(bytes) {
  if (!bytes) return '—'
  return bytes >= 1048576
    ? `${(bytes / 1048576).toFixed(2)} MB`
    : `${(bytes / 1024).toFixed(1)} KB`
}

// Map extension -> file-type label và icon class
const FILE_TYPE_CONFIG = {
  pdf:  { label: 'PDF',  className: 'docs-file-icon--pdf' },
  docx: { label: 'DOCX', className: 'docs-file-icon--docx' },
  doc:  { label: 'DOC',  className: 'docs-file-icon--docx' },
  txt:  { label: 'TXT',  className: 'docs-file-icon--txt' },
  md:   { label: 'MD',   className: 'docs-file-icon--md' },
}

function getFileTypeConfig(ext) {
  return FILE_TYPE_CONFIG[ext] || { label: (ext.toUpperCase().slice(0, 4) || 'FILE'), className: 'docs-file-icon--other' }
}

/**
 * Tạo headers có auth token + tenant ID (giống api/client.js)
 */
function buildAuthHeaders() {
  const headers = {
    'X-Request-ID': createRequestId(),
  }
  const rawTenantId = localStorage.getItem('tenantId')
  const tenantId =
    (rawTenantId && rawTenantId !== 'null' && rawTenantId !== 'undefined')
      ? rawTenantId
      : import.meta.env.VITE_DEFAULT_TENANT
  if (tenantId && tenantId !== 'null' && tenantId !== 'undefined') {
    headers['X-Tenant-ID'] = tenantId
  }
  const token = localStorage.getItem('ragnarok_token')
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }
  return headers
}

/**
 * DocumentViewerPanel - Hiển thị nội dung tài liệu trong pane phải của split view.
 * Render theo Content-Type trả về từ backend:
 *   - application/pdf      → <iframe> blob URL
 *   - application/json     → DOCX đã convert sang HTML (render dangerouslySetInnerHTML)
 *   - text/markdown        → react-markdown
 *   - text/plain           → <pre> monospace
 *
 * Props:
 *  - document: object document cần xem
 *  - onClose: callback đóng pane phải
 *  - onDownload: callback download (disposition=attachment)
 *  - isFullscreen: pane phải đang fullscreen (ẩn pane trái)
 *  - onToggleFullscreen: chuyển trạng thái fullscreen
 */
export function DocumentViewerPanel({
  document,
  onClose,
  onDownload,
  isFullscreen = false,
  onToggleFullscreen,
}) {
  // Key theo doc ID - remount khi đổi document → reset state sạch sẽ
  return (
    <PreviewContent
      key={document?.id || document?.doc_id || 'empty'}
      document={document}
      onClose={onClose}
      onDownload={onDownload}
      isFullscreen={isFullscreen}
      onToggleFullscreen={onToggleFullscreen}
    />
  )
}

function PreviewContent({ document, onClose, onDownload, isFullscreen, onToggleFullscreen }) {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [contentType, setContentType] = useState(null)  // 'pdf' | 'docx-html' | 'markdown' | 'text' | 'unsupported'
  const [blobUrl, setBlobUrl] = useState(null)
  const [html, setHtml] = useState(null)
  const [text, setText] = useState(null)
  const [retryKey, setRetryKey] = useState(0)  // tăng để retry
  const blobUrlRef = useRef(null)

  const ext = getFileExt(document?.filename || document?.doc_name || '')
  const typeConf = getFileTypeConfig(ext)

  // Cleanup blob URL cũ
  useEffect(() => {
    return () => {
      if (blobUrlRef.current) {
        URL.revokeObjectURL(blobUrlRef.current)
        blobUrlRef.current = null
      }
    }
  }, [])

  useEffect(() => {
    if (!document) return

    let cancelled = false

    const fetchContent = async () => {
      try {
        const token = localStorage.getItem('ragnarok_token')
        if (!token) {
          throw new Error('Chưa đăng nhập - vui lòng đăng nhập lại')
        }

        const headers = buildAuthHeaders()
        const docId = document.id || document.doc_id
        const url = `${API_BASE_URL}/v1/documents/${docId}/content?disposition=inline`

        const res = await fetch(url, { headers })

        if (!res.ok) {
          let errMsg = `HTTP ${res.status}`
          try {
            const err = await res.json()
            errMsg = err.detail || err.message || errMsg
          } catch (parseErr) {
            void parseErr
          }
          throw new Error(errMsg)
        }

        if (cancelled) return

        // Branch theo Content-Type trả về từ backend
        const responseContentType = res.headers.get('Content-Type') || ''

        if (responseContentType.includes('application/json')) {
          // DOCX đã convert sang HTML
          const data = await res.json()
          if (cancelled) return
          setHtml(data.html || '')
          setContentType('docx-html')
        } else if (responseContentType.includes('application/pdf')) {
          // PDF - tạo blob URL cho iframe
          const blob = await res.blob()
          if (cancelled) return
          const newBlobUrl = URL.createObjectURL(blob)

          // Revoke old nếu có
          if (blobUrlRef.current) URL.revokeObjectURL(blobUrlRef.current)
          blobUrlRef.current = newBlobUrl

          setBlobUrl(newBlobUrl)
          setContentType('pdf')
        } else if (responseContentType.includes('text/markdown')) {
          // Markdown - parse bằng react-markdown
          const mdText = await res.text()
          if (cancelled) return
          setText(mdText)
          setContentType('markdown')
        } else if (responseContentType.includes('text/plain')) {
          // Plain text - hiển thị monospace
          const plainText = await res.text()
          if (cancelled) return
          setText(plainText)
          setContentType('text')
        } else {
          // Không hỗ trợ - download thôi
          setContentType('unsupported')
        }
      } catch (e) {
        if (!cancelled) {
          setError(e.message || 'Không thể tải nội dung tài liệu')
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    fetchContent()

    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [document?.id, document?.doc_id, retryKey])

  // ESC để đóng (chỉ khi không focus input/textarea)
  useEffect(() => {
    const handleKey = (e) => {
      if (e.key === 'Escape' && !e.target.matches('input, textarea')) {
        if (isFullscreen && onToggleFullscreen) {
          onToggleFullscreen()
        } else {
          onClose?.()
        }
      }
    }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [onClose, isFullscreen, onToggleFullscreen])

  const handleRetry = useCallback(() => {
    setError(null)
    setLoading(true)
    setRetryKey(k => k + 1)
  }, [])

  // Compute status badge (lấy từ document.status - "ingested"/"processing"/"failed")
  const statusKey = (document?.status || '').toLowerCase()
  const statusInfo = useMemo(() => {
    if (statusKey === 'ingested' || statusKey === 'completed') {
      return { label: 'Đã indexed', className: 'docs-status--ingested' }
    }
    if (statusKey === 'failed') {
      return { label: 'Lỗi', className: 'docs-status--failed' }
    }
    return { label: 'Đang xử lý', className: 'docs-status--processing' }
  }, [statusKey])

  // Empty state khi không có document
  if (!document) {
    return (
      <aside className="docs-viewer-pane docs-viewer-pane--empty">
        <div className="docs-viewer-pane__empty-state">
          <svg width="56" height="56" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.2">
            <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
            <polyline points="14 2 14 8 20 8" />
            <line x1="16" y1="13" x2="8" y2="13" />
            <line x1="16" y1="17" x2="8" y2="17" />
            <polyline points="10 9 8 9 8 7" />
          </svg>
          <h3>Chọn 1 tài liệu để xem trước</h3>
          <p>Click vào bất kỳ hàng nào trong bảng bên trái để xem nội dung chi tiết tại đây.</p>
        </div>
      </aside>
    )
  }

  const name = document.filename || document.doc_name || 'Không rõ tên'
  const version = document.doc_version || document.version || 1

  return (
    <aside className={`docs-viewer-pane ${isFullscreen ? 'docs-viewer-pane--fullscreen' : ''}`}>
      {/* Header toolbar */}
      <header className="docs-viewer-pane__header">
        <div className="docs-viewer-pane__title-row">
          <div className={`docs-file-icon ${typeConf.className}`}>{typeConf.label}</div>
          <div className="docs-viewer-pane__title-info">
            <h2 className="docs-viewer-pane__title" title={name}>{name}</h2>
            <div className="docs-viewer-pane__badges">
              <span className="docs-viewer-pane__version-badge">v{version}</span>
              <span className={`docs-status ${statusInfo.className}`}>
                <span className="docs-status__dot" />
                {statusInfo.label}
              </span>
            </div>
          </div>
        </div>

        <div className="docs-viewer-pane__actions">
          {onToggleFullscreen && (
            <button
              className="docs-viewer-pane__action-btn"
              onClick={onToggleFullscreen}
              aria-label={isFullscreen ? 'Thoát toàn màn hình' : 'Mở rộng toàn màn hình'}
              title={isFullscreen ? 'Thoát toàn màn hình (ESC)' : 'Mở rộng toàn màn hình'}
            >
              {isFullscreen ? (
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
                  <path d="M8 3v3a2 2 0 01-2 2H3" />
                  <path d="M21 8h-3a2 2 0 01-2-2V3" />
                  <path d="M3 16h3a2 2 0 012 2v3" />
                  <path d="M16 21v-3a2 2 0 012-2h3" />
                </svg>
              ) : (
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
                  <path d="M3 8V5a2 2 0 012-2h3" />
                  <path d="M16 3h3a2 2 0 012 2v3" />
                  <path d="M21 16v3a2 2 0 01-2 2h-3" />
                  <path d="M8 21H5a2 2 0 01-2-2v-3" />
                </svg>
              )}
            </button>
          )}

          <button
            className="docs-viewer-pane__action-btn docs-viewer-pane__action-btn--primary"
            onClick={() => onDownload?.(document)}
            disabled={loading}
            title="Tải về"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
              <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" />
              <polyline points="7 10 12 15 17 10" />
              <line x1="12" y1="15" x2="12" y2="3" />
            </svg>
            Tải về
          </button>

          <button
            className="docs-viewer-pane__action-btn docs-viewer-pane__action-btn--close"
            onClick={isFullscreen ? onToggleFullscreen : onClose}
            aria-label="Đóng"
            title="Đóng"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        {/* Meta row dưới title */}
        <div className="docs-viewer-pane__meta-row">
          <span className="docs-viewer-pane__meta-item">
            <span className="docs-viewer-pane__meta-label">Dung lượng</span>
            <strong>{formatSize(document.file_size)}</strong>
          </span>
          <span className="docs-viewer-pane__meta-divider" />
          <span className="docs-viewer-pane__meta-item">
            <span className="docs-viewer-pane__meta-label">Ngày tải</span>
            <strong>{formatDate(document.createdAt || document.ingested_at || document.created_at) || '—'}</strong>
          </span>
          <span className="docs-viewer-pane__meta-divider" />
          <span className="docs-viewer-pane__meta-item">
            <span className="docs-viewer-pane__meta-label">Định dạng</span>
            <strong>.{ext}</strong>
          </span>
        </div>
      </header>

      {/* Body - Render theo Content-Type */}
      <div className="docs-viewer-pane__body">
        {/* Skeleton loading */}
        {loading && <ViewerSkeleton />}

        {/* Error state */}
        {error && !loading && (
          <div className="docs-viewer-pane__error">
            <svg width="44" height="44" viewBox="0 0 24 24" fill="none" stroke="#ef4444" strokeWidth="1.5">
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
            <h4>Không thể tải nội dung</h4>
            <p>{error}</p>
            <button className="docs-viewer-pane__retry-btn" onClick={handleRetry}>
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
                <path d="M23 4v6h-6" />
                <path d="M20.49 15a9 9 0 11-2.12-9.36L23 10" />
              </svg>
              Thử lại
            </button>
          </div>
        )}

        {/* PDF: iframe với blob URL */}
        {!loading && !error && contentType === 'pdf' && blobUrl && (
          <div className="docs-viewer-pane__pdf-wrapper">
            <iframe
              key={blobUrl}
              src={blobUrl}
              className="docs-viewer-pane__pdf-iframe"
              title={name}
            />
          </div>
        )}

        {/* DOCX: HTML render (từ server mammoth) */}
        {!loading && !error && contentType === 'docx-html' && (
          <div className="docs-viewer-pane__docx-wrapper">
            <article
              className="docs-viewer-pane__docx"
              dangerouslySetInnerHTML={{ __html: html || '' }}
            />
          </div>
        )}

        {/* Markdown: react-markdown */}
        {!loading && !error && contentType === 'markdown' && (
          <div className="docs-viewer-pane__md-wrapper">
            <article className="docs-viewer-pane__markdown">
              <ReactMarkdown>{text || ''}</ReactMarkdown>
            </article>
          </div>
        )}

        {/* Plain text */}
        {!loading && !error && contentType === 'text' && (
          <div className="docs-viewer-pane__text-wrapper">
            <pre className="docs-viewer-pane__text">{text || ''}</pre>
          </div>
        )}

        {/* Không hỗ trợ preview */}
        {!loading && !error && contentType === 'unsupported' && (
          <div className="docs-viewer-pane__unsupported">
            <svg width="56" height="56" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.2">
              <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
              <polyline points="14 2 14 8 20 8" />
            </svg>
            <h4>Không hỗ trợ xem trước</h4>
            <p>Định dạng <code>.{ext}</code> không hỗ trợ preview. Vui lòng tải về để xem.</p>
            <button
              className="docs-viewer-pane__retry-btn"
              onClick={() => onDownload?.(document)}
            >
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
                <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" />
                <polyline points="7 10 12 15 17 10" />
                <line x1="12" y1="15" x2="12" y2="3" />
              </svg>
              Tải về
            </button>
          </div>
        )}
      </div>
    </aside>
  )
}

/**
 * Skeleton loading - hiển thị trong lúc đợi fetch content.
 * Không dùng spinner, dùng shimmer effect giả lập nội dung.
 */
function ViewerSkeleton() {
  return (
    <div className="docs-viewer-pane__skeleton">
      <div className="docs-skeleton-line docs-skeleton-line--title" />
      <div className="docs-skeleton-line docs-skeleton-line--h2" />
      <div className="docs-skeleton-line docs-skeleton-line--full" />
      <div className="docs-skeleton-line docs-skeleton-line--full" />
      <div className="docs-skeleton-line docs-skeleton-line--medium" />
      <div className="docs-skeleton-line docs-skeleton-line--full" />
      <div className="docs-skeleton-line docs-skeleton-line--short" />
      <div className="docs-skeleton-line docs-skeleton-line--h2" />
      <div className="docs-skeleton-line docs-skeleton-line--full" />
      <div className="docs-skeleton-line docs-skeleton-line--medium" />
    </div>
  )
}

// Backward compatible alias
export { DocumentViewerPanel as DocumentPreview }

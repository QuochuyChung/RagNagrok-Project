import { useState, useRef } from 'react'

const FILE_TYPE_CONFIG = {
  pdf:  { label: 'PDF',  className: 'docs-file-icon--pdf' },
  docx: { label: 'DOCX', className: 'docs-file-icon--docx' },
  doc:  { label: 'DOC',  className: 'docs-file-icon--docx' },
  txt:  { label: 'TXT',  className: 'docs-file-icon--txt' },
  md:   { label: 'MD',   className: 'docs-file-icon--md' },
  zip:  { label: 'ZIP',  className: 'docs-file-icon--other' },
}

function getFileExt(name = '') {
  return (name.split('.').pop() || '').toLowerCase()
}
function getFileTypeConfig(ext) {
  return FILE_TYPE_CONFIG[ext] || { label: ext.toUpperCase().slice(0, 4) || 'FILE', className: 'docs-file-icon--other' }
}
function formatBytes(bytes) {
  if (!bytes) return '—'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1048576).toFixed(2)} MB`
}

const MODES = [
  { key: 'files',  label: 'Tệp',      icon: '📄' },
  { key: 'folder', label: 'Thư mục',  icon: '📁' },
]

export function DocumentUploader({ onUploadBatch }) {
  const [mode, setMode]           = useState('files')
  const [dragActive, setDragActive] = useState(false)
  const [selectedFiles, setSelectedFiles] = useState([]) // always array
  const [progress, setProgress]   = useState(0)
  const [uploading, setUploading] = useState(false)
  const [batchResult, setBatchResult] = useState(null)
  const [uploadError, setUploadError] = useState(null)

  const filesRef  = useRef(null)
  const folderRef = useRef(null)

  const activeRef = mode === 'files' ? filesRef : folderRef

  const handleDrag = (e) => {
    e.preventDefault(); e.stopPropagation()
    if (e.type === 'dragenter' || e.type === 'dragover') setDragActive(true)
    else if (e.type === 'dragleave') setDragActive(false)
  }

  const handleDrop = (e) => {
    e.preventDefault(); e.stopPropagation(); setDragActive(false)
    addFiles(Array.from(e.dataTransfer.files || []))
  }

  const handleChange = (e) => {
    addFiles(Array.from(e.target.files || []))
    e.target.value = ''
  }

  const addFiles = (files) => {
    if (!files.length) return
    setSelectedFiles((current) => {
      const known = new Set(
        current.map((file) => `${file.webkitRelativePath || file.name}:${file.size}:${file.lastModified}`),
      )
      return [...current, ...files.filter((file) => {
        const key = `${file.webkitRelativePath || file.name}:${file.size}:${file.lastModified}`
        if (known.has(key)) return false
        known.add(key)
        return true
      })]
    })
    setBatchResult(null)
    setUploadError(null)
  }

  const handleZoneClick = () => {
    if (!uploading) activeRef.current?.click()
  }

  const removeFile = (index) => {
    setSelectedFiles((current) => current.filter((_, i) => i !== index))
  }

  const clearFiles = () => { setSelectedFiles([]); setBatchResult(null); setUploadError(null) }
  
  const handleSubmit = async () => {
    if (!selectedFiles.length || uploading) return
    setUploading(true); setProgress(0); setBatchResult(null); setUploadError(null)

    const interval = setInterval(() => {
      setProgress((p) => p >= 88 ? p : p + Math.random() * 10)
    }, 280)

    try {
      const result = await onUploadBatch?.(selectedFiles)
      clearInterval(interval); setProgress(100)
      await new Promise(r => setTimeout(r, 400))
      setBatchResult(result)
      setSelectedFiles([])
      setProgress(0)
    } catch (err) {
      clearInterval(interval); setProgress(0)
      setUploadError(err?.message || 'Tải lên thất bại. Vui lòng thử lại.')
    } finally {
      setUploading(false)
    }
  }

  const switchMode = (m) => {
    if (uploading) return
    setMode(m); setSelectedFiles([]); setBatchResult(null); setProgress(0)
  }

  const totalSize = selectedFiles.reduce((a, f) => a + (f.size || 0), 0)

  return (
    <div className="docs-upload-wrap">
      {/* Mode Tabs */}
      <div className="docs-upload-tabs">
        {MODES.map((m) => (
          <button
            key={m.key}
            className={`docs-upload-tab ${mode === m.key ? 'docs-upload-tab--active' : ''}`}
            onClick={() => switchMode(m.key)}
            disabled={uploading}
          >
            <span>{m.icon}</span> {m.label}
          </button>
        ))}
        <div className="docs-upload-tabs__hint">
          {mode === 'files'  && 'Chọn một hoặc nhiều tệp cùng lúc (Ctrl/Cmd + click)'}
          {mode === 'folder' && 'Chọn cả thư mục — tất cả file bên trong sẽ được tải lên'}
        </div>
      </div>

      {/* Hidden inputs */}
      <input ref={filesRef} type="file" accept=".pdf,.docx,.doc,.txt,.md,.zip" multiple onChange={handleChange} style={{ display: 'none' }} />
      <input ref={folderRef} type="file" webkitdirectory="true" multiple onChange={handleChange} style={{ display: 'none' }} />

      {/* Drop Zone */}
      <div
        className={`docs-upload-zone ${dragActive ? 'docs-upload-zone--active' : ''} ${uploading ? 'docs-upload-zone--uploading' : ''}`}
        onDragEnter={handleDrag} onDragOver={handleDrag} onDragLeave={handleDrag} onDrop={handleDrop}
        onClick={selectedFiles.length || uploading || batchResult ? undefined : handleZoneClick}
      >
        {/* ─── State: Uploading ─── */}
        {uploading && (
          <>
            <div className="docs-upload-zone__icon">
              <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="1.5">
                <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" /><polyline points="17 8 12 3 7 8" /><line x1="12" y1="3" x2="12" y2="15" />
              </svg>
            </div>
            <p className="docs-upload-zone__title">Đang tải lên {selectedFiles.length} file...</p>
            <div className="docs-upload-progress">
              <div className="docs-upload-progress__bar-wrap">
                <div className="docs-upload-progress__bar" style={{ width: `${Math.min(progress, 100)}%` }} />
              </div>
              <span className="docs-upload-progress__label">{Math.round(Math.min(progress, 100))}%</span>
            </div>
          </>
        )}

        {/* ─── State: Batch result ─── */}
        {!uploading && batchResult && (
          <div className="docs-batch-result">
            <div className="docs-batch-result__title">✅ Tải lên hoàn tất</div>
            <div className="docs-batch-result__grid">
              <div className="docs-batch-result__item docs-batch-result__item--new">
                <strong>{batchResult.new?.length || 0}</strong> file mới
              </div>
              <div className="docs-batch-result__item docs-batch-result__item--updated">
                <strong>{batchResult.updated?.length || 0}</strong> đã cập nhật
              </div>
              <div className="docs-batch-result__item docs-batch-result__item--unchanged">
                <strong>{batchResult.unchanged?.length || 0}</strong> không đổi
              </div>
              <div className="docs-batch-result__item docs-batch-result__item--failed">
                <strong>{batchResult.failed?.length || 0}</strong> thất bại
              </div>
            </div>
            {batchResult.failed?.length > 0 && (
              <ul className="docs-batch-result__errors">
                {batchResult.failed.map((f, i) => (
                  <li key={i}><code>{f.name || f}</code>: {f.error || 'Lỗi không xác định'}</li>
                ))}
              </ul>
            )}
            <button className="docs-upload-cancel" onClick={(e) => { e.stopPropagation(); setBatchResult(null) }}>
              Tải lên thêm
            </button>
          </div>
        )}

        {/* ─── Upload error banner ─── */}
        {!uploading && uploadError && (
          <div className="docs-upload-error" onClick={(e) => e.stopPropagation()}>
            ⚠️ {uploadError}
          </div>
        )}

        {/* ─── State: Files selected ─── */}
        {!uploading && !batchResult && selectedFiles.length > 0 && (
          <>
            <div className="docs-multi-preview">
                <div className="docs-multi-preview__header">
                  <span className="docs-multi-preview__count">
                    {selectedFiles.length} file • {formatBytes(totalSize)}
                  </span>
                  <div className="docs-multi-preview__actions">
                    <button
                      className="docs-multi-preview__add"
                      onClick={(e) => { e.stopPropagation(); handleZoneClick() }}
                    >
                      + {mode === 'folder' ? 'Thêm thư mục' : 'Thêm tệp'}
                    </button>
                    <button
                      className="docs-selected-file__clear"
                      onClick={(e) => { e.stopPropagation(); clearFiles() }}
                      aria-label="Bỏ toàn bộ tệp đã chọn"
                      title="Bỏ toàn bộ tệp đã chọn"
                    >
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                        <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
                      </svg>
                    </button>
                  </div>
                </div>
                <div className="docs-multi-preview__list">
                  {selectedFiles.map((f, i) => {
                    const ext = getFileExt(f.name)
                    const tc = getFileTypeConfig(ext)
                    return (
                      <div key={i} className="docs-multi-preview__item">
                        <span className={`docs-multi-preview__icon docs-file-icon ${tc.className}`}>{tc.label}</span>
                        <span className="docs-multi-preview__name" title={f.webkitRelativePath || f.name}>
                          {f.webkitRelativePath || f.name}
                        </span>
                        <span className="docs-multi-preview__size">{formatBytes(f.size)}</span>
                        <button
                          className="docs-multi-preview__remove"
                          onClick={(e) => { e.stopPropagation(); removeFile(i) }}
                          aria-label={`Bỏ ${f.webkitRelativePath || f.name}`}
                          title={`Bỏ ${f.webkitRelativePath || f.name}`}
                        >
                          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                            <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
                          </svg>
                        </button>
                      </div>
                    )
                  })}
                </div>
            </div>

            <div className="docs-upload-actions">
              <button className="docs-upload-submit" onClick={(e) => { e.stopPropagation(); handleSubmit() }}>
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                  <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" /><polyline points="17 8 12 3 7 8" /><line x1="12" y1="3" x2="12" y2="15" />
                </svg>
                Tải lên {selectedFiles.length > 1 ? `${selectedFiles.length} file` : 'ngay'}
              </button>
              <button className="docs-upload-cancel" onClick={(e) => { e.stopPropagation(); clearFiles() }}>Hủy</button>
            </div>
          </>
        )}

        {/* ─── State: Idle ─── */}
        {!uploading && !batchResult && selectedFiles.length === 0 && (
          <>
            <div className="docs-upload-zone__icon">
              {mode === 'folder' ? (
                <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
                  <path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z" />
                </svg>
              ) : (
                <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
                  <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" /><polyline points="17 8 12 3 7 8" /><line x1="12" y1="3" x2="12" y2="15" />
                </svg>
              )}
            </div>
            <div>
              <p className="docs-upload-zone__title">
                {mode === 'folder'
                  ? 'Click để chọn thư mục'
                  : 'Kéo thả tệp vào đây hoặc '}
                {mode !== 'folder' && <span style={{ color: 'var(--accent)' }}>click để chọn</span>}
              </p>
              <p className="docs-upload-zone__hint">
                {mode === 'folder'
                  ? 'Toàn bộ file trong thư mục sẽ được đưa vào Knowledge Base'
                  : 'Hỗ trợ PDF · DOCX · TXT · MD · ZIP — có thể chọn một hoặc nhiều tệp'}
              </p>
            </div>
            {mode !== 'folder' && (
              <div className="docs-upload-zone__filetypes">
                {['PDF','DOCX','TXT','MD','ZIP'].map((t) => (
                  <span key={t} className="docs-filetype-badge">{t}</span>
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}

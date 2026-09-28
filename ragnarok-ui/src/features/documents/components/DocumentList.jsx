import { useState, useEffect } from 'react'
import { formatDate } from '../../../shared/utils/formatDate'

const FILE_TYPE_CONFIG = {
  pdf:  { label: 'PDF',  className: 'docs-file-icon--pdf' },
  docx: { label: 'DOCX', className: 'docs-file-icon--docx' },
  doc:  { label: 'DOC',  className: 'docs-file-icon--docx' },
  txt:  { label: 'TXT',  className: 'docs-file-icon--txt' },
  md:   { label: 'MD',   className: 'docs-file-icon--md' },
}

function getFileExt(name = '') {
  return (name.split('.').pop() || '').toLowerCase()
}

function getFileTypeConfig(ext) {
  return FILE_TYPE_CONFIG[ext] || { label: (ext.toUpperCase().slice(0, 4) || 'FILE'), className: 'docs-file-icon--other' }
}

function SortIcon({ field, sortField, sortDirection }) {
  const isActive = sortField === field
  const isAsc = isActive && sortDirection === 'asc'
  const isDesc = isActive && sortDirection === 'desc'

  return (
    <span className={`docs-sort-icon ${isActive ? 'docs-sort-icon--active' : ''}`}>
      {isAsc ? (
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
          <polyline points="18 15 12 9 6 15" />
        </svg>
      ) : isDesc ? (
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
          <polyline points="6 9 12 15 18 9" />
        </svg>
      ) : (
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" opacity="0.4">
          <polyline points="18 15 12 9 6 15" />
          <polyline points="6 9 12 15 18 9" />
        </svg>
      )}
    </span>
  )
}

export function DocumentList({
  documents = [],
  onDelete,
  onRestore,
  onPreview,
  selectedDocId,
  selectedIds = [],
  onToggleSelect,
  onToggleSelectAll,
  sortField = 'date',
  sortDirection = 'desc',
  onSort,
}) {
  const [deletingId, setDeletingId]   = useState(null)
  const [restoringId, setRestoringId]   = useState(null)
  const [currentPage, setCurrentPage] = useState(1)
  const PAGE_SIZE = 10

  // Soft-deleted docs luôn xuống cuối danh sách — bất kể sort hiện tại —
  // để user thấy rõ "tài liệu đang hoạt động" ở trên và "đã xóa" ở dưới.
  const orderedDocuments = [...documents].sort((a, b) => {
    const aDeleted = Boolean(a.is_deleted)
    const bDeleted = Boolean(b.is_deleted)
    if (aDeleted !== bDeleted) return aDeleted ? 1 : -1
    return 0
  })

  // Check if all/some documents in list are selected
  const allDocIds = documents.map((d) => d.id || d.doc_id)
  const selectedSet = new Set(selectedIds)
  const isAllSelected = allDocIds.length > 0 && allDocIds.every((id) => selectedSet.has(id))
  const isSomeSelected = selectedSet.size > 0 && !isAllSelected

  // Reset page when documents change (filter/sort/search)
  useEffect(() => {
    setCurrentPage(1)
  }, [documents.length])

  const paged = orderedDocuments.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE)

  if (!documents.length) {
    return (
      <div className="docs-empty">
        <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
          <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
          <polyline points="14 2 14 8 20 8" />
          <line x1="16" y1="13" x2="8" y2="13" />
          <line x1="16" y1="17" x2="8" y2="17" />
          <line x1="10" y1="9" x2="8" y2="9" />
        </svg>
        <p>Chưa có tài liệu nào trong thư viện này.</p>
        <p style={{ fontSize: '12.5px' }}>Tải lên tài liệu đầu tiên để bắt đầu xây dựng Knowledge Base.</p>
      </div>
    )
  }

  if (!paged.length) {
    return (
      <div className="docs-empty">
        <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
          <circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" />
        </svg>
        <p>Không tìm thấy tài liệu phù hợp.</p>
      </div>
    )
  }

  const handleDelete = async (doc) => {
    if (doc.is_deleted) return
    setDeletingId(doc.id)
    try { await onDelete?.(doc.id) } finally { setDeletingId(null) }
  }

  const handleRestore = async (doc) => {
    setRestoringId(doc.id)
    try { await onRestore?.(doc.id) } finally { setRestoringId(null) }
  }

  return (
    <>
      <div style={{ overflowX: 'auto' }}>
        <table className="docs-table">
          <thead>
            <tr>
              <th className="docs-select-column">
                <input
                  type="checkbox"
                  checked={isAllSelected}
                  ref={(el) => {
                    if (el) el.indeterminate = isSomeSelected
                  }}
                  onChange={() => onToggleSelectAll?.(allDocIds)}
                  title={isAllSelected ? 'Bỏ chọn tất cả' : 'Chọn tất cả tài liệu'}
                />
              </th>
              <th>Tài liệu</th>
              <th>Phiên bản</th>
              <th
                className="docs-sortable-header"
                onClick={() => onSort?.('size')}
                title="Sắp xếp theo dung lượng"
              >
                Dung lượng
                <SortIcon field="size" sortField={sortField} sortDirection={sortDirection} />
              </th>
              <th>Trạng thái</th>
              <th
                className="docs-sortable-header"
                onClick={() => onSort?.('date')}
                title="Sắp xếp theo ngày tải lên"
              >
                Ngày tải lên
                <SortIcon field="date" sortField={sortField} sortDirection={sortDirection} />
              </th>
              <th style={{ textAlign: 'right' }}>Hành động</th>
            </tr>
          </thead>
          <tbody>
            {paged.map((doc) => {
              const name   = doc.filename || doc.doc_name || 'Không rõ tên'
              const ext    = getFileExt(name)
              const typeConf = getFileTypeConfig(ext)
              const s = (doc.status || '').toLowerCase()
              const isIngested = s === 'ingested' || s === 'completed'
              const isFailed = s === 'failed'
              const isDeleted = Boolean(doc.is_deleted)
              const isDeleting = deletingId === doc.id
              const isRestoring  = restoringId === doc.id
              const docId = doc.id || doc.doc_id
              const isSelected = selectedDocId === docId
              const isChecked = selectedSet.has(docId)

              const rowClass = [
                isSelected ? 'docs-row--selected' : '',
                isChecked ? 'docs-row--checked' : '',
                onPreview ? 'docs-row--clickable' : '',
                isDeleted ? 'docs-row--deleted' : '',
              ].filter(Boolean).join(' ')

              return (
                <tr
                  key={docId}
                  className={rowClass}
                  onClick={onPreview && !isDeleted ? () => onPreview(doc) : undefined}
                >
                  {/* Checkbox column */}
                  <td className="docs-select-column" onClick={(e) => e.stopPropagation()}>
                    <input
                      type="checkbox"
                      checked={isChecked}
                      onChange={(e) => {
                        e.stopPropagation()
                        onToggleSelect?.(docId)
                      }}
                    />
                  </td>

                  {/* File name + icon */}
                  <td>
                    <div className="docs-file-cell">
                      <div className={`docs-file-icon ${typeConf.className}`}>{typeConf.label}</div>
                      <div>
                        <span className="docs-file-name" title={name}>{name}</span>
                        <span className="docs-file-ext">.{ext}</span>
                        {isDeleted && (
                          <span className="docs-row__deleted-tag" title="Tài liệu đã bị xóa, có thể khôi phục">
                            Đã xóa
                          </span>
                        )}
                      </div>
                    </div>
                  </td>

                  {/* Version */}
                  <td>
                    <span className="docs-version">v{doc.doc_version || doc.version || '1'}</span>
                  </td>

                  {/* Size */}
                  <td>
                    <span className="docs-size">
                      {doc.file_size
                        ? doc.file_size >= 1048576
                          ? `${(doc.file_size / 1048576).toFixed(2)} MB`
                          : `${(doc.file_size / 1024).toFixed(1)} KB`
                        : (doc.size || '—')}
                    </span>
                  </td>

                  {/* Status */}
                  <td>
                    <span className={`docs-status ${isDeleted ? 'docs-status--deleted' : isIngested ? 'docs-status--ingested' : isFailed ? 'docs-status--failed' : 'docs-status--processing'}`}>
                      <span className="docs-status__dot" />
                      {isDeleted ? 'Đã xóa' : isIngested ? 'Đã indexed' : isFailed ? 'Lỗi' : 'Đang xử lý'}
                    </span>
                  </td>

                  {/* Date */}
                  <td>
                    <span className="docs-date">
                      {formatDate(doc.createdAt || doc.ingested_at || doc.created_at) || '—'}
                    </span>
                  </td>

                  {/* Actions */}
                  <td onClick={(e) => e.stopPropagation()}>
                    <div className="docs-actions">
                      {isDeleted ? (
                        <button
                          className="docs-action-btn docs-action-btn--restore"
                          onClick={() => handleRestore(doc)}
                          disabled={isRestoring || isDeleting}
                          title="Khôi phục tài liệu"
                        >
                          {isRestoring ? (
                            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" style={{ animation: 'spin 0.7s linear infinite' }}>
                              <circle cx="12" cy="12" r="10" strokeDasharray="32" strokeDashoffset="10" />
                            </svg>
                          ) : (
                            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                              <path d="M3 12a9 9 0 1015-6.7L21 8" />
                              <polyline points="21 3 21 8 16 8" />
                            </svg>
                          )}
                          {isRestoring ? 'Đang...' : 'Tải lại'}
                        </button>
                      ) : (
                        <button
                          className="docs-action-btn docs-action-btn--danger"
                          onClick={() => handleDelete(doc)}
                          disabled={isDeleting || isRestoring}
                          title="Xóa tài liệu"
                        >
                          {isDeleting ? (
                            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" style={{ animation: 'spin 0.7s linear infinite' }}>
                              <circle cx="12" cy="12" r="10" strokeDasharray="32" strokeDashoffset="10" />
                            </svg>
                          ) : (
                            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                              <polyline points="3,6 5,6 21,6" />
                              <path d="M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6" />
                            </svg>
                          )}
                          Xóa
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {orderedDocuments.length > PAGE_SIZE && (
        <div className="docs-pagination">
          <span className="docs-pagination__info">
            {(currentPage - 1) * PAGE_SIZE + 1}–{Math.min(currentPage * PAGE_SIZE, orderedDocuments.length)} trên {orderedDocuments.length} tài liệu
          </span>
          <div className="docs-pagination__controls">
            <button className="docs-pagination__btn" onClick={() => setCurrentPage((p) => Math.max(p - 1, 1))} disabled={currentPage === 1}>← Trước</button>
            {Array.from({ length: Math.max(1, Math.ceil(orderedDocuments.length / PAGE_SIZE)) }, (_, i) => i + 1).map((p) => (
              <button
                key={p}
                className={`docs-pagination__btn ${p === currentPage ? 'docs-pagination__btn--active' : ''}`}
                onClick={() => setCurrentPage(p)}
              >
                {p}
              </button>
            ))}
            <button className="docs-pagination__btn" onClick={() => setCurrentPage((p) => Math.min(p + 1, Math.ceil(orderedDocuments.length / PAGE_SIZE)))} disabled={currentPage === Math.ceil(orderedDocuments.length / PAGE_SIZE)}>Sau →</button>
          </div>
        </div>
      )}
    </>
  )
}

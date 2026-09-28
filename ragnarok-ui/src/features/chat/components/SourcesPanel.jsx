/**
 * Panel bên phải liệt kê đầy đủ citations của 1 tin nhắn — mở ra khi bấm nút
 * "Nguồn" gọn trong MessageBubble. Field khớp schema Citation của backend
 * (app/schemas/chat.py): doc_id, doc_name, chunk_index, content_snippet, score.
 */
export function SourcesPanel({ citations, isOpen, onClose }) {
  const list = citations || []

  // Panel luôn nằm trong DOM (kể cả lúc đóng) để có hiệu ứng kéo ra/vô bằng
  // transform thay vì mount/unmount đột ngột — giữ nội dung cũ trong lúc
  // trượt vào để không bị chớp trắng.
  return (
    <div className={`sources-panel ${isOpen ? 'sources-panel--open' : ''}`}>
      <div className="sources-panel-header">
        <div className="sources-panel-title">
          Nguồn trích dẫn <span className="sources-panel-count">· {list.length}</span>
        </div>
        <button className="sources-panel-close" onClick={onClose} aria-label="Đóng">
          <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>
      </div>

      <div className="sources-panel-list">
        {list.map((cit, idx) => (
          <SourcesPanelItem key={`${cit.doc_id || 'doc'}-${cit.chunk_index ?? idx}`} citation={cit} />
        ))}
      </div>
    </div>
  )
}

function SourcesPanelItem({ citation }) {
  // doc_name có thể rỗng nếu tài liệu được ingest trước khi backend thêm field
  // này vào payload Qdrant -> fallback về doc_id cắt ngắn cho dễ đọc.
  const docLabel = citation.doc_name
    ? citation.doc_name
    : citation.doc_id
    ? `Tài liệu ${String(citation.doc_id).slice(0, 8)}`
    : 'Tài liệu'

  const hasChunkIndex = Number.isInteger(citation.chunk_index) && citation.chunk_index >= 0
  const chunkLabel = hasChunkIndex ? `Đoạn ${citation.chunk_index}` : null

  return (
    <div className="sources-panel-item">
      <span className="sources-panel-item-icon">
        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
          <polyline points="14 2 14 8 20 8" />
          <line x1="16" y1="13" x2="8" y2="13" />
          <line x1="16" y1="17" x2="8" y2="17" />
        </svg>
      </span>

      <div className="sources-panel-item-body">
        <div className="sources-panel-item-title">{docLabel}</div>
        {chunkLabel && (
          <div className="sources-panel-item-meta">{chunkLabel}</div>
        )}
        {citation.content_snippet && (
          <div className="sources-panel-item-snippet">"{citation.content_snippet}"</div>
        )}
      </div>
    </div>
  )
}

export function MessageBubble({ message, onShowCitations }) {
  const isUser = message.role === 'user'

  return (
    <div className={`message-row ${isUser ? 'user' : 'assistant'}`}>
      {!isUser && (
        <img
          src="/logo.jpg"
          alt="Ragnarok AI"
          className="message-avatar"
          onError={(e) => {
            e.target.src = 'https://api.dicebear.com/7.x/initials/svg?seed=R&radius=50'
          }}
        />
      )}

      <div className="message-content-wrapper">
        {isUser ? (
          <div className="message-bubble-user">{message.content}</div>
        ) : (
          <div className={`message-bubble-assistant ${message.isStreaming ? 'streaming-text' : ''} ${message.isError || message.isInterrupted ? 'error-text' : ''}`}>
            {message.content && formatContent(message.content)}

            {(message.isError || message.isInterrupted) && (
              <div className="message-interrupted-note">
                <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0Z" />
                  <line x1="12" y1="9" x2="12" y2="13" />
                  <line x1="12" y1="17" x2="12.01" y2="17" />
                </svg>
                <span>
                  {message.content
                    ? (message.isInterrupted
                        ? 'Cuộc trò chuyện đã bị ngắt trước khi câu trả lời hoàn tất.'
                        : 'Đã có lỗi xảy ra giữa chừng, câu trả lời trên có thể chưa đầy đủ.')
                    : (message.isInterrupted
                        ? 'Cuộc trò chuyện đã bị ngắt trước khi nhận được câu trả lời. Bạn gửi lại câu hỏi này giúp mình nhé.'
                        : 'Rất tiếc, đã có lỗi xảy ra khi tạo câu trả lời. Bạn thử gửi lại câu hỏi này nhé.')}
                </span>
              </div>
            )}

            {/* Nút gọn mở panel bên phải liệt kê đầy đủ citations */}
            {message.citations && message.citations.length > 0 && (
              <button
                type="button"
                className="citations-trigger-btn"
                onClick={() => onShowCitations?.(message.citations)}
              >
                <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                  <polyline points="14 2 14 8 20 8" />
                  <line x1="16" y1="13" x2="8" y2="13" />
                  <line x1="16" y1="17" x2="8" y2="17" />
                </svg>
                <span>Nguồn</span>
                <span className="citations-trigger-count">{message.citations.length}</span>
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

// Lightweight parser for simple code blocks and inline code blocks
function formatContent(text) {
  if (!text) return ''
  // Thứ tự alternation quan trọng: `**đậm**` phải đứng trước `*nghiêng*`,
  // nếu không cặp ** sẽ bị mẫu 1-sao ăn mất.
  const parts = text.split(/(```[\s\S]*?```|`.*?`|\*\*.*?\*\*|\*[^*\n]+?\*)/g)

  return parts.map((part, idx) => {
    if (part.startsWith('```') && part.endsWith('```')) {
      const match = part.match(/```(\w*)\n([\s\S]*?)```/)
      const lang = match ? match[1] : ''
      const code = match ? match[2] : part.slice(3, -3)
      return (
        <pre key={idx}>
          <code className={lang}>{code}</code>
        </pre>
      )
    } else if (part.startsWith('**') && part.endsWith('**') && part.length > 4) {
      return <strong key={idx}>{part.slice(2, -2)}</strong>
    } else if (part.startsWith('*') && part.endsWith('*') && part.length > 2) {
      return <em key={idx}>{part.slice(1, -1)}</em>
    } else if (part.startsWith('`') && part.endsWith('`')) {
      return <code key={idx}>{part.slice(1, -1)}</code>
    }
    
    // Support newline breaks in raw text parts
    return part.split('\n').map((line, lineIdx, array) => (
      <span key={`${idx}-${lineIdx}`}>
        {line}
        {lineIdx < array.length - 1 && <br />}
      </span>
    ))
  })
}

import { useState, useRef, useEffect } from 'react'
import { useChat } from '../../../context/ChatContext'
import { ChatWindow } from '../components/ChatWindow'
import { SourcesPanel } from '../components/SourcesPanel'
import '../styles/ChatPage.css'

export function ChatPage() {
  const {
    messages,
    isStreaming,
    streamingText,
    statusMessage,
    llmProvider,
    setLlmProvider,
    sendMessage,
    startNewChat
  } = useChat()

  const [input, setInput] = useState('')
  const textareaRef = useRef(null)

  const [isModelMenuOpen, setIsModelMenuOpen] = useState(false)
  const modelMenuRef = useRef(null)

  // Tách nội dung khỏi trạng thái đóng/mở để panel giữ nguyên citations lúc
  // trượt ra (đóng), tránh chớp trắng khi animation transform đang chạy.
  const [activeCitations, setActiveCitations] = useState(null)
  const [isSourcesPanelOpen, setIsSourcesPanelOpen] = useState(false)

  const handleShowCitations = (citations) => {
    // Bấm lại đúng nút "Nguồn" của tin nhắn đang mở -> đóng panel (toggle)
    if (isSourcesPanelOpen && activeCitations === citations) {
      setIsSourcesPanelOpen(false)
      return
    }
    setActiveCitations(citations)
    setIsSourcesPanelOpen(true)
  }

  const MODEL_OPTIONS = [
    { value: 'ollama', label: 'Ollama', subtitle: 'Chạy local, miễn phí' },
    { value: 'gemini', label: 'Gemini', subtitle: 'Google, cần API key' },
  ]
  const activeModel = MODEL_OPTIONS.find((m) => m.value === llmProvider) || MODEL_OPTIONS[0]

  // Đóng dropdown khi click ra ngoài
  useEffect(() => {
    function handleClickOutside(e) {
      if (modelMenuRef.current && !modelMenuRef.current.contains(e.target)) {
        setIsModelMenuOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  // Auto-grow textarea height
  useEffect(() => {
    const textarea = textareaRef.current
    if (textarea) {
      textarea.style.height = 'auto'
      const scrollHeight = textarea.scrollHeight
      textarea.style.height = `${Math.min(scrollHeight, 180)}px`
      textarea.style.overflowY = scrollHeight > 180 ? 'auto' : 'hidden'
    }
  }, [input])

  const handleSend = () => {
    if (!input.trim() || isStreaming) return
    sendMessage(input.trim())
    setInput('')
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
      textareaRef.current.style.overflowY = 'hidden'
    }
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleSuggestionClick = (promptText) => {
    if (isStreaming) return
    sendMessage(promptText)
  }

  const suggestions = [
    {
      title: 'Chính sách công ty',
      subtitle: 'Tìm hiểu quy định nghỉ phép, bảo hiểm nhân viên năm 2026',
      prompt: 'Hãy tóm tắt chính sách nghỉ phép và hỗ trợ đào tạo của công ty.'
    },
    {
      title: 'Tư vấn sức khỏe',
      subtitle: 'Tra cứu thông tin y tế về triệu chứng cảm cúm thông thường',
      prompt: 'Tôi bị đau họng và nghẹt mũi thì nên làm gì để phục hồi nhanh?'
    },
    {
      title: 'Viết API FastAPI',
      subtitle: 'Tạo đoạn code ví dụ FastAPI hỗ trợ truyền dữ liệu SSE',
      prompt: 'Viết code ví dụ Python FastAPI hỗ trợ stream Server-Sent Events (SSE).'
    },
    {
      title: 'Tải lên tài liệu',
      subtitle: 'Quy trình trích xuất ngữ cảnh RAG từ cơ sở dữ liệu Qdrant',
      prompt: 'Hệ thống Ragnarok trích xuất và hiển thị nguồn trích dẫn RAG như thế nào?'
    }
  ]

  const isWelcome = messages.length === 0 && !isStreaming && !statusMessage

  return (
    <div className="chat-page-layout">
      <div className="chat-container">
        {isWelcome ? (
          <div className="chat-welcome">
            <img
              src="/logo.jpg"
              alt="Ragnarok Logo"
              className="chat-welcome-logo"
              onError={(e) => {
                e.target.src = 'https://api.dicebear.com/7.x/initials/svg?seed=R&radius=50'
              }}
            />
            <h1 className="chat-welcome-title">Tôi có thể giúp gì cho bạn hôm nay?</h1>

            <div className="chat-suggestions-grid">
              {suggestions.map((sug, i) => (
                <button
                  key={i}
                  className="chat-suggestion-card"
                  onClick={() => handleSuggestionClick(sug.prompt)}
                  disabled={isStreaming}
                >
                  <div className="chat-suggestion-title">{sug.title}</div>
                  <div className="chat-suggestion-subtitle">{sug.subtitle}</div>
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="chat-messages-wrapper">
            <ChatWindow
              messages={messages}
              isStreaming={isStreaming}
              streamingText={streamingText}
              statusMessage={statusMessage}
              onShowCitations={handleShowCitations}
            />
          </div>
        )}

        <div className="chat-input-wrapper">
          <div className="chat-input-box">
            <textarea
              ref={textareaRef}
              rows={1}
              placeholder="Gửi tin nhắn đến Ragnarok RAG..."
              className="chat-textarea"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={isStreaming}
            />

            <div className="chat-model-selector" ref={modelMenuRef}>
              <button
                className="chat-model-trigger"
                onClick={() => setIsModelMenuOpen((v) => !v)}
                disabled={isStreaming}
              >
                {activeModel.label}
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <polyline points="6 9 12 15 18 9" />
                </svg>
              </button>

              {isModelMenuOpen && (
                <div className="chat-model-menu">
                  {MODEL_OPTIONS.map((opt) => (
                    <button
                      key={opt.value}
                      className={`chat-model-menu-item ${opt.value === llmProvider ? 'chat-model-menu-item--active' : ''}`}
                      onClick={() => {
                        setLlmProvider(opt.value)
                        setIsModelMenuOpen(false)
                      }}
                    >
                      <div>
                        <div className="chat-model-menu-item-label">{opt.label}</div>
                        <div className="chat-model-menu-item-subtitle">{opt.subtitle}</div>
                      </div>
                      {opt.value === llmProvider && (
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                          <polyline points="20 6 9 17 4 12" />
                        </svg>
                      )}
                    </button>
                  ))}
                </div>
              )}
            </div>

            <button
              className={`chat-send-btn ${input.trim() && !isStreaming ? 'active' : ''}`}
              onClick={handleSend}
              disabled={!input.trim() || isStreaming}
              title="Gửi tin nhắn"
            >
              <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <line x1="12" y1="19" x2="12" y2="5" />
                <polyline points="5 12 12 5 19 12" />
              </svg>
            </button>
          </div>
          <div className="chat-disclaimer">
            Ragnarok RAG có thể đưa ra câu trả lời không chính xác. Vui lòng xác minh các thông tin quan trọng.
          </div>
        </div>
      </div>

      <SourcesPanel
        citations={activeCitations}
        isOpen={isSourcesPanelOpen}
        onClose={() => setIsSourcesPanelOpen(false)}
      />
    </div>
  )
}

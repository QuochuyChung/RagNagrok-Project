import { useEffect, useRef } from 'react'
import { MessageBubble } from './MessageBubble'

export function ChatWindow({
  messages = [],
  isStreaming = false,
  streamingText = '',
  statusMessage = '',
  onShowCitations
}) {
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, streamingText, statusMessage])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '28px', width: '100%' }}>
      {messages.map((message) => (
        <MessageBubble key={message.id} message={message} onShowCitations={onShowCitations} />
      ))}

      {/* RAG vector search status updates */}
      {isStreaming && statusMessage && (
        <div className="rag-status-container">
          <div className="rag-status-spinner"></div>
          <span>{statusMessage}</span>
        </div>
      )}

      {/* Active stream response bubble */}
      {isStreaming && streamingText && (
        <MessageBubble
          message={{
            role: 'assistant',
            content: streamingText,
            isStreaming: true
          }}
        />
      )}

      <div ref={bottomRef} style={{ height: '1px' }} />
    </div>
  )
}

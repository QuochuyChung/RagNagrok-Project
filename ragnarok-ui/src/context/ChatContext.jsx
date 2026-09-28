import { createContext, useContext, useState, useEffect } from 'react'
import { useAuth } from './AuthContext'
import { streamChatMessage } from '../api/endpoints/chat'
import { listConversations, getConversationMessages, deleteConversationApi } from '../api/endpoints/conversations'

const ChatContext = createContext(null)

/** Đổi shape message từ API (role_chat, citation_content JSON string...) sang shape FE đang dùng. */
function mapApiMessages(conversationId, apiMessages) {
  return (apiMessages || []).map((m) => ({
    id: `${conversationId}-${m.message_index}`,
    role: m.role_chat,
    content: m.content,
    citations: m.citation_content ? JSON.parse(m.citation_content) : [],
    createdAt: m.created_at,
    // 'error' = lỗi giữa chừng (LLM/network), 'interrupted' = user rời đi
    // trước khi nhận được câu trả lời (backend chat_service.py lưu lại).
    isError: m.message_type === 'error',
    isInterrupted: m.message_type === 'interrupted',
  }))
}

export function ChatProvider({ children }) {
  const { user } = useAuth()
  const [conversations, setConversations] = useState([])
  const [currentConversationId, setCurrentConversationId] = useState(null)
  const [messages, setMessages] = useState([])
  const [isStreaming, setIsStreaming] = useState(false)
  const [streamingText, setStreamingText] = useState('')
  const [statusMessage, setStatusMessage] = useState('') // Steps like "Searching vector database..."
  const [llmProvider, setLlmProvider] = useState('ollama')

  // Load danh sách hội thoại từ backend mỗi khi đổi user (thay cho localStorage cũ).
  useEffect(() => {
    setMessages([])
    setCurrentConversationId(null)

    if (!user) {
      setConversations([])
      return
    }

    listConversations()
      .then((data) => {
        const mapped = (data.conversations || []).map((c) => ({
          id: c.conversation_id,
          title: c.title,
          updatedAt: c.updated_at,
          turnCount: c.turn_count,
        }))
        setConversations(mapped)
      })
      .catch((err) => {
        console.warn('Không tải được danh sách hội thoại:', err)
        setConversations([])
      })

    // F5 lúc đang mở sẵn 1 hội thoại (URL còn ?id=...) -> tự mở lại đúng hội thoại đó
    const convoIdFromUrl = new URLSearchParams(window.location.search).get('id')
    if (convoIdFromUrl) {
      setCurrentConversationId(convoIdFromUrl)
      getConversationMessages(convoIdFromUrl)
        .then((data) => setMessages(mapApiMessages(convoIdFromUrl, data.messages)))
        .catch((err) => {
          console.warn('Không mở lại được hội thoại từ URL:', err)
          setCurrentConversationId(null)
        })
    }
  }, [user])

  const saveConversations = (updated) => {
    setConversations(updated)
  }

  const startNewChat = () => {
    setCurrentConversationId(null)
    setMessages([])
    setStreamingText('')
    setStatusMessage('')
    
    // Clear URL query parameters
    if (window.history.pushState) {
      const newurl = window.location.protocol + "//" + window.location.host + window.location.pathname
      window.history.pushState({ path: newurl }, '', newurl)
    }
  }

  const selectConversation = (id) => {
    setCurrentConversationId(id)
    setStreamingText('')
    setStatusMessage('')

    getConversationMessages(id)
      .then((data) => setMessages(mapApiMessages(id, data.messages)))
      .catch((err) => {
        console.error('Không tải được lịch sử hội thoại:', err)
        setMessages([])
      })

    // Update URL query parameters
    if (window.history.pushState) {
      const newurl = window.location.protocol + "//" + window.location.host + window.location.pathname + `?id=${id}`
      window.history.pushState({ path: newurl }, '', newurl)
    }
  }

  const deleteConversation = async (id, e) => {
    if (e) e.stopPropagation()
    try {
      await deleteConversationApi(id)
      const updated = conversations.filter(c => c.id !== id)
      saveConversations(updated)
      if (currentConversationId === id) {
        startNewChat()
      }
    } catch (err) {
      console.error('Xóa hội thoại thất bại:', err)
    }
  }

  const sendMessage = async (text) => {
    if (!text.trim() || isStreaming) return

    const userMsg = {
      id: crypto.randomUUID(),
      role: 'user',
      content: text,
      createdAt: new Date().toISOString()
    }
    
    const updatedMessages = [...messages, userMsg]
    setMessages(updatedMessages)
    setIsStreaming(true)
    setStreamingText('')
    setStatusMessage('Đang truy xuất tài liệu và tổng hợp câu trả lời...')

    let fullText = ''
    let citations = []
    let conversationId = currentConversationId

    try {
      for await (const evt of streamChatMessage({
        message: text,
        conversation_id: currentConversationId,
        top_k: 5,
        llm_provider: llmProvider,
      })) {
        if (evt.event === 'citations') {
          citations = evt.data
        } else if (evt.event === 'token') {
          if (!fullText) setStatusMessage('')
          fullText += evt.data
          setStreamingText(fullText)
        } else if (evt.event === 'done') {
          conversationId = evt.data.conversation_id
        } else if (evt.event === 'error') {
          throw new Error(evt.data.message)
        }
      }

      const assistantMsg = {
        id: crypto.randomUUID(),
        role: 'assistant',
        content: fullText,
        citations,
        createdAt: new Date().toISOString()
      }

      const finalMessages = [...updatedMessages, assistantMsg]
      setMessages(finalMessages)

      const activeConvoId = conversationId
      if (!currentConversationId) {
        setCurrentConversationId(activeConvoId)

        const newConvo = {
          id: activeConvoId,
          title: text.length > 30 ? text.substring(0, 30) + '...' : text,
          messages: finalMessages,
          createdAt: new Date().toISOString()
        }
        saveConversations([newConvo, ...conversations])

        // Update URL query parameters
        if (window.history.pushState) {
          const newurl = window.location.protocol + "//" + window.location.host + window.location.pathname + `?id=${activeConvoId}`
          window.history.pushState({ path: newurl }, '', newurl)
        }
      } else {
        const updated = conversations.map(c => {
          if (c.id === activeConvoId) {
            return { ...c, messages: finalMessages }
          }
          return c
        })
        saveConversations(updated)
      }

    } catch (err) {
      console.error('Chat request failed', err)

      // conversation_id lưu ở localStorage có thể trỏ tới hội thoại đã bị xoá
      // (vd sau khi reset DB) -> bỏ id cũ để lượt gửi sau tạo hội thoại mới.
      if (err?.errorCode === 'CONVERSATION_NOT_FOUND') {
        setCurrentConversationId(null)
      }

      const errorMsg = {
        id: crypto.randomUUID(),
        role: 'assistant',
        content: describeChatError(err),
        isError: true,
        createdAt: new Date().toISOString()
      }
      setMessages(prev => [...prev, errorMsg])
    } finally {
      setIsStreaming(false)
      setStreamingText('')
      setStatusMessage('')
    }
  }

  return (
    <ChatContext.Provider value={{
      conversations,
      currentConversationId,
      messages,
      isStreaming,
      streamingText,
      statusMessage,
      llmProvider,
      setLlmProvider,
      startNewChat,
      selectConversation,
      deleteConversation,
      sendMessage
    }}>
      {children}
    </ChatContext.Provider>
  )
}

/** Đổi error_code backend trả về thành thông báo tiếng Việt cho người dùng. */
function describeChatError(err) {
  switch (err?.errorCode) {
    case 'UNAUTHORIZED':
    case 'INVALID_TOKEN':
    case 'TOKEN_EXPIRED':
      return 'Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.'
    case 'FORBIDDEN':
      return 'Tài khoản của bạn không có quyền dùng chức năng chat (chỉ TENANT_ADMIN và USER).'
    case 'CONVERSATION_NOT_FOUND':
      return 'Hội thoại này không còn tồn tại trên máy chủ. Cuộc trò chuyện đã được đặt lại — hãy gửi lại câu hỏi.'
    case 'TENANT_REQUIRED':
    case 'TENANT_NOT_FOUND':
      return 'Không xác định được tenant của bạn. Vui lòng đăng nhập lại.'
    case 'VALIDATION_ERROR':
      return 'Câu hỏi không hợp lệ (rỗng hoặc vượt quá 4000 ký tự).'
    default:
      return err?.message || 'Không thể kết nối đến máy chủ xử lý RAG. Vui lòng thử lại sau.'
  }
}

export function useChat() {
  const context = useContext(ChatContext)
  if (!context) {
    throw new Error('useChat must be used inside ChatProvider')
  }
  return context
}

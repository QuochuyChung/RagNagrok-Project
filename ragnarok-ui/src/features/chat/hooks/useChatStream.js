import { useState } from 'react'
import { streamChat } from '../../../api/endpoints/chat'

export function useChatStream() {
  const [isStreaming, setIsStreaming] = useState(false)
  const [error, setError] = useState(null)

  async function startStream(payload) {
    setIsStreaming(true)
    setError(null)

    try {
      return await streamChat(payload)
    } catch (streamError) {
      setError(streamError)
      throw streamError
    } finally {
      setIsStreaming(false)
    }
  }

  return { error, isStreaming, startStream }
}

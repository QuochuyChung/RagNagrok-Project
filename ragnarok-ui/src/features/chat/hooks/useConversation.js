import { useState } from 'react'

export function useConversation() {
  const [messages, setMessages] = useState([])

  function addMessage(message) {
    setMessages((current) => [
      ...current,
      { id: crypto.randomUUID(), ...message },
    ])
  }

  return { addMessage, messages }
}

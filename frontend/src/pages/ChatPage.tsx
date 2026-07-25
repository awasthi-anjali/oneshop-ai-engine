import { useCallback, useEffect, useRef, useState, type KeyboardEvent } from 'react'
import { getPersonalizationUserId, getStoredSessionId, sendMessage, type ChatMessage } from '../api'
import { applyCheckoutProfileFromChat } from '../checkoutProfile'
import MessageBubble from '../components/MessageBubble'
import '../App.css'

const WELCOME: ChatMessage = {
  role: 'assistant',
  content:
    "Hi! I'm **ShopAssist**, your AI shopping assistant. I can search, compare, **add to cart**, and **start checkout** for you.\n\nTry:\n- \"Show me phones under $500\"\n- \"Compare iPhone 15 Pro vs Samsung S24 Ultra\"\n- \"Add the iPhone 15 Pro and unlimited plan to my cart\"\n- \"I'm ready to checkout\"",
}

const STARTERS = [
  'Show me phones under $500',
  'Compare iPhone vs Samsung',
  'Add iPhone 15 Pro to my cart',
  'I want to checkout',
]

interface Props {
  initialMessage?: string | null
  onConsumed?: () => void
  onOpenCheckout?: () => void
  onCartUpdated?: () => void
  channel?: import('../api').Channel
}

export default function ChatPage({
  initialMessage,
  onConsumed,
  onOpenCheckout,
  onCartUpdated,
  channel = 'oneshop',
}: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([WELCOME])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [sessionId, setSessionId] = useState<string | null>(getStoredSessionId())
  const [suggestions, setSuggestions] = useState<string[]>(STARTERS)
  const [actionBanner, setActionBanner] = useState<string | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const initialSent = useRef(false)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading, actionBanner])

  useEffect(() => {
    if (!actionBanner) return
    const t = setTimeout(() => setActionBanner(null), 6000)
    return () => clearTimeout(t)
  }, [actionBanner])

  const handleSend = useCallback(
    async (text?: string) => {
      const msg = (text ?? input).trim()
      if (!msg || loading) return

      setInput('')
      setActionBanner(null)
      setMessages((prev) => [...prev, { role: 'user', content: msg }])
      setLoading(true)
      setSuggestions([])

      try {
        const res = await sendMessage(msg, sessionId, undefined, channel)
        setSessionId(res.session_id)
        const comparisonProducts = Array.isArray(res.comparison)
          ? res.comparison
          : res.comparison?.products ?? []
        setMessages((prev) => [
          ...prev,
          {
            role: 'assistant',
            content: res.message,
            products: res.recommendations.map((item) => item.product),
            comparison: comparisonProducts.length ? comparisonProducts : undefined,
          },
        ])
        setSuggestions(res.suggested_actions.length > 0 ? res.suggested_actions : STARTERS)

        if (res.cart_updated) {
          setActionBanner('Cart updated — switch to Shop tab to see your items and AI recommendations.')
          onCartUpdated?.()
        }
        if (res.open_checkout) {
          setActionBanner('Opening checkout on Shop tab…')
          onOpenCheckout?.()
        }
        if (res.checkout_profile) {
          applyCheckoutProfileFromChat(getPersonalizationUserId(), res.checkout_profile)
        }
      } catch {
        setMessages((prev) => [
          ...prev,
          {
            role: 'assistant',
            content: 'Sorry, something went wrong. Please make sure the backend is running on port 8000.',
          },
        ])
        setSuggestions(STARTERS)
      } finally {
        setLoading(false)
        inputRef.current?.focus()
      }
    },
    [input, loading, sessionId, onOpenCheckout, onCartUpdated, channel]
  )

  useEffect(() => {
    if (initialMessage && !initialSent.current) {
      initialSent.current = true
      handleSend(initialMessage)
      onConsumed?.()
    }
  }, [initialMessage, handleSend, onConsumed])

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <main className="chat-container">
      {actionBanner && (
        <div className="chat-action-banner">
          <span>✓</span> {actionBanner}
        </div>
      )}

      <div className="messages">
        {messages.map((msg, i) => (
          <MessageBubble key={i} message={msg} />
        ))}
        {loading && (
          <div className="message-row assistant">
            <div className="avatar assistant-avatar">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
                <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2z" />
              </svg>
            </div>
            <div className="bubble assistant-bubble">
              <div className="typing-indicator">
                <span /><span /><span />
              </div>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {suggestions.length > 0 && !loading && (
        <div className="suggestions">
          {suggestions.map((s) => (
            <button key={s} className="suggestion-chip" onClick={() => handleSend(s)}>
              {s}
            </button>
          ))}
        </div>
      )}

      <div className="input-area">
        <textarea
          ref={inputRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask me anything — discover, compare, add to cart, or checkout…"
          rows={1}
          disabled={loading}
        />
        <button
          className="send-btn"
          onClick={() => handleSend()}
          disabled={!input.trim() || loading}
          aria-label="Send message"
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
            <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z" />
          </svg>
        </button>
      </div>
    </main>
  )
}

import ReactMarkdown from 'react-markdown'
import type { ChatMessage } from '../api'
import ProductCard from './ProductCard'
import ComparisonTable from './ComparisonTable'
import './MessageBubble.css'

interface Props {
  message: ChatMessage
}

export default function MessageBubble({ message }: Props) {
  const isUser = message.role === 'user'

  return (
    <div className={`message-row ${isUser ? 'user' : 'assistant'}`}>
      {!isUser && (
        <div className="avatar assistant-avatar">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
            <path
              d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 15h2v2h-2v-2zm0-8h2v6h-2V9z"
              fill="currentColor"
            />
          </svg>
        </div>
      )}
      <div className={`bubble ${isUser ? 'user-bubble' : 'assistant-bubble'}`}>
        {isUser ? (
          <p>{message.content}</p>
        ) : (
          <div className="markdown-content">
            <ReactMarkdown>{message.content}</ReactMarkdown>
          </div>
        )}

        {message.comparison && message.comparison.length >= 2 && (
          <ComparisonTable products={message.comparison} />
        )}

        {message.products && message.products.length > 0 && !message.comparison && (
          <div className="product-scroll">
            {message.products.map((p) => (
              <ProductCard key={p.id} product={p} compact />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

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
        <div className="avatar assistant-avatar" aria-hidden="true">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
            <path
              d="M12 2.8c.55 4.45 2.75 6.65 7.2 7.2-4.45.55-6.65 2.75-7.2 7.2-.55-4.45-2.75-6.65-7.2-7.2 4.45-.55 6.65-2.75 7.2-7.2Z"
              fill="currentColor"
            />
            <circle cx="18.5" cy="18.5" r="1.7" fill="currentColor" />
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

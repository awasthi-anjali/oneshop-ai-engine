import { useEffect, useRef, type KeyboardEvent } from 'react'
import type {
  ChatAction,
  ChatMessage,
  ChatStatus,
  PageContext,
  Product,
  ShoppingNeed,
  ShopAssistRecommendation,
} from '../api'
import ComparisonTable from './ComparisonTable'
import MessageBubble from './MessageBubble'
import './ShopAssistDrawer.css'

interface Props {
  open: boolean
  messages: ChatMessage[]
  draft: string
  loading: boolean
  error: string | null
  status: ChatStatus | null
  mode: 'ai' | 'fallback' | null
  need: ShoppingNeed
  context: PageContext | null
  contextProduct: Product | null
  recommendations: ShopAssistRecommendation[]
  comparison: Product[]
  actions: ChatAction[]
  confirming: boolean
  confirmed: boolean
  onClose: () => void
  onDraftChange: (value: string) => void
  onSend: (message?: string) => void
  onRetry: () => void
  onRemoveContext: () => void
  onRemoveNeed: (key: keyof ShoppingNeed, value?: string) => void
  onAction: (action: ChatAction) => void
  onConfirmBundle: (productIds: string[]) => void
}

const STARTERS = [
  { label: 'Find a phone', text: 'Help me find a phone for my needs.' },
  { label: 'Choose a plan', text: 'Help me choose a mobile plan.' },
  { label: 'Build phone + plan', text: 'Help me build a phone and plan bundle.' },
]

function price(product: Product) {
  const currency = product.currency || 'USD'
  const value = new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency,
    maximumFractionDigits: 0,
  }).format(product.price)
  return product.billing_period === 'monthly' || product.category === 'plan'
    ? `${value}/month`
    : value
}

function needChips(need: ShoppingNeed) {
  const chips: { key: keyof ShoppingNeed; value?: string; label: string }[] = []
  need.categories.forEach((value) => chips.push({ key: 'categories', value, label: value }))
  need.use_cases.forEach((value) => chips.push({ key: 'use_cases', value, label: value }))
  if (need.platform) chips.push({ key: 'platform', label: need.platform })
  if (need.device_budget_max != null) {
    chips.push({ key: 'device_budget_max', label: `Device ≤ $${need.device_budget_max}` })
  }
  if (need.monthly_budget_max != null) {
    chips.push({ key: 'monthly_budget_max', label: `Plan ≤ $${need.monthly_budget_max}/mo` })
  }
  if (need.roaming_required) {
    chips.push({ key: 'roaming_required', label: 'International roaming' })
  }
  if (need.lines != null) chips.push({ key: 'lines', label: `${need.lines} lines` })
  need.must_haves.forEach((value) => chips.push({ key: 'must_haves', value, label: value }))
  need.nice_to_haves.forEach((value) => chips.push({ key: 'nice_to_haves', value, label: value }))
  return chips
}

export default function ShopAssistDrawer({
  open,
  messages,
  draft,
  loading,
  error,
  status,
  mode,
  need,
  context,
  contextProduct,
  recommendations,
  comparison,
  actions,
  confirming,
  confirmed,
  onClose,
  onDraftChange,
  onSend,
  onRetry,
  onRemoveContext,
  onRemoveNeed,
  onAction,
  onConfirmBundle,
}: Props) {
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    inputRef.current?.focus()
    const handleEscape = (event: globalThis.KeyboardEvent) => {
      if (
        event.key === 'Escape' &&
        !document.querySelector('.modal-overlay, .checkout-overlay')
      ) {
        onClose()
      }
    }
    document.addEventListener('keydown', handleEscape)
    return () => document.removeEventListener('keydown', handleEscape)
  }, [open, onClose])

  useEffect(() => {
    if (open) bottomRef.current?.scrollIntoView({ block: 'nearest' })
  }, [messages, loading, open])

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      onSend()
    }
  }

  const proposal = actions.find((action) => action.type === 'PROPOSE_ADD_BUNDLE')
  const proposalProducts = proposal
    ? proposal.product_ids
        .map((id) => recommendations.find((item) => item.product.id === id)?.product)
        .filter((product): product is Product => Boolean(product))
    : []
  const oneTimeTotal = proposalProducts
    .filter((product) => product.billing_period !== 'monthly' && product.category !== 'plan')
    .reduce((sum, product) => sum + product.price, 0)
  const monthlyTotal = proposalProducts
    .filter((product) => product.billing_period === 'monthly' || product.category === 'plan')
    .reduce((sum, product) => sum + product.price, 0)
  const chips = needChips(need)

  return (
    <aside
      className={`shopassist-drawer ${open ? 'open' : ''}`}
      aria-hidden={!open}
      aria-label="ShopAssist purchase guide"
    >
      <header className="shopassist-header">
        <div>
          <div className="shopassist-title-row">
            <h2>ShopAssist</h2>
            {mode && <span className={`assist-mode ${mode}`}>{mode === 'ai' ? 'AI guided' : 'Safe fallback'}</span>}
          </div>
          <p>Phone and plan guidance from this demo catalog</p>
        </div>
        <button className="assist-close" onClick={onClose} aria-label="Close ShopAssist">
          ×
        </button>
      </header>

      <div className="demo-notice" role="note">
        Product, stock, and plan information shown here is synthetic demo data.
      </div>

      {context && (
        <div className="assist-context">
          <span>Context: {contextProduct?.name ?? context.surface}</span>
          <button onClick={onRemoveContext} aria-label="Remove product context">×</button>
        </div>
      )}

      {chips.length > 0 && (
        <section className="need-profile" aria-label="Understood shopping need">
          <div className="need-heading">
            <h3>Your need</h3>
            <span>Remove a chip to draft a refinement</span>
          </div>
          <div className="need-chips">
            {chips.map((chip) => (
              <button
                key={`${chip.key}-${chip.value ?? chip.label}`}
                className="need-chip"
                onClick={() => onRemoveNeed(chip.key, chip.value)}
                aria-label={`Remove ${chip.label}`}
              >
                {chip.label} <span aria-hidden="true">×</span>
              </button>
            ))}
          </div>
        </section>
      )}

      <div className="assist-messages" aria-live="polite">
        {messages.length === 0 ? (
          <section className="assist-welcome">
            <h3>What would you like to choose?</h3>
            <p>I can narrow the demo catalog, explain trade-offs, and prepare an exact cart proposal for you to confirm.</p>
            <div className="assist-starters">
              {STARTERS.map((starter) => (
                <button key={starter.label} onClick={() => onDraftChange(starter.text)}>
                  {starter.label}
                </button>
              ))}
            </div>
          </section>
        ) : (
          messages.map((message, index) => (
            <MessageBubble key={message.id ?? index} message={message} />
          ))
        )}

        {comparison.length === 2 && (
          <section className="drawer-comparison" aria-label="Phone comparison">
            <ComparisonTable products={comparison} />
          </section>
        )}

        {proposal && (
          <section className="proposal-card" aria-label="Cart proposal">
            <span className="proposal-eyebrow">Review exact proposal</span>
            <h3>{proposal.label}</h3>
            {proposalProducts.length === proposal.product_ids.length ? (
              <>
                <ul>
                  {proposalProducts.map((product) => (
                    <li key={product.id}>
                      <span>{product.name}</span>
                      <strong>{price(product)}</strong>
                    </li>
                  ))}
                </ul>
                <div className="proposal-totals">
                  {oneTimeTotal > 0 && <span>Due once: ${oneTimeTotal.toFixed(2)}</span>}
                  {monthlyTotal > 0 && <span>Monthly: ${monthlyTotal.toFixed(2)}/month</span>}
                </div>
                <p>Nothing changes in your cart until you confirm.</p>
                <button
                  className="confirm-proposal"
                  onClick={() => onConfirmBundle(proposal.product_ids)}
                  disabled={confirming || confirmed}
                >
                  {confirming ? 'Adding…' : confirmed ? 'Added to cart' : 'Confirm and add exact bundle'}
                </button>
              </>
            ) : (
              <p className="proposal-warning">This proposal is stale or incomplete. Refine your request before confirming.</p>
            )}
          </section>
        )}

        {actions.filter((action) => action !== proposal).length > 0 && (
          <div className="assist-actions" aria-label="ShopAssist actions">
            {actions
              .filter((action) => action !== proposal)
              .map((action) =>
                action.type === 'HANDOFF_SERVICE' ? (
                  <span className="assist-handoff" key={`${action.type}-${action.label}`}>
                    {action.label}
                  </span>
                ) : (
                  <button key={`${action.type}-${action.label}`} onClick={() => onAction(action)}>
                    {action.label}
                  </button>
                )
              )}
          </div>
        )}

        {loading && <div className="assist-loading" role="status">ShopAssist is checking the catalog…</div>}
        {error && (
          <div className="assist-error" role="alert">
            <span>{error}</span>
            <button onClick={onRetry}>Try again</button>
          </div>
        )}
        {status && status !== 'recommended' && (
          <span className={`assist-status ${status}`}>{status.replace('_', ' ')}</span>
        )}
        <div ref={bottomRef} />
      </div>

      <footer className="assist-composer">
        <label htmlFor="shopassist-input">Describe what you need</label>
        <div>
          <textarea
            id="shopassist-input"
            ref={inputRef}
            value={draft}
            maxLength={1000}
            rows={2}
            onChange={(event) => onDraftChange(event.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="For example: Android camera phone under $700"
            disabled={loading}
          />
          <button
            className="assist-send"
            onClick={() => onSend()}
            disabled={loading || !draft.trim()}
            aria-label="Send to ShopAssist"
          >
            Send
          </button>
        </div>
        <span className="composer-help">Enter to send · Shift+Enter for a new line</span>
      </footer>
    </aside>
  )
}

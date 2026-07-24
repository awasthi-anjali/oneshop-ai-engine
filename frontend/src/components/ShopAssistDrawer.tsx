import { useEffect, useRef, useState, type KeyboardEvent } from 'react'
import { useSpeechToText } from '../hooks/useSpeechToText'
import type {
  ChatAction,
  CartProposal,
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
  recommendationMode: 'profile' | 'request'
  recommendationHeading: string
  comparison: Product[]
  actions: ChatAction[]
  cartProposal: CartProposal | null
  confirming: boolean
  confirmed: boolean
  onClose: () => void
  onDraftChange: (value: string) => void
  onSend: (message?: string) => void
  onRetry: () => void
  onRemoveContext: () => void
  onRemoveNeed: (key: keyof ShoppingNeed, value?: string) => void
  onAction: (action: ChatAction) => void
  onConfirmProposal: (proposalId: string) => void
  onViewPicks: () => void
}

const MAX_MESSAGE_LENGTH = 1000

const STARTERS = [
  { label: 'Find a phone', text: 'Help me find a phone for my needs.' },
  { label: 'Choose a plan', text: 'Help me choose a mobile plan.' },
  { label: 'Build phone + plan', text: 'Help me build a phone and plan bundle.' },
]

const BUDGET_REPLIES = [
  { label: '$500 phone + $60 plan', text: 'Android phone under $500 and plan under $60 per month.' },
  { label: '$800 phone + $90 plan', text: 'Android phone under $800 and plan under $90 per month.' },
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

function recommendationLabel(recommendation: ShopAssistRecommendation, index: number, mode: 'profile' | 'request') {
  if (mode === 'profile') return index === 0 ? 'Top pick' : 'For you'
  if (recommendation.slot === 'primary_phone') return 'Best match'
  if (recommendation.slot === 'alternative_phone') return 'Alternative'
  return 'Plan'
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
  recommendationMode,
  recommendationHeading,
  comparison,
  actions,
  cartProposal,
  confirming,
  confirmed,
  onClose,
  onDraftChange,
  onSend,
  onRetry,
  onRemoveContext,
  onRemoveNeed,
  onAction,
  onConfirmProposal,
  onViewPicks,
}: Props) {
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  const recommendationsRef = useRef<HTMLElement>(null)
  const [selectedRecommendationId, setSelectedRecommendationId] = useState<string | null>(null)
  const [voiceNotice, setVoiceNotice] = useState<string | null>(null)

  const { listening, supported, toggle, abort } = useSpeechToText({
    disabled: loading,
    onInterim: onDraftChange,
    onFinal: (text) => {
      setVoiceNotice(null)
      onSend(text.slice(0, MAX_MESSAGE_LENGTH))
    },
    onError: setVoiceNotice,
  })

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

  useEffect(() => {
    setSelectedRecommendationId(
      recommendationMode === 'request' ? recommendations[0]?.product.id ?? null : null,
    )
    if (open && recommendationMode === 'request' && recommendations.length > 0) {
      recommendationsRef.current?.scrollIntoView({ block: 'start' })
    }
  }, [open, recommendationMode, recommendations])

  useEffect(() => {
    if (!open) {
      abort()
      setVoiceNotice(null)
    }
  }, [abort, open])

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      onSend()
    }
  }

  const proposalProducts = cartProposal?.products ?? []
  const proposalIsComplete = Boolean(
    cartProposal
    && proposalProducts.length === cartProposal.product_ids.length
    && proposalProducts.every((product, index) => product.id === cartProposal.product_ids[index]),
  )
  const chips = needChips(need)
  const comparisonIds = recommendations
    .filter((recommendation) => recommendation.product.category === 'phone')
    .map((recommendation) => recommendation.product.id)
    .slice(0, 2)
  const comparisonOffered = actions.some((action) => action.type === 'COMPARE')
  const selectedRecommendation = recommendations.find(
    (recommendation) => recommendation.product.id === selectedRecommendationId,
  )
  const selectedRecommendationIndex = selectedRecommendation
    ? recommendations.indexOf(selectedRecommendation)
    : -1
  const contextLabel = contextProduct
    ? `Helping with ${contextProduct.name}`
    : context?.surface === 'cart' || context?.entry_point === 'cart'
      ? 'Using your cart'
      : context?.entry_point === 'next_best_action'
        ? 'From next best action'
        : null
  const supplementalActions = actions.filter(
    (action) => action.type === 'HANDOFF_SERVICE',
  )
  const latestMessage = messages[messages.length - 1]
  const showRecommendations = recommendations.length > 0 && (
    recommendationMode === 'profile'
      ? messages.length === 0
      : latestMessage?.role === 'assistant' && !loading
  )
  const waitingForBundleBudgets = (
    status === 'clarifying'
    && need.categories.includes('phone')
    && need.categories.includes('plan')
    && need.device_budget_max == null
    && need.monthly_budget_max == null
  )
  const quickReplies = status === 'clarifying' && latestMessage?.role === 'assistant' && !loading
    ? waitingForBundleBudgets ? BUDGET_REPLIES : STARTERS
    : []

  return (
    <aside
      className={`shopassist-drawer ${open ? 'open' : ''}`}
      aria-hidden={!open}
      aria-label="ShopAssist purchase guide"
    >
      <header className="shopassist-header">
        <div className="shopassist-title-row">
          <h2>ShopAssist</h2>
          {mode && (
            <span className={`assist-mode ${mode}`}>
              {mode === 'ai' ? 'AI guided' : 'Catalog mode'}
            </span>
          )}
        </div>
        <button className="assist-close" onClick={onClose} aria-label="Close ShopAssist">
          ×
        </button>
      </header>

      <div className="assist-messages" aria-live="polite">
        {contextLabel && (
          <div className="assist-context">
            <span>{contextLabel}</span>
            <button onClick={onRemoveContext} aria-label={`Remove context: ${contextLabel}`}>×</button>
          </div>
        )}

        {chips.length > 0 && (
          <section className="need-profile" aria-label="Understood shopping need">
            <div className="need-heading">
              <h3>Your need</h3>
              <span>Remove a chip to refine</span>
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

        {messages.length === 0 ? (
          <section className="assist-welcome">
            <h3>What would you like to choose?</h3>
            <p>I can narrow the catalog, explain trade-offs, and prepare an exact cart proposal for you to confirm.</p>
            <div className="assist-starters">
              {STARTERS.map((starter) => (
                <button key={starter.label} onClick={() => onSend(starter.text)}>
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

        {quickReplies.length > 0 && (
          <div className="assist-quick-replies" aria-label="Quick replies">
            {quickReplies.map((reply) => (
              <button
                type="button"
                key={reply.label}
                onClick={() => onSend(reply.text)}
              >
                {reply.label}
              </button>
            ))}
          </div>
        )}

        {showRecommendations && (
          <section
            ref={recommendationsRef}
            className="assist-recommendations"
            aria-labelledby="assist-recommendations-heading"
          >
            <div className="assist-recommendations-heading">
              <div>
                <span>
                  {recommendationMode === 'profile' ? 'Based on your profile' : 'Catalog-validated matches'}
                </span>
                <h3 id="assist-recommendations-heading">{recommendationHeading}</h3>
              </div>
              <button type="button" onClick={onViewPicks}>
                {recommendationMode === 'profile' ? 'View For You' : 'View in shop'}
              </button>
            </div>
            <div className="assist-recommendation-pills" aria-label="Recommended products">
              {recommendations.map((recommendation, index) => (
                <button
                  type="button"
                  className={`assist-recommendation-pill ${
                    selectedRecommendationId === recommendation.product.id ? 'selected' : ''
                  }`}
                  key={`${recommendation.slot}-${recommendation.product.id}`}
                  aria-pressed={selectedRecommendationId === recommendation.product.id}
                  aria-label={`${recommendationLabel(recommendation, index, recommendationMode)}: ${recommendation.product.name}, ${price(recommendation.product)}`}
                  onClick={() => {
                    setSelectedRecommendationId((current) =>
                      current === recommendation.product.id ? null : recommendation.product.id,
                    )
                  }}
                >
                  <img src={recommendation.product.image_url} alt="" />
                  <span>
                    <small>{recommendationLabel(recommendation, index, recommendationMode)}</small>
                    <strong>{recommendation.product.name}</strong>
                    <em>{price(recommendation.product)}</em>
                  </span>
                </button>
              ))}
            </div>

            {selectedRecommendation && (
              <article className="assist-recommendation-preview" aria-live="polite">
                <div className="assist-preview-heading">
                  <span>
                    {recommendationLabel(
                      selectedRecommendation,
                      selectedRecommendationIndex,
                      recommendationMode,
                    )}
                  </span>
                  <strong>{selectedRecommendation.product.name}</strong>
                  <em>{price(selectedRecommendation.product)}</em>
                </div>
                <p>{selectedRecommendation.reason.split(';')[0].trim()}</p>
                {selectedRecommendation.reason_codes.length > 0 && (
                  <div className="assist-reason-badges" aria-label="Matched constraints">
                    {selectedRecommendation.reason_codes.slice(0, 2).map((code) => (
                      <span key={code}>{code.replace(/_/g, ' ').toLowerCase()}</span>
                    ))}
                  </div>
                )}
                <div className="assist-preview-actions">
                  <button
                    type="button"
                    onClick={() => onAction({
                      type: 'OPEN_PRODUCT',
                      label: `Open ${selectedRecommendation.product.name}`,
                      product_ids: [selectedRecommendation.product.id],
                    })}
                  >
                    Open product
                  </button>
                  {comparisonIds.length === 2 && comparisonOffered && (
                    <button
                      type="button"
                      onClick={() => onAction({
                        type: 'COMPARE',
                        label: 'Compare recommended phones',
                        product_ids: comparisonIds,
                      })}
                    >
                      Compare phones
                    </button>
                  )}
                </div>
              </article>
            )}

            {recommendationMode === 'request' && (
              <div className="assist-recommendation-actions">
                <button
                  type="button"
                  onClick={() => onDraftChange('Refine these recommendations: ')}
                >
                  Refine results
                </button>
              </div>
            )}
          </section>
        )}

        {comparison.length === 2 && (
          <section className="drawer-comparison" aria-label="Phone comparison">
            <ComparisonTable products={comparison} />
          </section>
        )}

        {cartProposal && (
          <section className="proposal-card" aria-label="Cart proposal">
            <span className="proposal-eyebrow">Review exact proposal</span>
            <h3>{proposalProducts.map((product) => product.name).join(' + ')}</h3>
            {proposalIsComplete ? (
              <>
                <div className="proposal-items">
                  {proposalProducts.map((product) => (
                    <span className="proposal-item-pill" key={product.id}>
                      <img src={product.image_url} alt="" />
                      <span>
                        <strong>{product.name}</strong>
                        <small>{price(product)}</small>
                      </span>
                    </span>
                  ))}
                </div>
                <div className="proposal-totals">
                  {cartProposal.one_time_total > 0 && <span>Due once: ${cartProposal.one_time_total.toFixed(2)}</span>}
                  {cartProposal.monthly_total > 0 && <span>Monthly: ${cartProposal.monthly_total.toFixed(2)}/month</span>}
                </div>
                {cartProposal.excluded_product_ids.length > 0 && (
                  <p>
                    {cartProposal.excluded_product_ids.length} item
                    {cartProposal.excluded_product_ids.length === 1 ? '' : 's'} already in your cart will not be added twice.
                  </p>
                )}
                <p>Nothing changes in your cart until you confirm.</p>
                <button
                  className="confirm-proposal"
                  onClick={() => onConfirmProposal(cartProposal.proposal_id)}
                  disabled={confirming || confirmed}
                >
                  {confirming
                    ? 'Adding…'
                    : confirmed
                      ? 'Added to cart'
                      : proposalProducts.length === 1
                        ? 'Confirm and add exact item'
                        : 'Confirm and add exact bundle'}
                </button>
              </>
            ) : (
              <p className="proposal-warning">This proposal is stale or incomplete. Refine your request before confirming.</p>
            )}
          </section>
        )}

        {supplementalActions.length > 0 && (
          <div className="assist-actions" aria-label="ShopAssist actions">
            {supplementalActions.map((action) => (
              <span className="assist-handoff" key={`${action.type}-${action.label}`}>
                {action.label}
              </span>
            ))}
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
            maxLength={MAX_MESSAGE_LENGTH}
            rows={2}
            onChange={(event) => onDraftChange(event.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="For example: Android camera phone under $700"
            disabled={loading || listening}
            aria-describedby={voiceNotice ? 'shopassist-voice-notice' : undefined}
          />
          {supported && (
            <button
              type="button"
              className={`assist-mic ${listening ? 'listening' : ''}`}
              onClick={() => {
                setVoiceNotice(null)
                toggle()
              }}
              disabled={loading}
              aria-label={listening ? 'Stop voice input' : 'Start voice input'}
              aria-pressed={listening}
            >
              <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                <path d="M12 14a3 3 0 0 0 3-3V6a3 3 0 1 0-6 0v5a3 3 0 0 0 3 3Z" />
                <path d="M19 11a1 1 0 1 0-2 0 5 5 0 0 1-10 0 1 1 0 1 0-2 0 7 7 0 0 0 6 6.92V21H9a1 1 0 1 0 0 2h6a1 1 0 1 0 0-2h-2v-3.08A7 7 0 0 0 19 11Z" />
              </svg>
            </button>
          )}
          <button
            className="assist-send"
            onClick={() => onSend()}
            disabled={loading || listening || !draft.trim()}
            aria-label="Send to ShopAssist"
          >
            Send
          </button>
        </div>
        {voiceNotice ? (
          <span id="shopassist-voice-notice" className="composer-help voice-notice" role="status">
            {voiceNotice}
          </span>
        ) : (
          <span className="composer-help">
            {supported
              ? 'Mic to speak and search · Enter to send · Shift+Enter for a new line'
              : 'Enter to send · Shift+Enter for a new line'}
          </span>
        )}
        <p className="assist-disclosure">
          AI-guided answers can be inaccurate. Product facts, prices, and cart changes are validated by OneShop.
        </p>
      </footer>
    </aside>
  )
}

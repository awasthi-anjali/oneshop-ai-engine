import { useEffect, useState } from 'react'
import type { CheckoutReview, Product } from '../api'
import { createCheckoutReview } from '../api'
import './CheckoutModal.css'

interface Props {
  open: boolean
  cart: Product[]
  sessionId: string | null
  userId: string
  onClose: () => void
  onReview: (review: CheckoutReview) => void
}

const SUCCESS_CARD = '4242424242424242'
const DECLINED_CARD = '4000000000000002'

function formatCard(value: string) {
  return value.replace(/\D/g, '').slice(0, 16).replace(/(\d{4})(?=\d)/g, '$1 ')
}

export default function CheckoutModal({
  open,
  cart,
  sessionId,
  userId,
  onClose,
  onReview,
}: Props) {
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [card, setCard] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [review, setReview] = useState<CheckoutReview | null>(null)
  const oneTimeTotal = cart
    .filter((product) => product.billing_period !== 'monthly' && product.category !== 'plan')
    .reduce((total, product) => total + product.price, 0)
  const monthlyTotal = cart
    .filter((product) => product.billing_period === 'monthly' || product.category === 'plan')
    .reduce((total, product) => total + product.price, 0)

  useEffect(() => {
    if (!open) {
      setCard('')
      setReview(null)
      setError('')
    }
  }, [open])

  if (!open) return null

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault()
    setError('')
    if (!sessionId) {
      setError('Your session is not ready. Close checkout and try again.')
      return
    }
    const digits = card.replace(/\D/g, '')
    if (digits !== SUCCESS_CARD && digits !== DECLINED_CARD) {
      setError('Use one of the approved demo card numbers shown below.')
      return
    }
    setLoading(true)
    try {
      const result = await createCheckoutReview(
        sessionId,
        userId,
        name.trim(),
        email.trim(),
        digits === SUCCESS_CARD ? 'demo_card_success' : 'demo_card_declined',
      )
      setCard('')
      setReview(result)
    } catch (err) {
      setCard('')
      setError(err instanceof Error ? err.message : 'Demo checkout failed')
    } finally {
      setLoading(false)
    }
  }

  if (review) {
    return (
      <div className="checkout-overlay" onClick={onClose}>
        <div
          className="checkout-modal"
          role="dialog"
          aria-modal="true"
          aria-labelledby="checkout-review-title"
          onClick={(event) => event.stopPropagation()}
        >
          <button className="checkout-close" onClick={onClose} aria-label="Close checkout">×</button>
          <span className="checkout-step">Final trusted review</span>
          <h2 id="checkout-review-title">Review your demo order</h2>
          <p className="checkout-subtitle">
            Nothing is ordered until you continue to Ava and explicitly confirm.
          </p>
          <div className="checkout-items">
            {review.items.map((item) => (
              <div key={item.product_id} className="checkout-item">
                <div>
                  <span className="item-name">{item.name}</span>
                  <span className="item-price">
                    ${(item.unit_amount_minor / 100).toFixed(2)}
                    {item.billing_period === 'monthly' ? '/month' : ' once'}
                  </span>
                </div>
              </div>
            ))}
          </div>
          <div className="checkout-summary">
            {review.one_time_total_minor > 0 && (
              <div className="summary-row total">
                <span>Due once</span>
                <span>${(review.one_time_total_minor / 100).toFixed(2)}</span>
              </div>
            )}
            {review.monthly_total_minor > 0 && (
              <div className="summary-row total">
                <span>Monthly service</span>
                <span>${(review.monthly_total_minor / 100).toFixed(2)}/month</span>
              </div>
            )}
          </div>
          <p className="demo-payment-notice">
            Demo card ending {review.payment_last4}. No payment or charge occurs.
            Taxes, fees, shipping, eligibility, and activation are not calculated.
          </p>
          <button
            type="button"
            className="checkout-submit"
            onClick={() => onReview(review)}
          >
            Continue in Ava to confirm
          </button>
          <button type="button" className="checkout-secondary" onClick={onClose}>
            Edit cart
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="checkout-overlay" onClick={onClose}>
      <div
        className="checkout-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="checkout-title"
        onClick={(event) => event.stopPropagation()}
      >
        <button className="checkout-close" onClick={onClose} aria-label="Close checkout">×</button>
        <span className="checkout-step">Checkout details</span>
        <h2 id="checkout-title">Prepare a demo order</h2>
        <p className="checkout-subtitle">
          {cart.length} {cart.length === 1 ? 'item' : 'items'} in your cart
        </p>

        <div className="checkout-items">
          {cart.map((product) => (
            <div key={product.id} className="checkout-item">
              <img src={product.image_url} alt="" />
              <div>
                <span className="item-name">{product.name}</span>
                <span className="item-price">
                  {product.category === 'plan' ? `$${product.price}/month` : `$${product.price} once`}
                </span>
              </div>
            </div>
          ))}
        </div>

        <div className="checkout-summary">
          {oneTimeTotal > 0 && (
            <div className="summary-row total">
              <span>Due once</span>
              <span>${oneTimeTotal.toFixed(2)}</span>
            </div>
          )}
          {monthlyTotal > 0 && (
            <div className="summary-row total">
              <span>Monthly service</span>
              <span>${monthlyTotal.toFixed(2)}/month</span>
            </div>
          )}
          <p className="checkout-subtitle">No promotional discount is assumed.</p>
        </div>

        <form className="checkout-form" onSubmit={handleSubmit}>
          <label>
            Full name
            <input value={name} onChange={(event) => setName(event.target.value)} required maxLength={80} />
          </label>
          <label>
            Email for this demo receipt
            <input
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
              maxLength={254}
            />
          </label>
          <label>
            Demo card number
            <input
              inputMode="numeric"
              autoComplete="off"
              value={card}
              onChange={(event) => setCard(formatCard(event.target.value))}
              placeholder="4242 4242 4242 4242"
              maxLength={19}
              required
            />
          </label>
          <div className="demo-card-options" aria-label="Approved demo card numbers">
            <button type="button" onClick={() => setCard(formatCard(SUCCESS_CARD))}>
              Use 4242 4242 4242 4242 — success
            </button>
            <button type="button" onClick={() => setCard(formatCard(DECLINED_CARD))}>
              Use 4000 0000 0000 0002 — decline
            </button>
          </div>
          <p className="demo-payment-notice">
            Demo card only — no real payment is processed. Do not enter real card information.
            The raw number stays in this form and is never sent to OneShop.
          </p>
          {error && <p className="checkout-error" role="alert">{error}</p>}
          <button type="submit" className="checkout-submit" disabled={loading || cart.length === 0}>
            {loading ? 'Validating demo details…' : 'Create final review'}
          </button>
        </form>
      </div>
    </div>
  )
}

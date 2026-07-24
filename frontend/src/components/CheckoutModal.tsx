import { useState } from 'react'
import type { CheckoutResponse, Product } from '../api'
import { completeCheckout } from '../api'
import './CheckoutModal.css'

interface Props {
  open: boolean
  cart: Product[]
  sessionId: string | null
  subtotal: number
  estimatedSavings: number
  discountOffer: number
  onClose: () => void
  onSuccess: (order: CheckoutResponse) => void
}

export default function CheckoutModal({
  open,
  cart,
  sessionId,
  subtotal,
  estimatedSavings,
  discountOffer,
  onClose,
  onSuccess,
}: Props) {
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [card, setCard] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [order, setOrder] = useState<CheckoutResponse | null>(null)

  if (!open) return null

  const discountAmount = subtotal * (discountOffer / 100)
  const total = Math.max(subtotal - estimatedSavings - discountAmount, 0)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const last4 = card.replace(/\D/g, '').slice(-4) || '4242'
      const result = await completeCheckout(sessionId, name.trim(), email.trim(), last4)
      setOrder(result)
      onSuccess(result)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Checkout failed')
    } finally {
      setLoading(false)
    }
  }

  if (order) {
    return (
      <div className="checkout-overlay" onClick={onClose}>
        <div className="checkout-modal success" onClick={(e) => e.stopPropagation()}>
          <div className="checkout-success-icon">✓</div>
          <h2>Order Confirmed!</h2>
          <p className="order-id">Order {order.order_id}</p>
          <p>{order.message}</p>
          <div className="checkout-summary">
            <div className="summary-row total">
              <span>Total paid</span>
              <span>${order.total.toFixed(2)}</span>
            </div>
          </div>
          <button className="checkout-submit" onClick={onClose}>Continue Shopping</button>
        </div>
      </div>
    )
  }

  return (
    <div className="checkout-overlay" onClick={onClose}>
      <div className="checkout-modal" onClick={(e) => e.stopPropagation()}>
        <button className="checkout-close" onClick={onClose}>×</button>
        <h2>Checkout</h2>
        <p className="checkout-subtitle">{cart.length} item(s) in your cart</p>

        <div className="checkout-items">
          {cart.map((p) => (
            <div key={p.id} className="checkout-item">
              <img src={p.image_url} alt={p.name} />
              <div>
                <span className="item-name">{p.name}</span>
                <span className="item-price">
                  {p.category === 'plan' ? `$${p.price}/mo` : `$${p.price}`}
                </span>
              </div>
            </div>
          ))}
        </div>

        <div className="checkout-summary">
          <div className="summary-row">
            <span>Subtotal</span>
            <span>${subtotal.toFixed(2)}</span>
          </div>
          {estimatedSavings > 0 && (
            <div className="summary-row savings">
              <span>Bundle savings</span>
              <span>-${estimatedSavings.toFixed(2)}</span>
            </div>
          )}
          {discountOffer > 0 && (
            <div className="summary-row savings">
              <span>Recovery discount ({discountOffer}%)</span>
              <span>-${discountAmount.toFixed(2)}</span>
            </div>
          )}
          <div className="summary-row total">
            <span>Total</span>
            <span>${total.toFixed(2)}</span>
          </div>
        </div>

        <form className="checkout-form" onSubmit={handleSubmit}>
          <label>
            Full name
            <input value={name} onChange={(e) => setName(e.target.value)} required />
          </label>
          <label>
            Email
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
          </label>
          <label>
            Card number (demo)
            <input
              value={card}
              onChange={(e) => setCard(e.target.value)}
              placeholder="4242 4242 4242 4242"
              maxLength={19}
            />
          </label>
          {error && <p className="checkout-error">{error}</p>}
          <button type="submit" className="checkout-submit" disabled={loading || cart.length === 0}>
            {loading ? 'Processing…' : `Pay $${total.toFixed(2)}`}
          </button>
        </form>
      </div>
    </div>
  )
}

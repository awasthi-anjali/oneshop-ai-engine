import { useEffect, useState } from 'react'
import type { CheckoutResponse, Product } from '../api'
import { completeCheckout } from '../api'
import {
  fetchCheckoutProfile,
  formatCardNumber,
  saveCheckoutProfile,
} from '../checkoutProfile'
import './CheckoutModal.css'

interface Props {
  open: boolean
  cart: Product[]
  sessionId: string | null
  userId: string
  oneTimeTotal: number
  monthlyTotal: number
  onClose: () => void
  onSuccess: (order: CheckoutResponse) => void
}

export default function CheckoutModal({
  open,
  cart,
  sessionId,
  userId,
  oneTimeTotal,
  monthlyTotal,
  onClose,
  onSuccess,
}: Props) {
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [card, setCard] = useState('')
  const [loading, setLoading] = useState(false)
  const [profileLoading, setProfileLoading] = useState(false)
  const [error, setError] = useState('')
  const [order, setOrder] = useState<CheckoutResponse | null>(null)
  const [step, setStep] = useState<'details' | 'confirm'>('details')

  useEffect(() => {
    if (!open) return
    setStep('details')
    setOrder(null)
    setError('')
    let cancelled = false
    setProfileLoading(true)
    fetchCheckoutProfile(userId)
      .then((profile) => {
        if (cancelled) return
        setName(profile.full_name)
        setEmail(profile.email)
        setCard(formatCardNumber(profile.card_number))
      })
      .finally(() => {
        if (!cancelled) setProfileLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [open, userId])

  const persistProfile = async (patch: {
    full_name?: string
    email?: string
    card_number?: string
  }) => {
    await saveCheckoutProfile(userId, patch)
  }

  if (!open) return null

  const handleContinue = (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    if (!name.trim() || !email.trim()) {
      setError('Enter your name and email to continue.')
      return
    }
    setStep('confirm')
  }

  const handleConfirmOrder = async () => {
    setError('')
    setLoading(true)
    try {
      const cardDigits = card.replace(/\D/g, '')
      await persistProfile({
        full_name: name.trim(),
        email: email.trim(),
        card_number: cardDigits,
      })
      const last4 = cardDigits.slice(-4) || '4242'
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
          {order.receipt_sent ? (
            <p className="checkout-subtitle">Check your Gmail inbox for the HTML receipt from Eva.</p>
          ) : (
            <p className="checkout-subtitle">
              Inbox delivery is not configured on the server yet. Use the receipt link below.
            </p>
          )}
          {order.receipt_url && (
            <p className="checkout-subtitle">
              <a
                href={order.receipt_url}
                target="_blank"
                rel="noopener noreferrer"
              >
                View HTML receipt from {order.receipt_from || 'Eva'}
              </a>
            </p>
          )}
          <div className="checkout-summary">
            {order.one_time_total > 0 && (
              <div className="summary-row total">
                <span>Paid once</span>
                <span>${order.one_time_total.toFixed(2)}</span>
              </div>
            )}
            {order.monthly_total > 0 && (
              <div className="summary-row total">
                <span>Monthly service</span>
                <span>${order.monthly_total.toFixed(2)}/month</span>
              </div>
            )}
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
          <p className="checkout-subtitle">Receipts are sent by Eva (eva@gmail.com) after you confirm the order.</p>
        </div>

        {step === 'details' ? (
        <form className="checkout-form" onSubmit={handleContinue}>
          <label>
            Full name
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              disabled={profileLoading}
            />
          </label>
          <label>
            Email
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              disabled={profileLoading}
            />
          </label>
          <label>
            Card number (demo)
            <input
              value={card}
              onChange={(e) => setCard(formatCardNumber(e.target.value))}
              placeholder="4242 4242 4242 4242"
              maxLength={23}
              disabled={profileLoading}
            />
          </label>
          {error && <p className="checkout-error">{error}</p>}
          <button type="submit" className="checkout-submit" disabled={profileLoading || cart.length === 0}>
            Continue
          </button>
        </form>
        ) : (
        <div className="checkout-form">
          <div className="checkout-summary">
            <p className="checkout-subtitle"><strong>{name.trim()}</strong></p>
            <p className="checkout-subtitle">Receipt email: <strong>{email.trim()}</strong></p>
            <p className="checkout-subtitle">Card ending in <strong>{card.replace(/\D/g, '').slice(-4) || '4242'}</strong></p>
          </div>
          {error && <p className="checkout-error">{error}</p>}
          <button
            type="button"
            className="checkout-submit"
            disabled={loading || cart.length === 0}
            onClick={() => void handleConfirmOrder()}
          >
            {loading ? 'Processing…' : 'Confirm order'}
          </button>
          <button
            type="button"
            className="checkout-close-secondary"
            disabled={loading}
            onClick={() => setStep('details')}
          >
            Back
          </button>
        </div>
        )}
      </div>
    </div>
  )
}

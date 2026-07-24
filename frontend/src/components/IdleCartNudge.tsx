import { useEffect, useRef, useState } from 'react'
import type { Product } from '../api'
import './IdleCartNudge.css'

interface Props {
  cartItems: Product[]
  onCheckout: () => void
  onDismiss: () => void
}

const IDLE_MS = 30_000
const CHECK_MS = 5_000

export default function IdleCartNudge({ cartItems, onCheckout, onDismiss }: Props) {
  const [show, setShow] = useState(false)
  const lastInteraction = useRef(Date.now())

  useEffect(() => {
    const resetTimer = () => {
      lastInteraction.current = Date.now()
      setShow(false)
    }
    window.addEventListener('click', resetTimer)
    window.addEventListener('keydown', resetTimer)
    window.addEventListener('scroll', resetTimer, { passive: true })
    return () => {
      window.removeEventListener('click', resetTimer)
      window.removeEventListener('keydown', resetTimer)
      window.removeEventListener('scroll', resetTimer)
    }
  }, [])

  useEffect(() => {
    if (cartItems.length === 0) {
      setShow(false)
      return
    }

    const interval = window.setInterval(() => {
      if (Date.now() - lastInteraction.current > IDLE_MS) {
        setShow(true)
      }
    }, CHECK_MS)

    return () => window.clearInterval(interval)
  }, [cartItems.length])

  if (!show || cartItems.length === 0) return null

  const total = cartItems.reduce((sum, item) => sum + item.price, 0)

  return (
    <div className="idle-cart-nudge" role="dialog" aria-label="Cart reminder">
      <button type="button" className="idle-nudge-close" onClick={() => { setShow(false); onDismiss() }} aria-label="Dismiss">
        ✕
      </button>
      <p className="idle-nudge-title">🔔 Still thinking?</p>
      <p className="idle-nudge-body">
        You have {cartItems.length} item{cartItems.length > 1 ? 's' : ''} worth ${total.toFixed(2)} in your cart.
      </p>
      <p className="idle-nudge-hint">
        These items are popular — complete your purchase before they&apos;re gone!
      </p>
      <button type="button" className="idle-nudge-checkout" onClick={() => { setShow(false); onCheckout() }}>
        Complete Purchase
      </button>
    </div>
  )
}

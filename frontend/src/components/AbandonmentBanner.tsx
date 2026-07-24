import './AbandonmentBanner.css'

interface Props {
  message: string
  discount: number
  onCheckout: () => void
  onDismiss: () => void
}

export default function AbandonmentBanner({ message, discount, onCheckout, onDismiss }: Props) {
  return (
    <div className="abandon-banner">
      <div className="abandon-content">
        <span className="abandon-icon">🛒</span>
        <div>
          <strong>Cart recovery</strong>
          <p>{message}</p>
          {discount > 0 && (
            <span className="abandon-discount">{discount}% off applied at checkout</span>
          )}
        </div>
      </div>
      <div className="abandon-actions">
        <button className="abandon-checkout" onClick={onCheckout}>Complete Checkout</button>
        <button className="abandon-dismiss" onClick={onDismiss}>Dismiss</button>
      </div>
    </div>
  )
}

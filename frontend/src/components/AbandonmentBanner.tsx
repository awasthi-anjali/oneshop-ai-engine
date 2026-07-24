import './AbandonmentBanner.css'

interface Props {
  message: string
  onCheckout: () => void
  onDismiss: () => void
}

export default function AbandonmentBanner({ message, onCheckout, onDismiss }: Props) {
  return (
    <div className="abandon-banner">
      <div className="abandon-content">
        <span className="abandon-icon">🛒</span>
        <div>
          <strong>Cart recovery</strong>
          <p>{message}</p>
        </div>
      </div>
      <div className="abandon-actions">
        <button className="abandon-checkout" onClick={onCheckout}>Complete Checkout</button>
        <button className="abandon-dismiss" onClick={onDismiss}>Dismiss</button>
      </div>
    </div>
  )
}

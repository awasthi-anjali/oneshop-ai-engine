import type { BundleSuggestion } from '../api'
import './SmartCartPanel.css'

interface Props {
  bundles: BundleSuggestion[]
  nudge: string
  checkoutTip: string
  aiPowered: boolean
  cartCount: number
  subtotal: number
  onCheckout: () => void
  onAddBundle: (productIds: string[]) => void
}

export default function SmartCartPanel({
  bundles,
  nudge,
  checkoutTip,
  aiPowered,
  cartCount,
  subtotal,
  onCheckout,
  onAddBundle,
}: Props) {
  return (
    <div className="smart-cart smart-cart-scroll">
      <div className="smart-cart-header">
        <h3>Smart Cart</h3>
        {aiPowered && <span className="smart-ai">AI</span>}
      </div>

      {nudge && <p className="smart-nudge">{nudge}</p>}
      {checkoutTip && <p className="smart-tip">💡 {checkoutTip}</p>}

      {cartCount === 0 ? (
        <p className="smart-empty">Add items to see bundle deals</p>
      ) : (
        <>
          <div className="cart-summary-row">
            <span>Cart subtotal</span>
            <span className="cart-subtotal">${subtotal.toFixed(0)}</span>
          </div>

          <button className="btn-checkout-main" onClick={onCheckout}>
            Proceed to Checkout →
          </button>

          {bundles.filter((b) => b.savings > 0).map((bundle, i) => (
            <div key={i} className="bundle-card">
              <div className="bundle-header">
                <span className="bundle-name">{bundle.name}</span>
                {bundle.savings > 0 && (
                  <span className="bundle-save">Save ${bundle.savings.toFixed(0)}</span>
                )}
              </div>
              <p className="bundle-reason">{bundle.reason}</p>
              <div className="bundle-products">
                {bundle.products.map((p) => (
                  <span key={p.id} className="bundle-item">{p.name}</span>
                ))}
              </div>
              <div className="bundle-footer">
                <span className="bundle-total">${bundle.total_price.toFixed(0)}</span>
                <button
                  className="btn-add-bundle"
                  onClick={() => onAddBundle(bundle.product_ids)}
                >
                  Add bundle to cart
                </button>
              </div>
            </div>
          ))}
        </>
      )}
    </div>
  )
}

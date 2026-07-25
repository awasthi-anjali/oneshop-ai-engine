import type { BundleSuggestion, CrossSellItem, Product } from '../api'
import './SmartCartPanel.css'

interface Props {
  bundles: BundleSuggestion[]
  crossSell: CrossSellItem[]
  nudge: string
  checkoutTip: string
  aiPowered: boolean
  cartCount: number
  cartItems: Product[]
  oneTimeTotal: number
  monthlyTotal: number
  onCheckout: () => void
  onAddBundle: (productIds: string[]) => void
  onAddCrossSell: (productId: string) => void
  onRemoveFromCart: (productId: string) => void
}

export default function SmartCartPanel({
  bundles,
  crossSell,
  nudge,
  checkoutTip,
  aiPowered,
  cartCount,
  cartItems,
  oneTimeTotal,
  monthlyTotal,
  onCheckout,
  onAddBundle,
  onAddCrossSell,
  onRemoveFromCart,
}: Props) {
  const formatBundleTotal = (bundle: BundleSuggestion) => {
    const allMonthly = bundle.products.length > 0
      && bundle.products.every((product) => product.category === 'plan')
    const mixedCadence = bundle.products.some((product) => product.category === 'plan')
      && !allMonthly
    if (mixedCadence) return 'See item prices'
    return `$${bundle.total_price.toFixed(0)}${allMonthly ? '/mo' : ''}`
  }

  return (
    <div className="smart-cart smart-cart-scroll">
      <div className="smart-cart-header">
        <h3>Your cart {cartCount > 0 && `(${cartCount})`}</h3>
        {aiPowered && <span className="smart-ai">AI validated</span>}
      </div>

      {nudge && <p className="smart-nudge">{nudge}</p>}
      {checkoutTip && <p className="smart-tip">💡 {checkoutTip}</p>}

      {cartCount === 0 ? (
        <p className="smart-empty">Add items to see bundle deals</p>
      ) : (
        <>
          <div className="cart-items-list">
            {cartItems.map((item) => (
              <div key={item.id} className="cart-line-item">
                <div className="cart-line-info">
                  <span className="cart-line-name">{item.name}</span>
                  <span className="cart-line-price">
                    ${item.price.toFixed(0)}{item.category === 'plan' ? '/mo' : ''}
                  </span>
                </div>
                <button
                  type="button"
                  className="cart-line-remove"
                  onClick={() => onRemoveFromCart(item.id)}
                  aria-label={`Remove ${item.name} from cart`}
                >
                  ✕
                </button>
              </div>
            ))}
          </div>

          {crossSell.length > 0 && (
            <details className="cross-sell-section">
              <summary className="cross-sell-heading">
                Optional catalog items ({crossSell.length})
              </summary>
              {crossSell.map((item) => (
                <div key={item.product.id} className="cross-sell-row">
                  <div className="cross-sell-info">
                    <span className="cross-sell-name">{item.product.name}</span>
                    <span className="cross-sell-reason">{item.reason}</span>
                  </div>
                  <div className="cross-sell-actions">
                    <span className="cross-sell-price">${item.product.price.toFixed(0)}</span>
                    <button
                      type="button"
                      className="btn-cross-sell-add"
                      onClick={() => onAddCrossSell(item.product.id)}
                    >
                      Add
                    </button>
                  </div>
                </div>
              ))}
            </details>
          )}

          {bundles.map((bundle, i) => (
            <details key={i} className="bundle-card bundle-card-highlight">
              <summary className="bundle-header">
                <span className="bundle-name">Suggested set: {bundle.name}</span>
                <span className="bundle-save">Catalog items</span>
              </summary>
              <p className="bundle-reason">{bundle.reason}</p>
              <div className="bundle-product-rows">
                {bundle.products.map((p) => (
                  <div key={p.id} className="bundle-product-row">
                    <span>{p.name}</span>
                    <span className="bundle-original-price">
                      ${p.price.toFixed(0)}{p.category === 'plan' ? '/mo' : ''}
                    </span>
                  </div>
                ))}
              </div>
              <div className="bundle-footer">
                <div className="bundle-pricing">
                  <span className="bundle-total">{formatBundleTotal(bundle)}</span>
                  <span className="bundle-savings-label">No discount assumed</span>
                </div>
                <button
                  type="button"
                  className="btn-add-bundle"
                  onClick={() => onAddBundle(bundle.product_ids)}
                >
                  Review & add set
                </button>
              </div>
            </details>
          ))}

          <div className="cart-totals">
            <div className="cart-total-row">
              <span>Cart items ({cartCount})</span>
              <span>Catalog prices</span>
            </div>
            {oneTimeTotal > 0 && (
              <div className="cart-total-row cart-final-row">
                <span>Due once</span>
                <span>${oneTimeTotal.toFixed(2)}</span>
              </div>
            )}
            {monthlyTotal > 0 && (
              <div className="cart-total-row cart-final-row">
                <span>Monthly</span>
                <span>${monthlyTotal.toFixed(2)}/month</span>
              </div>
            )}
          </div>

          <button className="btn-checkout-main" onClick={onCheckout}>
            Start demo checkout
          </button>
        </>
      )}
    </div>
  )
}

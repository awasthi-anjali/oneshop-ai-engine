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
  subtotal: number
  discount: number
  total: number
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
  subtotal,
  discount,
  total,
  onCheckout,
  onAddBundle,
  onAddCrossSell,
  onRemoveFromCart,
}: Props) {
  const activeBundles = bundles.filter((b) => b.savings > 0)

  return (
    <div className="smart-cart smart-cart-scroll">
      <div className="smart-cart-header">
        <h3>Smart Cart {cartCount > 0 && `(${cartCount})`}</h3>
        {aiPowered && <span className="smart-ai">AI</span>}
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
            <div className="cross-sell-section">
              <h4 className="cross-sell-heading">🛍️ Frequently Bought Together</h4>
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
            </div>
          )}

          {activeBundles.map((bundle, i) => (
            <div key={i} className="bundle-card bundle-card-highlight">
              <div className="bundle-header">
                <span className="bundle-name">📦 {bundle.name}</span>
                {bundle.discount_percent ? (
                  <span className="bundle-save">{bundle.discount_percent}% off</span>
                ) : (
                  <span className="bundle-save">Save ${bundle.savings.toFixed(0)}</span>
                )}
              </div>
              <p className="bundle-reason">{bundle.reason}</p>
              <div className="bundle-product-rows">
                {bundle.products.map((p) => (
                  <div key={p.id} className="bundle-product-row">
                    <span>{p.name}</span>
                    <span className="bundle-original-price">${p.price.toFixed(0)}</span>
                  </div>
                ))}
              </div>
              <div className="bundle-footer">
                <div className="bundle-pricing">
                  {bundle.original_price ? (
                    <span className="bundle-was">${bundle.original_price.toFixed(0)}</span>
                  ) : null}
                  <span className="bundle-total">${bundle.total_price.toFixed(0)}</span>
                  <span className="bundle-savings-label">Save ${bundle.savings.toFixed(0)}</span>
                </div>
                <button
                  type="button"
                  className="btn-add-bundle"
                  onClick={() => onAddBundle(bundle.product_ids)}
                >
                  Allow & add bundle
                </button>
              </div>
            </div>
          ))}

          <div className="cart-totals">
            <div className="cart-total-row">
              <span>Subtotal ({cartCount} item{cartCount !== 1 ? 's' : ''})</span>
              <span>${subtotal.toFixed(2)}</span>
            </div>
            {discount > 0 && (
              <div className="cart-total-row cart-discount-row">
                <span>Bundle Discount</span>
                <span>-${discount.toFixed(2)}</span>
              </div>
            )}
            <div className="cart-total-row cart-final-row">
              <span>Total</span>
              <span>${total.toFixed(2)}</span>
            </div>
            {discount > 0 && (
              <p className="cart-saved-msg">💰 You saved ${discount.toFixed(2)}!</p>
            )}
          </div>

          <button className="btn-checkout-main" onClick={onCheckout}>
            Checkout
          </button>
        </>
      )}
    </div>
  )
}

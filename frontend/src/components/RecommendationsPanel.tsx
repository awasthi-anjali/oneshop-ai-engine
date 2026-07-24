import type { MouseEvent } from 'react'
import type { BundleSuggestion, CustomerIntent, RecommendationItem } from '../api'
import SmartCartPanel from './SmartCartPanel'
import './RecommendationsPanel.css'

interface Props {
  intent: CustomerIntent | null
  recommendations: RecommendationItem[]
  wishlistCount: number
  cartCount: number
  viewedCount: number
  loading: boolean
  aiPowered: boolean
  smartCart: {
    bundles: BundleSuggestion[]
    nudge: string
    checkoutTip: string
    aiPowered: boolean
    subtotal: number
  }
  onToggleWishlist: (id: string) => void
  onAddToCart: (id: string) => void
  onRemoveFromCart: (id: string) => void
  onCheckout: () => void
  onAddBundle: (productIds: string[]) => void
  wishlistIds: Set<string>
  cartIds: Set<string>
}

export default function RecommendationsPanel({
  intent,
  recommendations,
  wishlistCount,
  cartCount,
  viewedCount,
  loading,
  aiPowered,
  smartCart,
  onToggleWishlist,
  onAddToCart,
  onRemoveFromCart,
  onCheckout,
  onAddBundle,
  wishlistIds,
  cartIds,
}: Props) {
  const handleRecCartClick = (e: MouseEvent, productId: string, inCart: boolean) => {
    e.stopPropagation()
    if (inCart) onRemoveFromCart(productId)
    else onAddToCart(productId)
  }

  return (
    <aside className="rec-panel">
      <div className="rec-panel-header">
        <h2>For You</h2>
        <div className="rec-header-badges">
          {aiPowered && <span className="rec-ai-badge">AI Powered</span>}
          <p className="rec-subtitle">Personalized Discovery</p>
        </div>
      </div>

      <div className="rec-stats">
        <div className="rec-stat">
          <span className="rec-stat-num">{viewedCount}</span>
          <span className="rec-stat-label">Viewed</span>
        </div>
        <div className="rec-stat">
          <span className="rec-stat-num">{wishlistCount}</span>
          <span className="rec-stat-label">Wishlist</span>
        </div>
        <div className="rec-stat">
          <span className="rec-stat-num">{cartCount}</span>
          <span className="rec-stat-label">Cart</span>
        </div>
      </div>

      {intent && (
        <div className="rec-intent">
          <span className="rec-intent-label">Your intent</span>
          <p>{intent.summary}</p>
          {intent.ecosystem && (
            <p className="rec-ecosystem">🏷 {intent.ecosystem}</p>
          )}
          {intent.tags.length > 0 && (
            <div className="rec-tags">
              {intent.tags.map((tag) => (
                <span key={tag} className="rec-tag">{tag}</span>
              ))}
            </div>
          )}
        </div>
      )}

      <div className="rec-list">
        {loading ? (
          <p className="rec-empty">Updating recommendations…</p>
        ) : recommendations.length === 0 ? (
          <p className="rec-empty">
            Click products to view, ♡ wishlist, or 🛒 add to cart for AI recommendations
          </p>
        ) : (
          recommendations.map(({ product, reason }) => {
            const priceLabel =
              product.category === 'plan'
                ? `$${product.price.toFixed(0)}/mo`
                : `$${product.price.toFixed(0)}`
            const inCart = cartIds.has(product.id)

            return (
              <div key={product.id} className="rec-item">
                <img src={product.image_url} alt={product.name} className="rec-item-img" />
                <div className="rec-item-info">
                  <span className="rec-item-brand">{product.brand}</span>
                  <h4 className="rec-item-name">{product.name}</h4>
                  <span className="rec-item-reason">{reason}</span>
                  <div className="rec-item-footer">
                    <span className="rec-item-price">{priceLabel}</span>
                    <div className="rec-item-actions">
                      <button
                        className={`rec-icon-btn ${wishlistIds.has(product.id) ? 'active' : ''}`}
                        onClick={() => onToggleWishlist(product.id)}
                        title="Wishlist"
                      >
                        {wishlistIds.has(product.id) ? '♥' : '♡'}
                      </button>
                      <button
                        className={`rec-icon-btn cart ${inCart ? 'active' : ''}`}
                        onClick={(e) => handleRecCartClick(e, product.id, inCart)}
                        title={inCart ? 'Click to remove from cart' : 'Add to cart'}
                      >
                        🛒
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            )
          })
        )}
      </div>

      <SmartCartPanel
        bundles={smartCart.bundles}
        nudge={smartCart.nudge}
        checkoutTip={smartCart.checkoutTip}
        aiPowered={smartCart.aiPowered}
        cartCount={cartCount}
        subtotal={smartCart.subtotal}
        onCheckout={onCheckout}
        onAddBundle={onAddBundle}
      />
    </aside>
  )
}

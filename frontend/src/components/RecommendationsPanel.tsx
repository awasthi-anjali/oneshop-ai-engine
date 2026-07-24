import type { MouseEvent } from 'react'
import type { BundleSuggestion, RecommendationItem } from '../api'
import SmartCartPanel from './SmartCartPanel'
import './RecommendationsPanel.css'

interface Props {
  recommendations: RecommendationItem[]
  wishlistCount: number
  cartCount: number
  viewedCount: number
  loading: boolean
  aiPowered: boolean
  recommendationPipeline?: string
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
  recommendations,
  wishlistCount,
  cartCount,
  viewedCount,
  loading,
  aiPowered,
  recommendationPipeline,
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

  const sourceLabel = (source?: string) => {
    if (source === 'ai') return 'AI pick'
    if (source === 'semantic_backup') return 'Semantic match'
    return 'Rule-based'
  }

  return (
    <aside className="rec-panel">
      <div className="rec-panel-header">
        <h2>For You</h2>
        <div className="rec-header-badges">
          {aiPowered && <span className="rec-ai-badge">AI Powered</span>}
          {recommendationPipeline === 'ai_validated' && (
            <span className="rec-pipeline-badge ai">AI validated</span>
          )}
          {recommendationPipeline === 'semantic_backup' && (
            <span className="rec-pipeline-badge semantic">Semantic backup</span>
          )}
          <p className="rec-subtitle">Personalized Discovery</p>
        </div>
      </div>

      <div className="rec-stats">
        <div className="rec-stat rec-stat-compact">
          <span className="rec-stat-num">{viewedCount}</span>
          <span className="rec-stat-label">Viewed</span>
        </div>
        <div className="rec-stat rec-stat-compact">
          <span className="rec-stat-num">{wishlistCount}</span>
          <span className="rec-stat-label">Wishlist</span>
        </div>
        <div className="rec-stat rec-stat-cart">
          <span className="rec-stat-num">{cartCount}</span>
          <span className="rec-stat-label">Cart</span>
        </div>
      </div>

      <div className="rec-panel-body">
        <div className="rec-list">
        {loading ? (
          <p className="rec-empty">Updating recommendations…</p>
        ) : recommendations.length === 0 ? (
          <p className="rec-empty">
            Click products to view, ♡ wishlist, or 🛒 add to cart for AI recommendations
          </p>
        ) : (
          recommendations.map(({ product, reason, source }) => {
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
                  <span className={`rec-item-source ${source || 'rules'}`}>{sourceLabel(source)}</span>
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
                        aria-label={inCart ? 'Remove from cart' : 'Add to cart'}
                      >
                        <span className="rec-cart-icon" aria-hidden="true">🛒</span>
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
      </div>
    </aside>
  )
}

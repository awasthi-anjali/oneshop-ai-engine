import type { Product } from '../api'
import './ProductDetailModal.css'

interface Props {
  product: Product | null
  isWishlisted: boolean
  isInCart: boolean
  onClose: () => void
  onToggleWishlist: (id: string) => void
  onAddToCart: (id: string) => void
  onRemoveFromCart: (id: string) => void
}

export default function ProductDetailModal({
  product,
  isWishlisted,
  isInCart,
  onClose,
  onToggleWishlist,
  onAddToCart,
  onRemoveFromCart,
}: Props) {
  if (!product) return null

  const priceLabel =
    product.category === 'plan' ? `$${product.price.toFixed(0)}/mo` : `$${product.price.toFixed(0)}`

  const handleCartClick = () => {
    if (isInCart) onRemoveFromCart(product.id)
    else onAddToCart(product.id)
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <button className="modal-close" onClick={onClose} aria-label="Close">×</button>

        <div className="modal-grid">
          <div className="modal-image">
            <img src={product.image_url} alt={product.name} />
            <span className="modal-category">{product.category}</span>
          </div>

          <div className="modal-info">
            <span className="modal-brand">{product.brand}</span>
            <h2>{product.name}</h2>
            <p className="modal-desc">{product.description}</p>

            <div className="modal-meta">
              <span className="modal-price">{priceLabel}</span>
              <span className="modal-rating">★ {product.rating}</span>
            </div>

            <ul className="modal-features">
              {product.features.map((f) => (
                <li key={f}>{f}</li>
              ))}
            </ul>

            <div className="modal-specs">
              {Object.entries(product.specs).map(([k, v]) => (
                <div key={k} className="spec-row">
                  <span className="spec-key">{k}</span>
                  <span className="spec-val">{String(v)}</span>
                </div>
              ))}
            </div>

            <div className="modal-actions">
              <button
                className={`modal-wishlist ${isWishlisted ? 'active' : ''}`}
                onClick={() => onToggleWishlist(product.id)}
              >
                {isWishlisted ? '♥ Wishlisted' : '♡ Add to Wishlist'}
              </button>
              <button
                className={`modal-cart ${isInCart ? 'in-cart' : ''}`}
                onClick={handleCartClick}
                disabled={!product.in_stock}
                title={isInCart ? 'Click to remove from cart' : 'Add to cart'}
              >
                {isInCart ? '✓ In Cart · Remove' : 'Add to Cart'}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

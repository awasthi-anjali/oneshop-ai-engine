import type { MouseEvent } from 'react'
import type { Product } from '../api'
import './ProductShopCard.css'

interface Props {
  product: Product
  isWishlisted: boolean
  isInCart: boolean
  onProductClick: (product: Product) => void
  onToggleWishlist: (id: string) => void
  onAddToCart: (id: string) => void
  onRemoveFromCart: (id: string) => void
  reason?: string
  reasonCodes?: string[]
}

export default function ProductShopCard({
  product,
  isWishlisted,
  isInCart,
  onProductClick,
  onToggleWishlist,
  onAddToCart,
  onRemoveFromCart,
  reason,
  reasonCodes = [],
}: Props) {
  const priceLabel =
    product.category === 'plan' ? `$${product.price.toFixed(0)}/mo` : `$${product.price.toFixed(0)}`

  const handleCartClick = (e: MouseEvent) => {
    e.stopPropagation()
    if (isInCart) onRemoveFromCart(product.id)
    else onAddToCart(product.id)
  }

  const handleWishlistClick = (e: MouseEvent) => {
    e.stopPropagation()
    onToggleWishlist(product.id)
  }

  return (
    <article
      className="shop-card"
      data-product-id={product.id}
      onClick={() => onProductClick(product)}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault()
          onProductClick(product)
        }
      }}
      role="button"
      tabIndex={0}
      aria-label={`View details for ${product.name}`}
    >
      <div className="shop-card-image">
        <img src={product.image_url} alt={product.name} loading="lazy" />
        <button
          className={`wishlist-btn ${isWishlisted ? 'active' : ''}`}
          onClick={handleWishlistClick}
          aria-label={isWishlisted ? 'Remove from wishlist' : 'Add to wishlist'}
          title={isWishlisted ? 'Remove from wishlist' : 'Add to wishlist'}
        >
          {isWishlisted ? '♥' : '♡'}
        </button>
        <span className="shop-card-category">{product.category}</span>
      </div>

      <div className="shop-card-body">
        <span className="shop-card-brand">{product.brand}</span>
        <h3 className="shop-card-name">{product.name}</h3>
        <p className="shop-card-desc">{product.description.slice(0, 100)}…</p>

        {reason && <p className="shopassist-reason">{reason}</p>}
        {reasonCodes.length > 0 && (
          <div className="reason-badges" aria-label="Why this matches">
            {reasonCodes.map((code) => (
              <span key={code}>{code.replace(/_/g, ' ').toLowerCase()}</span>
            ))}
          </div>
        )}

        <div className="shop-card-meta">
          <span className="shop-card-price">{priceLabel}</span>
          <span className="shop-card-rating">★ {product.rating}</span>
        </div>

        <div className="shop-card-actions">
          <button
            className={`btn-cart ${isInCart ? 'in-cart' : ''}`}
            onClick={handleCartClick}
            disabled={!product.in_stock}
            title={isInCart ? 'Click to remove from cart' : 'Add to cart'}
          >
            {isInCart ? '✓ In Cart · Remove' : 'Add to Cart'}
          </button>
        </div>
      </div>
    </article>
  )
}

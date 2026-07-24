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
}

export default function ProductShopCard({
  product,
  isWishlisted,
  isInCart,
  onProductClick,
  onToggleWishlist,
  onAddToCart,
  onRemoveFromCart,
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
    <article className="shop-card" onClick={() => onProductClick(product)}>
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

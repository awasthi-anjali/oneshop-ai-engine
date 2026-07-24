import type { Product } from '../api'
import './ProductCard.css'

interface Props {
  product: Product
  compact?: boolean
}

export default function ProductCard({ product, compact }: Props) {
  const priceLabel =
    product.category === 'plan' ? `$${product.price.toFixed(0)}/mo` : `$${product.price.toFixed(0)}`

  return (
    <div className={`product-card ${compact ? 'compact' : ''}`}>
      <div className="product-image">
        <img src={product.image_url} alt={product.name} loading="lazy" />
        {!product.in_stock && <span className="out-of-stock">Out of stock</span>}
      </div>
      <div className="product-info">
        <span className="product-brand">{product.brand}</span>
        <h4 className="product-name">{product.name}</h4>
        {!compact && <p className="product-desc">{product.description.slice(0, 90)}…</p>}
        <div className="product-meta">
          <span className="product-price">{priceLabel}</span>
          <span className="product-rating">★ {product.rating}</span>
        </div>
        {!compact && product.features.length > 0 && (
          <ul className="product-features">
            {product.features.slice(0, 3).map((f) => (
              <li key={f}>{f}</li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}

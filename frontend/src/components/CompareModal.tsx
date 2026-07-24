import type { Product } from '../api'
import ComparisonTable from './ComparisonTable'
import './CompareModal.css'

interface Props {
  open: boolean
  products: Product[]
  loading?: boolean
  onClose: () => void
}

export default function CompareModal({ open, products, loading = false, onClose }: Props) {
  if (!open) return null

  return (
    <div className="compare-modal-backdrop" onClick={onClose} role="presentation">
      <div
        className="compare-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="compare-modal-title"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="compare-modal-header">
          <h3 id="compare-modal-title">Compare Products</h3>
          <button type="button" className="compare-modal-close" onClick={onClose} aria-label="Close">
            ×
          </button>
        </div>
        <div className="compare-modal-body">
          {loading ? (
            <p className="compare-modal-loading">Loading comparison…</p>
          ) : (
            <ComparisonTable products={products} />
          )}
        </div>
      </div>
    </div>
  )
}

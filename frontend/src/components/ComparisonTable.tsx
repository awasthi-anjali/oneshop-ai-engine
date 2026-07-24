import type { Product } from '../api'
import './ComparisonTable.css'

interface Props {
  products: Product[]
}

export default function ComparisonTable({ products }: Props) {
  if (products.length < 2) return null

  const rows: { label: string; values: string[] }[] = [
    {
      label: 'Price',
      values: products.map((p) =>
        p.category === 'plan' ? `$${p.price}/mo` : `$${p.price}`
      ),
    },
    { label: 'Brand', values: products.map((p) => p.brand) },
    { label: 'Rating', values: products.map((p) => `${p.rating}/5`) },
    { label: 'Category', values: products.map((p) => p.category) },
    {
      label: 'Top Feature',
      values: products.map((p) => p.features[0] || '—'),
    },
  ]

  return (
    <div className="comparison-table-wrap">
      <h4 className="comparison-title">Product Comparison</h4>
      <div className="comparison-table-scroll">
        <table className="comparison-table">
          <thead>
            <tr>
              <th>Feature</th>
              {products.map((p) => (
                <th key={p.id}>{p.name}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.label}>
                <td className="row-label">{row.label}</td>
                {row.values.map((val, i) => (
                  <td key={i}>{val}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

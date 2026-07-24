import { describe, expect, it } from 'vitest'
import type { Product } from '../api'
import { filterProductsForSearch } from './catalogFilters'

const products: Product[] = [
  {
    id: 'iphone-15-pro',
    name: 'iPhone 15 Pro',
    category: 'phone',
    brand: 'Apple',
    price: 999,
    description: 'Premium iOS phone',
    features: ['A17 Pro chip'],
    specs: {},
    image_url: '',
    rating: 4.8,
    in_stock: true,
    tags: ['ios', 'premium'],
    currency: 'USD',
    billing_period: 'one_time',
  },
  {
    id: 'iphone-se',
    name: 'iPhone SE (3rd Gen)',
    category: 'phone',
    brand: 'Apple',
    price: 429,
    description: 'Affordable compact iPhone',
    features: ['A15 Bionic'],
    specs: {},
    image_url: '',
    rating: 4.2,
    in_stock: true,
    tags: ['ios', 'budget'],
    currency: 'USD',
    billing_period: 'one_time',
  },
  {
    id: 'google-pixel-8',
    name: 'Google Pixel 8',
    category: 'phone',
    brand: 'Google',
    price: 699,
    description: 'Android camera phone',
    features: ['Tensor G3'],
    specs: {},
    image_url: '',
    rating: 4.6,
    in_stock: true,
    tags: ['android', 'camera'],
    currency: 'USD',
    billing_period: 'one_time',
  },
]

describe('filterProductsForSearch', () => {
  it('keeps only literal catalog matches for a name search response', () => {
    expect(filterProductsForSearch(products, 'iphone', 'name').map((product) => product.id))
      .toEqual(['iphone-15-pro', 'iphone-se'])
  })

  it('does not discard trusted semantic results that need not contain the query text', () => {
    expect(filterProductsForSearch(products, 'best travel device', 'embeddings'))
      .toEqual(products)
  })

  it('leaves the catalog unchanged when the query is blank', () => {
    expect(filterProductsForSearch(products, '  ', 'name')).toEqual(products)
  })
})

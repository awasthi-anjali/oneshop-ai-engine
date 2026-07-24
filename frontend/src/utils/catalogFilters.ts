import type { Product, ProductSearchMethod } from '../api'

export type SortOption = 'relevance' | 'price_asc' | 'price_desc' | 'rating'
export type PriceRange = 'all' | 'under_500' | '500_1000' | 'over_1000'

export function priceRangeToParams(range: PriceRange): { min_price?: number; max_price?: number } {
  switch (range) {
    case 'under_500':
      return { max_price: 500 }
    case '500_1000':
      return { min_price: 500, max_price: 1000 }
    case 'over_1000':
      return { min_price: 1000 }
    default:
      return {}
  }
}

export function sortProducts(products: Product[], sort: SortOption): Product[] {
  const copy = [...products]
  switch (sort) {
    case 'price_asc':
      return copy.sort((a, b) => a.price - b.price)
    case 'price_desc':
      return copy.sort((a, b) => b.price - a.price)
    case 'rating':
      return copy.sort((a, b) => b.rating - a.rating)
    default:
      return copy
  }
}

export function nameMatchesQuery(product: Product, query: string): boolean {
  const normalized = query.trim().toLowerCase()
  if (!normalized) return true

  const tokens = normalized.split(/\s+/).filter(Boolean)
  const haystack = [
    product.name,
    product.brand,
    product.description,
    product.category,
    ...product.tags,
    ...product.features,
  ]
    .join(' ')
    .toLowerCase()

  return tokens.every((token) => haystack.includes(token))
}

export function filterProductsForSearch(
  products: Product[],
  query: string,
  searchMethod: ProductSearchMethod,
): Product[] {
  if (!query.trim() || searchMethod !== 'name') return products
  return products.filter((product) => nameMatchesQuery(product, query))
}

export function filterSuggestions(names: string[], query: string, limit = 6): string[] {
  const normalized = query.trim().toLowerCase()
  if (!normalized) return []

  const startsWith: string[] = []
  const includes: string[] = []

  for (const name of names) {
    const lower = name.toLowerCase()
    if (lower.startsWith(normalized)) startsWith.push(name)
    else if (lower.includes(normalized)) includes.push(name)
  }

  return [...startsWith, ...includes].slice(0, limit)
}

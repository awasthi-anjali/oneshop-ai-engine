import { useEffect, useRef, useState, type ReactNode } from 'react'
import type { PriceRange, SortOption } from '../utils/catalogFilters'
import './CatalogFilters.css'

interface Props {
  sortBy: SortOption
  onSortChange: (value: SortOption) => void
  priceRange: PriceRange
  onPriceRangeChange: (value: PriceRange) => void
  brands: string[]
  brandFilter: string
  onBrandChange: (value: string) => void
}

const SORT_OPTIONS: { value: SortOption; label: string }[] = [
  { value: 'relevance', label: 'Relevance' },
  { value: 'price_asc', label: 'Price: Low → High' },
  { value: 'price_desc', label: 'Price: High → Low' },
  { value: 'rating', label: 'Rating' },
]

const PRICE_OPTIONS: { value: PriceRange; label: string }[] = [
  { value: 'all', label: 'Any price' },
  { value: 'under_500', label: 'Under $500' },
  { value: '500_1000', label: '$500 – $1000' },
  { value: 'over_1000', label: 'Over $1000' },
]

function FilterDropdown({
  id,
  label,
  active,
  children,
}: {
  id: string
  label: string
  active?: boolean
  children: ReactNode
}) {
  const [open, setOpen] = useState(false)
  const wrapRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const handleClick = (event: MouseEvent) => {
      if (!wrapRef.current?.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

  return (
    <div className="catalog-filter-dropdown" ref={wrapRef}>
      <button
        type="button"
        id={`${id}-trigger`}
        className={`catalog-filter-btn ${open ? 'open' : ''} ${active ? 'active' : ''}`}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={`${id}-menu`}
        onClick={() => setOpen((current) => !current)}
      >
        <span>{label}</span>
        <span className="catalog-filter-chevron" aria-hidden="true">
          ▾
        </span>
      </button>
      {open && (
        <div
          id={`${id}-menu`}
          className="catalog-filter-menu"
          role="listbox"
          aria-labelledby={`${id}-trigger`}
          onClick={(event) => {
            if ((event.target as HTMLElement).closest('.catalog-filter-option')) {
              setOpen(false)
            }
          }}
        >
          {children}
        </div>
      )}
    </div>
  )
}

function MenuOption({
  selected,
  onClick,
  children,
}: {
  selected: boolean
  onClick: () => void
  children: ReactNode
}) {
  return (
    <button
      type="button"
      role="option"
      aria-selected={selected}
      className={`catalog-filter-option ${selected ? 'selected' : ''}`}
      onClick={onClick}
    >
      {selected && <span aria-hidden="true">✓</span>}
      {children}
    </button>
  )
}

export default function CatalogFilters({
  sortBy,
  onSortChange,
  priceRange,
  onPriceRangeChange,
  brands,
  brandFilter,
  onBrandChange,
}: Props) {
  const sortLabel = SORT_OPTIONS.find((option) => option.value === sortBy)?.label ?? 'Sort'
  const priceLabel = PRICE_OPTIONS.find((option) => option.value === priceRange)?.label ?? 'Price'
  const sortButtonLabel = sortBy === 'relevance' ? 'Sort' : sortLabel
  const priceButtonLabel = priceRange === 'all' ? 'Price' : priceLabel
  const brandButtonLabel = brandFilter === 'all' ? 'Brand' : brandFilter

  return (
    <div className="catalog-filters-inline">
      <FilterDropdown id="catalog-sort" label={sortButtonLabel} active={sortBy !== 'relevance'}>
        {SORT_OPTIONS.map((option) => (
          <MenuOption
            key={option.value}
            selected={sortBy === option.value}
            onClick={() => onSortChange(option.value)}
          >
            {option.label}
          </MenuOption>
        ))}
      </FilterDropdown>

      <FilterDropdown id="catalog-price" label={priceButtonLabel} active={priceRange !== 'all'}>
        {PRICE_OPTIONS.map((option) => (
          <MenuOption
            key={option.value}
            selected={priceRange === option.value}
            onClick={() => onPriceRangeChange(option.value)}
          >
            {option.label}
          </MenuOption>
        ))}
      </FilterDropdown>

      {brands.length > 0 && (
        <FilterDropdown id="catalog-brand" label={brandButtonLabel} active={brandFilter !== 'all'}>
          <MenuOption selected={brandFilter === 'all'} onClick={() => onBrandChange('all')}>
            All brands
          </MenuOption>
          {brands.map((brand) => (
            <MenuOption key={brand} selected={brandFilter === brand} onClick={() => onBrandChange(brand)}>
              {brand}
            </MenuOption>
          ))}
        </FilterDropdown>
      )}
    </div>
  )
}

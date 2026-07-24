import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react'
import { filterSuggestions } from '../utils/catalogFilters'
import { getRecentSearches } from '../utils/recentSearches'
import './ProductSearchBar.css'

interface Props {
  value: string
  onChange: (value: string) => void
  onSubmit?: (value: string) => void
  loading?: boolean
  productNames?: string[]
  placeholder?: string
}

export default function ProductSearchBar({
  value,
  onChange,
  onSubmit,
  loading = false,
  productNames = [],
  placeholder = 'Search by product name…',
}: Props) {
  const [open, setOpen] = useState(false)
  const [recentSearches, setRecentSearches] = useState<string[]>(() => getRecentSearches())
  const wrapRef = useRef<HTMLDivElement>(null)

  const suggestions = useMemo(
    () => filterSuggestions(productNames, value),
    [productNames, value]
  )

  const showPanel = open && (suggestions.length > 0 || (!value.trim() && recentSearches.length > 0))

  useEffect(() => {
    setRecentSearches(getRecentSearches())
  }, [value])

  useEffect(() => {
    const handleClick = (event: MouseEvent) => {
      if (!wrapRef.current?.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

  const pickSuggestion = (next: string) => {
    onChange(next)
    onSubmit?.(next)
    setOpen(false)
  }

  const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Enter') {
      event.preventDefault()
      onSubmit?.(value)
      setOpen(false)
    }
    if (event.key === 'Escape') setOpen(false)
  }

  return (
    <div className="product-search-wrap" ref={wrapRef}>
      <div className="product-search-bar" role="search">
        <span className="product-search-icon" aria-hidden="true">
          ⌕
        </span>
        <input
          id="product-search"
          type="search"
          className="product-search-input"
          value={value}
          onChange={(event) => onChange(event.target.value)}
          onFocus={() => setOpen(true)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          autoComplete="off"
          enterKeyHint="search"
          aria-label="Search products"
          aria-busy={loading}
          aria-expanded={showPanel}
          aria-controls="product-search-suggestions"
        />
        {value && !loading && (
          <button
            type="button"
            className="product-search-clear"
            onClick={() => onChange('')}
            aria-label="Clear search"
          >
            ×
          </button>
        )}
        {loading && <span className="product-search-spinner" aria-hidden="true" />}
      </div>

      {showPanel && (
        <div id="product-search-suggestions" className="product-search-panel" role="listbox">
          {!value.trim() && recentSearches.length > 0 && (
            <div className="product-search-section">
              <p className="product-search-section-title">Recent searches</p>
              {recentSearches.map((item) => (
                <button
                  key={item}
                  type="button"
                  className="product-search-option"
                  onClick={() => pickSuggestion(item)}
                >
                  <span aria-hidden="true">↺</span>
                  {item}
                </button>
              ))}
            </div>
          )}
          {value.trim() && suggestions.length > 0 && (
            <div className="product-search-section">
              <p className="product-search-section-title">Suggestions</p>
              {suggestions.map((item) => (
                <button
                  key={item}
                  type="button"
                  className="product-search-option"
                  onClick={() => pickSuggestion(item)}
                >
                  {item}
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

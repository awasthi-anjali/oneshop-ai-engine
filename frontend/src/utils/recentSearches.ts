const STORAGE_KEY = 'oneshop_recent_searches'
const MAX_RECENT = 5

export function getRecentSearches(): string[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed.filter((item) => typeof item === 'string') : []
  } catch {
    return []
  }
}

export function addRecentSearch(query: string): string[] {
  const trimmed = query.trim()
  if (!trimmed) return getRecentSearches()

  const next = [trimmed, ...getRecentSearches().filter((item) => item.toLowerCase() !== trimmed.toLowerCase())]
    .slice(0, MAX_RECENT)

  localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
  return next
}

export function clearRecentSearches(): void {
  localStorage.removeItem(STORAGE_KEY)
}

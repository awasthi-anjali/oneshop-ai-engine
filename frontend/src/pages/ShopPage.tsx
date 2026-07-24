import { useCallback, useEffect, useRef, useState, type MouseEvent } from 'react'
import {
  addBundleToCart,
  addToCart,
  compareProducts,
  dismissAbandonment,
  fetchProducts,
  fetchProductsWithMeta,
  getIntelligenceProfile,
  getSession,
  getStoredSessionId,
  ensureSessionId,
  removeFromCart,
  sendMessage,
  toggleWishlist,
  trackProductView,
  type AbandonmentStatus,
  type BundleSuggestion,
  type ChatAction,
  type ChatMessage,
  type ChatStatus,
  type CheckoutResponse,
  type NextBestAction,
  type PageContext,
  type Product,
  type ProductSearchMethod,
  type RecommendationItem,
  type Channel,
  type ShoppingNeed,
  type ShopAssistRecommendation,
} from '../api'
import AbandonmentBanner from '../components/AbandonmentBanner'
import CatalogFilters from '../components/CatalogFilters'
import CheckoutModal from '../components/CheckoutModal'
import CompareModal from '../components/CompareModal'
import NextBestActionBanner from '../components/NextBestActionBanner'
import OmnichannelSyncBanner from '../components/OmnichannelSyncBanner'
import ProductDetailModal from '../components/ProductDetailModal'
import ProductSearchBar from '../components/ProductSearchBar'
import ProductShopCard from '../components/ProductShopCard'
import RecommendationsPanel from '../components/RecommendationsPanel'
import ShopAssistDrawer from '../components/ShopAssistDrawer'
import ShopAssistFab from '../components/ShopAssistFab'
import { useCartAbandonmentTracking } from '../hooks/useCartAbandonment'
import { useCrossTabSync } from '../hooks/useCrossTabSync'
import {
  nameMatchesQuery,
  priceRangeToParams,
  sortProducts,
  type PriceRange,
  type SortOption,
} from '../utils/catalogFilters'
import { addRecentSearch } from '../utils/recentSearches'
import './ShopPage.css'

interface Props {
  channel?: Channel
  layout?: 'desktop' | 'mobile'
  onAskAssistant?: (message: string) => void
  openCheckout?: boolean
  onCheckoutOpened?: () => void
  refreshKey?: number
}

const EMPTY_NEED: ShoppingNeed = {
  categories: [],
  use_cases: [],
  must_haves: [],
  nice_to_haves: [],
}

export default function ShopPage({
  channel = 'oneshop',
  layout = 'desktop',
  openCheckout,
  onCheckoutOpened,
  refreshKey = 0,
}: Props) {
  const [products, setProducts] = useState<Product[]>([])
  const [sessionId, setSessionId] = useState<string | null>(() => ensureSessionId())
  const [wishlistIds, setWishlistIds] = useState<Set<string>>(new Set())
  const [cartIds, setCartIds] = useState<Set<string>>(new Set())
  const [viewedIds, setViewedIds] = useState<Set<string>>(new Set())
  const [cartProducts, setCartProducts] = useState<Product[]>([])
  const [recommendations, setRecommendations] = useState<RecommendationItem[]>([])
  const [aiPowered, setAiPowered] = useState(false)
  const [nbaActions, setNbaActions] = useState<NextBestAction[]>([])
  const [nbaStage, setNbaStage] = useState('new')
  const [nbaAi, setNbaAi] = useState(false)
  const [smartCart, setSmartCart] = useState<{
    bundles: BundleSuggestion[]
    nudge: string
    checkoutTip: string
    aiPowered: boolean
    subtotal: number
    estimatedSavings: number
  }>({ bundles: [], nudge: '', checkoutTip: '', aiPowered: false, subtotal: 0, estimatedSavings: 0 })
  const [abandonment, setAbandonment] = useState<AbandonmentStatus | null>(null)
  const [syncMessage, setSyncMessage] = useState('')
  const [channelsUsed, setChannelsUsed] = useState<string[]>([])
  const [showCheckout, setShowCheckout] = useState(false)
  const [selectedProduct, setSelectedProduct] = useState<Product | null>(null)
  const [loading, setLoading] = useState(true)
  const [recLoading, setRecLoading] = useState(false)
  const [filter, setFilter] = useState('all')
  const [searchQuery, setSearchQuery] = useState('')
  const [searchLoading, setSearchLoading] = useState(false)
  const [searchMethod, setSearchMethod] = useState<ProductSearchMethod>('name')
  const [sortBy, setSortBy] = useState<SortOption>('relevance')
  const [priceRange, setPriceRange] = useState<PriceRange>('all')
  const [brandFilter, setBrandFilter] = useState('all')
  const [catalogBrands, setCatalogBrands] = useState<string[]>([])
  const [productNames, setProductNames] = useState<string[]>([])
  const [compareIds, setCompareIds] = useState<Set<string>>(new Set())
  const [compareOpen, setCompareOpen] = useState(false)
  const [compareResults, setCompareResults] = useState<Product[]>([])
  const [compareLoading, setCompareLoading] = useState(false)
  const [recommendationPipeline, setRecommendationPipeline] = useState('rules')

  const [drawerOpen, setDrawerOpen] = useState(false)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [draft, setDraft] = useState('')
  const [need, setNeed] = useState<ShoppingNeed>(EMPTY_NEED)
  const [assistRecommendations, setAssistRecommendations] = useState<ShopAssistRecommendation[]>([])
  const [comparison, setComparison] = useState<Product[]>([])
  const [assistActions, setAssistActions] = useState<ChatAction[]>([])
  const [assistStatus, setAssistStatus] = useState<ChatStatus | null>(null)
  const [assistMode, setAssistMode] = useState<'ai' | 'fallback' | null>(null)
  const [assistContext, setAssistContext] = useState<PageContext | null>(null)
  const [assistLoading, setAssistLoading] = useState(false)
  const [assistError, setAssistError] = useState<string | null>(null)
  const [catalogMode, setCatalogMode] = useState<'all' | 'picks'>('all')
  const [confirming, setConfirming] = useState(false)
  const [confirmed, setConfirmed] = useState(false)
  const lastSent = useRef('')
  const launcherRef = useRef<HTMLElement | null>(null)
  const confirmationInFlight = useRef(false)

  useCartAbandonmentTracking(cartIds.size, sessionId)

  const applySession = useCallback((session: {
    session_id: string
    wishlist_ids: string[]
    cart_ids: string[]
    viewed_ids: string[]
    cart?: Product[]
  }) => {
    setSessionId(session.session_id)
    setWishlistIds(new Set(session.wishlist_ids))
    setCartIds(new Set(session.cart_ids))
    setViewedIds(new Set(session.viewed_ids))
    if (session.cart) setCartProducts(session.cart)
  }, [])

  const refreshIntelligence = useCallback(async (sid: string | null) => {
    setRecLoading(true)
    try {
      const profile = await getIntelligenceProfile(sid, channel)
      setSessionId(profile.session_id)
      setRecommendations(profile.recommendations)
      setAiPowered(profile.ai_powered)
      setNbaActions(profile.next_actions)
      setNbaStage(profile.funnel_stage)
      setNbaAi(profile.ai_powered)
      setCartProducts(profile.cart)
      setCartIds(new Set(profile.cart.map((p) => p.id)))
      setRecommendationPipeline(profile.recommendation_pipeline || 'rules')
      setSmartCart({
        bundles: profile.bundles,
        nudge: profile.nudge,
        checkoutTip: profile.checkout_tip,
        aiPowered: profile.ai_powered,
        subtotal: profile.subtotal,
        estimatedSavings: profile.estimated_savings,
      })
      if (profile.abandonment?.is_abandoned) setAbandonment(profile.abandonment)
      setSyncMessage(profile.sync_message ?? '')
      setChannelsUsed(profile.channels_used ?? [])
    } finally {
      setRecLoading(false)
    }
  }, [channel])

  const reloadFromServer = useCallback(async () => {
    const sid = getStoredSessionId() || ensureSessionId()
    const session = await getSession(sid)
    applySession({ ...session, cart: session.cart })
    await refreshIntelligence(session.session_id)
  }, [applySession, refreshIntelligence])

  const loadProducts = useCallback(
    async (query: string, category: string, brand: string, price: PriceRange) => {
      const { min_price, max_price } = priceRangeToParams(price)
      return fetchProductsWithMeta({
        query: query.trim() || undefined,
        category: category !== 'all' ? category : undefined,
        brand: brand !== 'all' ? brand : undefined,
        min_price,
        max_price,
        limit: 50,
      })
    },
    []
  )

  useCrossTabSync(reloadFromServer)

  useEffect(() => {
    if (openCheckout) {
      setShowCheckout(true)
      onCheckoutOpened?.()
    }
  }, [openCheckout, onCheckoutOpened])

  useEffect(() => {
    if (refreshKey > 0) {
      getSession(sessionId).then((session) => {
        applySession({ ...session, cart: session.cart })
        return refreshIntelligence(session.session_id)
      })
    }
  }, [refreshKey, sessionId, refreshIntelligence])

  useEffect(() => {
    async function init() {
      try {
        const [catalog, session] = await Promise.all([
          fetchProducts({ limit: 50 }),
          getSession(sessionId),
        ])
        setCatalogBrands([...new Set(catalog.map((product) => product.brand))].sort())
        setProductNames(catalog.map((product) => product.name))

        const result = await loadProducts(searchQuery, filter, brandFilter, priceRange)
        setProducts(result.products)
        setSearchMethod(result.search_method)
        applySession({ ...session, cart: session.cart })
        await refreshIntelligence(session.session_id)
      } finally {
        setLoading(false)
      }
    }
    init()
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (loading) return

    let cancelled = false
    const delay = searchQuery.trim() ? 300 : 0

    const timer = window.setTimeout(async () => {
      setSearchLoading(true)
      try {
        const result = await loadProducts(searchQuery, filter, brandFilter, priceRange)
        if (!cancelled) {
          setProducts(result.products)
          setSearchMethod(result.search_method)
        }
      } finally {
        if (!cancelled) setSearchLoading(false)
      }
    }, delay)

    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [searchQuery, filter, brandFilter, priceRange, loading, loadProducts])

  const handleSearchChange = (value: string) => {
    setSearchQuery(value)
    if (value.trim()) setCatalogMode('all')
  }

  const handleSearchSubmit = (value: string) => {
    const trimmed = value.trim()
    if (trimmed) addRecentSearch(trimmed)
  }

  const handleToggleCompare = (productId: string) => {
    setCompareIds((current) => {
      const next = new Set(current)
      if (next.has(productId)) next.delete(productId)
      else if (next.size < 3) next.add(productId)
      return next
    })
  }

  const handleOpenCompare = async () => {
    const ids = [...compareIds]
    if (ids.length < 2) return
    setCompareOpen(true)
    setCompareLoading(true)
    try {
      setCompareResults(await compareProducts(ids))
    } catch {
      setCompareResults(products.filter((product) => compareIds.has(product.id)))
    } finally {
      setCompareLoading(false)
    }
  }

  const handleProductClick = async (product: Product) => {
    setSelectedProduct(product)
    const session = await trackProductView(product.id, sessionId, channel)
    applySession({ ...session, cart: session.cart })
    await refreshIntelligence(session.session_id)
  }

  const handleToggleWishlist = async (productId: string) => {
    const session = await toggleWishlist(productId, sessionId, channel)
    applySession({ ...session, cart: session.cart })
    await refreshIntelligence(session.session_id)
  }

  const handleAddToCart = async (productId: string) => {
    const session = await addToCart(productId, sessionId, channel)
    applySession({ ...session, cart: session.cart })
    await refreshIntelligence(session.session_id)
  }

  const handleRemoveFromCart = async (productId: string) => {
    const session = await removeFromCart(productId, sessionId, channel)
    applySession({ ...session, cart: session.cart })
    await refreshIntelligence(session.session_id)
  }

  const handleAddBundle = async (productIds: string[]) => {
    const session = await addBundleToCart(productIds, sessionId, channel)
    applySession({ ...session, cart: session.cart })
    await refreshIntelligence(session.session_id)
  }

  const handleCheckoutSuccess = async (_order: CheckoutResponse) => {
    setAbandonment(null)
    const session = await getSession(sessionId)
    applySession({ ...session, cart: session.cart })
    await refreshIntelligence(session.session_id)
  }

  const handleDismissAbandonment = async () => {
    await dismissAbandonment(sessionId)
    setAbandonment(null)
  }

  const openAssistant = (
    context: PageContext,
    source?: HTMLElement | null,
    editableDraft?: string
  ) => {
    launcherRef.current = source ?? (document.activeElement as HTMLElement | null)
    setAssistContext(context)
    if (editableDraft !== undefined) setDraft(editableDraft)
    setDrawerOpen(true)
  }

  const closeAssistant = useCallback(() => {
    setDrawerOpen(false)
    window.requestAnimationFrame(() => launcherRef.current?.focus())
  }, [])

  const handleNbaClick = (label: string, event?: MouseEvent<HTMLButtonElement>) => {
    if (label.toLowerCase().includes('checkout')) {
      setShowCheckout(true)
      return
    }
    openAssistant(
      {
        surface: 'catalog',
        entry_point: 'next_best_action',
        visible_product_ids: products.slice(0, 20).map((product) => product.id),
      },
      event?.currentTarget,
      label
    )
  }

  const handleSend = useCallback(async (message?: string) => {
    const text = (message ?? draft).trim()
    if (!text || assistLoading) return

    lastSent.current = text
    setDraft('')
    setAssistError(null)
    setConfirmed(false)
    setMessages((current) => [...current, { role: 'user', content: text }])
    setAssistLoading(true)

    try {
      const response = await sendMessage(
        text,
        sessionId,
        assistContext ?? {
          surface: 'catalog',
          entry_point: 'help_me_choose',
          visible_product_ids: products.slice(0, 20).map((product) => product.id),
        },
        channel
      )
      setSessionId(response.session_id)
      setNeed(response.need_profile)
      setAssistRecommendations(response.recommendations.slice(0, 3))
      setAssistActions(response.actions)
      setAssistStatus(response.status)
      setAssistMode(response.mode)
      const comparisonProducts = Array.isArray(response.comparison)
        ? response.comparison
        : response.comparison?.products ?? []
      setComparison(comparisonProducts.slice(0, 2))
      setMessages((current) => [
        ...current,
        {
          role: 'assistant',
          content: response.message,
          status: response.status,
          mode: response.mode,
        },
      ])
      if (response.recommendations.length > 0) setCatalogMode('picks')
    } catch (error) {
      const message = error instanceof Error ? error.message : 'ShopAssist could not respond.'
      setAssistError(message.replace(/port\s*8000/gi, 'service'))
    } finally {
      setAssistLoading(false)
    }
  }, [assistContext, assistLoading, channel, draft, products, sessionId])

  const handleRemoveNeed = (key: keyof ShoppingNeed, value?: string) => {
    setNeed((current) => {
      const next = { ...current }
      const currentValue = current[key]
      if (Array.isArray(currentValue)) {
        ;(next[key] as string[]) = currentValue.filter((item) => item !== value)
      } else {
        ;(next[key] as undefined) = undefined
      }
      return next
    })
    setDraft(`Please remove ${value ?? key.replace(/_/g, ' ')} from my preferences.`)
  }

  const handleAssistAction = (action: ChatAction) => {
    if (action.type === 'COMPARE') {
      const choices = action.product_ids
        .map((id) => assistRecommendations.find((item) => item.product.id === id)?.product)
        .filter((product): product is Product => Boolean(product))
        .filter((product) => product.category !== 'plan')
        .slice(0, 2)
      if (choices.length === 2) setComparison(choices)
      return
    }
    if (action.type === 'OPEN_PRODUCT') {
      const product = products.find((item) => item.id === action.product_ids[0])
      if (product) setSelectedProduct(product)
      return
    }
    if (action.type === 'REFINE') setDraft(action.label)
  }

  const handleConfirmBundle = async (productIds: string[]) => {
    if (confirmationInFlight.current || confirming || confirmed || productIds.length === 0) return
    const validIds = new Set(assistRecommendations.map((item) => item.product.id))
    if (!productIds.every((id) => validIds.has(id))) {
      setAssistError('This proposal is no longer valid. Please ask ShopAssist to refresh it.')
      return
    }
    confirmationInFlight.current = true
    setConfirming(true)
    setAssistError(null)
    try {
      await handleAddBundle(productIds)
      setConfirmed(true)
    } catch {
      setAssistError('The cart could not be updated. Nothing was added; please try again.')
    } finally {
      confirmationInFlight.current = false
      setConfirming(false)
    }
  }

  const categories = ['all', ...Array.from(new Set(products.map((product) => product.category)))]
  const normalizedQuery = searchQuery.trim().toLowerCase()
  const categoryFiltered =
    filter === 'all' ? products : products.filter((product) => product.category === filter)
  const allFiltered = sortProducts(
    normalizedQuery ? categoryFiltered : categoryFiltered.filter((product) => nameMatchesQuery(product, searchQuery)),
    sortBy
  )
  const filteredPickItems = assistRecommendations.filter(
    (item) =>
      (filter === 'all' ? true : item.product.category === filter) &&
      nameMatchesQuery(item.product, searchQuery)
  )
  const sortedPickItems = sortProducts(
    filteredPickItems.map((item) => item.product),
    sortBy
  )
    .map((product) => filteredPickItems.find((item) => item.product.id === product.id)!)
    .filter(Boolean)
  const showEmptySearch = catalogMode === 'all' && !searchLoading && normalizedQuery && allFiltered.length === 0
  const hasSearchResults = catalogMode === 'all' && !searchLoading && normalizedQuery && allFiltered.length > 0
  const showCompareMode = catalogMode === 'all'

  if (loading) return <div className="shop-loading">Loading OneShop…</div>

  return (
    <>
      <div className={`shop-layout ${layout}`}>
        <section className="shop-main">
          {abandonment?.is_abandoned && (
            <AbandonmentBanner
              message={abandonment.recovery_message}
              discount={abandonment.discount_offer}
              onCheckout={() => setShowCheckout(true)}
              onDismiss={handleDismissAbandonment}
            />
          )}

          <OmnichannelSyncBanner
            message={syncMessage}
            channelsUsed={channelsUsed}
            currentChannel={channel}
          />

          <NextBestActionBanner
            actions={nbaActions}
            aiPowered={nbaAi}
            funnelStage={nbaStage}
            onActionClick={handleNbaClick}
          />

          <div className="catalog-heading">
            <div>
              <h2>{catalogMode === 'picks' ? 'ShopAssist Picks' : 'All Products'}</h2>
              <p>Catalog information is synthetic demo data.</p>
            </div>
            <div className="catalog-entry-actions">
              {cartIds.size > 0 && (
                <button
                  className="cart-assist-btn"
                  onClick={(event) =>
                    openAssistant(
                      {
                        surface: 'cart',
                        entry_point: 'cart',
                        visible_product_ids: cartProducts.slice(0, 20).map((product) => product.id),
                      },
                      event.currentTarget,
                      'Help me choose a compatible phone and plan for my cart.'
                    )
                  }
                >
                  Ask about cart
                </button>
              )}
              <button
                className="help-choose-btn"
                onClick={(event) =>
                  openAssistant(
                    assistContext ?? {
                      surface: 'catalog',
                      entry_point: 'help_me_choose',
                      visible_product_ids: products.slice(0, 20).map((product) => product.id),
                    },
                    event.currentTarget
                  )
                }
              >
                Help me choose
              </button>
            </div>
          </div>

          <div className="shop-toolbar">
            <div className="shop-search-row">
              <ProductSearchBar
                value={searchQuery}
                onChange={handleSearchChange}
                onSubmit={handleSearchSubmit}
                loading={searchLoading}
                productNames={productNames}
              />
              <CatalogFilters
                sortBy={sortBy}
                onSortChange={setSortBy}
                priceRange={priceRange}
                onPriceRangeChange={setPriceRange}
                brands={catalogBrands}
                brandFilter={brandFilter}
                onBrandChange={setBrandFilter}
              />
              {searchMethod === 'embeddings' && normalizedQuery && (
                <span className="semantic-search-badge" title="Results ranked with AI embeddings">
                  ✦ AI matched
                </span>
              )}
            </div>
            {normalizedQuery && !searchLoading && catalogMode === 'all' && (
              <div className="shop-search-meta-row">
                <p className="shop-search-meta" aria-live="polite">
                  {allFiltered.length} result{allFiltered.length === 1 ? '' : 's'} for &ldquo;{searchQuery.trim()}&rdquo;
                </p>
                {hasSearchResults && (
                  <button
                    type="button"
                    className="search-assist-btn"
                    onClick={(event) =>
                      openAssistant(
                        {
                          surface: 'catalog',
                          entry_point: 'help_me_choose',
                          visible_product_ids: allFiltered.slice(0, 20).map((product) => product.id),
                        },
                        event.currentTarget,
                        `Help me choose from these search results: ${allFiltered.map((product) => product.name).join(', ')}`
                      )
                    }
                  >
                    Ask ShopAssist about these results
                  </button>
                )}
              </div>
            )}
            <div className="shop-toolbar-actions">
              <div className="catalog-modes" aria-label="Catalog view">
                <button className={catalogMode === 'all' ? 'active' : ''} onClick={() => setCatalogMode('all')}>
                  All Products
                </button>
                {assistRecommendations.length > 0 && (
                  <button className={catalogMode === 'picks' ? 'active' : ''} onClick={() => setCatalogMode('picks')}>
                    ShopAssist Picks ({assistRecommendations.length})
                  </button>
                )}
              </div>
              <div className="shop-filters" aria-label="Product category">
                {categories.map((category) => (
                  <button
                    key={category}
                    className={`filter-btn ${filter === category ? 'active' : ''}`}
                    onClick={() => setFilter(category)}
                  >
                    {category === 'all' ? 'All' : category}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {showEmptySearch ? (
            <div className="shop-empty-search">
              <p>No products found for &ldquo;{searchQuery.trim()}&rdquo;</p>
              <span>Try a different keyword, switch category, or ask ShopAssist for help.</span>
              <div className="shop-empty-search-actions">
                <button type="button" className="shop-empty-clear" onClick={() => setSearchQuery('')}>
                  Clear search
                </button>
                <button
                  type="button"
                  className="shop-empty-assist"
                  onClick={(event) =>
                    openAssistant(
                      {
                        surface: 'catalog',
                        entry_point: 'help_me_choose',
                        visible_product_ids: products.slice(0, 20).map((product) => product.id),
                      },
                      event.currentTarget,
                      `Help me find ${searchQuery.trim()}`
                    )
                  }
                >
                  Ask ShopAssist
                </button>
              </div>
            </div>
          ) : (
          <div className="shop-grid">
            {catalogMode === 'picks'
              ? sortedPickItems.map((item) => (
                  <ProductShopCard
                    key={item.product.id}
                    product={item.product}
                    reason={item.reason}
                    reasonCodes={item.reason_codes}
                    isWishlisted={wishlistIds.has(item.product.id)}
                    isInCart={cartIds.has(item.product.id)}
                    onProductClick={handleProductClick}
                    onToggleWishlist={handleToggleWishlist}
                    onAddToCart={handleAddToCart}
                    onRemoveFromCart={handleRemoveFromCart}
                    compareMode={showCompareMode}
                    isCompareSelected={compareIds.has(item.product.id)}
                    onToggleCompare={handleToggleCompare}
                  />
                ))
              : allFiltered.map((product) => (
                  <ProductShopCard
                    key={product.id}
                    product={product}
                    isWishlisted={wishlistIds.has(product.id)}
                    isInCart={cartIds.has(product.id)}
                    onProductClick={handleProductClick}
                    onToggleWishlist={handleToggleWishlist}
                    onAddToCart={handleAddToCart}
                    onRemoveFromCart={handleRemoveFromCart}
                    compareMode={showCompareMode}
                    isCompareSelected={compareIds.has(product.id)}
                    onToggleCompare={handleToggleCompare}
                  />
                ))}
          </div>
          )}

          {compareIds.size > 0 && (
            <div className="compare-bar">
              <span>{compareIds.size} selected (max 3)</span>
              <div className="compare-bar-actions">
                <button type="button" className="compare-bar-clear" onClick={() => setCompareIds(new Set())}>
                  Clear
                </button>
                <button
                  type="button"
                  className="compare-bar-go"
                  disabled={compareIds.size < 2}
                  onClick={handleOpenCompare}
                >
                  Compare {compareIds.size} products
                </button>
              </div>
            </div>
          )}
        </section>

        <RecommendationsPanel
          recommendations={recommendations}
          wishlistCount={wishlistIds.size}
          cartCount={cartIds.size}
          viewedCount={viewedIds.size}
          loading={recLoading}
          aiPowered={aiPowered}
          recommendationPipeline={recommendationPipeline}
          smartCart={smartCart}
          onToggleWishlist={handleToggleWishlist}
          onAddToCart={handleAddToCart}
          onRemoveFromCart={handleRemoveFromCart}
          onCheckout={() => setShowCheckout(true)}
          onAddBundle={handleAddBundle}
          wishlistIds={wishlistIds}
          cartIds={cartIds}
        />
      </div>

      <ShopAssistFab
        hidden={drawerOpen}
        onOpen={(source) =>
          openAssistant(
            assistContext ?? {
              surface: 'catalog',
              entry_point: 'help_me_choose',
              visible_product_ids: products.slice(0, 20).map((product) => product.id),
            },
            source
          )
        }
      />

      <ShopAssistDrawer
        open={drawerOpen}
        messages={messages}
        draft={draft}
        loading={assistLoading}
        error={assistError}
        status={assistStatus}
        mode={assistMode}
        need={need}
        context={assistContext}
        contextProduct={products.find((product) => product.id === assistContext?.product_id) ?? null}
        recommendations={assistRecommendations}
        comparison={comparison}
        actions={assistActions}
        confirming={confirming}
        confirmed={confirmed}
        onClose={closeAssistant}
        onDraftChange={setDraft}
        onSend={handleSend}
        onRetry={() => handleSend(lastSent.current)}
        onRemoveContext={() => setAssistContext(null)}
        onRemoveNeed={handleRemoveNeed}
        onAction={handleAssistAction}
        onConfirmBundle={handleConfirmBundle}
      />

      <ProductDetailModal
        product={selectedProduct}
        isWishlisted={selectedProduct ? wishlistIds.has(selectedProduct.id) : false}
        isInCart={selectedProduct ? cartIds.has(selectedProduct.id) : false}
        onClose={() => setSelectedProduct(null)}
        onToggleWishlist={handleToggleWishlist}
        onAddToCart={handleAddToCart}
        onRemoveFromCart={handleRemoveFromCart}
        onAskShopAssist={(product, _source) => {
          setSelectedProduct(null)
          openAssistant(
            {
              surface: 'product',
              entry_point: 'product_detail',
              product_id: product.id,
              visible_product_ids: [product.id],
            },
            document.querySelector<HTMLElement>(`[data-product-id="${product.id}"]`)
          )
        }}
      />

      <CheckoutModal
        open={showCheckout}
        cart={cartProducts}
        sessionId={sessionId}
        subtotal={smartCart.subtotal}
        estimatedSavings={smartCart.estimatedSavings}
        discountOffer={abandonment?.discount_offer ?? 0}
        onClose={() => setShowCheckout(false)}
        onSuccess={handleCheckoutSuccess}
      />

      <CompareModal
        open={compareOpen}
        products={compareResults}
        loading={compareLoading}
        onClose={() => setCompareOpen(false)}
      />
    </>
  )
}

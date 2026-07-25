import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent, type MouseEvent } from 'react'
import {
  addBundleToCart,
  addToCart,
  cancelCheckoutReview,
  confirmShopAssistCartProposal,
  DEMO_USERS,
  compareProducts,
  dismissAbandonment,
  fetchProductsWithMeta,
  getIntelligenceProfile,
  getCheckoutReview,
  getOrder,
  getPersonalizationUserId,
  getPersonalizedRecommendations,
  getSession,
  getStoredSessionId,
  getOrderByIdempotency,
  ensureSessionId,
  onPersonalizationUserChange,
  removeFromCart,
  sendMessage,
  setPersonalizationUserId,
  subscribeToPersonalizedRecommendations,
  trackInteraction,
  toggleWishlist,
  trackProductView,
  type AbandonmentStatus,
  type BundleSuggestion,
  type CrossSellItem,
  type ChatAction,
  type CartProposal,
  type CheckoutReview,
  type ChatMessage,
  type ChatStatus,
  type OrderReceipt,
  type NextBestAction,
  type PageContext,
  type Product,
  type CustomerIntent,
  type PersonalizedProfile,
  type PersonalizedRecommendation,
  type ProductSearchMethod,
  type Channel,
  type ShoppingNeed,
  type ShopAssistRecommendation,
} from '../api'
import AbandonmentBanner from '../components/AbandonmentBanner'
import IdleCartNudge from '../components/IdleCartNudge'
import CatalogFilters from '../components/CatalogFilters'
import CheckoutModal from '../components/CheckoutModal'
import CompareModal from '../components/CompareModal'
import NextBestActionBanner from '../components/NextBestActionBanner'
import OmnichannelSyncBanner from '../components/OmnichannelSyncBanner'
import ProductDetailModal from '../components/ProductDetailModal'
import ProductSearchBar from '../components/ProductSearchBar'
import ProductShopCard from '../components/ProductShopCard'
import ProfileSwitcher from '../components/ProfileSwitcher'
import RecommendationsPanel from '../components/RecommendationsPanel'
import ShopAssistDrawer from '../components/ShopAssistDrawer'
import ShopAssistFab from '../components/ShopAssistFab'
import SmartCartPanel from '../components/SmartCartPanel'
import { useCartAbandonmentTracking } from '../hooks/useCartAbandonment'
import { useCrossTabSync } from '../hooks/useCrossTabSync'
import {
  filterProductsForSearch,
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

const ACTIVE_REVIEW_KEY = 'oneshop.active-checkout-review'

function loadActiveReview(): CheckoutReview | null {
  try {
    const raw = sessionStorage.getItem(ACTIVE_REVIEW_KEY)
    if (!raw) return null
    const review = JSON.parse(raw) as CheckoutReview
    return review.confirmation_token && new Date(review.expires_at).getTime() > Date.now()
      ? review
      : null
  } catch {
    return null
  }
}

const discoveryCategoryLabel = (category: string) => {
  const labels: Record<string, string> = {
    all: 'For You',
    phone: 'Phones',
    tablet: 'Tablets',
    plan: 'Plans',
    accessory: 'Accessories',
    device: 'Devices',
  }
  return labels[category] ?? category
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
  const [cartVersion, setCartVersion] = useState<number | null>(null)
  const [wishlistIds, setWishlistIds] = useState<Set<string>>(new Set())
  const [cartIds, setCartIds] = useState<Set<string>>(new Set())
  const [viewedIds, setViewedIds] = useState<Set<string>>(new Set())
  const [cartProducts, setCartProducts] = useState<Product[]>([])
  const [recommendations, setRecommendations] = useState<PersonalizedRecommendation[]>([])
  const [personalizationUserId, setPersonalizationUser] = useState(getPersonalizationUserId)
  const [personalizedProfile, setPersonalizedProfile] = useState<PersonalizedProfile | null>(null)
  const [profileVersion, setProfileVersion] = useState<number | string>(0)
  const [streamStatus, setStreamStatus] = useState<'connecting' | 'live' | 'fallback' | 'error'>('connecting')
  const [personalizationError, setPersonalizationError] = useState<string | null>(null)
  const [intent, setIntent] = useState<CustomerIntent | null>(null)
  const [aiPowered, setAiPowered] = useState(false)
  const [nbaActions, setNbaActions] = useState<NextBestAction[]>([])
  const [nbaStage, setNbaStage] = useState('new')
  const [nbaAi, setNbaAi] = useState(false)
  const [smartCart, setSmartCart] = useState<{
    bundles: BundleSuggestion[]
    crossSell: CrossSellItem[]
    nudge: string
    checkoutTip: string
    aiPowered: boolean
    subtotal: number
    discount: number
    total: number
    oneTimeTotal: number
    monthlyTotal: number
    estimatedSavings: number
    cartItems: Product[]
  }>({
    bundles: [],
    crossSell: [],
    nudge: '',
    checkoutTip: '',
    aiPowered: false,
    subtotal: 0,
    discount: 0,
    total: 0,
    oneTimeTotal: 0,
    monthlyTotal: 0,
    estimatedSavings: 0,
    cartItems: [],
  })
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
  const [cartOpen, setCartOpen] = useState(false)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [draft, setDraft] = useState('')
  const [need, setNeed] = useState<ShoppingNeed>(EMPTY_NEED)
  const [assistRecommendations, setAssistRecommendations] = useState<ShopAssistRecommendation[]>([])
  const [comparison, setComparison] = useState<Product[]>([])
  const [assistActions, setAssistActions] = useState<ChatAction[]>([])
  const [assistCartProposal, setAssistCartProposal] = useState<CartProposal | null>(null)
  const [checkoutReview, setCheckoutReview] = useState<CheckoutReview | null>(loadActiveReview)
  const [orderReceipt, setOrderReceipt] = useState<OrderReceipt | null>(null)
  const [assistStatus, setAssistStatus] = useState<ChatStatus | null>(null)
  const [assistMode, setAssistMode] = useState<'ai' | 'fallback' | null>(null)
  const [assistContext, setAssistContext] = useState<PageContext | null>(null)
  const [assistLoading, setAssistLoading] = useState(false)
  const [assistError, setAssistError] = useState<string | null>(null)
  const [catalogMode, setCatalogMode] = useState<'all' | 'picks'>('all')
  const [showFullCatalog, setShowFullCatalog] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const [confirmed, setConfirmed] = useState(false)
  const lastSent = useRef('')
  const launcherRef = useRef<HTMLElement | null>(null)
  const confirmationInFlight = useRef(false)
  const confirmationKeys = useRef(new Map<string, string>())
  const orderConfirmationKeys = useRef(new Map<string, string>())
  const impressionKeys = useRef(new Set<string>())

  useCartAbandonmentTracking(cartIds.size, sessionId)

  useEffect(
    () => onPersonalizationUserChange((userId) => setPersonalizationUser(userId)),
    []
  )

  useEffect(() => {
    if (!checkoutReview?.confirmation_token) return
    let cancelled = false
    const token = checkoutReview.confirmation_token
    getCheckoutReview(
      checkoutReview.review_id,
      checkoutReview.session_id,
      personalizationUserId,
    ).then(async (persisted) => {
      if (cancelled) return
      if (
        persisted.status === 'awaiting_confirmation'
        && new Date(persisted.expires_at).getTime() > Date.now()
      ) {
        const recovered = { ...persisted, confirmation_token: token }
        setCheckoutReview(recovered)
        sessionStorage.setItem(ACTIVE_REVIEW_KEY, JSON.stringify(recovered))
        return
      }
      if (persisted.status === 'consumed' && persisted.consumed_order_id) {
        const receipt = await getOrder(
          persisted.consumed_order_id,
          persisted.session_id,
          personalizationUserId,
        )
        if (!cancelled) setOrderReceipt(receipt)
      }
      if (!cancelled) {
        setCheckoutReview(null)
        sessionStorage.removeItem(ACTIVE_REVIEW_KEY)
      }
    }).catch(() => {
      if (!cancelled) {
        setCheckoutReview(null)
        sessionStorage.removeItem(ACTIVE_REVIEW_KEY)
      }
    })

    const expiresIn = Math.max(0, new Date(checkoutReview.expires_at).getTime() - Date.now())
    const expiryTimer = window.setTimeout(() => {
      if (!cancelled) {
        setCheckoutReview(null)
        sessionStorage.removeItem(ACTIVE_REVIEW_KEY)
        setAssistError('The checkout review expired. Open checkout to create a fresh review.')
      }
    }, expiresIn)
    return () => {
      cancelled = true
      window.clearTimeout(expiryTimer)
    }
  }, [checkoutReview?.review_id, personalizationUserId])

  const applySession = useCallback((session: {
    session_id: string
    cart_version?: number
    wishlist_ids: string[]
    cart_ids: string[]
    viewed_ids: string[]
    cart?: Product[]
  }) => {
    setSessionId(session.session_id)
    if (typeof session.cart_version === 'number') setCartVersion(session.cart_version)
    setWishlistIds(new Set(session.wishlist_ids))
    setCartIds(new Set(session.cart_ids))
    setViewedIds(new Set(session.viewed_ids))
    if (session.cart) setCartProducts(session.cart)
  }, [])

  useEffect(() => {
    if (cartVersion === null) return
    if (
      assistCartProposal?.cart_version !== undefined
      && assistCartProposal.cart_version !== cartVersion
    ) {
      setAssistCartProposal(null)
      setAssistActions((current) => current.filter((action) => !action.type.startsWith('PROPOSE_')))
    }
    if (
      checkoutReview?.cart_version !== undefined
      && checkoutReview.cart_version !== cartVersion
    ) {
      setCheckoutReview(null)
      sessionStorage.removeItem(ACTIVE_REVIEW_KEY)
      setAssistError('Your cart changed. Open checkout to create a fresh final review.')
    }
  }, [
    assistCartProposal?.cart_version,
    cartVersion,
    checkoutReview?.cart_version,
  ])

  useEffect(() => {
    if (!assistCartProposal?.expires_at) return
    const expiresIn = Math.max(
      0,
      new Date(assistCartProposal.expires_at).getTime() - Date.now(),
    )
    const expiryTimer = window.setTimeout(() => {
      setAssistCartProposal((current) => (
        current?.proposal_id === assistCartProposal.proposal_id ? null : current
      ))
      setAssistActions((current) => current.filter((action) => !action.type.startsWith('PROPOSE_')))
      setAssistError('That cart proposal expired. Ask Ava for a fresh review.')
    }, expiresIn)
    return () => window.clearTimeout(expiryTimer)
  }, [assistCartProposal?.expires_at, assistCartProposal?.proposal_id])

  const refreshIntelligence = useCallback(async (
    sid: string | null,
    userId: string = personalizationUserId,
  ) => {
    setRecLoading(true)
    try {
      const profile = await getIntelligenceProfile(sid, channel, userId)
      setSessionId(profile.session_id)
      setIntent(profile.intent)
      setAiPowered(profile.ai_powered)
      setNbaActions(profile.next_actions)
      setNbaStage(profile.funnel_stage)
      setNbaAi(profile.ai_powered)
      setCartProducts(profile.cart)
      setCartIds(new Set(profile.cart.map((p) => p.id)))
      setRecommendationPipeline(profile.recommendation_pipeline || 'rules')
      setSmartCart({
        bundles: profile.bundles,
        crossSell: profile.cross_sell_suggestions ?? [],
        nudge: profile.nudge,
        checkoutTip: profile.checkout_tip,
        aiPowered: false,
        subtotal: profile.subtotal,
        discount: profile.discount ?? profile.estimated_savings ?? 0,
        total: profile.total ?? profile.subtotal,
        oneTimeTotal: profile.one_time_total ?? profile.subtotal,
        monthlyTotal: profile.monthly_total ?? 0,
        estimatedSavings: profile.estimated_savings,
        cartItems: profile.cart,
      })
      if (profile.abandonment?.is_abandoned) setAbandonment(profile.abandonment)
      setSyncMessage(profile.sync_message ?? '')
      setChannelsUsed(profile.channels_used ?? [])
    } finally {
      setRecLoading(false)
    }
  }, [channel, personalizationUserId])

  const applyPersonalized = useCallback((response: Awaited<ReturnType<typeof getPersonalizedRecommendations>>) => {
    setRecommendations(response.recommendations)
    setPersonalizedProfile(response.profile)
    setProfileVersion(response.profile_version)
    setPersonalizationError(null)
  }, [])

  useEffect(() => {
    let cancelled = false
    setStreamStatus('connecting')
    getPersonalizedRecommendations(personalizationUserId, sessionId, channel)
      .then((response) => {
        if (cancelled) return
        applyPersonalized(response)
        setStreamStatus('fallback')
      })
      .catch((error) => {
        if (cancelled) return
        setStreamStatus('error')
        setPersonalizationError(error instanceof Error ? error.message : 'Personalization unavailable.')
      })
    const unsubscribe = subscribeToPersonalizedRecommendations(
      personalizationUserId,
      sessionId,
      channel,
      'general',
      6,
      (response) => {
        if (cancelled) return
        applyPersonalized(response)
        setStreamStatus('live')
      },
      () => {
        if (!cancelled) setStreamStatus((current) => current === 'live' ? 'fallback' : current)
      }
    )
    return () => {
      cancelled = true
      unsubscribe()
    }
  }, [applyPersonalized, channel, personalizationUserId, sessionId])

  useEffect(() => {
    if (recommendations.length === 0) return
    const key = `${personalizationUserId}:${channel}:${recommendations
      .map((item) => item.product.id)
      .join(',')}`
    if (impressionKeys.current.has(key)) return
    impressionKeys.current.add(key)
    void Promise.all(recommendations.map((item) => trackInteraction({
        user_id: personalizationUserId,
        event_type: 'impression',
        product_id: item.product.id,
        channel,
        session_id: sessionId,
        metadata: { surface: 'for_you', visible: true },
      }))).catch(() => {
      impressionKeys.current.delete(key)
    })
  }, [channel, personalizationUserId, recommendations, sessionId])

  const observeInteraction = useCallback((
    event_type: 'product_view' | 'wishlist_add' | 'wishlist_remove' | 'cart_add' | 'cart_remove' | 'rec_click',
    productId: string,
    metadata: { rec_position?: number; rec_type?: string; surface?: string } = {}
  ) => {
    void trackInteraction({
      user_id: personalizationUserId,
      event_type,
      product_id: productId,
      channel,
      session_id: sessionId,
      metadata,
    }).catch(() => {
      setPersonalizationError('Your shopping action succeeded, but personalization could not update yet.')
    })
  }, [channel, personalizationUserId, sessionId])

  const handleProfileChange = (userId: string) => {
    setPersonalizationUserId(userId)
    setPersonalizationUser(userId)
    setRecommendations([])
    setPersonalizedProfile(null)
    setMessages([])
    setDraft('')
    setNeed(EMPTY_NEED)
    setAssistRecommendations([])
    setComparison([])
    setAssistActions([])
    setAssistStatus(null)
    setAssistMode(null)
    setAssistContext(null)
    setAssistError(null)
    setConfirmed(false)
    setAssistCartProposal(null)
    setCheckoutReview(null)
    setOrderReceipt(null)
    setCartIds(new Set())
    setCartProducts([])
    setCartVersion(0)
    setAbandonment(null)
    setSmartCart((current) => ({
      ...current,
      bundles: [],
      crossSell: [],
      nudge: '',
      checkoutTip: '',
      subtotal: 0,
      discount: 0,
      total: 0,
      oneTimeTotal: 0,
      monthlyTotal: 0,
      estimatedSavings: 0,
      cartItems: [],
    }))
    sessionStorage.removeItem(ACTIVE_REVIEW_KEY)
    setFilter('all')
    setCatalogMode('all')
    setShowFullCatalog(false)
    void refreshIntelligence(sessionId, userId).catch(() => {
      setPersonalizationError('This profile changed, but its cart could not refresh yet.')
    })
  }

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
        const [result, session] = await Promise.all([
          loadProducts(searchQuery, filter, brandFilter, priceRange),
          getSession(sessionId),
        ])
        const catalog = result.products
        setCatalogBrands([...new Set(catalog.map((product) => product.brand))].sort())
        setProductNames(catalog.map((product) => product.name))
        setProducts(result.products)
        setSearchMethod(result.search_method)
        applySession({ ...session, cart: session.cart })
        void refreshIntelligence(session.session_id).catch(() => {
          setPersonalizationError('Personalization is still loading. The catalog remains available.')
        })
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
    observeInteraction('product_view', product.id, { surface: 'catalog' })
    await refreshIntelligence(session.session_id)
  }

  const handleToggleWishlist = async (productId: string) => {
    const wasWishlisted = wishlistIds.has(productId)
    const session = await toggleWishlist(productId, sessionId, channel)
    applySession({ ...session, cart: session.cart })
    observeInteraction(wasWishlisted ? 'wishlist_remove' : 'wishlist_add', productId)
    await refreshIntelligence(session.session_id)
  }

  const handleAddToCart = async (productId: string) => {
    const session = await addToCart(productId, sessionId, channel)
    applySession({ ...session, cart: session.cart })
    setAssistCartProposal(null)
    setCheckoutReview(null)
    sessionStorage.removeItem(ACTIVE_REVIEW_KEY)
    observeInteraction('cart_add', productId)
    await refreshIntelligence(session.session_id)
  }

  const handleRemoveFromCart = async (productId: string) => {
    const session = await removeFromCart(productId, sessionId, channel)
    applySession({ ...session, cart: session.cart })
    setAssistCartProposal(null)
    setCheckoutReview(null)
    sessionStorage.removeItem(ACTIVE_REVIEW_KEY)
    observeInteraction('cart_remove', productId)
    await refreshIntelligence(session.session_id)
  }

  const handleAddBundle = async (productIds: string[]) => {
    const session = await addBundleToCart(productIds, sessionId, channel)
    applySession({ ...session, cart: session.cart })
    setAssistCartProposal(null)
    setCheckoutReview(null)
    sessionStorage.removeItem(ACTIVE_REVIEW_KEY)
    await refreshIntelligence(session.session_id)
  }

  const handleCheckoutReview = (review: CheckoutReview) => {
    setAssistCartProposal(null)
    if (typeof review.cart_version === 'number') setCartVersion(review.cart_version)
    setCheckoutReview(review)
    setOrderReceipt(null)
    sessionStorage.setItem(ACTIVE_REVIEW_KEY, JSON.stringify(review))
    setShowCheckout(false)
    setCartOpen(false)
    setDrawerOpen(true)
    setAssistContext({
      surface: 'cart',
      entry_point: 'cart',
      visible_product_ids: review.items.map((item) => item.product_id),
    })
    setMessages((current) => [
      ...current,
      {
        role: 'assistant',
        content: 'I prepared the trusted final demo order review. Check it below, then reply with yes, confirm, place order, or go ahead as the entire message.',
        status: 'recommended',
        mode: 'fallback',
      },
    ])
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
    setCartOpen(false)
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
    const normalized = text.toLowerCase().replace(/[^a-z\s]/g, '').trim().replace(/\s+/g, ' ')
    const isCheckoutTransition = [
      'yes', 'confirm', 'place order', 'go ahead', 'no', 'cancel', 'go back',
    ].includes(normalized)
    const orderKey = checkoutReview
      ? orderConfirmationKeys.current.get(checkoutReview.review_id) ?? crypto.randomUUID()
      : null
    if (checkoutReview && orderKey) {
      orderConfirmationKeys.current.set(checkoutReview.review_id, orderKey)
    }
    const checkoutConfirmation = (
      checkoutReview?.confirmation_token && isCheckoutTransition && orderKey
    ) ? {
        review_id: checkoutReview.review_id,
        confirmation_token: checkoutReview.confirmation_token,
        idempotency_key: orderKey,
      } : undefined

    try {
      const response = await sendMessage(
        text,
        sessionId,
        assistContext ?? {
          surface: 'catalog',
          entry_point: 'help_me_choose',
          visible_product_ids: products.slice(0, 20).map((product) => product.id),
        },
        channel,
        personalizationUserId,
        personalizedProfile ? {
          preferred_brands: Object.entries(personalizedProfile.brand_affinity)
            .sort((a, b) => b[1] - a[1])
            .slice(0, 3)
            .map(([brand]) => brand),
          preferred_categories: Object.entries(personalizedProfile.category_affinity)
            .sort((a, b) => b[1] - a[1])
            .slice(0, 3)
            .map(([category]) => category),
          price_centroid: personalizedProfile.price_centroid,
          interaction_count: personalizedProfile.total_interactions,
        } : undefined,
        checkoutConfirmation,
      )
      setSessionId(response.session_id)
      setNeed(response.need_profile)
      setAssistRecommendations(response.recommendations.slice(0, 3))
      setAssistActions(response.actions)
      setAssistCartProposal(response.cart_proposal ?? null)
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
      if (response.open_checkout) {
        setShowCheckout(true)
      }
      if (response.checkout_review_status === 'cancelled') {
        setCheckoutReview(null)
        sessionStorage.removeItem(ACTIVE_REVIEW_KEY)
      }
      if (response.order_receipt) {
        setOrderReceipt(response.order_receipt)
        setCheckoutReview(null)
        setCartIds(new Set())
        setCartProducts([])
        setSmartCart((current) => ({
          ...current,
          cartItems: [],
          subtotal: 0,
          discount: 0,
          total: 0,
          oneTimeTotal: 0,
          monthlyTotal: 0,
          bundles: [],
          crossSell: [],
        }))
        sessionStorage.removeItem(ACTIVE_REVIEW_KEY)
        setAbandonment(null)
        void reloadFromServer().catch(() => {
          setAssistError('Demo order saved. Shopping recommendations could not refresh yet.')
        })
      }
    } catch (error) {
      if (checkoutReview && orderKey && isCheckoutTransition && sessionId) {
        try {
          const recovered = await getOrderByIdempotency(
            orderKey,
            sessionId,
            personalizationUserId,
          )
          setOrderReceipt(recovered)
          setCheckoutReview(null)
          setCartIds(new Set())
          setCartProducts([])
          sessionStorage.removeItem(ACTIVE_REVIEW_KEY)
          void reloadFromServer().catch(() => {
            setAssistError('Demo order recovered. Shopping recommendations could not refresh yet.')
          })
          setMessages((current) => [
            ...current,
            {
              role: 'assistant',
              content: `Recovered demo order ${recovered.order_id}. No duplicate order was created.`,
              status: 'recommended',
              mode: 'fallback',
            },
          ])
          return
        } catch {
          // No persisted order exists for this key; surface the original error.
        }
      }
      const errorMessage = error instanceof Error ? error.message : 'Ava could not respond.'
      setAssistError(errorMessage.replace(/port\s*8000/gi, 'service'))
    } finally {
      setAssistLoading(false)
    }
  }, [
    assistContext,
    assistLoading,
    channel,
    checkoutReview,
    draft,
    personalizationUserId,
    personalizedProfile,
    products,
    reloadFromServer,
    sessionId,
  ])

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

  const handleConfirmProposal = async (proposalId: string) => {
    if (confirmationInFlight.current || confirming || confirmed || !sessionId) return
    if (!assistCartProposal || assistCartProposal.proposal_id !== proposalId) {
      setAssistError('This proposal is no longer valid. Please ask Ava to refresh it.')
      return
    }
    confirmationInFlight.current = true
    setConfirming(true)
    setAssistError(null)
    try {
      const idempotencyKey = confirmationKeys.current.get(proposalId) ?? crypto.randomUUID()
      confirmationKeys.current.set(proposalId, idempotencyKey)
      const result = await confirmShopAssistCartProposal(
        proposalId,
        idempotencyKey,
        sessionId,
        personalizationUserId,
        channel,
      )
      setSessionId(result.session_id)
      setCartVersion(result.cart_version)
      setCartIds(new Set(result.cart_summary.items.map((product) => product.id)))
      setCartProducts(result.cart_summary.items)
      setAssistCartProposal(null)
      setAssistActions((current) => current.filter(
        (action) =>
          action.type !== 'PROPOSE_ADD_TO_CART'
          && action.type !== 'PROPOSE_ADD_BUNDLE'
          && action.type !== 'PROPOSE_REMOVE_FROM_CART',
      ))
      const changedIds = result.operation === 'remove'
        ? result.removed_product_ids ?? []
        : result.added_product_ids
      const changedProducts = products.filter((product) => changedIds.includes(product.id))
      setMessages((current) => [
        ...current,
        {
          role: 'assistant',
          content: changedProducts.length > 0
            ? `${result.operation === 'remove' ? 'Removed' : 'Added'} ${changedProducts.map((product) => product.name).join(' and ')} ${result.operation === 'remove' ? 'from' : 'to'} your cart. Your cart now has ${result.cart_summary.total_items} item${result.cart_summary.total_items === 1 ? '' : 's'}.`
            : result.operation === 'remove'
              ? 'Those items were no longer in your cart. Nothing else changed.'
              : 'Those exact items were already in your cart. Nothing was added twice.',
          status: 'recommended',
          mode: 'fallback',
        },
      ])
      setConfirmed(true)
      setConfirming(false)
      confirmationInFlight.current = false
      try {
        await refreshIntelligence(result.session_id)
      } catch {
        setAssistError('Cart updated. Recommendations could not refresh yet.')
      }
    } catch (error) {
      setAssistError(
        error instanceof Error
          ? error.message
          : 'The cart could not be updated. Nothing was added; please try again.',
      )
    } finally {
      confirmationInFlight.current = false
      setConfirming(false)
    }
  }

  const handleCancelCheckout = async () => {
    if (!checkoutReview || !sessionId) return
    try {
      await cancelCheckoutReview(
        checkoutReview.review_id,
        sessionId,
        personalizationUserId,
      )
      setCheckoutReview(null)
      sessionStorage.removeItem(ACTIVE_REVIEW_KEY)
      setMessages((current) => [
        ...current,
        {
          role: 'assistant',
          content: 'Demo checkout cancelled. Your cart is unchanged.',
          status: 'recommended',
          mode: 'fallback',
        },
      ])
    } catch (error) {
      setAssistError(error instanceof Error ? error.message : 'Could not cancel checkout')
    }
  }

  const categories = ['all', ...Array.from(new Set(products.map((product) => product.category)))]
  const normalizedQuery = searchQuery.trim().toLowerCase()
  const categoryFiltered =
    filter === 'all' ? products : products.filter((product) => product.category === filter)
  const allFiltered = sortProducts(
    filterProductsForSearch(categoryFiltered, searchQuery, searchMethod),
    sortBy
  )
  const activeDemoProfile = DEMO_USERS.find((user) => user.id === personalizationUserId) ?? DEMO_USERS[0]
  const recommendationByProduct = new Map(
    recommendations.map((recommendation, index) => [recommendation.product.id, { recommendation, index }])
  )
  const recentProducts = (personalizedProfile?.recent_views ?? [])
    .map((productId) => products.find((product) => product.id === productId))
    .filter((product): product is Product => Boolean(product))
    .slice(0, 4)
  const suggestedProducts = filter === 'all'
    ? recommendations.map((recommendation) => recommendation.product)
    : products
        .filter((product) => product.category === filter)
        .sort((left, right) => {
          const leftRank = recommendationByProduct.get(left.id)?.index ?? Number.MAX_SAFE_INTEGER
          const rightRank = recommendationByProduct.get(right.id)?.index ?? Number.MAX_SAFE_INTEGER
          return leftRank - rightRank || right.rating - left.rating || left.id.localeCompare(right.id)
        })
  const suggestedHeading = filter === 'all'
    ? `Suggested for ${activeDemoProfile.name}`
    : `${discoveryCategoryLabel(filter)} for ${activeDemoProfile.name}`
  const topPickProducts = suggestedProducts.slice(0, 3)
  const topPickHeading = filter === 'all'
    ? `Top picks for ${activeDemoProfile.name}`
    : `Top ${discoveryCategoryLabel(filter).toLowerCase()} for ${activeDemoProfile.name}`
  const profileAssistRecommendations: ShopAssistRecommendation[] = useMemo(
    () => recommendations
      .slice(0, 3)
      .map((item, index) => ({
        product: item.product,
        slot: item.product.category === 'plan'
          ? 'recommended_plan'
          : index === 0 ? 'primary_phone' : 'alternative_phone',
        reason_codes: item.reason_codes,
        reason: item.explanation,
      })),
    [recommendations],
  )
  const drawerRecommendations = assistRecommendations.length > 0
    ? assistRecommendations
    : profileAssistRecommendations
  const drawerRecommendationMode = assistRecommendations.length > 0 ? 'request' : 'profile'

  const selectDiscoveryTab = (category: string) => {
    setFilter(category)
    setCatalogMode('all')
    setShowFullCatalog(false)
  }

  const handleDiscoveryTabKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return
    event.preventDefault()
    const lastIndex = categories.length - 1
    const nextIndex =
      event.key === 'Home'
        ? 0
        : event.key === 'End'
          ? lastIndex
          : event.key === 'ArrowRight'
            ? (index + 1) % categories.length
            : (index - 1 + categories.length) % categories.length
    selectDiscoveryTab(categories[nextIndex])
    window.requestAnimationFrame(() => {
      document.getElementById(`discovery-tab-${categories[nextIndex]}`)?.focus()
    })
  }
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
      <div
        className={`shop-layout ${layout} ${
          drawerOpen ? 'assistant-open' : cartOpen ? 'cart-open' : ''
        }`}
      >
        <section className="shop-main">
          <ProfileSwitcher userId={personalizationUserId} onChange={handleProfileChange} />
          <div className="discovery-tabs" role="tablist" aria-label="Personalized product categories">
            {categories.map((category, index) => {
              const label = discoveryCategoryLabel(category)
              return (
                <button
                  id={`discovery-tab-${category}`}
                  key={category}
                  type="button"
                  role="tab"
                  aria-selected={filter === category && catalogMode === 'all' && !showFullCatalog}
                  aria-controls="suggested-products-panel"
                  tabIndex={filter === category ? 0 : -1}
                  className={filter === category && catalogMode === 'all' && !showFullCatalog ? 'active' : ''}
                  onClick={() => selectDiscoveryTab(category)}
                  onKeyDown={(event) => handleDiscoveryTabKeyDown(event, index)}
                >
                  {label}
                </button>
              )
            })}
          </div>
          {personalizationError && (
            <div className="personalization-error" role="status">{personalizationError}</div>
          )}
          <OmnichannelSyncBanner
            message={syncMessage}
            channelsUsed={channelsUsed}
            currentChannel={channel}
          />

          {abandonment?.is_abandoned && !drawerOpen && !showCheckout && !checkoutReview && (
            <AbandonmentBanner
              message={abandonment.recovery_message}
              onCheckout={() => setShowCheckout(true)}
              onDismiss={handleDismissAbandonment}
            />
          )}

          <NextBestActionBanner
            actions={nbaActions}
            aiPowered={nbaAi}
            funnelStage={nbaStage}
            onActionClick={handleNbaClick}
          />

          <section className="personalized-surface" aria-labelledby="personalized-heading">
            <div className="personalized-heading">
              <div>
                <span className="personalized-eyebrow">Highest-confidence matches</span>
                <h2 id="personalized-heading">{topPickHeading}</h2>
                <p>
                  {filter === 'all'
                    ? 'Three diverse picks ranked from weighted interaction signals across Web and Mobile.'
                    : `Personalized matches first, followed by stable catalog quality within ${discoveryCategoryLabel(filter).toLowerCase()}.`}
                </p>
              </div>
              <div className="personalized-heading-meta">
                <span className={`personalized-live ${streamStatus}`}>
                  {streamStatus === 'live' ? 'Live' : 'Updating'}
                </span>
                <span>Profile v{String(profileVersion)}</span>
              </div>
            </div>

            {topPickProducts.length > 0 ? (
              <div className="top-picks-grid">
                {topPickProducts.map((product, position) => (
                  <article className="top-pick-card" key={`${personalizationUserId}-${filter}-${product.id}`}>
                    <button
                      className="top-pick-main"
                      type="button"
                      onClick={() => {
                        observeInteraction('rec_click', product.id, {
                          rec_position: position + 1,
                          surface: filter === 'all' ? 'top_picks' : 'category_top_picks',
                        })
                        void handleProductClick(product)
                      }}
                      aria-label={`Open top pick ${product.name}`}
                    >
                      <img src={product.image_url} alt="" />
                      <span>
                        <small>
                          {product.brand} · {recommendationByProduct.has(product.id)
                            ? `${Math.round(recommendationByProduct.get(product.id)!.recommendation.score * 100)}% match`
                            : 'popular category pick'}
                        </small>
                        <strong>{product.name}</strong>
                        <em>
                          {recommendationByProduct.has(product.id)
                            ? recommendationByProduct.get(product.id)!.recommendation.explanation
                                .split(';')[0]
                                .replace('Recommended because ', '')
                            : `highly rated in the ${discoveryCategoryLabel(product.category).toLowerCase()} catalog`}
                        </em>
                      </span>
                    </button>
                    <div className="top-pick-footer">
                      <strong>
                        ${product.price.toFixed(0)}{product.category === 'plan' ? '/mo' : ''}
                      </strong>
                      <button
                        type="button"
                        onClick={() => handleAddToCart(product.id)}
                        disabled={cartIds.has(product.id)}
                        aria-label={cartIds.has(product.id) ? `${product.name} is in cart` : `Add ${product.name} to cart`}
                      >
                        {cartIds.has(product.id) ? 'In cart' : 'Add'}
                      </button>
                    </div>
                  </article>
                ))}
              </div>
            ) : (
              <div className="personalized-loading" role="status">
                Preparing {activeDemoProfile.name}&apos;s ranked picks…
              </div>
            )}
          </section>

          {recentProducts.length > 0 && (
            <section className="continue-surface" aria-labelledby="continue-heading">
              <div>
                <span className="personalized-eyebrow">Continue your journey</span>
                <h2 id="continue-heading">
                  {recentProducts.length === 1 ? 'Still looking at this?' : 'Still looking for these?'}
                </h2>
              </div>
              <div className="continue-strip">
                {recentProducts.map((product) => (
                  <button
                    type="button"
                    key={product.id}
                    className="continue-card"
                    onClick={() => void handleProductClick(product)}
                    aria-label={`Continue exploring ${product.name}`}
                  >
                    <img src={product.image_url} alt="" />
                    <span>
                      <strong>{product.name}</strong>
                      <small>
                        ${product.price.toFixed(0)}{product.category === 'plan' ? '/mo' : ''} · Continue exploring
                      </small>
                    </span>
                  </button>
                ))}
              </div>
            </section>
          )}

          <div className="catalog-heading">
            <div>
              <span className="personalized-eyebrow">
                {showFullCatalog ? 'Unranked catalog' : catalogMode === 'picks' ? 'Explicit assistant result' : 'Personalized discovery'}
              </span>
              <h2>
                {showFullCatalog ? 'Browse full catalog' : catalogMode === 'picks' ? 'Ava Picks' : suggestedHeading}
              </h2>
              <p>
                {showFullCatalog
                  ? 'All synthetic demo products in catalog order.'
                  : catalogMode === 'picks'
                    ? 'Exact products returned for your latest Ava request.'
                    : 'Ranked for this profile; switch the category tabs to narrow the feed.'}
              </p>
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
                    Ask Ava about these results
                  </button>
                )}
              </div>
            )}
            <div className="shop-toolbar-actions">
              <div className="catalog-modes" aria-label="Catalog view">
                <button
                  className={catalogMode === 'all' && !showFullCatalog ? 'active' : ''}
                  onClick={() => {
                    setCatalogMode('all')
                    setShowFullCatalog(false)
                  }}
                >
                  Suggested
                </button>
                {assistRecommendations.length > 0 && (
                  <button
                    className={catalogMode === 'picks' ? 'active' : ''}
                    onClick={() => {
                      setCatalogMode('picks')
                      setShowFullCatalog(false)
                    }}
                  >
                    Ava Picks ({assistRecommendations.length})
                  </button>
                )}
                <button
                  className={showFullCatalog ? 'active' : ''}
                  onClick={() => {
                    setCatalogMode('all')
                    setShowFullCatalog(true)
                  }}
                >
                  Full catalog
                </button>
              </div>
            </div>
          </div>

          {showEmptySearch ? (
            <div className="shop-empty-search">
              <p>No products found for &ldquo;{searchQuery.trim()}&rdquo;</p>
              <span>Try a different keyword, switch category, or ask Ava for help.</span>
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
                  Ask Ava
                </button>
              </div>
            </div>
          ) : (
          <div
            id="suggested-products-panel"
            className="shop-grid"
            role="tabpanel"
            aria-labelledby={`discovery-tab-${filter}`}
            aria-live="polite"
          >
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
              : (normalizedQuery || showFullCatalog ? allFiltered : suggestedProducts).map((product) => {
                  const recommendation = recommendationByProduct.get(product.id)?.recommendation
                  return (
                  <ProductShopCard
                    key={product.id}
                    product={product}
                    reason={recommendation?.explanation}
                    reasonCodes={recommendation?.reason_codes.slice(0, 2)}
                    isWishlisted={wishlistIds.has(product.id)}
                    isInCart={cartIds.has(product.id)}
                    onProductClick={(selected) => {
                      if (!showFullCatalog) {
                        observeInteraction('rec_click', selected.id, {
                          rec_position: recommendationByProduct.get(selected.id)
                            ? recommendationByProduct.get(selected.id)!.index + 1
                            : undefined,
                          surface: filter === 'all' ? 'suggested_for_you' : 'category_suggestions',
                        })
                      }
                      void handleProductClick(selected)
                    }}
                    onToggleWishlist={handleToggleWishlist}
                    onAddToCart={handleAddToCart}
                    onRemoveFromCart={handleRemoveFromCart}
                    compareMode={showCompareMode}
                    isCompareSelected={compareIds.has(product.id)}
                    onToggleCompare={handleToggleCompare}
                  />
                  )
                })}
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
          intent={intent}
          recommendations={recommendations}
          profile={personalizedProfile}
          profileVersion={profileVersion}
          streamStatus={streamStatus}
          wishlistCount={wishlistIds.size}
          cartCount={cartIds.size}
          viewedCount={viewedIds.size}
          loading={recLoading}
          aiPowered={aiPowered}
          recommendationPipeline={recommendationPipeline}
        />
      </div>

      {!drawerOpen && !cartOpen && (
        <button
          type="button"
          className="cart-fab"
          aria-label={`Open cart with ${cartIds.size} ${cartIds.size === 1 ? 'item' : 'items'}`}
          onClick={() => {
            setDrawerOpen(false)
            setCartOpen(true)
          }}
        >
          <span>Cart</span>
          <strong>{cartIds.size}</strong>
        </button>
      )}

      <aside
        className={`cart-drawer ${cartOpen ? 'open' : ''}`}
        aria-label="Shopping cart"
        aria-hidden={!cartOpen}
      >
        <div className="cart-drawer-header">
          <div>
            <span>Trusted catalog totals</span>
            <h2>Shopping cart</h2>
          </div>
          <button
            type="button"
            aria-label="Close cart"
            onClick={() => setCartOpen(false)}
          >
            ×
          </button>
        </div>
        <SmartCartPanel
          bundles={smartCart.bundles}
          crossSell={smartCart.crossSell}
          nudge={smartCart.nudge}
          checkoutTip={smartCart.checkoutTip}
          aiPowered={smartCart.aiPowered}
          cartCount={cartIds.size}
          cartItems={smartCart.cartItems}
          oneTimeTotal={smartCart.oneTimeTotal}
          monthlyTotal={smartCart.monthlyTotal}
          onCheckout={() => {
            setCartOpen(false)
            setShowCheckout(true)
          }}
          onAddBundle={handleAddBundle}
          onAddCrossSell={handleAddToCart}
          onRemoveFromCart={handleRemoveFromCart}
        />
      </aside>

      <ShopAssistFab
        hidden={drawerOpen || cartOpen}
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
        recommendations={drawerRecommendations}
        recommendationMode={drawerRecommendationMode}
        recommendationHeading={
          drawerRecommendationMode === 'profile'
            ? `Recommended for ${activeDemoProfile.name}`
            : 'Ava recommends'
        }
        comparison={comparison}
        actions={assistActions}
        cartProposal={assistCartProposal}
        checkoutReview={checkoutReview}
        orderReceipt={orderReceipt}
        confirming={confirming}
        confirmed={confirmed}
        onClose={closeAssistant}
        onDraftChange={setDraft}
        onSend={handleSend}
        onRetry={() => handleSend(lastSent.current)}
        onRemoveContext={() => setAssistContext(null)}
        onRemoveNeed={handleRemoveNeed}
        onAction={handleAssistAction}
        onConfirmProposal={handleConfirmProposal}
        onCancelProposal={() => {
          setAssistCartProposal(null)
          setAssistActions((current) => current.filter(
            (action) => !action.type.startsWith('PROPOSE_'),
          ))
        }}
        onCancelCheckout={handleCancelCheckout}
        onViewPicks={() => {
          setFilter('all')
          setCatalogMode(drawerRecommendationMode === 'request' ? 'picks' : 'all')
          setShowFullCatalog(false)
          closeAssistant()
        }}
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
        userId={personalizationUserId}
        onClose={() => setShowCheckout(false)}
        onReview={handleCheckoutReview}
      />

      <CompareModal
        open={compareOpen}
        products={compareResults}
        loading={compareLoading}
        onClose={() => setCompareOpen(false)}
      />

      {!showCheckout && !drawerOpen && !cartOpen && !selectedProduct && !compareOpen && (
        <IdleCartNudge
          cartItems={cartProducts}
          onCheckout={() => setShowCheckout(true)}
          onDismiss={() => {}}
        />
      )}
    </>
  )
}

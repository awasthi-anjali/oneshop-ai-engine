import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent, type MouseEvent } from 'react'
import {
  addBundleToCart,
  addToCart,
  confirmShopAssistCartProposal,
  DEMO_USERS,
  dismissAbandonment,
  fetchProducts,
  getIntelligenceProfile,
  getPersonalizationUserId,
  getPersonalizedRecommendations,
  getSession,
  getStoredSessionId,
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
  type ChatAction,
  type CartProposal,
  type ChatMessage,
  type ChatStatus,
  type CheckoutResponse,
  type CustomerIntent,
  type NextBestAction,
  type PageContext,
  type Product,
  type PersonalizedProfile,
  type PersonalizedRecommendation,
  type Channel,
  type ShoppingNeed,
  type ShopAssistRecommendation,
} from '../api'
import AbandonmentBanner from '../components/AbandonmentBanner'
import CheckoutModal from '../components/CheckoutModal'
import NextBestActionBanner from '../components/NextBestActionBanner'
import OmnichannelSyncBanner from '../components/OmnichannelSyncBanner'
import ProductDetailModal from '../components/ProductDetailModal'
import ProductShopCard from '../components/ProductShopCard'
import ProfileSwitcher from '../components/ProfileSwitcher'
import RecommendationsPanel from '../components/RecommendationsPanel'
import ShopAssistDrawer from '../components/ShopAssistDrawer'
import ShopAssistFab from '../components/ShopAssistFab'
import { useCartAbandonmentTracking } from '../hooks/useCartAbandonment'
import { useCrossTabSync } from '../hooks/useCrossTabSync'
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
    nudge: string
    checkoutTip: string
    aiPowered: boolean
    subtotal: number
    estimatedSavings: number
  }>({ bundles: [], nudge: '', checkoutTip: '', aiPowered: false, subtotal: 0, estimatedSavings: 0 })
  const [abandonment, setAbandonment] = useState<AbandonmentStatus | null>(null)
  const [showCheckout, setShowCheckout] = useState(false)
  const [selectedProduct, setSelectedProduct] = useState<Product | null>(null)
  const [loading, setLoading] = useState(true)
  const [recLoading, setRecLoading] = useState(false)
  const [filter, setFilter] = useState('all')
  const [recommendationPipeline, setRecommendationPipeline] = useState('rules')
  const [retrievalMethod, setRetrievalMethod] = useState('none')
  const [retrievalQuery, setRetrievalQuery] = useState('')
  const [syncMessage, setSyncMessage] = useState('')
  const [channelsUsed, setChannelsUsed] = useState<string[]>([])

  const [drawerOpen, setDrawerOpen] = useState(false)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [draft, setDraft] = useState('')
  const [need, setNeed] = useState<ShoppingNeed>(EMPTY_NEED)
  const [assistRecommendations, setAssistRecommendations] = useState<ShopAssistRecommendation[]>([])
  const [comparison, setComparison] = useState<Product[]>([])
  const [assistActions, setAssistActions] = useState<ChatAction[]>([])
  const [assistCartProposal, setAssistCartProposal] = useState<CartProposal | null>(null)
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
  const impressionKeys = useRef(new Set<string>())

  useCartAbandonmentTracking(cartIds.size, sessionId)

  useEffect(
    () => onPersonalizationUserChange((userId) => setPersonalizationUser(userId)),
    []
  )

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
      setIntent(profile.intent)
      setAiPowered(profile.ai_powered)
      setNbaActions(profile.next_actions)
      setNbaStage(profile.funnel_stage)
      setNbaAi(profile.ai_powered)
      setCartProducts(profile.cart)
      setCartIds(new Set(profile.cart.map((p) => p.id)))
      setRecommendationPipeline(profile.recommendation_pipeline || 'rules')
      setRetrievalMethod(profile.retrieval_method || 'none')
      setRetrievalQuery(profile.retrieval_query || '')
      setSyncMessage(profile.sync_message || '')
      setChannelsUsed(profile.channels_used || [])
      setSmartCart({
        bundles: profile.bundles,
        nudge: profile.nudge,
        checkoutTip: profile.checkout_tip,
        aiPowered: profile.ai_powered,
        subtotal: profile.subtotal,
        estimatedSavings: profile.estimated_savings,
      })
      if (profile.abandonment?.is_abandoned) setAbandonment(profile.abandonment)
    } finally {
      setRecLoading(false)
    }
  }, [channel])

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
    setFilter('all')
    setCatalogMode('all')
    setShowFullCatalog(false)
  }

  const reloadFromServer = useCallback(async () => {
    const sid = getStoredSessionId() || ensureSessionId()
    const session = await getSession(sid)
    applySession({ ...session, cart: session.cart })
    await refreshIntelligence(session.session_id)
  }, [refreshIntelligence])

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
        const [prods, session] = await Promise.all([fetchProducts(), getSession(sessionId)])
        setProducts(prods)
        applySession({ ...session, cart: session.cart })
        await refreshIntelligence(session.session_id)
      } finally {
        setLoading(false)
      }
    }
    init()
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

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
    observeInteraction('cart_add', productId)
    await refreshIntelligence(session.session_id)
  }

  const handleRemoveFromCart = async (productId: string) => {
    const session = await removeFromCart(productId, sessionId, channel)
    applySession({ ...session, cart: session.cart })
    observeInteraction('cart_remove', productId)
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
        } : undefined
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
    } catch (error) {
      const message = error instanceof Error ? error.message : 'ShopAssist could not respond.'
      setAssistError(message.replace(/port\s*8000/gi, 'service'))
    } finally {
      setAssistLoading(false)
    }
  }, [assistContext, assistLoading, channel, draft, personalizationUserId, personalizedProfile, products, sessionId])

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
      setAssistError('This proposal is no longer valid. Please ask ShopAssist to refresh it.')
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
      setCartIds(new Set(result.cart_summary.items.map((product) => product.id)))
      setCartProducts(result.cart_summary.items)
      setAssistCartProposal(null)
      setAssistActions((current) => current.filter(
        (action) =>
          action.type !== 'PROPOSE_ADD_TO_CART'
          && action.type !== 'PROPOSE_ADD_BUNDLE',
      ))
      const addedProducts = result.cart_summary.items.filter((product) =>
        result.added_product_ids.includes(product.id),
      )
      setMessages((current) => [
        ...current,
        {
          role: 'assistant',
          content: addedProducts.length > 0
            ? `Added ${addedProducts.map((product) => product.name).join(' and ')} to your cart. Your cart now has ${result.cart_summary.total_items} item${result.cart_summary.total_items === 1 ? '' : 's'}.`
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
        setAssistError('Added to cart. Recommendations could not refresh yet.')
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

  const categories = ['all', ...Array.from(new Set(products.map((product) => product.category)))]
  const allFiltered = filter === 'all' ? products : products.filter((product) => product.category === filter)
  const pickItems = assistRecommendations.filter((item) =>
    filter === 'all' ? true : item.product.category === filter
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

  if (loading) return <div className="shop-loading">Loading OneShop…</div>

  return (
    <>
      <div className={`shop-layout ${layout}`}>
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

          {abandonment?.is_abandoned && (
            <AbandonmentBanner
              message={abandonment.recovery_message}
              discount={abandonment.discount_offer}
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
                {showFullCatalog ? 'Browse full catalog' : catalogMode === 'picks' ? 'ShopAssist Picks' : suggestedHeading}
              </h2>
              <p>
                {showFullCatalog
                  ? 'All synthetic demo products in catalog order.'
                  : catalogMode === 'picks'
                    ? 'Exact products returned for your latest ShopAssist request.'
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
                  ShopAssist Picks ({assistRecommendations.length})
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

          <div
            id="suggested-products-panel"
            className="shop-grid"
            role="tabpanel"
            aria-labelledby={`discovery-tab-${filter}`}
            aria-live="polite"
          >
            {catalogMode === 'picks'
              ? pickItems.map((item) => (
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
                  />
                ))
              : (showFullCatalog ? allFiltered : suggestedProducts).map((product) => {
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
                  />
                  )
                })}
          </div>
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
          retrievalMethod={retrievalMethod}
          retrievalQuery={retrievalQuery}
          smartCart={smartCart}
          onCheckout={() => setShowCheckout(true)}
          onAddBundle={handleAddBundle}
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
        recommendations={drawerRecommendations}
        recommendationMode={drawerRecommendationMode}
        recommendationHeading={
          drawerRecommendationMode === 'profile'
            ? `Recommended for ${activeDemoProfile.name}`
            : 'ShopAssist recommends'
        }
        comparison={comparison}
        actions={assistActions}
        cartProposal={assistCartProposal}
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
        subtotal={smartCart.subtotal}
        estimatedSavings={smartCart.estimatedSavings}
        discountOffer={abandonment?.discount_offer ?? 0}
        onClose={() => setShowCheckout(false)}
        onSuccess={handleCheckoutSuccess}
      />
    </>
  )
}

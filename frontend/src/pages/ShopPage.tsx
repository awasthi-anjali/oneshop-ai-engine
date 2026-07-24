import { useCallback, useEffect, useRef, useState, type MouseEvent } from 'react'
import {
  addBundleToCart,
  addToCart,
  dismissAbandonment,
  fetchProducts,
  getIntelligenceProfile,
  getSession,
  getStoredSessionId,
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
  type CustomerIntent,
  type NextBestAction,
  type PageContext,
  type Product,
  type RecommendationItem,
  type ShoppingNeed,
  type ShopAssistRecommendation,
} from '../api'
import AbandonmentBanner from '../components/AbandonmentBanner'
import CheckoutModal from '../components/CheckoutModal'
import NextBestActionBanner from '../components/NextBestActionBanner'
import ProductDetailModal from '../components/ProductDetailModal'
import ProductShopCard from '../components/ProductShopCard'
import RecommendationsPanel from '../components/RecommendationsPanel'
import ShopAssistDrawer from '../components/ShopAssistDrawer'
import ShopAssistFab from '../components/ShopAssistFab'
import { useCartAbandonmentTracking } from '../hooks/useCartAbandonment'
import './ShopPage.css'

const EMPTY_NEED: ShoppingNeed = {
  categories: [],
  use_cases: [],
  must_haves: [],
  nice_to_haves: [],
}

export default function ShopPage() {
  const [products, setProducts] = useState<Product[]>([])
  const [sessionId, setSessionId] = useState<string | null>(getStoredSessionId())
  const [wishlistIds, setWishlistIds] = useState<Set<string>>(new Set())
  const [cartIds, setCartIds] = useState<Set<string>>(new Set())
  const [viewedIds, setViewedIds] = useState<Set<string>>(new Set())
  const [cartProducts, setCartProducts] = useState<Product[]>([])
  const [recommendations, setRecommendations] = useState<RecommendationItem[]>([])
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
      const profile = await getIntelligenceProfile(sid)
      setSessionId(profile.session_id)
      setRecommendations(profile.recommendations)
      setIntent(profile.intent)
      setAiPowered(profile.ai_powered)
      setNbaActions(profile.next_actions)
      setNbaStage(profile.funnel_stage)
      setNbaAi(profile.ai_powered)
      setCartProducts(profile.cart)
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
  }, [])

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
    const session = await trackProductView(product.id, sessionId)
    applySession({ ...session, cart: session.cart })
    await refreshIntelligence(session.session_id)
  }

  const handleToggleWishlist = async (productId: string) => {
    const session = await toggleWishlist(productId, sessionId)
    applySession({ ...session, cart: session.cart })
    await refreshIntelligence(session.session_id)
  }

  const handleAddToCart = async (productId: string) => {
    const session = await addToCart(productId, sessionId)
    applySession({ ...session, cart: session.cart })
    await refreshIntelligence(session.session_id)
  }

  const handleRemoveFromCart = async (productId: string) => {
    const session = await removeFromCart(productId, sessionId)
    applySession({ ...session, cart: session.cart })
    await refreshIntelligence(session.session_id)
  }

  const handleAddBundle = async (productIds: string[]) => {
    const session = await addBundleToCart(productIds, sessionId)
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
      const response = await sendMessage(text, sessionId, assistContext ?? {
        surface: 'catalog',
        entry_point: 'help_me_choose',
        visible_product_ids: products.slice(0, 20).map((product) => product.id),
      })
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
  }, [assistContext, assistLoading, draft, products, sessionId])

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
  const allFiltered = filter === 'all' ? products : products.filter((product) => product.category === filter)
  const pickItems = assistRecommendations.filter((item) =>
    filter === 'all' ? true : item.product.category === filter
  )

  if (loading) return <div className="shop-loading">Loading OneShop…</div>

  return (
    <>
      <div className="shop-layout">
        <section className="shop-main">
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

          <div className="shop-grid">
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
                  />
                ))}
          </div>
        </section>

        <RecommendationsPanel
          intent={intent}
          recommendations={recommendations}
          wishlistCount={wishlistIds.size}
          cartCount={cartIds.size}
          viewedCount={viewedIds.size}
          loading={recLoading}
          aiPowered={aiPowered}
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
    </>
  )
}

import { useCallback, useEffect, useState } from 'react'
import {
  addBundleToCart,
  addToCart,
  dismissAbandonment,
  fetchProducts,
  getIntelligenceProfile,
  getSession,
  getStoredSessionId,
  ensureSessionId,
  removeFromCart,
  toggleWishlist,
  trackProductView,
  type AbandonmentStatus,
  type BundleSuggestion,
  type CheckoutResponse,
  type CustomerIntent,
  type NextBestAction,
  type Product,
  type RecommendationItem,
  type Channel,
} from '../api'
import AbandonmentBanner from '../components/AbandonmentBanner'
import CheckoutModal from '../components/CheckoutModal'
import NextBestActionBanner from '../components/NextBestActionBanner'
import OmnichannelSyncBanner from '../components/OmnichannelSyncBanner'
import ProductDetailModal from '../components/ProductDetailModal'
import ProductShopCard from '../components/ProductShopCard'
import RecommendationsPanel from '../components/RecommendationsPanel'
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

export default function ShopPage({
  channel = 'oneshop',
  layout = 'desktop',
  onAskAssistant,
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
  const [filter, setFilter] = useState<string>('all')
  const [recommendationPipeline, setRecommendationPipeline] = useState<string>('rules')
  const [retrievalMethod, setRetrievalMethod] = useState<string>('none')
  const [retrievalQuery, setRetrievalQuery] = useState<string>('')
  const [syncMessage, setSyncMessage] = useState('')
  const [channelsUsed, setChannelsUsed] = useState<string[]>([])

  useCartAbandonmentTracking(cartIds.size, sessionId)

  const applySession = (session: {
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
  }

  const refreshIntelligence = useCallback(async (sid: string | null) => {
    setRecLoading(true)
    try {
      const profile = await getIntelligenceProfile(sid, channel)
      setSessionId(profile.session_id)
      setRecommendations(profile.recommendations)
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
        const [prods, session] = await Promise.all([
          fetchProducts(),
          getSession(sessionId),
        ])
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

  const handleNbaClick = (label: string) => {
    if (label.toLowerCase().includes('checkout')) {
      setShowCheckout(true)
    } else if (onAskAssistant) {
      onAskAssistant(label)
    }
  }

  const categories = ['all', ...Array.from(new Set(products.map((p) => p.category)))]
  const filtered =
    filter === 'all' ? products : products.filter((p) => p.category === filter)

  if (loading) {
    return <div className="shop-loading">Loading OneShop…</div>
  }

  return (
    <>
      <div className={`shop-layout ${layout}`}>
        <section className="shop-main">
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

          <div className="shop-toolbar">
            <h2>All Products</h2>
            <div className="shop-filters">
              {categories.map((cat) => (
                <button
                  key={cat}
                  className={`filter-btn ${filter === cat ? 'active' : ''}`}
                  onClick={() => setFilter(cat)}
                >
                  {cat === 'all' ? 'All' : cat}
                </button>
              ))}
            </div>
          </div>

          <div className="shop-grid">
            {filtered.map((product) => (
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
          recommendationPipeline={recommendationPipeline}
          retrievalMethod={retrievalMethod}
          retrievalQuery={retrievalQuery}
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

      <ProductDetailModal
        product={selectedProduct}
        isWishlisted={selectedProduct ? wishlistIds.has(selectedProduct.id) : false}
        isInCart={selectedProduct ? cartIds.has(selectedProduct.id) : false}
        onClose={() => setSelectedProduct(null)}
        onToggleWishlist={handleToggleWishlist}
        onAddToCart={handleAddToCart}
        onRemoveFromCart={handleRemoveFromCart}
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

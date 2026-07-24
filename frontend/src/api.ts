export interface Product {
  id: string
  name: string
  category: string
  brand: string
  price: number
  description: string
  features: string[]
  specs: Record<string, unknown>
  image_url: string
  rating: number
  in_stock: boolean
  tags: string[]
}

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  products?: Product[]
  comparison?: Product[]
}

export interface ChatResponse {
  session_id: string
  message: {
    role: string
    content: string
    products: Product[]
    comparison: Product[] | null
  }
  suggested_actions: string[]
  cart_updated: boolean
  open_checkout: boolean
}

export interface CustomerIntent {
  categories: string[]
  brands: string[]
  tags: string[]
  price_min: number | null
  price_max: number | null
  price_avg: number | null
  summary: string
  funnel_stage?: string
  ecosystem?: string
  purchase_readiness?: string
}

export interface RecommendationItem {
  product: Product
  score: number
  reason: string
  source?: 'ai' | 'semantic_backup' | 'rules'
}

export interface RecommendationsResponse {
  session_id: string
  intent: CustomerIntent
  recommendations: RecommendationItem[]
  ai_powered: boolean
}

export interface NextBestAction {
  action: string
  label: string
  priority: number
}

export interface NextBestActionResponse {
  session_id: string
  funnel_stage: string
  actions: NextBestAction[]
  ai_powered: boolean
}

export interface BundleSuggestion {
  name: string
  products: Product[]
  product_ids: string[]
  total_price: number
  savings: number
  reason: string
}

export interface SmartCartResponse {
  session_id: string
  cart: Product[]
  bundles: BundleSuggestion[]
  nudge: string
  checkout_tip: string
  ai_powered: boolean
  subtotal: number
  estimated_savings: number
}

export interface CheckoutResponse {
  session_id: string
  order_id: string
  items: Product[]
  subtotal: number
  savings: number
  discount: number
  total: number
  message: string
}

export interface AbandonmentStatus {
  session_id: string
  is_abandoned: boolean
  recovery_message: string
  discount_offer: number
  cart_count: number
}

export interface IntelligenceProfile {
  session_id: string
  intent: CustomerIntent
  recommendations: RecommendationItem[]
  next_actions: NextBestAction[]
  funnel_stage: string
  cart: Product[]
  bundles: BundleSuggestion[]
  nudge: string
  checkout_tip: string
  subtotal: number
  estimated_savings: number
  ai_powered: boolean
  abandonment: AbandonmentStatus | null
  recommendation_pipeline?: 'ai_validated' | 'semantic_backup' | 'rules'
  retrieval_method?: 'embeddings' | 'keyword' | 'none'
  retrieved_product_ids?: string[]
  retrieval_query?: string
  current_channel?: string
  channels_used?: string[]
  is_cross_channel?: boolean
  sync_message?: string
  customer_id?: string | null
  continue_url_web?: string
  continue_url_app?: string
}

export interface OmnichannelContext {
  session_id: string
  customer_id: string | null
  current_channel: string
  last_channel: string
  channels_used: string[]
  is_cross_channel: boolean
  other_channel: string | null
  other_channel_label: string
  sync_message: string
  cart_count: number
  wishlist_count: number
  viewed_count: number
  continue_url_web: string
  continue_url_app: string
  funnel_stage: string
}

export interface SessionState {
  session_id: string
  wishlist: Product[]
  cart: Product[]
  viewed: Product[]
  wishlist_ids: string[]
  cart_ids: string[]
  viewed_ids: string[]
}

const API_BASE = '/api'
const SESSION_KEY = 'oneshop_session_id'
const CHANNEL_KEY = 'oneshop_channel'
const SYNC_TICK_KEY = 'oneshop_sync_tick'
const SYNC_BC = 'oneshop-omni-sync'

export type Channel = 'oneshop' | 'oneapp'

/** Create or reuse one session id before any API call (shared across tabs). */
export function ensureSessionId(): string {
  const fromUrl = initSessionFromUrl()
  if (fromUrl) return fromUrl
  const existing = localStorage.getItem(SESSION_KEY)
  if (existing) return existing
  const sid = crypto.randomUUID()
  storeSessionId(sid)
  return sid
}

/** Tell other tabs to refresh cart / recommendations. */
export function notifySessionSync() {
  localStorage.setItem(SYNC_TICK_KEY, String(Date.now()))
  try {
    new BroadcastChannel(SYNC_BC).postMessage('refresh')
  } catch {
    /* BroadcastChannel unsupported */
  }
}

export function onSessionSync(callback: () => void): () => void {
  const onStorage = (e: StorageEvent) => {
    if (e.key === SESSION_KEY || e.key === SYNC_TICK_KEY) callback()
  }
  const onVisible = () => {
    if (document.visibilityState === 'visible') callback()
  }
  let bc: BroadcastChannel | null = null
  try {
    bc = new BroadcastChannel(SYNC_BC)
    bc.onmessage = () => callback()
  } catch {
    /* ignore */
  }
  window.addEventListener('storage', onStorage)
  document.addEventListener('visibilitychange', onVisible)
  return () => {
    window.removeEventListener('storage', onStorage)
    document.removeEventListener('visibilitychange', onVisible)
    bc?.close()
  }
}

export function getChannel(): Channel {
  const c = localStorage.getItem(CHANNEL_KEY)
  return c === 'oneapp' ? 'oneapp' : 'oneshop'
}

export function setChannel(channel: Channel) {
  localStorage.setItem(CHANNEL_KEY, channel)
}

/** Adopt session_id from ?session_id= URL (cross-device continue link). */
export function initSessionFromUrl(): string | null {
  const params = new URLSearchParams(window.location.search)
  const sid = params.get('session_id')
  if (sid) {
    storeSessionId(sid)
    return sid
  }
  return null
}

export function getStoredSessionId(): string | null {
  return localStorage.getItem(SESSION_KEY)
}

export function storeSessionId(id: string) {
  const prev = localStorage.getItem(SESSION_KEY)
  localStorage.setItem(SESSION_KEY, id)
  if (prev && prev !== id) notifySessionSync()
}

export async function fetchProducts(): Promise<Product[]> {
  const res = await fetch(`${API_BASE}/products?limit=50`)
  if (!res.ok) throw new Error('Failed to load products')
  return res.json()
}

export async function getSession(sessionId: string | null): Promise<SessionState> {
  const params = sessionId ? `?session_id=${sessionId}` : ''
  const res = await fetch(`${API_BASE}/customer/session${params}`)
  if (!res.ok) throw new Error('Failed to load session')
  const data: SessionState = await res.json()
  storeSessionId(data.session_id)
  return data
}

async function sessionMutation(res: Response): Promise<SessionState> {
  if (!res.ok) throw new Error('Session update failed')
  const data: SessionState = await res.json()
  storeSessionId(data.session_id)
  notifySessionSync()
  return data
}

export async function trackProductView(
  productId: string,
  sessionId: string | null,
  channel: Channel = getChannel()
): Promise<SessionState> {
  const res = await fetch(`${API_BASE}/customer/view`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, product_id: productId, channel }),
  })
  if (!res.ok) throw new Error('Failed to track view')
  return sessionMutation(res)
}

export async function toggleWishlist(
  productId: string,
  sessionId: string | null,
  channel: Channel = getChannel()
): Promise<SessionState> {
  const res = await fetch(`${API_BASE}/customer/wishlist/toggle`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, product_id: productId, channel }),
  })
  if (!res.ok) throw new Error('Failed to update wishlist')
  return sessionMutation(res)
}

export async function addToCart(
  productId: string,
  sessionId: string | null,
  channel: Channel = getChannel()
): Promise<SessionState> {
  const res = await fetch(`${API_BASE}/customer/cart/add`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, product_id: productId, channel }),
  })
  if (!res.ok) throw new Error('Failed to add to cart')
  return sessionMutation(res)
}

export async function removeFromCart(
  productId: string,
  sessionId: string | null,
  channel: Channel = getChannel()
): Promise<SessionState> {
  const res = await fetch(`${API_BASE}/customer/cart/remove`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, product_id: productId, channel }),
  })
  if (!res.ok) throw new Error('Failed to remove from cart')
  return sessionMutation(res)
}

export async function getIntelligenceProfile(
  sessionId: string | null,
  channel: Channel = getChannel()
): Promise<IntelligenceProfile> {
  const params = new URLSearchParams()
  if (sessionId) params.set('session_id', sessionId)
  params.set('channel', channel)
  const res = await fetch(`${API_BASE}/intelligence/profile?${params}`)
  if (!res.ok) throw new Error('Failed to load intelligence profile')
  const data: IntelligenceProfile = await res.json()
  storeSessionId(data.session_id)
  return data
}

export async function getRecommendations(
  sessionId: string | null
): Promise<RecommendationsResponse> {
  const params = sessionId ? `?session_id=${sessionId}` : ''
  const res = await fetch(`${API_BASE}/discovery/recommend${params}`)
  if (!res.ok) throw new Error('Failed to load recommendations')
  const data: RecommendationsResponse = await res.json()
  storeSessionId(data.session_id)
  return data
}

export async function getNextBestActions(
  sessionId: string | null
): Promise<NextBestActionResponse> {
  const params = sessionId ? `?session_id=${sessionId}` : ''
  const res = await fetch(`${API_BASE}/intelligence/next-best-action${params}`)
  if (!res.ok) throw new Error('Failed to load next best actions')
  const data: NextBestActionResponse = await res.json()
  storeSessionId(data.session_id)
  return data
}

export async function getSmartCart(
  sessionId: string | null
): Promise<SmartCartResponse> {
  const params = sessionId ? `?session_id=${sessionId}` : ''
  const res = await fetch(`${API_BASE}/intelligence/smart-cart${params}`)
  if (!res.ok) throw new Error('Failed to load smart cart')
  const data: SmartCartResponse = await res.json()
  storeSessionId(data.session_id)
  return data
}

export async function addBundleToCart(
  productIds: string[],
  sessionId: string | null,
  channel: Channel = getChannel()
): Promise<SessionState> {
  const res = await fetch(`${API_BASE}/customer/cart/add-bundle`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, product_ids: productIds, channel }),
  })
  if (!res.ok) throw new Error('Failed to add bundle')
  return sessionMutation(res)
}

export async function completeCheckout(
  sessionId: string | null,
  customerName: string,
  email: string,
  paymentLast4: string
): Promise<CheckoutResponse> {
  const res = await fetch(`${API_BASE}/checkout/complete`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      session_id: sessionId,
      customer_name: customerName,
      email,
      payment_last4: paymentLast4,
    }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || 'Checkout failed')
  }
  const data: CheckoutResponse = await res.json()
  storeSessionId(data.session_id)
  return data
}

export async function getAbandonmentStatus(
  sessionId: string | null
): Promise<AbandonmentStatus> {
  const params = sessionId ? `?session_id=${sessionId}` : ''
  const res = await fetch(`${API_BASE}/checkout/abandonment-status${params}`)
  if (!res.ok) throw new Error('Failed to check abandonment')
  const data: AbandonmentStatus = await res.json()
  storeSessionId(data.session_id)
  return data
}

export async function markCartAbandoned(sessionId: string | null): Promise<void> {
  const params = sessionId ? `?session_id=${sessionId}` : ''
  await fetch(`${API_BASE}/checkout/abandon${params}`, { method: 'POST' })
}

export async function dismissAbandonment(sessionId: string | null): Promise<void> {
  const params = sessionId ? `?session_id=${sessionId}` : ''
  await fetch(`${API_BASE}/checkout/dismiss-abandonment${params}`, { method: 'POST' })
}

export async function sendMessage(
  message: string,
  sessionId: string | null,
  channel: Channel = getChannel()
): Promise<ChatResponse> {
  const res = await fetch(`${API_BASE}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, session_id: sessionId, channel }),
  })
  if (!res.ok) throw new Error('Failed to send message')
  const data: ChatResponse = await res.json()
  storeSessionId(data.session_id)
  if (data.cart_updated || data.open_checkout) {
    notifySessionSync()
  }
  return data
}

export async function getHealth(): Promise<{ llm_enabled: boolean; mode: string }> {
  const res = await fetch(`${API_BASE}/health`)
  return res.json()
}

export async function getOmnichannelContext(
  sessionId: string | null,
  channel: Channel = getChannel()
): Promise<OmnichannelContext> {
  const params = new URLSearchParams({ channel })
  if (sessionId) params.set('session_id', sessionId)
  const res = await fetch(`${API_BASE}/omnichannel/context?${params}`)
  if (!res.ok) throw new Error('Failed to load omnichannel context')
  const data: OmnichannelContext = await res.json()
  storeSessionId(data.session_id)
  return data
}

export async function linkCustomer(
  customerId: string,
  sessionId: string | null
): Promise<{ session_id: string; customer_id: string; message: string }> {
  const res = await fetch(`${API_BASE}/omnichannel/link`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ customer_id: customerId, session_id: sessionId }),
  })
  if (!res.ok) throw new Error('Failed to link customer')
  const data = await res.json()
  storeSessionId(data.session_id)
  return data
}

export async function getContinueUrl(
  sessionId: string | null,
  target: Channel
): Promise<{ continue_url: string; session_id: string }> {
  const params = new URLSearchParams({ target })
  if (sessionId) params.set('session_id', sessionId)
  const res = await fetch(`${API_BASE}/omnichannel/continue?${params}`)
  if (!res.ok) throw new Error('Failed to get continue URL')
  const data = await res.json()
  storeSessionId(data.session_id)
  return data
}

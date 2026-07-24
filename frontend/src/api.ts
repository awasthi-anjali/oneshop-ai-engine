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

export function getStoredSessionId(): string | null {
  return localStorage.getItem(SESSION_KEY)
}

export function storeSessionId(id: string) {
  localStorage.setItem(SESSION_KEY, id)
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

export async function trackProductView(
  productId: string,
  sessionId: string | null
): Promise<SessionState> {
  const res = await fetch(`${API_BASE}/customer/view`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, product_id: productId }),
  })
  if (!res.ok) throw new Error('Failed to track view')
  const data: SessionState = await res.json()
  storeSessionId(data.session_id)
  return data
}

export async function toggleWishlist(
  productId: string,
  sessionId: string | null
): Promise<SessionState> {
  const res = await fetch(`${API_BASE}/customer/wishlist/toggle`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, product_id: productId }),
  })
  if (!res.ok) throw new Error('Failed to update wishlist')
  const data: SessionState = await res.json()
  storeSessionId(data.session_id)
  return data
}

export async function addToCart(
  productId: string,
  sessionId: string | null
): Promise<SessionState> {
  const res = await fetch(`${API_BASE}/customer/cart/add`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, product_id: productId }),
  })
  if (!res.ok) throw new Error('Failed to add to cart')
  const data: SessionState = await res.json()
  storeSessionId(data.session_id)
  return data
}

export async function removeFromCart(
  productId: string,
  sessionId: string | null
): Promise<SessionState> {
  const res = await fetch(`${API_BASE}/customer/cart/remove`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, product_id: productId }),
  })
  if (!res.ok) throw new Error('Failed to remove from cart')
  const data: SessionState = await res.json()
  storeSessionId(data.session_id)
  return data
}

export async function getIntelligenceProfile(
  sessionId: string | null
): Promise<IntelligenceProfile> {
  const params = sessionId ? `?session_id=${sessionId}` : ''
  const res = await fetch(`${API_BASE}/intelligence/profile${params}`)
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
  sessionId: string | null
): Promise<SessionState> {
  const res = await fetch(`${API_BASE}/customer/cart/add-bundle`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, product_ids: productIds }),
  })
  if (!res.ok) throw new Error('Failed to add bundle')
  const data: SessionState = await res.json()
  storeSessionId(data.session_id)
  return data
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
  channel = 'oneshop'
): Promise<ChatResponse> {
  const res = await fetch(`${API_BASE}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, session_id: sessionId, channel }),
  })
  if (!res.ok) throw new Error('Failed to send message')
  return res.json()
}

export async function getHealth(): Promise<{ llm_enabled: boolean; mode: string }> {
  const res = await fetch(`${API_BASE}/chat/health`)
  return res.json()
}

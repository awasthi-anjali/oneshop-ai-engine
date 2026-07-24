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
  currency?: string
  billing_period?: 'one_time' | 'monthly'
}

export interface ChatMessage {
  id?: string
  role: 'user' | 'assistant'
  content: string
  products?: Product[]
  comparison?: Product[]
  status?: ChatStatus
  mode?: 'ai' | 'fallback'
  actions?: ChatAction[]
}

export type ChatStatus =
  | 'clarifying'
  | 'recommended'
  | 'no_match'
  | 'unsupported'
  | 'service_handoff'
  | 'error'

export interface ShoppingNeed {
  categories: string[]
  use_cases: string[]
  device_budget_max?: number | null
  monthly_budget_max?: number | null
  platform?: string | null
  roaming_required?: boolean | null
  lines?: number | null
  must_haves: string[]
  nice_to_haves: string[]
}

export type ChatActionType =
  | 'REFINE'
  | 'COMPARE'
  | 'OPEN_PRODUCT'
  | 'VIEW_CART'
  | 'PROPOSE_ADD_TO_CART'
  | 'PROPOSE_ADD_BUNDLE'
  | 'HANDOFF_SERVICE'

export interface ChatAction {
  type: ChatActionType
  label: string
  product_ids: string[]
  proposal_id?: string | null
}

export interface CartSummary {
  items: Product[]
  total_items: number
  one_time_total: number
  monthly_total: number
}

export interface CartProposal {
  proposal_id: string
  products: Product[]
  product_ids: string[]
  excluded_product_ids: string[]
  one_time_total: number
  monthly_total: number
}

export interface CartConfirmationResponse {
  session_id: string
  proposal_id: string
  added_product_ids: string[]
  excluded_product_ids: string[]
  idempotent_replay: boolean
  cart_summary: CartSummary
}

export interface ShopAssistRecommendation {
  product: Product
  slot: 'primary_phone' | 'alternative_phone' | 'recommended_plan'
  reason_codes: string[]
  reason: string
}

export interface PageContext {
  surface: 'catalog' | 'product' | 'cart'
  entry_point: 'help_me_choose' | 'product_detail' | 'next_best_action' | 'cart'
  product_id?: string
  visible_product_ids?: string[]
}

export interface ChatResponse {
  session_id: string
  status: ChatStatus
  message: string
  need_profile: ShoppingNeed
  recommendations: ShopAssistRecommendation[]
  comparison?: Product[] | { products?: Product[] } | null
  actions: ChatAction[]
  mode: 'ai' | 'fallback'
  suggested_actions: string[]
  cart_updated: false
  open_checkout: false
  selected_tool?: string | null
  cart_summary?: CartSummary | null
  cart_proposal?: CartProposal | null
}

interface LegacyChatResponse {
  session_id: string
  message: {
    role: string
    content: string
    products: Product[]
    comparison: Product[] | null
  }
  suggested_actions: string[]
  cart_updated: false
  open_checkout: false
}

interface WireV1ChatResponse {
  session_id: string
  status: ChatStatus
  message:
    | string
    | {
        role: string
        content: string
        products?: Product[]
        comparison?: Product[] | null
      }
  need_profile: ShoppingNeed
  recommendations: ShopAssistRecommendation[]
  comparison?: Product[] | null
  actions: ChatAction[]
  mode: 'ai' | 'fallback'
  suggested_actions?: string[]
  cart_updated: boolean
  open_checkout: boolean
  selected_tool?: string | null
  cart_summary?: CartSummary | null
  cart_proposal?: CartProposal | null
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

export interface PersonalizedScoreBreakdown {
  [component: string]: number
}

export interface PersonalizedProfile {
  user_id: string
  brand_affinity: Record<string, number>
  category_affinity: Record<string, number>
  price_centroid: number | null
  recent_views: string[]
  cart_products: string[]
  wishlist_products: string[]
  channels_used: string[]
  last_active_channel: string | null
  interaction_counts: Record<string, number>
  total_interactions: number
  cold_start?: boolean
}

export interface PersonalizedRecommendation {
  product: Product
  score: number
  explanation: string
  reason_codes: string[]
  score_breakdown: PersonalizedScoreBreakdown
}

export interface PersonalizedRecommendationsResponse {
  user_id: string
  session_id?: string
  channel: Channel
  context: string
  profile_version: number | string
  profile: PersonalizedProfile
  recommendations: PersonalizedRecommendation[]
}

export type InteractionEventType =
  | 'product_view'
  | 'wishlist_add'
  | 'wishlist_remove'
  | 'cart_add'
  | 'cart_remove'
  | 'impression'
  | 'rec_click'

export interface RecommendationEventMetadata {
  query?: string
  intent?: string
  rec_position?: number
  rec_type?: string
  surface?: string
  visible?: boolean
}

export interface InteractionEvent {
  event_id: string
  user_id: string
  event_type: InteractionEventType
  product_id?: string
  channel: Channel
  session_id: string | null
  metadata: RecommendationEventMetadata
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
const PERSONALIZATION_USER_KEY = 'oneshop_personalization_user'
const PERSONALIZATION_EVENT = 'oneshop-personalization-user'

export type Channel = 'oneshop' | 'oneapp'

export const DEMO_USERS = [
  { id: 'user_001', name: 'Alex', description: 'Budget student', emoji: '🎓' },
  { id: 'user_011', name: 'Dev', description: 'Tech enthusiast', emoji: '🚀' },
  { id: 'user_021', name: 'Morgan', description: 'Business pro', emoji: '💼' },
  { id: 'user_031', name: 'Greta', description: 'Senior', emoji: '🌿' },
  { id: 'user_041', name: 'Chris', description: 'Family parent', emoji: '👨‍👩‍👧' },
] as const

export function getPersonalizationUserId(): string {
  const stored = localStorage.getItem(PERSONALIZATION_USER_KEY)
  return DEMO_USERS.some((user) => user.id === stored) ? stored! : DEMO_USERS[0].id
}

export function setPersonalizationUserId(userId: string) {
  if (!DEMO_USERS.some((user) => user.id === userId)) return
  localStorage.setItem(PERSONALIZATION_USER_KEY, userId)
  window.dispatchEvent(new CustomEvent(PERSONALIZATION_EVENT, { detail: userId }))
  notifySessionSync()
}

export function onPersonalizationUserChange(callback: (userId: string) => void) {
  const onCustom = (event: Event) => callback((event as CustomEvent<string>).detail)
  const onStorage = (event: StorageEvent) => {
    if (event.key === PERSONALIZATION_USER_KEY && event.newValue) callback(event.newValue)
  }
  window.addEventListener(PERSONALIZATION_EVENT, onCustom)
  window.addEventListener('storage', onStorage)
  return () => {
    window.removeEventListener(PERSONALIZATION_EVENT, onCustom)
    window.removeEventListener('storage', onStorage)
  }
}

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

export interface ProductSearchParams {
  query?: string
  category?: string
  max_price?: number
  min_price?: number
  brand?: string
  limit?: number
  include_meta?: boolean
}

export type ProductSearchMethod = 'name' | 'embeddings' | 'keyword'

export interface ProductSearchResult {
  products: Product[]
  search_method: ProductSearchMethod
}

export async function fetchProducts(params: ProductSearchParams = {}): Promise<Product[]> {
  const result = await fetchProductsWithMeta(params)
  return result.products
}

export async function fetchProductsWithMeta(
  params: ProductSearchParams = {}
): Promise<ProductSearchResult> {
  const searchParams = new URLSearchParams()
  searchParams.set('limit', String(params.limit ?? 50))
  if (params.query?.trim()) searchParams.set('query', params.query.trim())
  if (params.category) searchParams.set('category', params.category)
  if (params.max_price != null) searchParams.set('max_price', String(params.max_price))
  if (params.min_price != null) searchParams.set('min_price', String(params.min_price))
  if (params.brand?.trim()) searchParams.set('brand', params.brand.trim())
  if (params.include_meta !== false) searchParams.set('include_meta', 'true')

  const res = await fetch(`${API_BASE}/products?${searchParams}`)
  if (!res.ok) throw new Error('Failed to load products')

  const data = await res.json()
  if (Array.isArray(data)) {
    return { products: data, search_method: 'name' }
  }
  return {
    products: data.products ?? [],
    search_method: data.search_method ?? 'name',
  }
}

export async function compareProducts(productIds: string[]): Promise<Product[]> {
  const res = await fetch(`${API_BASE}/products/compare`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ product_ids: productIds }),
  })
  if (!res.ok) throw new Error('Failed to compare products')
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

export async function confirmShopAssistCartProposal(
  proposalId: string,
  idempotencyKey: string,
  sessionId: string,
  userId: string,
  channel: Channel = getChannel()
): Promise<CartConfirmationResponse> {
  const res = await fetch(`${API_BASE}/chat/cart/confirm`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      proposal_id: proposalId,
      idempotency_key: idempotencyKey,
      session_id: sessionId,
      user_id: userId,
      channel,
    }),
  })
  if (!res.ok) {
    const detail = await res.json().catch(() => null)
    throw new Error(
      typeof detail?.detail === 'string'
        ? detail.detail
        : 'The cart proposal could not be confirmed.'
    )
  }
  const data: CartConfirmationResponse = await res.json()
  storeSessionId(data.session_id)
  notifySessionSync()
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
  pageContext?: PageContext,
  channel: Channel = getChannel(),
  userId: string = getPersonalizationUserId(),
  personalizationContext?: {
    preferred_brands: string[]
    preferred_categories: string[]
    price_centroid: number | null
    interaction_count: number
  }
): Promise<ChatResponse> {
  const res = await fetch(`${API_BASE}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      message,
      session_id: sessionId,
      channel,
      user_id: userId,
      personalization_context: personalizationContext,
      page_context: pageContext,
    }),
  })
  if (!res.ok) {
    const detail = await res.json().catch(() => null)
    throw new Error(
      typeof detail?.detail === 'string'
        ? detail.detail
        : 'ShopAssist could not respond. Please try again.'
    )
  }
  const raw = (await res.json()) as WireV1ChatResponse | LegacyChatResponse
  if ('status' in raw) {
    const data: ChatResponse = {
      session_id: raw.session_id,
      status: raw.status,
      message: typeof raw.message === 'string' ? raw.message : raw.message.content,
      need_profile: raw.need_profile,
      recommendations: raw.recommendations.slice(0, 3),
      comparison:
        raw.comparison ??
        (typeof raw.message === 'string' ? null : raw.message.comparison) ??
        null,
      actions: raw.actions,
      mode: raw.mode,
      suggested_actions: raw.suggested_actions ?? [],
      cart_updated: false,
      open_checkout: false,
      selected_tool: raw.selected_tool,
      cart_summary: raw.cart_summary,
      cart_proposal: raw.cart_proposal,
    }
    storeSessionId(data.session_id)
    return data
  }

  const legacy = raw as LegacyChatResponse
  const products = legacy.message.products ?? []
  const data: ChatResponse = {
    session_id: legacy.session_id,
    status: products.length > 0 ? 'recommended' : 'clarifying',
    message: legacy.message.content,
    need_profile: {
      categories: [],
      use_cases: [],
      must_haves: [],
      nice_to_haves: [],
    },
    recommendations: products.slice(0, 3).map((product, index) => ({
      product,
      slot:
        product.category === 'plan'
          ? 'recommended_plan'
          : index === 0
            ? 'primary_phone'
            : 'alternative_phone',
      reason_codes: [],
      reason: 'Recommended from the demo catalog.',
    })),
    comparison: legacy.message.comparison,
    actions: [],
    mode: 'fallback',
    suggested_actions: legacy.suggested_actions ?? [],
    cart_updated: false,
    open_checkout: false,
  }
  storeSessionId(data.session_id)
  return data
}

function normalizePersonalizedResponse(
  raw: Partial<PersonalizedRecommendationsResponse>,
  userId: string,
  channel: Channel,
  context: string
): PersonalizedRecommendationsResponse {
  const profile = raw.profile ?? ({} as PersonalizedProfile)
  const priceSignal = (profile as unknown as {
    price_signal?: { centroid?: number } | number
  }).price_signal
  return {
    user_id: raw.user_id ?? userId,
    session_id: raw.session_id,
    channel: raw.channel ?? channel,
    context: raw.context ?? context,
    profile_version: raw.profile_version ?? (raw as unknown as { version?: number | string }).version ?? 0,
    profile: {
      user_id: profile.user_id ?? userId,
      brand_affinity: profile.brand_affinity ?? {},
      category_affinity: profile.category_affinity ?? {},
      price_centroid:
        profile.price_centroid ??
        (typeof priceSignal === 'number' ? priceSignal : priceSignal?.centroid ?? null),
      recent_views: profile.recent_views ?? [],
      cart_products: profile.cart_products ?? (profile as unknown as { cart_exclusions?: string[] }).cart_exclusions ?? [],
      wishlist_products: profile.wishlist_products ?? (profile as unknown as { wishlist_exclusions?: string[] }).wishlist_exclusions ?? [],
      channels_used: profile.channels_used ?? (profile as unknown as { channels?: string[] }).channels ?? [],
      last_active_channel: profile.last_active_channel ?? null,
      interaction_counts: profile.interaction_counts ?? {},
      total_interactions: profile.total_interactions ?? 0,
      cold_start: profile.cold_start ?? false,
    },
    recommendations: (raw.recommendations ?? []).map((item) => ({
      ...item,
      score: Number(item.score ?? 0),
      explanation: item.explanation || (item as unknown as { reason?: string }).reason || 'Ranked from recorded interactions.',
      reason_codes: item.reason_codes ?? [],
      score_breakdown: item.score_breakdown ?? {},
    })),
  }
}

export async function getPersonalizedRecommendations(
  userId: string,
  sessionId: string | null,
  channel: Channel,
  context = 'general',
  topK = 6
): Promise<PersonalizedRecommendationsResponse> {
  const params = new URLSearchParams({ channel, query: context, limit: String(topK) })
  if (sessionId) params.set('session_id', sessionId)
  const res = await fetch(`${API_BASE}/recommendations/${encodeURIComponent(userId)}?${params}`)
  if (!res.ok) throw new Error('Personalized recommendations are temporarily unavailable.')
  return normalizePersonalizedResponse(await res.json(), userId, channel, context)
}

export function subscribeToPersonalizedRecommendations(
  userId: string,
  sessionId: string | null,
  channel: Channel,
  context: string,
  topK: number,
  onUpdate: (response: PersonalizedRecommendationsResponse) => void,
  onError: () => void
): () => void {
  let stopped = false
  let version: number | string = 0
  let timer: number | undefined
  const poll = async () => {
    const params = new URLSearchParams({
      channel,
      query: context,
      limit: String(topK),
      after_version: String(version),
    })
    if (sessionId) params.set('session_id', sessionId)
    try {
      const res = await fetch(
        `${API_BASE}/recommendations/${encodeURIComponent(userId)}/updates?${params}`
      )
      if (!res.ok) throw new Error('update unavailable')
      if (res.status === 204) return
      const raw = await res.json()
      if (raw?.changed === false) {
        version = raw.version ?? version
        return
      }
      if (raw && raw.recommendations) {
        const normalized = normalizePersonalizedResponse(raw, userId, channel, context)
        version = normalized.profile_version
        onUpdate(normalized)
      }
    } catch {
      onError()
    } finally {
      if (!stopped) timer = window.setTimeout(poll, 2000)
    }
  }
  void poll()
  return () => {
    stopped = true
    if (timer !== undefined) window.clearTimeout(timer)
  }
}

export async function trackInteraction(event: Omit<InteractionEvent, 'event_id'> & { event_id?: string }) {
  const payload: InteractionEvent = { ...event, event_id: event.event_id ?? crypto.randomUUID() }
  const res = await fetch(`${API_BASE}/recommendations/interactions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) throw new Error('Interaction tracking failed')
  return res.json() as Promise<{ status: string; event_id: string; profile_version?: number | string }>
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

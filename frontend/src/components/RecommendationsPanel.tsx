import type {
  BundleSuggestion,
  CrossSellItem,
  CustomerIntent,
  PersonalizedProfile,
  PersonalizedRecommendation,
  Product,
} from '../api'
import SmartCartPanel from './SmartCartPanel'
import './RecommendationsPanel.css'

interface Props {
  intent: CustomerIntent | null
  recommendations: PersonalizedRecommendation[]
  profile: PersonalizedProfile | null
  profileVersion: number | string
  streamStatus: 'connecting' | 'live' | 'fallback' | 'error'
  wishlistCount: number
  cartCount: number
  viewedCount: number
  loading: boolean
  aiPowered: boolean
  recommendationPipeline?: string
  retrievalMethod?: string
  retrievalQuery?: string
  smartCart: {
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
    cartItems: Product[]
  }
  onCheckout: () => void
  onAddBundle: (productIds: string[]) => void
  onAddCrossSell: (productId: string) => void
  onRemoveFromCart: (productId: string) => void
}

export default function RecommendationsPanel({
  intent,
  recommendations,
  profile,
  profileVersion,
  streamStatus,
  wishlistCount,
  cartCount,
  viewedCount,
  loading,
  aiPowered,
  recommendationPipeline,
  retrievalMethod,
  retrievalQuery,
  smartCart,
  onCheckout,
  onAddBundle,
  onAddCrossSell,
  onRemoveFromCart,
}: Props) {
  const strongestRecommendation = recommendations[0]

  return (
    <aside className="rec-panel">
      <div className="rec-panel-header">
        <h2>Why these picks?</h2>
        <div className="rec-header-badges">
          {aiPowered && <span className="rec-ai-badge">AI Powered</span>}
          <span className={`rec-live-badge ${streamStatus}`}>
            {streamStatus === 'live' ? 'Live' : streamStatus === 'connecting' ? 'Connecting' : 'Fetch fallback'}
          </span>
          {recommendationPipeline === 'ai_validated' && (
            <span className="rec-pipeline-badge ai">AI validated</span>
          )}
          {recommendationPipeline === 'semantic_backup' && (
            <span className="rec-pipeline-badge semantic">Semantic backup</span>
          )}
          <p className="rec-subtitle">Profile v{String(profileVersion)}</p>
        </div>
      </div>

      {retrievalMethod === 'embeddings' && (
        <div className="rec-rag-banner">
          <span className="rec-rag-icon">⌖</span>
          <div>
            <strong>Semantic search active</strong>
            <p>Catalog focused via embeddings{retrievalQuery ? `: “${retrievalQuery.slice(0, 48)}…”` : ''}</p>
          </div>
        </div>
      )}

      <div className="rec-stats">
        <div className="rec-stat">
          <span className="rec-stat-num">{viewedCount}</span>
          <span className="rec-stat-label">Viewed</span>
        </div>
        <div className="rec-stat">
          <span className="rec-stat-num">{wishlistCount}</span>
          <span className="rec-stat-label">Wishlist</span>
        </div>
        <div className="rec-stat">
          <span className="rec-stat-num">{cartCount}</span>
          <span className="rec-stat-label">Cart</span>
        </div>
      </div>

      {profile && (
        <div className="profile-evidence">
          <span>{profile.total_interactions} profile events</span>
          {profile.channels_used.length > 0 && (
            <span>{profile.channels_used.join(' + ')} continuity</span>
          )}
        </div>
      )}

      {intent && (
        <div className="rec-intent">
          <span className="rec-intent-label">Current shopping intent</span>
          <p>{intent.summary}</p>
          {intent.ecosystem && <p className="rec-ecosystem">🏷 {intent.ecosystem}</p>}
          {intent.tags.length > 0 && (
            <div className="rec-tags">
              {intent.tags.map((tag) => (
                <span key={tag} className="rec-tag">{tag}</span>
              ))}
            </div>
          )}
        </div>
      )}

      <section className="ranking-evidence" aria-label="Recommendation evidence">
        {loading && recommendations.length === 0 ? (
          <p className="rec-empty">Preparing profile evidence…</p>
        ) : strongestRecommendation ? (
          <>
            <span className="ranking-evidence-label">Strongest current match</span>
            <div className="ranking-evidence-product">
              <img src={strongestRecommendation.product.image_url} alt="" />
              <div>
                <strong>{strongestRecommendation.product.name}</strong>
                <span>{Math.round(strongestRecommendation.score * 100)}% match</span>
              </div>
            </div>
            <p>{strongestRecommendation.explanation}</p>
            <div className="rec-reason-codes">
              {strongestRecommendation.reason_codes.slice(0, 3).map((code) => (
                <span key={code}>{code.replace(/_/g, ' ').toLowerCase()}</span>
              ))}
            </div>
            <details className="score-evidence">
              <summary>Show score evidence</summary>
              {Object.entries(strongestRecommendation.score_breakdown).map(([label, value]) => (
                <span key={label}>{label.replace(/_/g, ' ')}: {Math.round(value * 100)}%</span>
              ))}
            </details>
          </>
        ) : (
          <p className="rec-empty">Interact with products to build recommendation evidence.</p>
        )}
      </section>

      <SmartCartPanel
        bundles={smartCart.bundles}
        crossSell={smartCart.crossSell}
        nudge={smartCart.nudge}
        checkoutTip={smartCart.checkoutTip}
        aiPowered={smartCart.aiPowered}
        cartCount={cartCount}
        cartItems={smartCart.cartItems}
        oneTimeTotal={smartCart.oneTimeTotal}
        monthlyTotal={smartCart.monthlyTotal}
        onCheckout={onCheckout}
        onAddBundle={onAddBundle}
        onAddCrossSell={onAddCrossSell}
        onRemoveFromCart={onRemoveFromCart}
      />
    </aside>
  )
}

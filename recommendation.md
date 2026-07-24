# Feature Spec: Personalized Recommendation Engine

> **Status:** Ready for implementation  
> **Effort:** 30-45 minutes (including testing)  
> **Context:** Hackathon — build fast, test with profile switcher, move on  
> **Dependencies:** Product DB seeded (200 products), Chroma embeddings generated, User profiles seeded (50 users)

---

## What This Feature Does

Captures user behavior (clicks, searches, cart actions) and uses it to rank products differently for each user. A budget student sees mid-range phones first; a tech enthusiast sees flagships first. Same catalog, different experience.

**Approach:** Rules-based scoring for ranking, LLM only for natural language explanation.

---

## Database

### Table 1: `interactions` (raw event log)

Append-only. Every user action goes here. Never modified after insert.

```sql
CREATE TABLE interactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    product_id TEXT,
    channel TEXT DEFAULT 'web',
    session_id TEXT NOT NULL,
    metadata JSON DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_interactions_user ON interactions(user_id);
CREATE INDEX idx_interactions_user_type ON interactions(user_id, event_type);
```

**Event types to capture:**

| Event | Tracked By | Trigger | metadata example |
|-------|-----------|---------|-----------------|
| `product_view` | Frontend | User clicks product card | `{}` |
| `search_query` | Backend (MCP tool) | User searches or chats | `{"query": "phone for photography", "results_count": 12}` |
| `cart_add` | Backend (MCP tool) | User adds to cart | `{"added_from": "recommendation"}` |
| `cart_remove` | Backend (MCP tool) | User removes from cart | `{}` |
| `wishlist_add` | Frontend | User likes/saves product | `{}` |
| `rec_click` | Frontend | User clicks a recommendation | `{"rec_position": 2, "rec_type": "personalized"}` |
| `rec_skip` | Frontend | User saw rec but didn't click (10s timer) | `{"skipped_product_ids": ["prod_01", "prod_02"]}` |
| `chat_message` | Backend (/api/chat) | User sends chat message | `{"message": "I need a phone"}` |

**Rule: Don't double-track.** Each event has ONE source (frontend OR backend, never both).

---

### Table 2: `user_preferences` (computed profile)

Derived from interactions. Recomputed synchronously after every interaction event (~25ms).

```sql
CREATE TABLE user_preferences (
    user_id TEXT PRIMARY KEY,
    brand_affinity JSON DEFAULT '{}',
    category_affinity JSON DEFAULT '{}',
    price_centroid REAL DEFAULT 500.0,
    price_min REAL DEFAULT 0.0,
    price_max REAL DEFAULT 2000.0,
    last_search_query TEXT,
    last_viewed_products JSON DEFAULT '[]',
    last_active_channel TEXT DEFAULT 'web',
    cart_products JSON DEFAULT '[]',
    wishlist_products JSON DEFAULT '[]',
    rec_click_rate REAL DEFAULT 0.0,
    total_interactions INTEGER DEFAULT 0,
    first_seen TIMESTAMP,
    last_active TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Example populated row:**
```json
{
  "user_id": "user_003",
  "brand_affinity": {"Samsung": 0.45, "Apple": 0.30, "Xiaomi": 0.15, "Google": 0.10},
  "category_affinity": {"smartphones": 0.55, "accessories": 0.25, "wearables": 0.20},
  "price_centroid": 420.00,
  "price_min": 99.00,
  "price_max": 799.00,
  "last_search_query": "phone for photography",
  "last_viewed_products": ["prod_042", "prod_015", "prod_033"],
  "last_active_channel": "web",
  "cart_products": ["prod_042"],
  "wishlist_products": ["prod_007"],
  "rec_click_rate": 0.35,
  "total_interactions": 47
}
```

---

## Backend Implementation

### File: `backend/tools/recommendations.py`

#### Event Weights (used for preference computation)

```python
EVENT_WEIGHTS = {
    "cart_add":        3.0,
    "wishlist_add":    2.5,
    "checkout_start":  3.0,
    "rec_click":       2.0,
    "comparison_view": 1.5,
    "product_view":    1.0,
    "search_query":    0.5,
    "cart_remove":    -2.0,
    "rec_skip":       -0.5,
}
```

#### Function: `recompute_preferences(user_id)`

Called after every `POST /api/track`. Takes ~25ms for 50 users.

```python
def recompute_preferences(user_id: str) -> dict:
    interactions = db.query(
        "SELECT * FROM interactions WHERE user_id = ? ORDER BY created_at DESC", user_id
    )

    brand_scores = {}
    category_scores = {}
    prices = []

    for event in interactions:
        weight = EVENT_WEIGHTS.get(event["event_type"], 0.5)

        if event["product_id"]:
            product = get_product(event["product_id"])
            brand_scores[product["brand"]] = brand_scores.get(product["brand"], 0) + weight
            category_scores[product["category"]] = category_scores.get(product["category"], 0) + weight
            if weight > 0:
                prices.append(product["price"])

        if event["event_type"] == "chat_message":
            # Extract entities from metadata if available
            meta = event.get("metadata", {})
            entities = meta.get("entities", {})
            if "brand" in entities:
                brand_scores[entities["brand"]] = brand_scores.get(entities["brand"], 0) + 1.5
            if "category" in entities:
                category_scores[entities["category"]] = category_scores.get(entities["category"], 0) + 1.5

    # Normalize scores to 0-1, keep top 10
    brand_affinity = normalize(brand_scores)
    category_affinity = normalize(category_scores)

    # Price stats
    price_centroid = sum(prices) / len(prices) if prices else 500.0

    # Recent activity
    last_viewed = [e["product_id"] for e in interactions if e["event_type"] == "product_view" and e["product_id"]][:10]
    last_search = next((e["metadata"].get("query") for e in interactions if e["event_type"] == "search_query"), None)

    # Rec feedback
    rec_events = [e for e in interactions if e["event_type"] in ("rec_click", "rec_skip")]
    rec_clicks = len([e for e in rec_events if e["event_type"] == "rec_click"])
    rec_click_rate = rec_clicks / len(rec_events) if rec_events else 0.0

    profile = {
        "user_id": user_id,
        "brand_affinity": brand_affinity,
        "category_affinity": category_affinity,
        "price_centroid": round(price_centroid, 2),
        "price_min": min(prices) if prices else 0.0,
        "price_max": max(prices) if prices else 2000.0,
        "last_search_query": last_search,
        "last_viewed_products": last_viewed,
        "last_active_channel": interactions[0]["channel"] if interactions else "web",
        "cart_products": get_cart_product_ids(user_id),
        "wishlist_products": get_wishlist_product_ids(user_id),
        "rec_click_rate": round(rec_click_rate, 3),
        "total_interactions": len(interactions),
        "last_active": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat()
    }

    db.upsert("user_preferences", profile)
    return profile


def normalize(scores: dict) -> dict:
    if not scores:
        return {}
    total = sum(max(0, v) for v in scores.values()) or 1
    normalized = {k: round(max(0, v) / total, 3) for k, v in scores.items()}
    return dict(sorted(normalized.items(), key=lambda x: x[1], reverse=True)[:10])
```

---

#### Function: `get_recommendations(user_id, context, top_k)`

The core recommendation logic. Called by the MCP tool.

```python
def get_recommendations(user_id: str, context: str = "general", top_k: int = 10) -> list[dict]:
    profile = db.get("user_preferences", user_id)

    # Step 1: Candidate generation via Chroma
    if context == "general":
        # Homepage: build query from user's top brand + category
        top_brand = max(profile["brand_affinity"], key=profile["brand_affinity"].get, default="")
        top_category = max(profile["category_affinity"], key=profile["category_affinity"].get, default="")
        search_query = f"{top_brand} {top_category} products"
    else:
        search_query = context

    candidates = chroma_collection.query(query_texts=[search_query], n_results=50)

    # Step 2: Score each candidate
    scored = []
    for i, product_id in enumerate(candidates["ids"][0]):
        product = get_product(product_id)

        # Skip products already in cart or recently viewed (top 3)
        if product_id in profile.get("cart_products", []):
            continue
        if product_id in profile.get("last_viewed_products", [])[:3]:
            continue

        similarity = 1 - candidates["distances"][0][i]  # Chroma distance → similarity
        profile_match = compute_profile_match(product, profile)
        popularity = product["popularity_score"]
        recency = 0.5  # Static for now

        final_score = (
            similarity * 0.40 +
            profile_match * 0.30 +
            popularity * 0.20 +
            recency * 0.10
        )

        explanation = build_explanation(product, profile, similarity, profile_match)

        scored.append({
            "product": product,
            "score": round(final_score, 3),
            "explanation": explanation,
            "score_breakdown": {
                "similarity": round(similarity, 3),
                "profile_match": round(profile_match, 3),
                "popularity": round(popularity, 3)
            }
        })

    # Step 3: Sort and diversify
    scored.sort(key=lambda x: x["score"], reverse=True)
    diversified = diversify(scored, max_per_brand=3)

    return diversified[:top_k]


def compute_profile_match(product: dict, profile: dict) -> float:
    score = 0.0

    # Price match (0-1): how close to user's price centroid
    centroid = profile.get("price_centroid", 500)
    price_diff = abs(product["price"] - centroid)
    price_score = max(0, 1 - (price_diff / max(centroid, 300)))
    score += price_score * 0.35

    # Brand match (0-1): user's affinity for this brand
    brand_score = profile.get("brand_affinity", {}).get(product["brand"], 0.05)
    score += brand_score * 0.30

    # Category match (0-1): user's affinity for this category
    cat_score = profile.get("category_affinity", {}).get(product["category"], 0.05)
    score += cat_score * 0.25

    # Tag overlap (bonus)
    # ... optional, skip for v1

    return min(score / 0.90, 1.0)  # Normalize to 0-1


def build_explanation(product, profile, similarity, profile_match) -> str:
    reasons = []

    if profile.get("brand_affinity", {}).get(product["brand"], 0) > 0.25:
        reasons.append(f"matches your preference for {product['brand']}")
    if abs(product["price"] - profile.get("price_centroid", 500)) < 150:
        reasons.append("fits your typical budget")
    if similarity > 0.75:
        reasons.append("closely matches what you're looking for")
    if product.get("rating", 0) >= 4.5:
        reasons.append(f"highly rated ({product['rating']}★)")

    if not reasons:
        reasons.append(f"popular in {product['category']}")

    return "Recommended because it " + " and ".join(reasons[:2]) + "."


def diversify(scored: list, max_per_brand: int = 3) -> list:
    """Don't show 10 Samsung phones. Mix brands."""
    brand_counts = {}
    result = []
    for item in scored:
        brand = item["product"]["brand"]
        if brand_counts.get(brand, 0) < max_per_brand:
            result.append(item)
            brand_counts[brand] = brand_counts.get(brand, 0) + 1
    return result
```

---

## API Endpoints

### `POST /api/track` — Capture interaction

```python
@app.post("/api/track")
async def track(event: InteractionEvent):
    db.execute(
        "INSERT INTO interactions (user_id, event_type, product_id, channel, session_id, metadata) VALUES (?, ?, ?, ?, ?, ?)",
        event.user_id, event.event_type, event.product_id,
        event.channel, event.session_id, json.dumps(event.metadata)
    )
    updated = recompute_preferences(event.user_id)
    return {"status": "tracked", "interaction_count": updated["total_interactions"]}
```

**Request body:**
```json
{
  "user_id": "user_003",
  "event_type": "product_view",
  "product_id": "prod_042",
  "channel": "web",
  "session_id": "sess_abc123",
  "metadata": {}
}
```

---

### `GET /api/recommendations/{user_id}` — Get personalized recs

```python
@app.get("/api/recommendations/{user_id}")
async def recommendations(user_id: str, context: str = "general", top_k: int = 10):
    recs = get_recommendations(user_id, context, top_k)
    return {"recommendations": recs, "user_id": user_id, "context": context}
```

**Response:**
```json
{
  "recommendations": [
    {
      "product": { "id": "prod_042", "name": "Galaxy A55", "price": 349, "brand": "Samsung", ... },
      "score": 0.742,
      "explanation": "Recommended because it matches your preference for Samsung and fits your typical budget.",
      "score_breakdown": { "similarity": 0.82, "profile_match": 0.91, "popularity": 0.70 }
    }
  ]
}
```

---

### `GET /api/recommendations/stream/{user_id}` — Real-time SSE

Pushes new recommendations whenever `user_preferences` changes.

```python
@app.get("/api/recommendations/stream/{user_id}")
async def stream_recs(user_id: str):
    async def generator():
        last_hash = None
        while True:
            profile = db.get("user_preferences", user_id)
            current_hash = hash(json.dumps(profile, sort_keys=True))
            if current_hash != last_hash:
                recs = get_recommendations(user_id, profile.get("last_search_query", "general"))
                yield {"event": "update", "data": json.dumps({"recommendations": recs})}
                last_hash = current_hash
            await asyncio.sleep(2)
    return EventSourceResponse(generator())
```

---

## Frontend Implementation

### Hook: `useTracking.js`

Single hook for all interaction tracking. Every component uses this.

```jsx
import axios from 'axios';

export function useTracking(userId, sessionId, channel) {
  const track = async (eventType, productId = null, metadata = {}) => {
    try {
      await axios.post('/api/track', {
        user_id: userId,
        event_type: eventType,
        product_id: productId,
        session_id: sessionId,
        channel: channel,
        metadata: metadata
      });
    } catch (e) {
      console.warn('Track failed:', e);  // Don't break UI if tracking fails
    }
  };
  return { track };
}
```

---

### Hook: `useRecommendations.js`

Listens to SSE for real-time rec updates.

```jsx
import { useState, useEffect } from 'react';
import { API_BASE } from '../utils/constants';

export function useRecommendations(userId) {
  const [recommendations, setRecommendations] = useState([]);
  const [lastUpdate, setLastUpdate] = useState(null);

  useEffect(() => {
    if (!userId) return;
    const es = new EventSource(`${API_BASE}/api/recommendations/stream/${userId}`);

    es.addEventListener('update', (event) => {
      const data = JSON.parse(event.data);
      setRecommendations(data.recommendations);
      setLastUpdate(new Date());
    });

    es.onerror = () => {
      es.close();
      // Reconnect after 5s
      setTimeout(() => {}, 5000);
    };

    return () => es.close();
  }, [userId]);

  return { recommendations, lastUpdate };
}
```

---

### Component Integration: Where to Fire Events

| Component | Event | Code |
|-----------|-------|------|
| `ProductCard.jsx` | `product_view` | `onClick={() => track('product_view', product.id)}` |
| `ProductGrid.jsx` | `rec_click` | `onClick={() => track('rec_click', product.id, {rec_position: i})}` |
| `RecPanel.jsx` | `rec_skip` | Timer-based: if no click after 10s, fire skip |
| `CartSidebar.jsx` | — | Cart events tracked by backend (MCP tool), NOT frontend |
| `WishlistButton.jsx` | `wishlist_add` | `onClick={() => track('wishlist_add', product.id)}` |
| `SearchBar.jsx` | — | Search events tracked by backend (MCP tool), NOT frontend |

---

### Component: `RecPanel.jsx` (Recommendation Panel with Skip Detection)

```jsx
export function RecPanel({ userId, channel }) {
  const { recommendations, lastUpdate } = useRecommendations(userId);
  const { track } = useTracking(userId, sessionId, channel);
  const clickedRef = useRef(new Set());

  // Track skips after 10 seconds
  useEffect(() => {
    if (recommendations.length === 0) return;
    clickedRef.current = new Set();

    const timer = setTimeout(() => {
      const shownIds = recommendations.map(r => r.product.id);
      const skipped = shownIds.filter(id => !clickedRef.current.has(id));
      if (skipped.length > 0) {
        track('rec_skip', null, { skipped_product_ids: skipped });
      }
    }, 10000);

    return () => clearTimeout(timer);
  }, [recommendations]);

  const handleRecClick = (product, index) => {
    clickedRef.current.add(product.id);
    track('rec_click', product.id, { rec_position: index });
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-semibold">Recommended For You</h3>
        {lastUpdate && (
          <span className="text-xs text-green-600">Updated just now</span>
        )}
      </div>
      <div className="grid grid-cols-2 gap-3">
        {recommendations.map((rec, i) => (
          <ProductCard
            key={rec.product.id}
            product={rec.product}
            explanation={rec.explanation}
            onClick={() => handleRecClick(rec.product, i)}
          />
        ))}
      </div>
    </div>
  );
}
```

---

### Session ID (generate once per browser tab)

```jsx
// App.jsx
const [sessionId] = useState(() => {
  let id = sessionStorage.getItem('session_id');
  if (!id) {
    id = crypto.randomUUID();
    sessionStorage.setItem('session_id', id);
  }
  return id;
});
```

---

## How It All Connects

```
FLOW: User clicks Galaxy A55 on homepage

1. Frontend: track('product_view', 'prod_042')
   → POST /api/track

2. Backend: INSERT into interactions

3. Backend: recompute_preferences('user_003')
   → Samsung affinity goes from 0.40 → 0.45
   → UPSERT into user_preferences

4. SSE endpoint (polling every 2s):
   → Detects profile hash changed
   → Calls get_recommendations('user_003', 'general')
   → New recs scored with updated Samsung affinity
   → Pushes via SSE

5. Frontend: useRecommendations hook receives update
   → RecPanel re-renders with Samsung products ranked higher
   → Shows "Updated just now" badge

Total time: ~2.5 seconds from click to updated recommendations
```

---

## Where Recommendations Appear (5 places)

| Location | Trigger | Data Source |
|----------|---------|------------|
| **Homepage Product Grid** | Page load | `GET /api/recommendations/{user_id}?context=general` |
| **After Chat Response** | Agent responds | Agent calls `get_recommendations` MCP tool internally |
| **RecPanel (sidebar/bottom)** | SSE real-time | `GET /api/recommendations/stream/{user_id}` |
| **Smart Cart Upsells** | Cart add event | `manage_cart` MCP tool returns upsells |
| **Search Results Re-ranking** | User searches | `search_products` MCP tool uses profile to re-rank |

---

## Profile Switcher (For Demo)

The frontend has a dropdown to switch between pre-seeded user profiles:

```jsx
const DEMO_USERS = [
  { id: "user_001", name: "Alex (Budget Student)", emoji: "🎓" },
  { id: "user_011", name: "Dev (Tech Enthusiast)", emoji: "🚀" },
  { id: "user_021", name: "Morgan (Business Pro)", emoji: "💼" },
  { id: "user_031", name: "Greta (Senior)", emoji: "👵" },
  { id: "user_041", name: "Chris (Family Parent)", emoji: "👨‍👩‍👧" },
];
```

When you switch users, the entire page re-renders with different recommendations. This is the **proof of personalization** for the demo.

---

## How `user_preferences` Is the Universal Table (Wiring Diagram)

This is the **single table** that powers ALL personalization across every feature:

```
                    ┌──────────────────────────────────┐
                    │      user_preferences TABLE       │
                    │                                   │
                    │  brand_affinity: {Samsung: 0.45}  │
                    │  category_affinity: {phones: 0.6} │
                    │  price_centroid: 420              │
                    │  last_search_query: "camera phone"│
                    │  cart_products: [prod_042]        │
                    │  wishlist_products: [prod_007]    │
                    └────────────┬──────────────────────┘
                                 │
          ┌──────────────────────┼───────────────────────────┐
          │                      │                           │
          ↓                      ↓                           ↓
┌─────────────────┐   ┌─────────────────────┐   ┌──────────────────┐
│ PRODUCT GRID    │   │ CHATBOT (LLM Agent) │   │ SMART CART       │
│ (Homepage/Shop) │   │                     │   │                  │
│                 │   │ System prompt gets:  │   │ Upsell uses:     │
│ On page load:   │   │ - brand_affinity     │   │ - brand_affinity │
│ GET /api/recs   │   │ - price_centroid     │   │   (suggest same  │
│ → scored by     │   │ - category_affinity  │   │    brand access) │
│   profile_match │   │ - last_search_query  │   │ - price_centroid │
│ → Samsung first │   │ - cart_products      │   │   (don't suggest │
│   for Samsung   │   │                     │   │    too expensive) │
│   lovers        │   │ Agent responds:      │   │ - category_affinity│
│                 │   │ "Since you prefer    │   │   (cross-sell    │
│ After search:   │   │  Samsung and budget  │   │    related cats) │
│ → same scoring  │   │  range, here's..."   │   │                  │
│   applied to    │   │                     │   │                  │
│   search results│   │ Agent sorts results  │   │                  │
│                 │   │ by profile before    │   │                  │
│                 │   │ showing to user      │   │                  │
└─────────────────┘   └─────────────────────┘   └──────────────────┘
```

### Consumer 1: Product Grid (Website Opens)

When the website loads or user navigates to Shop:

```python
# Frontend calls on page load:
GET /api/recommendations/{user_id}?context=general

# Backend logic:
def get_homepage_products(user_id):
    profile = db.get("user_preferences", user_id)
    
    # Build search query from user's preferences
    top_brand = max(profile["brand_affinity"], key=profile["brand_affinity"].get)
    top_category = max(profile["category_affinity"], key=profile["category_affinity"].get)
    
    # Get candidates from Chroma using preference-based query
    candidates = chroma.query(f"{top_brand} {top_category} products", n=50)
    
    # Score by profile → Samsung user sees Samsung first
    scored = score_by_profile(candidates, profile)
    
    return scored[:12]  # Show top 12 on homepage
```

**Result:** Budget student opens the site → sees Galaxy A55, Redmi Note 13. Tech enthusiast opens → sees iPhone 15 Pro, Galaxy S24 Ultra. Same website, different products.

---

### Consumer 2: Chatbot (AI Agent)

The LLM agent receives `user_preferences` as context in its system prompt AND uses it when calling tools:

```python
# When user sends a chat message:

@app.post("/api/chat")
async def chat(request: ChatRequest):
    # 1. Load user preferences
    profile = db.get("user_preferences", request.user_id)
    
    # 2. Build system prompt WITH user context
    system_prompt = f"""You are Ava, a shopping assistant for OmniShop.
    
    Current user preferences (use these to personalize your responses):
    - Preferred brands: {profile['brand_affinity']}
    - Preferred categories: {profile['category_affinity']}
    - Budget range: around €{profile['price_centroid']} (min €{profile['price_min']}, max €{profile['price_max']})
    - Currently in cart: {profile['cart_products']}
    - Recently viewed: {profile['last_viewed_products'][:5]}
    - Last search: {profile['last_search_query']}
    
    Rules:
    - When recommending products, prefer their preferred brands
    - Stay within their price range unless they explicitly ask for premium
    - Don't suggest products already in their cart
    - Explain WHY you're recommending something based on their preferences
    - If they ask "what should I buy?", use their affinities to guide the answer
    """
    
    # 3. Call LLM with tools (MCP tools also read user_preferences internally)
    response = await agent.invoke(
        message=request.message,
        system_prompt=system_prompt,
        tools=[search_products, get_recommendations, manage_cart, get_user_profile]
    )
    
    return response
```

**How chatbot uses preferences in practice:**

| User Says | What Agent Does With Preferences |
|-----------|--------------------------------|
| "I need a phone" | Calls `search_products("phone")` → MCP tool re-ranks results by `brand_affinity` + `price_centroid` → returns Samsung A55 first (not iPhone) for budget user |
| "What do you recommend?" | Calls `get_recommendations(user_id, "general")` → returns profile-scored results → Agent says "Based on your preference for Samsung in the mid-range, I'd recommend..." |
| "Add this to cart" | Calls `manage_cart(user_id, "add", product_id)` → Tool reads `brand_affinity` to generate upsell suggestions → "Since you're getting a Samsung phone, here's a Samsung case that 73% of buyers added" |
| "Is this phone good?" | Agent sees `price_centroid: 420` in prompt → knows user is budget-conscious → responds with value-focused language, mentions price-to-feature ratio |
| "Show me something better" | Agent reads `price_max: 799` from profile → suggests within that ceiling, not €1200 flagships |

**Key point:** The agent doesn't just get preferences as text — the MCP tools (`search_products`, `get_recommendations`) also read `user_preferences` internally to score/rank results BEFORE returning them to the agent.

---

### Consumer 3: Smart Cart

When a product is added to cart, the `manage_cart` MCP tool reads `user_preferences` to generate relevant upsells:

```python
# Inside manage_cart MCP tool:

async def generate_upsells(user_id, cart_item):
    profile = db.get("user_preferences", user_id)
    
    # Use brand affinity for cross-sell
    preferred_brand = cart_item["brand"]  # User just added this brand
    
    # Suggest accessories from SAME brand (brand affinity)
    accessories = db.query("""
        SELECT * FROM products 
        WHERE category = 'accessories' 
        AND brand = ?
        AND price < ?
        ORDER BY popularity_score DESC
        LIMIT 3
    """, preferred_brand, profile["price_centroid"] * 0.3)  # Accessories < 30% of their budget
    
    # Don't suggest things already in cart or wishlist
    accessories = [a for a in accessories if a["id"] not in profile["cart_products"]]
    accessories = [a for a in accessories if a["id"] not in profile["wishlist_products"]]
    
    return accessories
```

---

## Complete Wiring: Capture → Update → Use

### Step-by-step flow with ALL consumers:

```
═══════════════════════════════════════════════════════════════
CAPTURE: User clicks Samsung Galaxy A55
═══════════════════════════════════════════════════════════════

Frontend: track('product_view', 'prod_042')
    ↓
POST /api/track
    ↓
Backend: INSERT INTO interactions (user_id='user_003', event_type='product_view', product_id='prod_042', channel='web')
    ↓

═══════════════════════════════════════════════════════════════
UPDATE: Recompute user_preferences
═══════════════════════════════════════════════════════════════

recompute_preferences('user_003')
    ↓
    Read ALL interactions for user_003
    ↓
    Samsung viewed again → brand_affinity['Samsung'] goes 0.40 → 0.45
    Phone viewed → category_affinity['smartphones'] stays 0.55
    Price €349 → price_centroid shifts from 430 → 425
    last_viewed_products = ['prod_042', ...previous...]
    ↓
    UPSERT into user_preferences
    ↓

═══════════════════════════════════════════════════════════════
USE: All consumers now read updated preferences
═══════════════════════════════════════════════════════════════

Consumer 1 — PRODUCT GRID:
    SSE polls user_preferences → hash changed
    → get_recommendations() called with updated profile
    → Samsung products score higher now (affinity 0.45)
    → SSE pushes new recs to frontend
    → Product grid re-renders: Samsung products moved up

Consumer 2 — CHATBOT:
    Next time user chats, system prompt has:
    "Preferred brands: {Samsung: 0.45, Apple: 0.30}"
    → Agent's responses lean toward Samsung
    → search_products() MCP tool ranks Samsung higher

Consumer 3 — SMART CART:
    Next time user adds to cart:
    → manage_cart() reads brand_affinity
    → Suggests Samsung accessories (not Apple)
    → Stays within price_centroid range

Consumer 4 — OMNICHANNEL:
    User switches to mobile:
    → SAME user_preferences table (no channel column)
    → Mobile gets same Samsung-first ranking
    → Cart shows same upsells
    → Chat has same context
```

---

### The "Universal" Aspect: What Makes It Work Everywhere

```
user_preferences has NO channel dependency.
It works for:

✅ Web homepage    → reads user_preferences → ranks products
✅ Mobile homepage → reads SAME user_preferences → SAME ranking
✅ Web chatbot     → gets preferences in prompt → personalizes responses
✅ Mobile chatbot  → gets SAME preferences → SAME personalization
✅ Web cart        → reads preferences → suggests relevant upsells
✅ Mobile cart     → reads SAME preferences → SAME upsells
✅ Web search      → re-ranks by preferences
✅ Mobile search   → SAME re-ranking

ONE TABLE → EVERY TOUCHPOINT → EVERY CHANNEL
```

---

## Key Design Decisions

| Decision | Choice | Why |
|----------|--------|-----|
| Recompute timing | Synchronous on every event | Fast enough (~25ms), no stale data during demo |
| Scoring approach | Rules-based scoring | Deterministic, explainable, no LLM needed per request |
| LLM role | Explanation only | Products come from DB, LLM just narrates why |
| Real-time delivery | SSE (Server-Sent Events) | Simpler than WebSocket, no bidirectional needed |
| Skip detection | 10-second frontend timer | Only frontend knows what's visible |
| Double-tracking prevention | One source per event type | See table above — frontend OR backend, never both |

---

## What to Tell Judges About Scale

> "At Deutsche Telekom scale with millions of users, we'd batch preference computation via Kafka every 5 minutes and use Redis for profile caching. For this POC, synchronous recompute on SQLite handles 50 users in 25ms. The architecture is the same — only the compute layer changes."

---

## Acceptance Criteria

- [ ] `POST /api/track` stores events and triggers preference recompute
- [ ] `GET /api/recommendations/{user_id}` returns personalized, scored products with explanations
- [ ] `GET /api/recommendations/stream/{user_id}` pushes new recs via SSE when profile changes
- [ ] Different users see different product rankings for same query (testable via profile switcher)
- [ ] Explanation text reflects actual scoring reasons (not generic)
- [ ] Products already in cart are excluded from recommendations
- [ ] Brand diversity enforced (max 3 per brand in top 10)
- [ ] Frontend tracks: product_view, rec_click, rec_skip, wishlist_add
- [ ] Backend tracks: search_query, cart_add, cart_remove, chat_message
- [ ] No double-tracking (each event has exactly one source)

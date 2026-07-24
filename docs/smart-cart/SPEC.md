# Feature Spec: Smart Cart

> **Status:** Ready for implementation  
> **Effort:** 30-45 minutes (including testing)  
> **Context:** Hackathon — focus on high-impact, low-complexity features only  
> **Dependencies:** Products DB, Cart CRUD API working, user_preferences table populated

---

## What This Feature Does

The cart actively helps customers buy MORE and buy BETTER. When a user adds an item, the cart suggests relevant bundles, cross-sells, and shows savings — all rules-based, no LLM needed.

---

## Features Ranked by Impact vs Effort

| # | Feature | Demo Impact | Build Time | Verdict |
|---|---------|-------------|------------|---------|
| 1 | **Cross-Sell ("Also Bought")** | HIGH — visually impressive | 15 min | ✅ BUILD |
| 2 | **Bundle Detection + Discount** | HIGH — shows business value | 15 min | ✅ BUILD |
| 3 | **Savings Display** | MEDIUM — makes cart feel smart | 5 min | ✅ BUILD |
| 4 | **Abandonment Nudge** | MEDIUM — easy wow factor | 5 min | ✅ BUILD |
| 5 | Upgrade Suggestion | LOW — needs complex product matching | 20 min | ❌ SKIP |
| 6 | Comparison in Cart | LOW — niche use case | 25 min | ❌ SKIP |

**Build features 1-4 only. Skip 5-6.**

---

## Database

No new tables needed. Smart Cart reads from:

- `products` — to find accessories/bundles
- `cart` — current cart items  
- `user_preferences` — brand_affinity for personalized suggestions

### Cart Table (already exists)

```sql
CREATE TABLE cart (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    product_id TEXT NOT NULL,
    quantity INTEGER DEFAULT 1,
    added_from TEXT DEFAULT 'browse',   -- 'browse' | 'recommendation' | 'upsell' | 'bundle'
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, product_id)
);
```

---

## Feature 1: Cross-Sell ("Frequently Bought Together")

**Trigger:** When user adds a product to cart  
**Logic:** Pre-defined co-purchase map (hardcoded rules, simulated data)  
**LLM needed:** No

### Co-Purchase Rules

```python
# backend/tools/cart_manager.py

CO_PURCHASE_MAP = {
    "smartphones:Apple": [
        {"subcategory": "earbuds", "brand": "Apple", "rate": 73, "label": "AirPods Pro 2"},
        {"subcategory": "cases", "brand": "Apple", "rate": 87, "label": "MagSafe Case"},
        {"subcategory": "smartwatches", "brand": "Apple", "rate": 41, "label": "Apple Watch"},
    ],
    "smartphones:Samsung": [
        {"subcategory": "earbuds", "brand": "Samsung", "rate": 68, "label": "Galaxy Buds3"},
        {"subcategory": "cases", "brand": "Samsung", "rate": 82, "label": "Clear Case"},
        {"subcategory": "smartwatches", "brand": "Samsung", "rate": 45, "label": "Galaxy Watch"},
    ],
    "smartphones:Google": [
        {"subcategory": "earbuds", "brand": "Google", "rate": 61, "label": "Pixel Buds Pro"},
        {"subcategory": "cases", "brand": "Google", "rate": 79, "label": "Pixel Case"},
    ],
    "laptops:Apple": [
        {"subcategory": "mice", "brand": "Apple", "rate": 52, "label": "Magic Mouse"},
        {"subcategory": "laptop_bags", "brand": None, "rate": 67, "label": "Laptop Sleeve"},
    ],
    "laptops:*": [
        {"subcategory": "mice", "brand": None, "rate": 58, "label": "Wireless Mouse"},
        {"subcategory": "laptop_bags", "brand": None, "rate": 64, "label": "Laptop Bag"},
        {"subcategory": "keyboards", "brand": None, "rate": 39, "label": "Wireless Keyboard"},
    ],
    "tablets:*": [
        {"subcategory": "cases", "brand": None, "rate": 91, "label": "Tablet Case"},
        {"subcategory": "styluses", "brand": None, "rate": 44, "label": "Stylus Pen"},
    ],
}
```

### Implementation

```python
def get_cross_sell_suggestions(user_id: str, added_product: dict) -> list:
    """Get 'frequently bought together' suggestions when an item is added to cart."""
    category = added_product["category"]
    brand = added_product["brand"]
    
    # Look up co-purchase rules (brand-specific first, then generic)
    key_specific = f"{category}:{brand}"
    key_generic = f"{category}:*"
    
    rules = CO_PURCHASE_MAP.get(key_specific, CO_PURCHASE_MAP.get(key_generic, []))
    
    if not rules:
        return []
    
    # Find actual products matching the rules
    cart_product_ids = get_cart_product_ids(user_id)
    suggestions = []
    
    for rule in rules:
        # Find a product matching this rule
        filters = {"subcategory": rule["subcategory"]}
        if rule["brand"]:
            filters["brand"] = rule["brand"]
        
        product = db.query_one("""
            SELECT * FROM products 
            WHERE subcategory = ? 
            AND (? IS NULL OR brand = ?)
            AND id NOT IN ({})
            ORDER BY popularity_score DESC
            LIMIT 1
        """.format(",".join(["?"] * len(cart_product_ids))),
            rule["subcategory"], rule["brand"], rule["brand"], *cart_product_ids
        )
        
        if product:
            suggestions.append({
                "product": product,
                "rate": rule["rate"],
                "reason": f"{rule['rate']}% of buyers also added this"
            })
    
    # Return top 2 only (don't overwhelm)
    return sorted(suggestions, key=lambda x: x["rate"], reverse=True)[:2]
```

### Frontend Display

```jsx
// Inside CartSidebar.jsx — shown after item is added
{crossSellItems.length > 0 && (
  <div className="mt-4 p-3 bg-blue-50 rounded-lg">
    <h4 className="font-semibold text-sm mb-2">🛍️ Frequently Bought Together</h4>
    {crossSellItems.map(item => (
      <div key={item.product.id} className="flex items-center justify-between py-2 border-b last:border-0">
        <div>
          <p className="text-sm font-medium">{item.product.name}</p>
          <p className="text-xs text-gray-500">{item.reason}</p>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-sm font-bold">€{item.product.price}</span>
          <button 
            onClick={() => addToCart(item.product, 'upsell')}
            className="text-xs bg-magenta-600 text-white px-2 py-1 rounded"
          >
            Add
          </button>
        </div>
      </div>
    ))}
  </div>
)}
```

---

## Feature 2: Bundle Detection + Discount

**Trigger:** When cart contains a product from a trigger category  
**Logic:** Check if complementary items are missing → suggest bundle with discount  
**LLM needed:** No

### Bundle Rules

```python
BUNDLE_RULES = [
    {
        "name": "Phone Essentials Bundle",
        "trigger_category": "smartphones",
        "suggest_categories": ["cases", "screen_protectors"],
        "discount_percent": 10,
        "description": "Protect your new phone — save 10%"
    },
    {
        "name": "Laptop Starter Kit",
        "trigger_category": "laptops",
        "suggest_categories": ["laptop_bags", "mice"],
        "discount_percent": 15,
        "description": "Everything you need to get started — save 15%"
    },
    {
        "name": "Device + Plan Bundle",
        "trigger_categories": ["smartphones", "tablets"],
        "suggest_categories": ["plans"],
        "discount_percent": 20,
        "description": "Add a plan and save 20% on the device"
    },
]
```

### Implementation

```python
def detect_bundles(user_id: str, cart_items: list) -> list:
    """Check if any bundle rules apply to current cart."""
    cart_categories = {item["category"] for item in cart_items}
    cart_subcategories = {item.get("subcategory") for item in cart_items}
    bundles = []
    
    for rule in BUNDLE_RULES:
        trigger = rule.get("trigger_category") or rule.get("trigger_categories", [])
        triggers = [trigger] if isinstance(trigger, str) else trigger
        
        # Check if trigger is in cart
        if not any(t in cart_categories for t in triggers):
            continue
        
        # Find which suggested categories are MISSING from cart
        missing = [cat for cat in rule["suggest_categories"] if cat not in cart_subcategories]
        
        if not missing:
            continue  # Already has everything
        
        # Find products for missing categories
        suggested_products = []
        for cat in missing:
            product = db.query_one("""
                SELECT * FROM products 
                WHERE subcategory = ?
                ORDER BY popularity_score DESC
                LIMIT 1
            """, cat)
            if product:
                suggested_products.append(product)
        
        if suggested_products:
            original_total = sum(p["price"] for p in suggested_products)
            discount = original_total * rule["discount_percent"] / 100
            
            bundles.append({
                "name": rule["name"],
                "description": rule["description"],
                "products": suggested_products,
                "discount_percent": rule["discount_percent"],
                "original_price": round(original_total, 2),
                "bundle_price": round(original_total - discount, 2),
                "savings": round(discount, 2)
            })
    
    return bundles[:1]  # Show max 1 bundle at a time (don't overwhelm)
```

### Frontend Display

```jsx
{bundles.length > 0 && (
  <div className="mt-4 p-3 bg-green-50 border border-green-200 rounded-lg">
    <h4 className="font-semibold text-sm text-green-800">📦 {bundles[0].name}</h4>
    <p className="text-xs text-green-600 mt-1">{bundles[0].description}</p>
    <div className="mt-2">
      {bundles[0].products.map(p => (
        <div key={p.id} className="flex justify-between text-sm py-1">
          <span>{p.name}</span>
          <span className="line-through text-gray-400">€{p.price}</span>
        </div>
      ))}
    </div>
    <div className="mt-2 flex items-center justify-between">
      <div>
        <span className="text-lg font-bold text-green-700">€{bundles[0].bundle_price}</span>
        <span className="text-xs text-green-600 ml-1">Save €{bundles[0].savings}</span>
      </div>
      <button 
        onClick={() => addBundle(bundles[0].products)}
        className="bg-green-600 text-white px-3 py-1.5 rounded text-sm font-medium"
      >
        Add Bundle
      </button>
    </div>
  </div>
)}
```

---

## Feature 3: Savings Display

**Trigger:** Always visible when items are in cart  
**Logic:** Simple math — sum prices, apply any bundle discounts  
**LLM needed:** No

### Implementation

```jsx
// CartSidebar.jsx — bottom section
function CartTotal({ items, bundles }) {
  const subtotal = items.reduce((sum, item) => sum + item.price * item.quantity, 0);
  const totalDiscount = bundles.reduce((sum, b) => sum + b.savings, 0);
  const total = subtotal - totalDiscount;

  return (
    <div className="border-t pt-3 mt-4">
      <div className="flex justify-between text-sm text-gray-600">
        <span>Subtotal ({items.length} items)</span>
        <span>€{subtotal.toFixed(2)}</span>
      </div>
      {totalDiscount > 0 && (
        <div className="flex justify-between text-sm text-green-600 mt-1">
          <span>Bundle Discount</span>
          <span>-€{totalDiscount.toFixed(2)}</span>
        </div>
      )}
      <div className="flex justify-between font-bold text-lg mt-2">
        <span>Total</span>
        <span>€{total.toFixed(2)}</span>
      </div>
      {totalDiscount > 0 && (
        <p className="text-xs text-green-600 mt-1 text-right">
          💰 You saved €{totalDiscount.toFixed(2)}!
        </p>
      )}
      <button className="w-full mt-3 bg-magenta-600 text-white py-3 rounded-lg font-medium">
        Checkout
      </button>
    </div>
  );
}
```

---

## Feature 4: Abandonment Nudge

**Trigger:** Cart has items + no user interaction for 30 seconds  
**Logic:** Frontend timer only  
**LLM needed:** No

### Implementation

```jsx
// CartSidebar.jsx or App.jsx
function AbandonmentNudge({ cartItems, onDismiss }) {
  const [show, setShow] = useState(false);
  const lastInteraction = useRef(Date.now());

  // Reset timer on any user action
  useEffect(() => {
    const resetTimer = () => { lastInteraction.current = Date.now(); };
    window.addEventListener('click', resetTimer);
    window.addEventListener('keydown', resetTimer);
    return () => {
      window.removeEventListener('click', resetTimer);
      window.removeEventListener('keydown', resetTimer);
    };
  }, []);

  // Show nudge after 30s of inactivity
  useEffect(() => {
    if (cartItems.length === 0) return;
    
    const interval = setInterval(() => {
      if (Date.now() - lastInteraction.current > 30000) {
        setShow(true);
      }
    }, 5000);  // Check every 5 seconds
    
    return () => clearInterval(interval);
  }, [cartItems]);

  if (!show || cartItems.length === 0) return null;

  const total = cartItems.reduce((sum, item) => sum + item.price, 0);

  return (
    <div className="fixed bottom-4 right-4 bg-white shadow-xl rounded-xl p-4 w-80 border border-gray-200 animate-slide-up z-50">
      <button onClick={() => setShow(false)} className="absolute top-2 right-2 text-gray-400">✕</button>
      <p className="font-semibold">🔔 Still thinking?</p>
      <p className="text-sm text-gray-600 mt-1">
        You have {cartItems.length} item{cartItems.length > 1 ? 's' : ''} worth €{total.toFixed(2)} in your cart.
      </p>
      <p className="text-xs text-gray-400 mt-2">
        💡 These items are popular — complete your purchase before they're gone!
      </p>
      <button 
        onClick={() => { setShow(false); scrollToCart(); }}
        className="w-full mt-3 bg-magenta-600 text-white py-2 rounded-lg text-sm font-medium"
      >
        Complete Purchase
      </button>
    </div>
  );
}
```

---

## API: `manage_cart` MCP Tool

Single tool handles all cart operations + returns smart suggestions.

```python
# backend/tools/cart_manager.py (exposed via MCP)

async def manage_cart(user_id: str, action: str, product_id: str = None, quantity: int = 1) -> dict:
    """
    Manage cart with smart suggestions.
    
    Actions: add, remove, view, clear
    Returns: cart items + cross-sell + bundles + totals
    """
    if action == "add" and product_id:
        db.execute(
            "INSERT OR REPLACE INTO cart (user_id, product_id, quantity, added_from) VALUES (?, ?, ?, ?)",
            user_id, product_id, quantity, "browse"
        )
    elif action == "remove" and product_id:
        db.execute("DELETE FROM cart WHERE user_id = ? AND product_id = ?", user_id, product_id)
    elif action == "clear":
        db.execute("DELETE FROM cart WHERE user_id = ?", user_id)
    
    # Get current cart
    cart_items = db.query("""
        SELECT c.*, p.* FROM cart c 
        JOIN products p ON c.product_id = p.id 
        WHERE c.user_id = ?
    """, user_id)
    
    # Generate smart suggestions
    cross_sell = []
    bundles = []
    
    if cart_items:
        # Cross-sell based on last added item
        last_added = cart_items[-1] if action == "add" else cart_items[0]
        cross_sell = get_cross_sell_suggestions(user_id, last_added)
        bundles = detect_bundles(user_id, cart_items)
    
    # Calculate totals
    subtotal = sum(item["price"] * item["quantity"] for item in cart_items)
    discount = sum(b["savings"] for b in bundles)
    
    return {
        "items": cart_items,
        "item_count": len(cart_items),
        "subtotal": round(subtotal, 2),
        "discount": round(discount, 2),
        "total": round(subtotal - discount, 2),
        "cross_sell_suggestions": cross_sell,
        "bundle_suggestions": bundles
    }
```

---

## REST API Endpoint

```python
# backend/main.py

@app.get("/api/cart/{user_id}")
async def get_cart(user_id: str):
    return await manage_cart(user_id, "view")

@app.post("/api/cart/{user_id}/add")
async def add_to_cart(user_id: str, body: AddToCartRequest):
    result = await manage_cart(user_id, "add", body.product_id, body.quantity)
    # Track interaction (updates user_preferences)
    track_event(user_id, "cart_add", body.product_id, {"added_from": body.source})
    return result

@app.delete("/api/cart/{user_id}/remove/{product_id}")
async def remove_from_cart(user_id: str, product_id: str):
    result = await manage_cart(user_id, "remove", product_id)
    track_event(user_id, "cart_remove", product_id)
    return result
```

---

## Frontend: `useCart.js` Hook

```jsx
export function useCart(userId) {
  const [cart, setCart] = useState({ items: [], cross_sell_suggestions: [], bundle_suggestions: [], total: 0 });

  const fetchCart = async () => {
    const res = await axios.get(`/api/cart/${userId}`);
    setCart(res.data);
  };

  const addToCart = async (productId, source = 'browse') => {
    const res = await axios.post(`/api/cart/${userId}/add`, { product_id: productId, source });
    setCart(res.data);  // Response includes updated suggestions
  };

  const removeFromCart = async (productId) => {
    const res = await axios.delete(`/api/cart/${userId}/remove/${productId}`);
    setCart(res.data);
  };

  useEffect(() => { fetchCart(); }, [userId]);

  return { cart, addToCart, removeFromCart };
}
```

---

## Complete Cart Sidebar Layout

```
┌─────────────────────────────────────┐
│ 🛒 Your Cart (3)                    │
├─────────────────────────────────────┤
│                                     │
│ Galaxy A55           €349    [✕]    │
│ Galaxy Buds FE       €99     [✕]    │
│ Clear Case           €29     [✕]    │
│                                     │
├─────────────────────────────────────┤
│ 🛍️ Frequently Bought Together       │
│                                     │
│ Screen Protector  €19    [Add]      │
│ "82% of buyers also added this"     │
│                                     │
├─────────────────────────────────────┤
│ 📦 Phone Essentials Bundle          │
│ "Add protector + charger, save 10%" │
│                                     │
│ Was: €48  Now: €43   [Add Bundle]   │
│                                     │
├─────────────────────────────────────┤
│ Subtotal:                    €477   │
│ Bundle Discount:             -€5    │
│ ────────────────────────────────    │
│ Total:                       €472   │
│ 💰 You saved €5!                   │
│                                     │
│ [     Checkout     ]                │
└─────────────────────────────────────┘

After 30s idle:
┌─────────────────────────────────────┐
│ 🔔 Still thinking?                  │
│ You have 3 items worth €472         │
│ [Complete Purchase]                 │
└─────────────────────────────────────┘
```

---

## Testing (5 min)

1. Add a smartphone → verify cross-sell suggestions appear (earbuds + case)
2. Check that suggestions match the brand (Samsung phone → Samsung accessories)
3. Verify bundle appears if case is not in cart
4. Verify savings display shows correct math
5. Wait 30 seconds → verify abandonment nudge appears
6. Switch user profile → add item → verify different brand suggestions

---

## Acceptance Criteria

- [ ] Adding a phone shows "Frequently Bought Together" with brand-matched accessories
- [ ] Bundle suggestion appears with discount percentage and total savings
- [ ] Cart total shows subtotal, discount, and final total
- [ ] "You saved €X" displays when bundle/discount applies
- [ ] Abandonment nudge appears after 30s of no interaction
- [ ] Products already in cart are NOT suggested again
- [ ] Cart persists across channel switch (web ↔ mobile)
- [ ] `manage_cart` MCP tool returns suggestions in response (so chatbot can mention them)

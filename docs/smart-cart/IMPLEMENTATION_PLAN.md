# Smart Cart — Implementation Plan (Session Kickoff)

> **Spec:** [SPEC.md](./SPEC.md)  
> **Repo:** `E:\test\dtdl 5\oneshop-ai-engine`  
> **Scope:** Features 1–4 only (cross-sell, bundles, savings display, abandonment nudge)  
> **Approach:** Rules-based — no LLM required for Smart Cart core logic

---

## Current State vs Spec

| Feature | Spec | Current codebase | Gap |
|---------|------|------------------|-----|
| **1. Cross-sell** | Brand-matched "Frequently Bought Together" on add | Not implemented | **BUILD** |
| **2. Bundle detection** | Missing-category bundles with % discount | Partial — `_rule_bundles()` in `smart_cart_service.py` (phone+plan, phone+accessory) | **EXTEND** |
| **3. Savings display** | Subtotal, bundle discount, total, "You saved €X" | Partial — subtotal only in `SmartCartPanel.tsx` | **EXTEND** |
| **4. Abandonment nudge** | 30s idle toast | Different — leave-page recovery banner + 10% discount in `AbandonmentBanner.tsx` | **ADD** (keep existing recovery) |

### Architecture differences (adapt, don't rewrite)

| Spec assumes | This repo uses |
|--------------|----------------|
| SQLite `cart` + `products` tables | In-memory `session_store` + `products.json` catalog |
| `subcategory` field on products | `category` enum + `tags[]` (e.g. `"case"`, `"audio"`, `"charger"`) |
| `user_id` | `session_id` (omnichannel via `customer_id` link) |
| `manage_cart` MCP tool | REST: `/api/customer/cart/*` + `/api/intelligence/smart-cart` |
| EUR pricing | USD pricing |

---

## Implementation Tasks (~30–45 min)

### Backend (`backend/app/services/smart_cart_service.py`)

1. **Add `CO_PURCHASE_MAP`** — map `phone:Apple`, `phone:Samsung`, etc. to tag/category rules using existing catalog tags:
   - `phone:Apple` → tags `audio`+brand Apple, `case`, `charger`
   - `phone:Samsung` → tags `audio`+brand Samsung, `case`
2. **Add `get_cross_sell_suggestions(session_id, added_product)`** — return top 2 items not already in cart with `rate` + `reason`.
3. **Extend `BUNDLE_RULES`** — percentage-based discounts with `original_price`, `bundle_price`, `savings` (align with spec's Phone Essentials / Device+Plan bundles).
4. **Extend `SmartCartResponse` schema** — add `cross_sell_suggestions: list[CrossSellItem]`, `discount: float`, `total: float`.
5. **Wire into cart add** — optionally return suggestions from `POST /api/customer/cart/add` or keep single fetch via `/api/intelligence/smart-cart`.

### Frontend

1. **`SmartCartPanel.tsx`** — add "Frequently Bought Together" section with Add buttons.
2. **`SmartCartPanel.tsx`** — enhance bundle card (strikethrough prices, savings badge, Add Bundle).
3. **`SmartCartPanel.tsx`** — full totals block: subtotal, discount, total, "You saved $X".
4. **`IdleCartNudge.tsx`** (new) — 30s inactivity floating nudge; wire in `ShopPage.tsx`.
5. **`api.ts`** — extend `SmartCartResponse` + `CrossSellItem` types.

### Files to touch

```
backend/app/services/smart_cart_service.py   ← main logic
backend/app/models/schemas.py                ← CrossSellItem, extended SmartCartResponse
backend/app/routers/intelligence.py          ← pass through new fields
frontend/src/components/SmartCartPanel.tsx   ← UI
frontend/src/components/SmartCartPanel.css
frontend/src/components/IdleCartNudge.tsx    ← new
frontend/src/pages/ShopPage.tsx              ← wire nudge + refresh on add
frontend/src/api.ts                          ← types
```

---

## Tag → Subcategory mapping (for co-purchase rules)

Use existing product tags in `products.json`:

| Spec subcategory | Match via |
|------------------|-----------|
| earbuds | `tags` contains `audio` |
| cases | `tags` contains `case` |
| screen_protectors | (none in catalog — skip or use `case`) |
| plans | `category == plan` |
| chargers | `tags` contains `charger` |

---

## Test checklist (from spec)

1. Add Samsung phone → cross-sell shows Samsung Buds + case (not Apple)
2. Bundle appears when case/plan missing from cart
3. Savings math: subtotal − discount = total
4. Wait 30s idle → floating nudge appears
5. Items already in cart are not re-suggested
6. Switch to `/app?session_id=...` → same cart + suggestions persist

---

## Acceptance criteria

- [ ] Adding a phone shows brand-matched "Frequently Bought Together"
- [ ] Bundle suggestion shows discount % and savings
- [ ] Cart total shows subtotal, discount, final total
- [ ] "You saved $X" when bundle discount applies
- [ ] Idle abandonment nudge after 30s
- [ ] In-cart products excluded from suggestions
- [ ] Cart persists across web ↔ mobile session

# Demo Guardrails

OneShop ShopAssist + Smart Cart — safety boundaries for live demo.

## 1. Prompt injection & off-topic blocking

ShopAssist returns a fixed commerce boundary for attacks such as:

- Write a joke / poem / Python code
- Show system prompt / forget system prompt / ignore previous instructions
- Show tools / database / SQL queries
- Weather, news, recipes, jailbreak attempts

**Demo try:** "Write me a joke" → boundary message, cart unchanged.

## 2. No silent cart changes

- Chat proposes cart updates; user clicks **Allow & add** to confirm
- Smart Cart panel adds only on explicit button click
- Runtime guard raises if chat mutates cart without confirmation

**Demo try:** Ask to add a phone → proposal appears; cart count unchanged until Allow.

## 3. Catalog-grounded facts

- Recommendations validated against product catalog (stock, IDs)
- Smart Cart cross-sell and bundles use rules + profile, not LLM product picks
- Smart Cart copy is deterministic and cannot claim discounts, scarcity, shipping, or compatibility facts from an LLM
- No promotion is assumed unless a future trusted offer source supplies one

## 4. Smart Cart output validator

Before API response:

- Max 2 cross-sells, max 1 bundle
- Never suggest products already in cart
- Re-resolve every suggestion from the catalog and drop unknown/out-of-stock IDs
- Keep current-cart totals separate from proposed add-on prices
- Separate one-time device charges from monthly plan charges

## 5. Session / profile binding

- Personalization profile used only when session is linked to `recommendation:{user_id}`
- Prevents wrong profile influencing cross-sell on mismatched sessions

## 6. Omnichannel session

Same `session_id` keeps cart across OneShop web and OneApp mobile.

---

## 30-second demo script

> "Our assistant is commerce-bounded. Prompt attacks get a fixed refusal. Cart changes need explicit Allow. Products and prices come from the catalog. Smart Cart add-ons are rules-based, do not assume an offer, and keep one-time and monthly totals separate. Same session works across channels."

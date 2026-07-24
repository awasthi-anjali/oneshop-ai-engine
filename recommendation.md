# Personalized Recommendations — Integrated Implementation Audit

## Status

Implemented and verified for the OneShop hackathon demo on 2026-07-24.

This document describes the code that exists. It supersedes the upstream draft
that assumed 200 products, Chroma, 50 seeded users, and a 25 ms profile
recompute. Those assumptions do not match this repository.

## Actual scope

- Catalog: 18 in-memory demo products from the trusted backend catalog.
- Demo personas: five selectable profiles with intentionally different seeded
  interaction histories.
- Persistence: append-only recommendation interactions and computed profiles in
  a local SQLite database.
- Ranking: deterministic, diversified scoring over semantic retrieval, brand
  affinity, category affinity, price fit, catalog popularity, and recency.
- Updates: versioned polling; this implementation does not use SSE.
- Cross-channel continuity: the same profile can continue across the OneShop and
  OneApp demo surfaces.
- Exclusions: cart and wishlist state come from the authoritative session store
  and are removed from recommendation candidates.
- Explanations: deterministic prose and allow-listed reason codes derived from
  normalized score components. An LLM does not invent ranking facts.

## Trust boundaries

Trusted backend code owns:

- product identity, availability, prices, billing cadence, and catalog facts;
- candidate generation, hard exclusions, ranking, diversification, and score
  evidence;
- normalized interaction metadata and idempotent event acceptance;
- explicit current-request constraints passed into ShopAssist;
- promotion, discount, cashback, and savings claims;
- cart proposals, exact totals, confirmation, and idempotent mutation.

The model may help parse bounded shopping language and adapt presentation. It
cannot relax an explicit budget/platform requirement, reorder trusted results,
invent products or promotions, or mutate the cart.

## Implemented API

- `POST /api/recommendations/interactions`
- `GET /api/recommendations/{user_id}`
- `GET /api/recommendations/{user_id}/updates`
- `POST /api/chat`
- `POST /api/chat/cart/confirm`

Recommendation event IDs are idempotent. Metadata is allow-listed and bounded;
raw chat and arbitrary PII-shaped fields are rejected.

## Fresh integrated verification

- Backend: `82 passed in 9.47s`.
- Frontend: `6` files, `31` tests passed in `13.76s`.
- Production build: `234 modules transformed`, built in `2.60s`.
- Live profile divergence:
  - Dev: Pixel 8, OnePlus 12, Galaxy A54 5G.
  - Alex: Family Connect Plan, Data Only Plan, Galaxy A54 5G.
- Exact live attack sequence:
  `sugest me something under 300 dolalrs` → discount/deal → cashback retained
  the `$300` device ceiling, returned no catalog match, and disclosed that no
  validated promotion exists.
- ShopAssist responsive checks at 1440×900, 1024×768, and 375×812 reported
  `scrollWidth === clientWidth`; the mobile drawer and composer remained inside
  the viewport.
- Fresh merged-regression checks on 2026-07-25 confirmed that `iphone` returns
  only iPhone SE, iPhone 15 Pro, and MagSafe Charger instead of all 18 catalog
  items. A recommendation followed by the voice transcript `hay hello` kept the
  current need, returned a short greeting, and displayed no stale pick cards.

See `docs/recommendations/AUDIT.md` for the full evidence ledger and
`user-memory.md` for the behavioral-memory boundary.

## Honest limitations

- This is an 18-product demo, not evidence of production-scale retrieval.
- SQLite is local to one deployment and is not a distributed event store.
- Session/cart state, recent conversation turns, cart proposals, and
  idempotency caches are process-local.
- Versioned polling is not a push stream.
- The demo memory read/reset endpoints have no production authentication or
  ownership boundary.
- There is no offline learning, experiment framework, durable task queue, or
  multi-replica coordination.

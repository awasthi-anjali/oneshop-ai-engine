# Implementation Plan

## Architecture

1. Add a recommendation SQLite repository with `interactions` and derived `user_preferences`.
2. Seed five personas through the same append-only interaction path using real product IDs.
3. Compute profiles deterministically. Read cart/wishlist exclusions from the existing `SessionStore`; do not persist a second mutable copy.
4. Generate candidates through the existing catalog retrieval service with safe deterministic fallback.
5. Score, diversify, and explain from validated components and reason codes.
6. Add versioned REST tracking/recommendation endpoints plus a deterministic polling update path keyed by `user_id`, `session_id`, and channel.
7. Add a shared OneShop/OneApp profile switcher and a resilient recommendation client.
8. Feed only a bounded preference summary into ShopAssist as soft context after explicit constraints are applied.

## Ownership boundaries

- Backend/data: `backend/**` only, including SQLite, scoring, endpoints, ShopAssist integration, and backend tests.
- Frontend: `frontend/**` only, including switcher, tracking, real-time UI, evidence display, and frontend tests.
- Primary integration: conflict resolution, documentation, full regression gates.
- Independent verification: begins only after integration; adversarial API/browser checks and evidence capture, with no implementation ownership.

## Data rules

- `event_id` is globally unique and duplicate inserts return the existing result.
- `user_id` isolates profiles; `session_id` links current cart/wishlist and omnichannel state.
- Session store remains authoritative for current cart/wishlist. Recommendation events describe actions; they do not become competing state.
- Allowed metadata is normalized and bounded per event type.
- Impressions are neutral counters; only explicit positive actions affect affinity.

## Delivery order

1. Backend storage, seeds, scoring, API, versioned updates, and tests.
2. Frontend shared persona selection, client/hook, For You integration, tracking, and tests.
3. Cross-layer integration and full regression build.
4. Independent deterministic/adversarial evaluation and responsive browser evidence.
5. Update `AUDIT.md` only with observed results.

# Evaluation

## Deterministic checks

Run every ranking check at least twice and compare ordered product IDs and score components exactly.

| Gate | Evidence required |
|---|---|
| Persona divergence | Same query/catalog produces distinct top rankings for the five seeded profiles |
| Cold start | Unknown user receives stable popularity ordering |
| Cart exclusion | Every current cart product is absent |
| Wishlist exclusion | Every current wishlist product is absent when configured as an exclusion |
| Brand diversity | Returned list respects the documented per-brand cap |
| Channel continuity | OneShop interaction changes the same user's OneApp profile/ranking |
| User isolation | Events for user A do not change user B profile, version, or ranking |
| Idempotency | Repeated `event_id` creates one row and one profile update |
| No double tracking | One UI action emits one canonical event |
| Explanation grounding | Every reason code and sentence maps to product data or a nonzero score component |
| Metadata safety | Unknown keys, raw chat content, and overlong values are rejected or discarded |
| Real-time update | A tracked event advances a version and produces a testable update |

## Regression gates

- All backend tests.
- All frontend tests.
- Existing ShopAssist tests.
- Frontend production build.

## Browser evidence

Capture the existing light theme at:

- desktop: 1440 px wide;
- tablet: 1024 px wide;
- mobile: 375 px wide (OneApp and/or responsive OneShop as applicable).

Evidence must show the profile switcher, personalized `For You` ordering, grounded explanation/score details, and a usable failure state. Screenshots belong in `docs/recommendations/evidence/`.

## Claims policy

Report measured test counts, build output, deterministic ranking comparisons, and observed browser behavior only. Do not convert local test latency into scale or production-readiness claims.

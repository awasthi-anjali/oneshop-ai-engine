# Personalized Recommendations V1

## Outcome

Prove that five synthetic customers see measurably different, deterministic rankings from the same 18-product demo catalog on OneShop and OneApp. Interactions persist in SQLite, preference profiles are computed from evidence, and every explanation is derived from validated score components.

## Reality check

`recommendation.md` is directionally useful and operationally fictional:

- The repository has 18 JSON products, not a 200-product database.
- Retrieval is an optional OpenAI embedding cache with catalog keyword fallback, not Chroma.
- There are no 50 seeded users, MCP recommendation tools, Kafka, Redis, or production identity service.
- Cart, wishlist, view, customer-link, and channel continuity live in a process-local `SessionStore`.
- No evidence supports a 25 ms recompute claim or Telekom-scale readiness.

V1 therefore uses the real catalog and IDs, SQLite only for append-only recommendation interactions and computed profiles, and the existing session store as the sole cart/wishlist truth.

## Users and surfaces

Five catalog-grounded demo personas cover budget, premium technology, business/productivity, accessibility/value, and family/connectivity interests. A visible switcher is shared by OneShop and OneApp. The selected `user_id` is the durable personalization key; the existing `session_id` remains the shopping-state and channel-continuity key.

The main `For You` surface must show:

- deterministic personalized ordering;
- grounded reason codes and plain-language explanations;
- normalized component scores;
- visible update/failure state;
- cart and wishlist exclusions without copying their state into a competing store.

## Functional requirements

- Append-only SQLite events with client-supplied unique `event_id`; duplicate submissions are idempotent.
- Allow-listed event types and bounded metadata. Store normalized query/intent fields only, never unrestricted chat text or PII.
- Neutral impressions and explicit clicks. A 10-second non-click is not negative evidence.
- Computed profile: brand/category affinity, bounded price signal, recent views, cart/wishlist exclusions, last channel, channels used, and interaction counts.
- Candidate generation uses existing semantic retrieval where available and deterministic catalog/keyword fallback otherwise.
- Ranking includes normalized retrieval relevance, profile match, price match, popularity, and deterministic tie-breaking.
- Cart exclusion and brand diversity are enforced after scoring.
- Cold start falls back to deterministic catalog popularity.
- Provide GET recommendations, POST tracking, and a versioned real-time update stream.
- Use bounded preference context as a soft ShopAssist signal only. Explicit user constraints remain hard and cannot be relaxed.

## Non-goals

No Smart Cart expansion, checkout work, discounts, abandonment changes, new OneApp redesign, Chroma, MCP, production authentication, raw chat storage, or scale claims.

## Acceptance gates

Backend tests cover persistence, scoring, idempotency, user isolation, channel continuity, exclusions, diversity, cold start, streaming/version updates, and explanation grounding. Frontend tests cover switching, tracking once, updates, and failure fallback. Existing ShopAssist tests and the production build remain green. Desktop, tablet, and mobile light-theme screenshots are required before audit status can pass.

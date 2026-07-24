# Personalized Recommendations V1 Audit

## Verdict

**READY FOR PERSONALIZED RECOMMENDATIONS V1 DEMO — all defined verification gates pass.**

The V1 uses the actual 18-item catalog, persists append-only interaction events in SQLite, computes profiles, produces deterministic and diverse rankings, carries a profile across OneShop/OneApp, and derives explanations from normalized score components. The two failures found in the first independent pass were corrected and independently reverified in the live browser and API.

## Evidence ledger

| Gate | Status | Evidence |
|---|---|---|
| Backend API/data/scoring | Pass | Fresh combined regression passed `82` tests. Independent API probing returned five distinct persona top-three rankings, normalized scores/components, and at most two items per brand; merged catalog search now excludes zero-relevance products |
| SQLite persistence/idempotency | Pass | First event accepted at version 1; identical `event_id` rejected as duplicate at the same version; database inspection found zero duplicated event IDs |
| Isolation | Pass | Reusing user A's session ID for user B produced a different session and zero interactions |
| Versioned real-time updates | Pass | `/updates` returned `changed: false` before a new event and `changed: true`, version 2 after it; this is versioned polling, not SSE |
| Cold start | Pass | New user reported `cold_start: true`, retrieval method `popularity`, and every result had `POPULAR_COLD_START` |
| Cart/wishlist exclusion | Pass | Session cart `iphone-15-pro` and wishlist `google-pixel-8` were absent from 12 recommendations and surfaced in the computed profile exclusions |
| Persona divergence | Pass | All five personas had a different top-three ordering for query `phone`; browser switch Alex → Dev changed the visible first six from `Family Connect Plan, Data Only Plan, Samsung A54, iPhone SE, Pixel 8, AirPods Pro` to `Pixel 8, OnePlus 12, Samsung A54, S24 Ultra, iPhone 15 Pro, iPhone SE` |
| Channel continuity | Pass | Same profile/session continued across `oneshop` and `oneapp`; API profile and UI badge both showed `oneapp + oneshop` |
| Explanation grounding | Pass | Every audited reason code came from the declared allow-list; scores and all six components were in `[0,1]`; visible explanations referenced validated brand/category/query/price/recency evidence |
| Metadata privacy | Pass at API/storage boundary | Raw-chat metadata received 422; persisted audit rows contained only normalized `query`, `rec_position`, and `surface`; database search found no `raw_chat` or `@` metadata |
| ShopAssist hard constraints | Pass | Backend test sent an Apple preference with `Android under $500`; every result remained Android and at or below $500 |
| Frontend automated tests | Pass | Fresh merged-regression reverification: `6` files, `31` tests passed; includes exact/semantic search filtering, voice greeting auto-send, stale-card removal, compact ShopAssist behavior, exact proposal totals, and backend-controlled actions |
| Existing ShopAssist regression | Pass | Included in complete backend/frontend runs; no regression failures |
| Natural-language ShopAssist routing | Pass for tested attacks | Currency suffixes (`dollars`, `USD`, `bucks`), typo `sugest`, inherited phone context, promotion synonyms, greetings, thanks, and ambiguous AI classification are covered. Hard injection/service boundaries still precede AI and catalog facts remain deterministic |
| Production build | Pass | Fresh merged-regression `tsc -b && vite build`: `234 modules transformed`, built in `2.60s`; JS 340.75 kB (105.83 kB gzip), CSS 56.66 kB (10.00 kB gzip) |
| Frontend event tracking | Pass | Live browser load produced six HTTP 200 impression writes for six visible products, each with a product ID and exact metadata `{"surface":"for_you","visible":true}`. Clicking the first recommendation produced one HTTP 200 `rec_click` with `rec_position`/`surface`, followed by the intentional catalog `product_view`; no 422 remained |
| No double tracking | Pass | Reposting the captured browser `rec_click` event ID and a captured browser impression event ID each returned `accepted: false, duplicate: true`; SQLite retained one row per event ID |
| Responsive light theme | Pass | Desktop and tablet show the switcher, live For You, continuity, grounded explanations, and score components. Fresh 375 px evidence shows a full-width recommendation, complete explanation, reason codes, price/actions, and all six expanded score components; the former 400 px cap is gone |

## Commands and measured results

Run from the stated directories on 2026-07-24:

```text
backend> python -m pytest -q
........................................................................ [ 98%]
.                                                                        [100%]
82 passed in 9.47s

frontend> npm test -- --run
Test Files  6 passed (6)
Tests       31 passed (31)
Duration    13.76s

frontend> npm run build
234 modules transformed
built in 2.60s
```

The independent TestClient probe made 40 warmed recommendation requests for `user_011?query=phone&limit=6`: median **350.16 ms**, p95 **379.23 ms**, max **386.82 ms**. This is an in-process development measurement, not a production benchmark, but it decisively does not support the fictional 25 ms claim.

The corrected browser tracking observation was:

```text
6 visible recommendations -> 6 impression POSTs -> HTTP 200
1 recommendation click -> 1 rec_click POST -> HTTP 200
intentional product open -> 1 product_view POST -> HTTP 200
retry captured rec_click event_id -> accepted false, duplicate true
retry captured impression event_id -> accepted false, duplicate true
```

SQLite inspection of the accepted audit events showed normalized metadata:

```json
{"query":"camera phone","rec_position":0,"surface":"for_you"}
```

## Browser evidence

- `evidence/recommendations-desktop-1440.png` — Alex profile, live personalized For You, cross-channel badge, grounded explanation.
- `evidence/recommendations-tablet-1024.png` — Dev profile, visibly different ranking, expanded six-component score evidence.
- `evidence/recommendations-mobile-375.png` — responsive mobile profile switcher in the light theme.
- `evidence/recommendations-mobile-375-for-you.png` — corrected mobile For You layout with a full recommendation, grounded explanation, reason codes, and expanded semantic/brand/category/price/popularity/recency evidence.
- `evidence/shopassist-budget-discount-cashback-integrated.png` — exact typo/budget, discount/deal, and cashback follow-up sequence after merging current `origin/main`.
- `evidence/shopassist-integrated-desktop-1440.png`, `shopassist-integrated-tablet-1024.png`, and `shopassist-integrated-mobile-375.png` — post-merge ShopAssist layout and cart-confirmation evidence.
- `evidence/omnichannel-sync-single-integrated.png` — storefront after removing the duplicated `OmnichannelSyncBanner` render introduced during conflict resolution.
- `evidence/search-iphone-integrated-fixed.png` — live `iphone` search showing three relevant products rather than the full 18-product catalog.
- `evidence/shopassist-voice-hay-hello-fixed.png` — exact post-recommendation `hay hello` replay with the need retained, a short greeting, and no stale recommendation cards.

## Spec assumption roast

- “Ready for implementation” still arrived with four imaginary dependencies: a product DB, 200 products, Chroma, and 50 seeded users. V1 correctly uses what exists.
- “~25 ms” was decorative fiction. The only fresh measurement here is roughly 350 ms median in TestClient, and it must not be marketed as production performance either.
- A non-click remains neutral. The frontend now records a neutral impression only for each visible product and sends no invented negative signal.
- The metadata allow-list blocks raw chat and PII-shaped arbitrary fields, and production tracking now stays inside that contract.
- Session cart/wishlist remain authoritative rather than inventing a second mutable truth. Good.
- Explanation prose is deterministic and component-backed rather than LLM-authored. Good.
- Five synthetic users over 18 synthetic catalog items demonstrate a demo, not Telekom-scale readiness.

## Closure of first-pass findings

1. Production impression and `rec_click` payloads now match `RecommendationEventMetadata`; forbidden `product_ids` and `profile_version` fields are absent.
2. Browser/API evidence confirms accepted impressions and clicks plus idempotent duplicate retries.
3. The mobile max-height trap is removed and the 375 px recommendation/evidence interaction is usable.

## Research-informed discovery and ShopAssist verification

The final discovery hierarchy now separates ranking contexts instead of cloning the same rail:

- accessible one-row `For You`, `Phones`, `Tablets`, `Plans`, `Accessories`, and `Devices` tabs;
- three compact, category-aware top picks;
- a factual `Still looking for these?` continuation strip sourced from recent interactions;
- a primary `Suggested for {profile}` feed with full catalog as a secondary mode;
- a non-duplicative `Why these picks?` evidence rail;
- profile-ranked recommendations immediately when ShopAssist opens;
- request-constrained `Best match`, `Alternative`, and `Recommended plan` cards after chat;
- an explicit `View in shop` action instead of silently replacing the background catalog.

Live browser evidence showed Dev opening ShopAssist with collapsed `Pixel 8`, `OnePlus 12`, and `Galaxy S24 Ultra` pills while the composer remained visible. Selecting Pixel expanded one preview with two grounded evidence badges. The request `Android camera phone under $700 and a plan under $90 per month` replaced those starter pills with `Pixel 8` ($699), `Galaxy A54 5G` ($449), and `Unlimited Essential Plan` ($55/month), automatically expanded Best match, removed duplicate generated actions, and retained the explicit `View in shop` handoff. The header measured 60 px, generic catalog context and the drawer demo notice were absent, and an actual cart entry rendered the meaningful `Using your cart` context pill.

The independent adversarial pass scored the integrated experience **8.7/10** before the immediate-on-open chatbot enhancement. It verified five distinct persona top-three rankings, category-constrained tabs, exact ShopAssist handoff, and no horizontal overflow at 1024 px or 375 px. Its misleading `explicit interactions` wording finding was then corrected to the accurate `profile events`. Remaining honest gaps are content repetition between Top Picks/Continue/Suggested, stale session intent after profile switches, a low-position mobile evidence rail, and the lack of direct page-level automation for the new discovery hierarchy.

## Conversational-routing hardening

The judge-facing `AI load-bearing` claim no longer depends on a keyword-only
front door. Explicit off-topic, prompt-injection, and service requests are
still blocked deterministically first. Known commerce language uses a safe
fallback parser, while otherwise ambiguous language is offered to the bounded
need-parser model before ShopAssist rejects it.

The exact reported sequence was replayed in one live browser session. `sugest
me something under 300 dolalrs` produced an honest `no_match`, retained
`phone` and a `$300` device ceiling, and returned no fabricated product.
Discount and cashback follow-ups stayed inside the shopping boundary,
disclosed that no validated promotion exists, and preserved the hard budget.
The tests also cover `USD 300`, `300 bucks`, `budget is 500 dollars`,
promotion/rebate synonyms, contextual budget follow-ups, greeting/thanks
turns, and additional prompt-injection paraphrases.

The drawer now adopts the useful interaction patterns from Ask Magenta without
copying its unsupported account/identity flow: a branded assistant marker,
direct quick replies attached to clarifications, a fixed composer, and a
small AI-accuracy disclosure outside the message stream. It does not ask for
a name or other PII. At 375x812 the live drawer had zero page-level horizontal
overflow and the 151px composer remained fully inside the viewport.

## Behavioral-memory extension

ShopAssist now combines two intentionally separate, bounded inputs:

- the existing computed interaction profile supplies “what they like”: at most two brands/categories, a bounded price centroid, five recent product IDs, and cart/wishlist exclusions;
- durable SQLite behavioral memory supplies “how they decide”: validated price sensitivity, decision/negotiation/communication styles, explicit rejections, bounded objections/triggers/trust signals, and normalized future intent.

A Dreaming Agent pass is triggered after every five user turns. It receives only the last 12 process-local turns after 300-character bounding and email/phone redaction. Its Pydantic contract rejects extra fields. More importantly, the model cannot create product or brand exclusions: those are accepted only when deterministic clause-level extraction finds explicit rejection wording. The update has a stable ID, is append-claimed idempotently, and persists a versioned structured record; raw chat is not written to either memory table.

The system prompt is split by authority instead of becoming one giant persuasion prompt:

1. the need-parser prompt extracts a constrained shopping need;
2. the Dreaming Agent prompt extracts only allowed behavioral fields and treats transcript/memory as untrusted data;
3. the response-composer prompt receives server-derived preference/memory context plus already validated products and reasons.

Behavioral memory may alter tone, brevity, value framing, reason emphasis, objection acknowledgement, and whether the backend offers comparison. It cannot relax explicit constraints, change the selected products, invent facts/prices/discounts, mutate cart state, or manufacture explanation evidence. The frontend now renders Compare only when the backend provides the validated `COMPARE` action.

Fresh automated evidence covers durable reopen, idempotency, isolation, the memory GET/reset API, absence of raw-chat storage, neutral treatment of missing price evidence, clause-scoped rejection, the five-turn trigger, PII redaction/bounding, explicit-current-request override, unchanged product IDs under presentation adaptation, blocking model-authored hard exclusions, bounded system-prompt injection, rejection of an invented composed product/price, and deterministic “something like last time” resolution from structured intent.

Honest remaining gaps:

- the trigger uses an in-process background task, not a durable job queue; SQLite memory survives restarts after a completed update, but an update in flight can be lost if the process dies;
- recent chat turns remain process-local, so another application replica cannot continue the same conversational window;
- the demo API has no authenticated ownership boundary, so its memory read/reset endpoints are not production-ready;
- purchase ownership is deliberately not inferred from chat and has not yet been wired from a trusted completed-order event;
- there is no offline learning, experimentation framework, or evidence for large-scale performance. Calling this a “self-learning production memory platform” would still be résumé-driven fiction.

The live-log follow-up closed two visible drawer defects: discount/deal/coupon language now remains inside the shopping boundary and produces an explicit no-validated-offer answer, and recommendation pills are welcome-state/current-answer content rather than a persistent stale shelf. They disappear as soon as the next user turn begins. Switching demo identities also clears ShopAssist conversational state to prevent stale-profile UI leakage.

The memory-precedence follow-up now treats explicit current-turn style as authoritative without rewriting durable behavioral memory. Live Dev verification with stored `researcher/detailed` memory and “Just tell me the best Android phone under $800 for travel” returned one concise Best match sentence, no Compare action, and unchanged deterministic product ranking.

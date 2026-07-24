# ShopAssist Current-State Audit

## Audit rule

Status values are `Missing`, `Partial`, and `Verified`. A rendered component is
not verified until its behavior and failure cases pass the evaluation suite.

## Current roast

The implemented ShopAssist slice now behaves like a bounded commerce decision
guide in the observed golden journeys. Remaining claims must stay narrow:

- The visual release gate is still `Partial`: 1440px, 1024px, and 375px
  layouts were inspected, but a real mobile software keyboard was not
  emulated. Checkout-over-drawer was supported by observed CSS stacking
  (`1100 > 900`), not a simultaneous live interaction.
- Sessions remain process-local. Raw turns are capped at 12, but session
  records themselves have no production persistence or eviction policy.
- Provider failures were simulated; no live OpenAI outage was induced.
- The OneTel/USD catalog is synthetic demo data. The UI labels it honestly,
  but this is not current Telekom inventory, pricing, eligibility, or
  availability.
- The pre-existing Smart Cart still emits scarcity, savings, and free-shipping
  copy without reliable evidence. It was explicitly outside the ShopAssist V1
  implementation boundary, so its trust failure remains.
- OneApp UI and consistent production omnichannel persistence remain deferred
  non-goals. A request enum is not an implemented channel experience.

## Observed requirement status

| Requirement | Status | Observed evidence |
|---|---|---|
| Embedded drawer; no separate tab | Verified | Browser inspection at 1440/1024/375; frontend renders OneShop continuously |
| OneShop state retained while assistant opens | Verified | G15 live: six messages, draft, eight need chips, three picks, comparison/proposal, and context survived close/reopen |
| Commerce-only boundary | Verified | G11, G12, and G17 deterministic tests |
| Natural-language front door | Verified for tested attacks | Ambiguous turns can reach the bounded AI parser; deterministic fallback covers currency suffixes, budget paraphrases, typo/context continuity, and promotion synonyms without relaxing hard boundaries |
| Structured shopping need | Verified | Multi-turn test and live editable chips |
| Grounded phone-and-plan shortlist | Verified | G01-G09 assertions and live primary journey |
| At most three recommendations | Verified | Response schema cap plus golden assertions |
| Comparison of two validated phones | Verified | G10 and live comparison table; Pixel 8 vs OnePlus 12, $100 difference |
| Proposal before cart mutation | Verified | G13 live cart stayed at zero; G14 one explicit request changed it to two exact items |
| Provider fallback without crash | Verified | Timeout and malformed-output tests return normal fallback responses |
| One canonical prompt | Verified | Code inspection: one prompt module and one bounded parser call path |
| Currency and billing cadence | Verified | Backend contract tests and live proposal totals (`$699` once, `$85/month`) |
| Accessible responsive light theme | Partial | Three viewports, sampled AA token contrast, visible focus ring, no app overflow, mobile input visible; real software keyboard and simultaneous checkout layering not exercised |
| Automated evaluation evidence | Verified | Fresh merged-regression run: 82 backend tests and 31 frontend tests pass; production build transforms 234 modules |
| OneApp UI and production persistence | Missing | Explicitly deferred from V1 |

## Baseline verification

- `npm run build`: passes before V1 changes.
- `python -m compileall -q backend/app`: passes before V1 changes.
- Automated tests: none found.
- Rendered UI: separate Shop and ShopAssist buttons confirmed; ShopAssist
  replaces the catalog and advertises add-to-cart and checkout commands.

The implementation task updates this table only after observed evidence.

## V1 verification evidence

Commands observed after integration:

- `cd frontend && npm run build` — exit 0; 215 modules transformed.
- `cd frontend && npm test` — exit 0; 1 file, 4 tests passed.
- `python -m pytest backend -q` — exit 0; 28 tests passed.
- `python -m compileall -q backend/app backend/tests` — exit 0.
- `git diff --check -- backend frontend` — exit 0; line-ending notices only.
- Live isolated `POST /api/chat` contract check — `message` observed as a
  JSON string after the verifier found and rejected the legacy object shape.

Golden status:

| Scenario | Result | Evidence |
|---|---|---|
| G01-G09 | Pass | Deterministic IDs, budgets, reasons, and honest no-match assertions |
| G10 | Pass | Two validated phones and exact `$100` price difference |
| G11-G12 | Pass | Unsupported and Frag Magenta service routing |
| G13 | Pass | Proposal rendered; chat cart delta remained zero |
| G14 | Pass | Exactly one confirmation request; cart became the two proposed items |
| G15 | Pass | Live close/reopen persistence and focus return |
| G16-G17 | Pass | Provider fallback and prompt-injection boundary tests |

Screenshot evidence is stored in `docs/shopassist/evidence/`, including the
desktop proposal, 1024px drawer, 375px sheet, and product-modal layering.

## Conversational-routing and Magenta-pattern follow-up

Fresh merged-regression evidence through 2026-07-25:

- `python -m pytest -q` - exit 0; 82 tests passed in 9.47s.
- `npm test -- --run` - exit 0; 6 files and 31 tests passed in 13.76s.
- `npm run build` - exit 0; 234 modules transformed in 2.60s.
- The reported `$300` typo/paraphrase returns an honest phone no-match instead
  of `unsupported`.
- Discount, deal, cashback, promotion, and rebate turns remain in scope but
  never manufacture an offer.
- Greetings and thanks no longer produce the generic unsupported response.
- Additional prompt-injection paraphrases produce no recommendations, tools,
  or cart mutation.
- The live 375x812 drawer had no horizontal overflow and kept the composer
  fully visible. It now uses direct quick replies, a branded assistant marker,
  and a compact AI-accuracy disclosure without collecting identity or PII.
- The integrated browser run also covered greeting, thanks, ambiguous travel
  language, prompt injection, an exact Pixel 8 proposal, explicit confirmation,
  and a safe post-mutation recommendation-refresh fallback. Proposal replay and
  duplicate-mutation resistance remain covered by backend idempotency tests.
- Measured page widths were exact at 1440, 1024, and 375 pixels. The mobile
  drawer measured 375x812 and its 151-pixel composer remained fully inside the
  viewport.
- The duplicate omnichannel sync banner introduced during conflict resolution
  was traced to two adjacent `OmnichannelSyncBanner` renders; the second render
  was removed and the frontend tests/build were rerun.
- Voice-originated greeting variants (`hay hello`, `hey hello`, punctuation and
  casing variants) now run before inherited shopping context. Live replay after
  an Android-camera recommendation retained the need chips, returned the short
  greeting, and removed stale recommendation cards. Shopping-bearing near
  matches such as `hey, show me an Android phone under $700` remain shopping.

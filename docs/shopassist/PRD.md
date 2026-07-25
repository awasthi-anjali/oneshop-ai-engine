# ShopAssist V1 Product Requirements

## Status

Planned. This document is the product source of truth for the first complete
ShopAssist vertical slice.

## Product thesis

ShopAssist is a bounded purchase guide embedded in OneShop. It turns an
unclear telecom need into a small, justified, purchasable phone-and-plan
shortlist. It is not a general chatbot, a service bot, or an autonomous
checkout agent.

The current separate ShopAssist tab interrupts shopping and invites generic
chat. V1 replaces it with a contextual drawer while keeping products visible.

## User and job

The primary user is a customer who knows the outcome they want, but does not
know which device specifications or plan attributes express that need.

Job to be done:

> Help me choose a compatible phone and plan for my use case and budgets,
> explain the trade-offs, and let me confirm the exact cart change.

## V1 outcome

A customer can:

1. Open ShopAssist without leaving the catalog.
2. Describe a phone-and-plan need in natural language.
3. Answer at most one concise clarification turn for a normal journey.
4. See and edit the understood need as visible chips.
5. Receive at most two phone choices and one plan, all grounded in catalog
   data and hard constraints.
6. Compare the two phones while the shopping page remains visible.
7. Review an exact phone-and-plan cart proposal.
8. Explicitly confirm the proposal before the cart changes.

## Experience requirements

| ID | Requirement |
|---|---|
| SA-FR-01 | OneShop remains mounted while ShopAssist opens and closes. |
| SA-FR-02 | ShopAssist has no main navigation tab. |
| SA-FR-03 | Desktop uses a right drawer; mobile uses a full-width sheet. |
| SA-FR-04 | Entry points include Help me choose, product detail, next-best action, and cart. |
| SA-FR-05 | Product context is visible and removable; opening it does not auto-send a message. |
| SA-FR-06 | The assistant stores a structured shopping need, not only chat prose. |
| SA-FR-07 | A normal journey uses no more than one clarification turn. |
| SA-FR-08 | The main catalog switches to ShopAssist Picks and shows at most three products. |
| SA-FR-09 | Every price, feature, stock, and plan statement comes from validated catalog data. |
| SA-FR-10 | A chat request never mutates cart or starts checkout. |
| SA-FR-11 | Cart mutation occurs only after an explicit UI confirmation. |
| SA-FR-12 | Closing and reopening preserves the conversation, draft, need, and results. |
| SA-FR-13 | Unrelated requests receive a commerce boundary response. |
| SA-FR-14 | Billing, account, network, and service requests receive a generic customer-support handoff. |
| SA-FR-15 | No exact match is stated honestly; constraints are not silently relaxed. |
| SA-FR-16 | The UI clearly labels the local catalog as synthetic demo data. |

## Primary journey

1. Customer selects **Help me choose**.
2. Drawer opens with three focused starts: Find a phone, Choose a plan, and
   Build phone + plan.
3. Customer says: "I need a phone and plan for travel photography."
4. ShopAssist asks: "What is your phone budget and monthly plan budget?"
5. Customer answers: "Android, phone under $800 and plan under $90."
6. Need chips show Photography, Android, Device <= $800, Plan <= $90, and
   International travel.
7. Main catalog shows Google Pixel 8, OnePlus 12, and Unlimited Plus Plan with
   validated reasons.
8. Customer compares Pixel 8 and OnePlus 12.
9. ShopAssist proposes Pixel 8 plus Unlimited Plus Plan. The cart is unchanged.
10. Customer confirms. The existing cart endpoint applies exactly one bundle
    mutation and OneShop refreshes.

## Supported intents

- Discover a phone, plan, or phone-and-plan combination.
- Refine preferences and budgets.
- Explain a grounded recommendation.
- Compare two recommended phones.
- Ask a factual question about a visible product.
- Propose an exact cart addition.

## Unsupported and routed intents

- General knowledge, writing, coding, entertainment, and open-web questions:
  decline and restate the commerce boundary.
- Billing, account, contract support, network faults, and technical support:
  return a service handoff.
- Payment and checkout: outside V1.
- Unverified discounts, availability, compatibility, eligibility, or savings:
  never claim them.

## Non-functional requirements

- Provider failures return a safe deterministic fallback, not an HTTP 500.
- Keyboard users can open, operate, and close the drawer; focus returns to the
  originating control.
- Text and interactive controls meet WCAG AA contrast in the light theme.
- Mobile input remains visible when the software keyboard opens.
- A response contains no more than three recommendations.
- User, catalog, and page text are treated as untrusted data.

## Success measures

| Measure | V1 target |
|---|---:|
| Hard-constraint satisfaction on golden cases | 100% |
| Catalog claim grounding | 100% |
| Silent chat-triggered cart mutations | 0 |
| Boundary and service-routing correctness | 100% |
| Successful primary journeys | At least 80% |
| Recommendations per result | At most 3 |
| Clarification turns for normal cases | At most 1 |
| Drawer/session continuity | 100% |

## Judging evidence

- **AI load-bearing (30%)**: natural language becomes structured telecom
  preferences and a useful clarification, not keyword-only search.
- **Working prototype (25%)**: one live discovery-to-confirmation journey.
- **Scoping (25%)**: a completed phone-and-plan slice instead of unfinished
  bonus features.
- **DTDL fit (10%)**: OneShop integration, telecom decisions, channel context,
  and an explicit sales/service boundary.
- **Presentation (10%)**: visible before/after, grounded evidence, failure
  handling, and honest limitations.

## Non-goals

Smart Cart redesign, discounts, abandonment recovery, checkout, payments,
real account actions, real eligibility or inventory integration, OneApp UI,
voice, MCP, product-level multi-agent architecture, vector databases,
continuous learning, and A/B testing.

# ShopAssist V1 Implementation Plan

## Delivery rule

Implement the complete vertical slice, but keep each change independently
verifiable. Do not fix unrelated Smart Cart, checkout, image, or repository
issues.

## Workstream 1: embedded drawer and light theme

- Remove the Shop/ShopAssist route switch and always render OneShop.
- Make `ShopPage` the owner of session ID, drawer state, launch context,
  assistant results, comparison state, and cart refresh.
- Refactor the current chat page into an always-mounted `ShopAssistDrawer`.
- Add a Help me choose control near the catalog heading and an Ask ShopAssist
  control in product detail. Next-best actions open an editable draft.
- Desktop drawer width is 420px and overlays the existing recommendation rail.
  Mobile uses a full-width, full-height sheet.
- Keep messages, draft, need profile, scroll, and results when the drawer
  closes.
- Main catalog has `All Products` and `ShopAssist Picks` modes. Picks remain
  until the customer explicitly returns to all products.
- Replace the dark palette with a light commerce theme:
  - page background `#f6f7f9`
  - primary surfaces `#ffffff`
  - secondary surfaces `#f1f3f5`
  - borders `#d9dde3`
  - primary text `#1b1f23`
  - muted text `#5f6670`
  - Telekom-style magenta accent `#e20074`
  - accent hover `#bd0061`
  - focus ring `#7c3aed`
  - success `#15803d`, warning `#b45309`, error `#b91c1c`
- Replace dark-only hard-coded card/image/modal colors with tokens. Modal
  backdrops remain translucent dark overlays.
- Verify WCAG AA contrast, visible keyboard focus, hover/disabled states, and
  readable assistant/user bubbles.

## Workstream 2: public contracts

Preserve `POST /api/chat` and existing session/channel compatibility.

### Request

```text
ChatRequest
  message: string, 1..1000 characters
  session_id?: string
  channel: oneshop | oneapp
  page_context?:
    surface: catalog | product | cart
    entry_point: help_me_choose | product_detail | next_best_action | cart
    product_id?: string
    visible_product_ids?: string[<=20]
```

### Response

```text
ChatResponse
  session_id
  status: clarifying | recommended | no_match | unsupported |
          service_handoff | error
  message
  need_profile:
    categories[]
    use_cases[]
    device_budget_max?
    monthly_budget_max?
    platform?
    roaming_required?
    lines?
    must_haves[]
    nice_to_haves[]
  recommendations[<=3]:
    product
    slot: primary_phone | alternative_phone | recommended_plan
    reason_codes[]
    reason
  comparison?
  actions[]:
    type: REFINE | COMPARE | OPEN_PRODUCT |
          PROPOSE_ADD_BUNDLE | HANDOFF_SERVICE
    label
    product_ids[]
  mode: ai | fallback
```

Temporarily retain `suggested_actions`, `cart_updated`, and `open_checkout`.
The two mutation flags are always false for chat. Product records gain
`currency` and `billing_period: one_time | monthly`.

## Workstream 3: bounded recommendation engine

- Keep one canonical commerce assistant prompt in one module.
- Use `AsyncOpenAI` with an application timeout and at most three provider/tool
  rounds.
- The model classifies intent and extracts a validated shopping-need patch.
- Merge the patch into per-session structured state and retain at most the last
  12 raw user/assistant turns.
- Never persist system prompts, tool transcripts, page context, or appended
  internal annotations as user messages.
- For a phone-and-plan request missing both budgets, ask one concise question
  requesting device and monthly budgets.
- Deterministic code filters catalog candidates by category, stock, device
  budget, monthly budget, roaming, data, and platform.
- Deterministic code creates reason codes such as
  `WITHIN_DEVICE_BUDGET`, `WITHIN_MONTHLY_BUDGET`, `CAMERA_MATCH`,
  `ROAMING_MATCH`, `DATA_MATCH`, and `PLATFORM_MATCH`.
- Validate all product IDs and factual explanation inputs before returning
  them. Never trust model-authored price, stock, eligibility, or savings.
- Return no more than two phones and one plan.
- Remove add-to-cart, add-bundle, recovery, and checkout tools from the model.
- A `PROPOSE_ADD_BUNDLE` action contains validated product IDs. Its UI button
  calls the existing explicit bundle endpoint and then refreshes session and
  intelligence state.

## Workstream 4: failure policy

- Invalid message, channel, page surface, or referenced product returns 422.
- OpenAI timeout, rate limit, outage, or malformed output returns the normal
  response schema with `mode: fallback`.
- Off-topic or prompt-injection requests return `unsupported` with no product
  or mutation action.
- Billing, account, service, and fault requests return `service_handoff`.
- No exact match returns `no_match`; no constraint is relaxed automatically.
- Invalid or stale candidate IDs are discarded. If none remain, use the
  deterministic no-match path.
- Serialize concurrent turns for the same session to preserve ordering.

## Workstream 5: result and confirmation UI

- Drawer shows the conversation, editable need chips, status, retry state, and
  typed actions.
- The main catalog renders the three picks with reason badges.
- Comparison uses only the two validated phone choices.
- The proposal card lists the exact phone, plan, billing cadence, and totals
  without inventing a discount.
- Confirmation invokes exactly one explicit bundle mutation. Repeated clicks
  while loading are blocked.
- Customer-facing errors never mention backend ports or implementation details.

## Review boundary

Leave changes uncommitted and unpushed. Stop with a complete diff, test results,
screenshots, remaining failures, and explicit assumptions for owner review.

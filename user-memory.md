# ShopAssist Behavioral Memory — Integrated Implementation Audit

## Status

Implemented and verified for the OneShop hackathon demo on 2026-07-24.

Behavioral memory is deliberately separate from the recommendation interaction
profile:

- the recommendation profile represents bounded evidence about what a person
  tends to like;
- behavioral memory represents bounded evidence about how they make shopping
  decisions.

## Stored contract

SQLite persists a versioned structured record containing only:

- price sensitivity;
- decision, negotiation, and communication style;
- explicit rejected product IDs and brands;
- bounded objections, purchase triggers, and trust signals;
- normalized future intent;
- update count and timestamp.

List and text sizes are capped by Pydantic validators. Extra fields are
rejected. Raw chat is not stored in the memory tables.

## Update flow

After every five user turns, a background dreaming pass receives at most the
last 12 process-local turns. Each turn is capped at 300 characters and
email/phone-shaped text is redacted before model use.

The model may propose only the structured allow-listed patch. Product and brand
rejections are accepted only when deterministic clause-level extraction finds
explicit rejection wording. A stable update ID is append-claimed so retries are
idempotent.

## Authority and precedence

Current explicit requirements always override durable memory.

Memory may influence:

- tone, brevity, and amount of detail;
- value framing and ordering of already-grounded reasons;
- acknowledgement of objections;
- whether a trusted comparison action is offered.

Memory may not:

- relax budget, platform, category, roaming, or other hard constraints;
- select or reorder products;
- change prices, stock, compatibility, promotions, or score evidence;
- infer ownership from chat;
- mutate the cart;
- authorize a cart mutation without an exact backend proposal and explicit
  confirmation.

## Fresh integrated verification

The `73`-test backend run covers durable reopen, idempotent updates, user
isolation, GET/reset, absence of raw-chat storage, neutral missing-price
evidence, clause-scoped rejection, the five-turn trigger, PII redaction and
bounding, current-request precedence, unchanged product IDs under presentation
adaptation, rejected model-authored hard exclusions, prompt-injection bounding,
invented-product/price rejection, and structured “something like last time”
resolution.

Frontend and browser verification also confirmed that trusted backend actions
control comparison and cart confirmation, and that switching demo identities
clears stale ShopAssist conversational state.

## Honest limitations

- Completed memory writes survive restarts in SQLite, but the dreaming task is
  an in-process background task and can be lost if the process stops mid-update.
- Recent conversation turns are process-local and cannot continue across
  replicas.
- Cart proposals and confirmation idempotency caches are process-local.
- The demo API has no production authentication/ownership boundary.
- There is no durable job queue, distributed lock, offline learning, or
  production-scale performance evidence.

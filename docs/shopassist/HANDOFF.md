# ShopAssist V1 Implementation Handoff

## Objective

Implement the complete embedded phone-and-plan ShopAssist defined by the PRD,
including the consumer light theme, structured need elicitation, grounded
recommendations, comparison, and explicit cart confirmation.

## Required implementation workflow

The primary implementation task should use bounded subagents:

1. A frontend subagent owns the light theme, embedded drawer, state
   synchronization, reactive catalog, comparison, accessibility, and frontend
   tests.
2. A backend subagent owns schemas, the canonical prompt, structured need
   state, deterministic grounding, safe failure handling, and backend tests.
3. After integration, an independent verifier runs the full suite, inspects
   desktop/mobile UI, attacks unsupported claims, and updates `AUDIT.md` only
   from observed evidence.

Agents must not edit the same files concurrently without explicit ownership.

## Implementation-task prompt

> Work only in `D:\dtdl-ai-hackathon\oneshop-ai-engine`. Implement the complete
> ShopAssist V1 in `docs/shopassist/PRD.md` and
> `docs/shopassist/IMPLEMENTATION_PLAN.md`, including the accessible light
> theme. Use bounded frontend and backend subagents with non-overlapping file
> ownership, then use an independent verification subagent. Evaluate every
> slice against `docs/shopassist/EVALUATION.md`; update `AUDIT.md` only from
> evidence. Keep roasting unsupported claims and incomplete behavior. Do not
> implement Smart Cart redesign, discounts, abandonment, payment, OneApp UI,
> voice, MCP, product multi-agent architecture, vector DB, or unrelated
> cleanup. Preserve unrelated changes and secrets. Do not commit, push, or
> create a PR. Stop with local changes ready for the owner, and report changed
> files, test/build commands and results, screenshots, remaining failures,
> assumptions, and `git status --short`.

## Required commands

At minimum:

```powershell
python -m compileall -q backend/app
python -m pytest backend/tests -q
cd frontend
npm run test -- --run
npm run build
```

Run deterministic golden scenarios and browser checks from `EVALUATION.md`.

## Review gate

The owner performs final visual inspection, diff review, and Git actions.
Implementation is not authorized to commit or push.

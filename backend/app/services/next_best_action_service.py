import json
import re
from collections.abc import Iterable
from typing import Any

from app.config import settings
from app.models.schemas import NextBestAction
from app.services.ai_client import get_openai_client
from app.services.customer_context import build_customer_context, get_funnel_stage

SAFE_ACTION_LABELS = {
    "browse_phones": "Browse phones",
    "compare_brands": "Compare phone brands",
    "compare_top": "Compare matching phones",
    "view_plans": "Browse mobile plans",
    "add_plan": "Compare plan options",
    "complete_cart": "Review wishlist items",
    "review_cart": "Review cart",
    "checkout": "Start demo checkout",
    "add_accessory": "Browse compatible accessories",
    "explore": "Explore products",
}

RULE_ACTIONS: dict[str, list[tuple[str, str]]] = {
    "new": [
        ("browse_phones", SAFE_ACTION_LABELS["browse_phones"]),
        ("compare_brands", SAFE_ACTION_LABELS["compare_brands"]),
    ],
    "browsing": [
        ("compare_top", SAFE_ACTION_LABELS["compare_top"]),
        ("view_plans", SAFE_ACTION_LABELS["view_plans"]),
    ],
    "wishlisted": [
        ("add_plan", SAFE_ACTION_LABELS["add_plan"]),
        ("complete_cart", SAFE_ACTION_LABELS["complete_cart"]),
    ],
    "cart": [
        ("checkout", SAFE_ACTION_LABELS["checkout"]),
        ("add_accessory", SAFE_ACTION_LABELS["add_accessory"]),
    ],
}

NBA_PROMPT = """Given customer shopping context and funnel stage, suggest 2-3 next best actions.
Return JSON: {"actions": [{"action": "one allowlisted action id", "priority": 1}]}
Allowed action ids: browse_phones, compare_brands, compare_top, view_plans, add_plan,
complete_cart, review_cart, checkout, add_accessory, explore.
The backend supplies all user-facing labels. Checkout is a simulated demo checkout.
Never claim savings, discounts, security, payment, eligibility, or compatibility."""


def _normalize_action_id(value: Any) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")
    checkout_markers = ("checkout", "place_order", "complete_purchase")
    if any(marker in normalized for marker in checkout_markers):
        return "checkout"
    return normalized if normalized in SAFE_ACTION_LABELS else "explore"


def sanitize_next_best_actions(raw_actions: Iterable[Any]) -> list[NextBestAction]:
    """Use AI only to select an action; trusted backend copy describes the action."""
    actions: list[NextBestAction] = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_actions):
        if len(actions) >= 3:
            break
        if isinstance(raw, NextBestAction):
            raw_action = raw.action
            raw_priority = raw.priority
        elif isinstance(raw, dict):
            raw_action = raw.get("action")
            raw_priority = raw.get("priority", index + 1)
        else:
            continue

        action = _normalize_action_id(raw_action)
        if action in seen:
            continue
        seen.add(action)
        try:
            priority = max(1, int(raw_priority))
        except (TypeError, ValueError):
            priority = index + 1
        actions.append(
            NextBestAction(
                action=action,
                label=SAFE_ACTION_LABELS[action],
                priority=priority,
            )
        )
    return actions


def get_next_best_actions(session_id: str) -> tuple[str, list[NextBestAction], bool]:
    stage = get_funnel_stage(session_id)
    client = get_openai_client()

    if client:
        context = build_customer_context(session_id)
        try:
            response = client.chat.completions.create(
                model=settings.openai_model,
                reasoning_effort=settings.openai_reasoning_effort,
                messages=[
                    {"role": "system", "content": NBA_PROMPT},
                    {"role": "user", "content": json.dumps(context)},
                ],
                response_format={"type": "json_object"},
                temperature=0.5,
            )
            data = json.loads(response.choices[0].message.content or "{}")
            actions = sanitize_next_best_actions(data.get("actions", []))
            if actions:
                return stage, actions, True
        except Exception:
            pass

    rules = RULE_ACTIONS.get(stage, RULE_ACTIONS["new"])
    actions = [
        NextBestAction(action=a, label=label, priority=i + 1)
        for i, (a, label) in enumerate(rules)
    ]
    return stage, actions, False

import json

from app.config import settings
from app.models.schemas import NextBestAction
from app.services.ai_client import get_openai_client
from app.services.customer_context import build_customer_context, get_funnel_stage

RULE_ACTIONS: dict[str, list[tuple[str, str]]] = {
    "new": [
        ("browse_phones", "Explore top-rated phones"),
        ("compare_brands", "Compare iPhone vs Samsung"),
    ],
    "browsing": [
        ("compare_top", "Compare top 3 phones for camera"),
        ("view_plans", "See matching mobile plans"),
    ],
    "wishlisted": [
        ("add_plan", "Add a plan — save $15/mo bundled"),
        ("complete_cart", "Move wishlist items to cart"),
    ],
    "cart": [
        ("checkout", "Review your cart and continue checkout"),
        ("add_accessory", "Add a case or earbuds to your order"),
    ],
}

NBA_PROMPT = """Given customer shopping context and funnel stage, suggest 2-3 next best actions.
Return JSON: {"actions": [{"action": "snake_case_id", "label": "Short user-facing label", "priority": 1}]}
Actions should guide conversion: compare, add plan, checkout, bundle, etc."""


def get_next_best_actions(session_id: str) -> tuple[str, list[NextBestAction], bool]:
    stage = get_funnel_stage(session_id)
    client = get_openai_client()

    if client:
        context = build_customer_context(session_id)
        try:
            response = client.chat.completions.create(
                model=settings.openai_model,
                messages=[
                    {"role": "system", "content": NBA_PROMPT},
                    {"role": "user", "content": json.dumps(context)},
                ],
                response_format={"type": "json_object"},
                temperature=0.5,
            )
            data = json.loads(response.choices[0].message.content or "{}")
            actions = [
                NextBestAction(
                    action=a.get("action", "explore"),
                    label=a.get("label", "Explore products"),
                    priority=a.get("priority", i + 1),
                )
                for i, a in enumerate(data.get("actions", [])[:3])
            ]
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

import json

from app.config import settings
from app.models.schemas import RecommendationItem
from app.services.ai_client import get_openai_client
from app.services.customer_context import build_customer_context
from app.services.product_catalog import catalog

RECOMMEND_PROMPT = """You are a commerce recommendation AI. Given customer signals and candidate products,
pick the best recommendations and write a personalized "why" reason for each (1 sentence, friendly).

Return JSON:
{
  "recommendations": [
    {"product_id": "id-from-candidates", "reason": "Why this fits the customer"}
  ]
}

Only use product_ids from the candidates list. Pick up to 6. Prioritize cross-sell (phone→plan→accessories)."""


def enhance_with_ai(
    session_id: str,
    candidates: list[RecommendationItem],
    limit: int = 6,
) -> list[RecommendationItem]:
    client = get_openai_client()
    if not client or not candidates:
        return candidates[:limit]

    candidate_data = [
        {
            "product_id": r.product.id,
            "name": r.product.name,
            "category": r.product.category.value,
            "brand": r.product.brand,
            "price": r.product.price,
            "tags": r.product.tags,
            "rule_score": r.score,
        }
        for r in candidates[:12]
    ]
    context = build_customer_context(session_id)

    try:
        response = client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": RECOMMEND_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps({"customer": context, "candidates": candidate_data}),
                },
            ],
            response_format={"type": "json_object"},
            temperature=0.4,
        )
        data = json.loads(response.choices[0].message.content or "{}")
        by_id = {r.product.id: r for r in candidates}
        enhanced: list[RecommendationItem] = []

        for item in data.get("recommendations", [])[:limit]:
            pid = item.get("product_id")
            reason = item.get("reason", "")
            if pid in by_id:
                base = by_id[pid]
                enhanced.append(
                    RecommendationItem(
                        product=base.product,
                        score=base.score,
                        reason=reason or base.reason,
                    )
                )

        if enhanced:
            return enhanced
    except Exception:
        pass

    return candidates[:limit]

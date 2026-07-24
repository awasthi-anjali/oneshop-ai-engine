"""Validate AI-proposed product IDs against catalog and business rules."""

from app.models.schemas import RecommendationItem
from app.services.intent_engine import score_product
from app.services.product_catalog import catalog


def validate_recommendations(
    product_ids: list[str],
    reasons: dict[str, str],
    exclude_ids: set[str],
    signals: list,
    intent,
    cart: list,
    viewed_only: set[str],
    limit: int = 6,
    source: str = "ai",
) -> list[RecommendationItem]:
    """AI proposes IDs; rules validate stock, exclusions, and enrich scores."""
    items: list[RecommendationItem] = []
    seen: set[str] = set()

    for pid in product_ids:
        if pid in seen or pid in exclude_ids:
            continue
        product = catalog.get_by_id(pid)
        if not product or not product.in_stock:
            continue
        seen.add(pid)
        score, rule_reason = score_product(product, intent, signals, cart, viewed_only)
        ai_reason = reasons.get(pid, "")
        items.append(RecommendationItem(
            product=product,
            score=max(score, 1.0),
            reason=ai_reason or rule_reason,
            source=source if ai_reason else "semantic_backup" if source == "semantic_backup" else source,
        ))
        if len(items) >= limit:
            break

    return items

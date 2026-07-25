import json

from app.config import settings
from app.models.schemas import CustomerIntent
from app.services.ai_client import get_openai_client
from app.services.customer_context import build_customer_context
from app.services.intent_engine import extract_intent_from_signals
from app.services.session_store import session_store

INTENT_PROMPT = """Analyze this customer's shopping signals and return JSON with:
{
  "summary": "2-3 sentence natural language summary of customer intent",
  "categories": ["phone", "plan", etc],
  "brands": ["Apple", "Samsung", etc],
  "tags": ["premium", "camera", etc],
  "price_min": number or null,
  "price_max": number or null,
  "price_avg": number or null,
  "funnel_stage": "new|browsing|wishlisted|cart",
  "ecosystem": "e.g. Apple ecosystem, Android family, etc",
  "purchase_readiness": "low|medium|high"
}

Weight signals: cart (strongest purchase intent) > wishlist (interest) > viewed/clicked (considering).
If they viewed a product, treat it as intent to buy even without wishlist/cart."""


def extract_intent(session_id: str) -> CustomerIntent:
    wishlist = session_store.get_wishlist(session_id)
    cart = session_store.get_cart(session_id)
    viewed = session_store.get_viewed(session_id)
    rule_intent = extract_intent_from_signals(wishlist, cart, viewed)

    client = get_openai_client()
    if not client or not (wishlist or cart or viewed):
        return rule_intent

    context = build_customer_context(session_id)
    try:
        response = client.chat.completions.create(
            model=settings.openai_model,
            reasoning_effort=settings.openai_reasoning_effort,
            messages=[
                {"role": "system", "content": INTENT_PROMPT},
                {"role": "user", "content": json.dumps(context)},
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
        )
        data = json.loads(response.choices[0].message.content or "{}")
        return CustomerIntent(
            categories=data.get("categories", rule_intent.categories),
            brands=data.get("brands", rule_intent.brands),
            tags=data.get("tags", rule_intent.tags),
            price_min=data.get("price_min", rule_intent.price_min),
            price_max=data.get("price_max", rule_intent.price_max),
            price_avg=data.get("price_avg", rule_intent.price_avg),
            summary=data.get("summary", rule_intent.summary),
            funnel_stage=data.get("funnel_stage", rule_intent.funnel_stage),
            ecosystem=data.get("ecosystem", rule_intent.ecosystem),
            purchase_readiness=data.get("purchase_readiness", rule_intent.purchase_readiness),
        )
    except Exception:
        return rule_intent

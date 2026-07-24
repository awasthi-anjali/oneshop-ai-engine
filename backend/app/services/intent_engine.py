from collections import Counter

from app.models.schemas import CustomerIntent, Product, ProductCategory

CART_WEIGHT = 2
VIEWED_WEIGHT = 1.5  # clicked/viewed = considering purchase


def extract_intent_from_signals(
    wishlist: list[Product],
    cart: list[Product],
    viewed: list[Product] | None = None,
) -> CustomerIntent:
    viewed = viewed or []
    if not wishlist and not cart and not viewed:
        return CustomerIntent(
            summary="Browse products — click to view, wishlist, or add to cart for personalized picks.",
            funnel_stage="new",
        )

    tag_counts: Counter[str] = Counter()
    category_counts: Counter[str] = Counter()
    brand_counts: Counter[str] = Counter()
    prices: list[float] = []

    for p in wishlist:
        tag_counts.update({t.lower(): 1 for t in p.tags})
        category_counts[p.category.value] += 1
        brand_counts[p.brand] += 1
        prices.append(p.price)

    for p in cart:
        tag_counts.update({t.lower(): CART_WEIGHT for t in p.tags})
        category_counts[p.category.value] += CART_WEIGHT
        brand_counts[p.brand] += CART_WEIGHT
        prices.extend([p.price] * CART_WEIGHT)

    for p in viewed:
        if p.id not in {x.id for x in wishlist + cart}:
            tag_counts.update({t.lower(): VIEWED_WEIGHT for t in p.tags})
            category_counts[p.category.value] += VIEWED_WEIGHT
            brand_counts[p.brand] += VIEWED_WEIGHT
            prices.extend([p.price] * int(VIEWED_WEIGHT))

    funnel = "cart" if cart else "wishlisted" if wishlist else "browsing" if viewed else "new"

    categories = [c for c, _ in category_counts.most_common()]
    brands = [b for b, _ in brand_counts.most_common()]
    top_tags = [tag for tag, _ in tag_counts.most_common(5)]

    price_min = min(prices) if prices else None
    price_max = max(prices) if prices else None
    price_avg = sum(prices) / len(prices) if prices else None

    summary_parts: list[str] = []

    if cart and wishlist:
        summary_parts.append(
            f"Purchase intent from cart ({len(cart)} item{'s' if len(cart) != 1 else ''}) "
            f"and interest from wishlist ({len(wishlist)} item{'s' if len(wishlist) != 1 else ''})"
        )
    elif cart:
        summary_parts.append(
            f"Strong purchase intent — {len(cart)} item{'s' if len(cart) != 1 else ''} in cart"
        )
    elif wishlist:
        summary_parts.append(
            f"Browsing interest — {len(wishlist)} item{'s' if len(wishlist) != 1 else ''} wishlisted"
        )
    elif viewed:
        summary_parts.append(
            f"Considering purchase — recently viewed {len(viewed)} product{'s' if len(viewed) != 1 else ''}"
        )

    if len(categories) == 1:
        summary_parts.append(f"focused on {categories[0]}s")
    elif categories:
        summary_parts.append(f"across {', '.join(categories[:3])}")

    if brands:
        summary_parts.append(f"preferring {', '.join(brands[:2])}")

    if top_tags:
        summary_parts.append(f"interested in {', '.join(top_tags[:3])}")

    if price_avg is not None:
        if price_avg < 100:
            summary_parts.append(
                f"(around ${price_avg:.0f}/mo)" if "plan" in categories else f"(budget ~${price_avg:.0f})"
            )
        elif price_avg >= 500:
            summary_parts.append(f"(premium tier ~${price_avg:.0f})")
        else:
            summary_parts.append(f"(mid-range ~${price_avg:.0f})")

    return CustomerIntent(
        categories=categories,
        brands=brands,
        tags=top_tags,
        price_min=price_min,
        price_max=price_max,
        price_avg=price_avg,
        summary=". ".join(summary_parts) + ".",
        funnel_stage=funnel,
    )


CROSS_SELL: dict[str, list[str]] = {
    ProductCategory.PHONE.value: [ProductCategory.PLAN.value, ProductCategory.ACCESSORY.value],
    ProductCategory.TABLET.value: [ProductCategory.PLAN.value, ProductCategory.ACCESSORY.value],
    ProductCategory.PLAN.value: [ProductCategory.PHONE.value, ProductCategory.TABLET.value],
    ProductCategory.ACCESSORY.value: [ProductCategory.PHONE.value, ProductCategory.ACCESSORY.value],
    ProductCategory.DEVICE.value: [ProductCategory.PLAN.value],
}


def _price_fit(price: float, intent: CustomerIntent) -> float:
    if intent.price_avg is None:
        return 0.0
    margin = intent.price_avg * (0.5 if intent.price_avg < 100 else 0.35)
    low = intent.price_avg - margin
    high = intent.price_avg + margin
    if low <= price <= high:
        return 2.0
    if price <= high * 1.2:
        return 1.0
    return 0.0


def _cross_sell_reason(product: Product, signals: list[Product], cart: list[Product]) -> str | None:
    signal_categories = {p.category.value for p in signals}
    cart_ids = {p.id for p in cart}

    if product.category.value in CROSS_SELL.get(next(iter(signal_categories)), []):
        if product.category == ProductCategory.PLAN:
            return "Pairs well with what's in your cart" if cart else "Pairs well with your picks"
        if product.category == ProductCategory.ACCESSORY:
            return "Complete your cart setup" if cart else "Complete your setup"
        if product.category == ProductCategory.PHONE:
            return "Works great with your plan interest"
    if cart and product.id not in cart_ids:
        return "Complements your cart items"
    return None


def score_product(
    product: Product,
    intent: CustomerIntent,
    signals: list[Product],
    cart: list[Product],
    viewed_ids: set[str] | None = None,
) -> tuple[float, str]:
    if not signals:
        return product.rating * 0.5, "Popular pick"

    score = 0.0
    reasons: list[str] = []
    cart_ids = {p.id for p in cart}
    viewed_ids = viewed_ids or set()

    signal_tags: Counter[str] = Counter()
    for p in signals:
        if p.id in cart_ids:
            weight = CART_WEIGHT
        elif p.id in viewed_ids:
            weight = VIEWED_WEIGHT
        else:
            weight = 1
        signal_tags.update({t.lower(): weight for t in p.tags})

    product_tags = {t.lower() for t in product.tags}
    tag_overlap = {t for t in product_tags if t in signal_tags}
    if tag_overlap:
        overlap_score = sum(signal_tags[t] for t in tag_overlap)
        score += overlap_score * 1.2
        reasons.append(f"Matches your interest in {', '.join(list(tag_overlap)[:2])}")

    if product.brand in intent.brands:
        brand_weight = CART_WEIGHT if any(p.brand == product.brand and p.id in cart_ids for p in signals) else 1.5
        score += brand_weight
        if any(p.brand == product.brand and p.id in cart_ids for p in cart):
            reasons.append(f"Same brand in your cart ({product.brand})")
        else:
            reasons.append(f"Same brand you liked ({product.brand})")

    for s in signals:
        if product.category.value in CROSS_SELL.get(s.category.value, []):
            boost = CART_WEIGHT if s.id in cart_ids else 1.5
            score += boost
            cross = _cross_sell_reason(product, signals, cart)
            if cross:
                reasons.append(cross)
            break

    score += _price_fit(product.price, intent)
    if _price_fit(product.price, intent) >= 1.0:
        reasons.append("Within your price range")

    score += product.rating * 0.3

    if product.category.value in intent.categories:
        score += 1.0

    reason = reasons[0] if reasons else "Recommended based on your activity"
    return score, reason

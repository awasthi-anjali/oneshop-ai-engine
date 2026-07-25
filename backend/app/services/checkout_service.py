from app.models.schemas import Product, ProductCategory


def calculate_cadence_totals(cart: list[Product]) -> tuple[float, float]:
    one_time_total = round(
        sum(product.price for product in cart if product.category != ProductCategory.PLAN),
        2,
    )
    monthly_total = round(
        sum(product.price for product in cart if product.category == ProductCategory.PLAN),
        2,
    )
    return one_time_total, monthly_total


def calculate_totals(cart: list[Product]) -> tuple[float, float, float, float]:
    """Return catalog-owned totals without manufacturing an offer.

    `subtotal` and `total` are retained for API compatibility. Mixed billing
    cadences are exposed separately by `calculate_cadence_totals`.
    """
    subtotal = round(sum(product.price for product in cart), 2)
    return subtotal, 0.0, 0.0, subtotal

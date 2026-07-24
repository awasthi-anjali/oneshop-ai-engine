import json
import re
from pathlib import Path

from app.models.schemas import Product, ProductCategory, ProductSearchRequest

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "products.json"


class ProductCatalog:
    def __init__(self) -> None:
        with open(DATA_PATH, encoding="utf-8") as f:
            raw = json.load(f)
        self._products: list[Product] = [Product(**item) for item in raw]
        self._by_id = {p.id: p for p in self._products}

    @property
    def all(self) -> list[Product]:
        return list(self._products)

    def get_by_id(self, product_id: str) -> Product | None:
        return self._by_id.get(product_id)

    def get_by_ids(self, product_ids: list[str]) -> list[Product]:
        return [p for pid in product_ids if (p := self._by_id.get(pid))]

    def search(self, req: ProductSearchRequest) -> list[Product]:
        results = self._products

        if req.category:
            results = [p for p in results if p.category == req.category]

        if req.brand:
            brand_lower = req.brand.lower()
            results = [p for p in results if brand_lower in p.brand.lower()]

        if req.max_price is not None:
            results = [p for p in results if p.price <= req.max_price]

        if req.min_price is not None:
            results = [p for p in results if p.price >= req.min_price]

        if req.tags:
            tag_set = {t.lower() for t in req.tags}
            results = [
                p for p in results
                if tag_set.intersection({t.lower() for t in p.tags})
            ]

        if req.query:
            results = self._rank_by_query(results, req.query)

        return results[: req.limit]

    def _rank_by_query(self, products: list[Product], query: str) -> list[Product]:
        query_lower = query.lower()
        tokens = set(re.findall(r"\w+", query_lower))

        def score(product: Product) -> float:
            text = " ".join([
                product.name,
                product.description,
                product.brand,
                " ".join(product.features),
                " ".join(product.tags),
                product.category.value,
            ]).lower()

            token_hits = sum(1 for t in tokens if t in text)
            phrase_bonus = 2.0 if query_lower in text else 0.0
            price_match = 0.0
            price_patterns = re.findall(r"(?:under|below|less than|max|budget)\s*\$?(\d+)", query_lower)
            if price_patterns:
                max_p = float(price_patterns[0])
                if product.price <= max_p:
                    price_match = 1.5

            return token_hits + phrase_bonus + price_match + product.rating * 0.1

        return sorted(products, key=score, reverse=True)

    def compare(self, product_ids: list[str]) -> list[Product]:
        products = self.get_by_ids(product_ids)
        order = {pid: i for i, pid in enumerate(product_ids)}
        return sorted(products, key=lambda p: order.get(p.id, 999))

    def categories_summary(self) -> str:
        counts: dict[str, int] = {}
        for p in self._products:
            counts[p.category.value] = counts.get(p.category.value, 0) + 1
        return ", ".join(f"{k}: {v}" for k, v in counts.items())


catalog = ProductCatalog()

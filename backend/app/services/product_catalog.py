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
        products, _ = self.search_with_meta(req)
        return products

    def search_with_meta(self, req: ProductSearchRequest) -> tuple[list[Product], str]:
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

        search_method = "name"
        if req.query:
            pool = results
            results = self._rank_by_query(results, req.query)
            results, search_method = self._maybe_rerank_with_embeddings(results, req.query, pool)

        return results[: req.limit], search_method

    def _maybe_rerank_with_embeddings(
        self,
        name_matches: list[Product],
        query: str,
        candidate_pool: list[Product] | None = None,
    ) -> tuple[list[Product], str]:
        if not query.strip():
            return name_matches, "name"

        pool = candidate_pool if candidate_pool is not None else (name_matches or self._products)
        pool_ids = {p.id for p in pool}

        try:
            from app.services.ai_client import get_openai_client, is_ai_enabled
            from app.services.catalog_retrieval import (
                EMBED_MODEL,
                _cosine,
                _ensure_embeddings,
                semantic_retrieve_with_meta,
            )

            if not is_ai_enabled():
                return name_matches or self._rank_by_query(pool, query), "name"

            if name_matches:
                match_ids = {p.id for p in name_matches}
                retrieved_ids, meta = semantic_retrieve_with_meta(query, top_k=50)
                method = meta.get("method", "name")
                if method not in {"embeddings", "keyword"}:
                    return name_matches, "name"

                reranked = [
                    self._by_id[pid]
                    for pid in retrieved_ids
                    if pid in match_ids and pid in self._by_id
                ]
                if reranked:
                    seen = {p.id for p in reranked}
                    for product in name_matches:
                        if product.id not in seen:
                            reranked.append(product)
                    return reranked, method
                return name_matches, "name"

            embeddings = _ensure_embeddings()
            client = get_openai_client()
            if embeddings and client:
                q_emb = client.embeddings.create(model=EMBED_MODEL, input=query).data[0].embedding
                scored = [
                    (pid, _cosine(q_emb, emb))
                    for pid, emb in embeddings.items()
                    if pid in pool_ids
                ]
                scored.sort(key=lambda x: x[1], reverse=True)
                retrieved = [self._by_id[pid] for pid, _ in scored[:50] if pid in self._by_id]
                if retrieved:
                    return retrieved, "embeddings"

            fallback = self._rank_by_query(pool, query)
            if fallback:
                return fallback, "name"
        except Exception:
            pass

        return name_matches, "name"

    def _rank_by_query(self, products: list[Product], query: str) -> list[Product]:
        query_lower = query.lower().strip()
        if not query_lower:
            return products

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

            token_hits = sum(1 for token in tokens if token in text)
            phrase_bonus = 2.0 if query_lower in text else 0.0
            price_match = 0.0
            price_patterns = re.findall(
                r"(?:under|below|less than|max|budget)\s*\$?(\d+)", query_lower
            )
            if price_patterns:
                max_p = float(price_patterns[0])
                if product.price <= max_p:
                    price_match = 1.5

            relevance = token_hits + phrase_bonus + price_match
            if relevance <= 0:
                return 0.0
            return relevance + product.rating * 0.1

        scored = [(product, score(product)) for product in products]
        scored = [(product, value) for product, value in scored if value > 0]
        scored.sort(key=lambda item: item[1], reverse=True)
        return [product for product, _ in scored]

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

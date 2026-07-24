"""RAG-lite catalog retrieval — compact catalog for LLM + semantic search when API key is set."""

import json
import math
from typing import Any

from app.models.schemas import Product
from app.services.ai_client import get_openai_client
from app.services.product_catalog import catalog

EMBED_MODEL = "text-embedding-3-small"
_embedding_cache: dict[str, list[float]] | None = None


def _product_text(product: Product) -> str:
    return " | ".join([
        product.name,
        product.category.value,
        product.brand,
        product.description,
        " ".join(product.features),
        " ".join(product.tags),
        f"${product.price}",
    ])


def catalog_compact(exclude_ids: set[str] | None = None) -> list[dict]:
    exclude = exclude_ids or set()
    return [
        {
            "id": p.id,
            "name": p.name,
            "category": p.category.value,
            "brand": p.brand,
            "price": p.price,
            "tags": p.tags,
            "rating": p.rating,
        }
        for p in catalog.all
        if p.in_stock and p.id not in exclude
    ]


def catalog_text_for_llm(exclude_ids: set[str] | None = None) -> str:
    return json.dumps(catalog_compact(exclude_ids=exclude_ids), indent=0)


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _ensure_embeddings() -> dict[str, list[float]] | None:
    global _embedding_cache
    if _embedding_cache is not None:
        return _embedding_cache

    client = get_openai_client()
    if not client:
        return None

    texts = [_product_text(p) for p in catalog.all if p.in_stock]
    ids = [p.id for p in catalog.all if p.in_stock]
    if not texts:
        return None

    try:
        response = client.embeddings.create(model=EMBED_MODEL, input=texts)
        _embedding_cache = {
            pid: item.embedding
            for pid, item in zip(ids, response.data)
        }
        return _embedding_cache
    except Exception:
        return None


def is_embeddings_cached() -> bool:
    return _embedding_cache is not None and len(_embedding_cache) > 0


def semantic_retrieve_with_meta(
    query: str,
    top_k: int = 10,
    exclude_ids: set[str] | None = None,
) -> tuple[list[str], dict[str, Any]]:
    """
    Return product IDs + metadata about retrieval method.
    embeddings = OpenAI vector search; keyword = catalog text search fallback.
    """
    exclude = exclude_ids or set()
    meta: dict[str, Any] = {
        "method": "none",
        "query": query.strip(),
        "embeddings_cached": is_embeddings_cached(),
        "count": 0,
    }

    embeddings = _ensure_embeddings()
    client = get_openai_client()

    if embeddings and client and query.strip():
        try:
            q_emb = client.embeddings.create(model=EMBED_MODEL, input=query).data[0].embedding
            scored = [
                (pid, _cosine(q_emb, emb))
                for pid, emb in embeddings.items()
                if pid not in exclude
            ]
            scored.sort(key=lambda x: x[1], reverse=True)
            ids = [pid for pid, _ in scored[:top_k]]
            meta["method"] = "embeddings"
            meta["count"] = len(ids)
            meta["embeddings_cached"] = True
            return ids, meta
        except Exception:
            pass

    from app.models.schemas import ProductSearchRequest

    results = catalog.search(ProductSearchRequest(query=query, limit=top_k + len(exclude)))
    ids = [p.id for p in results if p.id not in exclude][:top_k]
    meta["method"] = "keyword"
    meta["count"] = len(ids)
    return ids, meta


def semantic_retrieve(
    query: str,
    top_k: int = 10,
    exclude_ids: set[str] | None = None,
) -> list[str]:
    ids, _ = semantic_retrieve_with_meta(query, top_k, exclude_ids)
    return ids

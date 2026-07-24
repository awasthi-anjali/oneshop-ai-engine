from fastapi.testclient import TestClient

from app.main import app
from app.services.product_catalog import catalog


def _disable_semantic_reranking(monkeypatch) -> None:
    monkeypatch.setattr(
        catalog,
        "_maybe_rerank_with_embeddings",
        lambda name_matches, query, candidate_pool=None: (name_matches, "name"),
    )


def test_name_search_excludes_unmatched_catalog_products(monkeypatch):
    _disable_semantic_reranking(monkeypatch)

    response = TestClient(app).get(
        "/api/products",
        params={"query": "iphone", "include_meta": True, "limit": 50},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["search_method"] == "name"
    assert [product["id"] for product in data["products"]] == [
        "iphone-15-pro",
        "magsafe-charger",
        "iphone-se",
    ]


def test_unmatched_name_search_returns_no_results(monkeypatch):
    _disable_semantic_reranking(monkeypatch)

    response = TestClient(app).get(
        "/api/products",
        params={"query": "nonexistent-gadget", "include_meta": True, "limit": 50},
    )

    assert response.status_code == 200
    assert response.json()["products"] == []

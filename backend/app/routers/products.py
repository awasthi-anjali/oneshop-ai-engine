from fastapi import APIRouter, HTTPException, Query

from app.models.schemas import CompareRequest, Product, ProductCategory, ProductSearchRequest, ProductSearchResponse
from app.services.product_catalog import catalog

router = APIRouter(prefix="/api/products", tags=["products"])


@router.get("")
async def list_products(
    query: str = "",
    category: ProductCategory | None = None,
    max_price: float | None = None,
    min_price: float | None = None,
    brand: str | None = None,
    limit: int = Query(default=20, le=50),
    include_meta: bool = False,
):
    req = ProductSearchRequest(
        query=query,
        category=category,
        max_price=max_price,
        min_price=min_price,
        brand=brand,
        limit=limit,
    )
    if include_meta:
        products, search_method = catalog.search_with_meta(req)
        return ProductSearchResponse(products=products, search_method=search_method)
    return catalog.search(req)


@router.get("/meta/categories")
async def get_categories() -> dict:
    return {"summary": catalog.categories_summary(), "total": len(catalog.all)}


@router.post("/compare", response_model=list[Product])
async def compare_products(request: CompareRequest) -> list[Product]:
    products = catalog.compare(request.product_ids)
    if len(products) < 2:
        raise HTTPException(status_code=404, detail="Need at least 2 valid product IDs")
    return products


@router.get("/{product_id}", response_model=Product)
async def get_product(product_id: str) -> Product:
    product = catalog.get_by_id(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product

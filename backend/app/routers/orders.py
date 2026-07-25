from fastapi import APIRouter, HTTPException, Query

from app.models.schemas import (
    CheckoutReviewRequest,
    CheckoutReviewResponse,
    OrderReceipt,
)
from app.services.commerce_store import commerce_error_detail, commerce_store
from app.services.personalized_recommendation import resolve_profile_session
from app.services.session_store import session_store


router = APIRouter(prefix="/api", tags=["orders"])


def _resolve(session_id: str, user_id: str | None) -> str:
    if user_id:
        return resolve_profile_session(user_id, session_id, "oneshop")
    return session_store.get_or_create(session_id)


@router.post("/checkout/reviews", response_model=CheckoutReviewResponse)
async def create_checkout_review(request: CheckoutReviewRequest) -> CheckoutReviewResponse:
    sid = _resolve(request.session_id, request.user_id)
    try:
        return commerce_store.create_review(request.model_copy(update={"session_id": sid}))
    except ValueError as exc:
        status = 402 if str(exc).startswith("SIMULATED_DECLINE") else 409
        raise HTTPException(status_code=status, detail=commerce_error_detail(exc)) from exc


@router.get("/checkout/reviews/{review_id}", response_model=CheckoutReviewResponse)
async def get_checkout_review(
    review_id: str,
    session_id: str = Query(..., min_length=1, max_length=128),
    user_id: str | None = Query(default=None, min_length=2, max_length=64),
) -> CheckoutReviewResponse:
    sid = _resolve(session_id, user_id)
    try:
        return commerce_store.get_review(review_id, sid, user_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=commerce_error_detail(exc)) from exc


@router.delete("/checkout/reviews/{review_id}", status_code=204)
async def cancel_checkout_review(
    review_id: str,
    session_id: str = Query(..., min_length=1, max_length=128),
    user_id: str | None = Query(default=None, min_length=2, max_length=64),
) -> None:
    sid = _resolve(session_id, user_id)
    try:
        commerce_store.cancel_review(review_id, sid, user_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=commerce_error_detail(exc)) from exc


@router.get("/orders/by-idempotency/{key}", response_model=OrderReceipt)
async def get_order_by_idempotency(
    key: str,
    session_id: str = Query(..., min_length=1, max_length=128),
    user_id: str | None = Query(default=None, min_length=2, max_length=64),
) -> OrderReceipt:
    sid = _resolve(session_id, user_id)
    try:
        return commerce_store.get_order_by_idempotency(key, sid, user_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=commerce_error_detail(exc)) from exc


@router.get("/orders/{order_id}", response_model=OrderReceipt)
async def get_order(
    order_id: str,
    session_id: str = Query(..., min_length=1, max_length=128),
    user_id: str | None = Query(default=None, min_length=2, max_length=64),
) -> OrderReceipt:
    sid = _resolve(session_id, user_id)
    try:
        return commerce_store.get_order(order_id, sid, user_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=commerce_error_detail(exc)) from exc

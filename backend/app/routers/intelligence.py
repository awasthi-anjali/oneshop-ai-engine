from fastapi import APIRouter, HTTPException, Query

from app.models.schemas import (
    AbandonmentResponse,
    BundleAddRequest,
    IntelligenceProfileResponse,
    NextBestActionResponse,
    RecommendationsResponse,
    SessionActionRequest,
    SessionStateResponse,
    SmartCartResponse,
)
from app.services.next_best_action_service import get_next_best_actions
from app.services.omnichannel_service import get_omnichannel_context
from app.services.orchestrator_service import get_intelligence_profile
from app.services.personalized_recommendation import resolve_profile_session
from app.services.product_catalog import catalog
from app.services.recommendation_engine import get_recommendations
from app.services.session_helpers import session_response
from app.services.session_store import session_store
from app.services.smart_cart_service import get_smart_cart

router = APIRouter(tags=["intelligence"])


def _touch_channel(session_id: str | None, channel: str | None) -> str:
    sid = session_store.get_or_create(session_id)
    if channel:
        session_store.record_channel(sid, channel)
    return sid


@router.get("/api/intelligence/profile", response_model=IntelligenceProfileResponse)
async def intelligence_profile(
    session_id: str | None = None,
    customer_id: str | None = None,
    user_id: str | None = None,
    channel: str = Query(default="oneshop"),
    limit: int = Query(default=6, le=12),
) -> IntelligenceProfileResponse:
    """Unified AI orchestrator — intent, recs, NBA, smart cart in one call."""
    sid = (
        resolve_profile_session(user_id, session_id, channel)
        if user_id
        else session_store.resolve_session(session_id, customer_id)
    )
    profile = get_intelligence_profile(sid, limit=limit)
    abandon_data = profile.pop("abandonment", {})
    omni = get_omnichannel_context(sid, channel)
    profile.update({
        "session_id": sid,
        "current_channel": omni["current_channel"],
        "last_channel": omni["last_channel"],
        "channels_used": omni["channels_used"],
        "is_cross_channel": omni["is_cross_channel"],
        "other_channel": omni["other_channel"],
        "sync_message": omni["sync_message"],
        "customer_id": omni["customer_id"],
        "continue_url_web": omni["continue_url_web"],
        "continue_url_app": omni["continue_url_app"],
    })
    return IntelligenceProfileResponse(
        **profile,
        abandonment=AbandonmentResponse(session_id=sid, **abandon_data),
    )


@router.get("/api/discovery/recommend", response_model=RecommendationsResponse)
async def recommend(
    session_id: str | None = None,
    limit: int = Query(default=6, le=12),
) -> RecommendationsResponse:
    sid = session_store.get_or_create(session_id)
    intent, recommendations, ai_powered = get_recommendations(sid, limit=limit)
    return RecommendationsResponse(
        session_id=sid,
        intent=intent,
        recommendations=recommendations,
        ai_powered=ai_powered,
    )


@router.get("/api/intelligence/next-best-action", response_model=NextBestActionResponse)
async def next_best_action(session_id: str | None = None) -> NextBestActionResponse:
    sid = session_store.get_or_create(session_id)
    stage, actions, ai_powered = get_next_best_actions(sid)
    return NextBestActionResponse(
        session_id=sid,
        funnel_stage=stage,
        actions=actions,
        ai_powered=ai_powered,
    )


@router.get("/api/intelligence/smart-cart", response_model=SmartCartResponse)
async def smart_cart(session_id: str | None = None) -> SmartCartResponse:
    sid = session_store.get_or_create(session_id)
    result = get_smart_cart(sid)
    return SmartCartResponse(session_id=sid, **result)


@router.post("/api/customer/cart/add-bundle", response_model=SessionStateResponse)
async def add_bundle_to_cart(request: BundleAddRequest) -> SessionStateResponse:
    for pid in request.product_ids:
        if not catalog.get_by_id(pid):
            raise HTTPException(status_code=404, detail=f"Product not found: {pid}")
    sid = _touch_channel(request.session_id, request.channel)
    session_store.add_bundle_to_cart(sid, request.product_ids)
    return session_response(sid)


@router.post("/api/checkout/abandon", response_model=AbandonmentResponse)
async def mark_cart_abandoned(session_id: str | None = None) -> AbandonmentResponse:
    sid = session_store.get_or_create(session_id)
    session_store.mark_abandoned(sid)
    status = session_store.get_abandonment_status(sid)
    return AbandonmentResponse(session_id=sid, **status)


@router.get("/api/checkout/abandonment-status", response_model=AbandonmentResponse)
async def abandonment_status(session_id: str | None = None) -> AbandonmentResponse:
    sid = session_store.get_or_create(session_id)
    status = session_store.get_abandonment_status(sid)
    return AbandonmentResponse(session_id=sid, **status)


@router.post("/api/checkout/dismiss-abandonment")
async def dismiss_abandonment(session_id: str | None = None) -> dict:
    sid = session_store.get_or_create(session_id)
    session_store.clear_abandonment(sid)
    return {"status": "ok", "session_id": sid}


@router.get("/api/customer/session", response_model=SessionStateResponse)
async def get_session(session_id: str | None = None) -> SessionStateResponse:
    sid = session_store.get_or_create(session_id)
    return session_response(sid)


@router.post("/api/customer/view", response_model=SessionStateResponse)
async def track_view(request: SessionActionRequest) -> SessionStateResponse:
    if not catalog.get_by_id(request.product_id):
        raise HTTPException(status_code=404, detail="Product not found")
    sid = _touch_channel(request.session_id, request.channel)
    session_store.track_view(sid, request.product_id)
    return session_response(sid)


@router.post("/api/customer/wishlist/toggle", response_model=SessionStateResponse)
async def toggle_wishlist(request: SessionActionRequest) -> SessionStateResponse:
    if not catalog.get_by_id(request.product_id):
        raise HTTPException(status_code=404, detail="Product not found")
    sid = _touch_channel(request.session_id, request.channel)
    session_store.toggle_wishlist(sid, request.product_id)
    return session_response(sid)


@router.post("/api/customer/cart/add", response_model=SessionStateResponse)
async def add_to_cart(request: SessionActionRequest) -> SessionStateResponse:
    if not catalog.get_by_id(request.product_id):
        raise HTTPException(status_code=404, detail="Product not found")
    sid = _touch_channel(request.session_id, request.channel)
    session_store.add_to_cart(sid, request.product_id)
    return session_response(sid)


@router.post("/api/customer/cart/remove", response_model=SessionStateResponse)
async def remove_from_cart(request: SessionActionRequest) -> SessionStateResponse:
    sid = _touch_channel(request.session_id, request.channel)
    session_store.remove_from_cart(sid, request.product_id)
    return session_response(sid)


@router.post("/api/customer/cart/toggle", response_model=SessionStateResponse)
async def toggle_cart(request: SessionActionRequest) -> SessionStateResponse:
    if not catalog.get_by_id(request.product_id):
        raise HTTPException(status_code=404, detail="Product not found")
    sid = session_store.get_or_create(request.session_id)
    session_store.toggle_cart(sid, request.product_id)
    return session_response(sid)

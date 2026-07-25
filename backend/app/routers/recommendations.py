from fastapi import APIRouter, HTTPException, Query

from app.models.schemas import RecommendationInteractionRequest
from app.services.behavioral_memory import behavioral_memory_store, bounded_memory_context
from app.services.interaction_store import DEMO_PROFILES, interaction_store
from app.services.personalized_recommendation import (
    get_personalized_recommendations,
    resolve_profile_session,
)
from app.services.product_catalog import catalog
from app.services.session_store import session_store

router = APIRouter(prefix="/api/recommendations", tags=["personalized-recommendations"])


@router.get("/demo-profiles")
async def demo_profiles() -> dict:
    return {"profiles": DEMO_PROFILES}


@router.get("/{user_id}/memory")
async def behavioral_memory(user_id: str) -> dict:
    record = behavioral_memory_store.get(user_id)
    return {
        "user_id": user_id,
        "version": record.version,
        "updated_at": record.updated_at,
        "memory": record.memory.model_dump(),
        "assistant_context": bounded_memory_context(user_id),
    }


@router.delete("/{user_id}/memory")
async def reset_behavioral_memory(user_id: str) -> dict:
    deleted = behavioral_memory_store.reset(user_id)
    return {"user_id": user_id, "deleted": deleted, "version": 0}


@router.post("/interactions")
async def track_interaction(request: RecommendationInteractionRequest) -> dict:
    if request.product_id and not catalog.get_by_id(request.product_id):
        raise HTTPException(status_code=404, detail="Product not found")
    sid = resolve_profile_session(request.user_id, request.session_id, request.channel.value)
    persisted = request.model_copy(update={"session_id": sid})
    accepted, version = interaction_store.append(persisted)
    if accepted and request.event_type.value == "product_view" and request.product_id:
        session_store.track_view(sid, request.product_id)
    return {
        "accepted": accepted,
        "duplicate": not accepted,
        "user_id": request.user_id,
        "session_id": sid,
        "version": version,
    }


@router.get("/{user_id}/profile")
async def recommendation_profile(
    user_id: str,
    session_id: str | None = None,
    channel: str = Query(default="oneshop", pattern="^(oneshop|oneapp)$"),
) -> dict:
    payload = get_personalized_recommendations(
        user_id=user_id, session_id=session_id, channel=channel, limit=1
    )
    return {
        "user_id": user_id,
        "session_id": payload["session_id"],
        "version": payload["version"],
        "profile": payload["profile"],
    }


@router.get("/{user_id}/updates")
async def recommendation_updates(
    user_id: str,
    after_version: int = Query(default=-1, ge=-1),
    session_id: str | None = None,
    channel: str = Query(default="oneshop", pattern="^(oneshop|oneapp)$"),
    query: str = Query(default="", max_length=120),
    limit: int = Query(default=6, ge=1, le=12),
) -> dict:
    current_version = interaction_store.version(user_id)
    if current_version <= after_version:
        sid = resolve_profile_session(user_id, session_id, channel)
        return {
            "changed": False,
            "user_id": user_id,
            "session_id": sid,
            "channel": channel,
            "version": current_version,
            "recommendations": [],
        }
    payload = get_personalized_recommendations(
        user_id=user_id,
        session_id=session_id,
        channel=channel,
        query=query,
        limit=limit,
    )
    return {"changed": True, **payload}


@router.get("/{user_id}")
async def recommendations(
    user_id: str,
    session_id: str | None = None,
    channel: str = Query(default="oneshop", pattern="^(oneshop|oneapp)$"),
    query: str = Query(default="", max_length=120),
    limit: int = Query(default=6, ge=1, le=12),
) -> dict:
    return get_personalized_recommendations(
        user_id=user_id,
        session_id=session_id,
        channel=channel,
        query=query,
        limit=limit,
    )

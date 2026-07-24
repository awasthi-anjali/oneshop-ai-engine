from fastapi import APIRouter, Query, Request

from app.models.schemas import OmnichannelContextResponse, OmnichannelLinkRequest, OmnichannelLinkResponse
from app.services.omnichannel_service import build_continue_urls, get_omnichannel_context, resolve_frontend_base
from app.services.session_store import session_store

router = APIRouter(prefix="/api/omnichannel", tags=["omnichannel"])


def _request_origin(request: Request) -> str:
    return resolve_frontend_base(request.headers.get("origin"))


@router.post("/link", response_model=OmnichannelLinkResponse)
async def link_customer(request: OmnichannelLinkRequest) -> OmnichannelLinkResponse:
    """Link a stable customer_id to a session (same cart across devices when logged in)."""
    sid = session_store.link_customer(request.customer_id, request.session_id)
    return OmnichannelLinkResponse(
        session_id=sid,
        customer_id=request.customer_id,
        message=f"Customer {request.customer_id} linked. Use this session on any channel.",
    )


@router.get("/context", response_model=OmnichannelContextResponse)
async def omnichannel_context(
    request: Request,
    session_id: str | None = None,
    customer_id: str | None = None,
    channel: str = Query(default="oneshop"),
) -> OmnichannelContextResponse:
    """Full cross-channel context — cart sync status, continue URLs, channel history."""
    sid = session_store.resolve_session(session_id, customer_id)
    data = get_omnichannel_context(sid, channel, base_url=_request_origin(request))
    return OmnichannelContextResponse(**data)


@router.get("/continue")
async def continue_on_device(
    request: Request,
    session_id: str | None = None,
    customer_id: str | None = None,
    target: str = Query(default="oneapp", pattern="^(oneshop|oneapp)$"),
) -> dict:
    """Get URL to continue shopping on another channel with the same session."""
    sid = session_store.resolve_session(session_id, customer_id)
    urls = build_continue_urls(sid, base_url=_request_origin(request))
    return {
        "session_id": sid,
        "customer_id": session_store.get_customer_id(sid),
        "target_channel": target,
        "continue_url": urls[target],
        "continue_url_web": urls["oneshop"],
        "continue_url_app": urls["oneapp"],
    }

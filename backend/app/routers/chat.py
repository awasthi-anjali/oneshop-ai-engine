from fastapi import APIRouter

from app.models.schemas import ChatRequest, ChatResponse
from app.services.conversational_assistant import assistant

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    session_id, message, suggested, cart_updated, open_checkout = await assistant.chat(
        message=request.message,
        session_id=request.session_id,
        channel=request.channel,
    )
    return ChatResponse(
        session_id=session_id,
        message=message,
        suggested_actions=suggested,
        cart_updated=cart_updated,
        open_checkout=open_checkout,
    )


@router.get("/health")
async def chat_health() -> dict:
    return {
        "status": "ok",
        "llm_enabled": assistant.uses_llm,
        "mode": "openai" if assistant.uses_llm else "rule-based-fallback",
    }

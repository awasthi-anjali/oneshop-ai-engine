from fastapi import APIRouter, HTTPException

from app.models.schemas import ChatRequest, ChatResponse
from app.services.shopassist_service import shopassist

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    try:
        return await shopassist.chat(request)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/health")
async def chat_health() -> dict:
    return {
        "status": "ok",
        "llm_enabled": shopassist.uses_llm,
        "mode": "openai" if shopassist.uses_llm else "rule-based-fallback",
    }

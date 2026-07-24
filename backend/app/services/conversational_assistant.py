"""Compatibility adapter for the retired, mutation-capable chat implementation."""

from app.models.schemas import ChatMessage, ChatRequest
from app.services.shopassist_service import shopassist


class ConversationalAssistant:
    @property
    def uses_llm(self) -> bool:
        return shopassist.uses_llm

    async def chat(
        self,
        message: str,
        session_id: str | None = None,
        channel: str = "oneshop",
    ) -> tuple:
        response = await shopassist.chat(
            ChatRequest(message=message, session_id=session_id, channel=channel)
        )
        legacy_message = ChatMessage(
            role="assistant",
            content=response.message,
            products=[item.product for item in response.recommendations],
            comparison=response.comparison,
        )
        return (
            response.session_id,
            legacy_message,
            response.suggested_actions,
            False,
            False,
        )


assistant = ConversationalAssistant()

import logging

from assistant.application.context_builder import ContextBuilder
from assistant.domain.messages import IncomingMessage, OutgoingMessage
from assistant.infrastructure.ai.service import AIService

logger = logging.getLogger(__name__)

_FALLBACK_REPLY = "I hit a problem generating a reply. Please try again in a moment."


class ProcessMessage:
    def __init__(self, *, ai_service: AIService, context_builder: ContextBuilder) -> None:
        self._ai_service = ai_service
        self._context_builder = context_builder

    async def execute(self, incoming: IncomingMessage) -> OutgoingMessage:
        context = self._context_builder.build(incoming)
        try:
            reply = await self._ai_service.complete(context)
        except Exception:
            logger.exception("AI completion failed for user_id=%s", incoming.user_id)
            reply = _FALLBACK_REPLY
        return OutgoingMessage(chat_id=incoming.chat_id, text=reply)

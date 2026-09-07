import logging

from assistant.application.context_builder import ContextBuilder
from assistant.application.conversation_store import ConversationStore
from assistant.domain.messages import ChatMessage, IncomingMessage, OutgoingMessage
from assistant.infrastructure.ai.service import AIService

logger = logging.getLogger(__name__)

_FALLBACK_REPLY = "I hit a problem generating a reply. Please try again in a moment."


class ProcessMessage:
    def __init__(
        self,
        *,
        ai_service: AIService,
        context_builder: ContextBuilder,
        conversation_store: ConversationStore | None = None,
    ) -> None:
        self._ai_service = ai_service
        self._context_builder = context_builder
        self._conversation_store = conversation_store

    async def execute(self, incoming: IncomingMessage) -> OutgoingMessage:
        history: list[ChatMessage] = []
        if self._conversation_store is not None:
            try:
                history = list(
                    await self._conversation_store.list_recent(
                        user_id=incoming.user_id, chat_id=incoming.chat_id
                    )
                )
            except Exception:
                logger.exception(
                    "Conversation history lookup failed for user_id=%s", incoming.user_id
                )

        context = self._context_builder.build(incoming, history)
        try:
            reply = await self._ai_service.complete(context)
        except Exception:
            logger.exception("AI completion failed for user_id=%s", incoming.user_id)
            reply = _FALLBACK_REPLY
        else:
            if self._conversation_store is not None:
                try:
                    await self._conversation_store.append(
                        user_id=incoming.user_id,
                        chat_id=incoming.chat_id,
                        message=ChatMessage(role="user", content=incoming.text),
                    )
                    await self._conversation_store.append(
                        user_id=incoming.user_id,
                        chat_id=incoming.chat_id,
                        message=ChatMessage(role="assistant", content=reply),
                    )
                except Exception:
                    logger.exception(
                        "Conversation persistence failed for user_id=%s", incoming.user_id
                    )
        return OutgoingMessage(chat_id=incoming.chat_id, text=reply)

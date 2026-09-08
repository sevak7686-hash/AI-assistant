from __future__ import annotations

import logging

from assistant.application.context_builder import ContextBuilder
from assistant.application.process_message import ProcessMessage
from assistant.config import Settings
from assistant.infrastructure.ai.deepseek import DeepSeekAIService
from assistant.infrastructure.db.conversation_store import SqlAlchemyConversationStore
from assistant.infrastructure.db.session import create_session_factory
from assistant.interfaces.telegram.bot import build_telegram_app


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    settings = Settings()
    if not settings.allowed_user_ids():
        raise RuntimeError("ALLOWED_TELEGRAM_USER_IDS must contain at least one Telegram user ID")

    ai_service = DeepSeekAIService(
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
        model=settings.deepseek_model,
        max_tokens=settings.deepseek_max_tokens,
    )
    conversation_store = SqlAlchemyConversationStore(create_session_factory(settings.database_url))
    process_message = ProcessMessage(
        ai_service=ai_service,
        context_builder=ContextBuilder(),
        conversation_store=conversation_store,
    )

    async def close_ai_service(_application) -> None:
        await ai_service.aclose()

    application = build_telegram_app(settings, process_message, close_ai_service)
    application.run_polling()


if __name__ == "__main__":
    main()

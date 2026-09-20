from __future__ import annotations

import logging

import httpx

from assistant.application.context_builder import ContextBuilder
from assistant.application.process_message import ProcessMessage
from assistant.config import Settings
from assistant.infrastructure.ai.deepseek import DeepSeekAIService
from assistant.infrastructure.ai.transcription import OpenAITranscriptionService
from assistant.infrastructure.db.conversation_store import SqlAlchemyConversationStore
from assistant.infrastructure.db.reminder_store import SqlAlchemyReminderStore
from assistant.infrastructure.db.session import create_session_factory
from assistant.infrastructure.search.serpapi import SerpAPIWebSearch
from assistant.interfaces.telegram.bot import build_telegram_app


def _build_http_client(proxy_url: str, timeout: float) -> httpx.AsyncClient | None:
    if not proxy_url:
        return None
    return httpx.AsyncClient(timeout=timeout, proxy=proxy_url)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    settings = Settings()
    if not settings.allowed_user_ids():
        raise RuntimeError("ALLOWED_TELEGRAM_USER_IDS must contain at least one Telegram user ID")

    ai_client = _build_http_client(settings.ai_proxy_url, timeout=60.0)
    ai_service = DeepSeekAIService(
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
        model=settings.deepseek_model,
        max_tokens=settings.deepseek_max_tokens,
        client=ai_client,
    )
    search_service = (
        SerpAPIWebSearch(
            api_key=settings.serpapi_api_key,
            max_results=settings.search_max_results,
            timeout_seconds=settings.search_timeout_seconds,
        )
        if settings.serpapi_api_key
        else None
    )
    transcription_client = _build_http_client(settings.ai_proxy_url, timeout=120.0)
    transcription_service = (
        OpenAITranscriptionService(
            api_key=settings.openai_api_key or settings.deepseek_api_key,
            base_url=settings.openai_base_url,
            model=settings.openai_transcription_model,
            language=settings.transcription_language,
            client=transcription_client,
        )
        if settings.openai_api_key or settings.deepseek_api_key
        else None
    )
    session_factory = create_session_factory(settings.database_url)
    conversation_store = SqlAlchemyConversationStore(session_factory)
    reminder_store = SqlAlchemyReminderStore(session_factory)
    reminder_timezone = settings.reminder_timezone_info()
    process_message = ProcessMessage(
        ai_service=ai_service,
        context_builder=ContextBuilder(timezone=reminder_timezone),
        conversation_store=conversation_store,
        search_service=search_service,
        reminder_store=reminder_store,
        reminder_timezone=reminder_timezone,
        max_tool_rounds=settings.max_tool_rounds,
    )

    async def close_ai_service(_application) -> None:
        await ai_service.aclose()
        if search_service is not None:
            await search_service.aclose()
        if transcription_service is not None:
            await transcription_service.aclose()
        if ai_client is not None:
            await ai_client.aclose()
        if transcription_client is not None:
            await transcription_client.aclose()

    application = build_telegram_app(
        settings,
        process_message,
        close_ai_service,
        transcription_service,
        reminder_store,
        reminder_timezone,
    )
    application.run_polling()


if __name__ == "__main__":
    main()

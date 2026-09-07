from __future__ import annotations

import logging

from assistant.application.context_builder import ContextBuilder
from assistant.application.process_message import ProcessMessage
from assistant.config import Settings
from assistant.infrastructure.ai.deepseek import DeepSeekAIService
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
    process_message = ProcessMessage(
        ai_service=ai_service,
        context_builder=ContextBuilder(),
    )
    application = build_telegram_app(settings, process_message)
    application.run_polling()


if __name__ == "__main__":
    main()

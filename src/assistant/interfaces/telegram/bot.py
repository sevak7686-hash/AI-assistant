from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from telegram import Update
from telegram.constants import ChatType
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from assistant.application.process_message import ProcessMessage
from assistant.config import Settings
from assistant.domain.messages import IncomingMessage

logger = logging.getLogger(__name__)
_MAX_TELEGRAM_MESSAGE_LENGTH = 4096


def _split_message(text: str) -> list[str]:
    return [
        text[index : index + _MAX_TELEGRAM_MESSAGE_LENGTH]
        for index in range(0, len(text), _MAX_TELEGRAM_MESSAGE_LENGTH)
    ]


def build_telegram_app(
    settings: Settings,
    process_message: ProcessMessage,
    post_shutdown: Callable[[Application], Awaitable[None]] | None = None,
) -> Application:
    builder = Application.builder().token(settings.telegram_bot_token)
    if post_shutdown is not None:
        builder = builder.post_shutdown(post_shutdown)
    application = builder.build()
    allowed = settings.allowed_user_ids()
    handlers = TelegramHandlers(process_message=process_message, allowed_user_ids=allowed)
    application.add_handler(CommandHandler("start", handlers.start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.on_text))
    return application


class TelegramHandlers:
    def __init__(
        self,
        *,
        process_message: ProcessMessage,
        allowed_user_ids: frozenset[int],
    ) -> None:
        self._process_message = process_message
        self._allowed_user_ids = allowed_user_ids

    def _is_allowed(self, user_id: int) -> bool:
        if not self._allowed_user_ids:
            return False
        return user_id in self._allowed_user_ids

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        del context
        if update.effective_user is None or update.effective_chat is None or update.message is None:
            return
        if update.effective_chat.type != ChatType.PRIVATE:
            logger.warning("Rejected /start from non-private chat_id=%s", update.effective_chat.id)
            return
        if not self._is_allowed(update.effective_user.id):
            logger.warning("Rejected /start from user_id=%s", update.effective_user.id)
            return
        await update.message.reply_text("Assistant is online. Send a message.")

    async def on_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        del context
        if update.effective_user is None or update.effective_chat is None or update.message is None:
            return
        if update.effective_chat.type != ChatType.PRIVATE:
            logger.warning("Rejected message from non-private chat_id=%s", update.effective_chat.id)
            return
        user_id = update.effective_user.id
        if not self._is_allowed(user_id):
            logger.warning("Rejected message from user_id=%s", user_id)
            return
        text = (update.message.text or "").strip()
        if not text:
            return
        incoming = IncomingMessage(
            user_id=user_id,
            chat_id=update.effective_chat.id,
            text=text,
        )
        outgoing = await self._process_message.execute(incoming)
        for chunk in _split_message(outgoing.text):
            await update.message.reply_text(chunk)

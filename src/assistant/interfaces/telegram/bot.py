from __future__ import annotations

import logging
from base64 import b64encode
from collections.abc import Awaitable, Callable

from telegram import Update
from telegram.constants import ChatType
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from assistant.application.process_message import ProcessMessage
from assistant.config import Settings
from assistant.domain.messages import ContentPart, IncomingMessage, MessageContent
from assistant.infrastructure.ai.service import TranscriptionService

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
    transcription_service: TranscriptionService | None = None,
) -> Application:
    builder = Application.builder().token(settings.telegram_bot_token)
    if post_shutdown is not None:
        builder = builder.post_shutdown(post_shutdown)
    application = builder.build()
    allowed = settings.allowed_user_ids()
    handlers = TelegramHandlers(
        process_message=process_message,
        allowed_user_ids=allowed,
        transcription_service=transcription_service,
    )
    application.add_handler(CommandHandler("start", handlers.start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.on_text))
    application.add_handler(
        MessageHandler(filters.PHOTO | filters.VOICE | filters.AUDIO, handlers.on_media)
    )
    return application


class TelegramHandlers:
    def __init__(
        self,
        *,
        process_message: ProcessMessage,
        allowed_user_ids: frozenset[int],
        transcription_service: TranscriptionService | None = None,
    ) -> None:
        self._process_message = process_message
        self._allowed_user_ids = allowed_user_ids
        self._transcription_service = transcription_service

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
        if not self._is_valid_message(update):
            return
        text = (update.message.text or "").strip()
        if not text:
            return
        incoming = self._incoming(update, text=text)
        await self._reply(update, incoming)

    async def on_media(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_valid_message(update):
            return
        message = update.message
        if message is None:
            return
        if message.photo:
            photo = message.photo[-1]
            telegram_file = await context.bot.get_file(photo.file_id)
            data = bytes(await telegram_file.download_as_bytearray())
            caption = (message.caption or "").strip()
            content: list[ContentPart] = [
                {"type": "text", "text": caption or "Describe this image."},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{_base64(data)}"},
                },
            ]
            incoming = self._incoming(update, text=caption or "[Image]", content=content)
        else:
            if self._transcription_service is None:
                await self._reply_error(update, "Voice messages are not configured yet.")
                return
            media = message.voice or message.audio
            if media is None:
                return
            telegram_file = await context.bot.get_file(media.file_id)
            data = bytes(await telegram_file.download_as_bytearray())
            filename = getattr(media, "file_name", None) or "voice.ogg"
            content_type = getattr(media, "mime_type", None) or "audio/ogg"
            try:
                text = (
                    await self._transcription_service.transcribe(
                        data, filename=filename, content_type=content_type
                    )
                ).strip()
            except Exception:
                logger.exception(
                    "Audio transcription failed for user_id=%s", update.effective_user.id
                )
                await self._reply_error(update, "I could not process that audio message.")
                return
            if not text:
                await self._reply_error(update, "I could not understand that audio message.")
                return
            incoming = self._incoming(update, text=text)
        await self._reply(update, incoming)

    def _is_valid_message(self, update: Update) -> bool:
        if update.effective_user is None or update.effective_chat is None or update.message is None:
            return False
        if update.effective_chat.type != ChatType.PRIVATE:
            logger.warning("Rejected message from non-private chat_id=%s", update.effective_chat.id)
            return False
        if not self._is_allowed(update.effective_user.id):
            logger.warning("Rejected message from user_id=%s", update.effective_user.id)
            return False
        return True

    def _incoming(
        self, update: Update, *, text: str, content: MessageContent | None = None
    ) -> IncomingMessage:
        assert update.effective_user is not None
        assert update.effective_chat is not None
        return IncomingMessage(
            user_id=update.effective_user.id,
            chat_id=update.effective_chat.id,
            text=text,
            content=content,
        )

    async def _reply(self, update: Update, incoming: IncomingMessage) -> None:
        outgoing = await self._process_message.execute(incoming)
        assert update.message is not None
        for chunk in _split_message(outgoing.text):
            await update.message.reply_text(chunk)

    async def _reply_error(self, update: Update, text: str) -> None:
        if update.message is not None:
            await update.message.reply_text(text)


def _base64(data: bytes) -> str:
    return b64encode(data).decode("ascii")

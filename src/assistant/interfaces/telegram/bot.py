from __future__ import annotations

import logging
from base64 import b64encode
from collections.abc import Awaitable, Callable
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.constants import ChatType
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from assistant.application.process_message import ProcessMessage
from assistant.config import Settings
from assistant.domain.messages import ContentPart, IncomingMessage, MessageContent
from assistant.infrastructure.ai.service import TranscriptionService
from assistant.infrastructure.db.reminder_store import SqlAlchemyReminderStore

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
    reminder_store: SqlAlchemyReminderStore | None = None,
    reminder_timezone: ZoneInfo | None = None,
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
        reminder_store=reminder_store,
        reminder_timezone=reminder_timezone,
    )
    application.add_handler(CommandHandler("start", handlers.start))
    application.add_handler(CommandHandler("remind", handlers.remind))
    application.add_handler(CommandHandler("reminders", handlers.reminders))
    application.add_handler(CommandHandler("remove_reminder", handlers.remove_reminder))
    application.add_handler(CommandHandler("edit_reminder", handlers.edit_reminder))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.on_text))
    application.add_handler(
        MessageHandler(filters.PHOTO | filters.VOICE | filters.AUDIO, handlers.on_media)
    )
    if reminder_store is not None:
        if application.job_queue is None:
            raise RuntimeError("Reminder support requires python-telegram-bot[job-queue]")
        application.job_queue.run_repeating(handlers.deliver_due_reminders, interval=60, first=1)
    return application


class TelegramHandlers:
    def __init__(
        self,
        *,
        process_message: ProcessMessage,
        allowed_user_ids: frozenset[int],
        transcription_service: TranscriptionService | None = None,
        reminder_store: SqlAlchemyReminderStore | None = None,
        reminder_timezone: ZoneInfo | None = None,
    ) -> None:
        self._process_message = process_message
        self._allowed_user_ids = allowed_user_ids
        self._transcription_service = transcription_service
        self._reminder_store = reminder_store
        self._reminder_timezone = reminder_timezone or ZoneInfo("Europe/Moscow")

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

    async def remind(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_valid_message(update) or self._reminder_store is None:
            return
        if len(context.args) < 2:
            await self._reply_error(update, "Use: /remind 22:00 text of the reminder")
            return
        try:
            reminder_time = datetime.strptime(context.args[0], "%H:%M").time()
        except ValueError:
            await self._reply_error(update, "Time must use 24-hour format, for example 22:00.")
            return
        due_at = _next_due_at(reminder_time, self._reminder_timezone)
        assert update.effective_user is not None
        assert update.effective_chat is not None
        reminder = await self._reminder_store.create(
            user_id=update.effective_user.id,
            chat_id=update.effective_chat.id,
            text=" ".join(context.args[1:]),
            due_at=due_at,
        )
        assert update.message is not None
        await update.message.reply_text(f"Reminder set for {reminder.due_at:%Y-%m-%d %H:%M}.")

    async def reminders(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        del context
        if not self._is_valid_message(update) or self._reminder_store is None:
            return
        assert update.effective_user is not None
        reminders = await self._reminder_store.list_pending(user_id=update.effective_user.id)
        if not reminders:
            await self._reply_error(update, "You have no pending reminders.")
            return
        lines = ["Pending reminders:"]
        lines.extend(
            f"{reminder.id}. {reminder.due_at:%Y-%m-%d %H:%M} - {reminder.text}"
            for reminder in reminders
        )
        lines.append("Use /edit_reminder ID HH:MM new text or /remove_reminder ID.")
        assert update.message is not None
        await update.message.reply_text("\n".join(lines))

    async def remove_reminder(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_valid_message(update) or self._reminder_store is None:
            return
        if len(context.args) != 1 or not context.args[0].isdigit():
            await self._reply_error(update, "Use: /remove_reminder ID")
            return
        assert update.effective_user is not None
        deleted = await self._reminder_store.delete_pending(
            user_id=update.effective_user.id,
            reminder_id=int(context.args[0]),
        )
        await self._reply_error(
            update,
            "Reminder removed." if deleted else "Pending reminder not found.",
        )

    async def edit_reminder(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_valid_message(update) or self._reminder_store is None:
            return
        if len(context.args) < 3 or not context.args[0].isdigit():
            await self._reply_error(update, "Use: /edit_reminder ID HH:MM new text")
            return
        try:
            reminder_time = datetime.strptime(context.args[1], "%H:%M").time()
        except ValueError:
            await self._reply_error(update, "Time must use 24-hour format, for example 22:00.")
            return
        due_at = _next_due_at(reminder_time, self._reminder_timezone)
        assert update.effective_user is not None
        reminder = await self._reminder_store.update_pending(
            user_id=update.effective_user.id,
            reminder_id=int(context.args[0]),
            text=" ".join(context.args[2:]),
            due_at=due_at,
        )
        await self._reply_error(
            update,
            f"Reminder updated for {reminder.due_at:%Y-%m-%d %H:%M}."
            if reminder is not None
            else "Pending reminder not found.",
        )

    async def deliver_due_reminders(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        if self._reminder_store is None:
            return
        for reminder in await self._reminder_store.claim_due():
            try:
                await context.bot.send_message(
                    chat_id=reminder.chat_id,
                    text=f"Reminder: {reminder.text}",
                )
            except Exception:
                logger.exception("Failed to send reminder_id=%s", reminder.id)
                await self._reminder_store.release(reminder.id)
            else:
                await self._reminder_store.mark_sent(reminder.id)

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


def _next_due_at(
    reminder_time: time, timezone: ZoneInfo, *, now: datetime | None = None
) -> datetime:
    current_time = (now or datetime.now(timezone)).astimezone(timezone)
    due_at = datetime.combine(current_time.date(), reminder_time, tzinfo=timezone)
    if due_at <= current_time:
        due_at += timedelta(days=1)
    return due_at

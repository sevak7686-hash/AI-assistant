from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from assistant.infrastructure.db.models import Reminder, User
from assistant.infrastructure.db.session import session_scope


class SqlAlchemyReminderStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def create(self, *, user_id: int, chat_id: int, text: str, due_at: datetime) -> Reminder:
        reminder = Reminder(user_id=user_id, chat_id=chat_id, text=text, due_at=due_at)
        async with session_scope(self._session_factory) as session:
            if await session.get(User, user_id) is None:
                session.add(User(id=user_id))
                await session.flush()
            session.add(reminder)
            await session.flush()
        return reminder

    async def claim_due(self, *, now: datetime | None = None) -> list[Reminder]:
        current_time = now or datetime.now(UTC)
        async with session_scope(self._session_factory) as session:
            result = await session.execute(
                select(Reminder)
                .where(Reminder.status == "pending", Reminder.due_at <= current_time)
                .with_for_update(skip_locked=True)
            )
            reminders = list(result.scalars().all())
            for reminder in reminders:
                reminder.status = "claimed"
                reminder.claimed_at = current_time
        return reminders

    async def list_pending(self, *, user_id: int) -> list[Reminder]:
        async with session_scope(self._session_factory) as session:
            result = await session.execute(
                select(Reminder)
                .where(Reminder.user_id == user_id, Reminder.status == "pending")
                .order_by(Reminder.due_at, Reminder.id)
            )
            return list(result.scalars().all())

    async def delete_pending(self, *, user_id: int, reminder_id: int) -> bool:
        async with session_scope(self._session_factory) as session:
            reminder = await session.get(Reminder, reminder_id)
            if reminder is None or reminder.user_id != user_id or reminder.status != "pending":
                return False
            await session.delete(reminder)
            return True

    async def update_pending(
        self, *, user_id: int, reminder_id: int, text: str, due_at: datetime
    ) -> Reminder | None:
        async with session_scope(self._session_factory) as session:
            reminder = await session.get(Reminder, reminder_id)
            if reminder is None or reminder.user_id != user_id or reminder.status != "pending":
                return None
            reminder.text = text
            reminder.due_at = due_at
            return reminder

    async def mark_sent(self, reminder_id: int) -> None:
        async with session_scope(self._session_factory) as session:
            reminder = await session.get(Reminder, reminder_id)
            if reminder is not None:
                reminder.status = "sent"
                reminder.sent_at = datetime.now(UTC)

    async def release(self, reminder_id: int) -> None:
        async with session_scope(self._session_factory) as session:
            reminder = await session.get(Reminder, reminder_id)
            if reminder is not None:
                reminder.status = "pending"
                reminder.claimed_at = None
                reminder.retry_count += 1
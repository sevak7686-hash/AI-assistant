from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from assistant.application.conversation_store import ConversationStore
from assistant.domain.messages import ChatMessage
from assistant.infrastructure.db.models import Message, User
from assistant.infrastructure.db.session import session_scope


class SqlAlchemyConversationStore(ConversationStore):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def list_recent(
        self, *, user_id: int, chat_id: int, limit: int = 20
    ) -> list[ChatMessage]:
        async with session_scope(self._session_factory) as session:
            result = await session.execute(
                select(Message)
                .where(Message.user_id == user_id, Message.chat_id == chat_id)
                .order_by(Message.created_at.desc(), Message.id.desc())
                .limit(limit)
            )
            messages = result.scalars().all()

        return [
            ChatMessage(role=message.role, content=message.content)
            for message in reversed(messages)
        ]

    async def append(self, *, user_id: int, chat_id: int, message: ChatMessage) -> None:
        async with session_scope(self._session_factory) as session:
            if await session.get(User, user_id) is None:
                session.add(User(id=user_id))
                await session.flush()
            session.add(
                Message(
                    user_id=user_id,
                    chat_id=chat_id,
                    role=message.role,
                    content=message.content,
                )
            )

from contextlib import asynccontextmanager

from assistant.domain.messages import ChatMessage
from assistant.infrastructure.db import conversation_store
from assistant.infrastructure.db.conversation_store import SqlAlchemyConversationStore
from assistant.infrastructure.db.models import Message, User


class FakeSession:
    def __init__(self) -> None:
        self.actions: list[object] = []

    async def get(self, model, user_id: int):
        self.actions.append(("get", model, user_id))
        return None

    def add(self, value: object) -> None:
        self.actions.append(("add", value))

    async def flush(self) -> None:
        self.actions.append(("flush",))


class FakeSessionFactory:
    def __init__(self, session: FakeSession) -> None:
        self.session = session


async def test_append_flushes_user_before_message(monkeypatch) -> None:
    session = FakeSession()

    @asynccontextmanager
    async def fake_session_scope(session_factory):
        del session_factory
        yield session

    monkeypatch.setattr(conversation_store, "session_scope", fake_session_scope)
    store = SqlAlchemyConversationStore(FakeSessionFactory(session))

    await store.append(
        user_id=42,
        chat_id=99,
        message=ChatMessage(role="user", content="hello"),
    )

    assert isinstance(session.actions[1][1], User)
    assert session.actions[2] == ("flush",)
    assert isinstance(session.actions[3][1], Message)

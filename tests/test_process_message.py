from collections.abc import Sequence

from assistant.application.context_builder import ContextBuilder
from assistant.application.process_message import ProcessMessage
from assistant.domain.messages import ChatMessage, IncomingMessage


class FakeAIService:
    def __init__(self, reply: str = "ok") -> None:
        self.reply = reply
        self.received: list[Sequence[ChatMessage]] = []

    async def complete(self, messages: Sequence[ChatMessage]) -> str:
        self.received.append(messages)
        return self.reply


class FailingAIService:
    async def complete(self, messages: Sequence[ChatMessage]) -> str:
        del messages
        raise RuntimeError("upstream down")


class FakeConversationStore:
    def __init__(self, history: list[ChatMessage] | None = None) -> None:
        self.history = history or []
        self.appended: list[ChatMessage] = []

    async def list_recent(self, *, user_id: int, chat_id: int, limit: int = 20):
        del user_id, chat_id, limit
        return self.history

    async def append(self, *, user_id: int, chat_id: int, message: ChatMessage) -> None:
        del user_id, chat_id
        self.appended.append(message)


async def test_execute_returns_ai_reply() -> None:
    fake = FakeAIService(reply="Hi there")
    service = ProcessMessage(ai_service=fake, context_builder=ContextBuilder())
    incoming = IncomingMessage(user_id=42, chat_id=99, text="Hello")

    outgoing = await service.execute(incoming)

    assert outgoing.chat_id == 99
    assert outgoing.text == "Hi there"
    assert fake.received[0][-1].content == "Hello"


async def test_execute_returns_fallback_when_ai_fails() -> None:
    service = ProcessMessage(ai_service=FailingAIService(), context_builder=ContextBuilder())
    incoming = IncomingMessage(user_id=1, chat_id=2, text="Hello")

    outgoing = await service.execute(incoming)

    assert outgoing.chat_id == 2
    assert "try again" in outgoing.text.lower()


async def test_execute_uses_and_persists_conversation_history() -> None:
    fake = FakeAIService(reply="The earlier answer")
    store = FakeConversationStore([ChatMessage(role="user", content="My name is Ana")])
    service = ProcessMessage(
        ai_service=fake,
        context_builder=ContextBuilder(),
        conversation_store=store,
    )

    await service.execute(IncomingMessage(user_id=42, chat_id=99, text="What is my name?"))

    assert [message.content for message in fake.received[0]] == [
        fake.received[0][0].content,
        "My name is Ana",
        "What is my name?",
    ]
    assert store.appended == [
        ChatMessage(role="user", content="What is my name?"),
        ChatMessage(role="assistant", content="The earlier answer"),
    ]

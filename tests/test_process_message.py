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

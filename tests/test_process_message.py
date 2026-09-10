from collections.abc import Sequence
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from assistant.application.context_builder import ContextBuilder
from assistant.application.process_message import ProcessMessage
from assistant.domain.messages import ChatMessage, IncomingMessage, ToolCall
from assistant.infrastructure.ai.service import AICompletion


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


class ToolCallingAIService:
    def __init__(self) -> None:
        self.calls = []

    async def complete(self, messages, *, tools=()):
        self.calls.append((messages, tools))
        if len(self.calls) == 1:
            return AICompletion(
                tool_calls=(
                    ToolCall(
                        id="call-1",
                        name="web_search",
                        arguments='{"query":"latest technology news"}',
                    ),
                )
            )
        assert messages[-1].role == "tool"
        assert "Example" in messages[-1].content
        return AICompletion(content="Here is the latest result: https://example.test")


class FakeSearchService:
    async def search(self, query: str):
        assert query == "latest technology news"
        return [
            type(
                "Result",
                (),
                {"title": "Example", "url": "https://example.test", "snippet": "A result."},
            )()
        ]


class FailingSearchService:
    async def search(self, query: str):
        del query
        from assistant.infrastructure.search.serpapi import SearchError

        raise SearchError("SerpAPI account is not activated")


class SearchFailureAIService:
    def __init__(self) -> None:
        self.calls = 0

    async def complete(self, messages, *, tools=()):
        self.calls += 1
        if self.calls == 1:
            return AICompletion(
                tool_calls=(
                    ToolCall(id="call-1", name="web_search", arguments='{"query":"weather"}'),
                )
            )
        assert messages[-1].role == "tool"
        assert "temporarily unavailable" in messages[-1].content
        return AICompletion(content="I cannot access live search right now.")


class ReminderAIService:
    def __init__(self, due_at: str) -> None:
        self.due_at = due_at
        self.calls = []

    async def complete(self, messages, *, tools=()):
        self.calls.append((messages, tools))
        if len(self.calls) == 1:
            return AICompletion(
                tool_calls=(
                    ToolCall(
                        id="reminder-1",
                        name="create_reminder",
                        arguments=f'{{"text":"take medicine","due_at":"{self.due_at}"}}',
                    ),
                )
            )
        assert messages[-1].role == "tool"
        assert '"created": true' in messages[-1].content
        return AICompletion(content="Reminder created.")


class FakeReminderCreator:
    def __init__(self) -> None:
        self.created = []

    async def create(self, *, user_id: int, chat_id: int, text: str, due_at: datetime):
        reminder = type(
            "Reminder",
            (),
            {"id": 8, "user_id": user_id, "chat_id": chat_id, "text": text, "due_at": due_at},
        )()
        self.created.append(reminder)
        return reminder


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


async def test_execute_lets_model_search_and_returns_final_reply() -> None:
    ai_service = ToolCallingAIService()
    service = ProcessMessage(
        ai_service=ai_service,
        context_builder=ContextBuilder(),
        search_service=FakeSearchService(),
    )

    outgoing = await service.execute(
        IncomingMessage(user_id=42, chat_id=99, text="What is happening in tech?")
    )

    assert outgoing.text == "Here is the latest result: https://example.test"
    assert len(ai_service.calls) == 2
    assert ai_service.calls[0][1][0]["function"]["name"] == "web_search"


async def test_execute_returns_model_reply_when_search_is_unavailable() -> None:
    ai_service = SearchFailureAIService()
    service = ProcessMessage(
        ai_service=ai_service,
        context_builder=ContextBuilder(),
        search_service=FailingSearchService(),
    )

    outgoing = await service.execute(IncomingMessage(user_id=42, chat_id=99, text="Search"))

    assert outgoing.text == "I cannot access live search right now."


async def test_execute_creates_reminder_from_natural_language_request() -> None:
    timezone = ZoneInfo("Europe/Moscow")
    due_at = (datetime.now(timezone) + timedelta(hours=1)).isoformat()
    ai_service = ReminderAIService(due_at)
    reminder_store = FakeReminderCreator()
    service = ProcessMessage(
        ai_service=ai_service,
        context_builder=ContextBuilder(),
        reminder_store=reminder_store,
        reminder_timezone=timezone,
    )

    outgoing = await service.execute(
        IncomingMessage(user_id=42, chat_id=99, text="Remind me to take medicine in one hour")
    )

    assert outgoing.text == "Reminder created."
    assert reminder_store.created[0].user_id == 42
    assert reminder_store.created[0].chat_id == 99
    assert reminder_store.created[0].text == "take medicine"
    assert ai_service.calls[0][1][0]["function"]["name"] == "create_reminder"

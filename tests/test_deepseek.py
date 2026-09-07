from assistant.domain.messages import ChatMessage
from assistant.infrastructure.ai.deepseek import DeepSeekAIService


async def test_complete_sends_multi_turn_history_and_output_limit(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"choices": [{"message": {"content": "The answer is 4."}}]}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return None

        async def post(self, url, *, json, headers):
            captured["url"] = url
            captured["json"] = json
            captured["headers"] = headers
            return FakeResponse()

    monkeypatch.setattr("httpx.AsyncClient", lambda timeout: FakeClient())
    service = DeepSeekAIService(
        api_key="key",
        base_url="https://example.test/",
        model="deepseek-chat",
        max_tokens=128,
    )
    messages = [
        ChatMessage(role="system", content="Answer briefly."),
        ChatMessage(role="user", content="What is 2 + 2?"),
        ChatMessage(role="assistant", content="It is 4."),
        ChatMessage(role="user", content="Repeat the answer."),
    ]

    reply = await service.complete(messages)

    assert reply == "The answer is 4."
    assert captured["url"] == "https://example.test/chat/completions"
    assert captured["json"] == {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": "Answer briefly."},
            {"role": "user", "content": "What is 2 + 2?"},
            {"role": "assistant", "content": "It is 4."},
            {"role": "user", "content": "Repeat the answer."},
        ],
        "max_tokens": 128,
    }
    assert captured["headers"] == {
        "Authorization": "Bearer key",
        "Content-Type": "application/json",
    }

import httpx
import pytest

from assistant.domain.messages import ChatMessage, ToolCall
from assistant.infrastructure.ai.deepseek import DeepSeekAIService, DeepSeekError


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


async def test_complete_reuses_owned_client_and_closes_it(monkeypatch) -> None:
    calls = 0

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"choices": [{"message": {"content": "ok"}}]}

    class FakeClient:
        async def post(self, url, *, json, headers):
            nonlocal calls
            calls += 1
            return FakeResponse()

        async def aclose(self) -> None:
            self.closed = True

    client = FakeClient()
    monkeypatch.setattr("httpx.AsyncClient", lambda timeout: client)
    service = DeepSeekAIService(api_key="key", base_url="https://example.test", model="model")

    assert await service.complete([]) == "ok"
    assert await service.complete([]) == "ok"
    await service.aclose()

    assert calls == 2
    assert client.closed is True


async def test_http_status_error_is_wrapped(monkeypatch) -> None:
    request = httpx.Request("POST", "https://example.test/chat/completions")
    response = httpx.Response(503, request=request, text="upstream unavailable")

    class FakeResponse:
        def raise_for_status(self) -> None:
            raise httpx.HTTPStatusError("server error", request=request, response=response)

    class FakeClient:
        async def post(self, url, *, json, headers):
            return FakeResponse()

    monkeypatch.setattr("httpx.AsyncClient", lambda timeout: FakeClient())
    service = DeepSeekAIService(api_key="key", base_url="https://example.test", model="model")

    with pytest.raises(DeepSeekError, match="HTTP 503: upstream unavailable"):
        await service.complete([])


async def test_complete_serializes_tool_call_and_result_messages(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"choices": [{"message": {"content": "Final answer"}}]}

    class FakeClient:
        async def post(self, url, *, json, headers):
            del url, headers
            captured["json"] = json
            return FakeResponse()

    monkeypatch.setattr("httpx.AsyncClient", lambda timeout: FakeClient())
    service = DeepSeekAIService(api_key="key", base_url="https://example.test", model="model")
    messages = [
        ChatMessage(
            role="assistant",
            content="",
            tool_calls=(ToolCall(id="call-1", name="web_search", arguments='{"query":"x"}'),),
        ),
        ChatMessage(role="tool", content="results", tool_call_id="call-1"),
    ]

    await service.complete(messages, tools=[{"type": "function"}])

    assert captured["json"]["messages"] == [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call-1",
                    "type": "function",
                    "function": {"name": "web_search", "arguments": '{"query":"x"}'},
                }
            ],
        },
        {"role": "tool", "content": "results", "tool_call_id": "call-1"},
    ]

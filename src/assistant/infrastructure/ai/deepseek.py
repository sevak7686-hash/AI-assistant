from collections.abc import Sequence

import httpx

from assistant.domain.messages import ChatMessage, ToolCall
from assistant.infrastructure.ai.service import AICompletion, ToolDefinition


class DeepSeekError(RuntimeError):
    pass


class DeepSeekAIService:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        max_tokens: int | None = None,
        timeout_seconds: float = 60.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key = api_key
        self._url = f"{base_url.rstrip('/')}/chat/completions"
        self._model = model
        self._max_tokens = max_tokens
        self._client = client or httpx.AsyncClient(timeout=timeout_seconds)
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def complete(
        self, messages: Sequence[ChatMessage], *, tools: Sequence[ToolDefinition] = ()
    ) -> AICompletion:
        payload = {
            "model": self._model,
            "messages": [_serialize_message(message) for message in messages],
        }
        if self._max_tokens is not None:
            payload["max_tokens"] = self._max_tokens
        if tools:
            payload["tools"] = list(tools)
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        try:
            response = await self._client.post(self._url, json=payload, headers=headers)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise DeepSeekError(
                f"DeepSeek HTTP {exc.response.status_code}: {exc.response.text[:300]}"
            ) from exc
        except httpx.HTTPError as exc:
            raise DeepSeekError(f"DeepSeek request failed: {exc}") from exc

        try:
            data = response.json()
        except ValueError as exc:
            raise DeepSeekError("DeepSeek returned invalid JSON") from exc
        try:
            message = data["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise DeepSeekError("DeepSeek returned an unexpected response shape") from exc
        if not isinstance(message, dict):
            raise DeepSeekError("DeepSeek returned an unexpected response shape")
        content = message.get("content") or ""
        raw_tool_calls = message.get("tool_calls") or []
        if not isinstance(content, str) or not isinstance(raw_tool_calls, list):
            raise DeepSeekError("DeepSeek returned an unexpected response shape")
        tool_calls: list[ToolCall] = []
        for raw_call in raw_tool_calls:
            try:
                function = raw_call["function"]
                tool_calls.append(
                    ToolCall(
                        id=str(raw_call["id"]),
                        name=str(function["name"]),
                        arguments=str(function["arguments"]),
                    )
                )
            except (KeyError, TypeError) as exc:
                raise DeepSeekError("DeepSeek returned an invalid tool call") from exc
        if not content.strip() and not tool_calls:
            raise DeepSeekError("DeepSeek returned an empty reply")
        completion = AICompletion(content=content.strip(), tool_calls=tool_calls)
        return completion if tools or tool_calls else completion.content


def _serialize_message(message: ChatMessage) -> dict[str, object]:
    serialized: dict[str, object] = {"role": message.role, "content": message.content}
    if message.tool_calls:
        serialized["tool_calls"] = [
            {
                "id": call.id,
                "type": "function",
                "function": {"name": call.name, "arguments": call.arguments},
            }
            for call in message.tool_calls
        ]
    if message.tool_call_id is not None:
        serialized["tool_call_id"] = message.tool_call_id
    return serialized

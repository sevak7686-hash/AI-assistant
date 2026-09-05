from collections.abc import Sequence

import httpx

from assistant.domain.messages import ChatMessage


class DeepSeekError(RuntimeError):
    pass


class DeepSeekAIService:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        timeout_seconds: float = 60.0,
    ) -> None:
        self._api_key = api_key
        self._url = f"{base_url.rstrip('/')}/chat/completions"
        self._model = model
        self._timeout_seconds = timeout_seconds

    async def complete(self, messages: Sequence[ChatMessage]) -> str:
        payload = {
            "model": self._model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                response = await client.post(self._url, json=payload, headers=headers)
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
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise DeepSeekError("DeepSeek returned an unexpected response shape") from exc
        if not isinstance(content, str) or not content.strip():
            raise DeepSeekError("DeepSeek returned an empty reply")
        return content.strip()

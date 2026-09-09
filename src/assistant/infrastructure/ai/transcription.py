import httpx


class TranscriptionError(RuntimeError):
    pass


class OpenAITranscriptionService:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://openrouter.ai/api/v1",
        model: str = "openai/gpt-4o-mini-transcribe",
        language: str = "ru",
        timeout_seconds: float = 120.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key = api_key
        self._url = f"{base_url.rstrip('/')}/audio/transcriptions"
        self._model = model
        self._language = language
        self._client = client or httpx.AsyncClient(timeout=timeout_seconds)
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def transcribe(self, audio: bytes, *, filename: str, content_type: str) -> str:
        try:
            response = await self._client.post(
                self._url,
                headers={"Authorization": f"Bearer {self._api_key}"},
                data={"model": self._model, "language": self._language},
                files={"file": (filename, audio, content_type)},
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise TranscriptionError(
                f"Transcription HTTP {exc.response.status_code}: {exc.response.text[:300]}"
            ) from exc
        except httpx.HTTPError as exc:
            raise TranscriptionError(f"Transcription request failed: {exc}") from exc
        try:
            text = response.json()["text"]
        except (KeyError, TypeError, ValueError) as exc:
            raise TranscriptionError("Transcription returned an unexpected response shape") from exc
        if not isinstance(text, str) or not text.strip():
            raise TranscriptionError("Transcription returned an empty result")
        return text.strip()

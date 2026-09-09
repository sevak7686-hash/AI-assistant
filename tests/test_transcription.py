from assistant.infrastructure.ai.transcription import OpenAITranscriptionService


async def test_transcribe_sends_audio_multipart_request() -> None:
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"text": " Привет, мир "}

    class FakeClient:
        async def post(self, url, *, headers, data, files):
            captured.update(url=url, headers=headers, data=data, files=files)
            return FakeResponse()

    service = OpenAITranscriptionService(
        api_key="key",
        base_url="https://example.test/v1",
        model="whisper-1",
        language="ru",
        client=FakeClient(),
    )

    assert await service.transcribe(b"audio", filename="voice.ogg", content_type="audio/ogg") == (
        "Привет, мир"
    )
    assert captured["url"] == "https://example.test/v1/audio/transcriptions"
    assert captured["headers"] == {"Authorization": "Bearer key"}
    assert captured["data"] == {"model": "whisper-1", "language": "ru"}
    assert captured["files"]["file"] == ("voice.ogg", b"audio", "audio/ogg")

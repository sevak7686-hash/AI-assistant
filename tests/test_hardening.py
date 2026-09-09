from types import SimpleNamespace

import pytest
from telegram.constants import ChatType

from assistant.config import Settings
from assistant.domain.messages import OutgoingMessage
from assistant.infrastructure.ai.deepseek import DeepSeekAIService, DeepSeekError
from assistant.interfaces.telegram.bot import TelegramHandlers, _split_message


class FakeProcessMessage:
    def __init__(self) -> None:
        self.received = []

    async def execute(self, incoming):
        self.received.append(incoming)
        return OutgoingMessage(chat_id=incoming.chat_id, text="x" * 5000)


class ReplyMessage:
    def __init__(self, text: str) -> None:
        self.text = text
        self.replies: list[str] = []

    async def reply_text(self, text: str) -> None:
        self.replies.append(text)


def make_update(*, chat_type: str = ChatType.PRIVATE, text: str = "hello"):
    message = ReplyMessage(text)
    return (
        SimpleNamespace(
            effective_user=SimpleNamespace(id=42),
            effective_chat=SimpleNamespace(id=99, type=chat_type),
            message=message,
        ),
        message,
    )


def test_empty_allow_list_fails_closed() -> None:
    handlers = TelegramHandlers(process_message=FakeProcessMessage(), allowed_user_ids=frozenset())

    assert handlers._is_allowed(42) is False


def test_malformed_allow_list_has_clear_error() -> None:
    settings = Settings(
        telegram_bot_token="token",
        deepseek_api_key="key",
        allowed_telegram_user_ids="not-an-id",
    )

    with pytest.raises(ValueError, match="comma-separated integers"):
        settings.allowed_user_ids()


async def test_group_messages_are_rejected() -> None:
    handlers = TelegramHandlers(
        process_message=FakeProcessMessage(), allowed_user_ids=frozenset({42})
    )
    update, message = make_update(chat_type=ChatType.GROUP)

    await handlers.on_text(update, None)

    assert message.replies == []


async def test_long_replies_are_split_for_telegram() -> None:
    handlers = TelegramHandlers(
        process_message=FakeProcessMessage(), allowed_user_ids=frozenset({42})
    )
    update, message = make_update()

    await handlers.on_text(update, None)

    assert [len(reply) for reply in message.replies] == [4096, 904]


async def test_photo_is_forwarded_as_multimodal_content() -> None:
    process = FakeProcessMessage()
    handlers = TelegramHandlers(process_message=process, allowed_user_ids=frozenset({42}))
    update, message = make_update()
    message.text = None
    message.caption = "Что на фото?"
    message.photo = [SimpleNamespace(file_id="photo-id")]
    message.voice = None
    message.audio = None

    class FakeTelegramFile:
        async def download_as_bytearray(self):
            return bytearray(b"image")

    class FakeBot:
        async def get_file(self, file_id):
            assert file_id == "photo-id"
            return FakeTelegramFile()

    await handlers.on_media(update, SimpleNamespace(bot=FakeBot()))

    assert process.received[0].text == "Что на фото?"
    assert process.received[0].content[0] == {"type": "text", "text": "Что на фото?"}
    assert process.received[0].content[1]["image_url"]["url"].endswith("aW1hZ2U=")


async def test_voice_is_transcribed_before_processing() -> None:
    process = FakeProcessMessage()

    class FakeTranscription:
        async def transcribe(self, audio, *, filename, content_type):
            assert audio == b"voice"
            assert filename == "voice.ogg"
            assert content_type == "audio/ogg"
            return "  Привет, помощник  "

    handlers = TelegramHandlers(
        process_message=process,
        allowed_user_ids=frozenset({42}),
        transcription_service=FakeTranscription(),
    )
    update, message = make_update()
    message.text = None
    message.photo = []
    message.voice = SimpleNamespace(file_id="voice-id")
    message.audio = None

    class FakeTelegramFile:
        async def download_as_bytearray(self):
            return bytearray(b"voice")

    class FakeBot:
        async def get_file(self, file_id):
            assert file_id == "voice-id"
            return FakeTelegramFile()

    await handlers.on_media(update, SimpleNamespace(bot=FakeBot()))

    assert process.received[0].text == "Привет, помощник"


def test_split_message_preserves_short_text() -> None:
    assert _split_message("hello") == ["hello"]


async def test_invalid_provider_json_raises_deepseek_error(monkeypatch) -> None:
    class InvalidJsonResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self):
            raise ValueError("invalid json")

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return None

        async def post(self, url, *, json, headers):
            return InvalidJsonResponse()

    monkeypatch.setattr("httpx.AsyncClient", lambda timeout: FakeClient())
    service = DeepSeekAIService(api_key="key", base_url="https://example.test", model="model")

    with pytest.raises(DeepSeekError, match="invalid JSON"):
        await service.complete([])

from collections.abc import Sequence
from typing import Protocol

from assistant.domain.messages import ChatMessage


class AIService(Protocol):
    async def complete(self, messages: Sequence[ChatMessage]) -> str:
        """Return the assistant's text reply for the given chat context."""


class TranscriptionService(Protocol):
    async def transcribe(self, audio: bytes, *, filename: str, content_type: str) -> str:
        """Return the spoken content as text."""

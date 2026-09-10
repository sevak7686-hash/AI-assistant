from collections.abc import Sequence
from typing import Protocol

from assistant.domain.messages import ChatMessage, ToolCall

ToolDefinition = dict[str, object]


class AICompletion:
    def __init__(self, *, content: str = "", tool_calls: Sequence[ToolCall] = ()) -> None:
        self.content = content
        self.tool_calls = tuple(tool_calls)

    @property
    def has_tool_calls(self) -> bool:
        return bool(self.tool_calls)


class AIService(Protocol):
    async def complete(
        self, messages: Sequence[ChatMessage], *, tools: Sequence[ToolDefinition] = ()
    ) -> AICompletion | str:
        """Return text or a request to execute one or more tools."""


class TranscriptionService(Protocol):
    async def transcribe(self, audio: bytes, *, filename: str, content_type: str) -> str:
        """Return the spoken content as text."""

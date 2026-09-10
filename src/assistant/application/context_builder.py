from collections.abc import Sequence
from datetime import datetime
from zoneinfo import ZoneInfo

from assistant.application.prompts import SYSTEM_PROMPT
from assistant.domain.messages import ChatMessage, IncomingMessage


class ContextBuilder:
    """Build the system prompt, prior conversation, and current user message."""

    def __init__(
        self,
        system_prompt: str = SYSTEM_PROMPT,
        timezone: ZoneInfo | None = None,
        clock=None,
    ) -> None:
        self._system_prompt = system_prompt
        self._timezone = timezone or ZoneInfo("UTC")
        self._clock = clock or datetime.now

    def build(
        self, incoming: IncomingMessage, history: Sequence[ChatMessage] = ()
    ) -> Sequence[ChatMessage]:
        safe_history = tuple(
            message for message in history if message.role != "tool" and not message.tool_calls
        )
        current_time = self._clock(self._timezone)
        system_prompt = (
            f"{self._system_prompt}\n\n"
            "## Current date and time\n"
            f"Today is {current_time:%Y-%m-%d} and the current time is "
            f"{current_time:%H:%M} in {self._timezone.key}. Use this for relative dates "
            "such as today, tomorrow, and in one hour."
        )
        return (
            ChatMessage(role="system", content=system_prompt),
            *safe_history,
            ChatMessage(role="user", content=incoming.content or incoming.text),
        )

from collections.abc import Sequence

from assistant.application.prompts import SYSTEM_PROMPT
from assistant.domain.messages import ChatMessage, IncomingMessage


class ContextBuilder:
    """Build the system prompt, prior conversation, and current user message."""

    def __init__(self, system_prompt: str = SYSTEM_PROMPT) -> None:
        self._system_prompt = system_prompt

    def build(
        self, incoming: IncomingMessage, history: Sequence[ChatMessage] = ()
    ) -> Sequence[ChatMessage]:
        safe_history = tuple(
            message for message in history if message.role != "tool" and not message.tool_calls
        )
        return (
            ChatMessage(role="system", content=self._system_prompt),
            *safe_history,
            ChatMessage(role="user", content=incoming.content or incoming.text),
        )

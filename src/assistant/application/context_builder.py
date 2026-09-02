from collections.abc import Sequence

from assistant.application.prompts import SYSTEM_PROMPT
from assistant.domain.messages import ChatMessage, IncomingMessage


class ContextBuilder:
    """Builds the LLM message list. Stage 1 uses only system prompt + current text."""

    def __init__(self, system_prompt: str = SYSTEM_PROMPT) -> None:
        self._system_prompt = system_prompt

    def build(self, incoming: IncomingMessage) -> Sequence[ChatMessage]:
        return (
            ChatMessage(role="system", content=self._system_prompt),
            ChatMessage(role="user", content=incoming.text),
        )

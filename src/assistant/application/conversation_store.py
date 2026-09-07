from collections.abc import Sequence
from typing import Protocol

from assistant.domain.messages import ChatMessage


class ConversationStore(Protocol):
    async def list_recent(
        self, *, user_id: int, chat_id: int, limit: int = 20
    ) -> Sequence[ChatMessage]:
        """Return recent messages in chronological order."""

    async def append(self, *, user_id: int, chat_id: int, message: ChatMessage) -> None:
        """Persist one conversation message."""

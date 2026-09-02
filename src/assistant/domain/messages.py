from dataclasses import dataclass
from typing import Literal

Role = Literal["system", "user", "assistant"]


@dataclass(frozen=True)
class IncomingMessage:
    user_id: int
    chat_id: int
    text: str


@dataclass(frozen=True)
class OutgoingMessage:
    chat_id: int
    text: str


@dataclass(frozen=True)
class ChatMessage:
    role: Role
    content: str

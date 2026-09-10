from dataclasses import dataclass
from typing import Literal, TypeAlias

Role = Literal["system", "user", "assistant", "tool"]
ContentPart: TypeAlias = dict[str, object]
MessageContent: TypeAlias = str | list[ContentPart]


@dataclass(frozen=True)
class IncomingMessage:
    user_id: int
    chat_id: int
    text: str
    content: MessageContent | None = None


@dataclass(frozen=True)
class OutgoingMessage:
    chat_id: int
    text: str


@dataclass(frozen=True)
class ChatMessage:
    role: Role
    content: MessageContent
    tool_calls: tuple["ToolCall", ...] = ()
    tool_call_id: str | None = None


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: str

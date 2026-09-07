"""SQLAlchemy ORM models."""

from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from assistant.infrastructure.db.base import Base


class ConversationMessage(Base):
    __tablename__ = "conversation_messages"
    __table_args__ = (
        CheckConstraint(
            "role IN ('system', 'user', 'assistant')",
            name="ck_conversation_messages_role",
        ),
        Index(
            "ix_conversation_messages_conversation_created",
            "user_id",
            "chat_id",
            "created_at",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str | None] = mapped_column(String(255))
    first_name: Mapped[str | None] = mapped_column(String(255))
    last_name: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint("role IN ('system', 'user', 'assistant')", name="ck_messages_role"),
        Index("ix_messages_conversation_created", "user_id", "chat_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


class MemoryEntry(Base):
    __tablename__ = "memory_entries"
    __table_args__ = (Index("ix_memory_entries_user_created", "user_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    source_message_id: Mapped[int | None] = mapped_column(ForeignKey("messages.id"))
    memory_type: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


__all__ = ["Base", "ConversationMessage", "MemoryEntry", "Message", "User"]

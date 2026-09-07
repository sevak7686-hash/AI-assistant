"""Create messages and memory entries tables.

Revision ID: 0003
Revises: 0002
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "messages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "role IN ('system', 'user', 'assistant')",
            name="ck_messages_role",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_messages_conversation_created",
        "messages",
        ["user_id", "chat_id", "created_at"],
    )

    op.create_table(
        "memory_entries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("source_message_id", sa.Integer(), nullable=True),
        sa.Column("memory_type", sa.String(length=32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["source_message_id"], ["messages.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_memory_entries_user_created",
        "memory_entries",
        ["user_id", "created_at"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_memory_entries_user_created", table_name="memory_entries")
    op.drop_table("memory_entries")
    op.drop_index("ix_messages_conversation_created", table_name="messages")
    op.drop_table("messages")

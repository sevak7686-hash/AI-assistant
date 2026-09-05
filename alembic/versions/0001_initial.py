"""Create the initial conversation message schema.

Revision ID: 0001
Revises:
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "conversation_messages",
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
            name="ck_conversation_messages_role",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_conversation_messages_conversation_created",
        "conversation_messages",
        ["user_id", "chat_id", "created_at"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "ix_conversation_messages_conversation_created",
        table_name="conversation_messages",
    )
    op.drop_table("conversation_messages")

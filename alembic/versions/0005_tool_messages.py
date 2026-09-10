"""Support persisted tool messages.

Revision ID: 0005
Revises: 0004
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("messages") as batch_op:
        batch_op.drop_constraint("ck_messages_role", type_="check")
        batch_op.create_check_constraint(
            "ck_messages_role",
            "role IN ('system', 'user', 'assistant', 'tool')",
        )
        batch_op.add_column(sa.Column("tool_call_id", sa.String(length=128), nullable=True))
        batch_op.add_column(sa.Column("tool_calls", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("messages") as batch_op:
        batch_op.drop_column("tool_calls")
        batch_op.drop_column("tool_call_id")
        batch_op.drop_constraint("ck_messages_role", type_="check")
        batch_op.create_check_constraint(
            "ck_messages_role",
            "role IN ('system', 'user', 'assistant')",
        )

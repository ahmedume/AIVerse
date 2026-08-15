"""messages seq column for deterministic ordering

Revision ID: 9d1c3b2f4a5e
Revises: 50491b68a161
Create Date: 2026-08-15 15:15:00.000000

"""

import sqlalchemy as sa

from alembic import op

revision = "9d1c3b2f4a5e"
down_revision = "50491b68a161"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "messages",
        sa.Column("seq", sa.Integer(), nullable=False, server_default="0"),
    )
    op.drop_index("ix_messages_conversation_created", table_name="messages")
    op.create_index(
        "ix_messages_conversation_seq", "messages", ["conversation_id", "seq"]
    )

    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            "SELECT id, conversation_id FROM messages "
            "ORDER BY conversation_id, created_at, id"
        )
    ).fetchall()
    counters: dict[str, int] = {}
    for row in rows:
        seq = counters.get(row[1], 0) + 1
        counters[row[1]] = seq
        connection.execute(
            sa.text("UPDATE messages SET seq = :seq WHERE id = :id"),
            {"seq": seq, "id": row[0]},
        )


def downgrade() -> None:
    op.drop_index("ix_messages_conversation_seq", table_name="messages")
    op.create_index(
        "ix_messages_conversation_created", "messages", ["conversation_id", "created_at"]
    )
    op.drop_column("messages", "seq")
"""Add timeline_events table for agent timeline logging.

Stores append-only timeline events (messages and history truncation)
per thread, replacing the file-based agent_timeline.json approach.

Revision ID: 002
Revises: 001
Create Date: 2026-02-25
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "timeline_events",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("thread_id", sa.String(64), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("stage", sa.String(32), nullable=True),
        sa.Column("message_index", sa.Integer, nullable=True),
        sa.Column("role", sa.String(32), nullable=True),
        sa.Column("message_id", sa.Text, nullable=True),
        sa.Column(
            "message_data",
            sa.JSON().with_variant(sa.dialects.postgresql.JSONB, "postgresql"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("idx_timeline_thread_id", "timeline_events", ["thread_id"])
    op.create_index("idx_timeline_created_at", "timeline_events", ["created_at"])


def downgrade() -> None:
    op.drop_table("timeline_events")

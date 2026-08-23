"""Add composite indexes for cursor pagination.

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-23
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_submissions_created_id",
        "submissions",
        ["created_at", "id"],
        unique=False,
    )
    op.create_index(
        "ix_submissions_risk_cursor",
        "submissions",
        [
            sa.text("risk_score DESC"),
            sa.text("created_at ASC"),
            sa.text("id ASC"),
        ],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_submissions_risk_cursor", table_name="submissions")
    op.drop_index("ix_submissions_created_id", table_name="submissions")

"""Add scan-job claim ownership token.

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-24
"""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "scan_jobs",
        sa.Column("claim_token", sa.String(length=36), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("scan_jobs", "claim_token")

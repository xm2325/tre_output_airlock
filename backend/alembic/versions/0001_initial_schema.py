"""Initial airlock schema.

Revision ID: 0001
Revises:
Create Date: 2026-07-14
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "submissions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("project_code", sa.String(length=80), nullable=False),
        sa.Column("output_type", sa.String(length=40), nullable=False),
        sa.Column("output_description", sa.Text(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=120), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=120), nullable=True, unique=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("automated_decision", sa.String(length=24), nullable=False),
        sa.Column("final_decision", sa.String(length=24), nullable=True),
        sa.Column("risk_score", sa.Float(), nullable=False),
        sa.Column("policy_version", sa.String(length=64), nullable=False),
        sa.Column("submitted_by", sa.String(length=120), nullable=False),
        sa.Column("reviewer", sa.String(length=120), nullable=True),
        sa.Column("review_rationale", sa.Text(), nullable=True),
        sa.Column("claimed_by", sa.String(length=120), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("row_version", sa.Integer(), nullable=False),
        sa.Column("file_deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_submissions_project_code", "submissions", ["project_code"])
    op.create_index("ix_submissions_sha256", "submissions", ["sha256"])
    op.create_index("ix_submissions_status", "submissions", ["status"])
    op.create_index("ix_submissions_claimed_by", "submissions", ["claimed_by"])

    op.create_table(
        "findings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "submission_id",
            sa.String(length=36),
            sa.ForeignKey("submissions.id"),
            nullable=False,
        ),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("evidence", sa.Text(), nullable=True),
    )
    op.create_index("ix_findings_submission_id", "findings", ["submission_id"])

    op.create_table(
        "audit_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "submission_id",
            sa.String(length=36),
            sa.ForeignKey("submissions.id"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("actor", sa.String(length=120), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column("request_id", sa.String(length=80), nullable=True),
        sa.Column("prev_hash", sa.String(length=64), nullable=False),
        sa.Column("event_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_audit_events_submission_id", "audit_events", ["submission_id"])
    op.create_index("ix_audit_events_event_hash", "audit_events", ["event_hash"])


def downgrade() -> None:
    op.drop_index("ix_audit_events_event_hash", table_name="audit_events")
    op.drop_index("ix_audit_events_submission_id", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_index("ix_findings_submission_id", table_name="findings")
    op.drop_table("findings")
    op.drop_index("ix_submissions_claimed_by", table_name="submissions")
    op.drop_index("ix_submissions_status", table_name="submissions")
    op.drop_index("ix_submissions_sha256", table_name="submissions")
    op.drop_index("ix_submissions_project_code", table_name="submissions")
    op.drop_table("submissions")

"""Add actor-scoped idempotency records.

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-23
"""
from __future__ import annotations

import hashlib
import json

import sqlalchemy as sa

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

FINGERPRINT_VERSION = "submission-create-v1"


def _scope_key(actor_name: str, raw_key: str) -> str:
    return hashlib.sha256(f"{actor_name}\0{raw_key}".encode("utf-8")).hexdigest()


def _fingerprint(row: sa.RowMapping) -> str:
    payload = {
        "contract": FINGERPRINT_VERSION,
        "content_type": row["content_type"],
        "filename": row["filename"],
        "output_description": row["output_description"],
        "output_type": row["output_type"],
        "project_code": row["project_code"],
        "sha256": row["sha256"],
        "size_bytes": row["size_bytes"],
    }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def upgrade() -> None:
    op.create_table(
        "idempotency_records",
        sa.Column("scope_key", sa.String(length=64), primary_key=True),
        sa.Column("submitted_by", sa.String(length=120), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column(
            "submission_id",
            sa.String(length=36),
            sa.ForeignKey("submissions.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_idempotency_records_submitted_by",
        "idempotency_records",
        ["submitted_by"],
    )

    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            """
            SELECT id, project_code, output_type, output_description, filename,
                   content_type, size_bytes, sha256, idempotency_key, submitted_by,
                   created_at
            FROM submissions
            WHERE idempotency_key IS NOT NULL
            """
        )
    ).mappings()
    for row in rows:
        raw_key = str(row["idempotency_key"]).strip()
        connection.execute(
            sa.text(
                """
                INSERT INTO idempotency_records (
                    scope_key, submitted_by, request_fingerprint, submission_id, created_at
                ) VALUES (
                    :scope_key, :submitted_by, :request_fingerprint, :submission_id, :created_at
                )
                """
            ),
            {
                "scope_key": _scope_key(str(row["submitted_by"]), raw_key),
                "submitted_by": row["submitted_by"],
                "request_fingerprint": _fingerprint(row),
                "submission_id": row["id"],
                "created_at": row["created_at"],
            },
        )


def downgrade() -> None:
    op.drop_index("ix_idempotency_records_submitted_by", table_name="idempotency_records")
    op.drop_table("idempotency_records")

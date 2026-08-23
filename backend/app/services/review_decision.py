from __future__ import annotations

from datetime import datetime

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models import Submission


def compare_and_swap_review_decision(
    db: Session,
    *,
    submission_id: str,
    expected_version: int,
    reviewer: str,
    decision: str,
    rationale: str,
    require_claim: bool,
    claim_cutoff: datetime,
) -> bool:
    """Atomically complete a review only from the expected submission version."""

    conditions = [
        Submission.id == submission_id,
        Submission.status == "AWAITING_REVIEW",
        Submission.row_version == expected_version,
    ]
    if require_claim:
        conditions.extend(
            [
                Submission.claimed_by == reviewer,
                Submission.claimed_at.is_not(None),
                Submission.claimed_at > claim_cutoff,
            ]
        )

    statement = (
        update(Submission)
        .where(*conditions)
        .values(
            final_decision=decision,
            status="COMPLETED",
            reviewer=reviewer,
            review_rationale=rationale,
            claimed_by=None,
            claimed_at=None,
            row_version=expected_version + 1,
        )
        .execution_options(synchronize_session=False)
    )
    result = db.execute(statement)
    return getattr(result, "rowcount", 0) == 1

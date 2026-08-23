from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, asc, desc, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.core.auth import Actor, get_actor
from app.core.cursor_pagination import (
    SubmissionCursor,
    cursor_contract,
    decode_submission_cursor,
    encode_submission_cursor,
)
from app.db import get_db
from app.models import Submission
from app.schemas import SubmissionCursorPage, SubmissionSummary

router = APIRouter()


@router.get(
    "/api/v1/submissions/cursor",
    response_model=SubmissionCursorPage,
    tags=["submissions"],
)
def list_submissions_cursor(
    limit: int = Query(default=25, ge=1, le=100),
    cursor: str | None = Query(default=None, min_length=16, max_length=2048),
    decision: Literal["ALLOW", "REVIEW", "BLOCK"] | None = Query(default=None),
    workflow_status: Literal["AWAITING_REVIEW", "COMPLETED", "QUARANTINED", "SCANNING"]
    | None = Query(default=None),
    project_code: str | None = Query(default=None, max_length=80),
    search: str | None = Query(default=None, max_length=120),
    sort: Literal["newest", "oldest", "risk_desc"] = Query(default="newest"),
    actor: Actor = Depends(get_actor),
    db: Session = Depends(get_db),
) -> SubmissionCursorPage:
    """List submissions using a signed keyset cursor.

    The existing page/offset endpoint remains available for the browser demo. This
    endpoint avoids deep OFFSET scans and binds a cursor to the authenticated actor,
    filters and sort contract that created it.
    """

    conditions: list[ColumnElement[bool]] = []
    if actor.role == "researcher":
        conditions.append(Submission.submitted_by == actor.name)
    if decision is not None:
        conditions.append(Submission.automated_decision == decision)
    if workflow_status is not None:
        conditions.append(Submission.status == workflow_status)
    if project_code and project_code.strip():
        conditions.append(Submission.project_code == project_code.strip())
    if search and search.strip():
        term = f"%{search.strip()}%"
        conditions.append(
            or_(
                Submission.filename.ilike(term),
                Submission.submitted_by.ilike(term),
                Submission.project_code.ilike(term),
                Submission.output_description.ilike(term),
            )
        )

    contract = cursor_contract(
        actor_role=actor.role,
        actor_name=actor.name,
        decision=decision,
        workflow_status=workflow_status,
        project_code=project_code,
        search=search,
        sort=sort,
    )
    anchor: SubmissionCursor | None = None
    if cursor is not None:
        try:
            anchor = decode_submission_cursor(
                cursor,
                expected_contract=contract,
                expected_sort=sort,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    statement = select(Submission)
    if conditions:
        statement = statement.where(*conditions)

    if sort == "oldest":
        if anchor is not None:
            statement = statement.where(
                or_(
                    Submission.created_at > anchor.created_at,
                    and_(
                        Submission.created_at == anchor.created_at,
                        Submission.id > anchor.submission_id,
                    ),
                )
            )
        statement = statement.order_by(asc(Submission.created_at), asc(Submission.id))
    elif sort == "risk_desc":
        if anchor is not None:
            if anchor.risk_score is None:
                raise HTTPException(status_code=400, detail="Invalid or incompatible submission cursor.")
            statement = statement.where(
                or_(
                    Submission.risk_score < anchor.risk_score,
                    and_(
                        Submission.risk_score == anchor.risk_score,
                        Submission.created_at > anchor.created_at,
                    ),
                    and_(
                        Submission.risk_score == anchor.risk_score,
                        Submission.created_at == anchor.created_at,
                        Submission.id > anchor.submission_id,
                    ),
                )
            )
        statement = statement.order_by(
            desc(Submission.risk_score),
            asc(Submission.created_at),
            asc(Submission.id),
        )
    else:
        if anchor is not None:
            statement = statement.where(
                or_(
                    Submission.created_at < anchor.created_at,
                    and_(
                        Submission.created_at == anchor.created_at,
                        Submission.id < anchor.submission_id,
                    ),
                )
            )
        statement = statement.order_by(desc(Submission.created_at), desc(Submission.id))

    rows = list(db.scalars(statement.limit(limit + 1)))
    has_more = len(rows) > limit
    items = rows[:limit]
    next_cursor = None
    if has_more and items:
        last = items[-1]
        next_cursor = encode_submission_cursor(
            SubmissionCursor(
                sort=sort,
                contract=contract,
                created_at=last.created_at,
                submission_id=last.id,
                risk_score=last.risk_score if sort == "risk_desc" else None,
            )
        )

    return SubmissionCursorPage(
        items=[SubmissionSummary.model_validate(item) for item in items],
        limit=limit,
        has_more=has_more,
        next_cursor=next_cursor,
    )

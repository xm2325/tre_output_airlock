from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from fastapi import HTTPException

PreconditionSource = Literal["if-match", "expected-version"]


@dataclass(frozen=True)
class ReviewPrecondition:
    expected_version: int
    source: PreconditionSource


def submission_etag(submission_id: str, row_version: int) -> str:
    """Return the strong entity tag for one submission representation."""
    return f'"airlock-submission:{submission_id}:v{row_version}"'


def resolve_review_precondition(
    *,
    if_match: str | None,
    expected_version: int | None,
    submission_id: str,
    current_version: int,
) -> ReviewPrecondition:
    """Resolve the review concurrency contract without weakening legacy clients.

    A strong ``If-Match`` tag is the preferred HTTP contract. The historical JSON
    ``expected_version`` field remains supported. If both are supplied they must
    describe the same current representation.
    """

    if if_match is not None:
        candidates = [candidate.strip() for candidate in if_match.split(",") if candidate.strip()]
        if not candidates:
            raise HTTPException(status_code=400, detail="If-Match must contain an entity tag.")
        if "*" in candidates:
            raise HTTPException(
                status_code=400,
                detail="If-Match wildcard is not supported; send the submission ETag.",
            )
        if any(candidate.startswith("W/") for candidate in candidates):
            raise HTTPException(
                status_code=400,
                detail="Weak ETags are not supported for review decisions.",
            )

        current_etag = submission_etag(submission_id, current_version)
        if current_etag not in candidates:
            raise HTTPException(
                status_code=412,
                detail="If-Match precondition failed. Refresh the submission and try again.",
            )
        if expected_version is not None and expected_version != current_version:
            raise HTTPException(
                status_code=400,
                detail="If-Match and expected_version describe different submission versions.",
            )
        return ReviewPrecondition(expected_version=current_version, source="if-match")

    if expected_version is None:
        raise HTTPException(
            status_code=428,
            detail="Send If-Match with the submission ETag or provide expected_version.",
        )
    if expected_version != current_version:
        raise HTTPException(
            status_code=409,
            detail="The review item changed. Refresh and try again.",
        )
    return ReviewPrecondition(
        expected_version=expected_version,
        source="expected-version",
    )


def stale_write_error(source: PreconditionSource) -> HTTPException:
    if source == "if-match":
        return HTTPException(
            status_code=412,
            detail="If-Match precondition failed. Refresh the submission and try again.",
        )
    return HTTPException(
        status_code=409,
        detail="The review item changed. Refresh and try again.",
    )

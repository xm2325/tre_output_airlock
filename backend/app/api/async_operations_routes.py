from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.core.async_scan import load_async_scan_settings
from app.db import get_db
from app.services.async_operations import (
    collect_async_operations_snapshot,
    prometheus_async_operations,
)

router = APIRouter()


@router.get("/metrics/async", response_class=PlainTextResponse, tags=["operations"])
def async_operations_metrics(db: Session = Depends(get_db)) -> str:
    """Expose durable async backlog/lease/retry state without granting the API SQS access."""

    snapshot = collect_async_operations_snapshot(db, load_async_scan_settings())
    return prometheus_async_operations(snapshot)

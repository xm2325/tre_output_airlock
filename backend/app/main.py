from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.core.config import settings
from app.core.logging import configure_logging
from app.core.policy import API_VERSION
from app.core.telemetry import telemetry
from app.db import initialise_database

configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):  # type: ignore[no-untyped-def]
    settings.quarantine_dir.mkdir(parents=True, exist_ok=True)
    if settings.auto_create_schema:
        initialise_database()
    yield


app = FastAPI(
    title="TRE Output Airlock API",
    description=(
        "Synthetic full-stack demonstration for checking research outputs before release "
        "from a trusted research environment. It combines versioned rules, human review, "
        "role checks, tamper-evident audit events and signed decision reports."
    ),
    version=API_VERSION,
    lifespan=lifespan,
    openapi_tags=[
        {"name": "operations", "description": "Health, readiness, metrics and telemetry."},
        {"name": "identity", "description": "Header-based demo identity and role context."},
        {
            "name": "policy",
            "description": "Versioned policy, rule catalogue and policy simulation.",
        },
        {
            "name": "submissions",
            "description": "Upload, search, recheck, retention and signed reports.",
        },
        {"name": "review", "description": "Claim-based, risk-prioritised human review workflow."},
        {"name": "audit", "description": "Tamper-evident audit-chain verification."},
    ],
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_context(request: Request, call_next):  # type: ignore[no-untyped-def]
    request_id = request.headers.get("X-Request-ID", str(uuid4()))
    request.state.request_id = request_id
    started = perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        duration_ms = round((perf_counter() - started) * 1000, 2)
        telemetry.record(request.method, request.url.path, 500, duration_ms)
        logger.exception(
            "Unhandled request error",
            extra={
                "request_id": request_id,
                "path": request.url.path,
                "method": request.method,
                "status_code": 500,
            },
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error.", "request_id": request_id},
            headers={"X-Request-ID": request_id},
        )

    duration_ms = round((perf_counter() - started) * 1000, 2)
    telemetry.record(request.method, request.url.path, response.status_code, duration_ms)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    logger.info(
        "Request completed",
        extra={
            "request_id": request_id,
            "path": request.url.path,
            "method": request.method,
            "status_code": response.status_code,
            "duration_ms": duration_ms,
        },
    )
    return response


app.include_router(router)

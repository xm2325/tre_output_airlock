from fastapi import APIRouter

from app.api.agentic_routes import router as agentic_router
from app.api.async_operations_routes import router as async_operations_router
from app.api.operations_routes import router as operations_router
from app.api.policy_routes import router as policy_router
from app.api.review_routes import router as review_router
from app.api.submission_cursor_routes import router as submission_cursor_router
from app.api.submission_routes import router as submission_router

router = APIRouter()
router.include_router(operations_router)
router.include_router(async_operations_router)
router.include_router(policy_router)
# Register the fixed /submissions/cursor path before /submissions/{submission_id}.
router.include_router(submission_cursor_router)
router.include_router(submission_router)
router.include_router(review_router)
router.include_router(agentic_router)

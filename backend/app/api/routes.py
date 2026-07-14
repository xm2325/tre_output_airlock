from fastapi import APIRouter

from app.api.operations_routes import router as operations_router
from app.api.policy_routes import router as policy_router
from app.api.review_routes import router as review_router
from app.api.submission_routes import router as submission_router

router = APIRouter()
router.include_router(operations_router)
router.include_router(policy_router)
router.include_router(submission_router)
router.include_router(review_router)

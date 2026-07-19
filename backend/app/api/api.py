from fastapi import APIRouter

from app.api.patents import router as patents_router
from app.api.meta import router as meta_router
from app.api.imports import router as imports_router
from app.api.ai import router as ai_router

api_router = APIRouter()
api_router.include_router(patents_router)
api_router.include_router(meta_router)
api_router.include_router(imports_router)
api_router.include_router(ai_router)

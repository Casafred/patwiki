from fastapi import APIRouter

from app.api.patents import router as patents_router
from app.api.meta import router as meta_router
from app.api.imports import router as imports_router
from app.api.ai import router as ai_router
from app.api.settings import router as settings_router
from app.api.fields import router as fields_router
from app.api.databases import router as databases_router
from app.api.analytics import router as analytics_router
from app.api.sharing import router as sharing_router

api_router = APIRouter()
api_router.include_router(databases_router)
api_router.include_router(patents_router)
api_router.include_router(meta_router)
api_router.include_router(imports_router)
api_router.include_router(ai_router)
api_router.include_router(settings_router)
api_router.include_router(fields_router)
api_router.include_router(analytics_router)
api_router.include_router(sharing_router)

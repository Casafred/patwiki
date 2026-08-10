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
from app.api.views import router as views_router  # P0-13 新增
from app.api.links import router as links_router  # M3：通用关联字段
from app.api.public_shares import router as public_shares_router  # P2-4：单专利 Wiki 分享
from app.api.search import router as search_router  # P2-6：搜索自动补全
from app.api.formula import router as formula_router  # M1：公式字段
from app.api.export import router as export_router  # M1：数据导出
from app.api.form import router as form_router  # M4：公开表单

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
api_router.include_router(views_router)
api_router.include_router(links_router)
api_router.include_router(public_shares_router)
api_router.include_router(search_router)
api_router.include_router(formula_router)
api_router.include_router(export_router)
api_router.include_router(form_router)

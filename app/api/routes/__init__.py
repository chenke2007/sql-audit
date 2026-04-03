"""
API 路由
"""
from app.api.routes.collect import router as collect_router
from app.api.routes.analyze import router as analyze_router
from app.api.routes.db_sources import router as db_sources_router

__all__ = ["collect_router", "analyze_router", "db_sources_router"]

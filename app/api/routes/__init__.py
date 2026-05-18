"""
API 路由
"""
from app.api.routes.collect import router as collect_router
from app.api.routes.analyze import router as analyze_router
from app.api.routes.db_sources import router as db_sources_router
from app.api.routes.auth import router as auth_router
from app.api.routes.users import router as users_router
from app.api.routes.roles import router as roles_router
from app.api.routes.analysis_history import router as analysis_history_router
from app.api.routes.datasource_permissions import router as datasource_permissions_router

__all__ = [
    "collect_router", "analyze_router", "db_sources_router",
    "auth_router", "users_router", "roles_router", "analysis_history_router",
    "datasource_permissions_router"
]

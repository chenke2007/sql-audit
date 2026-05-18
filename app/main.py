"""
SQL Audit System - FastAPI Application

SQL智能审核系统主入口。
"""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.config import settings
from app.oracle.client import oracle_client, OracleConnectionError
from app.api.routes import (
    collect_router, analyze_router, db_sources_router,
    auth_router, users_router, roles_router, analysis_history_router,
    datasource_permissions_router
)
from app.core.oracle_client_init import init_thick_mode

# 配置日志
logging.basicConfig(
    level=getattr(logging, settings.app.log_level.upper()),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    应用生命周期管理

    不再强制初始化默认Oracle连接。
    所有数据库连接通过数据源管理动态获取。
    """
    # 启动
    logger.info(f"启动 {settings.app.name} ...")
    # 优先尝试启用 Oracle thick 模式（支持 Oracle 11g）
    thick_ok = init_thick_mode()
    if not thick_ok:
        logger.info("未启用 thick 模式，将使用 thin 模式（要求 Oracle 12.1+）")

    # 不再强制初始化默认Oracle连接
    # 如果 .env 中配置了默认连接，仍然尝试初始化（向后兼容）
    if settings.oracle.host and settings.oracle.username:
        try:
            oracle_client.initialize()
            logger.info("Oracle默认连接初始化成功")
        except OracleConnectionError as e:
            logger.warning(f"Oracle默认连接初始化失败: {e}，应用将以无默认连接模式运行")
    else:
        logger.info("未配置默认Oracle连接，完全依赖数据源管理模块")

    yield

    # 关闭
    logger.info("关闭应用...")
    oracle_client.close()


# 创建FastAPI应用
app = FastAPI(
    title="SQL Audit System",
    description="SQL智能审核与优化系统",
    version="1.2.1",
    lifespan=lifespan
)

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应限制为具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册API路由
app.include_router(auth_router)
app.include_router(collect_router)
app.include_router(analyze_router)
app.include_router(db_sources_router)
app.include_router(users_router)
app.include_router(roles_router)
app.include_router(analysis_history_router)
app.include_router(datasource_permissions_router)


# 静态文件服务
frontend_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
if os.path.exists(frontend_path):
    app.mount("/static", StaticFiles(directory=os.path.join(frontend_path, "static")), name="static")


@app.get("/")
async def serve_index():
    """服务前端首页"""
    index_path = os.path.join(frontend_path, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {
        "name": settings.app.name,
        "version": "1.0.0",
        "status": "running"
    }


@app.get("/api")
async def api_root():
    """API 根路径"""
    return {
        "name": settings.app.name,
        "version": "1.0.0",
        "status": "running",
        "docs_url": "/docs"
    }


@app.get("/health")
async def health_check():
    """详细健康检查"""
    return {
        "status": "healthy",
        "config_loaded": True
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.app.debug
    )

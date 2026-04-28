"""
数据库源管理 API

提供数据库源的 CRUD 和连接测试功能
"""

import logging
from typing import List, Optional
from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException, Query

from app.core.database import DBSourceManager, DBSource
from app.core.dynamic_db_client import DynamicOracleClient
from app.oracle.metadata import MetadataCollector

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/db-sources", tags=["数据库源管理"])


# ========== 请求/响应模型 ==========

class DBSourceCreate(BaseModel):
    """创建数据源请求"""
    name: str = Field(..., min_length=1, description="数据源名称")
    db_type: str = Field(..., description="数据库类型: oracle")
    host: str = Field(..., min_length=1, description="主机地址")
    port: int = Field(..., ge=1, le=65535, description="端口")
    service_name: Optional[str] = Field(None, description="Service Name (Oracle)")
    sid: Optional[str] = Field(None, description="SID (Oracle)")
    username: str = Field(..., min_length=1, description="用户名")
    password: str = Field(..., min_length=1, description="密码")
    description: Optional[str] = Field(None, description="描述")


class DBSourceUpdate(BaseModel):
    """更新数据源请求"""
    name: Optional[str] = Field(None, min_length=1, description="数据源名称")
    host: Optional[str] = Field(None, min_length=1, description="主机地址")
    port: Optional[int] = Field(None, ge=1, le=65535, description="端口")
    service_name: Optional[str] = Field(None, description="Service Name (Oracle)")
    sid: Optional[str] = Field(None, description="SID (Oracle)")
    username: Optional[str] = Field(None, min_length=1, description="用户名")
    password: Optional[str] = Field(None, description="密码（不传则不修改）")
    description: Optional[str] = Field(None, description="描述")
    is_default: Optional[bool] = Field(None, description="设为默认数据源")


class DBSourceResponse(BaseModel):
    """数据源响应"""
    id: str
    name: str
    db_type: str
    host: str
    port: int
    service_name: Optional[str]
    sid: Optional[str]
    username: str
    description: str
    is_default: bool
    created_at: Optional[str]
    updated_at: Optional[str]


class DBSourceListResponse(BaseModel):
    """数据源列表响应"""
    items: List[DBSourceResponse]
    total: int


class TestConnectionResponse(BaseModel):
    """连接测试结果响应"""
    success: bool
    message: str
    version: Optional[str] = None


class SchemaListResponse(BaseModel):
    """Schema 列表响应"""
    schemas: List[str]
    total: int


class DBSourceDetailResponse(DBSourceResponse):
    """数据源详情响应（含密码，仅内部使用）"""
    password: str


class TestConnectionRequest(BaseModel):
    """测试连接请求（不保存数据源）"""
    db_type: str = Field(..., description="数据库类型")
    host: str = Field(..., min_length=1, description="主机地址")
    port: int = Field(..., ge=1, le=65535, description="端口")
    service_name: Optional[str] = Field(None, description="Service Name")
    sid: Optional[str] = Field(None, description="SID")
    username: str = Field(..., min_length=1, description="用户名")
    password: str = Field(..., min_length=1, description="密码")


# ========== API 路由 ==========

@router.get("", response_model=DBSourceListResponse)
async def list_db_sources(
    db_type: Optional[str] = Query(None, description="筛选数据库类型"),
    host: Optional[str] = Query(None, description="筛选 IP 地址（模糊匹配）"),
    name: Optional[str] = Query(None, description="筛选名称（模糊匹配）")
):
    """
    列出数据库源

    支持按类型、IP、名称筛选
    """
    sources = DBSourceManager.list_all(
        db_type=db_type,
        host=host,
        name=name
    )

    return DBSourceListResponse(
        items=[DBSourceResponse(**s.to_dict()) for s in sources],
        total=len(sources)
    )


@router.get("/default", response_model=Optional[DBSourceResponse])
async def get_default_db_source():
    """
    获取默认数据源
    """
    source = DBSourceManager.get_default()
    if not source:
        return None
    return DBSourceResponse(**source.to_dict())


@router.get("/{source_id}", response_model=DBSourceResponse)
async def get_db_source(source_id: str):
    """
    获取数据源详情
    """
    source = DBSourceManager.get_by_id(source_id)
    if not source:
        raise HTTPException(status_code=404, detail="数据源不存在")
    return DBSourceResponse(**source.to_dict())


@router.post("", response_model=DBSourceResponse)
async def create_db_source(source_data: DBSourceCreate):
    """
    创建新数据源

    - 首次创建的数据源自动设为默认
    - 名称必须唯一
    """
    # 检查名称唯一性
    existing = DBSourceManager.get_by_name(source_data.name)
    if existing:
        raise HTTPException(status_code=400, detail=f"数据源名称 '{source_data.name}' 已存在")

    try:
        source = DBSourceManager.create(
            name=source_data.name,
            db_type=source_data.db_type,
            host=source_data.host,
            port=source_data.port,
            username=source_data.username,
            password=source_data.password,
            service_name=source_data.service_name,
            sid=source_data.sid,
            description=source_data.description
        )
        return DBSourceResponse(**source.to_dict())
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建数据源失败: {str(e)}")


@router.put("/{source_id}", response_model=DBSourceResponse)
async def update_db_source(source_id: str, source_data: DBSourceUpdate):
    """
    更新数据源

    - 不传 password 则不修改密码
    - 可以设置/取消默认数据源
    """
    source = DBSourceManager.get_by_id(source_id)
    if not source:
        raise HTTPException(status_code=404, detail="数据源不存在")

    # 检查名称唯一性（如果修改了名称）
    if source_data.name and source_data.name != source.name:
        existing = DBSourceManager.get_by_name(source_data.name)
        if existing:
            raise HTTPException(status_code=400, detail=f"数据源名称 '{source_data.name}' 已存在")

    try:
        updated = DBSourceManager.update(
            source_id=source_id,
            name=source_data.name,
            host=source_data.host,
            port=source_data.port,
            username=source_data.username,
            password=source_data.password,
            service_name=source_data.service_name,
            sid=source_data.sid,
            description=source_data.description,
            is_default=source_data.is_default
        )
        return DBSourceResponse(**updated.to_dict())
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"更新数据源失败: {str(e)}")


@router.delete("/{source_id}")
async def delete_db_source(source_id: str):
    """
    删除数据源
    """
    source = DBSourceManager.get_by_id(source_id)
    if not source:
        raise HTTPException(status_code=404, detail="数据源不存在")

    deleted = DBSourceManager.delete(source_id)
    if deleted:
        return {"success": True, "message": "数据源已删除"}
    else:
        raise HTTPException(status_code=500, detail="删除数据源失败")


@router.post("/{source_id}/test", response_model=TestConnectionResponse)
async def test_db_source_connection(source_id: str):
    """
    测试数据源连接

    返回连接是否成功，以及数据库版本信息
    """
    source = DBSourceManager.get_by_id(source_id)
    if not source:
        raise HTTPException(status_code=404, detail="数据源不存在")

    success, message = DBSourceManager.test_connection(source)

    return TestConnectionResponse(
        success=success,
        message=message if not success else "连接成功",
        version=message if success else None
    )


@router.post("/test-connection", response_model=TestConnectionResponse)
async def test_connection_without_save(data: TestConnectionRequest):
    """
    测试数据库连接（不保存数据源）

    用于数据源创建/编辑时的连接测试。
    """
    from app.core.database import DBSource

    source = DBSource(
        id="test",
        name="test",
        db_type=data.db_type,
        host=data.host,
        port=data.port,
        username=data.username,
        password="",  # 占位，通过 setter 设置以触发加密
        service_name=data.service_name,
        sid=data.sid
    )
    source.password = data.password

    success, message = DBSourceManager.test_connection(source)

    return TestConnectionResponse(
        success=success,
        message=message if not success else "连接成功",
        version=message if success else None
    )


@router.get("/{source_id}/schemas", response_model=SchemaListResponse)
async def get_db_source_schemas(source_id: str):
    """
    获取数据源的 Schema 列表

    连接目标数据库，获取当前用户可访问的所有 schema（owner）列表。
    """
    source = DBSourceManager.get_by_id(source_id)
    if not source:
        raise HTTPException(status_code=404, detail="数据源不存在")

    client = None
    try:
        client = DynamicOracleClient()
        client.connect_to_source(source_id)

        try:
            collector = MetadataCollector(client)
            schemas = collector.get_schemas()

            return SchemaListResponse(
                schemas=schemas,
                total=len(schemas)
            )
        finally:
            client.close()

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"获取 schema 列表失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取 schema 列表失败: {e}")

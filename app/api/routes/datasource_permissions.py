"""
数据源权限管理 API 路由

提供数据源与角色的绑定关系管理（管理员权限）。
"""

import logging
from typing import List

from fastapi import APIRouter, HTTPException, status, Depends

from app.core.database import get_metadata_db
from app.core.rbac import get_current_user, require_permission
from app.models.user_models import DatasourcePermissionCreate, DatasourcePermissionInfo

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/datasource-permissions", tags=["数据源权限管理"])


@router.get("", response_model=List[DatasourcePermissionInfo])
async def list_datasource_permissions(
    current_user: dict = Depends(require_permission("datasource:assign"))
):
    """获取所有数据源权限分配（管理员）"""
    with get_metadata_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT dp.role_id, r.name as role_name, dp.db_source_id, ds.name as db_source_name
            FROM datasource_permissions dp
            JOIN roles r ON dp.role_id = r.id
            LEFT JOIN db_sources ds ON dp.db_source_id = ds.id
            ORDER BY r.name, ds.name
        """)
        results = []
        for row in cursor.fetchall():
            results.append(DatasourcePermissionInfo(
                role_id=row["role_id"],
                role_name=row["role_name"],
                db_source_id=row["db_source_id"],
                db_source_name=row["db_source_name"]
            ))
        return results


@router.post("", status_code=status.HTTP_201_CREATED)
async def assign_datasource_permission(
    request: DatasourcePermissionCreate,
    current_user: dict = Depends(require_permission("datasource:assign"))
):
    """给角色分配数据源权限（管理员）"""
    with get_metadata_db() as conn:
        cursor = conn.cursor()

        # 验证角色存在
        cursor.execute("SELECT id FROM roles WHERE id = ?", (request.role_id,))
        if cursor.fetchone() is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="角色不存在")

        # 验证数据源存在
        cursor.execute("SELECT id FROM db_sources WHERE id = ?", (request.db_source_id,))
        if cursor.fetchone() is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="数据源不存在")

        # 检查是否已存在
        cursor.execute(
            "SELECT 1 FROM datasource_permissions WHERE role_id = ? AND db_source_id = ?",
            (request.role_id, request.db_source_id)
        )
        if cursor.fetchone():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该数据源权限已分配")

        cursor.execute(
            "INSERT INTO datasource_permissions (role_id, db_source_id) VALUES (?, ?)",
            (request.role_id, request.db_source_id)
        )
        conn.commit()

    return {"message": "数据源权限分配成功"}


@router.delete("/{role_id}/{db_source_id}")
async def revoke_datasource_permission(
    role_id: int,
    db_source_id: str,
    current_user: dict = Depends(require_permission("datasource:assign"))
):
    """撤销角色的数据源权限（管理员）"""
    with get_metadata_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM datasource_permissions WHERE role_id = ? AND db_source_id = ?",
            (role_id, db_source_id)
        )
        conn.commit()

    return {"message": "数据源权限已撤销"}


@router.get("/my-datasources")
async def get_my_datasources(
    current_user: dict = Depends(get_current_user)
):
    """获取当前用户可访问的数据源列表"""
    user_id = current_user["id"]

    with get_metadata_db() as conn:
        cursor = conn.cursor()

        # 检查是否是 admin
        cursor.execute("""
            SELECT 1 FROM user_roles ur
            JOIN roles r ON ur.role_id = r.id
            WHERE ur.user_id = ? AND r.name = 'admin'
        """, (user_id,))
        is_admin = cursor.fetchone() is not None

        if is_admin:
            # admin 返回所有数据源
            cursor.execute("SELECT id, name, db_type, host, port, description FROM db_sources ORDER BY name")
        else:
            # 非 admin 只返回授权的数据源
            cursor.execute("""
                SELECT DISTINCT ds.id, ds.name, ds.db_type, ds.host, ds.port, ds.description
                FROM db_sources ds
                JOIN datasource_permissions dp ON ds.id = dp.db_source_id
                JOIN user_roles ur ON dp.role_id = ur.role_id
                WHERE ur.user_id = ?
                ORDER BY ds.name
            """, (user_id,))

        results = []
        for row in cursor.fetchall():
            results.append(dict(row))
        return results

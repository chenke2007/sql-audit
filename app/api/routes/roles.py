"""
角色管理 API 路由

提供角色列表查询和权限配置功能（管理员权限）。
"""

import logging
from typing import List

from fastapi import APIRouter, HTTPException, status, Depends

from app.core.database import get_metadata_db
from app.core.rbac import require_permission
from app.models.user_models import RoleCreate, RoleInfo, RolePermissionUpdate, RoleUpdate

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/roles", tags=["角色管理"])


@router.get("", response_model=List[RoleInfo])
async def list_roles(
    current_user: dict = Depends(require_permission("role:manage"))
):
    """获取角色列表（管理员）"""
    with get_metadata_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, description FROM roles ORDER BY id")
        roles = []
        for row in cursor.fetchall():
            role = dict(row)

            # 查询角色的权限码
            cursor.execute("""
                SELECT p.code FROM permissions p
                JOIN role_permissions rp ON p.id = rp.permission_id
                WHERE rp.role_id = ?
            """, (role["id"],))
            role["permissions"] = [r["code"] for r in cursor.fetchall()]
            roles.append(RoleInfo(**role))
        return roles


@router.get("/{role_id}/permissions")
async def get_role_permissions(
    role_id: int,
    current_user: dict = Depends(require_permission("role:manage"))
):
    """获取角色权限详情（管理员）"""
    with get_metadata_db() as conn:
        cursor = conn.cursor()

        # 验证角色存在
        cursor.execute("SELECT id, name FROM roles WHERE id = ?", (role_id,))
        role = cursor.fetchone()
        if role is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="角色不存在")

        # 查询所有权限及该角色的授权状态
        cursor.execute("""
            SELECT p.id, p.code, p.name, p.description,
                   CASE WHEN rp.role_id IS NOT NULL THEN 1 ELSE 0 END as granted
            FROM permissions p
            LEFT JOIN role_permissions rp ON p.id = rp.permission_id AND rp.role_id = ?
            ORDER BY p.id
        """, (role_id,))

        permissions = []
        for row in cursor.fetchall():
            permissions.append({
                "id": row["id"],
                "code": row["code"],
                "name": row["name"],
                "description": row["description"],
                "granted": bool(row["granted"]),
            })

        return {
            "role_id": role_id,
            "role_name": role["name"],
            "permissions": permissions,
        }


@router.put("/{role_id}/permissions")
async def update_role_permissions(
    role_id: int,
    request: RolePermissionUpdate,
    current_user: dict = Depends(require_permission("role:manage"))
):
    """更新角色权限（管理员）"""
    with get_metadata_db() as conn:
        cursor = conn.cursor()

        # 验证角色存在
        cursor.execute("SELECT id FROM roles WHERE id = ?", (role_id,))
        if cursor.fetchone() is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="角色不存在")

        # 删除旧权限
        cursor.execute("DELETE FROM role_permissions WHERE role_id = ?", (role_id,))

        # 插入新权限
        for perm_id in request.permission_ids:
            cursor.execute(
                "INSERT INTO role_permissions (role_id, permission_id) VALUES (?, ?)",
                (role_id, perm_id)
            )

        conn.commit()

    return {"message": "角色权限已更新"}


@router.post("", response_model=RoleInfo, status_code=status.HTTP_201_CREATED)
async def create_role(
    request: RoleCreate,
    current_user: dict = Depends(require_permission("role:manage"))
):
    """创建角色（管理员）"""
    with get_metadata_db() as conn:
        cursor = conn.cursor()

        # 检查名称唯一性
        cursor.execute("SELECT id FROM roles WHERE name = ?", (request.name,))
        if cursor.fetchone() is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"角色名称 '{request.name}' 已存在")

        cursor.execute(
            "INSERT INTO roles (name, description) VALUES (?, ?)",
            (request.name, request.description)
        )
        role_id = cursor.lastrowid
        conn.commit()

        return RoleInfo(id=role_id, name=request.name, description=request.description, permissions=[])


@router.put("/{role_id}", response_model=RoleInfo)
async def update_role(
    role_id: int,
    request: RoleUpdate,
    current_user: dict = Depends(require_permission("role:manage"))
):
    """更新角色（管理员）"""
    with get_metadata_db() as conn:
        cursor = conn.cursor()

        cursor.execute("SELECT id, name, description FROM roles WHERE id = ?", (role_id,))
        role = cursor.fetchone()
        if role is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="角色不存在")

        # 检查名称唯一性
        if request.name is not None and request.name != role["name"]:
            cursor.execute("SELECT id FROM roles WHERE name = ?", (request.name,))
            if cursor.fetchone() is not None:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"角色名称 '{request.name}' 已存在")

        updates = []
        params = []
        if request.name is not None:
            updates.append("name = ?")
            params.append(request.name)
        if request.description is not None:
            updates.append("description = ?")
            params.append(request.description)

        if updates:
            params.append(role_id)
            cursor.execute(f"UPDATE roles SET {', '.join(updates)} WHERE id = ?", params)
            conn.commit()

    return _get_role_by_id(role_id)


@router.delete("/{role_id}")
async def delete_role(
    role_id: int,
    current_user: dict = Depends(require_permission("role:manage"))
):
    """删除角色（管理员）"""
    with get_metadata_db() as conn:
        cursor = conn.cursor()

        cursor.execute("SELECT id FROM roles WHERE id = ?", (role_id,))
        if cursor.fetchone() is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="角色不存在")

        cursor.execute("DELETE FROM roles WHERE id = ?", (role_id,))
        conn.commit()

    return {"message": "角色已删除"}


def _get_role_by_id(role_id: int) -> RoleInfo:
    """根据 ID 获取角色详情"""
    with get_metadata_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, description FROM roles WHERE id = ?", (role_id,))
        row = cursor.fetchone()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="角色不存在")

        cursor.execute("""
            SELECT p.code FROM permissions p
            JOIN role_permissions rp ON p.id = rp.permission_id
            WHERE rp.role_id = ?
        """, (role_id,))
        permissions = [r["code"] for r in cursor.fetchall()]

        return RoleInfo(id=row["id"], name=row["name"], description=row["description"], permissions=permissions)

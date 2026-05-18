"""
用户管理 API 路由

提供用户 CRUD、密码修改等功能（管理员权限）。
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException, status, Depends

from app.core.auth import get_password_hash, verify_password
from app.core.database import get_metadata_db
from app.core.rbac import get_current_user, require_permission
from app.models.user_models import (
    UserCreate, UserUpdate, UserInfo, ChangePasswordRequest
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/users", tags=["用户管理"])


def _get_user_by_id(user_id: int) -> Optional[dict]:
    """根据 ID 获取用户详情"""
    with get_metadata_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, username, real_name, email, is_active, created_at FROM users WHERE id = ?",
            (user_id,)
        )
        row = cursor.fetchone()
        if row is None:
            return None
        user = dict(row)
        user["is_active"] = bool(user["is_active"])

        # 查询角色
        cursor.execute("""
            SELECT r.name FROM roles r
            JOIN user_roles ur ON r.id = ur.role_id
            WHERE ur.user_id = ?
        """, (user_id,))
        user["roles"] = [r["name"] for r in cursor.fetchall()]
        return user


def _get_user_by_username(username: str) -> Optional[dict]:
    """根据用户名获取用户"""
    with get_metadata_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, username, password_hash, real_name, email, is_active FROM users WHERE username = ?",
            (username,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None


@router.get("", response_model=List[UserInfo])
async def list_users(
    current_user: dict = Depends(require_permission("user:manage"))
):
    """获取用户列表（管理员）"""
    with get_metadata_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, username, real_name, email, is_active, created_at FROM users ORDER BY id"
        )
        users = []
        for row in cursor.fetchall():
            user = dict(row)
            user["is_active"] = bool(user["is_active"])

            cursor.execute("""
                SELECT r.name FROM roles r
                JOIN user_roles ur ON r.id = ur.role_id
                WHERE ur.user_id = ?
            """, (user["id"],))
            user["roles"] = [r["name"] for r in cursor.fetchall()]
            users.append(UserInfo(**user))
        return users


@router.post("", response_model=UserInfo, status_code=status.HTTP_201_CREATED)
async def create_user(
    request: UserCreate,
    current_user: dict = Depends(require_permission("user:manage"))
):
    """创建用户（管理员）"""
    # 检查用户名是否已存在
    if _get_user_by_username(request.username):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="用户名已存在")

    with get_metadata_db() as conn:
        cursor = conn.cursor()

        # 创建用户
        password_hash = get_password_hash(request.password)
        cursor.execute(
            """INSERT INTO users (username, password_hash, real_name, email, is_active)
               VALUES (?, ?, ?, ?, ?)""",
            (request.username, password_hash, request.real_name, request.email, 1 if request.is_active else 0)
        )
        user_id = cursor.lastrowid

        # 绑定角色
        for role_id in request.role_ids:
            cursor.execute(
                "INSERT INTO user_roles (user_id, role_id) VALUES (?, ?)",
                (user_id, role_id)
            )

        conn.commit()

    return _get_user_by_id(user_id)


@router.put("/{user_id}", response_model=UserInfo)
async def update_user(
    user_id: int,
    request: UserUpdate,
    current_user: dict = Depends(require_permission("user:manage"))
):
    """更新用户（管理员）"""
    user = _get_user_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")

    with get_metadata_db() as conn:
        cursor = conn.cursor()

        # 更新基本信息
        updates = []
        params = []
        if request.real_name is not None:
            updates.append("real_name = ?")
            params.append(request.real_name)
        if request.email is not None:
            updates.append("email = ?")
            params.append(request.email)
        if request.is_active is not None:
            updates.append("is_active = ?")
            params.append(1 if request.is_active else 0)

        if updates:
            params.append(user_id)
            cursor.execute(
                f"UPDATE users SET {', '.join(updates)} WHERE id = ?",
                params
            )

        # 更新密码（单独处理，避免与基本信息混在同一 UPDATE 中导致顺序问题）
        if request.password is not None and request.password.strip():
            new_hash = get_password_hash(request.password)
            cursor.execute(
                "UPDATE users SET password_hash = ? WHERE id = ?",
                (new_hash, user_id)
            )

        # 更新角色绑定
        if request.role_ids is not None:
            cursor.execute("DELETE FROM user_roles WHERE user_id = ?", (user_id,))
            for role_id in request.role_ids:
                cursor.execute(
                    "INSERT INTO user_roles (user_id, role_id) VALUES (?, ?)",
                    (user_id, role_id)
                )

        conn.commit()

    return _get_user_by_id(user_id)


@router.delete("/{user_id}")
async def delete_user(
    user_id: int,
    current_user: dict = Depends(require_permission("user:manage"))
):
    """禁用用户（管理员）- 物理删除改为禁用"""
    user = _get_user_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")

    # 不能禁用自己
    if user_id == current_user["id"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不能禁用当前登录用户")

    with get_metadata_db() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET is_active = 0 WHERE id = ?", (user_id,))
        conn.commit()

    return {"message": "用户已禁用"}


@router.post("/{user_id}/change-password")
async def change_password(
    user_id: int,
    request: ChangePasswordRequest,
    current_user: dict = Depends(get_current_user)
):
    """修改密码（用户自己或管理员）"""
    # 只能修改自己的密码，除非有 user:manage 权限
    if user_id != current_user["id"] and "user:manage" not in current_user.get("permissions", []):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="只能修改自己的密码")

    with get_metadata_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT password_hash FROM users WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")

        # 验证旧密码（管理员修改他人密码时不需要验证旧密码）
        if user_id == current_user["id"]:
            if not verify_password(request.old_password, row["password_hash"]):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="旧密码错误")

        # 更新密码
        new_hash = get_password_hash(request.new_password)
        cursor.execute("UPDATE users SET password_hash = ? WHERE id = ?", (new_hash, user_id))
        conn.commit()

    return {"message": "密码修改成功"}

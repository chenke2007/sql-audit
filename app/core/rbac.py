"""
RBAC 权限控制模块

提供用户角色查询、权限检查和依赖注入功能。
"""

import logging
from typing import Optional, List, Dict, Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.core.auth import decode_token
from app.core.database import get_metadata_db

logger = logging.getLogger(__name__)
security = HTTPBearer(auto_error=False)


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Dict[str, Any]:
    """获取当前登录用户（FastAPI Depends 用）"""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供认证凭证",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_token(credentials.credentials)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的认证凭证",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的 Token 类型",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的认证凭证",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 查询用户信息和权限
    user = get_user_with_permissions(int(user_id))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账号已被禁用",
        )

    return user


def get_user_with_permissions(user_id: int) -> Optional[Dict[str, Any]]:
    """获取用户及其权限信息"""
    with get_metadata_db() as conn:
        cursor = conn.cursor()

        # 查询用户基本信息
        cursor.execute(
            "SELECT id, username, real_name, email, is_active FROM users WHERE id = ?",
            (user_id,)
        )
        row = cursor.fetchone()
        if row is None:
            return None

        user = dict(row)
        user["is_active"] = bool(user["is_active"])

        # 查询用户角色
        cursor.execute("""
            SELECT r.id, r.name, r.description
            FROM roles r
            JOIN user_roles ur ON r.id = ur.role_id
            WHERE ur.user_id = ?
        """, (user_id,))
        roles = [dict(r) for r in cursor.fetchall()]
        user["roles"] = roles
        user["role_names"] = [r["name"] for r in roles]

        # 查询用户权限码
        cursor.execute("""
            SELECT DISTINCT p.code
            FROM permissions p
            JOIN role_permissions rp ON p.id = rp.permission_id
            JOIN user_roles ur ON rp.role_id = ur.role_id
            WHERE ur.user_id = ?
        """, (user_id,))
        permissions = [r["code"] for r in cursor.fetchall()]
        user["permissions"] = permissions

        return user


def require_permission(permission_code: str):
    """检查用户是否拥有指定权限（FastAPI Depends 用）"""
    def checker(current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
        if permission_code not in current_user.get("permissions", []):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"没有权限执行此操作：{permission_code}",
            )
        return current_user
    return checker


def require_any_permission(*permission_codes: str):
    """检查用户是否拥有任一指定权限"""
    def checker(current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
        user_perms = set(current_user.get("permissions", []))
        if not user_perms.intersection(set(permission_codes)):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="没有权限执行此操作",
            )
        return current_user
    return checker


def get_user_datasource_permissions(user_id: int) -> List[str]:
    """获取用户可访问的数据源 ID 列表"""
    with get_metadata_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT DISTINCT dp.db_source_id
            FROM datasource_permissions dp
            JOIN user_roles ur ON dp.role_id = ur.role_id
            WHERE ur.user_id = ?
        """, (user_id,))
        return [r["db_source_id"] for r in cursor.fetchall()]


def has_datasource_permission(user_id: int, db_source_id: str) -> bool:
    """检查用户是否有指定数据源的访问权限"""
    with get_metadata_db() as conn:
        cursor = conn.cursor()
        # 先检查是否是 admin（admin 拥有所有权限）
        cursor.execute("""
            SELECT 1 FROM user_roles ur
            JOIN roles r ON ur.role_id = r.id
            WHERE ur.user_id = ? AND r.name = 'admin'
        """, (user_id,))
        if cursor.fetchone():
            return True

        # 检查数据源绑定权限
        cursor.execute("""
            SELECT 1 FROM datasource_permissions dp
            JOIN user_roles ur ON dp.role_id = ur.role_id
            WHERE ur.user_id = ? AND dp.db_source_id = ?
        """, (user_id, db_source_id))
        return cursor.fetchone() is not None

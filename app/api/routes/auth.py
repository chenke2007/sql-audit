"""
认证 API 路由

提供登录、刷新 Token、获取当前用户信息等功能。
"""

import logging
from datetime import timedelta

from fastapi import APIRouter, HTTPException, status, Depends

from app.core.auth import (
    verify_password, get_password_hash, create_access_token,
    create_refresh_token, decode_token, ACCESS_TOKEN_EXPIRE_MINUTES
)
from app.core.database import get_metadata_db
from app.core.rbac import get_current_user, get_user_with_permissions
from app.models.user_models import LoginRequest, RefreshTokenRequest, LoginResponse, UserDetail

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["认证"])


def _init_default_data():
    """初始化默认角色、权限和管理员账号"""
    with get_metadata_db() as conn:
        cursor = conn.cursor()

        # 检查是否已初始化
        cursor.execute("SELECT COUNT(*) as count FROM roles")
        if cursor.fetchone()["count"] > 0:
            return

        # 插入预置角色
        cursor.executemany(
            "INSERT INTO roles (name, description) VALUES (?, ?)",
            [
                ("admin", "系统管理员，拥有所有权限"),
                ("dba", "数据库管理员，可管理数据源和执行分析"),
                ("developer", "开发人员，可执行分析"),
            ]
        )

        # 插入预置权限
        permissions = [
            ("user:manage", "管理用户", "创建、编辑、禁用用户"),
            ("role:manage", "管理角色", "配置角色权限"),
            ("datasource:manage", "管理数据源", "增删改数据源配置"),
            ("datasource:assign", "数据源授权", "给角色分配数据源权限"),
            ("datasource:use", "使用数据源", "使用数据源执行分析"),
            ("analysis:execute", "执行分析", "执行 SQL 分析"),
            ("analysis:history:all", "查看全部历史", "查看所有人的分析历史"),
            ("analysis:history:own", "查看自己的历史", "查看自己的分析历史"),
            ("system:audit", "系统审计", "查看系统操作日志"),
        ]
        cursor.executemany(
            "INSERT INTO permissions (code, name, description) VALUES (?, ?, ?)",
            permissions
        )

        # 绑定角色权限
        # admin 拥有所有权限
        cursor.execute("SELECT id FROM roles WHERE name = 'admin'")
        admin_role_id = cursor.fetchone()["id"]
        cursor.execute("SELECT id FROM permissions")
        perm_ids = [(admin_role_id, r["id"]) for r in cursor.fetchall()]
        cursor.executemany(
            "INSERT INTO role_permissions (role_id, permission_id) VALUES (?, ?)",
            perm_ids
        )

        # dba 权限
        cursor.execute("SELECT id FROM roles WHERE name = 'dba'")
        dba_role_id = cursor.fetchone()["id"]
        dba_codes = [
            "datasource:use", "datasource:manage",
            "analysis:execute", "analysis:history:own"
        ]
        for code in dba_codes:
            cursor.execute("SELECT id FROM permissions WHERE code = ?", (code,))
            perm_id = cursor.fetchone()["id"]
            cursor.execute(
                "INSERT INTO role_permissions (role_id, permission_id) VALUES (?, ?)",
                (dba_role_id, perm_id)
            )

        # developer 权限
        cursor.execute("SELECT id FROM roles WHERE name = 'developer'")
        dev_role_id = cursor.fetchone()["id"]
        dev_codes = [
            "datasource:use", "analysis:execute", "analysis:history:own"
        ]
        for code in dev_codes:
            cursor.execute("SELECT id FROM permissions WHERE code = ?", (code,))
            perm_id = cursor.fetchone()["id"]
            cursor.execute(
                "INSERT INTO role_permissions (role_id, permission_id) VALUES (?, ?)",
                (dev_role_id, perm_id)
            )

        # 创建默认管理员账号（密码: admin123）
        admin_hash = get_password_hash("admin123")
        cursor.execute(
            "INSERT INTO users (username, password_hash, real_name, email, is_active) VALUES (?, ?, ?, ?, ?)",
            ("admin", admin_hash, "系统管理员", "admin@local", 1)
        )
        admin_user_id = cursor.lastrowid
        cursor.execute(
            "INSERT INTO user_roles (user_id, role_id) VALUES (?, ?)",
            (admin_user_id, admin_role_id)
        )

        conn.commit()
        logger.info("用户管理默认数据初始化完成")


# 在模块导入时初始化默认数据
_init_default_data()


@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    """用户登录"""
    with get_metadata_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, username, password_hash, real_name, email, is_active FROM users WHERE username = ?",
            (request.username,)
        )
        row = cursor.fetchone()

    if row is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")

    user = dict(row)
    if not verify_password(request.password, user["password_hash"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")

    if not user["is_active"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号已被禁用")

    # 查询用户角色
    with get_metadata_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT r.name FROM roles r
            JOIN user_roles ur ON r.id = ur.role_id
            WHERE ur.user_id = ?
        """, (user["id"],))
        roles = [r["name"] for r in cursor.fetchall()]

    token_data = {"sub": str(user["id"]), "username": user["username"]}
    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)

    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user={
            "id": user["id"],
            "username": user["username"],
            "real_name": user["real_name"],
            "email": user["email"],
            "is_active": bool(user["is_active"]),
            "roles": roles,
            "created_at": None,
        }
    )


@router.post("/refresh")
async def refresh_token(request: RefreshTokenRequest):
    """刷新 Access Token"""
    payload = decode_token(request.refresh_token)
    if payload is None or payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效的刷新令牌")

    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效的刷新令牌")

    # 验证用户是否仍然存在且启用
    user = get_user_with_permissions(int(user_id))
    if user is None or not user.get("is_active", True):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在或已被禁用")

    token_data = {"sub": str(user_id), "username": user.get("username", "")}
    access_token = create_access_token(token_data)

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }


@router.get("/me", response_model=UserDetail)
async def get_me(current_user: dict = Depends(get_current_user)):
    """获取当前登录用户信息"""
    return UserDetail(
        id=current_user["id"],
        username=current_user["username"],
        real_name=current_user.get("real_name"),
        email=current_user.get("email"),
        is_active=current_user.get("is_active", True),
        roles=current_user.get("role_names", []),
        permissions=current_user.get("permissions", []),
    )

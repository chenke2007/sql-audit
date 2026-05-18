"""
用户管理相关 Pydantic 模型
"""

from typing import Optional, List
from pydantic import BaseModel, Field


# ========== 认证模型 ==========

class LoginRequest(BaseModel):
    """登录请求"""
    username: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=1, max_length=100)


class RefreshTokenRequest(BaseModel):
    """刷新 Token 请求"""
    refresh_token: str = Field(..., min_length=1)


class TokenResponse(BaseModel):
    """Token 响应"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class LoginResponse(BaseModel):
    """登录响应"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: "UserInfo"


# ========== 用户模型 ==========

class UserBase(BaseModel):
    """用户基础信息"""
    username: str = Field(..., min_length=2, max_length=50)
    real_name: Optional[str] = Field(None, max_length=100)
    email: Optional[str] = Field(None, max_length=100)


class UserCreate(UserBase):
    """创建用户请求"""
    password: str = Field(..., min_length=6, max_length=100)
    role_ids: List[int] = Field(default_factory=list)
    is_active: bool = True


class UserUpdate(BaseModel):
    """更新用户请求"""
    real_name: Optional[str] = Field(None, max_length=100)
    email: Optional[str] = Field(None, max_length=100)
    password: Optional[str] = Field(None, min_length=6, max_length=100)
    role_ids: Optional[List[int]] = None
    is_active: Optional[bool] = None


class UserInfo(BaseModel):
    """用户信息响应"""
    id: int
    username: str
    real_name: Optional[str] = None
    email: Optional[str] = None
    is_active: bool
    roles: List[str] = []
    created_at: Optional[str] = None


class UserDetail(UserInfo):
    """用户详细信息（包含权限）"""
    permissions: List[str] = []


class ChangePasswordRequest(BaseModel):
    """修改密码请求"""
    old_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=6, max_length=100)


# ========== 角色模型 ==========

class RoleBase(BaseModel):
    """角色基础信息"""
    name: str = Field(..., min_length=1, max_length=50)
    description: Optional[str] = Field(None, max_length=255)


class RoleCreate(RoleBase):
    """创建角色请求"""
    pass


class RoleUpdate(BaseModel):
    """更新角色请求"""
    name: Optional[str] = Field(None, min_length=1, max_length=50)
    description: Optional[str] = Field(None, max_length=255)


class RoleInfo(BaseModel):
    """角色信息响应"""
    id: int
    name: str
    description: Optional[str] = None
    permissions: List[str] = []


class RolePermissionUpdate(BaseModel):
    """更新角色权限请求"""
    permission_ids: List[int] = Field(default_factory=list)


# ========== 数据源权限模型 ==========

class DatasourcePermissionCreate(BaseModel):
    """创建数据源权限请求"""
    role_id: int
    db_source_id: str = Field(..., min_length=1)


class DatasourcePermissionInfo(BaseModel):
    """数据源权限信息"""
    role_id: int
    role_name: str
    db_source_id: str
    db_source_name: Optional[str] = None


# ========== 分析历史模型 ==========

class AnalysisHistoryCreate(BaseModel):
    """创建分析历史记录"""
    db_source_id: Optional[str] = None
    schema: Optional[str] = None
    sql_text: str
    sql_id: Optional[str] = None
    input_mode: str = "sql_text"
    result_json: Optional[str] = None
    risk_level: Optional[str] = None


class AnalysisHistoryItem(BaseModel):
    """分析历史列表项"""
    id: int
    db_source_name: Optional[str] = None
    schema: Optional[str] = None
    sql_text: str
    sql_id: Optional[str] = None
    input_mode: str
    risk_level: Optional[str] = None
    created_at: str
    username: Optional[str] = None


class AnalysisHistoryDetail(AnalysisHistoryItem):
    """分析历史详情"""
    result_json: Optional[str] = None
    user_id: int


class AnalysisHistoryListResponse(BaseModel):
    """分析历史列表响应"""
    items: List[AnalysisHistoryItem]
    total: int
    page: int
    page_size: int

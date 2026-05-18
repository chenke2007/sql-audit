# 用户管理与 RBAC 权限体系 — API 接口文档

版本: v1.0
日期: 2026-05-16
状态: 已确认
关联文档: REQUIREMENTS_USER_MANAGEMENT.md, DESIGN_USER_MANAGEMENT.md

---

## 认证方式

所有非公开接口需要在 HTTP Header 中携带：
```
Authorization: Bearer <access_token>
```

---

## 1. 认证接口

### 1.1 用户登录

```
POST /api/auth/login
Content-Type: application/json
```

**请求体：**
```json
{
  "username": "admin",
  "password": "admin123"
}
```

**响应 (200)：**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 900,
  "user": {
    "id": 1,
    "username": "admin",
    "real_name": "系统管理员",
    "roles": ["admin"]
  }
}
```

**错误响应：**
- 401: `{"detail": "用户名或密码错误"}`
- 403: `{"detail": "账号已被禁用"}`

---

### 1.2 刷新 Token

```
POST /api/auth/refresh
Content-Type: application/json
```

**请求体：**
```json
{
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

**响应 (200)：**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 900
}
```

---

### 1.3 获取当前用户信息

```
GET /api/auth/me
Authorization: Bearer <token>
```

**响应 (200)：**
```json
{
  "id": 1,
  "username": "admin",
  "real_name": "系统管理员",
  "email": "admin@local",
  "roles": ["admin"],
  "permissions": ["user:manage", "role:manage", "datasource:manage", "..."]
}
```

---

## 2. 用户管理接口（需要 user:manage 权限）

### 2.1 获取用户列表

```
GET /api/users
Authorization: Bearer <token>
```

**响应 (200)：**
```json
{
  "users": [
    {
      "id": 1,
      "username": "admin",
      "real_name": "系统管理员",
      "email": "admin@local",
      "is_active": true,
      "roles": ["admin"],
      "created_at": "2026-05-16T09:00:00"
    }
  ],
  "total": 1
}
```

---

### 2.2 创建用户

```
POST /api/users
Authorization: Bearer <token>
Content-Type: application/json
```

**请求体：**
```json
{
  "username": "zhangsan",
  "password": "initial123",
  "real_name": "张三",
  "email": "zhangsan@company.com",
  "role_ids": [3]
}
```

**响应 (201)：**
```json
{
  "id": 2,
  "username": "zhangsan",
  "real_name": "张三",
  "email": "zhangsan@company.com",
  "is_active": true,
  "roles": ["developer"],
  "created_at": "2026-05-16T09:00:00"
}
```

---

### 2.3 更新用户

```
PUT /api/users/{user_id}
Authorization: Bearer <token>
Content-Type: application/json
```

**请求体：**
```json
{
  "real_name": "张三（ updated）",
  "email": "new@company.com",
  "role_ids": [2, 3],
  "is_active": true
}
```

**响应 (200)：** 更新后的用户对象

---

### 2.4 删除/禁用用户

```
DELETE /api/users/{user_id}
Authorization: Bearer <token>
```

**响应 (200)：**
```json
{
  "message": "用户已禁用"
}
```

> 注：实际操作为禁用（is_active = 0），而非物理删除，保留历史数据。

---

### 2.5 修改密码

```
POST /api/users/{user_id}/change-password
Authorization: Bearer <token>
Content-Type: application/json
```

**请求体：**
```json
{
  "old_password": "current_password",
  "new_password": "new_password123"
}
```

**响应 (200)：**
```json
{
  "message": "密码修改成功"
}
```

---

## 3. 角色管理接口（需要 role:manage 权限）

### 3.1 获取角色列表

```
GET /api/roles
Authorization: Bearer <token>
```

**响应 (200)：**
```json
{
  "roles": [
    {
      "id": 1,
      "name": "admin",
      "description": "系统管理员",
      "permissions": ["user:manage", "role:manage", "..."]
    }
  ]
}
```

---

### 3.2 获取角色权限详情

```
GET /api/roles/{role_id}/permissions
Authorization: Bearer <token>
```

**响应 (200)：**
```json
{
  "role_id": 1,
  "role_name": "admin",
  "permissions": [
    {
      "id": 1,
      "code": "user:manage",
      "name": "管理用户",
      "granted": true
    }
  ]
}
```

---

### 3.3 更新角色权限

```
PUT /api/roles/{role_id}/permissions
Authorization: Bearer <token>
Content-Type: application/json
```

**请求体：**
```json
{
  "permission_ids": [1, 2, 3, 4, 5]
}
```

**响应 (200)：**
```json
{
  "message": "角色权限已更新"
}
```

---

## 4. 数据源授权接口（需要 datasource:assign 权限）

### 4.1 获取数据源权限列表

```
GET /api/datasource-permissions
Authorization: Bearer <token>
```

**响应 (200)：**
```json
{
  "permissions": [
    {
      "role_id": 2,
      "role_name": "dba",
      "db_source_id": "source-001",
      "db_source_name": "生产数据库"
    }
  ]
}
```

---

### 4.2 给角色授权数据源

```
POST /api/datasource-permissions
Authorization: Bearer <token>
Content-Type: application/json
```

**请求体：**
```json
{
  "role_id": 3,
  "db_source_id": "source-001"
}
```

**响应 (201)：** 创建的授权记录

---

### 4.3 撤销数据源授权

```
DELETE /api/datasource-permissions
Authorization: Bearer <token>
Content-Type: application/json
```

**请求体：**
```json
{
  "role_id": 3,
  "db_source_id": "source-001"
}
```

**响应 (200)：**
```json
{
  "message": "授权已撤销"
}
```

---

## 5. 分析历史接口

### 5.1 获取当前用户的分析历史

```
GET /api/analysis-history
Authorization: Bearer <token>
```

**查询参数：**
- `page`: 页码，默认 1
- `page_size`: 每页条数，默认 20
- `keyword`: SQL 文本关键词搜索（可选）

**响应 (200)：**
```json
{
  "items": [
    {
      "id": 1,
      "db_source_name": "生产数据库",
      "schema": "OM",
      "sql_text": "SELECT * FROM users WHERE ...",
      "sql_id": "2dvu61d0wry48",
      "input_mode": "sql_id",
      "risk_level": "HIGH",
      "created_at": "2026-05-16T09:00:00"
    }
  ],
  "total": 100,
  "page": 1,
  "page_size": 20
}
```

---

### 5.2 获取单条分析历史详情

```
GET /api/analysis-history/{history_id}
Authorization: Bearer <token>
```

**响应 (200)：**
```json
{
  "id": 1,
  "user_id": 1,
  "db_source_id": "source-001",
  "schema": "OM",
  "sql_text": "SELECT * FROM users WHERE ...",
  "sql_id": "2dvu61d0wry48",
  "input_mode": "sql_id",
  "result_json": "{...}",
  "risk_level": "HIGH",
  "created_at": "2026-05-16T09:00:00"
}
```

---

### 5.3 获取所有人的分析历史（需要 analysis:history:all 权限）

```
GET /api/analysis-history/all
Authorization: Bearer <token>
```

**查询参数：** 同 5.1

**响应 (200)：** 同 5.1，额外包含 `username` 字段

---

### 5.4 删除分析历史

```
DELETE /api/analysis-history/{history_id}
Authorization: Bearer <token>
```

**响应 (200)：**
```json
{
  "message": "记录已删除"
}
```

> 注：用户只能删除自己的历史，管理员可以删除任何人的。

---

## 6. 现有接口改造

### 6.1 分析接口（/api/analyze/*）

所有现有分析接口需要：
1. 添加 `@require_auth` 认证检查
2. 从 JWT 中获取当前用户 ID
3. 分析完成后自动存入 `analysis_history` 表
4. 数据源下拉框按用户权限过滤

### 6.2 数据源接口（/api/db-sources/*）

- `GET /api/db-sources`：按当前用户角色过滤，只返回有权限的数据源
- `POST /api/db-sources`：需要 `datasource:manage` 权限
- `DELETE /api/db-sources/{id}`：需要 `datasource:manage` 权限

### 6.3 采集接口（/api/collect/*）

- 添加 `@require_auth` 认证检查
- 数据源选择按用户权限过滤

---

## 7. 错误码统一

| 状态码 | 场景 | 响应示例 |
|--------|------|---------|
| 401 | 未提供 Token 或 Token 无效 | `{"detail": "未提供有效的认证凭证"}` |
| 401 | Token 过期 | `{"detail": "认证已过期，请重新登录"}` |
| 403 | 权限不足 | `{"detail": "没有权限执行此操作"}` |
| 403 | 用户被禁用 | `{"detail": "账号已被禁用"}` |
| 404 | 用户/角色/记录不存在 | `{"detail": "用户不存在"}` |
| 409 | 用户名已存在 | `{"detail": "用户名已存在"}` |
| 422 | 请求参数验证失败 | `{"detail": [{"loc": ["body", "username"], "msg": "用户名不能为空"}]}` |

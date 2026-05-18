# 用户管理与 RBAC 权限体系 — 设计文档

版本: v1.0
日期: 2026-05-16
状态: 已确认
关联需求: REQUIREMENTS_USER_MANAGEMENT.md

---

## 1. 设计目标

为 SQL Audit System 引入完整的用户认证和 RBAC 权限控制，使系统从"无状态工具"升级为"多用户企业应用"。

## 2. 技术选型

| 组件 | 选型 | 理由 |
|------|------|------|
| 认证方式 | JWT (HS256) | 无状态、适合 SPA、FastAPI 生态成熟 |
| 密码哈希 | bcrypt (passlib) | 业界标准、安全性高、Python 原生支持 |
| 数据库 | SQLite（复用现有） | 零部署成本、项目已有基础设施 |
| ORM/DB 操作 | 原生 SQL + sqlite3 | 项目现有模式，保持一致性 |
| Token 存储 | HTTP Header (Bearer) | SPA 标准做法 |
| 前端状态 | Vue reactive + localStorage | 无需引入 Vuex/Pinia，保持轻量 |

## 3. 架构设计

### 3.1 整体架构

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Vue 3 SPA     │────▶│   FastAPI       │────▶│   SQLite        │
│   (Frontend)    │◀────│   (Backend)     │◀────│   (Database)    │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                              │
                              ▼
                        ┌─────────────┐
                        │ JWT Token   │
                        │ (HS256)     │
                        └─────────────┘
```

### 3.2 认证流程

```
1. 用户输入用户名密码
   ↓
2. POST /api/auth/login
   ↓
3. 后端验证 bcrypt 哈希
   ↓
4. 生成 JWT (access_token + refresh_token)
   ↓
5. 前端存储 token 到 localStorage
   ↓
6. 后续请求携带 Authorization: Bearer <token>
   ↓
7. 后端 JWT 中间件解析并验证
   ↓
8. 请求进入路由处理函数
```

### 3.3 权限检查流程

```
1. 用户请求 /api/users (需要 user:manage 权限)
   ↓
2. JWT 中间件解析当前用户 ID
   ↓
3. RBAC 中间件查询用户角色和权限码
   ↓
4. 检查用户是否拥有 user:manage 权限码
   ↓
5. 有权限 → 继续执行路由函数
   无权限 → 返回 403 Forbidden
```

## 4. 数据模型设计

### 4.1 E-R 关系图

```
┌─────────────┐       ┌─────────────┐       ┌─────────────┐
│   users     │       │   roles     │       │ permissions │
├─────────────┤       ├─────────────┤       ├─────────────┤
│ id          │       │ id          │       │ id          │
│ username    │       │ name        │       │ code        │
│ password_hash│      │ description │       │ name        │
│ real_name   │       └─────────────┘       │ description │
│ email       │              │              └─────────────┘
│ is_active   │              │                     │
│ created_at  │              │                     │
└─────────────┘              │                     │
       │                     │                     │
       │              ┌──────┴──────┐              │
       │              │ user_roles  │              │
       │              ├─────────────┤              │
       └─────────────▶│ user_id     │              │
                      │ role_id     │              │
                      └─────────────┘              │
                                                   │
                            ┌──────────────────────┘
                            │
                     ┌──────┴──────────┐
                     │ role_permissions│
                     ├─────────────────┤
                     │ role_id         │
                     │ permission_id   │
                     └─────────────────┘
```

### 4.2 数据源权限扩展

```
┌─────────────┐       ┌──────────────────────┐
│   roles     │       │ datasource_permissions│
├─────────────┤       ├──────────────────────┤
│ id          │◀──────│ role_id              │
│ name        │       │ db_source_id         │
└─────────────┘       └──────────────────────┘
```

### 4.3 分析历史

```
┌──────────────────┐
│ analysis_history │
├──────────────────┤
│ id               │
│ user_id          │──▶ users.id
│ db_source_id     │──▶ db_sources.id (nullable)
│ schema           │
│ sql_text         │
│ sql_id           │
│ input_mode       │
│ result_json      │
│ risk_level       │
│ created_at       │
└──────────────────┘
```

## 5. 权限模型设计

### 5.1 权限码列表

| 权限码 | 说明 | admin | dba | developer |
|--------|------|-------|-----|-----------|
| `user:manage` | 管理用户 | ✅ | ❌ | ❌ |
| `role:manage` | 管理角色和权限 | ✅ | ❌ | ❌ |
| `datasource:manage` | 增删改数据源 | ✅ | ✅ | ❌ |
| `datasource:assign` | 数据源授权 | ✅ | ❌ | ❌ |
| `datasource:use` | 使用数据源分析 | ✅ | ✅ | ✅ |
| `analysis:execute` | 执行 SQL 分析 | ✅ | ✅ | ✅ |
| `analysis:history:all` | 查看所有人历史 | ✅ | ❌ | ❌ |
| `analysis:history:own` | 查看自己历史 | ✅ | ✅ | ✅ |
| `system:audit` | 查看系统日志 | ✅ | ❌ | ❌ |

### 5.2 预置角色

| 角色 | 说明 | 默认权限 |
|------|------|---------|
| `admin` | 系统管理员 | 全部权限 |
| `dba` | 数据库管理员 | datasource:use, datasource:manage, analysis:execute, analysis:history:own |
| `developer` | 开发人员 | datasource:use, analysis:execute, analysis:history:own |

## 6. 模块设计

### 6.1 后端模块结构

```
app/
├── api/
│   └── routes/
│       ├── auth.py          # 认证接口 (login/refresh/me)
│       ├── users.py         # 用户管理接口
│       ├── roles.py         # 角色管理接口
│       └── analysis_history.py  # 分析历史接口
├── core/
│   ├── auth.py              # JWT 工具、密码工具
│   ├── rbac.py              # RBAC 中间件、权限检查
│   └── user_repository.py   # 用户/角色/权限数据访问
├── models/
│   └── user_models.py       # Pydantic 模型
```

### 6.2 前端模块结构

```
frontend/
├── index.html               # 主入口（新增登录状态判断）
└── static/
    └── ...
```

## 7. 安全设计

### 7.1 密码安全

- 使用 bcrypt 哈希，salt rounds = 12
- 密码最小长度：8 位
- 密码传输使用 HTTPS（生产环境）

### 7.2 Token 安全

- JWT Secret 从环境变量读取，不硬编码
- Access token 过期：15 分钟
- Refresh token 过期：7 天
- Token 使用 HS256 签名

### 7.3 接口安全

- 所有非公开接口需要 `Authorization: Bearer <token>`
- 管理接口额外检查权限码
- 用户只能操作自己的数据（除非有 admin 权限）

## 8. 错误处理

| 场景 | HTTP 状态码 | 错误消息 |
|------|------------|---------|
| 用户名或密码错误 | 401 | 用户名或密码错误 |
| Token 过期 | 401 | Token 已过期，请重新登录 |
| Token 无效 | 401 | 无效的认证凭证 |
| 权限不足 | 403 | 没有权限执行此操作 |
| 用户被禁用 | 403 | 账号已被禁用 |

## 9. 风险与应对

| 风险 | 影响 | 应对 |
|------|------|------|
| Token 泄露 | 高 | 短期 access token + HTTPS |
| 密码暴力破解 | 中 | bcrypt 慢哈希 + 登录频率限制（二期） |
| 权限配置错误 | 高 | 默认最小权限原则 + 管理界面验证 |
| 分析历史数据量大 | 中 | 定期归档或限制保留条数（二期） |

## 10. 后续扩展（二期）

- 对接企业 LDAP/AD 认证
- 登录频率限制和账号锁定
- 用户头像和个人信息
- 操作日志详细记录（IP、UA 等）
- 分析历史数据压缩/归档
- 批量用户导入

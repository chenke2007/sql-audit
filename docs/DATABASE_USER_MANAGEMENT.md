# 用户管理与 RBAC 权限体系 — 数据库设计文档

版本: v1.0
日期: 2026-05-16
状态: 已确认
关联文档: REQUIREMENTS_USER_MANAGEMENT.md, DESIGN_USER_MANAGEMENT.md

---

## 1. 数据库选择

复用项目现有的 **SQLite** 数据库（`data/sql_audit_metadata.db`），新增用户相关的表。

## 2. 表结构定义

### 2.1 users（用户表）

```sql
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    real_name TEXT,
    email TEXT,
    is_active INTEGER DEFAULT 1,  -- 0=禁用, 1=启用
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_users_active ON users(is_active);
```

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | INTEGER | PK, AUTOINCREMENT | 用户 ID |
| username | TEXT | UNIQUE, NOT NULL | 登录用户名 |
| password_hash | TEXT | NOT NULL | bcrypt 哈希后的密码 |
| real_name | TEXT | | 真实姓名 |
| email | TEXT | | 邮箱 |
| is_active | INTEGER | DEFAULT 1 | 是否启用 |
| created_at | DATETIME | DEFAULT CURRENT_TIMESTAMP | 创建时间 |
| updated_at | DATETIME | DEFAULT CURRENT_TIMESTAMP | 更新时间 |

### 2.2 roles（角色表）

```sql
CREATE TABLE IF NOT EXISTS roles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    description TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_roles_name ON roles(name);
```

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | INTEGER | PK, AUTOINCREMENT | 角色 ID |
| name | TEXT | UNIQUE, NOT NULL | 角色标识（admin/dba/developer） |
| description | TEXT | | 角色描述 |
| created_at | DATETIME | DEFAULT CURRENT_TIMESTAMP | 创建时间 |

### 2.3 permissions（权限表）

```sql
CREATE TABLE IF NOT EXISTS permissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_permissions_code ON permissions(code);
```

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | INTEGER | PK, AUTOINCREMENT | 权限 ID |
| code | TEXT | UNIQUE, NOT NULL | 权限码（datasource:manage） |
| name | TEXT | NOT NULL | 权限名称 |
| description | TEXT | | 权限描述 |
| created_at | DATETIME | DEFAULT CURRENT_TIMESTAMP | 创建时间 |

### 2.4 user_roles（用户-角色关联表）

```sql
CREATE TABLE IF NOT EXISTS user_roles (
    user_id INTEGER NOT NULL,
    role_id INTEGER NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, role_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (role_id) REFERENCES roles(id) ON DELETE CASCADE
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_user_roles_user ON user_roles(user_id);
CREATE INDEX IF NOT EXISTS idx_user_roles_role ON user_roles(role_id);
```

### 2.5 role_permissions（角色-权限关联表）

```sql
CREATE TABLE IF NOT EXISTS role_permissions (
    role_id INTEGER NOT NULL,
    permission_id INTEGER NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (role_id, permission_id),
    FOREIGN KEY (role_id) REFERENCES roles(id) ON DELETE CASCADE,
    FOREIGN KEY (permission_id) REFERENCES permissions(id) ON DELETE CASCADE
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_role_permissions_role ON role_permissions(role_id);
CREATE INDEX IF NOT EXISTS idx_role_permissions_perm ON role_permissions(permission_id);
```

### 2.6 datasource_permissions（数据源-角色权限绑定表）

```sql
CREATE TABLE IF NOT EXISTS datasource_permissions (
    role_id INTEGER NOT NULL,
    db_source_id TEXT NOT NULL,  -- 关联 db_sources.id
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (role_id, db_source_id),
    FOREIGN KEY (role_id) REFERENCES roles(id) ON DELETE CASCADE
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_ds_permissions_role ON datasource_permissions(role_id);
CREATE INDEX IF NOT EXISTS idx_ds_permissions_source ON datasource_permissions(db_source_id);
```

### 2.7 analysis_history（分析历史表）

```sql
CREATE TABLE IF NOT EXISTS analysis_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    db_source_id TEXT,  -- 可为空（未选择数据源时）
    schema TEXT,
    sql_text TEXT NOT NULL,
    sql_id TEXT,
    input_mode TEXT NOT NULL DEFAULT 'sql_text',  -- sql_text/sql_id/file_upload
    result_json TEXT,  -- 分析结果的 JSON 字符串
    risk_level TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_history_user ON analysis_history(user_id);
CREATE INDEX IF NOT EXISTS idx_history_created ON analysis_history(created_at);
```

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | INTEGER | PK, AUTOINCREMENT | 历史记录 ID |
| user_id | INTEGER | NOT NULL, FK | 执行分析的用户 |
| db_source_id | TEXT | | 使用的数据源 ID |
| schema | TEXT | | 使用的 Schema |
| sql_text | TEXT | NOT NULL | 分析的 SQL 文本 |
| sql_id | TEXT | | SQL_ID（如果适用） |
| input_mode | TEXT | DEFAULT 'sql_text' | 输入方式 |
| result_json | TEXT | | 完整分析结果 JSON |
| risk_level | TEXT | | 风险等级 |
| created_at | DATETIME | DEFAULT CURRENT_TIMESTAMP | 分析时间 |

## 3. 初始数据

### 3.1 预置角色

```sql
INSERT INTO roles (name, description) VALUES
('admin', '系统管理员，拥有所有权限'),
('dba', '数据库管理员，可管理数据源和执行分析'),
('developer', '开发人员，可执行分析');
```

### 3.2 预置权限

```sql
INSERT INTO permissions (code, name, description) VALUES
('user:manage', '管理用户', '创建、编辑、禁用用户'),
('role:manage', '管理角色', '配置角色权限'),
('datasource:manage', '管理数据源', '增删改数据源配置'),
('datasource:assign', '数据源授权', '给角色分配数据源权限'),
('datasource:use', '使用数据源', '使用数据源执行分析'),
('analysis:execute', '执行分析', '执行 SQL 分析'),
('analysis:history:all', '查看全部历史', '查看所有人的分析历史'),
('analysis:history:own', '查看自己的历史', '查看自己的分析历史'),
('system:audit', '系统审计', '查看系统操作日志');
```

### 3.3 预置角色权限绑定

```sql
-- admin 拥有所有权限
INSERT INTO role_permissions (role_id, permission_id)
SELECT 1, id FROM permissions;

-- dba 权限
INSERT INTO role_permissions (role_id, permission_id) VALUES
(2, (SELECT id FROM permissions WHERE code = 'datasource:use')),
(2, (SELECT id FROM permissions WHERE code = 'datasource:manage')),
(2, (SELECT id FROM permissions WHERE code = 'analysis:execute')),
(2, (SELECT id FROM permissions WHERE code = 'analysis:history:own'));

-- developer 权限
INSERT INTO role_permissions (role_id, permission_id) VALUES
(3, (SELECT id FROM permissions WHERE code = 'datasource:use')),
(3, (SELECT id FROM permissions WHERE code = 'analysis:execute')),
(3, (SELECT id FROM permissions WHERE code = 'analysis:history:own'));
```

### 3.4 默认管理员账号

```sql
-- 密码: admin123 (bcrypt 哈希)
INSERT INTO users (username, password_hash, real_name, email, is_active) VALUES
('admin', '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewKyNiAYMyzJ/IhK', '系统管理员', 'admin@local', 1);

INSERT INTO user_roles (user_id, role_id) VALUES (1, 1);
```

## 4. 关系图

```
users (1) ────< (N) user_roles (N) >──── (1) roles (1) ────< (N) role_permissions (N) >──── (1) permissions
  │
  │
  └──< (N) analysis_history

roles (1) ────< (N) datasource_permissions
```

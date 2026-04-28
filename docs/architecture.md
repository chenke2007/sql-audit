# 系统架构

## 整体架构

```
+------------------+     +------------------+     +------------------+
|     前端 UI      |     |    FastAPI       |     |   Oracle DB      |
|  Vue3 + Tailwind |<--->|   REST API       |<--->|  (目标数据库)     |
|                  |     |                  |     |                  |
+------------------+     +------------------+     +------------------+
                                |   |
                                |   +--> SQLite (元数据)
                                |
                                +--> LLM API (智能分析)
```

## 核心模块

### 1. API 层 (`app/api/routes/`)

| 模块 | 职责 |
|------|------|
| `analyze.py` | SQL 分析接口：单条/批量分析、规则管理、PDF 导出 |
| `collect.py` | SQL 采集接口：慢 SQL 采集、SQL_ID 查询、文件上传 |
| `db_sources.py` | 数据源管理：CRUD、连接测试、Schema 列表 |

### 2. 分析引擎 (`app/core/`)

| 模块 | 职责 |
|------|------|
| `rule_engine.py` | 规则引擎：基于 AST 的静态分析，检测 SQL 反模式 |
| `llm_analyzer.py` | LLM 分析：构建结构化 prompt，调用大模型生成优化建议 |
| `preprocessing.py` | SQL 预处理：解析 SQL 文本，提取表引用、操作类型等 |
| `pdf_exporter.py` | PDF 导出：生成格式化的分析报告 |

### 3. Oracle 模块 (`app/oracle/`)

| 模块 | 职责 |
|------|------|
| `client.py` | 连接池管理：基于 python-oracledb 的连接池 |
| `collector.py` | SQL 采集器：从 v$sql 和 AWR 采集慢 SQL |
| `metadata.py` | 元数据获取：表结构、索引、统计信息、约束 |

### 4. 数据源管理 (`app/core/database.py`)

使用 SQLite 存储数据源配置：
- 数据源基本信息（host、port、认证信息）
- 默认数据源标记
- 密码加密存储

### 5. Oracle 连接模式

```
应用启动
    |
    +--> oracle_client_init.init_thick_mode()
            |
            +--> 检测平台 (macOS/Linux)
            +--> 定位 instantclient 目录
            +--> 调用 oracledb.init_oracle_client()
            |
    +--> 所有连接自动使用 thick 模式
```

连接优先级：
1. **thick 模式**：支持 Oracle 11g+，通过 Instant Client 实现
2. **thin 模式**：纯 Python，仅支持 Oracle 12.1+

当 thin 模式遇到 DPY-3010（版本太旧）时，自动 fallback 到 thick 模式。

## 数据流

### SQL 分析流程

```
用户输入 SQL
    |
    +--> SQL 预处理（preprocessing）
            +--> 解析 SQL AST
            +--> 提取表引用（TableRef）
            +--> 识别 DML 类型
    |
    +--> 元数据获取（metadata）
            +--> 查询 all_tables
            +--> 查询 all_tab_columns
            +--> 查询 all_indexes
            +--> 查询 all_constraints / all_tab_col_statistics
    |
    +--> 规则引擎分析（rule_engine）
            +--> SELECT * 检测
            +--> 缺少 WHERE 检测
            +--> 隐式类型转换检测
            +--> LIKE 前导通配符检测
            +--> ...（共 10+ 条规则）
    |
    +--> LLM 智能分析（llm_analyzer）
            +--> 构建结构化 prompt（SQL + 执行计划 + 元数据）
            +--> 调用大模型 API
            +--> 解析返回结果
    |
    +--> 结果聚合
            +--> 规则结果 + LLM 建议 + 元数据注释
    |
    +--> 前端展示 / PDF 导出
```

### 慢 SQL 采集流程

```
定时/手动触发
    |
    +--> DynamicOracleClient.connect_to_source(source_id)
            +--> 从 SQLite 读取数据源配置
            +--> 建立 Oracle 连接
    |
    +--> SQLCollector.collect_slow_sqls()
            +--> 查询 v$sql（兼容 ROWNUM 语法）
            +--> 应用阈值过滤
            +--> 排除系统 SQL
    |
    +--> 返回 SQLObject 列表
```

## 规则引擎

规则基于 SQL AST（抽象语法树）进行静态分析：

| 规则 ID | 名称 | 严重级别 | 检测逻辑 |
|---------|------|----------|----------|
| R001 | Avoid SELECT * | medium | 检测 SELECT * 用法 |
| R002 | Missing WHERE Clause | critical | 检测缺少 WHERE 子句 |
| R003 | Implicit Type Conversion | high | 检测隐式类型转换 |
| R004 | LIKE Leading Wildcard | high | 检测 LIKE 前导 % |
| R005 | Large IN Clause | medium | 检测 IN 元素过多（>1000） |
| R006 | Not Equal Operator | low | 检测 != / <> 操作符 |
| R007 | Cartesian Product Risk | high | 检测无 JOIN 条件的多表查询 |
| R008 | Correlated Subquery | medium | 检测关联子查询 |
| R009 | ORDER BY No Index | low | 检测 ORDER BY 列缺少索引 |
| R010 | Missing Index Suggestion | medium | 基于 WHERE 条件建议索引 |

规则可动态启用/禁用，通过 `/api/analyze/rules/{rule_id}/toggle` 接口控制。

## LLM 分析 Prompt 结构

```
系统角色：Oracle SQL 优化专家

输入内容：
1. SQL 文本（格式化）
2. 执行计划（树形结构）
3. 表元数据（列信息、索引、统计信息）
4. 约束信息（主键、外键）

输出格式（结构化 JSON）：
- summary: 问题总结
- issues: 具体问题列表（含严重级别）
- suggestions: 优化建议
- rewritten_sql: 改写后的 SQL（如有）
- indexes: 建议创建的索引
```

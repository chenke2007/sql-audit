# 变更日志

## [1.2.0] - 2026-04-28

### 新增
- 动态数据源管理：支持配置多个 Oracle 数据库连接，分析时可动态切换
- Oracle Instant Client thick 模式支持：项目已包含 Linux x64 版本客户端库，支持 Oracle 11g 连接
- 平台自动检测：`oracle_client_init.py` 根据运行平台自动选择对应的 Instant Client 目录
- Schema 感知分析：SQL 分析时自动获取并传入表结构、索引、统计信息、约束等元数据
- Schema 选择器：前端分析页面支持选择目标 Schema
- 元数据来源标注：分析结果中标注每条建议的数据来源（规则引擎 / LLM / 元数据）
- 重复索引检测：在索引建议中标记已存在的重复或覆盖索引
- 智能 SQL 格式化：分析前自动格式化 SQL，提升可读性
- PDF 报告导出：支持将分析结果导出为 PDF 格式

### 修复
- Oracle 11g 兼容性：将 `FETCH FIRST ... ROWS ONLY` 语法改为 `ROWNUM` 包装
- DPY-3010 错误处理：thin 模式遇到旧版 Oracle 时自动 fallback 到 thick 模式
- 错误提示优化：移除"联系 DBA 升级"、"安装 Instant Client"等误导性提示
- 修复后端错误消息重复前缀问题

### 变更
- `requirements.txt`：oracledb 版本从 2.0.0 更新至 3.4.2
- `.gitignore`：仅忽略 macOS ARM64 版 Instant Client，Linux x64 版本纳入版本控制
- 前端 UI 重构：数据源管理页面、分析结果展示优化

## [1.1.1] - 2026-03-27

### 修复
- 修复 QA 发现的 3 个问题

## [1.1.0] - 2026-03-26

### 新增
- SQL 规则引擎：10 条内置审核规则
- LLM 智能分析：集成 SCNet API（MiniMax-M2.5 模型）
- 批量 SQL 分析支持
- 规则动态开关
- 单页面 Web UI（Vue 3 + Tailwind CSS）

## [1.0.1] - 2026-03-20

### 新增
- 基础 SQL 采集功能（v$sql 慢 SQL 扫描）
- SQL_ID 查询
- 文件上传分析
- FastAPI 基础框架
- Oracle 连接池管理

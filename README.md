# SQL 智能审核系统

基于 AI 的 SQL 性能分析与优化系统，支持 Oracle 数据库的智能审核、慢 SQL 采集、执行计划分析和优化建议生成。

## 功能特性

### SQL 分析
- **规则引擎分析**：内置 10+ 条 SQL 审核规则，自动检测性能隐患
- **LLM 智能分析**：调用大语言模型进行深度分析，提供优化建议和 SQL 改写
- **执行计划解析**：自动获取并解析 Oracle 执行计划，识别全表扫描等性能问题
- **Schema 感知分析**：自动获取表结构、索引、统计信息，结合元数据进行精准分析

### SQL 采集
- **自动采集**：从 Oracle v$sql 视图扫描慢 SQL（支持 Top N、阈值筛选）
- **SQL_ID 查询**：根据 SQL_ID 查询特定 SQL 的完整文本和执行统计
- **文件上传**：支持 SQL 文件批量上传分析

### 数据源管理
- **多数据源支持**：支持配置多个 Oracle 数据库连接，动态切换
- **连接测试**：实时测试数据源连通性
- **Schema 切换**：分析时支持指定不同 Schema

### 报告与导出
- **PDF 报告导出**：生成格式化的分析报告
- **批量分析**：支持同时分析多条 SQL
- **规则开关**：可动态启用/禁用特定审核规则

## 技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| 后端框架 | FastAPI | Python 异步 Web 框架 |
| 数据库驱动 | python-oracledb | Oracle 数据库连接（thin + thick 双模式） |
| 元数据存储 | SQLite | 数据源配置等元数据 |
| 前端 | Vue 3 + Tailwind CSS | 单页面应用，无需构建 |
| AI 分析 | OpenAI 兼容 API | 支持 Qwen、MiniMax 等大模型 |
| 规则引擎 | 自定义 | 基于 AST 的 SQL 解析与规则匹配 |
| 报告生成 | WeasyPrint | PDF 导出 |

## 快速开始

### 环境要求

- Python 3.9+
- Oracle 数据库（目标审计数据库）
- OpenAI 兼容的 LLM API（可选，用于智能分析）

### 1. 克隆项目

```bash
git clone --branch v1.2.0 https://github.com/chenke2007/sql-audit.git
cd sql-audit
```

### 2. 创建虚拟环境

```bash
python3 -m venv venv
source venv/bin/activate  # Linux/macOS
# venv\Scripts\activate   # Windows
```

### 3. 安装依赖

```bash
pip install -r requirements.txt
```

### 4. 配置环境变量

创建 `.env` 文件：

```env
# Oracle 默认数据源配置
ORACLE_HOST=192.168.13.82
ORACLE_PORT=1522
ORACLE_SERVICE_NAME=omdb
ORACLE_USERNAME=sqlaudit
ORACLE_PASSWORD=your_password

# LLM API 配置
LLM_BASE_URL=https://api.scnet.cn/api/llm/v1
LLM_MODEL_NAME=MiniMax-M2.5
LLM_API_KEY=your_api_key

# 应用配置
APP_DEBUG=false
APP_LOG_LEVEL=INFO
```

### 5. 启动服务

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

访问 http://localhost:8000 使用系统。

## 项目结构

```
sql-audit/
├── app/                          # 后端应用
│   ├── main.py                   # FastAPI 入口
│   ├── config.py                 # 配置管理
│   ├── api/routes/               # API 路由
│   │   ├── analyze.py            # SQL 分析接口
│   │   ├── collect.py            # SQL 采集接口
│   │   └── db_sources.py         # 数据源管理接口
│   ├── core/                     # 核心模块
│   │   ├── rule_engine.py        # 规则引擎
│   │   ├── llm_analyzer.py       # LLM 分析
│   │   ├── preprocessing.py      # SQL 预处理
│   │   ├── database.py           # 数据源管理（SQLite）
│   │   ├── dynamic_db_client.py  # 动态数据库连接
│   │   ├── oracle_client_init.py # Oracle thick 模式初始化
│   │   ├── pdf_exporter.py       # PDF 报告导出
│   │   └── security.py           # 密码加密
│   ├── oracle/                   # Oracle 相关
│   │   ├── client.py             # Oracle 连接池管理
│   │   ├── collector.py          # SQL 采集器
│   │   └── metadata.py           # 元数据获取
│   └── analyzer/                 # 分析模块
├── frontend/                     # 前端（Vue 3 + Tailwind）
│   └── index.html                # 单页面应用
├── oracle_instantclient/         # Oracle Instant Client
│   └── linux_x64/                # Linux x64 版本（已提交）
├── downloads/                    # 原始安装包
│   ├── instantclient-basiclite-macos.arm64-...dmg
│   └── instantclient-basiclite-linux.x64-...zip
├── docs/                         # 文档
├── tests/                        # 测试
├── requirements.txt              # Python 依赖
└── README.md                     # 本文档
```

## Oracle 兼容性

| Oracle 版本 | 支持状态 | 说明 |
|-------------|----------|------|
| Oracle 11g | 支持 | 使用 thick 模式（项目已包含 Instant Client） |
| Oracle 12c+ | 支持 | 默认 thin 模式，无需额外配置 |
| Oracle 19c | 支持 | 测试通过 |

## API 文档

启动服务后访问：
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

主要 API 端点：

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/analyze/single` | POST | 单条 SQL 分析 |
| `/api/analyze/batch` | POST | 批量 SQL 分析 |
| `/api/analyze/by-sql-id` | POST | 通过 SQL_ID 分析 |
| `/api/analyze/rules` | GET | 列出所有规则 |
| `/api/analyze/export/pdf` | POST | 导出 PDF 报告 |
| `/api/collect/slow-sqls` | POST | 采集慢 SQL |
| `/api/collect/by-sql-id` | POST | SQL_ID 查询 |
| `/api/db-sources` | GET/POST | 数据源列表/创建 |
| `/api/db-sources/{id}/test` | POST | 测试数据源连接 |

## 配置说明

### Oracle 权限要求

自动采集和元数据获取需要以下权限：
- `v$sql`, `v$sql_plan` - 实时 SQL 信息
- `v$version` - 数据库版本
- `all_tables`, `all_tab_columns` - 表结构元数据
- `all_indexes`, `all_constraints` - 索引和约束信息
- `DBA_HIST_SQLSTAT`, `DBA_HIST_SQLTEXT` - AWR 历史数据（可选）

### LLM 配置

系统通过标准 OpenAI API 格式调用大模型，支持：
- 本地部署模型（vLLM、Ollama 等）
- 云端 API（SCNet、OpenAI、Claude 等）

配置项：
```env
LLM_BASE_URL=https://your-api-endpoint/v1
LLM_MODEL_NAME=your-model-name
LLM_API_KEY=your-api-key
LLM_TIMEOUT_SECONDS=60
LLM_MAX_TOKENS=4096
```

## 开发

### 运行测试

```bash
pytest tests/ -v
```

### 代码格式化

```bash
black app/
```

## 部署

详见 [docs/deploy.md](docs/deploy.md)。

## 版本历史

详见 [CHANGELOG.md](CHANGELOG.md)。

## License

内部项目

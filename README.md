# SQL 智能审核系统 (SQL Audit System)

基于AI的SQL性能分析与优化系统，支持自动采集慢SQL、SQL_ID查询和文件上传三种输入方式。

## 功能特性

- **多源SQL采集**
  - 自动采集：从Oracle v$sql扫描慢SQL
  - SQL_ID查询：根据sql_id查询特定SQL
  - 文件上传：支持SQL文件批量上传

- **AI智能分析**
  - 本地大模型(Qwen3.5)分析
  - 执行计划解析
  - 索引优化建议
  - SQL改写建议

- **DBA审核界面**
  - Web界面展示分析结果
  - 优化建议审核
  - 报告导出

## 技术栈

- **后端**: Python 3.9+, FastAPI
- **数据库**: Oracle (oracledb驱动)
- **AI**: 本地Qwen3.5 (OpenAI兼容API)
- **部署**: Docker

## 快速开始

### 1. 安装依赖

```bash
cd sql-audit
pip install -r requirements.txt
```

### 2. 配置环境变量

创建 `.env` 文件:

```env
# Oracle配置
ORACLE_HOST=localhost
ORACLE_PORT=1521
ORACLE_SERVICE_NAME=ORCL
ORACLE_USERNAME=system
ORACLE_PASSWORD=your_password

# 本地LLM配置
LLM_BASE_URL=http://localhost:8000/v1
LLM_MODEL_NAME=qwen3.5

# 应用配置
APP_DEBUG=true
APP_LOG_LEVEL=INFO
```

### 3. 启动服务

```bash
python -m app.main
```

访问 http://localhost:8000/docs 查看API文档。

### 4. 运行测试

```bash
pytest tests/ -v
```

## 项目结构

```
sql-audit/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI入口
│   ├── config.py            # 配置管理
│   ├── oracle/              # Oracle相关模块
│   │   ├── client.py        # 连接管理
│   │   └── collector.py     # SQL采集
│   ├── analyzer/            # 分析引擎
│   │   ├── rules/           # 规则引擎
│   │   └── llm_client.py    # LLM调用
│   └── reporter/            # 报告生成
├── tests/                   # 测试
├── requirements.txt         # 依赖
├── Dockerfile              # Docker构建
└── README.md               # 本文档
```

## 开发计划

详见 [PLAN.md](./PLAN.md)

## 配置说明

### Oracle权限要求

自动采集功能需要以下视图访问权限:
- `v$sql`, `v$sql_plan` - 实时SQL信息
- `DBA_HIST_SQLSTAT`, `DBA_HIST_SQLTEXT` - AWR历史数据(可选)

### 本地LLM配置

系统通过HTTP API调用本地部署的大模型，需要:
- OpenAI兼容的API接口
- 支持长文本输入(执行计划+SQL文本)

## License

内部项目
